"""Sales kit: brochures / floor plans / photos (uploaded per project), cost sheets and EMI illustrations.

Every number here is calculated by code from approved data (list price or management-approved offer price, and
the project's configured charges) and sent as fixed text, so the AI can never mistype or invent a figure.
"""
from __future__ import annotations

import mimetypes
import os
import re

from . import db, inventory
from .config import DATA_DIR, get_settings
from .pricing import fmt_money

ALLOWED = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
           ".webp": "image/webp"}
MAX_BYTES = {"application/pdf": 16 * 1024 * 1024, "image": 5 * 1024 * 1024}
KINDS = ["brochure", "floor_plan", "photo", "price_list", "other"]


# ------------------------------------------------------------------ media files

def media_dir():
    d = DATA_DIR / "media"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_media(project_id: int, kind: str, title: str, filename: str, data: bytes, unit_type: str = "") -> dict:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED:
        return {"ok": False, "error": "Only PDF, JPG, PNG or WEBP files."}
    mime = ALLOWED[ext]
    limit = MAX_BYTES["application/pdf"] if mime == "application/pdf" else MAX_BYTES["image"]
    if len(data) > limit:
        return {"ok": False, "error": f"File too large (max {limit // (1024 * 1024)} MB for this type — WhatsApp limit)."}
    if not data:
        return {"ok": False, "error": "Empty file."}
    token = db.new_token()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(filename)).strip("-") or f"file{ext}"
    path = media_dir() / f"{token}_{safe}"
    path.write_bytes(data)
    mid = db.insert("media", {"project_id": project_id, "unit_type": (unit_type or "").upper().replace(" BHK", "BHK"),
                              "kind": kind if kind in KINDS else "other", "title": title or safe, "filename": safe,
                              "path": str(path), "token": token, "mime": mime, "size": len(data),
                              "created_at": db.now_iso()})
    return {"ok": True, "media_id": mid}


def delete_media(mid: int) -> None:
    m = db.q1("SELECT * FROM media WHERE id = ?", (mid,))
    if m:
        try:
            os.remove(m["path"])
        except OSError:
            pass
        db.q("DELETE FROM media WHERE id = ?", (mid,))


def media_url(m: dict) -> str:
    from .team import base_url
    return f"{base_url()}/m/{m['token']}/{m['filename']}"


def find_media(project_id: int, kind: str = "any", unit_type: str = "") -> list[dict]:
    rows = db.q("SELECT * FROM media WHERE project_id = ? ORDER BY id", (project_id,))
    if kind and kind != "any":
        rows = [m for m in rows if m["kind"] == kind]
    t = (unit_type or "").replace(" ", "").upper()
    if t:
        exact = [m for m in rows if (m["unit_type"] or "").replace(" ", "").upper() == t]
        general = [m for m in rows if not m["unit_type"]]
        rows = exact or general
    return rows


def media_summary(project_id: int) -> list[str]:
    return [f"{m['kind']}{' ' + m['unit_type'] if m['unit_type'] else ''}: {m['title']}"
            for m in db.q("SELECT * FROM media WHERE project_id = ?", (project_id,))]


# ------------------------------------------------------------------ cost sheet

def _charges(project: dict) -> list[tuple[str, int]]:
    from .events import parse_amount
    out = []
    for line in (project.get("other_charges") or "").splitlines():
        if ":" not in line:
            continue
        label, amt = line.rsplit(":", 1)
        val = parse_amount(amt.strip())
        if label.strip() and val:
            out.append((label.strip(), val))
    return out


def approved_offer(lead_id: int | None, unit: dict) -> dict | None:
    if not lead_id:
        return None
    return db.q1("SELECT * FROM offers WHERE lead_id = ? AND unit_id = ? AND status IN "
                 "('auto_approved','approved','countered','accepted') ORDER BY id DESC LIMIT 1", (lead_id, unit["id"]))


def approved_price(lead_id: int | None, unit: dict) -> tuple[int, str]:
    """Management-approved price for this lead and unit if any, else the list price."""
    o = approved_offer(lead_id, unit)
    if o:
        return int(o["owner_counter_price"] or o["offered_price"]), "your approved price"
    return int(unit["list_price"]), "list price"


