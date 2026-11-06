"""Turns real-world events into agent runs, and handles WhatsApp commands from the team."""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from . import agent, channels, db, leads, pipeline, pricing, team, visits
from .config import get_settings

log = logging.getLogger("salesagent.events")
_pool = ThreadPoolExecutor(max_workers=int(os.environ.get("AGENT_WORKERS", "4")))

STOP_WORDS = {"stop", "unsubscribe", "stop messages", "don't message", "do not message", "remove me"}


def dispatch(fn, *args):
    """Run in the background (server) or inline (tests / CLI)."""
    if os.environ.get("SALESAGENT_SYNC") == "1":
        return fn(*args)
    fut = _pool.submit(fn, *args)
    fut.add_done_callback(lambda f: f.exception() and log.exception("event failed", exc_info=f.exception()))
    return fut


# ------------------------- customer-side events -------------------------

def new_lead(lead_id: int) -> None:
    lead = db.get_lead(lead_id)
    rm = team.assign_rm(lead_id)
    detail = (f"A new lead just came in from source '{lead['source']}'"
              f"{' (campaign ' + lead['campaign'] + ')' if lead.get('campaign') else ''}. It is assigned to "
              f"{rm['name'] if rm else 'the team'}. Send a short, genuine first WhatsApp message as "
              f"{rm['name'] if rm else 'the salesperson'} (thank them, mention what they enquired about, say you'll "
              "give them a quick call). Then create an intro call task due within 10 minutes with a brief.")
    _run(lead_id, "new_lead", detail)


def inbound_message(phone: str | None, email: str | None, text: str, channel: str = "whatsapp") -> int | None:
    lead = db.find_lead_by_phone(phone) if phone else None
    if not lead and email:
        lead = db.q1("SELECT * FROM leads WHERE lower(email) = lower(?)", (email,))
    if not lead:
        lead, _ = leads.upsert_lead({"phone": phone, "email": email, "source": "inbound_" + channel})
        team.assign_rm(lead["id"])
        lead = db.get_lead(lead["id"])
    lead_id = lead["id"]
    db.log_interaction(lead_id, "in", channel, "customer", text)
    db.update("leads", lead_id, {"followup_attempts": 0})
    leads.rescore(lead_id)

    norm = text.strip().lower().strip(".!")
    if norm in STOP_WORDS:
        db.update("leads", lead_id, {"opted_out": 1, "next_followup_at": None})
        try:
            pipeline.move(lead_id, "lost", "system", "opted out (keyword)")
        except pipeline.StageError:
            pass
        if lead["phone"]:
            channels.send_whatsapp(lead["phone"], "Understood — you won't receive further messages from us. "
                                                  "Reply START anytime if you'd like to hear from us again.")
        return lead_id
    if lead["opted_out"]:
        if norm == "start":
            db.update("leads", lead_id, {"opted_out": 0})
            try:
                pipeline.move(lead_id, "nurture", "system", "opted back in")
            except pipeline.StageError:
                pass
        else:
            return lead_id
    if lead["stage"] == "lost":
        try:
            pipeline.move(lead_id, "contacted", "system", "customer re-engaged")
        except pipeline.StageError:
            pass
    if lead["stage"] == "payment_pending" and re.search(r"paid|transferred|utr|receipt|done|sent", norm):
        channels.notify_staff(get_settings().owner["phone"],
                              f"💰 {lead['name']} (#{lead_id}) says: \"{text[:300]}\"\nVerify in the bank, then "
                              f"reply PAID B<booking no> <amount> <UTR>")
    rm = team.rm_for(lead)
    if lead["needs_human"]:
        for who in {get_settings().owner["phone"], rm["phone"]}:
            channels.notify_staff(who, f"Lead #{lead_id} {lead['name']} (with you) wrote: {text[:500]}")
        return lead_id
    _run(lead_id, "customer_message", f"The customer just sent: \"{text}\". Reply appropriately.")
    return lead_id


