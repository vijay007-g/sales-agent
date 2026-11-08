"""Operational health: go-live checklist, AI failure alerts, scheduler heartbeat, backups, data erasure."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import zipfile
from datetime import timedelta
from io import BytesIO

from . import channels, db
from .config import DATA_DIR, config_path, env, get_settings, storage_status

_heartbeat = {"at": 0.0}
SAMPLE_PHONE = re.compile(r"^\+?9198000000\d\d$|^\+?914400000\d{3}$")


# ------------------------------------------------------------------ scheduler heartbeat

def beat() -> None:
    _heartbeat["at"] = time.time()


def scheduler_status() -> dict:
    if env("DISABLE_SCHEDULER") == "1":
        return {"running": None, "seconds_since": None}
    if not _heartbeat["at"]:
        return {"running": False, "seconds_since": None}
    ago = time.time() - _heartbeat["at"]
    return {"running": ago < 600, "seconds_since": int(ago)}


# ------------------------------------------------------------------ AI failure alerts

def ai_failed(lead_id: int, status: int | None, message: str) -> None:
    """Record an AI call failure and alert the owner (at most once an hour)."""
    db.audit(lead_id, "system", "ai_error", json.dumps({"status": status, "message": (message or "")[:300]}))
    recent = db.q1("SELECT created_at FROM audit WHERE action = 'ai_error_alert' ORDER BY id DESC LIMIT 1")
    if recent and get_settings().now() - db.parse_dt(recent["created_at"]) < timedelta(hours=1):
        return
    low = (message or "").lower()
    if "credit" in low or "billing" in low or "balance" in low:
        why = "Claude credits have run out. Add funds (or turn on auto-reload) at console.anthropic.com"
    elif status in (401, 403):
        why = "the Claude API key is invalid or was removed. Check ANTHROPIC_API_KEY in Railway"
    elif status == 429:
        why = "Claude usage limits were reached. It retries automatically; raise limits in the Claude Console if this repeats"
    else:
        why = f"Claude returned an error ({status}). It will retry in 15 minutes"
    channels.notify_staff(get_settings().owner["phone"],
                          f"⚠️ The AI could not reply to a buyer: {why}. Buyers are waiting — replies resume "
                          "automatically once fixed.")
    db.audit(None, "system", "ai_error_alert", why)


def recent_ai_errors(hours: int = 24) -> int:
    since = (get_settings().now() - timedelta(hours=hours)).isoformat()
    return db.q1("SELECT COUNT(*) n FROM audit WHERE action = 'ai_error' AND created_at >= ?", (since,))["n"]


# ------------------------------------------------------------------ go-live checklist

def checklist() -> list[dict]:
    """Things to fix before (and while) running with real buyers. level: 'block' | 'warn' | 'ok'."""
    from . import inventory, lead_sources
    s = get_settings()
    items: list[dict] = []

    def add(ok: bool, text: str, fix: str, link: str, level: str = "block"):
        items.append({"ok": ok, "text": text, "fix": fix, "link": link, "level": "ok" if ok else level})

    st = storage_status()
    add(st["persistent"], "Data is saved on a permanent disk", "Attach a Railway volume to the service", "/health")
    sch = scheduler_status()
    add(sch["running"] is not False, "Background clock is running (follow-ups, reminders, mailbox)",
        "The app may need a restart in Railway", "/health")
    add(bool(env("ANTHROPIC_API_KEY")), "Claude API key is set", "Add ANTHROPIC_API_KEY in Railway", "/settings")
    errs = recent_ai_errors()
    add(errs == 0, "AI replied without errors in the last 24 hours",
        f"{errs} failed AI replies — check Claude credits / key", "/reports", "warn")
    owner = s.owner.get("phone", "")
    add(bool(owner) and not SAMPLE_PHONE.match(owner), "Your WhatsApp number is real", "Settings → You (management)",
        "/settings")
    add("example.com" not in (s.owner.get("email") or "example.com"), "Your email is set", "Settings → You", "/settings",
        "warn")
    fake_team = [r["name"] for r in s.sales_team if SAMPLE_PHONE.match(r.get("phone") or "")] + \
                [r["name"] for r in s.site_persons if SAMPLE_PHONE.match(r.get("phone") or "")]
    add(not fake_team and bool(s.sales_team), "Sales and site team have real numbers",
        f"Sample numbers for: {', '.join(fake_team) or 'no salesperson added'}", "/settings")
    b = s.booking
    sample_bank = b.get("account_number") in ("", None, "50200000000000") or b.get("ifsc") in ("", None, "HDFC0000000") \
        or "edit in settings" in (b.get("office_address") or "").lower()
    add(not sample_bank, "Bank details for the advance (own projects) are real", "Settings → Booking advance & payment",
        "/settings")
    add(bool(s.business.get("legal_name")), "Registered firm/company name is filled", "Settings → Company", "/settings",
        "warn")
    add(bool(s.business.get("rera_by_city") or s.business.get("rera_agent")), "RERA agent numbers are filled",
        "Settings → Company → RERA per city", "/settings")
    samples = [p["name"] for p in inventory.list_projects() if p.get("is_sample")]
    add(not samples, "No sample projects are being offered to buyers",
        f"Remove sample inventory ({len(samples)} projects)", "/inventory")
    demo = [p["name"] for p in inventory.list_projects() if p["name"] == "Sunrise Meadows"]
    add(not demo, "Demo project 'Sunrise Meadows' removed", "Inventory → Sunrise Meadows → Delete project", "/inventory")
    real = [p for p in inventory.list_projects() if not p.get("is_sample") and p["name"] != "Sunrise Meadows"]
    add(bool(real), "Your real projects are in Inventory", "Inventory → + Add project", "/inventory")
    partners = db.q("SELECT name FROM builders WHERE is_own = 0 AND is_sample = 0 AND (bank_account IS NULL OR "
                    "bank_account = '' OR contact_phone IS NULL OR contact_phone = '')")
    add(not partners, "Partner builders have bank details and a registration contact",
        f"Missing for: {', '.join(p['name'] for p in partners)}", "/inventory", "warn")
    add(env("CHANNEL_MODE", "console").lower() == "live", "WhatsApp Business is connected (real messages to buyers)",
        "Set up WhatsApp Business, then CHANNEL_MODE=live", "/sources", "warn")
    src = lead_sources.status()
    add(src["portal_email"]["configured"], "Portal emails are connected", "Lead sources → Portal emails", "/sources",
        "warn")
    add(src["meta_leads"]["configured"], "Meta lead ads are connected", "Lead sources → Meta lead ads", "/sources",
        "warn")
    unopened = db.q("SELECT name FROM team_access WHERE revoked = 0 AND last_seen IS NULL")
    add(not unopened, "Team members have opened their portal links",
        f"Not yet opened: {', '.join(u['name'] for u in unopened)} — Team → Send link", "/team", "warn")
    return items


# ------------------------------------------------------------------ backups

def backup_dir():
    d = DATA_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshot(keep: int = 7) -> str:
    """Consistent copy of the database (SQLite online backup) into data/backups; keeps the last `keep` days."""
    day = get_settings().now().strftime("%Y-%m-%d")
    target = backup_dir() / f"salesagent-{day}.db"
    with db._lock:
        dst = sqlite3.connect(target)
        db.conn().backup(dst)
        dst.close()
    for old in sorted(backup_dir().glob("salesagent-*.db"))[:-keep]:
        old.unlink(missing_ok=True)
    db.audit(None, "system", "backup", target.name)
    return target.name


def backup_zip() -> bytes:
    """Database + settings + uploaded files, for the owner to download."""
    buf = BytesIO()
    tmp = backup_dir() / "download-tmp.db"
    with db._lock:
        dst = sqlite3.connect(tmp)
        db.conn().backup(dst)
        dst.close()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "salesagent.db")
        if config_path().exists():
            z.write(config_path(), "config.yaml")
        media = DATA_DIR / "media"
        if media.exists():
            for f in media.iterdir():
                z.write(f, f"media/{f.name}")
    tmp.unlink(missing_ok=True)
    return buf.getvalue()


# ------------------------------------------------------------------ personal data erasure (DPDP)

def erase_lead(lead_id: int, actor: str = "owner") -> bool:
    lead = db.get_lead(lead_id)
    if not lead:
        return False
    db.update("leads", lead_id, {"name": f"Deleted buyer #{lead_id}", "phone": None, "email": None, "memory": "",
                                 "strategy": None, "opted_out": 1, "next_followup_at": None, "consent_text": None,
                                 "consent_source": None})
    db.q("UPDATE interactions SET content = '[removed on request]' WHERE lead_id = ?", (lead_id,))
    db.q("UPDATE drafts SET text = '[removed]', status = 'dropped' WHERE lead_id = ? AND status = 'pending'", (lead_id,))
    db.q("UPDATE call_tasks SET brief = '[removed]', notes = '', form_data = NULL, status = 'cancelled' "
         "WHERE lead_id = ?", (lead_id,))
    db.q("UPDATE site_visits SET form_data = NULL, feedback = '' WHERE lead_id = ?", (lead_id,))
    db.q("UPDATE audit SET detail = '[removed]' WHERE lead_id = ? AND action NOT IN ('stage', 'data_erased')", (lead_id,))
    try:
        from . import pipeline
        pipeline.move(lead_id, "lost", actor, "personal data erased on request")
    except Exception:  # noqa: BLE001 - erasure must succeed whatever the stage
        pass
    db.audit(lead_id, actor, "data_erased", "personal data removed on request")
    return True
