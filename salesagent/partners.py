"""Channel-partner protection: client registration with partner builders, and the commission ledger.

Registration is sent in writing (WhatsApp + email) BEFORE the client visits a partner project, with a timestamp,
so a builder cannot later treat the buyer as a direct customer. The builder replies ACK R<no> (or DISPUTE).
Every booking on a partner project creates a commission entry that is tracked until the money is collected.
"""
from __future__ import annotations

from datetime import timedelta

from . import channels, db, inventory
from .config import get_settings
from .pricing import fmt_money


# ------------------------------------------------------------------ client registration

def active_registration(lead_id: int, project_id: int) -> dict | None:
    now = get_settings().now().isoformat()
    return db.q1("SELECT * FROM registrations WHERE lead_id = ? AND project_id = ? AND status IN ('sent','acknowledged') "
                 "AND valid_until > ? ORDER BY id DESC LIMIT 1", (lead_id, project_id, now))


def register_client(lead_id: int, project_ref, reason: str = "site visit", force: bool = False) -> dict:
    """Register this client with the partner builder of the project. Own projects need no registration."""
    s = get_settings()
    project = inventory.get_project(project_ref)
    if not project:
        return {"ok": False, "error": "Unknown project."}
    builder = inventory.builder_for(project)
    if builder.get("is_own", 1):
        return {"ok": True, "skipped": "own project"}
    existing = active_registration(lead_id, project["id"])
    if existing and not force:
        return {"ok": True, "registration_id": existing["id"], "already": True}
    lead = db.get_lead(lead_id)
    now = s.now()
    valid_until = now + timedelta(days=int(builder.get("registration_validity_days") or 90))
    rid = db.insert("registrations", {"lead_id": lead_id, "project_id": project["id"], "builder_id": builder["id"],
                                      "status": "sent", "reason": reason, "sent_at": now.isoformat(timespec="seconds"),
                                      "valid_until": valid_until.isoformat(timespec="seconds")})
    msg = (f"CLIENT REGISTRATION R{rid} — {s.business['name']} (channel partner)\n"
           f"Date/time: {now:%d %b %Y, %I:%M %p}\n"
           f"Project: {project['name']} ({project['city']})\n"
           f"Client: {lead['name'] or '-'}  ·  {lead['phone'] or lead['email'] or '-'}\n"
           f"Interest: {lead.get('unit_type') or '-'}, budget {fmt_money(lead.get('budget_max'))}\n"
           f"Reason: {reason}\n"
           f"Please register this client against {s.business['name']}. Valid until {valid_until:%d %b %Y}.\n"
           f"Reply  ACK R{rid}  to confirm, or  DISPUTE R{rid} <reason>  if this client is already with you.")
    db.update("registrations", rid, {"message": msg})
    sent_any = False
    if builder.get("contact_phone"):
        sent_any |= bool(channels.notify_staff(builder["contact_phone"], msg).get("ok"))
    if builder.get("contact_email"):
        sent_any |= bool(channels.send_email(builder["contact_email"],
                                             f"Client registration R{rid}: {lead['name'] or ''} for {project['name']}",
                                             msg).get("ok"))
    if not sent_any:
        channels.notify_staff(s.owner["phone"], f"⚠️ Could not send client registration R{rid} to {builder['name']}: "
                                                f"no contact phone/email saved for this builder. Please register "
                                                f"{lead['name']} for {project['name']} manually.")
    db.audit(lead_id, "system", "client_registered", {"registration_id": rid, "project": project["name"],
                                                      "builder": builder["name"], "sent": sent_any})
    return {"ok": True, "registration_id": rid, "sent": sent_any}


def builder_reply(phone: str, cmd: str, rid: int, note: str) -> str | None:
    """ACK / DISPUTE from a partner builder's contact. Returns a reply, or None if not that builder."""
    r = db.q1("SELECT * FROM registrations WHERE id = ?", (rid,))
    if not r:
        return f"Registration R{rid} not found."
    b = db.q1("SELECT * FROM builders WHERE id = ?", (r["builder_id"],))
    if db.normalize_phone(b.get("contact_phone")) != db.normalize_phone(phone):
        return None
    lead = db.get_lead(r["lead_id"])
    if cmd == "ACK":
        db.update("registrations", rid, {"status": "acknowledged", "ack_at": db.now_iso(), "builder_note": note})
        db.audit(r["lead_id"], "builder", "registration_ack", {"registration_id": rid})
        return f"Thank you — registration R{rid} for {lead['name']} confirmed."
    db.update("registrations", rid, {"status": "disputed", "ack_at": db.now_iso(), "builder_note": note})
    db.audit(r["lead_id"], "builder", "registration_disputed", {"registration_id": rid, "note": note})
    channels.notify_staff(get_settings().owner["phone"],
                          f"⚠️ {b['name']} DISPUTED registration R{rid} ({lead['name']}, lead #{lead['id']}): "
                          f"{note or 'no reason given'}. Check before the site visit.")
    return f"Noted — R{rid} marked disputed. Our team will contact you."