def followup_due(lead_id: int) -> None:
    lead = db.get_lead(lead_id)
    s = get_settings()
    attempts = (lead["followup_attempts"] or 0) + 1
    db.update("leads", lead_id, {"followup_attempts": attempts, "next_followup_at": None})
    limit = int(s.followups.get("max_attempts_before_nurture", 5))
    hint = ""
    if attempts >= limit and lead["stage"] not in ("nurture", "booking_pending", "payment_pending"):
        hint = (f" This is attempt {attempts} with no reply. Ask the salesperson for one last call, send one "
                "warm message that leaves the door open, then move the lead to nurture.")
    _run(lead_id, "followup_due",
         f"Follow-up time. Purpose noted earlier: {lead.get('followup_purpose') or 'general check-in'}. "
         f"Attempt #{attempts}. Follow your strategy for this lead: send a follow-up that adds something new and "
         f"moves them one step closer to booking, and/or create a call task (alternate channels - if the last "
         f"two messages got no reply, a call is usually better).{hint}")


def visit_outcome(visit_id: int, form: dict) -> None:
    v = visits.record_feedback(visit_id, form)
    if not v:
        return
    if v["status"] == "completed":
        report = "\n".join(f"- {label}: {form.get(field)}" for field, label, _, _ in visits.VISIT_FORM
                           if form.get(field))
        detail = (f"The site person submitted the visit report for visit #{visit_id}:\n{report}\n\n"
                  "1) Analyse it together with everything else you know, and call save_conversion_strategy with a "
                  "concrete plan to convert this lead to a booking. 2) Send a warm thank-you message that refers to "
                  "what they liked and their specific requirements. 3) Create a post-visit call task (within 2 "
                  "hours) whose brief follows the strategy. If a price move is part of the plan, do not offer it - "
                  "use propose_offer only when the customer actually asks or is ready to decide.")
    else:
        detail = (f"The customer did NOT come for visit #{visit_id}. Send a kind message (no guilt), and create a "
                  "call task to understand why and fix a new time. Offer two specific slots.")
    _run(v["lead_id"], "visit_outcome", detail)


def call_logged(task_id: int, outcome: str, data: dict) -> None:
    t = team.log_call(task_id, outcome, data)
    if not t:
        return
    report = "\n".join(f"- {k}: {v}" for k, v in data.items() if v)
    if outcome == "spoke":
        detail = (f"{t['rm_name']} just CALLED the customer (task C{task_id}: {t['purpose']}). Call notes:\n{report}\n"
                  "Update the lead profile and notes with what was learned. Then send a short WhatsApp that "
                  "naturally continues the call ('as we discussed...') and confirms what was agreed, and set the "
                  "next step (visit, follow-up, offer request, call task). Update the strategy if things changed.")
    else:
        detail = (f"{t['rm_name']} tried to call (task C{task_id}: {t['purpose']}) — outcome: {outcome}. {report}\n"
                  "Send a brief WhatsApp in the salesperson's voice ('tried calling you...') asking for a good time "
                  "to talk, and schedule another call task at a different time of day.")
    _run(t["lead_id"], "call_logged", detail)


# ------------------------- management decisions -------------------------

