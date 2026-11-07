"""Lead generation: campaign creation (ads, posts, broadcast templates, forms) and buyer-profile insights.

Generated campaigns are saved as DRAFTS. Nothing is published until the owner approves it in the dashboard,
and the actual ad spend runs in your Meta / Google / portal accounts, which send leads back to
POST /webhook/lead.
"""
from __future__ import annotations

import json

from . import db, pricing
from .agent import get_client
from .config import get_settings

CAMPAIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "campaign_name": {"type": "string"},
        "target_personas": {"type": "array", "items": {"type": "object", "properties": {
            "persona": {"type": "string"}, "why_they_buy": {"type": "string"},
            "targeting": {"type": "string"}}, "required": ["persona", "why_they_buy", "targeting"],
            "additionalProperties": False}},
        "ad_variants": {"type": "array", "items": {"type": "object", "properties": {
            "headline": {"type": "string"}, "primary_text": {"type": "string"},
            "call_to_action": {"type": "string"}, "creative_idea": {"type": "string"}},
            "required": ["headline", "primary_text", "call_to_action", "creative_idea"],
            "additionalProperties": False}},
        "lead_form_questions": {"type": "array", "items": {"type": "string"}},
        "whatsapp_template": {"type": "string"},
        "social_posts": {"type": "array", "items": {"type": "string"}},
        "landing_page": {"type": "object", "properties": {
            "hero": {"type": "string"}, "sub": {"type": "string"},
            "sections": {"type": "array", "items": {"type": "string"}}},
            "required": ["hero", "sub", "sections"], "additionalProperties": False},
        "big_creative_ideas": {"type": "array", "items": {"type": "object", "properties": {
            "idea": {"type": "string"}, "how_to_execute": {"type": "string"}, "why_it_fits_our_buyers": {"type": "string"}},
            "required": ["idea", "how_to_execute", "why_it_fits_our_buyers"], "additionalProperties": False}},
        "two_week_content_calendar": {"type": "array", "items": {"type": "string"}},
        "referral_offer_idea": {"type": "string"},
        "budget_split_advice": {"type": "string"},
        "compliance_notes": {"type": "string"},
    },
    "required": ["campaign_name", "target_personas", "ad_variants", "lead_form_questions", "whatsapp_template",
                 "social_posts", "landing_page", "big_creative_ideas", "two_week_content_calendar",
                 "referral_offer_idea", "budget_split_advice", "compliance_notes"],
    "additionalProperties": False,
}


def _wins_summary() -> str:
    rows = db.q("SELECT source, campaign, unit_type, budget_max, purpose, timeline, location_pref, stage "
                "FROM leads WHERE stage IN ('booked','booking_pending','negotiation','visit_done') LIMIT 200")
    if not rows:
        return "No conversion history yet."
    by_source: dict[str, int] = {}
    for r in rows:
        by_source[r["source"] or "other"] = by_source.get(r["source"] or "other", 0) + 1
    return json.dumps({"converting_leads": len(rows), "by_source": by_source, "sample": rows[:40]}, default=str)


def generate_campaign(project_name: str, channel: str, brief: str = "", monthly_budget: str = "") -> dict:
    s = get_settings()
    from . import inventory
    proj = inventory.get_project(project_name)
    if not proj:
        raise ValueError(f"Unknown project {project_name}")
    facts = inventory.project_facts(proj, max_units=0)
    for t in facts["unit_types"]:
        t["price_range"] = f"{pricing.fmt_money(t['price_min'])}–{pricing.fmt_money(t['price_max'])}"
    prompt = f"""Create a lead-generation campaign for this real-estate project.

<project>{json.dumps(facts, default=str)}</project>
<business>{s.business['name']}, {s.business.get('website', '')}, languages: {s.business.get('languages')}</business>
<channel>{channel}</channel>
<monthly_budget>{monthly_budget or 'not given'}</monthly_budget>
<owner_brief>{brief or 'none'}</owner_brief>
<what_has_converted_so_far>{_wins_summary()}</what_has_converted_so_far>
<conversion_by_campaign_variant>{json.dumps(funnel_report("campaign"))}</conversion_by_campaign_variant>
<learned_playbook>{_playbook()}</learned_playbook>

Be genuinely creative and learn from the data above: double down on the angles, audiences and words that
converted, drop what didn't, and try at least two bold new angles drawn from the playbook's creative ideas and
from who our buyers actually are. Write copy that is specific to this project (no generic "dream home" filler),
uses only the facts given, and is ready to paste into the ad platform. Give 5 ad variants, each testing a
clearly different angle or audience. Lead form questions should qualify (budget, BHK, timeline,
loan) in at most 4 questions. The WhatsApp template must be suitable for Meta approval (opt-in audiences only,
with a clear opt-out line). Compliance notes: RERA number display, no guaranteed-returns claims, consent for
contact, and local telemarketing / data-protection rules."""
    resp = get_client().beta.messages.create(
        model=s.agent.get("model", "claude-opus-5-5"),
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": CAMPAIGN_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("The model declined to generate this campaign.")
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    cid = db.q1("SELECT COALESCE(MAX(id), 0) + 1 n FROM campaigns")["n"]
    for i, ad in enumerate(data["ad_variants"], 1):
        # Put this code in the ad's lead-form hidden field / UTM so each lead is traced to its variant.
        ad["tracking_code"] = f"C{cid}-V{i}"
    cid = db.insert("campaigns", {"name": data["campaign_name"], "channel": channel, "audience": brief,
                                  "content": json.dumps(data, ensure_ascii=False), "status": "draft",
                                  "created_at": db.now_iso()})
    data["id"] = cid
    return data


def _playbook() -> str:
    row = db.q1("SELECT content FROM insights WHERE kind = 'playbook' ORDER BY id DESC LIMIT 1")
    return row["content"] if row else "none yet"


def funnel_report(by: str = "source") -> dict:
    """Conversion by lead source or campaign variant — tells you where to spend on lead generation."""
    col = "campaign" if by == "campaign" else "source"
    rows = db.q(f"SELECT {col} k, stage, COUNT(*) n FROM leads GROUP BY {col}, stage")
    report: dict[str, dict] = {}
    reached_visit = {"visit_scheduled", "visit_done", "negotiation", "booking_pending", "payment_pending", "booked"}
    for r in rows:
        src = report.setdefault(r["k"] or "(none)", {"total": 0, "visits": 0, "booked": 0})
        src["total"] += r["n"]
        if r["stage"] in reached_visit:
            src["visits"] += r["n"]
        if r["stage"] == "booked":
            src["booked"] += r["n"]
    for v in report.values():
        v["visit_rate"] = round(v["visits"] / v["total"] * 100, 1) if v["total"] else 0
        v["booking_rate"] = round(v["booked"] / v["total"] * 100, 1) if v["total"] else 0
    return report
