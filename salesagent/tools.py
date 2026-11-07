"""Tools the AI agent can call. Every tool is scoped to ONE lead and validated in code."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta

from . import channels, db, inventory, leads, pipeline, pricing, sales_kit, team, visits
from .config import get_settings

MAX_MESSAGES_PER_RUN = 3


@dataclass
class ToolContext:
    lead_id: int
    event: str
    messages_sent: int = 0
    followup_set: bool = False
    call_task_set: bool = False
    api_ok: bool = False
    actions: list[str] = field(default_factory=list)


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


STR = {"type": "string"}
INT = {"type": "integer"}

TOOLS: list[dict] = [
    {
        "name": "update_lead_profile",
        "description": (
            "Save what you learned about the customer. Call this whenever the customer reveals budget, "
            "unit preference, timeline, purpose, financing, language, or anything useful. `memory_note` "
            "is appended to your long-term notes on this lead (preferences, family, objections, promises "
            "made) - write it so a colleague could pick up the conversation."),
        "input_schema": _obj({
            "name": STR, "email": STR, "language": STR,
            "city": {"type": "string", "description": "City they want to buy in, e.g. Chennai or Bangalore"},
            "project_interest": STR, "unit_type": STR,
            "budget_min": INT, "budget_max": INT,
            "timeline": {"type": "string", "description": "e.g. 'immediate', '3 months', '6+ months'"},
            "purpose": {"type": "string", "description": "self-use / investment / rental"},
            "location_pref": STR, "financing": {"type": "string", "description": "loan / own funds / mixed"},
            "temperature": {"type": "string", "enum": ["hot", "warm", "cold", "unknown"]},
            "memory_note": STR,
        }, []),
    },
    {
        "name": "set_stage",
        "description": (
            "Move the lead in the sales funnel. Allowed by you: contacted, qualified, negotiation, "
            "nurture (not now - long-term follow-up), lost (give a reason). Visit, booking and closing "
            "stages are set automatically by the other tools."),
        "input_schema": _obj({
            "stage": {"type": "string", "enum": ["contacted", "qualified", "negotiation", "nurture", "lost"]},
            "reason": STR}, ["stage", "reason"]),
    },
    {
        "name": "send_message",
        "description": (
            "Send a WhatsApp/email message to the customer, in the voice of the assigned salesperson (it goes "
            "out under their name, from their number). Short, natural, like a real person typing on their "
            "phone. One clear next step per message. Max 3 per turn."),
        "input_schema": _obj({
            "text": STR,
            "channel": {"type": "string", "enum": ["whatsapp", "email"]},
            "subject": {"type": "string", "description": "Email subject (email only)"},
        }, ["text", "channel"]),
    },
    {
        "name": "search_properties",
        "description": (
            "Find real, currently available units across ALL our projects (own and partner builders) that fit "
            "the customer. Use it before recommending anything, and whenever the budget, city, size or possession "
            "need changes. Returns up to 8 units, best match first, with list price and why it matches. Recommend "
            "the best 2-3 with a short reason each; never mention a project or unit that the search didn't return."),
        "input_schema": _obj({
            "city": STR, "budget_max": INT, "budget_min": INT,
            "unit_type": {"type": "string", "description": "e.g. 2BHK; leave empty to see all sizes"},
            "locality": {"type": "string", "description": "Preferred area, e.g. Vadapalani"},
            "possession": {"type": "string", "enum": ["any", "ready", "within_1y"]},
        }, []),
    },
    {
        "name": "get_project_details",
        "description": (
            "All approved facts about one project: builder, RERA, highlights, payment plans, possession, every "
            "available unit (number, floor, facing, size, price) and which extras are allowed. Use it before "
            "answering detailed questions or naming a specific unit."),
        "input_schema": _obj({"project": STR}, ["project"]),
    },
    {
        "name": "send_brochure",
        "description": (
            "Send the customer the project's brochure, floor plan or photos as WhatsApp attachments (uploaded by the "
            "team). Use when they ask for details, plans or pictures, or after recommending a project. `caption` is a "
            "short line you write to go with it."),
        "input_schema": _obj({
            "project": STR,
            "kind": {"type": "string", "enum": ["brochure", "floor_plan", "photo", "price_list", "any"]},
            "unit_type": {"type": "string", "description": "e.g. 2BHK, to pick the right floor plan"},
            "caption": STR}, ["project", "kind", "caption"]),
    },
    {
        "name": "send_cost_sheet",
        "description": (
            "Send an exact cost sheet for a unit: unit price (list price, or the management-approved price for this "
            "customer), GST, stamp duty, registration and other charges, and the approximate total. Calculated by "
            "the system — never type cost figures yourself."),
        "input_schema": _obj({"project": STR, "unit_no": STR, "unit_type": STR}, ["project"]),
    },
    {
        "name": "send_emi_illustration",
        "description": (
            "Send an EMI illustration (loan amount, monthly EMI for a few tenures, total interest) calculated by the "
            "system for a unit's price, or for a price you pass. Use when the customer is taking a loan or asks "
            "about monthly payments. Defaults: settings' down payment, interest rate and tenure."),
        "input_schema": _obj({"project": STR, "unit_no": STR, "unit_type": STR, "price": INT,
                              "down_payment_pct": {"type": "number"}, "rate_pct": {"type": "number"},
                              "tenure_years": {"type": "number"}}, []),
    },
    {
        "name": "get_visit_slots",
        "description": "List free site-visit slots for a project on a date (YYYY-MM-DD).",
        "input_schema": _obj({"project": STR, "date": STR}, ["project", "date"]),
    },
    {
        "name": "book_site_visit",
        "description": (
            "Book a site visit at a free slot (ISO datetime from get_visit_slots). Assigns a site person "
            "and notifies them. Only book after the customer has agreed to the specific time. Booking "
            "again for the same lead reschedules it."),
        "input_schema": _obj({"project": STR, "datetime": STR,
                              "notes_for_site_person": STR}, ["project", "datetime", "notes_for_site_person"]),
    },
    {
        "name": "cancel_site_visit",
        "description": "Cancel a scheduled visit (customer can't make it and no new time yet).",
        "input_schema": _obj({"visit_id": INT, "reason": STR}, ["visit_id", "reason"]),
    },
    {
        "name": "schedule_followup",
        "description": (
            "Set when you should next reach out if the customer goes quiet, and why. If the customer "
            "named a time ('call me Monday'), use it. Otherwise the default cadence applies."),
        "input_schema": _obj({"hours_from_now": {"type": "number"}, "purpose": STR},
                             ["hours_from_now", "purpose"]),
    },
    {
        "name": "create_call_task",
        "description": (
            "Ask the assigned salesperson to PHONE the customer. Calls are the main channel for building trust; "
            "plan one at every stage: intro call right after a new lead, confirmation call before a visit, "
            "post-visit call the same day, offer call, booking/payment call, and when the customer goes quiet. "
            "The brief is what the salesperson reads just before dialing: who the customer is, what happened so "
            "far, the ONE goal of the call, 3-5 talking points, likely objections with suggested answers, and "
            "what to agree on before hanging up. Only one open call task per lead (this replaces it)."),
        "input_schema": _obj({
            "purpose": {"type": "string", "description": "One line goal, e.g. 'Fix site visit for Saturday'"},
            "minutes_from_now": {"type": "number"},
            "brief": STR}, ["purpose", "minutes_from_now", "brief"]),
    },
    {
        "name": "save_conversion_strategy",
        "description": (
            "After a site visit (or when the picture changes), write the plan to convert this lead to a booking, "
            "based on the site visit report, calls and messages. The salesperson and management see it, and "
            "you follow it in later turns. Price moves in the plan are proposals only: they still need "
            "propose_offer and management approval. Unit area is never part of the plan."),
        "input_schema": _obj({
            "situation": {"type": "string", "description": "Where the customer stands, in 2-3 lines"},
            "buying_motivators": {"type": "array", "items": STR},
            "objections_and_answers": {"type": "array", "items": STR},
            "recommended_unit": STR,
            "decision_maker_and_influencers": STR,
            "price_plan": {"type": "string", "description": "Opening position, and what concession to ask "
                                                            "management for if needed, in exchange for what"},
            "next_actions": {"type": "array", "items": STR,
                             "description": "Dated steps (calls, messages, revisit, offer, office visit)"},
            "risk": {"type": "string", "description": "What could make us lose this lead"},
        }, ["situation", "buying_motivators", "objections_and_answers", "recommended_unit",
            "decision_maker_and_influencers", "price_plan", "next_actions", "risk"]),
    },
    {
        "name": "get_office_slots",
        "description": "Free slots at the builder's office on a date (YYYY-MM-DD), for paying the advance in person.",
        "input_schema": _obj({"date": STR}, ["date"]),
    },
    {
        "name": "book_office_visit",
        "description": (
            "Book the customer's visit to the builder's office (to pay the booking advance / sign papers) once "
            "they choose a time. Management is notified."),
        "input_schema": _obj({"datetime": STR, "purpose": STR}, ["datetime", "purpose"]),
    },
    {
        "name": "share_payment_details",
        "description": (
            "Send the customer the builder's OFFICIAL bank account / UPI details for the booking advance, as a "
            "fixed, verified message. Use only after management has confirmed the booking (stage "
            "payment_pending). Never type account details yourself."),
        "input_schema": _obj({"booking_id": INT}, ["booking_id"]),
    },
    {
        "name": "propose_offer",
        "description": (
            "Ask management to approve a price / terms / extras BEFORE the customer hears them. You will be "
            "woken up with the decision (approve / counter / reject). Until then tell the customer you are "
            "checking with management, without hinting at a number. List price needs no approval. Area is "
            "fixed and cannot be offered."),
        "input_schema": _obj({
            "project": STR, "unit_type": STR, "unit_no": STR,
            "offered_price": {"type": "integer", "description": "Total price you propose, in currency units"},
            "concessions": {"type": "array", "items": STR},
            "payment_terms": STR,
            "customer_ask": {"type": "integer", "description": "What the customer asked for (0 if none)"},
            "justification": {"type": "string", "description": "For the owner: why this deal is worth it"},
        }, ["project", "unit_type", "offered_price", "concessions", "payment_terms", "customer_ask",
            "justification"]),
    },
    {
        "name": "request_booking_confirmation",
        "description": (
            "Customer has clearly agreed to an APPROVED offer (or list price) and wants to book. Sends it to "
            "management for confirmation. Tell the customer the booking is being confirmed - not that it is done. "
            "token_amount is the booking advance (use the standard advance unless management said otherwise)."),
        "input_schema": _obj({"offer_id": INT, "token_amount": INT, "notes": STR},
                             ["offer_id", "token_amount", "notes"]),
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand over to the owner when: customer is angry, asks for a call with a person, legal / RERA / "
            "refund / complaint questions, a question you can't answer from the facts you have, or anything "
            "risky. The owner gets notified."),
        "input_schema": _obj({"reason": STR, "urgency": {"type": "string", "enum": ["low", "normal", "high"]}},
                             ["reason", "urgency"]),
    },
    {
        "name": "mark_opted_out",
        "description": "Customer asked to stop messages / not interested in being contacted. Stops all outreach.",
        "input_schema": _obj({"reason": STR}, ["reason"]),
    },
    {
        "name": "add_referral",
        "description": (
            "Customer shared a friend/relative who may be interested AND said that person is okay being "
            "contacted. Creates a new lead from the referral."),
        "input_schema": _obj({"name": STR, "phone": STR, "relation": STR, "notes": STR},
                             ["name", "phone", "relation", "notes"]),
    },
]


# ------------------------- implementations -------------------------

def _update_lead_profile(ctx: ToolContext, a: dict) -> dict:
    allowed = {"name", "email", "language", "city", "project_interest", "unit_type", "budget_min", "budget_max",
               "timeline", "purpose", "location_pref", "financing", "temperature"}
    changes = {k: v for k, v in a.items() if k in allowed and v not in (None, "")}
    note = (a.get("memory_note") or "").strip()
    if note:
        lead = db.get_lead(ctx.lead_id)
        stamp = get_settings().now().strftime("%d %b")
        memory = ((lead.get("memory") or "") + f"\n[{stamp}] {note}").strip()
        changes["memory"] = memory[-6000:]
    db.update("leads", ctx.lead_id, changes)
    score = leads.rescore(ctx.lead_id)
    return {"ok": True, "saved": sorted(changes), "score": score}


def _set_stage(ctx: ToolContext, a: dict) -> dict:
    try:
        lead = pipeline.move(ctx.lead_id, a["stage"], "agent", a.get("reason", ""))
        return {"ok": True, "stage": lead["stage"]}
    except pipeline.StageError as e:
        return {"ok": False, "error": str(e)}


def _send_message(ctx: ToolContext, a: dict) -> dict:
    lead = db.get_lead(ctx.lead_id)
    if lead["opted_out"]:
        return {"ok": False, "error": "Customer opted out. Do not message them."}
    if ctx.messages_sent >= MAX_MESSAGES_PER_RUN:
        return {"ok": False, "error": "Message limit for this turn reached. Wait for the customer."}
    text = (a.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "Empty message."}
    res = team.send_or_draft(ctx.lead_id, text, a.get("channel", "whatsapp"), a.get("subject") or "")
    if res.get("ok"):
        ctx.messages_sent += 1
        if lead["stage"] == "new":
            try:
                pipeline.move(ctx.lead_id, "contacted", "agent", "first outreach")
            except pipeline.StageError:
                pass
    return res


def _create_call_task(ctx: ToolContext, a: dict) -> dict:
    ctx.call_task_set = True
    return team.create_call_task(ctx.lead_id, a["purpose"], float(a["minutes_from_now"]), a["brief"])


def _save_strategy(ctx: ToolContext, a: dict) -> dict:
    lead = db.get_lead(ctx.lead_id)
    a = {**a, "written_at": get_settings().now().strftime("%d %b %H:%M")}
    db.update("leads", ctx.lead_id, {"strategy": json.dumps(a, ensure_ascii=False)})
    rm = team.rm_for(lead)
    lines = [f"STRATEGY for {lead['name']} (#{lead['id']})", a["situation"],
             "Motivators: " + "; ".join(a["buying_motivators"]),
             "Objections: " + " | ".join(a["objections_and_answers"]),
             "Unit: " + a["recommended_unit"], "Price plan: " + a["price_plan"],
             "Next: " + " -> ".join(a["next_actions"]), "Risk: " + a["risk"]]
    channels.notify_staff(rm["phone"], "\n".join(lines))
    db.audit(ctx.lead_id, "agent", "strategy", a)
    return {"ok": True, "message": "Strategy saved and shared with the salesperson."}


def _get_office_slots(ctx: ToolContext, a: dict) -> dict:
    try:
        return {"ok": True, "slots": visits.office_slots(a["date"])[:12],
                "address": get_settings().booking.get("office_address", "")}
    except ValueError:
        return {"ok": False, "error": "Date must be YYYY-MM-DD."}


def _book_office_visit(ctx: ToolContext, a: dict) -> dict:
    return visits.book_office(ctx.lead_id, a["datetime"], a.get("purpose", "Booking advance"))


def payee_for(booking: dict) -> dict:
    """Whose account the advance goes to: the partner builder for partner projects, else our company account."""
    b = get_settings().booking
    own = {"payee_name": b.get("payee_name", ""), "bank_name": b.get("bank_name", ""),
           "account_number": b.get("account_number", ""), "ifsc": b.get("ifsc", ""), "upi_id": b.get("upi_id", ""),
           "verify_phone": b.get("verify_phone", ""), "office_address": b.get("office_address", "")}
    unit = db.q1("SELECT * FROM units WHERE id = ?", (booking.get("unit_id"),)) if booking.get("unit_id") else None
    proj = inventory.get_project(unit["project_id"]) if unit else None
    if not proj or proj["is_own"]:
        return own
    bl = inventory.builder_for(proj)
    return {"payee_name": bl.get("bank_payee") or "", "bank_name": bl.get("bank_name") or "",
            "account_number": bl.get("bank_account") or "", "ifsc": bl.get("bank_ifsc") or "",
            "upi_id": bl.get("upi_id") or "", "verify_phone": bl.get("verify_phone") or bl.get("contact_phone") or "",
            "office_address": bl.get("office_address") or "", "builder": bl.get("name", "")}


def payment_message(booking: dict) -> str:
    b = payee_for(booking)
    amt = pricing.fmt_money(booking.get("token_amount") or get_settings().booking.get("advance_amount"))
    lines = [f"Booking advance: {amt}",
             f"Please pay ONLY to {'the builder ' + b['builder'] + chr(39) + 's' if b.get('builder') else 'our company'} "
             "account:",
             f"Account name: {b['payee_name']}", f"Bank: {b['bank_name']}",
             f"A/c no: {b['account_number']}", f"IFSC: {b['ifsc']}"]
    if b.get("upi_id"):
        lines.append(f"UPI: {b['upi_id']}")
    lines += [f"Reference: Booking B{booking['id']}",
              f"Before paying, you can verify these details by calling {b['verify_phone']}. "
              "We will never ask you to pay into a personal account."]
    if b.get("office_address"):
        lines.append(f"You can also pay in person at: {b['office_address']}.")
    lines.append("Please share the payment receipt / UTR here once done.")
    return "\n".join(lines)


def _share_payment_details(ctx: ToolContext, a: dict) -> dict:
    bk = db.q1("SELECT * FROM bookings WHERE id = ? AND lead_id = ?", (int(a["booking_id"]), ctx.lead_id))
    if not bk:
        return {"ok": False, "error": "Booking not found for this lead."}
    if bk["status"] != "confirmed":
        return {"ok": False, "error": f"Booking is '{bk['status']}'. Payment details are shared only after "
                                      "management confirms the booking."}
    payee = payee_for(bk)
    if not (payee["payee_name"] and payee["account_number"] and payee["ifsc"]):
        return {"ok": False, "error": "The bank details for this payee are not set up yet. Escalate to a human "
                                      "(escalate_to_human) so management can share them; do not type any account "
                                      "details yourself."}
    # Fixed text from settings, delivered directly (not drafted) so it can't be altered.
    res = team.deliver(ctx.lead_id, payment_message(bk), "whatsapp", author="system")
    if res.get("ok"):
        db.audit(ctx.lead_id, "agent", "payment_details_shared", {"booking_id": bk["id"]})
    return {**res, "message": "Official payment details sent. Ask them to share the receipt/UTR after paying, "
                              "or to choose an office visit time."}


def _search_properties(ctx: ToolContext, a: dict) -> dict:
    lead = db.get_lead(ctx.lead_id)
    res = inventory.search(city=a.get("city") or lead.get("city") or "",
                           budget_max=a.get("budget_max") or lead.get("budget_max"),
                           budget_min=a.get("budget_min") or lead.get("budget_min"),
                           unit_type=a.get("unit_type") or "", locality=a.get("locality") or lead.get("location_pref") or "",
                           possession=a.get("possession") or "any")
    for r in res:
        r["price"] = pricing.fmt_money(r["list_price"])
    if not res:
        return {"ok": True, "matches": [], "message": "Nothing available matches. Try a wider budget, another size, "
                                                      "another locality or city, or 'any' possession — or tell the "
                                                      "customer honestly and ask what they could flex on.",
                "cities_we_cover": inventory.cities()}
    return {"ok": True, "matches": res}


def _get_project_details(ctx: ToolContext, a: dict) -> dict:
    p = inventory.get_project(a["project"])
    if not p or not p["active"]:
        return {"ok": False, "error": "No such active project. Use search_properties.",
                "projects": inventory.project_names()}
    facts = inventory.project_facts(p)
    for u in facts["available_units"]:
        u["price"] = pricing.fmt_money(u["list_price"])
    return {"ok": True, **facts}


def _kit_send(ctx: ToolContext, text: str, media_id: int | None = None) -> dict:
    lead = db.get_lead(ctx.lead_id)
    if lead["opted_out"]:
        return {"ok": False, "error": "Customer opted out."}
    if ctx.messages_sent >= MAX_MESSAGES_PER_RUN:
        return {"ok": False, "error": "Message limit for this turn reached. Wait for the customer."}
    res = team.send_or_draft(ctx.lead_id, text, "whatsapp", "", media_id=media_id)
    if res.get("ok"):
        ctx.messages_sent += 1
    return res


def _resolve_unit(ctx: ToolContext, a: dict):
    p = inventory.get_project(a.get("project", ""))
    if not p:
        return None, None, {"ok": False, "error": "Unknown project. Use search_properties."}
    lead = db.get_lead(ctx.lead_id)
    unit = inventory.find_unit(p, a.get("unit_type") or lead.get("unit_type") or "", a.get("unit_no") or "",
                               ctx.lead_id)
    if not unit:
        return p, None, {"ok": False, "error": f"No available {a.get('unit_type') or ''} {a.get('unit_no') or ''} in "
                                               f"{p['name']}. Check get_project_details for unit types."}
    return p, unit, None


def _send_brochure(ctx: ToolContext, a: dict) -> dict:
    p = inventory.get_project(a.get("project", ""))
    if not p:
        return {"ok": False, "error": "Unknown project."}
    files = sales_kit.find_media(p["id"], a.get("kind", "any"), a.get("unit_type", ""))[:3]
    if not files:
        have = sales_kit.media_summary(p["id"])
        return {"ok": False, "error": f"No {a.get('kind')} uploaded for {p['name']}."
                                      + (f" Available: {'; '.join(have)}." if have else " Nothing uploaded yet.")
                                      + " Tell the customer the team will share it, and mention it in a call task."}
    sent = []
    for i, m in enumerate(files):
        res = _kit_send(ctx, (a.get("caption") or "") if i == 0 else "", m["id"])
        if not res.get("ok"):
            return {**res, "sent_so_far": sent}
        sent.append(m["title"])
    return {"ok": True, "sent": sent}


def _send_cost_sheet(ctx: ToolContext, a: dict) -> dict:
    p, unit, err = _resolve_unit(ctx, a)
    if err:
        return err
    cs = sales_kit.cost_sheet(p, unit, ctx.lead_id)
    res = _kit_send(ctx, cs["text"])
    return {**res, "total": pricing.fmt_money(cs["total"]), "unit_price": pricing.fmt_money(cs["price"])}


def _send_emi(ctx: ToolContext, a: dict) -> dict:
    price = a.get("price")
    if not price:
        p, unit, err = _resolve_unit(ctx, a)
        if err:
            return err
        price = sales_kit.approved_price(ctx.lead_id, unit)[0]
    ill = sales_kit.emi_illustration(int(price), a.get("down_payment_pct"), a.get("rate_pct"), a.get("tenure_years"))
    return {**_kit_send(ctx, ill["text"]), "loan": pricing.fmt_money(ill["loan"])}


def _get_visit_slots(ctx: ToolContext, a: dict) -> dict:
    try:
        slots = visits.free_slots(a["project"], a["date"])
    except ValueError:
        return {"ok": False, "error": "Date must be YYYY-MM-DD."}
    return {"ok": True, "slots": slots[:16]}


def _book_site_visit(ctx: ToolContext, a: dict) -> dict:
    return visits.book(ctx.lead_id, a["project"], a["datetime"], a.get("notes_for_site_person", ""))


def _cancel_site_visit(ctx: ToolContext, a: dict) -> dict:
    return visits.cancel(ctx.lead_id, int(a["visit_id"]), a.get("reason", ""))


def _schedule_followup(ctx: ToolContext, a: dict) -> dict:
    hours = max(0.25, min(float(a["hours_from_now"]), 24 * 120))
    when = get_settings().now() + timedelta(hours=hours)
    db.update("leads", ctx.lead_id, {"next_followup_at": when.isoformat(timespec="minutes"),
                                     "followup_purpose": a.get("purpose", "")})
    ctx.followup_set = True
    return {"ok": True, "next_followup_at": when.isoformat(timespec="minutes")}


def _propose_offer(ctx: ToolContext, a: dict) -> dict:
    res = pricing.evaluate(ctx.lead_id, a["project"], a["unit_type"], int(a["offered_price"]),
                           list(a.get("concessions") or []), a.get("payment_terms", ""),
                           int(a.get("customer_ask") or 0) or None, a.get("justification", ""),
                           a.get("unit_no", ""))
    if res.get("ok"):
        lead = db.get_lead(ctx.lead_id)
        if lead["stage"] not in ("negotiation", "booking_pending"):
            try:
                pipeline.move(ctx.lead_id, "negotiation", "agent", "offer proposed")
            except pipeline.StageError:
                pass
    return res


def _request_booking_confirmation(ctx: ToolContext, a: dict) -> dict:
    o = db.q1("SELECT * FROM offers WHERE id = ? AND lead_id = ?", (int(a["offer_id"]), ctx.lead_id))
    if not o:
        return {"ok": False, "error": "Offer not found for this lead."}
    if o["status"] not in ("auto_approved", "approved", "countered"):
        return {"ok": False, "error": f"Offer status is '{o['status']}' - it must be approved first."}
    if db.q1("SELECT id FROM bookings WHERE lead_id = ? AND status = 'awaiting_owner'", (ctx.lead_id,)):
        return {"ok": False, "error": "A booking is already waiting for the owner's confirmation."}
    price = o["owner_counter_price"] or o["offered_price"]
    bid = db.insert("bookings", {"lead_id": ctx.lead_id, "offer_id": o["id"], "unit_id": o.get("unit_id"),
                                 "status": "awaiting_owner",
                                 "token_amount": int(a.get("token_amount") or 0)
                                 or int(get_settings().booking.get("advance_amount", 0)),
                                 "notes": a.get("notes", ""), "created_at": db.now_iso()})
    lead = db.get_lead(ctx.lead_id)
    try:
        if lead["stage"] != "negotiation":
            pipeline.move(ctx.lead_id, "negotiation", "agent", "pre-booking")
        pipeline.move(ctx.lead_id, "booking_pending", "system", f"booking #{bid}")
    except pipeline.StageError as e:
        db.update("bookings", bid, {"status": "cancelled", "notes": str(e)})
        return {"ok": False, "error": str(e)}
    s = get_settings()
    channels.notify_staff(s.owner["phone"], (
        f"BOOKING TO CONFIRM B{bid}\n{lead['name']} ({lead['phone']}) · Sales: {lead.get('rm_name') or '-'}\n"
        f"{o['unit_type']} {o['unit_no'] or ''} @ {o['project']} for {pricing.fmt_money(price)}\n"
        f"Token: {pricing.fmt_money(a.get('token_amount'))}\nNotes: {a.get('notes') or '-'}\n\n"
        f"Reply: CONFIRM B{bid}   |   HOLD B{bid} <note>"))
    db.audit(ctx.lead_id, "agent", "booking_requested", {"booking_id": bid, "offer_id": o["id"]})
    return {"ok": True, "booking_id": bid, "status": "awaiting_owner",
            "message": "Sent to management. Tell the customer their booking is being confirmed; once confirmed "
                       "you will share the official payment details for the advance."}


def _escalate(ctx: ToolContext, a: dict) -> dict:
    lead = db.get_lead(ctx.lead_id)
    db.update("leads", ctx.lead_id, {"needs_human": 1})
    s = get_settings()
    channels.notify_staff(s.owner["phone"], (
        f"{'URGENT ' if a.get('urgency') == 'high' else ''}HUMAN NEEDED — lead #{lead['id']} "
        f"{lead['name']} ({lead['phone']})\nStage: {lead['stage']}\nReason: {a['reason']}\n"
        f"Sales: {lead.get('rm_name') or '-'}\nReply RESUME {lead['id']} when the AI may continue."))
    db.audit(ctx.lead_id, "agent", "escalated", a)
    return {"ok": True, "message": "Owner notified. The AI is paused on this lead until they resume it. "
                                   "You may send one short holding message saying a team member will call."}


def _opt_out(ctx: ToolContext, a: dict) -> dict:
    db.update("leads", ctx.lead_id, {"opted_out": 1, "next_followup_at": None})
    try:
        pipeline.move(ctx.lead_id, "lost", "agent", "opted out: " + a.get("reason", ""))
    except pipeline.StageError:
        pass
    db.audit(ctx.lead_id, "agent", "opted_out", a)
    return {"ok": True, "message": "Opted out. You may send ONE short polite acknowledgement, nothing more."}


def _add_referral(ctx: ToolContext, a: dict) -> dict:
    referrer = db.get_lead(ctx.lead_id)
    try:
        lead, created = leads.upsert_lead({
            "name": a["name"], "phone": a["phone"], "source": "referral",
            "campaign": f"ref:{referrer['id']}"})
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    db.update("leads", lead["id"], {"memory": f"Referred by {referrer['name']} ({a.get('relation')}). "
                                              f"{a.get('notes', '')}"})
    db.audit(lead["id"], "agent", "referral", {"from": referrer["id"]})
    return {"ok": True, "lead_id": lead["id"], "created": created,
            "message": "Referral saved. The new lead will be contacted automatically."}


HANDLERS = {
    "update_lead_profile": _update_lead_profile,
    "set_stage": _set_stage,
    "send_message": _send_message,
    "search_properties": _search_properties,
    "send_brochure": _send_brochure,
    "send_cost_sheet": _send_cost_sheet,
    "send_emi_illustration": _send_emi,
    "get_project_details": _get_project_details,
    "get_visit_slots": _get_visit_slots,
    "book_site_visit": _book_site_visit,
    "cancel_site_visit": _cancel_site_visit,
    "schedule_followup": _schedule_followup,
    "create_call_task": _create_call_task,
    "save_conversion_strategy": _save_strategy,
    "get_office_slots": _get_office_slots,
    "book_office_visit": _book_office_visit,
    "share_payment_details": _share_payment_details,
    "propose_offer": _propose_offer,
    "request_booking_confirmation": _request_booking_confirmation,
    "escalate_to_human": _escalate,
    "mark_opted_out": _opt_out,
    "add_referral": _add_referral,
}


def run_tool(ctx: ToolContext, name: str, args: dict) -> tuple[str, bool]:
    """Returns (json_result, is_error)."""
    fn = HANDLERS.get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool {name}"}), True
    if not isinstance(args, dict):
        return json.dumps({"error": "tool input must be an object"}), True
    required = next(t for t in TOOLS if t["name"] == name)["input_schema"]["required"]
    missing = [r for r in required if r not in args]
    if missing:
        return json.dumps({"error": f"missing fields: {missing}"}), True
    try:
        res = fn(ctx, args)
    except (KeyError, ValueError, TypeError) as e:
        return json.dumps({"error": f"bad input: {e}"}), True
    ctx.actions.append(name)
    db.audit(ctx.lead_id, "agent", "tool:" + name, {"args": args, "ok": res.get("ok")})
    return json.dumps(res, default=str), not res.get("ok", True)
