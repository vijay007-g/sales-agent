"""Background clock: follow-ups, visit reminders, stale-approval nudges, daily owner digest."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, time, timedelta

from . import channels, db, events, pricing, team
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

    # 2. visit reminders to the customer and site person
    for v in db.q("SELECT * FROM site_visits WHERE status = 'scheduled'"):
        when = db.parse_dt(v["scheduled_at"])
        sent = set(json.loads(v["reminders_sent"] or "[]"))
        lead = db.get_lead(v["lead_id"])
        for h in s.messaging.get("visit_reminders_hours_before", [24, 2]):
            key = f"{h}h"
            if key in sent or now < when - timedelta(hours=h) or now >= when:
                continue
            if quiet and h > 3:
                continue
            if not lead["opted_out"] and lead["phone"]:
                if v["kind"] == "office":
                    text = (f"Hi {lead['name'] or ''}, looking forward to seeing you at our office on "
                            f"{when:%a %d %b at %I:%M %p}. Address: {s.booking.get('office_address', '')}.")
                else:
                    text = (f"Hi {lead['name'] or ''}, just a reminder of your site visit to {v['project']} on "
                            f"{when:%a %d %b at %I:%M %p}. {v['site_person']} will meet you there. "
                            f"Let me know if the timing needs to change.")
                team.deliver(lead["id"], text, "whatsapp", author="system")
            if h <= 3:
                channels.notify_staff(v["site_person_phone"],
                                      f"Reminder: visit #{v['id']} at {when:%I:%M %p} — {lead['name']} "
                                      f"{lead['phone']}, {v['project']}")
            sent.add(key)
            stats["reminders"] += 1
        db.update("site_visits", v["id"], {"reminders_sent": json.dumps(sorted(sent))})
        # site person forgot to report back
        if v["kind"] == "site" and now > when + timedelta(hours=2) and "feedback_nudge" not in sent:
            channels.notify_staff(v["site_person_phone"],
                                  f"How did visit #{v['id']} with {lead['name']} go? Please fill the visit report: "
                                  f"{team.base_url()}/f/visit/{v['form_token']}\n(or reply VISITED {v['id']} "
                                  f"<hot/warm/cold> <notes>  /  NOSHOW {v['id']})")
            sent.add("feedback_nudge")
            db.update("site_visits", v["id"], {"reminders_sent": json.dumps(sorted(sent))})
            stats["nudges"] += 1

    # 3. call tasks: alert the salesperson when due, remind once if overdue
    for t in db.q("SELECT * FROM call_tasks WHERE status = 'open'"):
        due = db.parse_dt(t["due_at"])
        if t["notified"] == 0 and now >= due - timedelta(minutes=30) and not quiet:
            team.notify_call_task(t["id"])
            stats["reminders"] += 1
        elif t["notified"] == 1 and now > due + timedelta(hours=2) and not quiet:
            lead = db.get_lead(t["lead_id"])
            channels.notify_staff(team.rm_for(lead)["phone"],
                                  f"⏰ Overdue call C{t['id']}: {lead['name']} {lead['phone']} — {t['purpose']}\n"
                                  f"Reply CALLED C{t['id']} <notes> or NOANSWER C{t['id']}")
            db.update("call_tasks", t["id"], {"notified": 2})
            stats["nudges"] += 1

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
