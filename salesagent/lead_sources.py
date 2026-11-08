"""Automatic lead sources and ad-spend import.

1. Meta lead ads   — Meta calls POST /webhook/meta when someone submits a Facebook/Instagram lead form; we fetch the
                     lead (name, phone, answers, ad and campaign name) from the Graph API and hand it to the AI.
2. Click-to-WhatsApp ads — WhatsApp messages carry a `referral` with the ad's headline/ID; the lead is tagged with
                     the ad and the AI sees what the buyer clicked.
3. Portal emails   — enquiry emails from 99acres, MagicBricks, Housing, NoBroker… are read from a mailbox (IMAP) or
                     forwarded to POST /webhook/portal-email, and turned into leads.
4. Ad spend        — Meta spend per campaign is pulled daily (Marketing API); Google Ads spend via CSV upload.

Credentials live in Railway variables (never in the database): META_PAGE_TOKEN, META_APP_SECRET, META_VERIFY_TOKEN,
META_ADS_TOKEN, META_AD_ACCOUNT_ID, LEADS_IMAP_HOST, LEADS_IMAP_USER, LEADS_IMAP_PASSWORD.
"""
from __future__ import annotations

import csv
import email
import email.policy
import hashlib
import hmac
import imaplib
import json
import logging
import re
from datetime import timedelta
from html import unescape

import requests

from . import channels, db, events, inventory, leads
from .config import env, get_settings

log = logging.getLogger("salesagent.lead_sources")
GRAPH = "https://graph.facebook.com/v21.0"
CODE_RE = re.compile(r"\bC\d+-V\d+\b", re.I)


# ------------------------------------------------------------------ helpers

def _seen(source: str, ext_id: str, mark: bool = True) -> bool:
    """True if this external event was already processed (Meta and mail servers retry)."""
    if db.q1("SELECT 1 x FROM processed_events WHERE source = ? AND ext_id = ?", (source, ext_id)):
        return True
    if mark:
        _mark(source, ext_id)
    return False


def _mark(source: str, ext_id: str) -> None:
    if not db.q1("SELECT 1 x FROM processed_events WHERE source = ? AND ext_id = ?", (source, ext_id)):
        db.insert("processed_events", {"source": source, "ext_id": ext_id, "created_at": db.now_iso()})


def _project_in(text: str) -> str:
    t = (text or "").lower()
    for p in inventory.list_projects():
        base = p["name"].replace(" (sample)", "").lower()
        if base and base in t:
            return p["name"]
    return ""


def campaign_code(*texts: str) -> str:
    for t in texts:
        m = CODE_RE.search(t or "")
        if m:
            return m.group(0).upper()
    return next((t.strip()[:60] for t in texts if t and t.strip()), "")


def _deliver_lead(data: dict, consent_text: str, consent_source: str, note: str = "") -> tuple[dict, bool]:
    lead, created = leads.upsert_lead(data, consent=True)
    upd = {"consent_at": db.now_iso(), "consent_text": consent_text, "consent_source": consent_source}
    if note:
        upd["memory"] = ((lead.get("memory") or "") + f"\n{note}").strip()
    db.update("leads", lead["id"], upd)
    db.audit(lead["id"], "system", "lead_source", {"source": data.get("source"), "via": consent_source})
    if created:
        events.dispatch(events.new_lead, lead["id"])
    elif lead.get("phone"):
        events.dispatch(events.inbound_message, lead["phone"], None,
                        f"[Enquired again via {data.get('source')}: {note or consent_source}]", "web")
    return lead, created


# ------------------------------------------------------------------ 1. Meta lead ads

def meta_signature_ok(body: bytes, header: str | None) -> bool:
    secret = env("META_APP_SECRET") or env("WHATSAPP_APP_SECRET")
    if not secret:
        return True   # signature checking switches on when the secret is set
    digest = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(header) and hmac.compare_digest(digest, header)


