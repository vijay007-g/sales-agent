"""15-year growth plan: targets, live progress, stage gates, unit economics and demand intelligence.

The plan (docs/Skyline-15-Year-Plan.pdf) climbs a ladder of four engines: distribution (channel partner, then
exclusive mandates), development with your own capital (from end-2027), investor capital in project companies
(from 2029; the main company stays 100% yours), and the sales platform. This module keeps the plan honest by
measuring, from real data, whether each gate is passed before the next step is taken. Targets can be overridden
in config.yaml under `growth:` (Admin → Settings → Advanced).
"""
from __future__ import annotations

from datetime import timedelta

from . import db, inventory, pricing
from .config import get_settings

CR = 10_000_000  # one crore in rupees

# year, bookings (channel partner), total sales value (₹ Cr), of which own development (₹ Cr),
# investor capital in project companies (₹ Cr), your capital (₹ Cr), profit after tax (₹ Cr), milestone.
# From the 15-year capital model: own capital 24% a year after tax, ~5% on investor capital (fees + profit share).
DEFAULT_PLAN = [
    (1, 90, 80, 0, 0, 8, 1, "Two cities, lean team: 8–10 bookings a month by Q4; own JV project selling; ₹8 Cr capital"),
    (2, 300, 288, 8, 0, 10, 3, "First own-capital site (₹6–8 Cr, or plotted layout + JV); exclusive mandates; Pvt Ltd"),
    (3, 600, 630, 30, 13, 16, 6, "First project-company investors; first plotted layout sold out; 3 micro-markets a city"),
    (4, 960, 1065, 65, 32, 27, 11, "3 own projects running; demand book of 10,000+ buyers"),
    (5, 1370, 1623, 123, 65, 44, 18, "First own-capital project delivered on the RERA schedule (the track record)"),
    (6, 1830, 2317, 217, 117, 72, 28, "Third city; ₹100 Cr+ investor capital; platform licensed to other builders"),
    (7, 2320, 3159, 359, 195, 113, 41, "Four cities; 10 projects running; in-house construction management"),
    (8, 2840, 4153, 553, 299, 173, 60, "₹300 Cr investor capital; landowners approach Skyline first for JVs"),
    (9, 3380, 5325, 825, 442, 259, 86, "Development pipeline of 5M sq ft; a recognised brand in South India"),
    (10, 3870, 6582, 1182, 624, 378, 119, "₹100 Cr+ profit a year; company worth ~₹1,800 Cr"),
    (11, 4370, 8124, 1724, 910, 545, 167, "Five to six cities; first investment-fund partner (via a SEBI-registered AIF)"),
    (12, 4870, 9969, 2469, 1300, 778, 233, "₹1,300 Cr investor capital; ₹10,000 Cr sales a year"),
    (13, 5320, 12074, 3474, 1820, 1100, 322, "Own capital passes ₹1,000 Cr"),
    (14, 5770, 14567, 4767, 2470, 1539, 439, "₹14,500 Cr sales a year across distribution and development"),
    (15, 6170, 17382, 6382, 3250, 2131, 592, "~₹590 Cr profit a year → ~₹8,800 Cr (~$1B) company, 100% owned"),
]


def cfg() -> dict:
    return get_settings().raw.get("growth") or {}


def start_year() -> int:
    return int(cfg().get("start_year") or 2027)


def plan() -> list[dict]:
    rows = cfg().get("targets") or [
        {"year": y, "bookings": b, "sales_cr": s, "own_cr": o, "investor_cr": inv, "capital_cr": cap, "profit_cr": pat,
         "milestone": m} for y, b, s, o, inv, cap, pat, m in DEFAULT_PLAN]
    out = []
    for r in rows:
        y = int(r["year"])
        out.append({"year": y, "calendar": start_year() + y - 1, "bookings": int(r.get("bookings") or 0),
                    "sales_cr": float(r.get("sales_cr") or 0), "own_cr": float(r.get("own_cr") or 0),
                    "investor_cr": float(r.get("investor_cr") or 0), "capital_cr": float(r.get("capital_cr") or 0),
                    "profit_cr": float(r.get("profit_cr") or 0), "milestone": r.get("milestone", "")})
    return out


