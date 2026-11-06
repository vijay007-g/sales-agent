"""Outbound messaging: WhatsApp Cloud API, email (SMTP), or console dry-run."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import requests

from .config import DATA_DIR, env, get_settings

log = logging.getLogger("salesagent.channels")
CONSOLE_LISTENERS: list = []   # callbacks(kind, to, text) - used by the simulator


def mode() -> str:
    return env("CHANNEL_MODE", "console").lower()


def _console(kind: str, to: str, text: str) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{get_settings().now():%Y-%m-%d %H:%M}] {kind} -> {to}\n{text}\n{'-' * 60}\n"
    with open(DATA_DIR / "outbox.log", "a") as f:
        f.write(line)
    log.info("%s -> %s: %s", kind, to, text[:200])
    for cb in CONSOLE_LISTENERS:
        cb(kind, to, text)
    return {"ok": True, "mode": "console"}


def send_whatsapp(phone: str, text: str, within_24h_window: bool = True,
                  phone_number_id: str | None = None, sender: str = "") -> dict:
    """Send a WhatsApp message. Outside Meta's 24-hour customer-service window,
    a pre-approved template is required; we use WHATSAPP_TEMPLATE_NAME with the
    text as its single body parameter. `phone_number_id` lets each salesperson send from their own
    WhatsApp Business number (defaults to the company number)."""
    if mode() != "live":
        return _console(f"WHATSAPP{' from ' + sender if sender else ''}", phone, text)
    token = env("WHATSAPP_TOKEN")
    phone_id = phone_number_id or env("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_id:
        return {"ok": False, "error": "WhatsApp credentials missing"}
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    to = phone.lstrip("+")
    if within_24h_window or not env("WHATSAPP_TEMPLATE_NAME"):
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
                   "text": {"preview_url": False, "body": text[:4096]}}
    else:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "template",
                   "template": {"name": env("WHATSAPP_TEMPLATE_NAME"),
                                "language": {"code": env("WHATSAPP_TEMPLATE_LANG", "en")},
                                "components": [{"type": "body", "parameters": [
                                    {"type": "text", "text": text[:1000]}]}]}}
    try:
        r = requests.post(url, json=payload, timeout=20,
                          headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 300:
            return {"ok": False, "error": f"WhatsApp {r.status_code}: {r.text[:300]}"}
        return {"ok": True, "mode": "live", "id": r.json().get("messages", [{}])[0].get("id")}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def send_email(to: str, subject: str, text: str) -> dict:
    if mode() != "live" or not env("SMTP_HOST"):
        return _console("EMAIL", to, f"Subject: {subject}\n\n{text}")
    msg = EmailMessage()
    msg["From"] = env("SMTP_FROM") or env("SMTP_USER")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    try:
        with smtplib.SMTP(env("SMTP_HOST"), int(env("SMTP_PORT", "587")), timeout=20) as s:
            s.starttls()
            if env("SMTP_USER"):
                s.login(env("SMTP_USER"), env("SMTP_PASSWORD"))
            s.send_message(msg)
        return {"ok": True, "mode": "live"}
    except Exception as e:  # noqa: BLE001 - report any SMTP failure back to the agent
        return {"ok": False, "error": str(e)}


def notify_staff(phone: str, text: str) -> dict:
    """Messages to the owner / site persons (always WhatsApp)."""
    return send_whatsapp(phone, text, within_24h_window=True)
