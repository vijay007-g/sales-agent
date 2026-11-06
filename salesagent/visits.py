"""Site visits (with the site team's standard report form) and builder-office visits (for the advance)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import channels, db, pipeline
from .config import get_settings
from .pricing import fmt_money

VISIT_MINUTES = 60

# The standard report the site person fills after every visit.
VISIT_FORM = [
    # (field, label, type, options)
    ("attended", "Did the customer come?", "choice", ["yes", "no"]),
    ("visitors", "Who came (e.g. husband+wife, parents)?", "text", None),
    ("decision_maker_present", "Was the decision maker present?", "choice", ["yes", "no", "not sure"]),
    ("units_shown", "Units / floors shown", "text", None),
    ("unit_liked", "Unit they liked most (type, floor, facing)", "text", None),
    ("liked", "What they liked", "textarea", None),
    ("concerns", "Concerns / objections raised", "textarea", None),
    ("specific_requirements", "Specific requirements (floor, facing, vastu, parking, possession, etc.)", "textarea", None),
    ("budget_confirmed", "Budget they mentioned", "text", None),
    ("financing", "Payment: loan / own funds / mixed; loan pre-approved?", "text", None),
    ("timeline", "When do they want to book?", "text", None),
    ("competitors", "Other projects they are considering", "text", None),
    ("price_reaction", "Reaction to the price", "choice", ["comfortable", "slightly high", "too high", "did not discuss"]),
    ("interest", "Interest level", "choice", ["hot", "warm", "cold"]),
    ("next_step_agreed", "Next step agreed with the customer", "text", None),
    ("notes", "Anything else", "textarea", None),
]


def _persons_for(project: str) -> list[dict]:
    s = get_settings()
    return [p for p in s.site_persons if not p.get("projects") or project in p["projects"]]


def _hm(day: datetime, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def free_slots(project: str, date_str: str) -> list[dict]:
    s = get_settings()
    day = datetime.fromisoformat(date_str).replace(tzinfo=s.tz)
    now = s.now()
    out = []
    for person in _persons_for(project):
        if day.weekday() not in person.get("working_days", range(7)):
            continue
        booked = db.q(
            "SELECT scheduled_at FROM site_visits WHERE kind = 'site' AND site_person = ? AND status = 'scheduled' "
            "AND substr(scheduled_at, 1, 10) = ?", (person["name"], date_str))
        if len(booked) >= person.get("max_visits_per_day", 6):
            continue
        taken = {db.parse_dt(b["scheduled_at"]) for b in booked}
        start, end = (_hm(day, t) for t in person.get("visit_hours", ["10:00", "18:00"]))
        t = start
        while t + timedelta(minutes=VISIT_MINUTES) <= end:
            clash = any(abs((t - b).total_seconds()) < VISIT_MINUTES * 60 for b in taken)
            if t > now + timedelta(hours=1) and not clash:
                out.append({"time": t.isoformat(timespec="minutes"), "site_person": person["name"]})
            t += timedelta(minutes=VISIT_MINUTES)
    seen, uniq = set(), []
    for slot in sorted(out, key=lambda x: x["time"]):
        if slot["time"] not in seen:
            seen.add(slot["time"])
            uniq.append(slot)
    return uniq


def office_slots(date_str: str) -> list[str]:
    s = get_settings()
    b = s.booking
    day = datetime.fromisoformat(date_str).replace(tzinfo=s.tz)
    if day.weekday() not in b.get("office_days", range(6)):
        return []
    cap = int(b.get("office_visit_slots_per_hour", 2))
    start, end = (_hm(day, t) for t in b.get("office_hours", ["10:00", "18:00"]))
    out, t = [], start
    while t + timedelta(minutes=60) <= end:
        n = db.q1("SELECT COUNT(*) n FROM site_visits WHERE kind = 'office' AND status = 'scheduled' "
                  "AND scheduled_at = ?", (t.isoformat(timespec="minutes"),))["n"]
        if n < cap and t > s.now() + timedelta(hours=2):
            out.append(t.isoformat(timespec="minutes"))
        t += timedelta(minutes=60)
    return out


def _parse_when(when_iso: str) -> datetime | None:
    try:
        when = db.parse_dt(when_iso)
    except ValueError:
        return None
    return when.astimezone(get_settings().tz).replace(second=0, microsecond=0) if when else None


def book(lead_id: int, project: str, when_iso: str, notes: str = "") -> dict:
    s = get_settings()
    if not s.project(project):
        return {"ok": False, "error": f"Unknown project '{project}'."}
    when = _parse_when(when_iso)
    if when is None:
        return {"ok": False, "error": "Invalid datetime."}
    slots = free_slots(project, when.date().isoformat())
    match = next((x for x in slots if db.parse_dt(x["time"]) == when), None)
    if not match:
        return {"ok": False, "error": "That slot is not available.",
                "available_that_day": [x["time"] for x in slots][:10]}
    person = next(p for p in s.site_persons if p["name"] == match["site_person"])
    for v in db.q("SELECT id FROM site_visits WHERE lead_id = ? AND kind = 'site' AND status = 'scheduled'",
                  (lead_id,)):
        db.update("site_visits", v["id"], {"status": "rescheduled"})
    token = db.new_token()
    vid = db.insert("site_visits", {
        "lead_id": lead_id, "kind": "site", "project": project, "scheduled_at": when.isoformat(timespec="minutes"),
        "site_person": person["name"], "site_person_phone": person["phone"], "status": "scheduled",
        "form_token": token, "feedback": notes, "created_at": db.now_iso(), "updated_at": db.now_iso()})
    lead = db.get_lead(lead_id)
    try:
        pipeline.move(lead_id, "visit_scheduled", "agent", f"visit #{vid}")
    except pipeline.StageError:
        pass
    from .team import base_url
    channels.notify_staff(person["phone"], (
        f"NEW SITE VISIT #{vid}\n{when:%a %d %b, %I:%M %p} — {project}\n"
        f"Customer: {lead['name']} ({lead['phone']})  · Sales: {lead.get('rm_name') or '-'}\n"
        f"Looking for: {lead['unit_type'] or '?'}, budget {fmt_money(lead['budget_max'])}, "
        f"timeline {lead['timeline'] or '?'}\nPrepare: {notes or '-'}\n\n"
        f"After the visit, fill the visit report (2 min): {base_url()}/f/visit/{token}\n"
        f"Quick reply also works: VISITED {vid} <hot/warm/cold> <notes>  or  NOSHOW {vid}"))
    db.audit(lead_id, "agent", "visit_booked", {"visit_id": vid, "when": match["time"],
                                               "site_person": person["name"]})
    return {"ok": True, "visit_id": vid, "when": match["time"], "site_person": person["name"]}


def book_office(lead_id: int, when_iso: str, purpose: str) -> dict:
    s = get_settings()
    when = _parse_when(when_iso)
    if when is None:
        return {"ok": False, "error": "Invalid datetime."}
    free = office_slots(when.date().isoformat())
    if when.isoformat(timespec="minutes") not in free:
        return {"ok": False, "error": "That office slot is not available.", "available_that_day": free[:10]}
    for v in db.q("SELECT id FROM site_visits WHERE lead_id = ? AND kind = 'office' AND status = 'scheduled'",
                  (lead_id,)):
        db.update("site_visits", v["id"], {"status": "rescheduled"})
    vid = db.insert("site_visits", {
        "lead_id": lead_id, "kind": "office", "project": "OFFICE", "scheduled_at": when.isoformat(timespec="minutes"),
        "site_person": "Office", "site_person_phone": s.owner["phone"], "status": "scheduled",
        "form_token": db.new_token(), "feedback": purpose, "created_at": db.now_iso(), "updated_at": db.now_iso()})
    lead = db.get_lead(lead_id)
    channels.notify_staff(s.owner["phone"], (
        f"OFFICE VISIT O{vid}\n{when:%a %d %b, %I:%M %p} at {s.booking.get('office_address', 'office')}\n"
        f"{lead['name']} ({lead['phone']}) — {purpose}\nSales: {lead.get('rm_name') or '-'}\n"
        f"When the advance is received reply: PAID B<booking no> <amount> <receipt/UTR>"))
    db.audit(lead_id, "agent", "office_visit_booked", {"visit_id": vid, "when": when.isoformat()})
    return {"ok": True, "office_visit_id": vid, "when": when.isoformat(timespec="minutes"),
            "address": s.booking.get("office_address", "")}


def cancel(lead_id: int, visit_id: int, reason: str) -> dict:
    v = db.q1("SELECT * FROM site_visits WHERE id = ? AND lead_id = ?", (visit_id, lead_id))
    if not v or v["status"] != "scheduled":
        return {"ok": False, "error": "No such scheduled visit for this lead."}
    db.update("site_visits", visit_id, {"status": "cancelled", "feedback": reason})
    channels.notify_staff(v["site_person_phone"], f"VISIT #{visit_id} CANCELLED — {reason}")
    db.audit(lead_id, "agent", "visit_cancelled", {"visit_id": visit_id, "reason": reason})
    return {"ok": True}


def record_feedback(visit_id: int, form: dict, actor: str = "site_person") -> dict | None:
    """Store the site person's report. `form` uses VISIT_FORM field names."""
    v = db.q1("SELECT * FROM site_visits WHERE id = ?", (visit_id,))
    if not v:
        return None
    attended = (form.get("attended") or "yes").lower() != "no"
    status = "completed" if attended else "no_show"
    interest = (form.get("interest") or "").lower()
    db.update("site_visits", visit_id, {
        "status": status, "interest_level": interest,
        "feedback": form.get("notes") or form.get("liked") or "",
        "liked_units": form.get("unit_liked", ""), "objections": form.get("concerns", ""),
        "form_data": json.dumps(form, ensure_ascii=False)})
    lead_id = v["lead_id"]
    if v["kind"] == "site":
        if status == "completed":
            try:
                pipeline.move(lead_id, "visit_done", actor, form.get("next_step_agreed", ""))
            except pipeline.StageError:
                pass
            if interest in ("hot", "warm", "cold"):
                db.update("leads", lead_id, {"temperature": interest})
        else:
            try:
                pipeline.move(lead_id, "qualified", actor, "no-show")
            except pipeline.StageError:
                pass
    db.audit(lead_id, actor, "visit_" + status, {"visit_id": visit_id, **form})
    return {**v, "status": status, "interest_level": interest, "form": form}