def owner_offer_decision(offer_id: int, decision: str, counter_price: int | None, note: str) -> str:
    o = db.q1("SELECT * FROM offers WHERE id = ?", (offer_id,))
    if not o:
        return f"Offer #{offer_id} not found."
    if o["status"] not in ("pending_approval", "blocked_floor"):
        return f"Offer #{offer_id} is already {o['status']}."
    if decision == "approve" and o["status"] == "blocked_floor":
        return f"Offer #{offer_id} is below your floor. Use COUNTER {offer_id} <price> to set a price."
    status = {"approve": "approved", "reject": "rejected", "counter": "countered"}[decision]
    db.update("offers", offer_id, {"status": status, "owner_counter_price": counter_price,
                                   "owner_note": note, "decided_at": db.now_iso()})
    db.audit(o["lead_id"], "owner", "offer_" + status, {"offer_id": offer_id, "counter": counter_price,
                                                        "note": note})
    tail = (" Create a call task (within 30 minutes) so the salesperson presents it by phone first; then send a "
            "short WhatsApp confirming the offer in writing, and push for the booking advance.")
    if decision == "approve":
        detail = (f"Management APPROVED offer #{offer_id}: {o['unit_type']} at "
                  f"{pricing.fmt_money(o['offered_price'])} ({o['offered_price']}). Note: {note or '-'}." + tail)
    elif decision == "counter":
        detail = (f"Management COUNTERED offer #{offer_id}: best possible price "
                  f"{pricing.fmt_money(counter_price)} ({counter_price}). Note: {note or '-'}. This counter is "
                  "approved — present it as the final best price." + tail)
    else:
        detail = (f"Management REJECTED offer #{offer_id}. Note: {note or '-'}. Hold the last approved price "
                  "politely, offer value instead, or suggest a unit that fits their budget. A call usually works "
                  "better than a message for this.")
    dispatch(_run, o["lead_id"], "owner_decision", detail)
    return f"Got it — offer #{offer_id} {status}. The team is informing the customer."


def owner_booking_decision(booking_id: int, confirm: bool, note: str) -> str:
    b = db.q1("SELECT * FROM bookings WHERE id = ?", (booking_id,))
    if not b:
        return f"Booking B{booking_id} not found."
    if b["status"] != "awaiting_owner":
        return f"Booking B{booking_id} is already {b['status']}."
    if confirm:
        db.update("bookings", booking_id, {"status": "confirmed", "decided_at": db.now_iso(),
                                           "notes": (b["notes"] or "") + f" | management: {note}"})
        pipeline.move(b["lead_id"], "payment_pending", "owner", f"booking B{booking_id} confirmed")
        detail = (f"Management CONFIRMED booking B{booking_id} (advance {pricing.fmt_money(b['token_amount'])}). "
                  f"Note: {note or '-'}. Now get the advance paid to the builder: 1) share_payment_details for "
                  f"B{booking_id}; 2) offer both options - online transfer, or a visit to our office (offer two "
                  "office slots); 3) create a call task for the salesperson to walk them through it. The deal is "
                  "booked only when the advance is received.")
    else:
        db.update("bookings", booking_id, {"status": "on_hold", "decided_at": db.now_iso(),
                                           "notes": (b["notes"] or "") + f" | management hold: {note}"})
        pipeline.move(b["lead_id"], "negotiation", "owner", f"booking B{booking_id} on hold")
        detail = (f"Management put booking B{booking_id} ON HOLD. Note: {note or '-'}. Tell the customer politely "
                  "there is a small delay and what happens next, without blaming anyone.")
    db.audit(b["lead_id"], "owner", "booking_" + ("confirmed" if confirm else "hold"), note)
    dispatch(_run, b["lead_id"], "booking_decision", detail)
    return (f"Booking B{booking_id} {'confirmed — AI is sending payment details' if confirm else 'on hold'}.")


def payment_received(booking_id: int, amount: int | None, ref: str) -> str:
    b = db.q1("SELECT * FROM bookings WHERE id = ?", (booking_id,))
    if not b:
        return f"Booking B{booking_id} not found."
    if b["status"] != "confirmed":
        return f"Booking B{booking_id} is '{b['status']}', not awaiting payment."
    db.update("bookings", booking_id, {"status": "paid", "amount_paid": amount or b["token_amount"],
                                       "payment_ref": ref, "paid_at": db.now_iso()})
    o = db.q1("SELECT * FROM offers WHERE id = ?", (b["offer_id"],))
    db.update("offers", o["id"], {"status": "accepted"})
    pipeline.move(b["lead_id"], "booked", "owner", f"advance received B{booking_id} {ref}")
    db.update("leads", b["lead_id"], {"next_followup_at": None})
    for v in db.q("SELECT id FROM site_visits WHERE lead_id = ? AND kind = 'office' AND status = 'scheduled'",
                  (b["lead_id"],)):
        db.update("site_visits", v["id"], {"status": "completed"})
    db.audit(b["lead_id"], "owner", "payment_received", {"booking_id": booking_id, "amount": amount, "ref": ref})
    dispatch(_run, b["lead_id"], "payment_received",
             f"The booking advance for B{booking_id} has been RECEIVED in the builder's account "
             f"({pricing.fmt_money(amount or b['token_amount'])}, ref {ref or '-'}). The flat is booked. Congratulate "
             "the customer warmly, explain next steps (agreement, documents, loan process if any), and if it feels "
             "right ask whether friends or family are also looking.")
    return (f"Payment for B{booking_id} recorded. Lead marked BOOKED. 🎉\n"
            f"Remember to reduce {o['unit_type']} availability for {o['project']} in Settings.")