def current_year_index() -> int:
    return get_settings().now().year - start_year() + 1


# ------------------------------------------------------------------ actuals

def deals(since_iso: str | None = None) -> list[dict]:
    """Every paid booking with its deal value, project and whether it is our own project."""
    rows = db.q("SELECT b.id, b.lead_id, b.paid_at, b.unit_id, o.offered_price, o.owner_counter_price, "
                "o.list_price, o.project_id, u.list_price AS unit_price, u.project_id AS unit_project "
                "FROM bookings b LEFT JOIN offers o ON o.id = b.offer_id LEFT JOIN units u ON u.id = b.unit_id "
                "WHERE b.status = 'paid'" + (" AND b.paid_at >= ?" if since_iso else ""),
                (since_iso,) if since_iso else ())
    out = []
    for r in rows:
        value = r["owner_counter_price"] or r["offered_price"] or r["unit_price"] or r["list_price"] or 0
        project = inventory.get_project(r["project_id"] or r["unit_project"]) if (r["project_id"] or r["unit_project"]) else None
        out.append({"id": r["id"], "lead_id": r["lead_id"], "paid_at": r["paid_at"] or "", "value": value,
                    "own": bool(project and project["is_own"]),
                    "project": project["name"] if project else "", "city": project["city"] if project else ""})
    return out


def _test_lead_ids() -> set[int]:
    return {r["id"] for r in db.q("SELECT id FROM leads WHERE campaign = 'test'")}


def progress() -> dict:
    """This plan year so far, against its target, with a pace projection."""
    now = get_settings().now()
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    test = _test_lead_ids()
    ds = [d for d in deals(year_start.isoformat()) if d["lead_id"] not in test]
    idx = current_year_index()
    target = next((p for p in plan() if p["year"] == max(idx, 1)), None)
    elapsed = max((now - year_start).days + 1, 1) / 365
    bookings = len(ds)
    sales = sum(d["value"] for d in ds)
    comm = db.q1("SELECT COALESCE(SUM(amount),0) n FROM commissions WHERE created_at >= ?",
                 (year_start.isoformat(),))["n"]
    return {"year_index": idx, "calendar": now.year, "target": target, "bookings": bookings, "sales": sales,
            "own_sales": sum(d["value"] for d in ds if d["own"]), "commission": comm,
            "pace_bookings": round(bookings / elapsed) if idx >= 1 else bookings,
            "pace_sales": sales / elapsed if idx >= 1 else sales, "elapsed_pct": round(elapsed * 100)}


def monthly(months: int = 12) -> list[dict]:
    now = get_settings().now()
    keys = []
    y, m = now.year, now.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    test = _test_lead_ids()
    by = {k: {"month": k, "bookings": 0, "sales": 0, "leads": 0} for k in keys}
    for d in deals():
        k = d["paid_at"][:7]
        if k in by and d["lead_id"] not in test:
            by[k]["bookings"] += 1
            by[k]["sales"] += d["value"]
    for r in db.q("SELECT substr(created_at,1,7) k, COUNT(*) n FROM leads WHERE campaign IS NOT 'test' GROUP BY k"):
        if r["k"] in by:
            by[r["k"]]["leads"] = r["n"]
    return [by[k] for k in reversed(keys)]


# ------------------------------------------------------------------ unit economics

def ai_cost_inr(since_iso: str) -> float:
    from . import models
    rate = float(cfg().get("usd_inr") or 88)
    total = 0.0
    for r in db.q("SELECT COALESCE(NULLIF(model,''),'claude-opus-5-5') m, SUM(input_tokens) i, SUM(output_tokens) o, "
                  "SUM(cache_read) cr, SUM(cache_write) cw FROM usage WHERE created_at >= ? GROUP BY m", (since_iso,)):
        total += models.cost_usd(r["m"], r["i"] or 0, r["o"] or 0, r["cr"] or 0, r["cw"] or 0)
    return total * rate


