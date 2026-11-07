"""The sales funnel: stages and which moves between them are allowed."""
from __future__ import annotations

from . import db

STAGES = [
    "new",              # just captured, not yet contacted
    "contacted",        # we reached out, no real conversation yet
    "qualified",        # budget / need / timeline understood
    "visit_scheduled",  # site visit booked with a site person
    "visit_done",       # site person reported the visit happened
    "negotiation",      # discussing price / terms
    "booking_pending",  # customer agreed, waiting for management's confirmation
    "payment_pending",  # management confirmed the deal; waiting for the advance to reach the builder's account
    "booked",           # advance received and verified — deal closed
    "nurture",          # not now; long-term drip
    "lost",             # dead (reason recorded)
]

TRANSITIONS = {
    "new": {"contacted", "qualified", "visit_scheduled"},
    "contacted": {"qualified", "visit_scheduled", "negotiation"},
    "qualified": {"visit_scheduled", "negotiation"},
    "visit_scheduled": {"visit_done", "qualified", "visit_scheduled"},
    "visit_done": {"negotiation", "visit_scheduled"},
    "negotiation": {"booking_pending", "visit_scheduled", "negotiation"},
    "booking_pending": {"payment_pending", "negotiation"},
    "payment_pending": {"booked", "negotiation"},
    "nurture": {"contacted", "qualified", "visit_scheduled", "negotiation"},
    "lost": {"nurture", "contacted", "qualified"},
    "booked": set(),
}
# Any open stage may drop to nurture or lost.
for _s in STAGES:
    if _s not in ("booked", "lost", "nurture"):
        TRANSITIONS[_s] |= {"nurture", "lost"}
TRANSITIONS["nurture"] |= {"lost"}

# Stages only the system/humans may set (site person feedback, owner confirmation).
SYSTEM_ONLY = {"visit_done", "booking_pending", "payment_pending", "booked"}

ACTIVE = [s for s in STAGES if s not in ("booked", "lost")]


class StageError(ValueError):
    pass


def move(lead_id: int, to: str, actor: str, reason: str = "") -> dict:
    lead = db.get_lead(lead_id)
    if not lead:
        raise StageError(f"lead {lead_id} not found")
    frm = lead["stage"]
    if to not in STAGES:
        raise StageError(f"unknown stage '{to}'")
    if actor == "agent" and to in SYSTEM_ONLY:
        raise StageError(f"stage '{to}' is set by the system, not by the agent")
    if frm == to and to != "visit_scheduled" and to != "negotiation":
        return lead
    if to not in TRANSITIONS.get(frm, set()):
        raise StageError(f"cannot move from '{frm}' to '{to}'")
    changes = {"stage": to}
    if to in ("nurture", "lost"):
        changes["followup_attempts"] = 0
    if to == "lost":
        changes["lost_reason"] = reason
        changes["next_followup_at"] = None
    db.update("leads", lead_id, changes)
    if to in ("booked", "lost"):
        # Nothing left to call about: close open call tasks so they don't clutter the salesperson's list.
        db.q("UPDATE call_tasks SET status = 'cancelled', notes = ? WHERE lead_id = ? AND status IN ('open','attempted')",
             (f"closed automatically: lead {to}", lead_id))
    db.audit(lead_id, actor, "stage", {"from": frm, "to": to, "reason": reason})
    return db.get_lead(lead_id)
