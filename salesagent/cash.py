"""Cash plan: big payment commitments (land, construction) against the money expected to cover them.

Commitments are payments you must make (e.g. ₹2.5 Cr to the landowner by 31 Dec). Sources are money you expect
(cash in bank, a loan disbursement, sales advances, a receivable) with a confidence level. For every open commitment
the plan shows the running balance up to its due date three ways: confirmed money only; plus likely; plus possible.
A negative balance is a gap that needs action now, not on the due date. You get WhatsApp reminders 30, 14, 7, 3 and
1 days before each commitment, and the morning digest carries the next one.
"""
from __future__ import annotations

import json
from datetime import date

from . import channels, db, pricing
from .config import get_settings

LEVELS = ("confirmed", "likely", "possible")
REMIND_DAYS = (30, 14, 7, 3, 1)


def items(kind: str | None = None, include_closed: bool = True) -> list[dict]:
    sql = "SELECT * FROM cash_items WHERE 1=1"
    args: list = []
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    if not include_closed:
        sql += " AND status = 'open'"
    return db.q(sql + " ORDER BY due_date, id", tuple(args))


def add(kind: str, title: str, amount: int, due_date: str, party: str = "", project: str = "",
        confidence: str = "confirmed", notes: str = "") -> int:
    if kind not in ("commitment", "source"):
        raise ValueError("kind must be commitment or source")
    date.fromisoformat(due_date)
    return db.insert("cash_items", {"kind": kind, "title": title.strip(), "party": party.strip(),
                                    "project": project.strip(), "amount": int(amount), "due_date": due_date,
                                    "confidence": confidence if confidence in LEVELS else "possible",
                                    "status": "open", "notes": notes.strip(), "created_at": db.now_iso()})


def mark(item_id: int, status: str) -> None:
    if status not in ("open", "done", "dropped"):
        raise ValueError(status)
    db.update("cash_items", item_id, {"status": status, "done_at": db.now_iso() if status != "open" else None})


def balance(upto: str, level: str) -> int:
    """Money in minus money out up to a date. Done items always count; open sources count up to `level`."""
    allowed = LEVELS[:LEVELS.index(level) + 1]
    total = 0
    for it in db.q("SELECT * FROM cash_items WHERE status != 'dropped' AND due_date <= ?", (upto,)):
        if it["kind"] == "commitment":
            total -= it["amount"]
        elif it["status"] == "done" or it["confidence"] in allowed:
            total += it["amount"]
    # money already received or paid counts whatever its planned date
    for it in db.q("SELECT * FROM cash_items WHERE status = 'done' AND due_date > ?", (upto,)):
        total += it["amount"] if it["kind"] == "source" else -it["amount"]
    return total


def coverage() -> list[dict]:
    out = []
    for c in items("commitment", include_closed=False):
        row = {**c, "days_left": (date.fromisoformat(c["due_date"]) - get_settings().now().date()).days}
        for lvl in LEVELS:
            row[lvl] = balance(c["due_date"], lvl)
        row["state"] = ("covered" if row["confirmed"] >= 0 else "likely" if row["likely"] >= 0
                        else "possible" if row["possible"] >= 0 else "gap")
        out.append(row)
    return out


def _line(r: dict) -> str:
    m = pricing.fmt_money
    if r["state"] == "covered":
        tail = "✅ covered by confirmed money"
    elif r["state"] == "likely":
        tail = f"⚠️ confirmed money short by {m(-r['confirmed'])}; covered only if 'likely' money arrives"
    elif r["state"] == "possible":
        tail = f"🟠 short by {m(-r['likely'])} even with 'likely' money; depends on 'possible' sources"
    else:
        tail = f"🔴 GAP of {m(-r['possible'])} even if every expected source comes in"
    return (f"{r['title']} — {m(r['amount'])}{' to ' + r['party'] if r['party'] else ''} on "
            f"{date.fromisoformat(r['due_date']):%d %b} ({r['days_left']} days): {tail}")


def digest_line() -> str:
    cov = coverage()
    return f"💰 Next payment: {_line(cov[0])}" if cov else ""


def reminders() -> int:
    """WhatsApp to the owner 30/14/7/3/1 days before each open commitment (once per milestone)."""
    s = get_settings()
    n = 0
    for r in coverage():
        sent = set(json.loads(r["reminders"] or "[]"))
        due = [d for d in REMIND_DAYS if r["days_left"] <= d and str(d) not in sent]
        if not due or r["days_left"] < 0:
            continue
        msg = f"💰 Payment reminder: {_line(r)}"
        if r["state"] != "covered":
            from .team import base_url
            msg += f"\nAct now: confirm a source, renegotiate the date, or line up a backup. Cash plan: {base_url()}/cash"
        channels.notify_staff(s.owner["phone"], msg)
        db.update("cash_items", r["id"], {"reminders": json.dumps(sorted(sent | {str(d) for d in due}))})
        n += 1
    return n
