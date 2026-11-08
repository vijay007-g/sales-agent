"""Personal portal links for salespeople and site team members (no passwords to remember).

Each person gets a long secret link (/s/<token> for sales, /site/<token> for site). It can be sent to them on
WhatsApp, saved to the phone's home screen like an app, and replaced at any time from the Team page.
"""
from __future__ import annotations

from . import channels, db
from .config import get_settings

ROLES = {"sales": "/s", "site": "/site"}


def _norm(phone: str) -> str:
    return db.normalize_phone(phone or "")


def members() -> list[dict]:
    """Everyone who should have a portal: salespeople and site persons from Settings, plus project site hosts."""
    from . import inventory
    s = get_settings()
    out = [{"role": "sales", "name": r["name"], "phone": _norm(r.get("phone"))} for r in s.sales_team if r.get("phone")]
    seen = set()
    for sp in s.site_persons:
        if sp.get("phone") and _norm(sp["phone"]) not in seen:
            seen.add(_norm(sp["phone"]))
            out.append({"role": "site", "name": sp["name"], "phone": _norm(sp["phone"])})
    for phone, h in inventory.all_host_phones().items():
        if phone not in seen:
            seen.add(phone)
            out.append({"role": "site", "name": h["name"], "phone": phone})
    for m in out:
        m.update(ensure(m["role"], m["name"], m["phone"]))
    return out


def ensure(role: str, name: str, phone: str) -> dict:
    row = db.q1("SELECT * FROM team_access WHERE role = ? AND phone = ? AND revoked = 0", (role, _norm(phone)))
    if row:
        if row["name"] != name:
            db.update("team_access", row["id"], {"name": name})
        return {"token": row["token"], "access_id": row["id"]}
    token = db.new_token() + db.new_token()[:8]
    aid = db.insert("team_access", {"role": role, "name": name, "phone": _norm(phone), "token": token,
                                    "created_at": db.now_iso()})
    return {"token": token, "access_id": aid}


def by_token(token: str, role: str) -> dict | None:
    row = db.q1("SELECT * FROM team_access WHERE token = ? AND role = ? AND revoked = 0", (token, role))
    if row:
        db.update("team_access", row["id"], {"last_seen": db.now_iso()})
    return row


def regenerate(access_id: int) -> dict | None:
    row = db.q1("SELECT * FROM team_access WHERE id = ?", (access_id,))
    if not row:
        return None
    db.update("team_access", access_id, {"revoked": 1})
    return ensure(row["role"], row["name"], row["phone"])


def portal_url(role: str, token: str, path: str = "") -> str:
    from .team import base_url
    return f"{base_url()}{ROLES[role]}/{token}{path}"


def link_for(role: str, phone: str, path: str = "") -> str:
    """Portal link for a team member by phone (creates one if needed), for use inside WhatsApp reminders."""
    row = db.q1("SELECT * FROM team_access WHERE role = ? AND phone = ? AND revoked = 0", (role, _norm(phone)))
    if not row:
        name = next((m["name"] for m in members() if m["role"] == role and m["phone"] == _norm(phone)), "Team")
        tok = ensure(role, name, phone)["token"]
    else:
        tok = row["token"]
    return portal_url(role, tok, path)


def send_link(access_id: int) -> bool:
    row = db.q1("SELECT * FROM team_access WHERE id = ? AND revoked = 0", (access_id,))
    if not row:
        return False
    what = "sales portal" if row["role"] == "sales" else "site visit app"
    url = portal_url(row["role"], row["token"])
    text = (f"Hi {row['name']}, here is your {get_settings().business['name']} {what}:\n{url}\n\n"
            "Open it and tap 'Add to Home screen' (Chrome menu ⋮ / iPhone Share) so it opens like an app. "
            "Please keep this link private — it's your personal login.")
    return bool(channels.notify_staff(row["phone"], text).get("ok"))
