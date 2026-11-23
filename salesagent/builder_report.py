"""Weekly report to each partner builder: registered buyers, site visits, buyer feedback, bookings, payments.

This is promise no. 4 in the builder pitch. It builds the trust that leads to pilots, preferred terms and exclusive
mandates. Phone numbers are never included (the builder already has them from registration). Test leads and
sample builders are skipped.

Settings (Admin → Settings → Advanced, optional):
  builder_reports:
    mode: review      # review = you get a WhatsApp on Wednesday and send from the dashboard; auto = sent
                      # automatically; off = never
    weekday: 2        # 0 = Monday … 2 = Wednesday
    hour: 10
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta

from . import channels, db, pricing
from .config import get_settings

ACTIVE_STAGES = ("visit_scheduled", "visit_done", "negotiation", "booking_pending", "payment_pending")


def cfg() -> dict:
    c = get_settings().raw.get("builder_reports") or {}
    return {"mode": (c.get("mode") or "review").lower(), "weekday": int(c.get("weekday", 2)),
            "hour": int(c.get("hour", 10))}


def builders() -> list[dict]:
    return db.q("SELECT * FROM builders WHERE is_own = 0 AND is_sample = 0 AND active = 1 ORDER BY name")


def _d(iso: str | None, with_time: bool = False) -> str:
    if not iso:
        return ""
    d = db.parse_dt(iso)
    return f"{d:%a %d %b %I:%M %p}".replace(" 0", " ") if with_time else f"{d:%d %b}"


def _first(name: str | None) -> str:
    return (name or "Buyer").split()[0]


def build(builder_id: int, days: int = 7) -> dict:
    """Everything that happened with this builder's projects in the last `days` days."""
    s = get_settings()
    now = s.now()
    since = (now - timedelta(days=days)).isoformat()
    b = db.q1("SELECT * FROM builders WHERE id = ?", (builder_id,))
    projects = db.q("SELECT id, name FROM inv_projects WHERE builder_id = ?", (builder_id,))
    pids = [p["id"] for p in projects]
    names = [p["name"] for p in projects]
    test = "(SELECT id FROM leads WHERE campaign = 'test')"
    out = {"builder": b, "projects": names, "since": since, "days": days, "new_regs": [], "visits": [],
           "upcoming": [], "pipeline": [], "pending_ack": [], "bookings": [], "commissions": [],
           "price": Counter(), "concerns": [], "competitors": Counter(), "active_regs": 0}
    if not b or not pids:
        return out
    pm = ",".join("?" for _ in pids)
    nm = ",".join("?" for _ in names)
    pname = {p["id"]: p["name"] for p in projects}

    for r in db.q(f"SELECT r.id, r.project_id, r.status, r.sent_at, l.name FROM registrations r JOIN leads l ON "
                  f"l.id = r.lead_id WHERE r.builder_id = ? AND r.sent_at >= ? AND r.lead_id NOT IN {test} "
                  f"ORDER BY r.sent_at", (builder_id, since)):
        out["new_regs"].append({"id": r["id"], "buyer": _first(r["name"]), "project": pname.get(r["project_id"], ""),
                                "status": r["status"], "date": _d(r["sent_at"])})
    out["active_regs"] = db.q1(f"SELECT COUNT(*) n FROM registrations WHERE builder_id = ? AND status IN "
                               f"('sent','acknowledged') AND lead_id NOT IN {test}", (builder_id,))["n"]
    cutoff = (now - timedelta(hours=24)).isoformat()
    for r in db.q(f"SELECT r.id, r.project_id, r.sent_at, l.name FROM registrations r JOIN leads l ON l.id = r.lead_id "
                  f"WHERE r.builder_id = ? AND r.status = 'sent' AND r.sent_at <= ? AND r.lead_id NOT IN {test}",
                  (builder_id, cutoff)):
        out["pending_ack"].append({"id": r["id"], "buyer": _first(r["name"]), "project": pname.get(r["project_id"], ""),
                                   "date": _d(r["sent_at"])})

    for v in db.q(f"SELECT v.*, l.name FROM site_visits v JOIN leads l ON l.id = v.lead_id WHERE v.kind = 'site' AND "
                  f"v.project IN ({nm}) AND v.scheduled_at >= ? AND v.scheduled_at <= ? AND v.lead_id NOT IN {test} "
                  f"ORDER BY v.scheduled_at", (*names, since, now.isoformat())):
        f = json.loads(v["form_data"] or "{}")
        row = {"buyer": _first(v["name"]), "project": v["project"], "date": _d(v["scheduled_at"]),
               "status": v["status"], "interest": v["interest_level"] or f.get("interest", ""),
               "price": f.get("price_reaction", ""), "liked": f.get("unit_liked") or v["liked_units"] or "",
               "concerns": f.get("concerns") or v["objections"] or "", "competitors": f.get("competitors", ""),
               "next": f.get("next_step_agreed", "")}
        out["visits"].append(row)
        if row["price"] and row["price"] != "did not discuss":
            out["price"][row["price"]] += 1
        if row["concerns"]:
            out["concerns"].append(row["concerns"].strip())
        for c in (row["competitors"] or "").replace(";", ",").split(","):
            if c.strip():
                out["competitors"][c.strip().title()] += 1
    for v in db.q(f"SELECT v.project, v.scheduled_at, l.name FROM site_visits v JOIN leads l ON l.id = v.lead_id "
                  f"WHERE v.kind = 'site' AND v.status = 'scheduled' AND v.project IN ({nm}) AND v.scheduled_at > ? "
                  f"AND v.scheduled_at <= ? AND v.lead_id NOT IN {test} ORDER BY v.scheduled_at",
                  (*names, now.isoformat(), (now + timedelta(days=7)).isoformat())):
        out["upcoming"].append({"buyer": _first(v["name"]), "project": v["project"], "when": _d(v["scheduled_at"], True)})

    stage_label = {"visit_scheduled": "visit fixed", "visit_done": "visited, deciding", "negotiation": "negotiating",
                   "booking_pending": "booking in progress", "payment_pending": "paying the advance"}
    for r in db.q(f"SELECT DISTINCT l.id, l.name, l.stage, r.project_id FROM registrations r JOIN leads l ON "
                  f"l.id = r.lead_id WHERE r.builder_id = ? AND r.status IN ('sent','acknowledged') AND l.stage IN "
                  f"({','.join('?' for _ in ACTIVE_STAGES)}) AND l.id NOT IN {test}", (builder_id, *ACTIVE_STAGES)):
        out["pipeline"].append({"buyer": _first(r["name"]), "project": pname.get(r["project_id"], ""),
                                "stage": stage_label.get(r["stage"], r["stage"])})

    for c in db.q(f"SELECT c.*, l.name, u.unit_no, u.unit_type FROM commissions c LEFT JOIN leads l ON l.id = c.lead_id "
                  f"LEFT JOIN units u ON u.id = c.unit_id WHERE c.builder_id = ? AND c.project_id IN ({pm})",
                  (builder_id, *pids)):
        if c["created_at"] >= since:
            out["bookings"].append({"buyer": _first(c["name"]), "project": pname.get(c["project_id"], ""),
                                    "unit": " ".join(x for x in (c["unit_type"], c["unit_no"]) if x),
                                    "value": c["deal_value"]})
        if c["status"] in ("earned", "invoiced", "part_collected"):
            out["commissions"].append({"id": c["id"], "invoice": c["invoice_no"] or "", "due": _d(c["due_at"]),
                                       "outstanding": (c["amount"] or 0) - (c["collected_amount"] or 0),
                                       "overdue": bool(c["due_at"] and c["due_at"] < now.isoformat())})
    return out


