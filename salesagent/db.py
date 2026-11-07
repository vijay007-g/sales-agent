"""SQLite storage for leads, conversations, visits, offers, approvals and the audit log."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from .config import DATA_DIR, get_settings

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, phone TEXT, email TEXT,
    source TEXT DEFAULT 'other', campaign TEXT,
    preferred_channel TEXT DEFAULT 'whatsapp',
    language TEXT,
    project_interest TEXT, unit_type TEXT,
    budget_min INTEGER, budget_max INTEGER,
    timeline TEXT, purpose TEXT, location_pref TEXT,
    financing TEXT,
    stage TEXT DEFAULT 'new',
    score INTEGER DEFAULT 0,
    temperature TEXT DEFAULT 'unknown',
    memory TEXT DEFAULT '',
    consent INTEGER DEFAULT 1,
    opted_out INTEGER DEFAULT 0,
    needs_human INTEGER DEFAULT 0,
    followup_attempts INTEGER DEFAULT 0,
    next_followup_at TEXT, followup_purpose TEXT,
    last_inbound_at TEXT, last_outbound_at TEXT,
    lost_reason TEXT,
    rm_name TEXT,
    strategy TEXT,
    city TEXT,
    consent_at TEXT, consent_text TEXT, consent_source TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone) WHERE phone IS NOT NULL AND phone != '';
CREATE INDEX IF NOT EXISTS idx_leads_followup ON leads(next_followup_at);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, direction TEXT, channel TEXT, author TEXT,
    content TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_inter_lead ON interactions(lead_id);

CREATE TABLE IF NOT EXISTS site_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, kind TEXT DEFAULT 'site', project TEXT, scheduled_at TEXT, site_person TEXT,
    site_person_phone TEXT,
    form_token TEXT, form_data TEXT,
    status TEXT DEFAULT 'scheduled',
    reminders_sent TEXT DEFAULT '[]',
    feedback TEXT, interest_level TEXT, liked_units TEXT, objections TEXT,
    created_at TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, project TEXT, unit_type TEXT, unit_no TEXT, unit_id INTEGER, project_id INTEGER,
    list_price INTEGER, offered_price INTEGER, discount_pct REAL,
    concessions TEXT, payment_terms TEXT,
    customer_ask INTEGER, justification TEXT,
    status TEXT,
    owner_counter_price INTEGER, owner_note TEXT,
    created_at TEXT, decided_at TEXT
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, offer_id INTEGER, unit_id INTEGER,
    status TEXT DEFAULT 'awaiting_owner',
    token_amount INTEGER, notes TEXT,
    payment_mode TEXT, amount_paid INTEGER, payment_ref TEXT, paid_at TEXT,
    created_at TEXT, decided_at TEXT
);

CREATE TABLE IF NOT EXISTS call_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, rm_name TEXT, due_at TEXT, purpose TEXT, brief TEXT,
    status TEXT DEFAULT 'open',
    form_token TEXT, outcome TEXT, notes TEXT, form_data TEXT,
    notified INTEGER DEFAULT 0,
    created_at TEXT, done_at TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, rm_name TEXT, channel TEXT, subject TEXT, text TEXT, media_id INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TEXT, decided_at TEXT
);

CREATE TABLE IF NOT EXISTS builders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, is_own INTEGER DEFAULT 0,
    contact_name TEXT, contact_phone TEXT, contact_email TEXT,
    commission_type TEXT DEFAULT 'pct', commission_value REAL DEFAULT 0,
    payment_terms_days INTEGER DEFAULT 45, registration_validity_days INTEGER DEFAULT 90,
    bank_payee TEXT, bank_name TEXT, bank_account TEXT, bank_ifsc TEXT, upi_id TEXT,
    verify_phone TEXT, office_address TEXT,
    notes TEXT, is_sample INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_at TEXT
);

CREATE TABLE IF NOT EXISTS inv_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    builder_id INTEGER, name TEXT, city TEXT, locality TEXT, type TEXT,
    status TEXT, possession TEXT, rera TEXT,
    highlights TEXT, payment_plans TEXT, approval_concessions TEXT, free_concessions TEXT,
    site_host_name TEXT, site_host_phone TEXT, visit_hours TEXT DEFAULT '10:00-18:00',
    visit_days TEXT DEFAULT '0,1,2,3,4,5,6', max_visits_per_day INTEGER DEFAULT 6,
    commission_type TEXT, commission_value REAL,
    slug TEXT, gst_pct REAL, stamp_duty_pct REAL, registration_pct REAL, other_charges TEXT,
    is_sample INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER, unit_no TEXT, unit_type TEXT, floor TEXT, facing TEXT,
    size_sqft INTEGER, carpet_sqft INTEGER, list_price INTEGER, floor_price INTEGER,
    quantity INTEGER DEFAULT 1,
    status TEXT DEFAULT 'available',
    notes TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_units_project ON units(project_id);

CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, project_id INTEGER, builder_id INTEGER,
    status TEXT DEFAULT 'sent', reason TEXT, message TEXT,
    sent_at TEXT, valid_until TEXT, ack_at TEXT, builder_note TEXT
);

CREATE TABLE IF NOT EXISTS commissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER, lead_id INTEGER, project_id INTEGER, builder_id INTEGER, unit_id INTEGER,
    deal_value INTEGER, amount INTEGER,
    status TEXT DEFAULT 'earned',
    invoice_no TEXT, invoiced_at TEXT, due_at TEXT,
    collected_amount INTEGER, collected_at TEXT, notes TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER, unit_type TEXT, kind TEXT, title TEXT,
    filename TEXT, path TEXT, token TEXT, mime TEXT, size INTEGER, created_at TEXT
);

CREATE TABLE IF NOT EXISTS ad_spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT, source TEXT, campaign TEXT, city TEXT, amount INTEGER, notes TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT, content TEXT, based_on INTEGER, created_at TEXT
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, channel TEXT, audience TEXT, content TEXT,
    status TEXT DEFAULT 'draft', created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, actor TEXT, action TEXT, detail TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, event TEXT, input_tokens INTEGER, output_tokens INTEGER,
    cache_read INTEGER, cache_write INTEGER, created_at TEXT
);
"""

