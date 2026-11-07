"""Property inventory: builders (own + partners), projects in any city, and units.

Units can be listed one by one (A-504, 5th floor, east) or as a stock count per type ("2BHK x 12") for builders
who only share counts — `quantity` handles both. Floor prices live here and are never shown to the AI.
"""
from __future__ import annotations

import csv
import re

from . import db
from .config import get_settings

LIVE = ("available", "held")


# ------------------------------------------------------------------ helpers

def _lines(text: str | None) -> list[str]:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


def project_dict(row: dict | None) -> dict | None:
    if not row:
        return None
    p = dict(row)
    for k in ("highlights", "payment_plans", "approval_concessions", "free_concessions"):
        p[k] = _lines(p.get(k))
    b = db.q1("SELECT * FROM builders WHERE id = ?", (p["builder_id"],)) or {}
    p["builder"] = b.get("name", "")
    p["is_own"] = bool(b.get("is_own"))
    return p


def get_project(ref) -> dict | None:
    if ref is None or ref == "":
        return None
    if isinstance(ref, int) or str(ref).isdigit():
        return project_dict(db.q1("SELECT * FROM inv_projects WHERE id = ?", (int(ref),)))
    name = str(ref).strip().lower()
    row = db.q1("SELECT * FROM inv_projects WHERE lower(name) = ?", (name,))
    if not row:  # tolerate "Sunrise Meadows, OMR" or partial names
        rows = db.q("SELECT * FROM inv_projects WHERE active = 1")
        row = next((r for r in rows if r["name"].lower() in name or name in r["name"].lower()), None)
    return project_dict(row)