def has_activity(r: dict) -> bool:
    return bool(r["new_regs"] or r["visits"] or r["upcoming"] or r["pipeline"] or r["bookings"] or r["pending_ack"])


def text(r: dict) -> str:
    """Plain-text report for WhatsApp and email."""
    s = get_settings()
    b = r["builder"]
    now = s.now()
    start = now - timedelta(days=r["days"])
    m = pricing.fmt_money
    done = [v for v in r["visits"] if v["status"] == "completed"]
    noshow = [v for v in r["visits"] if v["status"] == "no_show"]
    L = [f"Weekly partner report — {s.business['name']}",
         f"For {b['contact_name'] or b['name']} · {b['name']} · {start:%d %b} – {now:%d %b %Y}",
         f"Projects: {', '.join(r['projects'])}", "",
         f"• New buyers registered with you: {len(r['new_regs'])}  (active registrations: {r['active_regs']})",
         f"• Site visits done: {len(done)}" + (f"  · no-shows: {len(noshow)}" if noshow else ""),
         f"• Visits fixed for the next 7 days: {len(r['upcoming'])}",
         f"• Bookings this week: {len(r['bookings'])}"]
    if r["visits"]:
        L += ["", "SITE VISITS"]
        for v in r["visits"]:
            if v["status"] == "no_show":
                L.append(f"- {v['date']} {v['buyer']} · {v['project']}: did not come (we are rescheduling)")
                continue
            bits = [x for x in (v["interest"] and f"interest {v['interest']}", v["price"] and f"price: {v['price']}",
                                v["liked"] and f"liked {v['liked']}") if x]
            L.append(f"- {v['date']} {v['buyer']} · {v['project']}: " + ("; ".join(bits) or v["status"]))
            if v["concerns"]:
                L.append(f"    concerns: {v['concerns'][:160]}")
            if v["next"]:
                L.append(f"    next step: {v['next'][:120]}")
    if r["price"] or r["concerns"] or r["competitors"]:
        L += ["", "WHAT BUYERS ARE TELLING US"]
        if r["price"]:
            L.append("- Price reaction: " + ", ".join(f"{k} {n}" for k, n in r["price"].most_common()))
        if r["competitors"]:
            L.append("- Also considering: " + ", ".join(f"{k} ({n})" for k, n in r["competitors"].most_common(5)))
        for c in r["concerns"][:5]:
            L.append(f"- \"{c[:140]}\"")
    if r["upcoming"]:
        L += ["", "COMING UP (please keep the site team informed)"]
        L += [f"- {u['when']} {u['buyer']} · {u['project']}" for u in r["upcoming"]]
    if r["pipeline"]:
        L += ["", "REGISTERED BUYERS IN PROGRESS"]
        L += [f"- {p['buyer']} · {p['project']}: {p['stage']}" for p in r["pipeline"]]
    if r["bookings"]:
        L += ["", "BOOKINGS 🎉"]
        L += [f"- {x['buyer']} · {x['project']} {x['unit']}: {m(x['value'])}" for x in r["bookings"]]
    if r["pending_ack"]:
        L += ["", "PLEASE ACKNOWLEDGE THESE REGISTRATIONS"]
        L += [f"- R{p['id']} {p['buyer']} · {p['project']} (sent {p['date']}) — reply ACK R{p['id']}"
              for p in r["pending_ack"]]
    due = [c for c in r["commissions"] if c["overdue"]]
    if due:
        L += ["", "PAYMENTS DUE"]
        L += [f"- C{c['id']}{' inv ' + c['invoice'] if c['invoice'] else ''}: {m(c['outstanding'])} (due {c['due']})"
              for c in due]
    L += ["", f"Thank you for the partnership. Questions or feedback: {s.owner.get('name', '')} {s.owner.get('phone', '')}"]
    return "\n".join(L)


