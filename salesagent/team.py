"""The human sales team: lead assignment, messages sent in the salesperson's name, call tasks, drafts.

Every customer-facing message goes out under the lead's assigned salesperson (RM), from that person's
WhatsApp Business number, so the customer always deals with the same person who calls them.
"""
from __future__ import annotations

import json
from datetime import timedelta

from . import channels, db
from .config import env, get_settings


def assign_rm(lead_id: int) -> dict | None:
    """Assign the salesperson with the fewest active leads (and capacity)."""
    s = get_settings()
    lead = db.get_lead(lead_id)
    if lead.get("rm_name") and s.rm(lead["rm_name"]):
        return s.rm(lead["rm_name"])
    if not s.sales_team:
        return None
    loads = []
    city = (lead.get("city") or "").strip().lower()
    team_for_city = [r for r in s.sales_team if city and city in [c.lower() for c in r.get("cities") or []]]
    candidates = team_for_city or [r for r in s.sales_team if not r.get("cities")] or s.sales_team
    for r in candidates:
        n = db.q1("SELECT COUNT(*) n FROM leads WHERE rm_name = ? AND stage NOT IN ('booked','lost')",
                  (r["name"],))["n"]
        if n < r.get("max_active_leads", 10**6):
            loads.append((n, r["name"]))
    rm = s.rm(min(loads)[1]) if loads else candidates[0]
    db.update("leads", lead_id, {"rm_name": rm["name"]})
    db.audit(lead_id, "system", "assigned", rm["name"])
    return rm


def rm_for(lead: dict) -> dict:
    s = get_settings()
    rm = s.rm(lead.get("rm_name")) or assign_rm(lead["id"])
    return rm or {"name": s.business["name"], "phone": s.owner["phone"], "message_mode": "auto"}


def prompts_intro() -> str:
    from .prompts import assistant_intro
    return assistant_intro()


def base_url() -> str:
    return env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


def within_24h(lead: dict) -> bool:
    last = db.parse_dt(lead.get("last_inbound_at"))
    return bool(last and get_settings().now() - last < timedelta(hours=23, minutes=30))


# ------------------------- messages to customers -------------------------

def deliver(lead_id: int, text: str, channel: str = "whatsapp", subject: str = "",
            author: str = "agent", media_id: int | None = None) -> dict:
    """Actually send a message to the customer from the RM's number, and log it."""
    lead = db.get_lead(lead_id)
    if lead["opted_out"]:
        return {"ok": False, "error": "Customer opted out."}
    rm = rm_for(lead)
    if channel == "whatsapp" and not lead["phone"]:
        channel = "email"
    if media_id:
        from .sales_kit import media_url
        m = db.q1("SELECT * FROM media WHERE id = ?", (media_id,))
        if not m:
            return {"ok": False, "error": "Attachment no longer exists."}
        url = media_url(m)
        if channel == "email":
            res = channels.send_email(lead["email"], subject or m["title"], f"{text}\n\n{m['title']}: {url}")
        else:
            res = channels.send_whatsapp_media(lead["phone"], url, m["mime"], text, m["filename"],
                                               phone_number_id=rm.get("whatsapp_phone_number_id") or None,
                                               sender=rm["name"])
        if res.get("ok"):
            db.log_interaction(lead_id, "out", channel, author, f"[sent {m['kind']}: {m['title']}] {text}".strip())
        return res
    if channel == "email":
        if not lead["email"]:
            return {"ok": False, "error": "No email on file. Use WhatsApp."}
        res = channels.send_email(lead["email"], subject or get_settings().business["name"],
                                  f"{text}\n\n{prompts_intro()}, on behalf of {rm['name']}\n{get_settings().business['name']}")
    else:
        res = channels.send_whatsapp(lead["phone"], text, within_24h_window=within_24h(lead),
                                     phone_number_id=rm.get("whatsapp_phone_number_id") or None,
                                     sender=rm["name"])
    if res.get("ok"):
        db.log_interaction(lead_id, "out", channel, author, text)
    return res


def send_or_draft(lead_id: int, text: str, channel: str = "whatsapp", subject: str = "",
                  media_id: int | None = None) -> dict:
    """AI messages: sent directly in 'auto' mode, or queued for the RM to approve in 'review' mode."""
    lead = db.get_lead(lead_id)
    rm = rm_for(lead)
    if rm.get("message_mode", "auto") != "review":
        return deliver(lead_id, text, channel, subject, media_id=media_id)
    did = db.insert("drafts", {"lead_id": lead_id, "rm_name": rm["name"], "channel": channel,
                               "subject": subject, "text": text, "status": "pending", "media_id": media_id,
                               "created_at": db.now_iso()})
    channels.notify_staff(rm["phone"], (
        f"DRAFT D{did} for {lead['name'] or lead['phone']} (#{lead_id}):\n\n{text}\n"
        f"{_attachment_note(media_id)}\n"
        f"Reply  SEND D{did}   or   EDIT D{did} <your version>   or   DROP D{did}"))
    db.audit(lead_id, "agent", "draft", {"draft_id": did})
    return {"ok": True, "status": "drafted_for_review", "draft_id": did,
            "message": f"{rm['name']} reviews and sends it. Treat it as sent."}


