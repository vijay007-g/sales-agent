"""Background clock: follow-ups, visit reminders, stale-approval nudges, daily owner digest."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, time, timedelta

from . import channels, db, events, pricing, team, team_access
from .config import get_settings

log = logging.getLogger("salesagent.scheduler")


def in_quiet_hours(now: datetime | None = None) -> bool:
    s = get_settings()
    now = now or s.now()
    start, end = s.messaging.get("quiet_hours", ["21:00", "09:00"])
    a = time.fromisoformat(start)
    b = time.fromisoformat(end)
    t = now.time()
    return (t >= a or t < b) if a > b else (a <= t < b)


def _sent_today(action: str) -> bool:
    today = get_settings().now().date().isoformat()
    return bool(db.q1("SELECT id FROM audit WHERE action = ? AND substr(created_at,1,10) = ?", (action, today)))


def tick() -> dict:
    s = get_settings()
    now = s.now()
    stats = {"followups": 0, "reminders": 0, "nudges": 0}
    quiet = in_quiet_hours(now)

    # 1. follow-ups that are due
    if not quiet:
        due = db.q("SELECT id, next_followup_at FROM leads WHERE next_followup_at IS NOT NULL AND opted_out = 0 "
                   "AND needs_human = 0 AND stage NOT IN ('booked','lost')")
        for row in due:
            if db.parse_dt(row["next_followup_at"]) <= now:
                db.update("leads", row["id"], {"next_followup_at": None})
                events.dispatch(events.followup_due, row["id"])
                stats["followups"] += 1

    # 2. visit reminders: buyer, site coordinator and salesperson; confirmation call the day before
    for v in db.q("SELECT * FROM site_visits WHERE status = 'scheduled'"):
        when = db.parse_dt(v["scheduled_at"])
        sent = set(json.loads(v["reminders_sent"] or "[]"))
        lead = db.get_lead(v["lead_id"])
        before = sent.copy()
        stats["reminders"] += visit_reminders(v, lead, when, now, sent, quiet)
        if v["kind"] == "site" and now > when + timedelta(hours=2) and "feedback_nudge" not in sent:
            link = team_access.link_for("site", v["site_person_phone"], f"/visit/{v['id']}")
            channels.notify_staff(v["site_person_phone"],
                                  f"How did the visit with {lead['name']} go? Please fill the 2-minute report: {link}\n"
                                  f"(or reply VISITED {v['id']} <hot/warm/cold> <notes>  /  NOSHOW {v['id']})")
            rm = team.rm_for(lead)
            if rm.get("phone"):
                channels.notify_staff(rm["phone"], f"FYI: waiting for the visit report on {lead['name']} "
                                                   f"({v['project']}). A quick nudge to {v['site_person']} helps.")
            sent.add("feedback_nudge")
            stats["nudges"] += 1
        if sent != before:
            db.update("site_visits", v["id"], {"reminders_sent": json.dumps(sorted(sent))})

    # 3. call discipline: heads-up before, positive nudges after, then tell management
    for t in db.q("SELECT * FROM call_tasks WHERE status = 'open'"):
        if quiet:
            break
        due = db.parse_dt(t["due_at"])
        level = int(t["notified"] or 0)
        for lvl, at in ((0, due - timedelta(minutes=15)), (1, due + timedelta(minutes=20)),
                        (2, due + timedelta(minutes=60)), (3, due + timedelta(hours=3))):
            if level == lvl and now >= at:
                call_nudge(t, lvl)
                db.update("call_tasks", t["id"], {"notified": lvl + 1})
                stats["reminders" if lvl == 0 else "nudges"] += 1
                break

    # 4. approvals waiting too long
    for o in db.q("SELECT id, created_at FROM offers WHERE status = 'pending_approval'"):
        age = now - db.parse_dt(o["created_at"])
        if age > timedelta(hours=3) and not db.q1(
                "SELECT id FROM audit WHERE action = 'approval_nudge' AND detail = ?", (str(o["id"]),)):
            if not quiet:
                pricing.notify_owner_offer(o["id"])
                db.audit(None, "system", "approval_nudge", str(o["id"]))
                stats["nudges"] += 1

    # 5. channel partner housekeeping (once a day): renew expiring client registrations, chase overdue commissions
    if not _sent_today("partners_check"):
        db.audit(None, "system", "partners_check", "")
        from . import partners
        renewed = partners.renew_expiring()
        overdue = db.q("SELECT c.id, c.amount, c.collected_amount, c.due_at, b.name builder FROM commissions c "
                       "JOIN builders b ON b.id = c.builder_id WHERE c.status IN ('earned','invoiced','part_collected') "
                       "AND c.due_at < ?", (now.isoformat(),))
        if overdue and now.weekday() == 0:   # Monday reminder
            lines = [f"C{c['id']} {c['builder']}: {pricing.fmt_money((c['amount'] or 0) - (c['collected_amount'] or 0))}"
                     f" (due {c['due_at'][:10]})" for c in overdue[:15]]
            channels.notify_staff(s.owner["phone"], "💼 Overdue commissions — follow up with the builders:\n"
                                  + "\n".join(lines))
        stats["registrations_renewed"] = renewed

    # 6. weekly learning from won / lost leads (checked once a day)
    if not _sent_today("learning_check"):
        db.audit(None, "system", "learning_check", "")
        from . import learning
        if learning.due():
            events.dispatch(learning.learn)

    # 7. morning digest for the owner
    if now.time() >= time(9, 0) and not _sent_today("digest"):
        channels.notify_staff(s.owner["phone"], digest())
        db.audit(None, "system", "digest", "")
    return stats


NUDGES = [
    "{rm}, a quick win is waiting: {name} is {temp}. A 3-minute call now keeps the momentum. {why}",
    "{rm}, {name} hasn't heard from us by phone yet. Buyers who get a call within the hour are far more likely to "
    "visit — you've got this! {why}",
]


def _call_context(t: dict, lead: dict) -> str:
    last_in = db.q1("SELECT content FROM interactions WHERE lead_id = ? AND direction = 'in' ORDER BY id DESC LIMIT 1",
                    (lead["id"],))
    bits = [f"Goal: {t['purpose']}."]
    if last_in:
        bits.append(f"Their last message: \"{last_in['content'][:120]}\"")
    return " ".join(bits)


def call_nudge(t: dict, level: int) -> None:
    """level 0: heads-up before the call; 1-2: positive nudges after it's due; 3: management is told."""
    lead = db.get_lead(t["lead_id"])
    if not lead or lead["stage"] in ("booked", "lost"):
        return
    rm = team.rm_for(lead)
    link = team_access.link_for("sales", rm.get("phone", ""), f"/lead/{lead['id']}") if rm.get("phone") else ""
    temp = {"hot": "hot 🔥", "warm": "warm"}.get(lead.get("temperature") or "", "interested")
    if level == 0:
        team.notify_call_task(t["id"])
        return
    if level in (1, 2):
        text = NUDGES[level - 1].format(rm=rm.get("name", ""), name=lead["name"] or lead["phone"], temp=temp,
                                        why=_call_context(t, lead))
        channels.notify_staff(rm.get("phone", ""), f"📞 {text}\nCall {lead['phone']} · brief & log: {link}")
        return
    s = get_settings()
    channels.notify_staff(s.owner["phone"], f"⏰ Call not done for 3+ hours: {rm.get('name', '')} → {lead['name']} "
                                            f"({lead['stage']}, {lead.get('temperature') or 'new'}). {t['purpose']}. "
                                            f"A word with {rm.get('name', 'the salesperson')} may help.")
    channels.notify_staff(rm.get("phone", ""), f"{rm.get('name', '')}, {lead['name']} is still waiting for your call. "
                                               f"Management has been informed — please call when you can, or log "
                                               f"why it can't happen: {link}")
    db.audit(lead["id"], "system", "call_overdue_escalated", {"task_id": t["id"]})


