"""Learning loop: study won vs lost leads (messages, calls, visit reports, offers, the salesperson's edits to
AI drafts, which sources/campaigns convert) and distil a playbook. The playbook is fed back into every agent run
and into campaign creation, so the system gets better at selling the more it sells."""
from __future__ import annotations

import json
from datetime import timedelta

from . import db
from .agent import get_client
from .config import get_settings

_list = {"type": "array", "items": {"type": "string"}}

PLAYBOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "what_works_in_messages": _list,
        "what_works_on_calls": _list,
        "objection_playbook": {"type": "array", "items": {"type": "object", "properties": {
            "objection": {"type": "string"}, "best_response": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["objection", "best_response", "evidence"], "additionalProperties": False}},
        "best_converting_profiles": _list,
        "lead_source_verdicts": {"type": "array", "items": {"type": "object", "properties": {
            "source_or_campaign": {"type": "string"}, "verdict": {"type": "string"}},
            "required": ["source_or_campaign", "verdict"], "additionalProperties": False}},
        "follow_up_insights": _list,
        "rm_tone_preferences": _list,
        "things_to_stop": _list,
        "creative_campaign_ideas": {"type": "array", "items": {"type": "object", "properties": {
            "angle": {"type": "string"}, "audience": {"type": "string"}, "hook": {"type": "string"},
            "why_it_should_work": {"type": "string"}},
            "required": ["angle", "audience", "hook", "why_it_should_work"], "additionalProperties": False}},
        "experiments_to_run": _list,
    },
    "required": ["summary", "what_works_in_messages", "what_works_on_calls", "objection_playbook",
                 "best_converting_profiles", "lead_source_verdicts", "follow_up_insights", "rm_tone_preferences",
                 "things_to_stop", "creative_campaign_ideas", "experiments_to_run"],
    "additionalProperties": False,
}


def _lead_dossier(lead: dict) -> dict:
    msgs = db.q("SELECT direction, author, content, created_at FROM interactions WHERE lead_id = ? "
                "ORDER BY id LIMIT 60", (lead["id"],))
    visits = db.q("SELECT kind, status, interest_level, form_data FROM site_visits WHERE lead_id = ? "
                  "AND status IN ('completed','no_show')", (lead["id"],))
    offers = db.q("SELECT unit_type, list_price, offered_price, customer_ask, status, owner_counter_price "
                  "FROM offers WHERE lead_id = ?", (lead["id"],))
    return {
        "outcome": lead["stage"], "lost_reason": lead.get("lost_reason"), "source": lead["source"],
        "campaign": lead.get("campaign"), "salesperson": lead.get("rm_name"),
        "profile": {k: lead.get(k) for k in ("unit_type", "budget_max", "timeline", "purpose", "financing",
                                            "location_pref", "language", "score")},
        "notes": (lead.get("memory") or "")[-800:],
        "conversation": [f"{m['created_at'][:10]} {m['direction']}/{m['author']}: {m['content'][:400]}" for m in msgs],
        "visit_reports": [json.loads(v["form_data"]) if v["form_data"] else v for v in visits],
        "offers": offers,
    }


def gather(days: int = 120) -> dict:
    since = (get_settings().now() - timedelta(days=days)).isoformat()
    won = db.q("SELECT * FROM leads WHERE stage IN ('booked','payment_pending') AND updated_at >= ? "
               "ORDER BY updated_at DESC LIMIT 25", (since,))
    lost = db.q("SELECT * FROM leads WHERE (stage = 'lost' OR (stage = 'nurture' AND followup_attempts >= 3)) "
                "AND updated_at >= ? ORDER BY updated_at DESC LIMIT 25", (since,))
    progressing = db.q("SELECT * FROM leads WHERE stage IN ('visit_done','negotiation','booking_pending') "
                       "ORDER BY score DESC LIMIT 10")
    edits = db.q("SELECT detail FROM audit WHERE action = 'draft_edited' ORDER BY id DESC LIMIT 40")
    from .marketing import funnel_report, spend_report
    return {
        "won": [_lead_dossier(x) for x in won],
        "lost_or_stalled": [_lead_dossier(x) for x in lost],
        "in_progress": [_lead_dossier(x) for x in progressing],
        "salesperson_edits_to_ai_drafts": [json.loads(e["detail"]) for e in edits],
        "funnel_by_source": funnel_report("source"),
        "funnel_by_campaign": funnel_report("campaign"),
        "spend_and_unit_economics": spend_report("source")[:24],
        "counts": {"won": len(won), "lost": len(lost)},
    }


def learn(force: bool = False) -> dict | None:
    s = get_settings()
    data = gather()
    closed = data["counts"]["won"] + data["counts"]["lost"]
    if closed < int(s.learning.get("min_closed_leads", 3)) and not force:
        return None
    prev = db.q1("SELECT content FROM insights WHERE kind = 'playbook' ORDER BY id DESC LIMIT 1")
    prompt = f"""You are the head of sales analytics for {s.business['name']}, a real-estate developer. Below is \
real data from our own sales: full conversations (WhatsApp messages and logged phone calls), site-visit reports \
written by our site team, offers and management decisions, how our salespeople rewrote the AI's drafts, and \
conversion by lead source and campaign.

Find what actually separates the leads we won from the ones we lost, and turn it into a practical playbook for \
the team and for the AI that writes messages and plans calls. Be concrete and evidence-based: quote or \
paraphrase the actual messages / call moments that moved customers, and the ones that lost them. Prefer a few \
strong, specific lessons over many generic ones. Where evidence is thin, say so in the evidence field.

Also be genuinely creative about lead generation: from who converts and why, propose fresh campaign angles and \
audiences we are not using yet (specific communities, employers, life events, NRI segments, referral mechanics, \
offline events, partnerships), each with a hook and why it should work, plus small experiments to test them.

<previous_playbook>{prev['content'] if prev else 'none'}</previous_playbook>
<data>{json.dumps(data, default=str, ensure_ascii=False)}</data>"""
    resp = get_client().beta.messages.create(
        model=s.agent.get("model", "claude-opus-5-5"),
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": PLAYBOOK_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        db.audit(None, "system", "learning_failed", resp.stop_reason)
        return None
    playbook = json.loads(next(b.text for b in resp.content if b.type == "text"))
    db.insert("insights", {"kind": "playbook", "content": json.dumps(playbook, ensure_ascii=False),
                           "based_on": closed, "created_at": db.now_iso()})
    db.audit(None, "system", "learning", f"playbook from {closed} closed leads")
    return playbook


def due() -> bool:
    row = db.q1("SELECT created_at FROM insights WHERE kind = 'playbook' ORDER BY id DESC LIMIT 1")
    if not row:
        return True
    days = float(get_settings().learning.get("run_every_days", 7))
    return get_settings().now() - db.parse_dt(row["created_at"]) > timedelta(days=days)