# ------------------------- team WhatsApp commands -------------------------

def parse_amount(tok: str) -> int | None:
    t = tok.lower().replace(",", "").replace("₹", "").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(cr|crore|l|lakh|lac|k)?", t)
    if not m:
        return None
    n = float(m.group(1))
    mult = {"cr": 1e7, "crore": 1e7, "l": 1e5, "lakh": 1e5, "lac": 1e5, "k": 1e3}.get(m.group(2) or "", 1)
    return int(n * mult)


def _num(tok: str, prefix: str) -> int | None:
    t = tok.upper().lstrip("#")
    if t.startswith(prefix):
        t = t[len(prefix):]
    return int(t) if t.isdigit() else None


def staff_command(phone: str, text: str) -> str | None:
    """Returns a reply for team members, or None if the sender is not on the team."""
    s = get_settings()
    p = db.normalize_phone(phone)
    is_owner = p == db.normalize_phone(s.owner["phone"])
    site = next((x for x in s.site_persons if db.normalize_phone(x["phone"]) == p), None)
    rm = next((x for x in s.sales_team if db.normalize_phone(x["phone"]) == p), None)
    if not (is_owner or site or rm):
        return None
    parts = text.strip().split()
    if not parts:
        return HELP
    cmd = parts[0].upper()
    arg = parts[1] if len(parts) > 1 else ""
    rest = " ".join(parts[2:])

    # --- site team ---
    if cmd in ("VISITED", "NOSHOW") and (site or is_owner or rm):
        vid = _num(arg, "")
        if vid is None:
            return "Usage: VISITED <visit no> <hot/warm/cold> <notes>   or   NOSHOW <visit no>"
        if cmd == "NOSHOW":
            form = {"attended": "no"}
        else:
            interest, notes = "", rest
            if parts[2:3] and parts[2].lower() in ("hot", "warm", "cold"):
                interest, notes = parts[2].lower(), " ".join(parts[3:])
            form = {"attended": "yes", "interest": interest, "notes": notes}
        dispatch(visit_outcome, vid, form)
        tok = db.q1("SELECT form_token FROM site_visits WHERE id = ?", (vid,))
        extra = (f"\nFor a better follow-up, please also fill the full report: {team.base_url()}/f/visit/"
                 f"{tok['form_token']}" if tok and tok["form_token"] and cmd == "VISITED" else "")
        return f"Thanks! Visit #{vid} recorded. The sales team will follow up.{extra}"
    if cmd == "TODAY":
        today = s.now().date().isoformat()
        rows = db.q("SELECT v.id, v.kind, v.scheduled_at, v.site_person, l.name, l.phone FROM site_visits v "
                    "JOIN leads l ON l.id = v.lead_id WHERE v.status = 'scheduled' AND "
                    "substr(v.scheduled_at,1,10) = ? ORDER BY v.scheduled_at", (today,))
        if site and not is_owner:
            rows = [r for r in rows if r["site_person"] == site["name"]]
        return "\n".join(f"{'O' if r['kind'] == 'office' else '#'}{r['id']} {r['scheduled_at'][11:16]} {r['name']} "
                         f"{r['phone']} ({r['site_person']})" for r in rows) or "No visits today."

    # --- sales team ---
    if cmd in ("CALLED", "NOANSWER", "BUSY") and (rm or is_owner):
        tid = _num(arg, "C")
        if tid is None:
            return "Usage: CALLED C<task no> <what happened>   or   NOANSWER C<task no>"
        outcome = {"CALLED": "spoke", "NOANSWER": "no_answer", "BUSY": "busy"}[cmd]
        dispatch(call_logged, tid, outcome, {"summary": rest})
        return f"Call C{tid} logged. The AI will follow up on WhatsApp in your name."
    if cmd in ("SEND", "EDIT", "DROP") and (rm or is_owner):
        did = _num(arg, "D")
        if did is None:
            return "Usage: SEND D<no>  |  EDIT D<no> <your text>  |  DROP D<no>"
        if cmd == "DROP":
            return team.drop_draft(did)
        if cmd == "EDIT" and not rest:
            return "Add your text after EDIT D<no>."
        return team.approve_draft(did, rest if cmd == "EDIT" else None)
    if cmd == "TASKS" and (rm or is_owner):
        q = "SELECT c.id, c.due_at, c.purpose, l.name, l.phone FROM call_tasks c JOIN leads l ON l.id = c.lead_id " \
            "WHERE c.status IN ('open','attempted')"
        args: tuple = ()
        if rm and not is_owner:
            q += " AND c.rm_name = ?"
            args = (rm["name"],)
        rows = db.q(q + " ORDER BY c.due_at", args)
        return "\n".join(f"C{r['id']} {r['due_at'][5:16]} {r['name']} {r['phone']} — {r['purpose']}" for r in rows) \
            or "No calls pending."
    if cmd == "LEAD" and arg.isdigit():
        lead = db.get_lead(int(arg))
        if not lead:
            return "Not found."
        return (f"#{lead['id']} {lead['name']} {lead['phone']}\nStage {lead['stage']} | score {lead['score']} | "
                f"{lead['temperature']} | sales {lead['rm_name'] or '-'}\nWants {lead['unit_type'] or '?'} budget "
                f"{pricing.fmt_money(lead['budget_max'])} timeline {lead['timeline'] or '?'}\n"
                f"Notes: {(lead['memory'] or '-')[-600:]}")

    if not is_owner:
        return ("Commands: TASKS | CALLED C<no> <notes> | NOANSWER C<no> | SEND D<no> | EDIT D<no> <text> | "
                "LEAD <no>" if rm else "Commands: TODAY | VISITED <no> <hot/warm/cold> <notes> | NOSHOW <no>")

    # --- management ---
    if cmd in ("APPROVE", "REJECT") and arg.isdigit():
        return owner_offer_decision(int(arg), cmd.lower(), None, rest)
    if cmd == "COUNTER" and arg.isdigit() and len(parts) >= 3:
        amt = parse_amount(parts[2])
        if not amt:
            return "Usage: COUNTER <offer no> <price e.g. 7200000 or 72L> <note>"
        return owner_offer_decision(int(arg), "counter", amt, " ".join(parts[3:]))
    if cmd in ("CONFIRM", "HOLD") and _num(arg, "B") is not None:
        return owner_booking_decision(_num(arg, "B"), cmd == "CONFIRM", rest)
    if cmd == "PAID" and _num(arg, "B") is not None:
        amt = parse_amount(parts[2]) if len(parts) > 2 else None
        ref = " ".join(parts[3:]) if amt else rest
        return payment_received(_num(arg, "B"), amt, ref)
    if cmd in ("RESUME", "PAUSE") and arg.isdigit():
        db.update("leads", int(arg), {"needs_human": 0 if cmd == "RESUME" else 1})
        db.audit(int(arg), "owner", cmd.lower(), rest)
        if cmd == "RESUME":
            dispatch(_run, int(arg), "human_resumed",
                     f"Management handed this lead back to you. Note: {rest or '-'}. Continue from here.")
        return f"Lead #{arg} {'resumed — AI is back on it' if cmd == 'RESUME' else 'paused — AI will not message'}."
    if cmd == "STATUS":
        return pipeline_summary()
    return HELP