def is_builder_phone(phone: str) -> bool:
    p = db.normalize_phone(phone)
    return bool(p) and any(db.normalize_phone(b["contact_phone"]) == p
                           for b in db.q("SELECT contact_phone FROM builders WHERE is_own = 0 AND contact_phone != ''"))


def renew_expiring(days_before: int = 7) -> int:
    """Re-register active clients whose registration is about to expire."""
    soon = (get_settings().now() + timedelta(days=days_before)).isoformat()
    n = 0
    for r in db.q("SELECT r.* FROM registrations r JOIN leads l ON l.id = r.lead_id WHERE r.status IN "
                  "('sent','acknowledged') AND r.valid_until < ? AND l.stage NOT IN ('booked','lost') "
                  "AND r.id = (SELECT MAX(id) FROM registrations WHERE lead_id = r.lead_id AND "
                  "project_id = r.project_id)", (soon,)):
        db.update("registrations", r["id"], {"status": "expired"})
        register_client(r["lead_id"], r["project_id"], reason="renewal of earlier registration "
                                                              f"R{r['id']} (client still active)", force=True)
        n += 1
    return n


# ------------------------------------------------------------------ commission ledger

def record_commission(booking: dict, deal_value: int) -> int | None:
    if not booking.get("unit_id"):
        return None
    unit = db.q1("SELECT * FROM units WHERE id = ?", (booking["unit_id"],))
    project = inventory.get_project(unit["project_id"]) if unit else None
    if not project or project["is_own"]:
        return None
    builder = inventory.builder_for(project)
    amount = inventory.commission_for(project, deal_value)
    due = get_settings().now() + timedelta(days=int(builder.get("payment_terms_days") or 45))
    cid = db.insert("commissions", {"booking_id": booking["id"], "lead_id": booking["lead_id"],
                                    "project_id": project["id"], "builder_id": builder["id"], "unit_id": unit["id"],
                                    "deal_value": deal_value, "amount": amount, "status": "earned",
                                    "due_at": due.isoformat(timespec="seconds"), "created_at": db.now_iso()})
    reg = active_registration(booking["lead_id"], project["id"])
    warn = "" if reg else "\n⚠️ No active client registration found for this buyer — secure written confirmation now."
    channels.notify_staff(s_owner_phone(), f"💼 Commission earned C{cid}: {fmt_money(amount)} from {builder['name']} "
                                           f"({project['name']}, deal {fmt_money(deal_value)}). Due by "
                                           f"{due:%d %b %Y}. Raise the invoice and mark it on the Commissions page."
                                           + warn)
    db.audit(booking["lead_id"], "system", "commission_earned", {"commission_id": cid, "amount": amount})
    return cid


def s_owner_phone() -> str:
    return get_settings().owner["phone"]


def update_commission(cid: int, action: str, invoice_no: str = "", amount: int | None = None, note: str = "") -> str:
    c = db.q1("SELECT * FROM commissions WHERE id = ?", (cid,))
    if not c:
        return "Not found."
    if action == "invoiced":
        db.update("commissions", cid, {"status": "invoiced", "invoice_no": invoice_no, "invoiced_at": db.now_iso()})
    elif action == "collected":
        got = amount if amount is not None else c["amount"]
        status = "collected" if got >= c["amount"] else "part_collected"
        db.update("commissions", cid, {"status": status, "collected_amount": (c["collected_amount"] or 0) + got,
                                       "collected_at": db.now_iso()})
    elif action in ("disputed", "written_off"):
        db.update("commissions", cid, {"status": action, "notes": note})
    else:
        return "Unknown action."
    db.audit(c["lead_id"], "owner", "commission_" + action, {"commission_id": cid, "amount": amount})
    return f"Commission C{cid} marked {action}."


def commission_totals() -> dict:
    rows = db.q("SELECT * FROM commissions")
    now = get_settings().now()
    t = {"earned": 0, "invoiced": 0, "collected": 0, "outstanding": 0, "overdue": 0, "overdue_count": 0}
    for c in rows:
        t["earned"] += c["amount"] or 0
        t["collected"] += c["collected_amount"] or 0
        if c["status"] == "invoiced":
            t["invoiced"] += c["amount"] or 0
        if c["status"] in ("earned", "invoiced", "part_collected"):
            left = (c["amount"] or 0) - (c["collected_amount"] or 0)
            t["outstanding"] += left
            if c["due_at"] and db.parse_dt(c["due_at"]) < now:
                t["overdue"] += left
                t["overdue_count"] += 1
    return t