def _graph_get(path: str, params: dict, token: str) -> dict:
    r = requests.get(f"{GRAPH}/{path}", params={**params, "access_token": token}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Meta API {r.status_code}: {r.text[:200]}")
    return r.json()


FIELD_HINTS = [("phone", ("phone", "mobile", "whatsapp")), ("email", ("email",)),
               ("name", ("full_name", "name")), ("city", ("city",)),
               ("budget_max", ("budget", "price")), ("unit_type", ("bhk", "configuration", "size", "unit", "type")),
               ("timeline", ("when", "timeline", "planning", "buy")), ("location_pref", ("locality", "location", "area"))]


def map_meta_fields(field_data: list[dict]) -> dict:
    out: dict = {}
    first = last = ""
    for f in field_data or []:
        key = (f.get("name") or "").lower()
        val = ", ".join(v for v in (f.get("values") or []) if v).strip()
        if not val:
            continue
        if key == "first_name":
            first = val
            continue
        if key == "last_name":
            last = val
            continue
        for field, hints in FIELD_HINTS:
            if field not in out and any(h in key for h in hints):
                out[field] = val.replace("_", " ")
                break
    if "name" not in out and (first or last):
        out["name"] = f"{first} {last}".strip()
    if out.get("unit_type"):
        m = re.search(r"(\d)\s*bhk", out["unit_type"], re.I)
        out["unit_type"] = f"{m.group(1)}BHK" if m else out["unit_type"]
    if out.get("budget_max"):
        nums = re.findall(r"\d+(?:\.\d+)?\s*(?:cr|crore|l|lakh|lac)?", out["budget_max"].lower())
        out["budget_max"] = nums[-1].replace(" ", "") if nums else None
    return out


def handle_meta_webhook(payload: dict) -> int:
    """Process Meta 'leadgen' webhook events. Returns the number of leads created or updated."""
    n = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            v = change.get("value", {})
            lid = str(v.get("leadgen_id") or "")
            if not lid or _seen("meta_lead", lid):
                continue
            token = env("META_PAGE_TOKEN")
            if not token:
                db.audit(None, "system", "meta_lead_unfetched", lid)
                channels.notify_staff(get_settings().owner["phone"],
                                      f"⚠️ A Meta lead form was submitted (lead {lid}) but META_PAGE_TOKEN isn't set in "
                                      "Railway, so it couldn't be fetched. See Dashboard → Lead sources.")
                continue
            try:
                lead = _graph_get(lid, {"fields": "field_data,ad_name,campaign_name,form_id,platform,created_time"},
                                  token)
            except (RuntimeError, requests.RequestException) as e:
                db.audit(None, "system", "meta_lead_error", f"{lid}: {e}")
                continue
            data = map_meta_fields(lead.get("field_data", []))
            if not data.get("phone") and not data.get("email"):
                db.audit(None, "system", "meta_lead_no_contact", lid)
                continue
            ad = " / ".join(x for x in (lead.get("campaign_name"), lead.get("ad_name")) if x)
            data.update({"source": "meta_ads", "campaign": campaign_code(lead.get("ad_name"), lead.get("campaign_name")),
                         "project_interest": _project_in(ad)})
            _deliver_lead(data, "Submitted a Facebook/Instagram lead form (Meta) asking to be contacted",
                          f"meta lead form {lead.get('form_id') or v.get('form_id')}",
                          note=f"Came from Meta lead ad: {ad}" if ad else "")
            n += 1
    return n


# ------------------------------------------------------------------ 2. Click-to-WhatsApp ads

def ctwa_referral(message: dict) -> dict | None:
    ref = message.get("referral") or {}
    if not ref or ref.get("source_type") not in ("ad", "post"):
        return None
    return {"headline": ref.get("headline", ""), "body": ref.get("body", ""), "source_id": ref.get("source_id", ""),
            "source_url": ref.get("source_url", "")}


def tag_ctwa_lead(phone: str, name: str, ref: dict) -> dict:
    """Create/tag the lead behind a Click-to-WhatsApp ad before the AI replies to their first message."""
    text = f"{ref['headline']} {ref['body']}"
    lead = db.find_lead_by_phone(phone)
    campaign = campaign_code(ref["headline"], ref["body"]) if CODE_RE.search(text) else f"ad:{ref['source_id']}"
    note = f"Came from a Click-to-WhatsApp ad: \"{ref['headline']}\"" + (f" — {ref['body'][:150]}" if ref["body"] else "")
    if not lead:
        lead, _ = leads.upsert_lead({"phone": phone, "name": name, "source": "meta_ctwa", "campaign": campaign,
                                     "project_interest": _project_in(text)}, consent=True)
    db.update("leads", lead["id"], {"memory": ((lead.get("memory") or "") + f"\n{note}").strip(),
                                    "consent_at": lead.get("consent_at") or db.now_iso(),
                                    "consent_text": lead.get("consent_text") or "Started a WhatsApp chat from our ad",
                                    "consent_source": lead.get("consent_source") or f"ctwa ad {ref['source_id']}"})
    if not lead.get("campaign"):
        db.update("leads", lead["id"], {"campaign": campaign, "source": "meta_ctwa"})
    db.audit(lead["id"], "system", "ctwa_referral", ref)
    return db.get_lead(lead["id"])


# ------------------------------------------------------------------ 3. Portal emails

PORTALS = {"99acres": ("99acres",), "magicbricks": ("magicbricks",), "housing": ("housing.com", "housing "),
           "nobroker": ("nobroker",), "squareyards": ("squareyards",), "commonfloor": ("commonfloor",),
           "proptiger": ("proptiger",), "makaan": ("makaan",)}
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def portal_of(sender: str, subject: str, body: str) -> str | None:
    hay = f"{sender} {subject} {body}".lower()
    return next((name for name, keys in PORTALS.items() if any(k in hay for k in keys)), None)


def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", s)
    return unescape(re.sub(r"<[^>]+>", " ", s))


def _label(body: str, *labels: str) -> str:
    for lab in labels:
        m = re.search(rf"(?im)^\s*{lab}\s*[:\-]\s*(.+?)\s*$", body)
        if m:
            return m.group(1).strip()
    return ""


def parse_portal_email(sender: str, subject: str, body: str) -> dict | None:
    portal = portal_of(sender, subject, body)
    if not portal:
        return None
    text = _strip_html(body) if "<" in body and ">" in body else body
    own = {db.normalize_phone(x) for x in [get_settings().owner.get("phone", "")] +
           [r.get("phone", "") for r in get_settings().sales_team]}
    phone = next((db.normalize_phone(m.group(1)) for m in PHONE_RE.finditer(text)
                  if db.normalize_phone(m.group(1)) not in own), "")
    mail = next((e for e in EMAIL_RE.findall(text) if not any(k in e.lower() for k in
                 list(PORTALS) + ["noreply", "no-reply", "donotreply", "alerts", "support"])), "")
    if not phone and not mail:
        return None
    name = _label(text, "name", "buyer name", "customer name", "contact name", "user name") or ""
    name = re.sub(r"\s*(mobile|phone|email).*$", "", name, flags=re.I)[:60]
    data = {"name": name, "phone": phone, "email": mail, "source": "portal", "campaign": portal,
            "city": _label(text, "city"), "unit_type": _label(text, "bhk", "configuration", "property type"),
            "budget_max": _label(text, "budget", "price range"), "location_pref": _label(text, "locality", "location")}
    data["project_interest"] = _project_in(f"{subject} {text}") or _label(text, "project", "project name")
    if data["budget_max"]:
        nums = re.findall(r"\d+(?:\.\d+)?\s*(?:cr|crore|l|lakh|lac)?", data["budget_max"].lower())
        data["budget_max"] = nums[-1].replace(" ", "") if nums else None
    m = re.search(r"(\d)\s*bhk", data.get("unit_type") or "", re.I)
    if m:
        data["unit_type"] = f"{m.group(1)}BHK"
    return {k: v for k, v in data.items() if v}


def process_email(sender: str, subject: str, body: str, message_id: str = "") -> int | None:
    key = message_id or hashlib.sha256(f"{sender}|{subject}|{body[:2000]}".encode()).hexdigest()
    if _seen("email", key, mark=False) or _seen("email_ignored", key, mark=False):
        return None
    data = parse_portal_email(sender, subject, body)
    if not data:
        if portal_of(sender, subject, body):
            # A portal email we couldn't read: keep it for retry, and show a snippet on the Lead sources page once.
            if not db.q1("SELECT id FROM audit WHERE action = 'email_unreadable' AND detail LIKE ?", (f'%{key[:40]}%',)):
                text = _strip_html(body) if "<" in body else body
                db.audit(None, "system", "email_unreadable", json.dumps(
                    {"key": key[:40], "from": sender[:80], "subject": subject[:120],
                     "snippet": re.sub(r"\s+", " ", text)[:600]}, ensure_ascii=False))
            return None
        _mark("email_ignored", key)
        db.audit(None, "system", "email_ignored", json.dumps({"from": sender[:80], "subject": subject[:120]}))
        return None
    _mark("email", key)
    lead, _ = _deliver_lead(data, f"Enquired about property on {data['campaign']}",
                            f"{data['campaign']} enquiry email", note=f"Enquiry from {data['campaign']}: {subject[:120]}")
    return lead["id"]


def _email_text(msg) -> str:
    if msg.is_multipart():
        plain = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None)
        part = plain or next((p for p in msg.walk() if p.get_content_type() == "text/html"), None)
        return part.get_content() if part else ""
    return msg.get_content()