HELP = ("Management: APPROVE <no> | REJECT <no> <note> | COUNTER <no> <price> <note>\n"
        "CONFIRM B<no> | HOLD B<no> <note> | PAID B<no> <amount> <UTR>\nPAUSE <lead> | RESUME <lead> <note>\n"
        "STATUS | LEAD <no> | TODAY | TASKS\n"
        "Sales: CALLED C<no> <notes> | NOANSWER C<no> | SEND D<no> | EDIT D<no> <text> | DROP D<no>\n"
        "Site: VISITED <no> <hot/warm/cold> <notes> | NOSHOW <no>")


def pipeline_summary() -> str:
    rows = db.q("SELECT stage, COUNT(*) n FROM leads GROUP BY stage")
    counts = {r["stage"]: r["n"] for r in rows}
    pend = db.q1("SELECT COUNT(*) n FROM offers WHERE status = 'pending_approval'")["n"]
    book = db.q1("SELECT COUNT(*) n FROM bookings WHERE status = 'awaiting_owner'")["n"]
    pay = db.q1("SELECT COUNT(*) n FROM bookings WHERE status = 'confirmed'")["n"]
    calls = db.q1("SELECT COUNT(*) n FROM call_tasks WHERE status = 'open'")["n"]
    lines = [f"{st}: {counts.get(st, 0)}" for st in pipeline.STAGES if counts.get(st)]
    return ("Pipeline\n" + "\n".join(lines) + f"\nPrice approvals waiting: {pend}\nBookings to confirm: {book}"
            f"\nAdvance payments awaited: {pay}\nOpen call tasks: {calls}")