def unit_economics(days: int = 365) -> dict:
    """What one booking costs us (ads + AI + salesperson incentive) against what it earns."""
    now = get_settings().now()
    since = now - timedelta(days=days)
    test = _test_lead_ids()
    ds = [d for d in deals(since.isoformat()) if d["lead_id"] not in test]
    spend = db.q1("SELECT COALESCE(SUM(amount),0) n FROM ad_spend WHERE month >= ?", (since.strftime("%Y-%m"),))["n"]
    ai = ai_cost_inr(since.isoformat())
    commission = db.q1("SELECT COALESCE(SUM(amount),0) n FROM commissions WHERE created_at >= ?",
                       (since.isoformat(),))["n"]
    own_margin_pct = float(cfg().get("own_margin_pct") or 0)
    own_earn = sum(d["value"] for d in ds if d["own"]) * own_margin_pct / 100
    earnings = commission + own_earn
    n = len(ds)
    cost = spend + ai
    cpb = cost / n if n else None
    epb = earnings / n if n else None
    return {"days": days, "bookings": n, "ad_spend": spend, "ai_cost": ai, "cost": cost, "earnings": earnings,
            "cost_per_booking": cpb, "earnings_per_booking": epb,
            "cost_share": (cpb / epb) if cpb is not None and epb else None,
            "avg_deal": (sum(d["value"] for d in ds) / n) if n else None}


def funnel(days: int = 180) -> dict:
    from .marketing import QUALIFIED_PLUS, VISITED_PLUS, _reached
    since = (get_settings().now() - timedelta(days=days)).isoformat()
    ids = [r["id"] for r in db.q("SELECT id FROM leads WHERE created_at >= ? AND campaign IS NOT 'test'", (since,))]
    reached = _reached(ids)
    q = sum(1 for i in ids if reached[i] & QUALIFIED_PLUS)
    v = sum(1 for i in ids if reached[i] & VISITED_PLUS)
    b = sum(1 for i in ids if "booked" in reached[i])
    ref = db.q1("SELECT COUNT(*) n FROM leads WHERE created_at >= ? AND source = 'referral' AND campaign IS NOT 'test'",
                (since,))["n"]
    pct = lambda a, z: round(100 * a / z, 1) if z else None  # noqa: E731
    return {"days": days, "leads": len(ids), "qualified": q, "visited": v, "booked": b,
            "lead_to_visit": pct(v, len(ids)), "visit_to_booking": pct(b, v), "lead_to_booking": pct(b, len(ids)),
            "referral_share": pct(ref, len(ids))}


def collection() -> dict:
    """Share of commission collected within 60 days of being earned (cash discipline)."""
    cutoff = (get_settings().now() - timedelta(days=60)).isoformat()
    rows = db.q("SELECT amount, collected_amount, collected_at, created_at FROM commissions WHERE created_at <= ?",
                (cutoff,))
    due = sum(r["amount"] or 0 for r in rows)
    got = 0
    for r in rows:
        if r["collected_at"] and db.parse_dt(r["collected_at"]) - db.parse_dt(r["created_at"]) <= timedelta(days=60):
            got += r["collected_amount"] or r["amount"] or 0
    return {"due": due, "collected": got, "pct": round(100 * got / due) if due else None}


def concentration() -> list[dict]:
    """Commission by builder: depending on one builder for most income is a risk to fix early."""
    rows = db.q("SELECT b.name, SUM(c.amount) amt FROM commissions c JOIN builders b ON b.id = c.builder_id "
                "GROUP BY b.name ORDER BY amt DESC")
    total = sum(r["amt"] or 0 for r in rows)
    return [{"builder": r["name"], "amount": r["amt"] or 0, "share": round(100 * (r["amt"] or 0) / total)}
            for r in rows] if total else []


# ------------------------------------------------------------------ stage gates