def poll_mailbox(limit: int = 30, recheck_ignored: bool = False) -> dict:
    user = env("LEADS_IMAP_USER").strip().strip('"').strip("'")
    pw = env("LEADS_IMAP_PASSWORD").replace(" ", "").strip().strip('"').strip("'")   # Google shows app passwords with spaces
    if not user or not pw:
        return {"configured": False}
    host = env("LEADS_IMAP_HOST", "imap.gmail.com")
    created = 0
    if recheck_ignored:   # manual "Check mailbox now": give recently ignored emails another look
        db.q("DELETE FROM processed_events WHERE source = 'email_ignored'")
    with imaplib.IMAP4_SSL(host, timeout=30) as M:
        M.login(user, pw)
        M.select("INBOX")
        since = (get_settings().now() - timedelta(days=3)).strftime("%d-%b-%Y")
        _, data = M.search(None, "SINCE", since)      # recent mail, opened or not; duplicates are skipped
        for num in (data[0].split() if data and data[0] else [])[:limit]:
            _, parts = M.fetch(num, "(RFC822)")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), b"")
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            try:
                if process_email(str(msg.get("From", "")), str(msg.get("Subject", "")), _email_text(msg),
                                 str(msg.get("Message-ID", ""))):
                    created += 1
            finally:
                M.store(num, "+FLAGS", "\\Seen")
    db.audit(None, "system", "mailbox_polled", {"leads": created, "checked": len(data[0].split()) if data and data[0] else 0})
    return {"configured": True, "leads": created}