def visit_reminders(v: dict, lead: dict, when, now, sent: set, quiet: bool) -> int:
    """Reminders to the buyer, the site coordinator and the salesperson; a confirmation call task the day before."""
    s = get_settings()
    n = 0
    rm = team.rm_for(lead)
    t = f"{when:%a %d %b, %I:%M %p}".replace(" 0", " ")
    site = v["kind"] == "site"
    host_link = team_access.link_for("site", v["site_person_phone"], f"/visit/{v['id']}") if site else ""
    rm_link = team_access.link_for("sales", rm.get("phone", ""), f"/lead/{lead['id']}") if rm.get("phone") else ""
    if site and "confirm_task" not in sent and now >= when - timedelta(hours=26) and now < when - timedelta(hours=3):
        if not db.q1("SELECT id FROM call_tasks WHERE lead_id = ? AND status = 'open'", (lead["id"],)):
            team.create_call_task(lead["id"], f"Confirm tomorrow's site visit ({t})", 60,
                                  f"Visit to {v['project']} on {t} with {v['site_person']}.\nConfirm the time, who is "
                                  f"coming (bring the decision maker), and share the location. Ask if they'd like "
                                  f"anything ready (floor plans, cost sheet, loan info).")
        sent.add("confirm_task")
        n += 1
    for h in s.messaging.get("visit_reminders_hours_before", [24, 2]):
        if now < when - timedelta(hours=h) or now >= when or (quiet and h > 3):
            continue
        if f"{h}h" not in sent:
            if not lead["opted_out"] and lead["phone"]:
                if site:
                    text = (f"Hi {lead['name'] or ''}, a reminder of your visit to {v['project']} on {t}. "
                            f"{v['site_person']} will meet you there. Let me know if the timing needs to change.")
                else:
                    text = (f"Hi {lead['name'] or ''}, looking forward to seeing you at the office on {t}. "
                            f"Address: {v['feedback'] or s.booking.get('office_address', '')}.")
                team.deliver(lead["id"], text, "whatsapp", author="system")
            sent.add(f"{h}h")
            n += 1
        if site and f"{h}h_host" not in sent:
            channels.notify_staff(v["site_person_phone"], (
                f"{'Tomorrow' if h >= 12 else 'In 2 hours'}: site visit {t}\n{lead['name']} ({lead['phone']}) · "
                f"{v['project']}\nLooking for {lead.get('unit_type') or '?'}, budget "
                f"{pricing.fmt_money(lead.get('budget_max'))}\nSalesperson: {rm.get('name', '')} {rm.get('phone', '')}\n"
                f"Details & steps: {host_link}"))
            sent.add(f"{h}h_host")
            n += 1
        if rm.get("phone") and f"{h}h_rm" not in sent:
            extra = "Please do the confirmation call today." if h >= 12 else "A quick 'see you soon' call helps."
            channels.notify_staff(rm["phone"], f"{'Tomorrow' if h >= 12 else 'In 2 hours'}: {lead['name']} visits "
                                               f"{v['project'] if site else 'the office'} at {t} with "
                                               f"{v['site_person']}. {extra} {rm_link}")
            sent.add(f"{h}h_rm")
            n += 1
    return n


