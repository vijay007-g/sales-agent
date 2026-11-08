"""The agent loop: one run = one event for one lead."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict

import anthropic

from . import db, prompts
from .config import get_settings
from .tools import TOOLS, ToolContext, run_tool

log = logging.getLogger("salesagent.agent")

NEGOTIATION_EVENTS = {"owner_decision", "booking_decision", "visit_outcome"}
_lead_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4)
    return _client


def set_client(client) -> None:
    """Inject a fake client in tests."""
    global _client
    _client = client


def _effort(lead: dict, event: str) -> str:
    cfg = get_settings().agent
    if event in NEGOTIATION_EVENTS or lead["stage"] in ("negotiation", "visit_done", "booking_pending",
                                                         "payment_pending"):
        return cfg.get("effort_negotiation", "high")
    return cfg.get("effort_routine", "medium")


def run(lead_id: int, event: str, detail: str) -> ToolContext:
    with _lead_locks[lead_id]:
        return _run(lead_id, event, detail)


def _run(lead_id: int, event: str, detail: str) -> ToolContext:
    s = get_settings()
    lead = db.get_lead(lead_id)
    ctx = ToolContext(lead_id=lead_id, event=event)
    if not lead:
        return ctx
    if lead["needs_human"] and event not in ("human_resumed",):
        log.info("lead %s is with a human; skipping agent run for %s", lead_id, event)
        return ctx

    client = get_client()
    from .team import rm_for
    rm = rm_for(lead)
    system = [
        {"type": "text", "text": prompts.system_prompt(), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": prompts.persona_and_playbook(rm), "cache_control": {"type": "ephemeral"}},
    ]
    stale = db.q("SELECT id, text FROM drafts WHERE lead_id = ? AND status = 'pending' ORDER BY id", (lead_id,))
    if stale:
        for d in stale:
            db.update("drafts", d["id"], {"status": "superseded", "decided_at": db.now_iso()})
        db.audit(lead_id, "system", "drafts_superseded", [d["id"] for d in stale])
        detail += ("\n\nNote: these earlier drafts of yours were never sent (the salesperson hadn't approved them "
                   "before this new event) and have been withdrawn:\n" + "\n".join(f"- {d['text']}" for d in stale)
                   + "\nThe customer has NOT seen them. Write one fresh message that fits the situation now, "
                     "keeping only what is still relevant.")
    messages: list = [{"role": "user", "content": prompts.lead_briefing(lead_id, event, detail)}]
    max_rounds = int(s.agent.get("max_tool_rounds", 12))
    from . import models
    model, why = models.choose(lead, event, detail)
    ctx.model = model

    for _ in range(max_rounds):
        try:
            resp = client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=system,
                tools=TOOLS,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": _effort(lead, event)},
                **models.request_extras(model),
            )
        except anthropic.RateLimitError as e:
            log.warning("rate limited on lead %s; will retry on next follow-up tick", lead_id)
            from . import health
            health.ai_failed(lead_id, 429, getattr(e, "message", str(e)))
            _retry_later(lead_id)
            break
        except anthropic.APIStatusError as e:
            log.error("Claude API error %s on lead %s: %s", e.status_code, lead_id, e.message)
            from . import health
            health.ai_failed(lead_id, e.status_code, e.message)
            _retry_later(lead_id)
            break
        except anthropic.APIConnectionError as e:
            log.error("network error on lead %s: %s", lead_id, e)
            _retry_later(lead_id)
            break

        _record_usage(lead_id, event, resp, model)
        ctx.api_ok = True

        if resp.stop_reason == "refusal":
            db.audit(lead_id, "agent", "refusal", str(getattr(resp, "stop_details", "")))
            db.update("leads", lead_id, {"needs_human": 1})
            break
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not tool_uses:
            note = " ".join(b.text for b in resp.content if b.type == "text").strip()
            if note:
                db.audit(lead_id, "agent", "note", note[:2000])
            break

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for tu in tool_uses:
            out, is_err = run_tool(ctx, tu.name, tu.input)
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out,
                            "is_error": is_err})
        messages.append({"role": "user", "content": results})
    return ctx


def last_run_ok(ctx: ToolContext) -> bool:
    return bool(getattr(ctx, "api_ok", False))


def _retry_later(lead_id: int) -> None:
    from datetime import timedelta
    when = get_settings().now() + timedelta(minutes=15)
    db.update("leads", lead_id, {"next_followup_at": when.isoformat(timespec="minutes"),
                                 "followup_purpose": "retry after API error"})


def _record_usage(lead_id: int, event: str, resp, model: str = "") -> None:
    u = getattr(resp, "usage", None)
    if not u:
        return
    db.insert("usage", {
        "lead_id": lead_id, "event": event, "model": model,
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "created_at": db.now_iso()})