_conn: sqlite3.Connection | None = None


def db_path() -> str:
    return os.environ.get("SALESAGENT_DB", str(DATA_DIR / "salesagent.db"))


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = db_path()
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        stmts = [x.strip() for x in SCHEMA.split(";") if x.strip()]
        for st in stmts:
            if st.startswith("CREATE TABLE"):
                _conn.execute(st)
        _migrate(_conn)
        for st in stmts:
            if not st.startswith("CREATE TABLE"):
                _conn.execute(st)
        from . import inventory
        inventory.seed_from_config()
    return _conn


def _migrate(c: sqlite3.Connection) -> None:
    """Add columns introduced after a database was first created."""
    import re
    for table, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", SCHEMA, re.S):
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        for line in body.split("\n"):
            for part in line.strip().rstrip(",").split(", "):
                bits = part.split()
                if len(bits) >= 2 and bits[0].isidentifier() and bits[0] not in have and bits[0] != "id":
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {part}")
                    have.add(bits[0])


def reset_connection() -> None:
    """Used by tests to point at a fresh database."""
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _lock:
        c = conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise


def now_iso() -> str:
    return get_settings().now().isoformat(timespec="seconds")


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_settings().tz)
    return dt


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = ()) -> dict | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def insert(table: str, data: dict) -> int:
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    with _lock:
        cur = conn().execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))
        return cur.lastrowid


def update(table: str, row_id: int, data: dict) -> None:
    if not data:
        return
    if table in ("leads", "site_visits"):
        data = {**data, "updated_at": now_iso()}
    sets = ", ".join(f"{k} = ?" for k in data)
    with _lock:
        conn().execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), row_id))


def audit(lead_id: int | None, actor: str, action: str, detail: Any = "") -> None:
    if not isinstance(detail, str):
        detail = json.dumps(detail, default=str)
    insert("audit", {"lead_id": lead_id, "actor": actor, "action": action,
                     "detail": detail, "created_at": now_iso()})


# ---------- convenience accessors ----------

def get_lead(lead_id: int) -> dict | None:
    return q1("SELECT * FROM leads WHERE id = ?", (lead_id,))


def new_token() -> str:
    import secrets
    return secrets.token_urlsafe(16)


def find_lead_by_phone(phone: str) -> dict | None:
    return q1("SELECT * FROM leads WHERE phone = ?", (normalize_phone(phone),))


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:          # assume India if 10 digits; change for your country
        digits = "91" + digits
    return "+" + digits if digits else ""


def log_interaction(lead_id: int, direction: str, channel: str, author: str, content: str) -> None:
    ts = now_iso()
    insert("interactions", {"lead_id": lead_id, "direction": direction, "channel": channel,
                            "author": author, "content": content, "created_at": ts})
    if direction == "in":
        update("leads", lead_id, {"last_inbound_at": ts})
    elif direction == "out":
        update("leads", lead_id, {"last_outbound_at": ts})