def gate1() -> list[dict]:
    """Gate 1 — the engine works. Every item must hold before spending on expansion."""
    ms = monthly(3)
    ue = unit_economics()
    fn = funnel()
    col = collection()
    conc = concentration()

    def item(ok, text, now_text):
        return {"ok": bool(ok), "text": text, "now": now_text}

    return [
        item(all(m["bookings"] >= 8 for m in ms), "8+ bookings every month for 3 months in a row",
             ", ".join(f"{m['month']}: {m['bookings']}" for m in ms)),
        item(ue["cost_share"] is not None and ue["cost_share"] <= 0.30,
             "Ads + AI cost per booking is at most 30% of what a booking earns",
             f"{round(ue['cost_share'] * 100)}%" if ue["cost_share"] is not None else "not enough bookings yet"),
        item(fn["lead_to_booking"] is not None and fn["lead_to_booking"] >= 1.0,
             "At least 1 in 100 leads books (last 6 months)",
             f"{fn['lead_to_booking']}%" if fn["lead_to_booking"] is not None else "no leads yet"),
        item(fn["visit_to_booking"] is not None and fn["visit_to_booking"] >= 15,
             "At least 15 in 100 site visits book",
             f"{fn['visit_to_booking']}%" if fn["visit_to_booking"] is not None else "no visits yet"),
        item(col["pct"] is not None and col["pct"] >= 80, "80%+ of commission collected within 60 days",
             f"{col['pct']}%" if col["pct"] is not None else "nothing due yet"),
        item(conc and conc[0]["share"] <= 40, "No single builder is more than 40% of commission",
             f"{conc[0]['builder']} {conc[0]['share']}%" if conc else "no commission yet"),
    ]


# ------------------------------------------------------------------ demand intelligence

BANDS = [(0, 5_000_000, "under ₹50 L"), (5_000_000, 8_000_000, "₹50–80 L"), (8_000_000, 12_000_000, "₹80 L–1.2 Cr"),
         (12_000_000, 20_000_000, "₹1.2–2 Cr"), (20_000_000, 10**12, "₹2 Cr+")]


def band(budget: int | None) -> tuple[str, int | None]:
    if not budget:
        return "budget unknown", None
    for lo, hi, label in BANDS:
        if lo <= budget < hi:
            return label, hi
    return BANDS[-1][2], None


def demand(days: int = 180, limit: int = 25) -> list[dict]:
    """What buyers asked for (city × area × budget × home type) against what we can offer today.
    A high-demand, low-supply row is a mandate to pitch to builders — and, later, land worth developing."""
    since = (get_settings().now() - timedelta(days=days)).isoformat()
    groups: dict[tuple, dict] = {}
    for r in db.q("SELECT id, city, location_pref, budget_max, unit_type, stage FROM leads WHERE created_at >= ? "
                  "AND campaign IS NOT 'test'", (since,)):
        label, hi = band(r["budget_max"])
        area = (r["location_pref"] or "").strip().split(",")[0].strip()
        area = area if any(ch.isupper() for ch in area) else area.title()
        key = ((r["city"] or "").title(), area, label, (r["unit_type"] or "").upper().replace(" ", ""))
        g = groups.setdefault(key, {"city": key[0], "area": key[1], "budget": key[2], "unit_type": key[3],
                                    "budget_max": r["budget_max"], "leads": 0, "booked": 0, "lost": 0})
        g["leads"] += 1
        g["booked"] += r["stage"] == "booked"
        g["lost"] += r["stage"] == "lost"
        g["budget_max"] = max(g["budget_max"] or 0, r["budget_max"] or 0) or None
    out = []
    for g in groups.values():
        matches = inventory.search(city=g["city"], budget_max=g["budget_max"], unit_type=g["unit_type"],
                                   locality=g["area"], limit=50)
        g["supply"] = sum(m["units_like_this"] or 1 for m in matches if not g["area"] or
                          g["area"].lower() in f"{m['locality']} {m['project']}".lower())
        g["gap"] = g["leads"] - g["supply"]
        out.append(g)
    out.sort(key=lambda g: (-g["gap"], -g["leads"]))
    return out[:limit]


# ------------------------------------------------------------------ digest

def digest_line() -> str:
    p = progress()
    t = p["target"]
    if not t:
        return ""
    if p["year_index"] < 1:
        return f"15-year plan starts in {start_year()}: year-1 target {t['bookings']} bookings."
    return (f"Plan year {p['year_index']}: {p['bookings']}/{t['bookings']} bookings, "
            f"{pricing.fmt_money(p['sales'])} of ₹{t['sales_cr']:,.0f} Cr sales "
            f"(on pace for {p['pace_bookings']}).")