def list_projects(active_only: bool = True, city: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM inv_projects WHERE 1=1", []
    if active_only:
        sql += " AND active = 1"
    if city:
        sql += " AND lower(city) = lower(?)"
        args.append(city)
    return [project_dict(r) for r in db.q(sql + " ORDER BY city, name", tuple(args))]


def project_names() -> list[str]:
    return [p["name"] for p in list_projects(active_only=False)]


def cities() -> list[str]:
    return [r["city"] for r in db.q("SELECT DISTINCT city FROM inv_projects WHERE active = 1 AND city != '' "
                                    "ORDER BY city")]


def units_for(project_id: int, live_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM units WHERE project_id = ?"
    if live_only:
        sql += " AND status IN ('available','held') AND quantity > 0"
    return db.q(sql + " ORDER BY unit_type, list_price, unit_no", (project_id,))


def available_count(u: dict) -> int:
    return int(u["quantity"] or 0) if u["status"] == "available" else 0


def type_summary(project_id: int) -> list[dict]:
    out: dict[str, dict] = {}
    for u in units_for(project_id):
        t = out.setdefault(u["unit_type"], {"type": u["unit_type"], "available": 0, "prices": [], "sizes": []})
        t["available"] += available_count(u)
        if available_count(u):
            t["prices"].append(u["list_price"])
            if u["size_sqft"]:
                t["sizes"].append(u["size_sqft"])
    for t in out.values():
        t["price_min"] = min(t["prices"]) if t["prices"] else None
        t["price_max"] = max(t["prices"]) if t["prices"] else None
        t["size_min"] = min(t["sizes"]) if t["sizes"] else None
        t["size_max"] = max(t["sizes"]) if t["sizes"] else None
    return list(out.values())


def all_list_prices() -> list[int]:
    return [r["list_price"] for r in db.q(
        "SELECT u.list_price FROM units u JOIN inv_projects p ON p.id = u.project_id "
        "WHERE p.active = 1 AND u.status = 'available' AND u.quantity > 0 AND u.list_price > 0")]


def builder_for(project: dict) -> dict:
    return db.q1("SELECT * FROM builders WHERE id = ?", (project["builder_id"],)) or {}


def is_partner(project: dict) -> bool:
    return not builder_for(project).get("is_own", 1)


def commission_for(project: dict, deal_value: int) -> int:
    b = builder_for(project)
    ctype = project.get("commission_type") or b.get("commission_type") or "pct"
    cval = project.get("commission_value") if project.get("commission_value") not in (None, "") else b.get(
        "commission_value", 0)
    cval = float(cval or 0)
    return int(round(deal_value * cval / 100)) if ctype == "pct" else int(cval)


# ------------------------------------------------------------------ units: find, hold, book

def find_unit(project: dict, unit_type: str, unit_no: str = "", lead_id: int | None = None) -> dict | None:
    """A specific unit by number, else the cheapest live unit of that type."""
    units = units_for(project["id"], live_only=True)
    if unit_no:
        u = next((x for x in units if (x["unit_no"] or "").lower() == unit_no.strip().lower()), None)
        if u:
            return u
    t = (unit_type or "").replace(" ", "").lower()
    of_type = [x for x in units if x["unit_type"].replace(" ", "").lower() == t]
    if lead_id:
        held = [x for x in of_type if x["status"] == "held" and f"lead:{lead_id}" in (x["notes"] or "")]
        if held:
            return held[0]
    avail = [x for x in of_type if x["status"] == "available"]
    return min(avail, key=lambda x: x["list_price"] or 0) if avail else None


def hold_unit(unit_id: int, lead_id: int) -> None:
    """Reserve a unit while the advance is being paid (unit-level rows only)."""
    u = db.q1("SELECT * FROM units WHERE id = ?", (unit_id,))
    if u and (u["quantity"] or 1) == 1 and u["status"] == "available":
        db.update("units", unit_id, {"status": "held", "notes": f"lead:{lead_id} " + (u["notes"] or ""),
                                     "updated_at": db.now_iso()})


def release_unit(unit_id: int) -> None:
    u = db.q1("SELECT * FROM units WHERE id = ?", (unit_id,))
    if u and u["status"] == "held":
        db.update("units", unit_id, {"status": "available",
                                     "notes": re.sub(r"lead:\d+ ?", "", u["notes"] or ""), "updated_at": db.now_iso()})


def mark_booked(unit_id: int) -> None:
    u = db.q1("SELECT * FROM units WHERE id = ?", (unit_id,))
    if not u:
        return
    if (u["quantity"] or 1) > 1:
        db.update("units", unit_id, {"quantity": u["quantity"] - 1, "updated_at": db.now_iso()})
    else:
        db.update("units", unit_id, {"status": "booked", "quantity": 0 if u["quantity"] is not None else 0,
                                     "updated_at": db.now_iso()})


# ------------------------------------------------------------------ matchmaker

def _possession_ok(project: dict, want: str) -> bool:
    if not want or want == "any":
        return True
    status = f"{project.get('status') or ''} {project.get('possession') or ''}".lower()
    ready = any(w in status for w in ("ready", "completed", "oc received", "immediate"))
    if want == "ready":
        return ready
    if want == "within_1y":
        if ready:
            return True
        years = [int(y) for y in re.findall(r"20\d\d", status)]
        return bool(years) and min(years) <= get_settings().now().year + 1
    return True


def search(city: str = "", budget_max: int | None = None, budget_min: int | None = None, unit_type: str = "",
           locality: str = "", possession: str = "any", limit: int = 8) -> list[dict]:
    """Rank live units for a buyer. Returns at most 3 units per project, best first. No floor prices."""
    t = (unit_type or "").replace(" ", "").lower()
    results = []
    for p in list_projects(city=city or None):
        if not _possession_ok(p, possession):
            continue
        for u in units_for(p["id"], live_only=True):
            if u["status"] != "available":
                continue
            price = u["list_price"] or 0
            if budget_max and price > budget_max * 1.10:   # allow 10% stretch, flagged below
                continue
            if t and u["unit_type"].replace(" ", "").lower() != t:
                continue
            score = 0.0
            reasons = []
            if budget_max:
                if price <= budget_max:
                    score += 50 - 30 * (budget_max - price) / budget_max   # closer to budget = better use of it
                    reasons.append("within budget")
                else:
                    score += 10
                    reasons.append(f"{round((price / budget_max - 1) * 100)}% above budget")
            if budget_min and price < budget_min * 0.8:
                score -= 15
            if locality and locality.lower() in f"{p['locality']} {p['name']}".lower():
                score += 25
                reasons.append("preferred locality")
            if _possession_ok(p, "ready"):
                score += 5
            results.append({"score": round(score, 1), "project": p["name"], "builder": p["builder"],
                            "own_project": p["is_own"], "city": p["city"], "locality": p["locality"],
                            "unit_type": u["unit_type"], "unit_no": u["unit_no"] or "", "floor": u["floor"] or "",
                            "facing": u["facing"] or "", "size_sqft": u["size_sqft"], "carpet_sqft": u["carpet_sqft"],
                            "list_price": price, "units_like_this": available_count(u),
                            "possession": p["possession"] or p["status"] or "", "rera": p["rera"] or "",
                            "highlights": p["highlights"][:3], "why": ", ".join(reasons)})
    results.sort(key=lambda r: -r["score"])
    per_project: dict[str, int] = {}
    out = []
    for r in results:
        if per_project.get(r["project"], 0) >= 3:
            continue
        per_project[r["project"]] = per_project.get(r["project"], 0) + 1
        out.append(r)
        if len(out) >= limit:
            break
    return out


def project_facts(project: dict, max_units: int = 30) -> dict:
    """Everything the AI may tell a customer about a project (no floor prices, no commission)."""
    units = []
    for u in units_for(project["id"], live_only=True):
        if u["status"] != "available":
            continue
        units.append({k: u[k] for k in ("unit_no", "unit_type", "floor", "facing", "size_sqft", "carpet_sqft",
                                        "list_price") if u[k] not in (None, "")}
                     | ({"units_like_this": u["quantity"]} if (u["quantity"] or 1) > 1 else {}))
    return {"project": project["name"], "builder": project["builder"], "own_project": project["is_own"],
            "city": project["city"], "locality": project["locality"], "type": project["type"],
            "status": project["status"], "possession": project["possession"], "rera": project["rera"],
            "highlights": project["highlights"], "payment_plans": project["payment_plans"],
            "extras_you_may_mention_freely": project["free_concessions"],
            "extras_needing_management_approval": project["approval_concessions"],
            "unit_types": [{k: v for k, v in t.items() if k not in ("prices", "sizes")}
                           for t in type_summary(project["id"])],
            "available_units": units[:max_units], "more_units": max(0, len(units) - max_units)}


def catalog_text() -> str:
    """Short summary of all live projects for the system prompt; details come from the tools."""
    from .pricing import fmt_money
    lines = []
    for p in list_projects():
        types = []
        for t in type_summary(p["id"]):
            if t["available"]:
                rng = fmt_money(t["price_min"]) + ("" if t["price_min"] == t["price_max"]
                                                  else f"–{fmt_money(t['price_max'])}")
                types.append(f"{t['type']} {rng} ({t['available']} left)")
        if types:
            lines.append(f"- {p['name']} ({p['city']}, {p['locality']}; {'own project' if p['is_own'] else 'partner: ' + p['builder']}; "
                         f"{p['possession'] or p['status'] or ''}): " + "; ".join(types))
    return "\n".join(lines) or "(No inventory loaded yet.)"


# ------------------------------------------------------------------ visit hosts

def hosts_for(project_name: str) -> list[dict]:
    """Who can receive a site visit: the project's own site host (e.g. a partner builder's staff) plus any
    site persons in Settings who cover this project."""
    s = get_settings()
    out = []
    p = get_project(project_name)
    if p and p.get("site_host_phone"):
        a, b = (p.get("visit_hours") or "10:00-18:00").split("-")[:2]
        out.append({"name": p.get("site_host_name") or f"{p['name']} site team", "phone": p["site_host_phone"],
                    "working_days": [int(x) for x in (p.get("visit_days") or "0,1,2,3,4,5,6").split(",") if x.strip()],
                    "visit_hours": [a.strip(), b.strip()], "max_visits_per_day": p.get("max_visits_per_day") or 6})
    name = p["name"] if p else project_name
    out += [sp for sp in s.site_persons if not sp.get("projects") or name in sp["projects"]]
    seen, uniq = set(), []
    for h in out:
        key = db.normalize_phone(h["phone"])
        if key not in seen:
            seen.add(key)
            uniq.append(h)
    return uniq


def all_host_phones() -> dict[str, dict]:
    hosts = {}
    for p in list_projects(active_only=False):
        if p.get("site_host_phone"):
            hosts[db.normalize_phone(p["site_host_phone"])] = {"name": p.get("site_host_name") or "Site team",
                                                               "projects": [p["name"]]}
    return hosts


# ------------------------------------------------------------------ setup, import

def own_builder_id() -> int:
    row = db.q1("SELECT id FROM builders WHERE is_own = 1 ORDER BY id LIMIT 1")
    if row:
        return row["id"]
    return db.insert("builders", {"name": get_settings().business.get("name", "Own projects"), "is_own": 1,
                                  "commission_type": "pct", "commission_value": 0, "created_at": db.now_iso()})


def seed_from_config() -> int:
    """First run: copy projects from Settings into the inventory (type-level stock). Returns projects added."""
    if db.q1("SELECT id FROM inv_projects LIMIT 1"):
        return 0
    bid = own_builder_id()
    n = 0
    for p in get_settings().raw.get("projects") or []:
        loc = p.get("location", "")
        city = loc.split(",")[-1].strip() if "," in loc else ""
        pid = db.insert("inv_projects", {
            "builder_id": bid, "name": p["name"], "city": city, "locality": loc.split(",")[0].strip(),
            "type": p.get("type", ""), "status": p.get("status", ""), "possession": p.get("status", ""),
            "rera": p.get("rera", ""), "highlights": "\n".join(p.get("highlights") or []),
            "payment_plans": "\n".join(p.get("payment_plans") or []),
            "approval_concessions": "\n".join(p.get("approval_concessions") or []),
            "free_concessions": "\n".join(p.get("free_concessions") or []),
            "active": 1, "created_at": db.now_iso(), "updated_at": db.now_iso()})
        for u in p.get("units") or []:
            db.insert("units", {"project_id": pid, "unit_no": "", "unit_type": u["type"],
                                "size_sqft": u.get("size_sqft"), "carpet_sqft": u.get("carpet_sqft"),
                                "list_price": u.get("list_price"), "floor_price": u.get("floor_price"),
                                "quantity": int(u.get("available", 1) or 0),
                                "status": "available" if int(u.get("available", 1) or 0) > 0 else "sold",
                                "updated_at": db.now_iso()})
        n += 1
    if n:
        db.audit(None, "system", "inventory_seeded", f"{n} projects from settings")
    return n


CSV_COLUMNS = ["unit_no", "unit_type", "floor", "facing", "size_sqft", "carpet_sqft", "list_price", "floor_price",
               "quantity", "status"]


def import_units_csv(project_id: int, path: str, replace: bool = False) -> dict:
    """Columns (any order, header row required): unit_no, unit_type, floor, facing, size_sqft, carpet_sqft,
    list_price, floor_price, quantity, status. Prices accept 7500000 / 75L / 1.02cr."""
    from .events import parse_amount
    aliases = {"unit_no": ["unit_no", "unit no", "unit", "flat", "flat_no", "flat no", "unit number", "flat number",
                           "door no"],
               "unit_type": ["unit_type", "type", "bhk", "configuration"],
               "floor": ["floor"], "facing": ["facing", "direction"],
               "size_sqft": ["size_sqft", "size", "sba", "saleable area", "super built-up", "area"],
               "carpet_sqft": ["carpet_sqft", "carpet", "carpet area"],
               "list_price": ["list_price", "price", "total price", "agreement value"],
               "floor_price": ["floor_price", "floor price", "minimum price", "min price", "lowest price"],
               "quantity": ["quantity", "qty", "count", "units"], "status": ["status", "availability"]}
    added = updated = 0
    errors: list[str] = []
    if replace:
        db.q("DELETE FROM units WHERE project_id = ? AND status = 'available'", (project_id,))
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            rec = {}
            for field, names in aliases.items():
                for n in names:
                    if low.get(n) not in (None, ""):
                        rec[field] = low[n]
                        break
            if field_missing := [k for k in ("unit_type", "list_price", "floor_price") if not rec.get(k)]:
                errors.append(f"Row {i}: missing {', '.join(field_missing)}")
                continue
            lp, fp = parse_amount(rec["list_price"]), parse_amount(rec["floor_price"])
            if not lp or not fp:
                errors.append(f"Row {i}: couldn't read the price")
                continue
            if fp > lp:
                errors.append(f"Row {i}: floor price above list price")
                continue
            status = (rec.get("status") or "available").lower()
            status = status if status in ("available", "held", "booked", "sold", "blocked") else "available"
            data = {"project_id": project_id, "unit_no": rec.get("unit_no", ""), "unit_type": rec["unit_type"].upper()
                    .replace(" BHK", "BHK"), "floor": rec.get("floor", ""), "facing": rec.get("facing", "").title(),
                    "size_sqft": _int(rec.get("size_sqft")), "carpet_sqft": _int(rec.get("carpet_sqft")),
                    "list_price": lp, "floor_price": fp, "quantity": _int(rec.get("quantity")) or 1,
                    "status": status, "updated_at": db.now_iso()}
            existing = db.q1("SELECT id FROM units WHERE project_id = ? AND unit_no = ? AND unit_no != ''",
                             (project_id, data["unit_no"])) if data["unit_no"] else None
            if existing:
                db.update("units", existing["id"], data)
                updated += 1
            else:
                db.insert("units", data)
                added += 1
    db.audit(None, "owner", "units_imported", {"project_id": project_id, "added": added, "updated": updated})
    return {"added": added, "updated": updated, "errors": errors}


def _int(v) -> int | None:
    try:
        return int(float(str(v).replace(",", ""))) if v not in (None, "") else None
    except ValueError:
        return None