# ------------------------- helpers -------------------------

def _run(lead_id: int, event: str, detail: str) -> None:
    ctx = agent.run(lead_id, event, detail)
    _ensure_next_step(lead_id, ctx)


CALL_STAGES = {"new", "contacted", "qualified", "visit_done", "negotiation", "payment_pending"}


def _ensure_next_step(lead_id: int, ctx) -> None:
    """Safety net: every open lead has a follow-up time, and key stages always have a call planned."""
    lead = db.get_lead(lead_id)
    if not lead or lead["opted_out"] or lead["needs_human"] or lead["stage"] in ("booked", "lost"):
        return
    s = get_settings()
    if lead["stage"] in CALL_STAGES and not ctx.call_task_set and agent.last_run_ok(ctx) and not db.q1(
            "SELECT id FROM call_tasks WHERE lead_id = ? AND status IN ('open','attempted')", (lead_id,)):
        team.create_call_task(lead_id, f"{lead['stage'].replace('_', ' ')} call", 120,
                              _fallback_brief(lead))
    if ctx.followup_set or lead["next_followup_at"]:
        return
    if lead["stage"] == "nurture":
        hours = 24 * float(s.followups.get("nurture_every_days", 14))
    elif lead["stage"] in ("visit_scheduled", "booking_pending"):
        return  # reminders / management decision drive the next step
    else:
        cadence = s.followups.get(lead["stage"], [24, 48, 96])
        idx = min(lead["followup_attempts"] or 0, len(cadence) - 1)
        hours = float(cadence[idx])
    when = s.now() + timedelta(hours=hours)
    db.update("leads", lead_id, {"next_followup_at": when.isoformat(timespec="minutes"),
                                 "followup_purpose": f"default {lead['stage']} cadence"})


def _fallback_brief(lead: dict) -> str:
    strat = json.loads(lead["strategy"]) if lead.get("strategy") else {}
    return (f"Stage: {lead['stage']}. Wants {lead['unit_type'] or '?'}, budget "
            f"{pricing.fmt_money(lead['budget_max'])}, timeline {lead['timeline'] or '?'}.\n"
            f"Notes: {(lead['memory'] or '-')[-400:]}\n"
            + (f"Plan: {' -> '.join(strat.get('next_actions', []))}" if strat else
               "Goal: understand where they are and agree the next step toward booking."))
