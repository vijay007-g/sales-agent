"""Which Claude model answers each AI turn.

The owner picks a preset (or a model per stage group) in Settings. Whatever is chosen, KEY MOMENTS always use the
top model: price/discount/booking/payment talk, complaints, post-visit strategy, management decisions, and hot buyers.
That keeps conversion quality where it matters and saves cost on routine follow-ups.
"""
from __future__ import annotations

import re

from .config import get_settings

TOP = "claude-opus-5-5"
MODELS = {
    # id: label, $ per 1M input / output / cache-read tokens, server-side refusal fallback supported
    "claude-opus-5-5": {"label": "Opus 5.5 — best quality", "in": 4.0, "out": 20.0, "cache": 0.20, "fallback": True},
    "claude-sonnet-5-5": {"label": "Sonnet 5.5 — very good, about half the cost", "in": 2.0, "out": 10.0,
                          "cache": 0.20, "fallback": True},
    "claude-haiku-5-5": {"label": "Haiku 5.5 — fast and cheapest, simpler replies", "in": 0.10, "out": 0.50,
                         "cache": 0.01, "fallback": False},
}
GROUPS = {
    "early": ("First contact & quiet buyers", ("new", "contacted")),
    "qualifying": ("Qualifying & visit booking", ("qualified", "visit_scheduled")),
    "closing": ("After the visit, negotiation & booking", ("visit_done", "negotiation", "booking_pending",
                                                          "payment_pending", "booked")),
    "nurture": ("Nurture (long-term quiet buyers)", ("nurture", "lost")),
}
PRESETS = {
    "best": ("Best quality — top model everywhere (recommended to start)",
             {"early": TOP, "qualifying": TOP, "closing": TOP, "nurture": TOP}),
    "balanced": ("Balanced — Sonnet for early stages and nurture, top model from qualifying onward",
                 {"early": "claude-sonnet-5-5", "qualifying": TOP, "closing": TOP, "nurture": "claude-sonnet-5-5"}),
    "economy": ("Economy — Haiku for first contact and nurture, Sonnet for qualifying, top model for closing",
                {"early": "claude-haiku-5-5", "qualifying": "claude-sonnet-5-5", "closing": TOP,
                 "nurture": "claude-haiku-5-5"}),
}
KEY_EVENTS = {"owner_decision", "booking_decision", "visit_outcome", "payment_received", "human_resumed"}
KEY_WORDS = re.compile(
    r"price|discount|offer|final|best rate|negotiat|book|advance|token|payment|paid|cost|emi|loan|lakh|\blac\b|"
    r"crore|\bcr\b|₹|deal|agree|cancel|refund|complain|unhappy|angry|legal|rera|lawyer|registration|agreement|"
    r"competitor|other project|cheaper|too high|expensive", re.I)


def top_model() -> str:
    m = get_settings().agent.get("model") or TOP
    return m if m in MODELS else TOP


def stage_models() -> dict:
    a = get_settings().agent
    preset = a.get("model_preset") or "best"
    chosen = dict(PRESETS.get(preset, PRESETS["best"])[1])
    if preset == "custom":
        chosen.update({k: v for k, v in (a.get("stage_models") or {}).items() if v in MODELS})
    return {k: (top_model() if v == TOP else v) for k, v in chosen.items()}


def group_of(stage: str) -> str:
    return next((g for g, (_, stages) in GROUPS.items() if stage in stages), "early")


def choose(lead: dict, event: str, detail: str = "") -> tuple[str, str]:
    """Returns (model id, reason)."""
    top = top_model()
    if event in KEY_EVENTS:
        return top, f"key moment: {event}"
    if (lead.get("temperature") or "") == "hot":
        return top, "hot buyer"
    if detail and KEY_WORDS.search(detail):
        return top, "price / booking / sensitive topic"
    group = group_of(lead.get("stage") or "new")
    return stage_models()[group], f"stage group: {group}"


def request_extras(model: str) -> dict:
    """Server-side refusal fallback where the model supports it."""
    if MODELS.get(model, {}).get("fallback"):
        return {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return {}


def cost_usd(model: str, inp: int, out: int, cache_read: int, cache_write: int) -> float:
    p = MODELS.get(model or TOP, MODELS[TOP])
    return (inp * p["in"] + out * p["out"] + cache_read * p["cache"] + cache_write * p["in"] * 1.25) / 1e6