def _waived(label: str, concessions: list[str]) -> bool:
    """True if an approved concession covers this charge (e.g. 'Free car parking' covers 'Car parking')."""
    generic = {"charge", "charges", "fees", "cost", "costs", "amount", "free", "extra", "included", "waiver", "total",
               "price", "advance"}
    words = {w for w in re.findall(r"[a-z]+", label.lower()) if len(w) > 3 and w not in generic}
    text = " ".join(concessions).lower()
    return bool(words) and any(w in text for w in words)


def cost_sheet(project: dict, unit: dict, lead_id: int | None = None) -> dict:
    import json as _json
    price, basis = approved_price(lead_id, unit)
    offer = approved_offer(lead_id, unit)
    concessions = _json.loads(offer["concessions"] or "[]") if offer and offer.get("concessions") else []
    lines = [("Unit price" + (f" ({basis})" if basis != "list price" else ""), price)]
    notes = []
    gst = project.get("gst_pct")
    if gst not in (None, "") and float(gst) == 0:
        notes.append("GST: nil (ready to move)")
    for label, pct in (("GST", gst), ("Stamp duty", project.get("stamp_duty_pct")),
                       ("Registration", project.get("registration_pct"))):
        if pct not in (None, "") and float(pct) > 0:
            lines.append((f"{label} ({float(pct):g}%)", int(round(price * float(pct) / 100))))
    for label, amount in _charges(project):
        if _waived(label, concessions):
            notes.append(f"{label}: included free (approved)")
        else:
            lines.append((label, amount))
    total = sum(v for _, v in lines)
    unit_desc = " ".join(x for x in (unit.get("unit_no") or "", f"({unit['unit_type']}"
                                     + (f", {unit['size_sqft']} sq ft" if unit.get("size_sqft") else "") + ")") if x)
    text = [f"Cost sheet — {project['name']}, {unit_desc}"]
    text += [f"{label}: {fmt_money(v)}" for label, v in lines]
    text += notes
    text.append(f"Approx. total: {fmt_money(total)}")
    missing = [x for x, k in (("GST", "gst_pct"), ("stamp duty", "stamp_duty_pct"), ("registration", "registration_pct"))
               if project.get(k) in (None, "")]
    note = "Indicative only. Final figures as per the sale agreement and government rates on the registration date."
    if missing:
        note += f" {', '.join(missing).capitalize()} not included here; the team will confirm."
    text.append(note)
    return {"price": price, "total": total, "lines": lines, "text": "\n".join(text)}


# ------------------------------------------------------------------ EMI

def emi(principal: float, annual_rate_pct: float, years: float) -> int:
    r = annual_rate_pct / 12 / 100
    n = int(round(years * 12))
    if n <= 0:
        return 0
    if r == 0:
        return int(round(principal / n))
    return int(round(principal * r * (1 + r) ** n / ((1 + r) ** n - 1)))


def emi_illustration(price: int, down_payment_pct: float | None = None, rate_pct: float | None = None,
                     years: float | None = None) -> dict:
    f = get_settings().raw.get("finance") or {}
    dp = float(down_payment_pct if down_payment_pct is not None else f.get("default_down_payment_pct", 20))
    rate = float(rate_pct if rate_pct is not None else f.get("default_rate_pct", 8.5))
    yrs = float(years if years is not None else f.get("default_tenure_years", 20))
    dp = min(max(dp, 10.0), 90.0)   # banks lend at most ~90% for homes
    loan = int(round(price * (1 - dp / 100)))
    rows = []
    for y in sorted({max(5.0, yrs - 5), yrs, min(30.0, yrs + 5)}):
        e = emi(loan, rate, y)
        rows.append((y, e, e * int(y * 12) - loan))
    text = [f"EMI illustration for {fmt_money(price)}",
            f"Down payment {dp:g}%: {fmt_money(price - loan)} · Loan: {fmt_money(loan)} at {rate:g}% p.a."]
    text += [f"{y:g} years: about ₹{e:,.0f}/month (total interest ≈ {fmt_money(i)})" for y, e, i in rows]
    text.append("Illustrative only — the bank decides the actual rate, tenure and eligibility.")
    return {"loan": loan, "rows": rows, "text": "\n".join(text)}