def digest() -> str:
    s = get_settings()
    hot = db.q("SELECT id, name, stage, score FROM leads WHERE stage NOT IN ('booked','lost') "
               "ORDER BY score DESC LIMIT 5")
    today = s.now().date().isoformat()
    visits_today = db.q1("SELECT COUNT(*) n FROM site_visits WHERE status='scheduled' AND "
                         "substr(scheduled_at,1,10)=?", (today,))["n"]
    new_24h = db.q1("SELECT COUNT(*) n FROM leads WHERE created_at >= ?",
                    ((s.now() - timedelta(days=1)).isoformat(),))["n"]
    overdue = db.q("SELECT rm_name, COUNT(*) n FROM call_tasks WHERE status = 'open' AND due_at < ? "
                   "GROUP BY rm_name", (s.now().isoformat(),))
    drafts = db.q1("SELECT COUNT(*) n FROM drafts WHERE status = 'pending'")["n"]
    lines = [f"Good morning! {s.business['name']} sales digest", events.pipeline_summary(),
             f"New leads (24h): {new_24h}", f"Site visits today: {visits_today}",
             f"Drafts waiting for salespeople: {drafts}",
             "Overdue calls: " + (", ".join(f"{o['rm_name']} {o['n']}" for o in overdue) or "none")]
    from . import partners
    t = partners.commission_totals()
    if t["earned"]:
        lines.append(f"Commission outstanding: {pricing.fmt_money(t['outstanding'])}"
                     + (f" (overdue {pricing.fmt_money(t['overdue'])})" if t["overdue"] else ""))
    disputed = db.q1("SELECT COUNT(*) n FROM registrations WHERE status = 'disputed'")["n"]
    if disputed:
        lines.append(f"⚠️ Disputed client registrations: {disputed}")
    lines.append("Top leads:")
    lines += [f"  #{h['id']} {h['name']} — {h['stage']} (score {h['score']})" for h in hot]
    return "\n".join(lines)


def start_background(interval_sec: int = 60) -> threading.Thread:
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                tick()
            except Exception:  # noqa: BLE001 - keep the clock alive
                log.exception("scheduler tick failed")
            stop.wait(interval_sec)

    t = threading.Thread(target=loop, daemon=True, name="salesagent-scheduler")
    t.stop = stop  # type: ignore[attr-defined]
    t.start()
    return t