# ------------------------------------------------------------------ 4. Ad spend

def sync_meta_spend(months: int = 2) -> dict:
    token, account = env("META_ADS_TOKEN") or env("META_PAGE_TOKEN"), env("META_AD_ACCOUNT_ID").replace("act_", "")
    if not token or not account:
        return {"configured": False}
    now = get_settings().now()
    since = (now.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    params = {"level": "campaign", "fields": "campaign_name,spend", "time_increment": "monthly", "limit": 500,
              "time_range": json.dumps({"since": since.strftime("%Y-%m-%d"), "until": now.strftime("%Y-%m-%d")})}
    rows, url = [], f"act_{account}/insights"
    data = _graph_get(url, params, token)
    while True:
        rows += data.get("data", [])
        nxt = (data.get("paging") or {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=20)
        if r.status_code >= 300:
            break
        data = r.json()
    months_seen = sorted({r["date_start"][:7] for r in rows if r.get("date_start")})
    for m in months_seen:
        db.q("DELETE FROM ad_spend WHERE month = ? AND notes = 'auto:meta'", (m,))
    total = 0
    for r in rows:
        amt = int(round(float(r.get("spend") or 0)))
        if amt <= 0:
            continue
        db.insert("ad_spend", {"month": r["date_start"][:7], "source": "meta_ads",
                               "campaign": campaign_code(r.get("campaign_name", "")), "amount": amt,
                               "notes": "auto:meta", "created_at": db.now_iso()})
        total += amt
    db.audit(None, "system", "meta_spend_synced", {"months": months_seen, "total": total})
    return {"configured": True, "months": months_seen, "total": total, "rows": len(rows)}


def import_google_csv(path: str, default_month: str) -> dict:
    """Google Ads 'Campaign' report exported as CSV: needs Campaign and Cost columns; Month is optional."""
    from .events import parse_amount
    added, months = 0, set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    start = next((i for i, ln in enumerate(lines) if "campaign" in ln.lower() and "cost" in ln.lower()), 0)
    rows = list(csv.DictReader(lines[start:]))
    for r in rows:
        low = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        camp = low.get("campaign", "")
        cost = (low.get("cost") or "").replace("₹", "").replace(",", "").replace("INR", "").strip()
        if not camp or camp.lower().startswith("total") or not cost:
            continue
        try:
            amt = int(round(float(cost)))
        except ValueError:
            amt = parse_amount(cost) or 0
        month = (low.get("month") or default_month)[:7]
        if re.match(r"^[A-Za-z]+ \d{4}$", month):
            from datetime import datetime
            month = datetime.strptime(month, "%B %Y").strftime("%Y-%m")
        if amt <= 0:
            continue
        if month not in months:
            db.q("DELETE FROM ad_spend WHERE month = ? AND notes = 'csv:google'", (month,))
            months.add(month)
        db.insert("ad_spend", {"month": month, "source": "google_ads", "campaign": campaign_code(camp), "amount": amt,
                               "notes": "csv:google", "created_at": db.now_iso()})
        added += 1
    return {"rows": added, "months": sorted(months)}


# ------------------------------------------------------------------ status for the dashboard

def recent_emails(limit: int = 12) -> list[dict]:
    out = []
    for r in db.q("SELECT created_at, action, detail, lead_id FROM audit WHERE action IN "
                  "('email_unreadable','email_ignored') OR (action = 'lead_source' AND detail LIKE '%email%') "
                  "ORDER BY id DESC LIMIT ?", (limit,)):
        try:
            d = json.loads(r["detail"])
        except ValueError:
            d = {"subject": r["detail"]}
        out.append({"at": r["created_at"], "action": r["action"], "lead_id": r["lead_id"], **d})
    return out


def status() -> dict:
    week = (get_settings().now() - timedelta(days=7)).isoformat()

    def count(source):
        return db.q1("SELECT COUNT(*) n FROM leads WHERE source = ? AND created_at >= ?", (source, week))["n"]

    def last(action):
        r = db.q1("SELECT created_at, detail FROM audit WHERE action = ? ORDER BY id DESC LIMIT 1", (action,))
        return (r or {}).get("created_at", "")
    return {
        "meta_leads": {"configured": bool(env("META_PAGE_TOKEN")), "verify_token": bool(env("META_VERIFY_TOKEN")),
                       "signed": bool(env("META_APP_SECRET") or env("WHATSAPP_APP_SECRET")), "week": count("meta_ads")},
        "ctwa": {"configured": bool(env("WHATSAPP_TOKEN")), "week": count("meta_ctwa")},
        "portal_email": {"configured": bool(env("LEADS_IMAP_USER") and env("LEADS_IMAP_PASSWORD")),
                         "week": count("portal"), "last_poll": last("mailbox_polled")},
        "meta_spend": {"configured": bool((env("META_ADS_TOKEN") or env("META_PAGE_TOKEN")) and env("META_AD_ACCOUNT_ID")),
                       "last_sync": last("meta_spend_synced")},
    }