def last_sent(builder_id: int) -> str | None:
    r = db.q1("SELECT created_at FROM audit WHERE action = 'builder_report_sent' AND detail = ? ORDER BY id DESC "
              "LIMIT 1", (str(builder_id),))
    return r["created_at"] if r else None


def send(builder_id: int, actor: str = "owner") -> dict:
    r = build(builder_id)
    b = r["builder"]
    if not b:
        return {"ok": False, "error": "builder not found"}
    if not (b["contact_phone"] or b["contact_email"]):
        return {"ok": False, "error": f"{b['name']} has no contact phone or email (Inventory → builder)"}
    body = text(r)
    if b["contact_email"]:
        channels.send_email(b["contact_email"], f"Weekly partner report — {get_settings().business['name']}", body)
    if b["contact_phone"]:
        channels.notify_staff(b["contact_phone"], body)
    db.audit(None, actor, "builder_report_sent", str(builder_id))
    return {"ok": True, "builder": b["name"]}


def weekly_job() -> dict:
    """Run by the scheduler once on the report day: send (auto) or tell the owner reports are ready (review)."""
    from .team import base_url
    c = cfg()
    ready = [b for b in builders() if has_activity(build(b["id"]))]
    if c["mode"] == "off" or not ready:
        return {"ready": len(ready), "sent": 0}
    if c["mode"] == "auto":
        sent = sum(1 for b in ready if send(b["id"], "system")["ok"])
        channels.notify_staff(get_settings().owner["phone"], f"📊 Weekly reports sent to {sent} builder(s). "
                                                             f"See {base_url()}/builder-reports")
        return {"ready": len(ready), "sent": sent}
    channels.notify_staff(get_settings().owner["phone"],
                          f"📊 {len(ready)} weekly builder report(s) are ready: {', '.join(b['name'] for b in ready)}. "
                          f"Review and send (1 click): {base_url()}/builder-reports")
    return {"ready": len(ready), "sent": 0}