def _attachment_note(media_id: int | None) -> str:
    if not media_id:
        return ""
    m = db.q1("SELECT kind, title FROM media WHERE id = ?", (media_id,))
    return f"📎 with attachment: {m['title']} ({m['kind']})\n" if m else ""


def approve_draft(draft_id: int, edited_text: str | None = None, actor: str = "rm") -> str:
    d = db.q1("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    if not d or d["status"] != "pending":
        return f"Draft D{draft_id} is not pending."
    if edited_text is not None and " ".join(edited_text.split()) == " ".join(d["text"].split()):
        edited_text = None   # only whitespace differs: not a real edit
    text = (edited_text or d["text"]).strip()
    res = deliver(d["lead_id"], text, d["channel"], d["subject"] or "",
                  author="agent" if not edited_text else "rm", media_id=d.get("media_id"))
    if not res.get("ok"):
        return f"Could not send D{draft_id}: {res.get('error')}"
    db.update("drafts", draft_id, {"status": "edited" if edited_text else "sent", "text": text,
                                   "decided_at": db.now_iso()})
    if edited_text:
        # The RM's edits are the best training signal for the agent's tone.
        db.audit(d["lead_id"], actor, "draft_edited", {"ai": d["text"], "rm": text})
    return f"Sent D{draft_id}."


def drop_draft(draft_id: int) -> str:
    db.update("drafts", draft_id, {"status": "dropped", "decided_at": db.now_iso()})
    return f"Dropped D{draft_id}."


# ------------------------- call tasks -------------------------

CALL_OUTCOMES = ["spoke", "no_answer", "busy", "switched_off", "call_back_later", "wrong_number"]


def create_call_task(lead_id: int, purpose: str, minutes_from_now: float, brief: str) -> dict:
    lead = db.get_lead(lead_id)
    rm = rm_for(lead)
    # one open task per lead: update instead of piling up
    open_task = db.q1("SELECT * FROM call_tasks WHERE lead_id = ? AND status = 'open'", (lead_id,))
    due = get_settings().now() + timedelta(minutes=max(5.0, minutes_from_now))
    if open_task:
        db.update("call_tasks", open_task["id"], {"purpose": purpose, "brief": brief,
                                                  "due_at": due.isoformat(timespec="minutes"), "notified": 0})
        tid = open_task["id"]
    else:
        tid = db.insert("call_tasks", {"lead_id": lead_id, "rm_name": rm["name"],
                                       "due_at": due.isoformat(timespec="minutes"), "purpose": purpose,
                                       "brief": brief, "status": "open", "form_token": db.new_token(),
                                       "created_at": db.now_iso()})
    db.audit(lead_id, "agent", "call_task", {"task_id": tid, "purpose": purpose})
    if minutes_from_now <= 60:
        notify_call_task(tid)
    return {"ok": True, "task_id": tid, "due_at": due.isoformat(timespec="minutes"), "rm": rm["name"]}


def notify_call_task(task_id: int) -> None:
    t = db.q1("SELECT * FROM call_tasks WHERE id = ?", (task_id,))
    lead = db.get_lead(t["lead_id"])
    rm = rm_for(lead)
    due = db.parse_dt(t["due_at"])
    channels.notify_staff(rm["phone"], (
        f"📞 CALL C{task_id} — {lead['name'] or ''} {lead['phone']}  (by {due:%I:%M %p})\n"
        f"Goal: {t['purpose']}\n\n{t['brief']}\n\n"
        f"Brief, call button & log: {_rm_portal(rm, lead)}\n"
        f"or reply  CALLED C{task_id} <what happened>   |   NOANSWER C{task_id}"))
    db.update("call_tasks", task_id, {"notified": 1})


def _rm_portal(rm: dict, lead: dict) -> str:
    from . import team_access
    if not rm.get("phone"):
        return f"{base_url()}/f/call/"
    return team_access.link_for("sales", rm["phone"], f"/lead/{lead['id']}")


def log_call(task_id: int, outcome: str, data: dict, actor: str = "rm") -> dict | None:
    t = db.q1("SELECT * FROM call_tasks WHERE id = ?", (task_id,))
    if not t:
        return None
    done = outcome in ("spoke", "wrong_number")
    db.update("call_tasks", task_id, {"status": "done" if done else "attempted", "outcome": outcome,
                                      "notes": data.get("summary", ""),
                                      "form_data": json.dumps(data, ensure_ascii=False),
                                      "done_at": db.now_iso()})
    summary = "; ".join(f"{k}: {v}" for k, v in data.items() if v)
    db.log_interaction(t["lead_id"], "call", "phone", t["rm_name"] or actor,
                       f"[CALL {outcome}] {summary}")
    db.audit(t["lead_id"], actor, "call_logged", {"task_id": task_id, "outcome": outcome})
    return t
