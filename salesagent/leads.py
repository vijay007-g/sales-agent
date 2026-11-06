"""Lead capture, de-duplication and scoring."""
from __future__ import annotations

import csv
from typing import Iterable

from . import db
from .config import get_settings

FIELDS = ["name", "phone", "email", "source", "campaign", "preferred_channel", "language",
          "project_interest", "unit_type", "budget_min", "budget_max", "timeline", "purpose",
          "location_pref", "financing"]


def _int(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", "").strip()))
    except ValueError:
        return None


def upsert_lead(data: dict, consent: bool = True) -> tuple[dict, bool]:
    """Create a lead or merge into an existing one (matched by phone, then email).
    Returns (lead, created)."""
    clean = {k: data.get(k) for k in FIELDS if data.get(k) not in (None, "")}
    if "phone" in clean:
        clean["phone"] = db.normalize_phone(clean["phone"])
    for k in ("budget_min", "budget_max"):
        if k in clean:
            clean[k] = _int(clean[k])
    if not clean.get("phone") and not clean.get("email"):
        raise ValueError("A lead needs at least a phone number or an email.")

    existing = None
    if clean.get("phone"):
        existing = db.find_lead_by_phone(clean["phone"])
    if not existing and clean.get("email"):
        existing = db.q1("SELECT * FROM leads WHERE lower(email) = lower(?)", (clean["email"],))

    if existing:
        merge = {k: v for k, v in clean.items() if not existing.get(k)}
        db.update("leads", existing["id"], merge)
        db.audit(existing["id"], "system", "lead_merged", {"source": clean.get("source")})
        lead = db.get_lead(existing["id"])
        rescore(lead["id"])
        return db.get_lead(lead["id"]), False

    ts = db.now_iso()
    clean.setdefault("source", "other")
    if not clean.get("phone"):
        clean["preferred_channel"] = "email"
    lead_id = db.insert("leads", {**clean, "stage": "new", "consent": 1 if consent else 0,
                                  "created_at": ts, "updated_at": ts})
    db.audit(lead_id, "system", "lead_created", {"source": clean["source"]})
    rescore(lead_id)
    return db.get_lead(lead_id), True


def import_csv(path: str, source: str = "csv_import") -> dict:
    """Import a portal / ad-platform export. Columns are matched loosely."""
    aliases = {
        "name": ["name", "full_name", "customer name", "lead name"],
        "phone": ["phone", "mobile", "phone_number", "contact", "mobile number"],
        "email": ["email", "email address", "e-mail"],
        "budget_max": ["budget", "budget_max", "max budget"],
        "unit_type": ["unit_type", "bhk", "configuration", "property type"],
        "location_pref": ["location", "locality", "city"],
        "project_interest": ["project", "project name"],
        "campaign": ["campaign", "campaign_name", "ad name"],
        "timeline": ["timeline", "when", "purchase timeline"],
    }
    created = merged = failed = 0
    new_ids: list[int] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            low = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            data = {"source": source}
            for field, names in aliases.items():
                for n in names:
                    if low.get(n):
                        data[field] = low[n]
                        break
            try:
                lead, was_new = upsert_lead(data)
                created += was_new
                if was_new:
                    new_ids.append(lead["id"])
                merged += not was_new
            except ValueError:
                failed += 1
    return {"created": created, "merged": merged, "failed": failed, "new_ids": new_ids}


def _budget_fit(lead: dict) -> float:
    budget = lead.get("budget_max") or lead.get("budget_min")
    if not budget:
        return 0.3  # unknown
    prices = [u["list_price"] for p in get_settings().projects for u in p["units"]]
    if not prices:
        return 0.5
    cheapest = min(prices)
    if budget >= cheapest:
        return 1.0
    gap = (cheapest - budget) / cheapest
    return max(0.0, 1 - gap * 4)   # 10% short -> 0.6, 25% short -> 0


def _timeline(lead: dict) -> float:
    t = (lead.get("timeline") or "").lower()
    if not t:
        return 0.3
    if any(w in t for w in ("immediate", "now", "this month", "1 month", "asap", "urgent")):
        return 1.0
    if any(w in t for w in ("2 month", "3 month", "quarter", "soon")):
        return 0.8
    if any(w in t for w in ("6 month", "this year")):
        return 0.5
    return 0.2


def _engagement(lead: dict) -> float:
    inbound = db.q1("SELECT COUNT(*) n FROM interactions WHERE lead_id = ? AND direction = 'in'",
                    (lead["id"],))["n"]
    visits = db.q1("SELECT COUNT(*) n FROM site_visits WHERE lead_id = ? AND status IN "
                   "('scheduled','completed')", (lead["id"],))["n"]
    score = min(inbound, 6) / 6 * 0.6 + (0.4 if visits else 0)
    if lead.get("temperature") == "hot":
        score = max(score, 0.9)
    return min(score, 1.0)


def rescore(lead_id: int) -> int:
    lead = db.get_lead(lead_id)
    w = get_settings().scoring
    src = (w.get("source_weights") or {}).get(lead.get("source") or "other", 0.4)
    score = (w.get("budget_fit", 35) * _budget_fit(lead)
             + w.get("timeline", 25) * _timeline(lead)
             + w.get("engagement", 25) * _engagement(lead)
             + w.get("source_quality", 15) * src)
    score = int(round(score))
    db.update("leads", lead_id, {"score": score})
    return score


def iter_active() -> Iterable[dict]:
    return db.q("SELECT * FROM leads WHERE stage NOT IN ('booked','lost') ORDER BY score DESC")
