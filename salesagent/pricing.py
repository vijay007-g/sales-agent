"""Negotiation guardrails. These rules live in code, so the AI cannot talk its way past them.

* The AI never sees floor prices.
* Up to `auto_approve_discount_pct` off list (default 0) plus free concessions -> the AI may agree itself.
* Anything else -> management must approve BEFORE the customer hears it.
* Unit area is fixed; any area-related concession is refused.
* Below the floor -> blocked outright; owner is informed and may still counter manually.
"""
from __future__ import annotations

import json

from . import channels, db
from .config import get_settings


def fmt_money(amount: int | float | None) -> str:
    if amount is None:
        return "-"
    cur = get_settings().business.get("currency", "INR")
    if cur == "INR":
        a = float(amount)
        if a >= 1e7:
            return f"₹{a / 1e7:.2f} Cr"
        if a >= 1e5:
            return f"₹{a / 1e5:.2f} L"
        return f"₹{a:,.0f}"
    return f"{cur} {amount:,.0f}"


def public_unit_info(project: dict) -> list[dict]:
    """Unit data safe to show the AI (no floor price)."""
    out = []
    for u in project["units"]:
        out.append({k: v for k, v in u.items() if k != "floor_price"})
    return out


def evaluate(lead_id: int, project: str, unit_type: str, offered_price: int,
             concessions: list[str], payment_terms: str, customer_ask: int | None,
             justification: str, unit_no: str = "") -> dict:
    from . import inventory
    s = get_settings()
    proj = inventory.get_project(project)
    if not proj:
        return {"ok": False, "error": f"Unknown project '{project}'. Use search_properties to find valid projects."}
    unit = inventory.find_unit(proj, unit_type, unit_no, lead_id)
    if not unit:
        return {"ok": False, "error": f"No available {unit_type} {unit_no} in {proj['name']} (sold or not listed). "
                                      "Use search_properties to offer an alternative."}

    list_price = int(unit["list_price"])
    floor = int(unit["floor_price"])
    offered_price = int(offered_price)
    if offered_price > list_price:
        return {"ok": False, "error": "Offered price is above list price; quote the list price instead."}

    area_words = ("sqft", "sq ft", "square", "area", "carpet", "super built", "extra space", "bigger")
    if any(w in " ".join(concessions).lower() for w in area_words):
        return {"ok": False, "error": "Unit area is fixed and can never be changed or offered as a concession. "
                                      "Negotiate only on price, payment terms or the listed extras."}

    discount_pct = round((list_price - offered_price) / list_price * 100, 2)
    free = {c.lower() for c in proj.get("free_concessions", [])}
    unknown_or_paid = [c for c in concessions if c.lower() not in free]
    auto_pct = float(s.agent.get("auto_approve_discount_pct", 0) or 0)

    if offered_price < floor:
        status = "blocked_floor"
    elif discount_pct <= auto_pct and not unknown_or_paid:
        status = "auto_approved"
    else:
        status = "pending_approval"

    offer_id = db.insert("offers", {
        "lead_id": lead_id, "project": proj["name"], "unit_type": unit["unit_type"],
        "unit_no": unit["unit_no"] or unit_no, "unit_id": unit["id"], "project_id": proj["id"],
        "list_price": list_price, "offered_price": offered_price, "discount_pct": discount_pct,
        "concessions": json.dumps(concessions), "payment_terms": payment_terms,
        "customer_ask": customer_ask, "justification": justification, "status": status,
        "created_at": db.now_iso(),
    })
    db.audit(lead_id, "agent", "offer_" + status, {"offer_id": offer_id, "price": offered_price,
                                                   "discount_pct": discount_pct})
    lead = db.get_lead(lead_id)

    if status == "auto_approved":
        return {"ok": True, "offer_id": offer_id, "status": status,
                "message": (f"Approved within your authority: {fmt_money(offered_price)} "
                            f"({discount_pct}% off list). You may present it to the customer now.")}

    if status == "pending_approval":
        notify_owner_offer(offer_id)
        return {"ok": True, "offer_id": offer_id, "status": status,
                "message": ("This needs management approval. It has been sent. Tell the customer "
                            "you are checking with management and will come back shortly. Do NOT promise "
                            "this price. You will be woken up when the owner decides.")}

    # blocked_floor
    channels.notify_staff(s.owner["phone"], (
        f"FYI (no action needed): {lead['name']} (lead #{lead_id}) asked for "
        f"{fmt_money(customer_ask or offered_price)} on {unit['unit_type']} at {proj['name']}. This is below "
        f"your floor, so the AI did not offer it. To counter anyway reply: COUNTER {offer_id} <price>"))
    return {"ok": True, "offer_id": offer_id, "status": status,
            "message": ("That price is not possible. Do not offer it and do not propose it again. "
                        "Hold at the best approved price, offer value (payment plan, free concessions), "
                        "or propose a different unit that fits the budget.")}


def notify_owner_offer(offer_id: int) -> None:
    s = get_settings()
    o = db.q1("SELECT * FROM offers WHERE id = ?", (offer_id,))
    lead = db.get_lead(o["lead_id"])
    from . import inventory
    unit = db.q1("SELECT * FROM units WHERE id = ?", (o["unit_id"],)) if o.get("unit_id") else None
    unit = unit or {}
    margin_note = ""
    if unit.get("floor_price"):
        margin_note = f"\nAbove floor by: {fmt_money(o['offered_price'] - unit['floor_price'])}"
    proj = inventory.get_project(o["project_id"] or o["project"])
    if proj and not proj["is_own"]:
        margin_note += (f"\nPartner project ({proj['builder']}): your commission at this price ≈ "
                        f"{fmt_money(inventory.commission_for(proj, o['offered_price']))}")
    conc = ", ".join(json.loads(o["concessions"] or "[]")) or "none"
    text = (
        f"APPROVAL NEEDED #{offer_id}\n"
        f"Lead: {lead['name']} (#{lead['id']}, score {lead['score']}, {lead['temperature']})\n"
        f"{o['unit_type']} {o['unit_no'] or ''} @ {o['project']}\n"
        f"List: {fmt_money(o['list_price'])}  ->  Proposed: {fmt_money(o['offered_price'])} "
        f"({o['discount_pct']}% off){margin_note}\n"
        f"Customer asked: {fmt_money(o['customer_ask'])}\n"
        f"Extras: {conc}\nTerms: {o['payment_terms'] or '-'}\n"
        f"Why: {o['justification']}\n\n"
        f"Reply:  APPROVE {offer_id}   |   REJECT {offer_id} <note>   |   COUNTER {offer_id} <price> <note>"
    )
    channels.notify_staff(s.owner["phone"], text)


def best_approved_offer(lead_id: int) -> dict | None:
    return db.q1(
        "SELECT * FROM offers WHERE lead_id = ? AND status IN ('auto_approved','approved','countered') "
        "ORDER BY id DESC LIMIT 1", (lead_id,))
