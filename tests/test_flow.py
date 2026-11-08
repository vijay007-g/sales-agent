"""End-to-end tests with a scripted fake Claude client (no API key needed)."""
from __future__ import annotations

import itertools
import json
import os
import sqlite3
from datetime import timedelta
from types import SimpleNamespace

import pytest

os.environ["SALESAGENT_SYNC"] = "1"
os.environ["CHANNEL_MODE"] = "console"
os.environ["DISABLE_SCHEDULER"] = "1"

from salesagent import (agent, channels, db, events, leads, learning, marketing, pipeline, prompts,  # noqa: E402
                        scheduler, team, tools, visits)
from salesagent.config import get_settings  # noqa: E402

_ids = itertools.count(1)


def tool_use(name, **inp):
    return SimpleNamespace(type="tool_use", id=f"tu_{next(_ids)}", name=name, input=inp)


def reply(*blocks, stop="tool_use"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


END = reply(SimpleNamespace(type="text", text="done"), stop="end_turn")


class FakeClient:
    """Each agent run consumes one 'script' = list of tool-call rounds. Structured-output calls
    (learning, campaigns) consume one queued JSON reply."""

    def __init__(self):
        self.scripts: list[list] = []
        self.json_replies: list[dict] = []
        self.calls: list[dict] = []
        self.briefings: list[str] = []
        self._current: list | None = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def queue(self, *rounds):
        self.scripts.append(list(rounds))

    def create(self, **kw):
        self.calls.append(kw)
        if "format" in kw.get("output_config", {}):
            return reply(SimpleNamespace(type="text", text=json.dumps(self.json_replies.pop(0))), stop="end_turn")
        if len(kw["messages"]) == 1:
            self.briefings.append(kw["messages"][0]["content"])
            self._current = self.scripts.pop(0) if self.scripts else []
        if self._current:
            return reply(*self._current.pop(0))
        return END

    def agent_briefings(self):
        return self.briefings


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("SALESAGENT_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr("salesagent.channels.DATA_DIR", tmp_path)
    db.reset_connection()
    for r in get_settings().sales_team:
        monkeypatch.setitem(r, "message_mode", "auto")
    fake = FakeClient()
    agent.set_client(fake)
    sent = []
    channels.CONSOLE_LISTENERS.clear()
    channels.CONSOLE_LISTENERS.append(lambda k, to, t: sent.append((to, t)))
    yield SimpleNamespace(fake=fake, sent=sent)
    channels.CONSOLE_LISTENERS.clear()


def owner_phone():
    return get_settings().owner["phone"]


def rm_phone():
    return get_settings().sales_team[0]["phone"]


def site_phone():
    return get_settings().site_persons[0]["phone"]


def to(fresh, phone):
    return [t for p, t in fresh.sent if p == phone]


def mk_lead(**kw):
    lead, _ = leads.upsert_lead({"name": "Asha", "phone": "9876543210", "source": "meta_ads", **kw})
    return lead


OFFER = dict(project="Sunrise Meadows", unit_type="3BHK", concessions=[], payment_terms="CLP",
             customer_ask=9600000, justification="ready to book this week")


# ------------------------------------------------------------------ lead capture & first contact

def test_new_lead_assigned_first_message_and_intro_call(fresh):
    lead = mk_lead()
    fresh.fake.queue([tool_use("send_message", text="Hi Asha, Anitha here from Sunrise. Got your enquiry!",
                               channel="whatsapp"),
                      tool_use("create_call_task", purpose="Intro call", minutes_from_now=10,
                               brief="New Meta lead, asked about 2BHK. Goal: understand budget + fix visit.")])
    events.new_lead(lead["id"])
    lead = db.get_lead(lead["id"])
    assert lead["rm_name"] == "Anitha" and lead["stage"] == "contacted"
    assert any("Anitha here" in t for t in to(fresh, lead["phone"]))
    rm_msgs = to(fresh, rm_phone())
    assert any("CALL C1" in t and "/s/" in t and "/lead/" in t and "fix visit" in t for t in rm_msgs)
    call = fresh.fake.calls[0]
    system = call["system"][0]["text"] + call["system"][1]["text"]
    for u in (u for p in get_settings().projects for u in p["units"]):
        assert str(u["floor_price"]) not in system           # floor prices never reach the model
    assert "This lead's salesperson: Anitha" in call["system"][1]["text"]
    assert "Sunrise Meadows" in call["system"][1]["text"]            # inventory summary
    assert "Skyline Realty's assistant" in call["system"][0]["text"]
    assert call["fallbacks"] == "default"


def test_dedupe_by_phone():
    a, created_a = leads.upsert_lead({"name": "A", "phone": "+91 98765 43210"})
    b, created_b = leads.upsert_lead({"phone": "9876543210", "email": "a@x.com"})
    assert created_a and not created_b and a["id"] == b["id"]
    assert db.get_lead(a["id"])["email"] == "a@x.com"


def test_review_mode_drafts_go_to_salesperson(fresh, monkeypatch):
    monkeypatch.setitem(get_settings().sales_team[0], "message_mode", "review")
    lead = mk_lead()
    ctx = tools.ToolContext(lead_id=lead["id"], event="t")
    out, err = tools.run_tool(ctx, "send_message", {"text": "Hi Asha!", "channel": "whatsapp"})
    assert not err and "drafted_for_review" in out
    assert to(fresh, lead["phone"]) == []                       # nothing sent yet
    assert any("DRAFT D1" in t for t in to(fresh, rm_phone()))
    reply_text = events.staff_command(rm_phone(), "EDIT D1 Hi Asha, Anitha this side 🙂")
    assert "Sent D1" in reply_text
    assert to(fresh, lead["phone"]) == ["Hi Asha, Anitha this side 🙂"]
    assert db.q1("SELECT * FROM audit WHERE action = 'draft_edited'")    # learning signal recorded


# ------------------------------------------------------------------ calls

def test_call_logged_wakes_agent_with_notes(fresh):
    lead = mk_lead()
    team.assign_rm(lead["id"])
    t = team.create_call_task(lead["id"], "Intro call", 10, "brief")
    fresh.fake.queue([tool_use("send_message", text="Lovely speaking with you Asha! As discussed...",
                               channel="whatsapp")])
    msg = events.staff_command(rm_phone(), f"CALLED C{t['task_id']} wants east facing 2BHK, visit Sat 11am")
    assert "logged" in msg
    assert db.q1("SELECT status FROM call_tasks WHERE id = ?", (t["task_id"],))["status"] == "done"
    assert "east facing" in fresh.fake.agent_briefings()[-1]
    assert db.q1("SELECT * FROM interactions WHERE direction = 'call'")["content"].startswith("[CALL spoke]")
    assert "PHONE CALL by Anitha" in prompts.lead_briefing(lead["id"], "x", "y")


def test_call_form_no_login(fresh):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    lead = mk_lead()
    t = team.create_call_task(lead["id"], "Intro call", 10, "brief text")
    token = db.q1("SELECT form_token FROM call_tasks WHERE id = ?", (t["task_id"],))["form_token"]
    with TestClient(app) as c:
        assert "brief text" in c.get(f"/f/call/{token}").text
        r = c.post(f"/f/call/{token}", data={"outcome": "no_answer", "summary": "rang twice"})
        assert r.status_code == 200
        assert c.get("/f/call/not-a-token").status_code == 404
    assert db.q1("SELECT status FROM call_tasks WHERE id = ?", (t["task_id"],))["status"] == "attempted"
    assert "outcome: no_answer" in fresh.fake.agent_briefings()[-1]


def test_fallback_call_task_when_agent_forgets(fresh):
    lead = mk_lead()
    pipeline.move(lead["id"], "contacted", "system")
    fresh.fake.queue([tool_use("send_message", text="Hello", channel="whatsapp")])
    events.inbound_message(lead["phone"], None, "what's the price of 2BHK?", "whatsapp")
    task = db.q1("SELECT * FROM call_tasks WHERE lead_id = ?", (lead["id"],))
    assert task and task["status"] == "open"


# ------------------------------------------------------------------ site visit -> strategy

def test_site_visit_report_form_drives_strategy(fresh):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    lead = mk_lead()
    pipeline.move(lead["id"], "qualified", "system")
    tomorrow = (get_settings().now() + timedelta(days=1)).date().isoformat()
    slots = visits.free_slots("Sunrise Meadows", tomorrow)
    fresh.fake.queue([tool_use("book_site_visit", project="Sunrise Meadows", datetime=slots[0]["time"],
                               notes_for_site_person="wants east facing")])
    events.inbound_message(lead["phone"], None, "tomorrow works", "whatsapp")
    v = db.q1("SELECT * FROM site_visits WHERE lead_id = ?", (lead["id"],))
    assert v["status"] == "scheduled" and db.get_lead(lead["id"])["stage"] == "visit_scheduled"
    assert any(f"/f/visit/{v['form_token']}" in t for t in to(fresh, site_phone()))
    assert slots[0]["time"] not in [x["time"] for x in visits.free_slots("Sunrise Meadows", tomorrow)]

    fresh.fake.queue([
        tool_use("save_conversion_strategy", situation="Loved it, price worry", buying_motivators=["school nearby"],
                 objections_and_answers=["traffic -> new flyover"], recommended_unit="2BHK east, 5th floor",
                 decision_maker_and_influencers="wife decides", price_plan="hold list; ask docs waiver if booking "
                 "this week", next_actions=["call today 6pm", "revisit with parents Sat"], risk="competitor X"),
        tool_use("send_message", text="Thanks for coming today!", channel="whatsapp"),
        tool_use("create_call_task", purpose="Post-visit call", minutes_from_now=90, brief="follow strategy")])
    with TestClient(app) as c:
        page = c.get(f"/f/visit/{v['form_token']}")
        assert "Concerns / objections raised" in page.text
        c.post(f"/f/visit/{v['form_token']}", data={
            "attended": "yes", "visitors": "Asha + husband", "unit_liked": "2BHK east 5th floor",
            "concerns": "worried about OMR traffic", "specific_requirements": "needs vastu, 2 parkings",
            "interest": "hot", "price_reaction": "slightly high"})
        assert "already" in c.get(f"/f/visit/{v['form_token']}").text
    lead = db.get_lead(lead["id"])
    assert lead["stage"] == "visit_done" and lead["temperature"] == "hot"
    brief = fresh.fake.agent_briefings()[-1]
    assert "worried about OMR traffic" in brief and "save_conversion_strategy" in brief
    assert json.loads(lead["strategy"])["recommended_unit"].startswith("2BHK")
    assert any(t.startswith("STRATEGY for Asha") for t in to(fresh, rm_phone()))
    assert "conversion_strategy" in prompts.lead_briefing(lead["id"], "x", "y")


# ------------------------------------------------------------------ negotiation

def test_every_discount_needs_approval_and_area_is_fixed(fresh):
    lead = mk_lead()
    pipeline.move(lead["id"], "contacted", "system")
    ctx = tools.ToolContext(lead_id=lead["id"], event="test")
    base = {**OFFER, "unit_type": "2BHK"}
    out, _ = tools.run_tool(ctx, "propose_offer", {**base, "offered_price": 7490000})   # even 0.1% off
    assert '"pending_approval"' in out
    assert any("APPROVAL NEEDED" in t for t in to(fresh, owner_phone()))
    out, _ = tools.run_tool(ctx, "propose_offer", {**base, "offered_price": 6500000})   # below floor
    assert '"blocked_floor"' in out
    out, err = tools.run_tool(ctx, "propose_offer", {**base, "offered_price": 7500000,
                                                     "concessions": ["Extra 50 sqft"]})
    assert err and "area is fixed" in out.lower()
    out, _ = tools.run_tool(ctx, "propose_offer", {**base, "offered_price": 7500000,
                                                   "concessions": ["Free car parking"]})
    assert '"pending_approval"' in out
    assert db.get_lead(lead["id"])["stage"] == "negotiation"


def test_agent_cannot_set_system_stages():
    lead = mk_lead()
    ctx = tools.ToolContext(lead_id=lead["id"], event="t")
    for st in ("booked", "payment_pending", "visit_done"):
        with pytest.raises(pipeline.StageError):
            pipeline.move(lead["id"], st, "agent")
    out, is_err = tools.run_tool(ctx, "set_stage", {"stage": "booked", "reason": "x"})
    assert is_err


# ------------------------------------------------------------------ booking -> advance -> booked

def test_full_close_offer_booking_payment(fresh):
    lead = mk_lead()
    pipeline.move(lead["id"], "qualified", "system")
    ctx = tools.ToolContext(lead_id=lead["id"], event="test")
    tools.run_tool(ctx, "propose_offer", {**OFFER, "offered_price": 9800000})
    offer = db.q1("SELECT * FROM offers WHERE lead_id = ?", (lead["id"],))
    _, is_err = tools.run_tool(ctx, "request_booking_confirmation",
                               {"offer_id": offer["id"], "token_amount": 0, "notes": ""})
    assert is_err                                                 # not approved yet

    fresh.fake.queue([tool_use("create_call_task", purpose="Present offer", minutes_from_now=30, brief="97.5L final"),
                      tool_use("send_message", text="As discussed, 97.5L is approved.", channel="whatsapp")])
    assert "countered" in events.staff_command(owner_phone(), f"COUNTER {offer['id']} 97.5L if advance this week")
    assert "COUNTERED" in fresh.fake.agent_briefings()[-1]

    fresh.fake.queue([tool_use("request_booking_confirmation", offer_id=offer["id"], token_amount=0,
                               notes="agreed on call")])
    events.inbound_message(lead["phone"], None, "Okay we'll go ahead", "whatsapp")
    booking = db.q1("SELECT * FROM bookings WHERE lead_id = ?", (lead["id"],))
    assert booking["token_amount"] == get_settings().booking["advance_amount"]
    assert db.get_lead(lead["id"])["stage"] == "booking_pending"

    # payment details can't be shared before management confirms
    out, is_err = tools.run_tool(ctx, "share_payment_details", {"booking_id": booking["id"]})
    assert is_err

    tomorrow = (get_settings().now() + timedelta(days=1))
    while tomorrow.weekday() not in get_settings().booking["office_days"]:
        tomorrow += timedelta(days=1)
    slot = visits.office_slots(tomorrow.date().isoformat())[0]
    fresh.fake.queue([tool_use("share_payment_details", booking_id=booking["id"]),
                      tool_use("book_office_visit", datetime=slot, purpose="Pay advance + sign")])
    events.staff_command(owner_phone(), f"CONFIRM B{booking['id']}")
    assert db.get_lead(lead["id"])["stage"] == "payment_pending"
    acct = get_settings().booking["account_number"]
    assert any(acct in t and f"Booking B{booking['id']}" in t for t in to(fresh, lead["phone"]))
    assert any(f"OFFICE VISIT" in t for t in to(fresh, owner_phone()))

    events.inbound_message(lead["phone"], None, "Transferred, UTR 1234", "whatsapp")
    assert any("Verify in the bank" in t for t in to(fresh, owner_phone()))
    assert db.get_lead(lead["id"])["stage"] == "payment_pending"   # customer saying so is not enough

    fresh.fake.queue([tool_use("send_message", text="Congratulations!", channel="whatsapp")])
    assert "BOOKED" in events.staff_command(owner_phone(), f"PAID B{booking['id']} 2L UTR1234")
    assert db.get_lead(lead["id"])["stage"] == "booked"
    b = db.q1("SELECT * FROM bookings WHERE id = ?", (booking["id"],))
    assert b["status"] == "paid" and b["amount_paid"] == 200000 and b["payment_ref"] == "UTR1234"


# ------------------------------------------------------------------ safety

def test_stop_keyword_opts_out_without_llm(fresh):
    lead = mk_lead()
    events.inbound_message(lead["phone"], None, "STOP", "whatsapp")
    lead = db.get_lead(lead["id"])
    assert lead["opted_out"] == 1 and lead["stage"] == "lost"
    assert fresh.fake.calls == []
    ctx = tools.ToolContext(lead_id=lead["id"], event="t")
    _, is_err = tools.run_tool(ctx, "send_message", {"text": "hello?", "channel": "whatsapp"})
    assert is_err


def test_message_cap_per_turn():
    lead = mk_lead()
    ctx = tools.ToolContext(lead_id=lead["id"], event="t")
    results = [tools.run_tool(ctx, "send_message", {"text": f"m{i}", "channel": "whatsapp"})[1] for i in range(4)]
    assert results == [False, False, False, True]


def test_non_staff_cannot_run_commands():
    lead = mk_lead()
    assert events.staff_command(lead["phone"], "APPROVE 1") is None
    # a salesperson can't approve prices
    assert "Commands" in events.staff_command(rm_phone(), "APPROVE 1")


def test_escalation_pauses_agent(fresh):
    lead = mk_lead()
    fresh.fake.queue([tool_use("escalate_to_human", reason="wants refund", urgency="high")])
    events.inbound_message(lead["phone"], None, "I want my refund NOW", "whatsapp")
    assert db.get_lead(lead["id"])["needs_human"] == 1
    n = len(fresh.fake.calls)
    events.inbound_message(lead["phone"], None, "hello??", "whatsapp")
    assert len(fresh.fake.calls) == n
    assert any("wrote: hello??" in t for t in to(fresh, rm_phone()))


# ------------------------------------------------------------------ scheduler

def test_scheduler_followups_and_call_alerts(fresh, monkeypatch):
    lead = mk_lead()
    team.assign_rm(lead["id"])
    past = (get_settings().now() - timedelta(minutes=5)).isoformat()
    db.update("leads", lead["id"], {"next_followup_at": past, "stage": "contacted"})
    t = team.create_call_task(lead["id"], "Check in", 24 * 60, "brief")      # not notified yet (far future)
    db.update("call_tasks", t["task_id"], {"due_at": (get_settings().now() + timedelta(minutes=10)).isoformat()})
    monkeypatch.setattr(scheduler, "in_quiet_hours", lambda now=None: False)
    fresh.fake.queue([tool_use("send_message", text="Just checking in", channel="whatsapp")])
    stats = scheduler.tick()
    assert stats["followups"] == 1
    assert db.get_lead(lead["id"])["followup_attempts"] == 1
    assert any(f"CALL C{t['task_id']}" in m for m in to(fresh, rm_phone()))
    db.update("call_tasks", t["task_id"], {"due_at": (get_settings().now() - timedelta(hours=4)).isoformat()})
    scheduler.tick()
    assert any("quick win" in m for m in to(fresh, rm_phone()))                   # 1st positive nudge
    scheduler.tick()
    assert any("far more likely" in m for m in to(fresh, rm_phone()))             # 2nd nudge
    assert not any("Call not done" in m for m in to(fresh, owner_phone()))
    scheduler.tick()
    assert any("Call not done for 3+ hours" in m for m in to(fresh, owner_phone()))   # management told
    n = len(fresh.sent)
    scheduler.tick()
    assert not any("Call not done" in t for _, t in fresh.sent[n:])               # only once


# ------------------------------------------------------------------ learning + campaigns

PLAYBOOK = {
    "summary": "Same-day post-visit calls win.", "what_works_in_messages": ["mention the school"],
    "what_works_on_calls": ["call within 2h of visit"],
    "objection_playbook": [{"objection": "traffic", "best_response": "flyover", "evidence": "3 wins"}],
    "best_converting_profiles": ["IT couples 28-35"], "lead_source_verdicts": [],
    "follow_up_insights": ["day 2 call"], "rm_tone_preferences": ["shorter"], "things_to_stop": ["long messages"],
    "creative_campaign_ideas": [{"angle": "walk to work", "audience": "IT park", "hook": "5 min", "why_it_should_work": "x"}],
    "experiments_to_run": ["A/B school angle"],
}


def test_learning_builds_playbook_used_by_agent(fresh):
    for i, stage in enumerate(["booked", "lost", "lost"]):
        lead, _ = leads.upsert_lead({"name": f"L{i}", "phone": f"90000000{i:02d}", "source": "meta_ads"})
        db.update("leads", lead["id"], {"stage": stage})
        db.log_interaction(lead["id"], "in", "whatsapp", "customer", f"message {i}")
    assert learning.due()
    fresh.fake.json_replies.append(PLAYBOOK)
    assert learning.learn()["summary"].startswith("Same-day")
    sent_prompt = fresh.fake.calls[-1]["messages"][0]["content"]
    assert "message 0" in sent_prompt and "funnel_by_campaign" in sent_prompt
    assert not learning.due()
    persona = prompts.persona_and_playbook(get_settings().sales_team[0])
    assert "call within 2h of visit" in persona


def test_campaign_uses_playbook_and_tracking_codes(fresh):
    db.insert("insights", {"kind": "playbook", "content": json.dumps(PLAYBOOK), "based_on": 3,
                           "created_at": db.now_iso()})
    fresh.fake.json_replies.append({
        "campaign_name": "Walk to work", "target_personas": [], "lead_form_questions": ["Budget?"],
        "ad_variants": [{"headline": f"H{i}", "primary_text": "t", "call_to_action": "c", "creative_idea": "i"}
                        for i in range(3)],
        "whatsapp_template": "w", "social_posts": [], "landing_page": {"hero": "h", "sub": "s", "sections": []},
        "big_creative_ideas": [], "two_week_content_calendar": [], "referral_offer_idea": "r",
        "budget_split_advice": "b", "compliance_notes": "c"})
    data = marketing.generate_campaign("Sunrise Meadows", "Meta lead ads")
    assert [a["tracking_code"] for a in data["ad_variants"]] == ["C1-V1", "C1-V2", "C1-V3"]
    assert "walk to work" in fresh.fake.calls[-1]["messages"][0]["content"]
    assert "6900000" not in fresh.fake.calls[-1]["messages"][0]["content"]


# ------------------------------------------------------------------ web + misc

def test_lead_webhook(monkeypatch, fresh):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("LEAD_WEBHOOK_SECRET", "s3")
    fresh.fake.queue([tool_use("send_message", text="Hello from Anitha", channel="whatsapp")])
    with TestClient(app) as c:
        assert c.post("/webhook/lead", json={"phone": "9000000001"}).status_code == 401
        r = c.post("/webhook/lead", headers={"X-Webhook-Secret": "s3"},
                   json={"name": "Web Lead", "phone": "9000000001", "source": "website", "budget_max": "8000000",
                         "campaign": "C1-V2"})
        assert r.status_code == 200 and r.json()["created"]
    lead = db.get_lead(r.json()["lead_id"])
    assert lead["stage"] == "contacted" and lead["campaign"] == "C1-V2" and lead["rm_name"] == "Anitha"


def test_dashboard_pages(monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    lead = mk_lead()
    team.create_call_task(lead["id"], "Intro", 10, "b")
    with TestClient(app) as c:
        assert c.get("/").status_code == 401
        for path in ("/", "/leads", f"/leads/{lead['id']}", "/calls", "/visits", "/campaigns", "/insights",
                     "/reports"):
            assert c.get(path, auth=("owner", "pw")).status_code == 200, path


def test_parse_amount():
    assert events.parse_amount("72L") == 7200000
    assert events.parse_amount("1.02cr") == 10200000
    assert events.parse_amount("7,200,000") == 7200000
    assert events.parse_amount("abc") is None


def test_migrates_old_database(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT)")
    c.commit()
    c.close()
    monkeypatch.setenv("SALESAGENT_DB", str(path))
    db.reset_connection()
    cols = {r[1] for r in db.conn().execute("PRAGMA table_info(leads)")}
    assert {"rm_name", "strategy", "stage", "memory"} <= cols


# ------------------------------------------------------------------ cloud: settings + test mode

def test_settings_page_validates_and_saves(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent import config
    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("SALESAGENT_CONFIG", str(tmp_path / "cfg.yaml"))
    text = open(config.ROOT / "config.example.yaml").read()
    try:
        with TestClient(app) as c:
            bad = c.post("/settings/advanced", auth=("owner", "pw"), data={"config": "business: x"})
            assert "Not saved" in bad.text and not (tmp_path / "cfg.yaml").exists()
            worse = c.post("/settings/advanced", auth=("owner", "pw"),
                           data={"config": text.replace("floor_price: 6900000", "floor_price: 99000000")})
            assert "floor price is above list price" in worse.text
            ok = c.post("/settings/advanced", auth=("owner", "pw"),
                        data={"config": text.replace('name: "Skyline Realty"', 'name: "Vijay Homes"')})
            assert ok.status_code == 200 and (tmp_path / "cfg.yaml").exists()
            assert get_settings().business["name"] == "Vijay Homes"
    finally:
        monkeypatch.delenv("SALESAGENT_CONFIG")
        config.reload_settings()


def test_test_mode_from_browser(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    fresh.fake.queue([tool_use("send_message", text="Hi Ravi, Anitha here!", channel="whatsapp")])
    fresh.fake.queue([tool_use("send_message", text="Sure, Saturday works.", channel="whatsapp")])
    with TestClient(app) as c:
        r = c.post("/test/new", auth=("owner", "pw"), data={"name": "Ravi", "source": "website"})
        lead_page = r.text
        assert "TEST MODE" in lead_page and "Send as customer" in lead_page and "Hi Ravi" in lead_page
        lead = db.q1("SELECT * FROM leads WHERE campaign = 'test'")
        c.post(f"/test/{lead['id']}/customer", auth=("owner", "pw"), data={"text": "Can I visit Saturday?"})
        assert "Can I visit Saturday?" in fresh.fake.agent_briefings()[-1]
        out = c.post(f"/test/{lead['id']}/command", auth=("owner", "pw"), data={"role": "owner", "text": "STATUS"})
        assert "Pipeline" in out.text
        assert "Anitha here" in c.get("/test/outbox", auth=("owner", "pw")).text
        assert c.get("/manifest.json").json()["display"] == "standalone"


def _form_data(**over):
    d = {
        "business[name]": "Vijay Homes", "business[legal_name]": "Tiruana Private Limited",
        "business[rera_by_city]": "Chennai: TN/Agent/1 (Vijay)\nBangalore: KA/Agent/2 (Wife)", "business[website]": "", "business[languages]": "English, Tamil",
        "business[timezone]": "Asia/Kolkata", "business[currency]": "INR",
        "owner[name]": "Vijay", "owner[phone]": "98765 00000", "owner[email]": "",
        "sales_team[0][name]": "Priya", "sales_team[0][phone]": "+91 98765 11111",
        "sales_team[0][message_mode]": "review", "sales_team[0][languages]": "Tamil, English",
        "sales_team[0][max_active_leads]": "50", "sales_team[0][whatsapp_phone_number_id]": "",
        "sales_team[0][style]": "Friendly",
        "sales_team[n1][name]": "", "sales_team[n1][phone]": "",          # empty added row is ignored
        "site_persons[0][name]": "Kumar", "site_persons[0][phone]": "9876522222",
        "site_persons[0][projects]": "Sunrise Meadows", "site_persons[0][visit_hours][from]": "09:30",
        "site_persons[0][visit_hours][to]": "17:30", "site_persons[0][max_visits_per_day]": "5",
        "site_persons[0][working_days][]": ["0", "1", "2", "3", "4", "5"],
        "projects[0][name]": "Green Park", "projects[0][location]": "Porur, Chennai", "projects[0][type]": "Villas",
        "projects[0][status]": "Ready", "projects[0][rera]": "TN/1", "projects[0][highlights]": "Near metro\nPark",
        "projects[0][payment_plans]": "Bank loans", "projects[0][approval_concessions]": "Free parking",
        "projects[0][free_concessions]": "",
        "projects[0][units][0][type]": "3BHK Villa", "projects[0][units][0][size_sqft]": "1800",
        "projects[0][units][0][carpet_sqft]": "1400", "projects[0][units][0][list_price]": "1.2cr",
        "projects[0][units][0][floor_price]": "110L", "projects[0][units][0][available]": "4",
        "projects[0][units][0][auto_approve_discount_pct]": "0",
        "booking[advance_amount]": "3L", "booking[payee_name]": "Vijay Homes Pvt Ltd", "booking[bank_name]": "SBI",
        "booking[account_number]": "1234567890", "booking[ifsc]": "sbin0000001", "booking[upi_id]": "",
        "booking[verify_phone]": "", "booking[office_address]": "Anna Nagar",
        "booking[office_hours][from]": "10:00", "booking[office_hours][to]": "18:00",
        "booking[office_visit_slots_per_hour]": "2", "booking[office_days][]": ["0", "1", "2", "3", "4", "5"],
        "messaging[quiet_hours][from]": "21:00", "messaging[quiet_hours][to]": "09:00",
    }
    d.update(over)
    return d


def test_settings_form_round_trip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent import config
    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("SALESAGENT_CONFIG", str(tmp_path / "cfg.yaml"))
    config.reload_settings()
    try:
        with TestClient(app) as c:
            page_html = c.get("/settings", auth=("owner", "pw")).text
            assert "Brand name" in page_html and "Registered firm" in page_html and "Add salesperson" in page_html
            bad = c.post("/settings", auth=("owner", "pw"),
                         data=_form_data(**{"projects[0][units][0][floor_price]": "2cr",
                                            "site_persons[0][projects]": "Grn Park",
                                            "owner[phone]": "123"}))
            assert "Not saved" in bad.text
            assert "Grn Park" in bad.text and "look like a full phone number" in bad.text
            assert 'value="Grn Park"' in bad.text and not (tmp_path / "cfg.yaml").exists()   # input kept
            r = c.post("/settings", auth=("owner", "pw"), data=_form_data())
            assert r.status_code == 200 and "Saved" in r.text
        s = get_settings()
        assert s.business["name"] == "Vijay Homes" and s.owner["phone"] == "+919876500000"
        assert s.business["legal_name"] == "Tiruana Private Limited" and "KA/Agent/2" in s.business["rera_by_city"]
        from salesagent.config import rera_for
        assert rera_for("Bangalore") == "KA/Agent/2 (Wife)" and rera_for("chennai") == "TN/Agent/1 (Vijay)"
        assert "TN/Agent/1" in rera_for(None) and "KA/Agent/2" in rera_for(None)
        assert [t["name"] for t in s.sales_team] == ["Priya"]
        assert s.booking["advance_amount"] == 300000 and s.booking["ifsc"] == "SBIN0000001"
        assert s.site_persons[0]["visit_hours"] == ["09:30", "17:30"] and 6 not in s.site_persons[0]["working_days"]
        assert s.followups  # sections not on the form are kept
        assert "6900000" not in prompts.system_prompt()
    finally:
        monkeypatch.delenv("SALESAGENT_CONFIG")
        config.reload_settings()


def test_login_tolerates_spaces_and_reports_which_part(monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "Sunrise2026Sales")
    with TestClient(app) as c:
        assert c.get("/", auth=(" Owner ", "Sunrise2026Sales\n")).status_code == 200
        assert c.get("/", auth=("anything", "Sunrise2026Sales")).status_code == 200
        assert c.get("/", auth=("owner", "nope")).json()["detail"] == "Wrong password"
        assert c.get("/", auth=("Sunrise2026Sales", "owner")).status_code == 200   # boxes swapped


def test_drafts_show_on_lead_page_and_send_from_there(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    monkeypatch.setitem(get_settings().sales_team[0], "message_mode", "review")
    lead = mk_lead()
    team.send_or_draft(lead["id"], "Hi Asha, Anitha here!")
    with TestClient(app) as c:
        page = c.get(f"/leads/{lead['id']}", auth=("owner", "pw")).text
        assert "DRAFT D1" in page and "Hi Asha, Anitha here!" in page
        assert page.index("you play the customer") < page.index("Message the customer yourself")
        r = c.post("/drafts/1", auth=("owner", "pw"),
                   data={"action": "send", "text": "Hi Asha, Anitha here!", "back": f"/leads/{lead['id']}"})
        assert r.url.path == f"/leads/{lead['id']}" and "DRAFT D1" not in r.text
    assert to(fresh, lead["phone"]) == ["Hi Asha, Anitha here!"]


def test_new_event_withdraws_stale_drafts(fresh, monkeypatch):
    monkeypatch.setitem(get_settings().sales_team[0], "message_mode", "review")
    lead = mk_lead()
    team.assign_rm(lead["id"])
    team.send_or_draft(lead["id"], "I'll call you in 5 mins. What's your name?")
    t = team.create_call_task(lead["id"], "Intro", 10, "b")
    fresh.fake.queue([tool_use("send_message", text="Great speaking with you!", channel="whatsapp")])
    events.staff_command(rm_phone(), f"CALLED C{t['task_id']} spoke, name is Asha")
    assert db.q1("SELECT status FROM drafts WHERE id = 1")["status"] == "superseded"
    assert "never sent" in fresh.fake.agent_briefings()[-1] and "What's your name?" in fresh.fake.agent_briefings()[-1]
    assert "already" in events.staff_command(rm_phone(), "SEND D1") or "not pending" in events.staff_command(rm_phone(), "SEND D1")
    assert db.q1("SELECT status FROM drafts WHERE id = 2")["status"] == "pending"   # the fresh one


def test_unchanged_draft_is_not_counted_as_edit(fresh, monkeypatch):
    monkeypatch.setitem(get_settings().sales_team[0], "message_mode", "review")
    lead = mk_lead()
    team.send_or_draft(lead["id"], "Line one\nLine two")
    team.approve_draft(1, "Line one\r\nLine two  ")
    assert db.q1("SELECT status FROM drafts WHERE id = 1")["status"] == "sent"
    assert not db.q1("SELECT id FROM audit WHERE action = 'draft_edited'")


def test_bare_small_numbers_are_lakhs():
    assert events.parse_amount("95") == 9500000
    assert events.parse_amount("97.5") == 9750000
    assert events.parse_amount("80 lakhs") == 8000000
    assert events.parse_amount("2 crores") == 20000000
    assert events.parse_amount("200000") == 200000


# ------------------------------------------------------------------ channel partner: inventory, matchmaker, registration, commission

BUILDER_PHONE = "+919811100000"
HOST_PHONE = "+919811100001"


def _partner_setup():
    from salesagent import inventory
    bid = db.insert("builders", {"name": "Lakeside Partner", "is_own": 0, "contact_name": "Suresh",
                                 "contact_phone": BUILDER_PHONE, "contact_email": "crm@partner.example",
                                 "commission_type": "pct", "commission_value": 2, "payment_terms_days": 30,
                                 "registration_validity_days": 90, "bank_payee": "Lakeside Partner Pvt Ltd",
                                 "bank_name": "ICICI", "bank_account": "999888777", "bank_ifsc": "ICIC0000999",
                                 "verify_phone": "+918000000000", "created_at": db.now_iso()})
    pid = db.insert("inv_projects", {"builder_id": bid, "name": "Lakeview Heights", "city": "Bangalore",
                                     "locality": "Whitefield", "type": "Apartments", "status": "Ready to move",
                                     "possession": "Ready", "rera": "KA/1", "highlights": "Near ITPL\nLake view",
                                     "payment_plans": "Bank loans", "approval_concessions": "Free parking",
                                     "site_host_name": "Manju", "site_host_phone": HOST_PHONE,
                                     "visit_hours": "10:00-18:00", "visit_days": "0,1,2,3,4,5,6",
                                     "max_visits_per_day": 6, "active": 1, "created_at": db.now_iso()})
    for no, price, floor in (("A-101", 8800000, 8200000), ("A-502", 9200000, 8600000), ("B-1201", 9900000, 9300000)):
        db.insert("units", {"project_id": pid, "unit_no": no, "unit_type": "2BHK", "floor": no.split("-")[1][:-2],
                            "facing": "East", "size_sqft": 1200, "list_price": price, "floor_price": floor,
                            "quantity": 1, "status": "available"})
    return inventory.get_project(pid)


def test_inventory_seeded_from_settings_and_type_level_stock():
    from salesagent import inventory
    p = inventory.get_project("Sunrise Meadows")
    assert p and p["is_own"] and p["city"] == "Chennai"
    t = {x["type"]: x for x in inventory.type_summary(p["id"])}
    assert t["2BHK"]["available"] == 18 and t["2BHK"]["price_min"] == 7500000
    u = inventory.find_unit(p, "2BHK")
    inventory.mark_booked(u["id"])
    assert {x["type"]: x for x in inventory.type_summary(p["id"])}["2BHK"]["available"] == 17


def test_matchmaker_search_across_cities_without_floor_prices(fresh):
    _partner_setup()
    lead = mk_lead(city="Bangalore", budget_max="95L")
    ctx = tools.ToolContext(lead_id=lead["id"], event="t")
    out = json.loads(tools.run_tool(ctx, "search_properties", {"unit_type": "2BHK"})[0])
    projects = {m["project"] for m in out["matches"]}
    assert projects == {"Lakeview Heights"}                         # city filter from the lead
    assert out["matches"][0]["unit_no"] == "A-502"                  # closest under the 95L budget first
    assert all(m["list_price"] <= 9500000 * 1.1 for m in out["matches"])
    assert "8600000" not in json.dumps(out) and "floor_price" not in json.dumps(out)
    details = json.loads(tools.run_tool(ctx, "get_project_details", {"project": "lakeview"})[0])
    assert details["builder"] == "Lakeside Partner" and len(details["available_units"]) == 3
    assert "8200000" not in json.dumps(details)
    none = json.loads(tools.run_tool(ctx, "search_properties", {"city": "Pune"})[0])
    assert none["matches"] == [] and "Bangalore" in none["cities_we_cover"]
    assert "Lakeview Heights" in prompts.persona_and_playbook(get_settings().sales_team[0])
    assert "8200000" not in prompts.persona_and_playbook(get_settings().sales_team[0])


def test_city_routing_assigns_city_salesperson(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "raw", {**s.raw, "sales_team": [
        {"name": "Anitha", "phone": "+919800000010", "cities": ["Chennai"]},
        {"name": "Kiran", "phone": "+919800000020", "cities": ["Bangalore"]}]})
    blr = mk_lead(city="Bangalore")
    assert team.assign_rm(blr["id"])["name"] == "Kiran"
    lead2, _ = leads.upsert_lead({"name": "C", "phone": "9000011111", "city": "Chennai"})
    assert team.assign_rm(lead2["id"])["name"] == "Anitha"


def test_partner_visit_registers_client_and_builder_ack(fresh):
    p = _partner_setup()
    lead = mk_lead(city="Bangalore")
    pipeline.move(lead["id"], "qualified", "system")
    tomorrow = (get_settings().now() + timedelta(days=1)).date().isoformat()
    slots = visits.free_slots("Lakeview Heights", tomorrow)
    assert slots and slots[0]["site_person"] == "Manju"
    res = visits.book(lead["id"], "Lakeview Heights", slots[0]["time"], "wants high floor")
    assert res["ok"] and "registered with the builder" in res["partner_project"]
    reg = db.q1("SELECT * FROM registrations WHERE lead_id = ?", (lead["id"],))
    assert reg["status"] == "sent" and reg["project_id"] == p["id"]
    assert any(f"CLIENT REGISTRATION R{reg['id']}" in t and "Asha" in t for t in to(fresh, BUILDER_PHONE))
    assert any("crm@partner.example" == to_ for to_, _t in fresh.sent)          # emailed too
    assert any("NEW SITE VISIT" in t for t in to(fresh, HOST_PHONE))            # builder's site staff hosts it
    # registering again for the same project doesn't spam the builder
    assert visits and __import__("salesagent.partners", fromlist=["x"]).register_client(lead["id"], p["id"])["already"]
    # builder confirms
    assert "confirmed" in events.staff_command(BUILDER_PHONE, f"ACK R{reg['id']}")
    assert db.q1("SELECT status FROM registrations WHERE id = ?", (reg["id"],))["status"] == "acknowledged"
    # builder chatter is not turned into a customer lead
    assert "ACK R" in events.staff_command(BUILDER_PHONE, "hello, call me")
    # builder's site staff can submit the visit outcome
    v = db.q1("SELECT id FROM site_visits WHERE lead_id = ?", (lead["id"],))
    fresh.fake.queue([tool_use("send_message", text="Thanks for visiting Lakeview!", channel="whatsapp")])
    assert "recorded" in events.staff_command(HOST_PHONE, f"VISITED {v['id']} hot liked A-502")


def test_builder_dispute_alerts_owner(fresh):
    from salesagent import partners
    p = _partner_setup()
    lead = mk_lead(city="Bangalore")
    r = partners.register_client(lead["id"], p["id"])
    reply = events.staff_command(BUILDER_PHONE, f"DISPUTE R{r['registration_id']} already visited us directly")
    assert "disputed" in reply
    assert any("DISPUTED registration" in t for t in to(fresh, owner_phone()))
    assert events.staff_command("+919812345678", f"ACK R{r['registration_id']}") is None   # strangers can't ACK


def test_partner_booking_pays_builder_and_records_commission(fresh):
    p = _partner_setup()
    lead = mk_lead(city="Bangalore")
    pipeline.move(lead["id"], "qualified", "system")
    ctx = tools.ToolContext(lead_id=lead["id"], event="t")
    out, _ = tools.run_tool(ctx, "propose_offer", {**OFFER, "project": "Lakeview Heights", "unit_type": "2BHK",
                                                   "unit_no": "A-502", "offered_price": 9000000})
    assert '"pending_approval"' in out
    assert any("your commission at this price" in t for t in to(fresh, owner_phone()))
    offer = db.q1("SELECT * FROM offers WHERE lead_id = ?", (lead["id"],))
    unit = db.q1("SELECT * FROM units WHERE unit_no = 'A-502'")
    assert offer["unit_id"] == unit["id"]
    fresh.fake.queue([tool_use("send_message", text="Approved!", channel="whatsapp")])
    events.staff_command(owner_phone(), f"APPROVE {offer['id']}")
    tools.run_tool(ctx, "request_booking_confirmation", {"offer_id": offer["id"], "token_amount": 0, "notes": "ok"})
    booking = db.q1("SELECT * FROM bookings WHERE lead_id = ?", (lead["id"],))
    assert booking["unit_id"] == unit["id"]
    fresh.fake.queue([tool_use("share_payment_details", booking_id=booking["id"])])
    events.staff_command(owner_phone(), f"CONFIRM B{booking['id']}")
    assert db.q1("SELECT status FROM units WHERE id = ?", (unit["id"],))["status"] == "held"
    pay_msgs = [t for t in to(fresh, lead["phone"]) if "A/c no" in t]
    assert pay_msgs and "999888777" in pay_msgs[-1] and "Lakeside Partner" in pay_msgs[-1]
    assert get_settings().booking["account_number"] not in pay_msgs[-1]          # not our own account
    # held unit is no longer offered to other buyers
    other = mk_lead(name="Other", phone="9123456789", city="Bangalore")
    found = json.loads(tools.run_tool(tools.ToolContext(other["id"], "t"), "search_properties", {})[0])
    assert "A-502" not in [m["unit_no"] for m in found["matches"]]
    fresh.fake.queue([tool_use("send_message", text="Congratulations!", channel="whatsapp")])
    reply = events.staff_command(owner_phone(), f"PAID B{booking['id']} 2L UTR9")
    assert "BOOKED" in reply and "Commission C1" in reply
    assert db.q1("SELECT status FROM units WHERE id = ?", (unit["id"],))["status"] == "booked"
    c = db.q1("SELECT * FROM commissions")
    assert c["amount"] == 180000 and c["deal_value"] == 9000000 and c["status"] == "earned"
    from salesagent import partners
    partners.update_commission(c["id"], "invoiced", "INV-7")
    partners.update_commission(c["id"], "collected", amount=180000)
    t = partners.commission_totals()
    assert t["collected"] == 180000 and t["outstanding"] == 0


def test_payment_details_refused_when_builder_bank_missing(fresh):
    p = _partner_setup()
    db.q("UPDATE builders SET bank_account = '' WHERE id = ?", (p["builder_id"],))
    lead = mk_lead(city="Bangalore")
    unit = db.q1("SELECT * FROM units WHERE unit_no = 'A-101'")
    oid = db.insert("offers", {"lead_id": lead["id"], "project": p["name"], "unit_type": "2BHK", "unit_id": unit["id"],
                               "offered_price": 8800000, "list_price": 8800000, "status": "approved"})
    bid = db.insert("bookings", {"lead_id": lead["id"], "offer_id": oid, "unit_id": unit["id"], "status": "confirmed",
                                 "token_amount": 200000})
    out, is_err = tools.run_tool(tools.ToolContext(lead["id"], "t"), "share_payment_details", {"booking_id": bid})
    assert is_err and "escalate" in out


def test_registration_renewal_before_expiry(fresh):
    from salesagent import partners
    p = _partner_setup()
    lead = mk_lead(city="Bangalore")
    r = partners.register_client(lead["id"], p["id"])
    db.update("registrations", r["registration_id"],
              {"valid_until": (get_settings().now() + timedelta(days=3)).isoformat()})
    assert partners.renew_expiring() == 1
    rows = db.q("SELECT status FROM registrations WHERE lead_id = ? ORDER BY id", (lead["id"],))
    assert [x["status"] for x in rows] == ["expired", "sent"]
    assert partners.renew_expiring() == 0


def test_units_csv_import(tmp_path):
    from salesagent import inventory
    p = _partner_setup()
    csv_path = tmp_path / "u.csv"
    csv_path.write_text("Flat No,BHK,Floor,Facing,Size,Price,Min Price,Status\n"
                        "C-301,3 BHK,3,North,1600,1.2cr,1.1cr,available\n"
                        "A-101,2BHK,1,East,1200,90L,84L,available\n"
                        "C-302,3BHK,3,North,1600,1.1cr,1.2cr,available\n"
                        ",3BHK,,,,,,\n")
    res = inventory.import_units_csv(p["id"], str(csv_path))
    assert res["added"] == 1 and res["updated"] == 1 and len(res["errors"]) == 2
    u = db.q1("SELECT * FROM units WHERE unit_no = 'C-301'")
    assert u["unit_type"] == "3BHK" and u["list_price"] == 12000000 and u["floor_price"] == 11000000
    assert db.q1("SELECT list_price FROM units WHERE unit_no = 'A-101'")["list_price"] == 9000000


def test_inventory_pages(monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    p = _partner_setup()
    a = ("owner", "pw")
    with TestClient(app) as c:
        home = c.get("/inventory", auth=a).text
        assert "Bangalore" in home and "Chennai" in home and "Lakeside Partner" in home
        assert "Lakeview Heights" in c.get(f"/inventory/project/{p['id']}", auth=a).text
        assert c.get("/inventory/builder/new", auth=a).status_code == 200
        r = c.post("/inventory/builder/new", auth=a, data={"name": "Brigade Partner", "commission_type": "pct",
                                                           "commission_value": "1.5", "contact_phone": "9876500099",
                                                           "bank_ifsc": "hdfc0001"})
        assert r.status_code == 200
        b = db.q1("SELECT * FROM builders WHERE name = 'Brigade Partner'")
        assert b["commission_value"] == 1.5 and b["contact_phone"] == "+919876500099" and b["bank_ifsc"] == "HDFC0001"
        r = c.post("/inventory/project/new", auth=a, data={"name": "Brigade Orchards", "builder_id": str(b["id"]),
                                                           "city": "bangalore", "locality": "Devanahalli",
                                                           "visit_days[]": ["5", "6"], "visit_from": "09:00",
                                                           "visit_to": "17:00", "active": "1"})
        newp = db.q1("SELECT * FROM inv_projects WHERE name = 'Brigade Orchards'")
        assert newp["city"] == "Bangalore" and newp["visit_days"] == "5,6" and newp["visit_hours"] == "09:00-17:00"
        c.post(f"/inventory/project/{newp['id']}/units", auth=a, data={"unit_type": "3bhk", "list_price": "1.4cr",
                                                                      "floor_price": "1.3cr", "quantity": "5"})
        u = db.q1("SELECT * FROM units WHERE project_id = ?", (newp["id"],))
        assert u["quantity"] == 5 and u["list_price"] == 14000000
        bad = c.post(f"/inventory/project/{newp['id']}/units", auth=a,
                     data={"unit_type": "2BHK", "list_price": "50L", "floor_price": "60L"})
        assert "floor price is above" in bad.text
        assert "Commission summary" in c.get("/commissions", auth=a).text
        assert "Client registrations" in c.get("/registrations", auth=a).text
        assert "unit_no,unit_type" in c.get("/inventory/units-template.csv", auth=a).text


# ------------------------------------------------------------------ sales kit, landing pages, spend, sample inventory

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")


def test_sample_inventory_load_and_remove():
    from salesagent import inventory
    assert inventory.load_sample() == 4 and inventory.load_sample() == 0
    assert {"Chennai", "Bangalore"} <= set(inventory.cities())
    blr = inventory.search(city="Bangalore", budget_max=10000000)
    assert blr and all(m["city"] == "Bangalore" for m in blr)
    p = inventory.get_project("Whitefield Skyline (sample)")
    assert not p["is_own"] and p["slug"] == "whitefield-skyline-sample"
    assert inventory.remove_sample() == {"removed": 4, "paused": 0}
    assert not db.q1("SELECT id FROM builders WHERE is_sample = 1")
    assert inventory.get_project("Sunrise Meadows")           # real data untouched


def test_brochure_cost_sheet_and_emi(fresh, monkeypatch):
    from salesagent import inventory, sales_kit
    inventory.load_sample()
    p = inventory.get_project("Porur Greens (sample)")
    assert sales_kit.save_media(p["id"], "brochure", "Porur Greens brochure", "brochure.pdf", PDF)["ok"]
    assert sales_kit.save_media(p["id"], "floor_plan", "2BHK plan", "2bhk.png", PNG, "2BHK")["ok"]
    assert not sales_kit.save_media(p["id"], "other", "x", "virus.exe", b"MZ")["ok"]
    lead = mk_lead(city="Chennai")
    ctx = tools.ToolContext(lead_id=lead["id"], event="t")
    out, err = tools.run_tool(ctx, "send_brochure", {"project": "Porur Greens", "kind": "floor_plan",
                                                     "unit_type": "2BHK", "caption": "Here's the 2BHK plan"})
    assert not err and "2BHK plan" in out
    sent = to(fresh, lead["phone"])
    assert any("[2bhk.png] http" in t and "/m/" in t and "Here's the 2BHK plan" in t for t in sent)
    assert "sent floor_plan: 2BHK plan" in db.q1("SELECT content FROM interactions WHERE lead_id = ? ORDER BY id DESC",
                                                (lead["id"],))["content"]
    out, err = tools.run_tool(ctx, "send_brochure", {"project": "Whitefield Skyline", "kind": "brochure", "caption": "x"})
    assert err and "Nothing uploaded yet" in out
    # cost sheet: list price + GST 5% + stamp 7% + reg 2% + parking 3L + corpus 1L for T1-201 (78L)
    out, err = tools.run_tool(ctx, "send_cost_sheet", {"project": "Porur Greens", "unit_no": "T1-201"})
    assert not err
    sheet = to(fresh, lead["phone"])[-1]
    assert "Unit price: ₹78.00 L" in sheet and "GST (5%): ₹3.90 L" in sheet and "Stamp duty (7%): ₹5.46 L" in sheet
    assert "Car parking: ₹3.00 L" in sheet and "Approx. total: ₹92.92 L" in sheet and "Indicative only" in sheet
    assert "73320" not in sheet and "floor" not in sheet.lower()          # never the floor price
    # an approved offer for this lead changes the unit price used
    unit = db.q1("SELECT * FROM units WHERE unit_no = 'T1-201'")
    db.insert("offers", {"lead_id": lead["id"], "unit_id": unit["id"], "project": p["name"], "unit_type": "2BHK",
                         "list_price": 7800000, "offered_price": 7600000, "status": "approved"})
    tools.run_tool(ctx, "send_cost_sheet", {"project": "Porur Greens", "unit_no": "T1-201"})
    assert "Unit price (your approved price): ₹76.00 L" in to(fresh, lead["phone"])[-1]
    ctx2 = tools.ToolContext(lead_id=lead["id"], event="t")
    out, err = tools.run_tool(ctx2, "send_emi_illustration", {"price": 9200000})
    emi_text = to(fresh, lead["phone"])[-1]
    assert "Loan: ₹73.60 L at 8.5% p.a." in emi_text and "20 years: about ₹63,872/month" in emi_text
    assert "Illustrative only" in emi_text
    assert sales_kit.emi(7360000, 8.5, 20) == 63872


def test_attachment_goes_through_review_then_sends(fresh, monkeypatch):
    from salesagent import inventory, sales_kit
    monkeypatch.setitem(get_settings().sales_team[0], "message_mode", "review")
    inventory.load_sample()
    p = inventory.get_project("Porur Greens (sample)")
    sales_kit.save_media(p["id"], "brochure", "Porur brochure", "b.pdf", PDF)
    lead = mk_lead()
    tools.run_tool(tools.ToolContext(lead["id"], "t"), "send_brochure",
                   {"project": "Porur Greens", "kind": "brochure", "caption": "Brochure attached"})
    assert to(fresh, lead["phone"]) == []
    assert any("📎 with attachment: Porur brochure" in t for t in to(fresh, rm_phone()))
    events.staff_command(rm_phone(), "SEND D1")
    assert any("[b.pdf]" in t for t in to(fresh, lead["phone"]))


def test_public_media_link_and_project_upload(monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent import inventory, sales_kit
    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    inventory.load_sample()
    p = inventory.get_project("Porur Greens (sample)")
    with TestClient(app) as c:
        r = c.post(f"/inventory/project/{p['id']}/media", auth=("owner", "pw"),
                   files={"file": ("plan.pdf", PDF, "application/pdf")}, data={"kind": "floor_plan", "title": "Plan"})
        assert "Uploaded" in r.text
        m = db.q1("SELECT * FROM media WHERE project_id = ?", (p["id"],))
        got = c.get(f"/m/{m['token']}/{m['filename']}")                     # public, no login (WhatsApp fetches it)
        assert got.status_code == 200 and got.content == PDF
        assert c.get(f"/m/wrongtoken/{m['filename']}").status_code == 404
        assert "Landing page:" in c.get(f"/inventory/project/{p['id']}", auth=("owner", "pw")).text


def test_landing_page_captures_lead_with_consent(fresh):
    from fastapi.testclient import TestClient

    from salesagent import inventory, web_public
    from salesagent.server import app
    web_public._hits.clear()
    inventory.load_sample()
    fresh.fake.queue([tool_use("send_message", text="Hi Ravi, I'm Skyline Realty's assistant…", channel="whatsapp")])
    with TestClient(app) as c:
        page = c.get("/p/whitefield-skyline-sample?src=facebook&c=C7-V2")
        assert page.status_code == 200 and "Whitefield Skyline" in page.text and "2BHK" in page.text
        assert "(sample)" not in page.text.split("<h1>")[1].split("</h1>")[0]
        assert "9024000" not in page.text and "floor" not in page.text.lower().replace("floor plans", "")
        assert 'name="c" value="C7-V2"' in page.text and 'name="src" value="meta_ads"' in page.text
        data = {"name": "Ravi", "phone": "98450 12345", "unit_type": "2BHK", "budget": "1cr",
                "timeline": "Within 3 months", "src": "meta_ads", "c": "C7-V2", "website": ""}
        no_consent = c.post("/p/whitefield-skyline-sample", data=data)
        assert "consent box" in no_consent.text and not db.find_lead_by_phone("9845012345")
        bad_phone = c.post("/p/whitefield-skyline-sample", data={**data, "consent": "1", "phone": "123"})
        assert "valid 10-digit" in bad_phone.text
        ok = c.post("/p/whitefield-skyline-sample", data={**data, "consent": "1"})
        assert "Thank you" in ok.text
        bot = c.post("/p/whitefield-skyline-sample", data={**data, "consent": "1", "phone": "9845099999",
                                                          "website": "spam.example"})
        assert "Thank you" in bot.text and not db.find_lead_by_phone("9845099999")   # honeypot: silently dropped
        assert c.get("/p/no-such-project").status_code == 404
        assert "Whitefield" in c.get("/enquire?city=Bangalore").text and "Privacy" in c.get("/privacy").text
    lead = db.find_lead_by_phone("9845012345")
    assert lead["source"] == "meta_ads" and lead["campaign"] == "C7-V2" and lead["city"] == "Bangalore"
    assert lead["budget_max"] == 10000000 and lead["project_interest"] == "Whitefield Skyline (sample)"
    assert lead["consent_at"] and "AI assistant" in lead["consent_text"] and "C7-V2" in lead["consent_source"]
    assert fresh.fake.briefings and "new lead" in fresh.fake.briefings[-1].lower()


def test_landing_rate_limit(fresh):
    from fastapi.testclient import TestClient

    from salesagent import inventory, web_public
    from salesagent.server import app
    web_public._hits.clear()
    inventory.load_sample()
    with TestClient(app) as c:
        for i in range(web_public.RATE_LIMIT):
            r = c.post("/enquire", data={"name": f"P{i}", "phone": f"98450000{i:02d}", "city": "Chennai",
                                         "consent": "1"})
            assert "Thank you" in r.text
        r = c.post("/enquire", data={"name": "P9", "phone": "9845000099", "city": "Chennai", "consent": "1"})
        assert "Too many enquiries" in r.text


def test_spend_report_unit_economics(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    month = get_settings().now().strftime("%Y-%m")
    ids = []
    for i in range(4):
        lead, _ = leads.upsert_lead({"name": f"M{i}", "phone": f"90000555{i:02d}", "source": "meta_ads",
                                     "campaign": "C1-V1"})
        ids.append(lead["id"])
    pipeline.move(ids[0], "qualified", "system")
    pipeline.move(ids[1], "qualified", "system")
    pipeline.move(ids[1], "visit_scheduled", "system")
    pipeline.move(ids[1], "visit_done", "system")
    pipeline.move(ids[1], "lost", "system", "too far")           # lost, but it still counts as visited
    with TestClient(app) as c:
        c.post("/reports/spend", auth=("owner", "pw"), data={"month": month, "source": "meta_ads", "amount": "20k",
                                                             "campaign": ""})
        c.post("/reports/spend", auth=("owner", "pw"), data={"month": month, "source": "google_ads",
                                                             "campaign": "C1-V1", "amount": "8000"})
        html = c.get("/reports", auth=("owner", "pw")).text
        assert "Unit economics by channel" in html and "₹20,000" in html
    from salesagent import marketing
    row = next(r for r in marketing.spend_report("source") if r["key"] == "meta_ads")
    assert (row["leads"], row["qualified"], row["visited"], row["booked"]) == (4, 2, 1, 0)
    assert row["cpl"] == 5000 and row["cpq"] == 10000 and row["cpv"] == 20000 and row["cpb"] is None
    camp = next(r for r in marketing.spend_report("campaign") if r["key"] == "C1-V1")
    assert camp["spend"] == 8000 and camp["cpl"] == 2000


def test_access_key_login(monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw12345")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "k9Fq72LmZp0XwD4s")
    with TestClient(app) as c:
        assert c.get("/", headers={"Authorization": "Bearer k9Fq72LmZp0XwD4s"}).status_code == 200
        assert c.get("/inventory", headers={"Authorization": "Bearer k9Fq72LmZp0XwD4s"}).status_code == 200
        assert c.get("/", headers={"Authorization": "Bearer wrong-key-wrong-key"}).json()["detail"] == "Wrong access key"
        assert c.get("/", auth=("owner", "pw12345")).status_code == 200            # browser login still works
        r = c.get("/")
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Basic"   # browser still gets the prompt
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "short")
    with TestClient(app) as c:                                                     # too-short keys are refused
        assert c.get("/", headers={"Authorization": "Bearer short"}).status_code == 401


def test_new_builder_from_project_form(monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    with TestClient(app) as c:
        form = c.get("/inventory/project/new", auth=("owner", "pw")).text
        assert "+ New partner builder" in form
        c.post("/inventory/project/new", auth=("owner", "pw"), data={
            "name": "Anna Nagar Towers", "city": "chennai", "builder_id": "new", "new_builder_name": "Riverside Builders",
            "new_builder_commission": "2.5", "new_builder_phone": "9876512345", "active": "1"})
    b = db.q1("SELECT * FROM builders WHERE name = 'Riverside Builders'")
    p = db.q1("SELECT * FROM inv_projects WHERE name = 'Anna Nagar Towers'")
    assert b and b["is_own"] == 0 and b["commission_value"] == 2.5 and b["contact_phone"] == "+919876512345"
    assert p["builder_id"] == b["id"] and p["city"] == "Chennai"


def test_cost_sheet_applies_approved_free_parking_and_nil_gst(fresh):
    from salesagent import inventory, sales_kit
    inventory.load_sample()
    p = inventory.get_project("Whitefield Skyline (sample)")
    unit = db.q1("SELECT * FROM units WHERE unit_no = 'C-1203'")
    lead = mk_lead(city="Bangalore")
    db.insert("offers", {"lead_id": lead["id"], "unit_id": unit["id"], "project": p["name"], "unit_type": "2BHK",
                         "list_price": 9600000, "offered_price": 9600000, "owner_counter_price": 9500000,
                         "concessions": json.dumps(["Car parking included at no extra charge"]), "status": "countered"})
    text = sales_kit.cost_sheet(p, unit, lead["id"])["text"]
    assert "Unit price (your approved price): ₹95.00 L" in text
    assert "Car parking: included free (approved)" in text and "Car parking: ₹4.00 L" not in text
    assert "GST: nil (ready to move)" in text and "Maintenance deposit: ₹1.20 L" in text
    assert "Approx. total: ₹1.02 Cr" in text          # 95 + 4.75 + 0.95 + 1.2 = 101.9 L


def test_waiver_matching_ignores_generic_words():
    from salesagent.sales_kit import _waived
    assert _waived("Car parking", ["Free car parking"])
    assert _waived("Club membership", ["Club membership waiver"])
    assert not _waived("Registration charges", ["Documentation charges waiver"])
    assert not _waived("Maintenance deposit", ["Car parking included at no extra charge"])


def test_storage_status_flags_missing_railway_volume(monkeypatch):
    from salesagent import config
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    assert config.storage_status()["persistent"] is False
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(config.DATA_DIR))
    assert config.storage_status()["persistent"] is True


def test_partner_office_visit_uses_builder_office_or_online_only(fresh):
    p = _partner_setup()
    lead = mk_lead(city="Bangalore")
    unit = db.q1("SELECT * FROM units WHERE unit_no = 'A-101'")
    oid = db.insert("offers", {"lead_id": lead["id"], "project": p["name"], "unit_type": "2BHK", "unit_id": unit["id"],
                               "offered_price": 8800000, "list_price": 8800000, "status": "approved"})
    db.insert("bookings", {"lead_id": lead["id"], "offer_id": oid, "unit_id": unit["id"], "status": "confirmed",
                           "token_amount": 200000})
    ctx = tools.ToolContext(lead["id"], "t")
    out, err = tools.run_tool(ctx, "get_office_slots", {"date": "2030-01-07"})
    assert err and "Lakeside Partner's office" in out and "online transfer only" in out
    db.q("UPDATE builders SET office_address = 'Lakeside HQ, Whitefield' WHERE id = ?", (p["builder_id"],))
    out, err = tools.run_tool(ctx, "get_office_slots", {"date": "2030-01-07"})
    assert not err and "Lakeside HQ, Whitefield" in out
    assert get_settings().booking["office_address"] not in out


def test_call_tasks_close_when_lead_booked_or_lost():
    lead = mk_lead()
    team.create_call_task(lead["id"], "Follow up", 30, "b")
    pipeline.move(lead["id"], "lost", "system", "bought elsewhere")
    assert db.q1("SELECT status FROM call_tasks WHERE lead_id = ?", (lead["id"],))["status"] == "cancelled"


# ------------------------------------------------------------------ team portals, reminders, no-reply sequence

def _two_rms(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "raw", {**s.raw, "sales_team": [
        {"name": "Anitha", "phone": "+919800000010", "message_mode": "auto"},
        {"name": "Kiran", "phone": "+919800000020", "message_mode": "auto"}]})


def test_sales_portal_lobby_lead_steps_and_privacy(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent import team_access
    from salesagent.server import app
    _two_rms(monkeypatch)
    mine = mk_lead(name="Asha")
    db.update("leads", mine["id"], {"rm_name": "Anitha", "budget_max": 8000000, "unit_type": "2BHK"})
    other, _ = leads.upsert_lead({"name": "Bala", "phone": "9000099999"})
    db.update("leads", other["id"], {"rm_name": "Kiran"})
    t = team.create_call_task(mine["id"], "Intro call", 10, "Ask about budget and visit day")
    tok = team_access.ensure("sales", "Anitha", "+919800000010")["token"]
    with TestClient(app) as c:
        lobby = c.get(f"/s/{tok}").text
        assert "Hi Anitha" in lobby and "Asha" in lobby and "Bala" not in lobby and "Intro call" in lobby
        page = c.get(f"/s/{tok}/lead/{mine['id']}").text
        assert "Path to booking" in page and "Ask about budget" in page and 'href="tel:' in page
        assert 'class="now"' in page and "Intro call" in page
        assert c.get(f"/s/{tok}/lead/{other['id']}").status_code == 404          # not her buyer
        assert c.get("/s/not-a-real-token").status_code == 404
        assert c.get(f"/s/{tok}/manifest.json").json()["start_url"] == f"/s/{tok}"
        fresh.fake.queue([tool_use("send_message", text="Lovely speaking with you!", channel="whatsapp")])
        r = c.post(f"/s/{tok}/call/{t['task_id']}", data={"outcome": "spoke", "summary": "Wants east facing, visit Sat"})
        assert "Call saved" in r.text
    assert db.q1("SELECT status FROM call_tasks WHERE id = ?", (t["task_id"],))["status"] == "done"
    assert "east facing" in fresh.fake.briefings[-1]
    steps = __import__("salesagent.web_portals", fromlist=["x"]).lead_steps(db.get_lead(mine["id"]))
    assert [x["state"] for x in steps[:3]] == ["done", "done", "now"]                # intro + qualify done → book visit


def test_sales_portal_draft_approval(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent import team_access
    from salesagent.server import app
    monkeypatch.setitem(get_settings().sales_team[0], "message_mode", "review")
    lead = mk_lead()
    team.assign_rm(lead["id"])
    team.send_or_draft(lead["id"], "Hi Asha, Skyline Realty's assistant here.")
    tok = team_access.ensure("sales", "Anitha", rm_phone())["token"]
    with TestClient(app) as c:
        assert "Messages to approve" in c.get(f"/s/{tok}").text
        c.post(f"/s/{tok}/draft/1", data={"action": "send", "text": "Hi Asha, Skyline Realty's assistant here."})
    assert to(fresh, lead["phone"]) == ["Hi Asha, Skyline Realty's assistant here."]


def test_site_app_visit_steps_notify_salesperson(fresh):
    from fastapi.testclient import TestClient

    from salesagent import team_access
    from salesagent.server import app
    lead = mk_lead()
    team.assign_rm(lead["id"])
    pipeline.move(lead["id"], "qualified", "system")
    tomorrow = (get_settings().now() + timedelta(days=1)).date().isoformat()
    v = visits.book(lead["id"], "Sunrise Meadows", visits.free_slots("Sunrise Meadows", tomorrow)[0]["time"], "x")
    tok = team_access.ensure("site", "Ravi", site_phone())["token"]
    other = team_access.ensure("site", "Someone", "+919811122233")["token"]
    with TestClient(app) as c:
        assert "Asha" in c.get(f"/site/{tok}").text and "Coming up" in c.get(f"/site/{tok}").text
        page = c.get(f"/site/{tok}/visit/{v['visit_id']}").text
        assert "Called &amp; confirmed" in page and "Fill visit report" not in page.split('class="now"')[0]
        assert c.get(f"/site/{other}/visit/{v['visit_id']}").status_code == 404     # not their visit
        c.post(f"/site/{tok}/visit/{v['visit_id']}/confirm")
        c.post(f"/site/{tok}/visit/{v['visit_id']}/arrived")
        page = c.get(f"/site/{tok}/visit/{v['visit_id']}").text
        assert "Fill visit report" in page
    assert any("confirmed Asha" in t for t in to(fresh, rm_phone()))
    assert any("has arrived at Sunrise Meadows" in t for t in to(fresh, rm_phone()))


def test_team_page_links_send_and_regenerate(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    with TestClient(app) as c:
        page = c.get("/team", auth=("owner", "pw")).text
        assert "Anitha" in page and "Salesperson portal" in page and "Site visit app" in page
        acc = db.q1("SELECT * FROM team_access WHERE role = 'sales'")
        c.post(f"/team/{acc['id']}", auth=("owner", "pw"), data={"action": "send"})
        assert any(acc["token"] in t and "Add to Home screen" in t for t in to(fresh, rm_phone()))
        c.post(f"/team/{acc['id']}", auth=("owner", "pw"), data={"action": "new"})
        assert c.get(f"/s/{acc['token']}").status_code == 404                     # old link revoked
        new = db.q1("SELECT token FROM team_access WHERE role = 'sales' AND revoked = 0")["token"]
        assert c.get(f"/s/{new}").status_code == 200


def test_visit_reminders_reach_buyer_site_and_salesperson(fresh, monkeypatch):
    lead = mk_lead()
    team.assign_rm(lead["id"])
    pipeline.move(lead["id"], "qualified", "system")
    day = (get_settings().now() + timedelta(days=1)).date().isoformat()
    slot = visits.free_slots("Sunrise Meadows", day)[0]["time"]
    visits.book(lead["id"], "Sunrise Meadows", slot, "x")
    monkeypatch.setattr(scheduler, "in_quiet_hours", lambda now=None: False)
    when = db.parse_dt(slot)
    monkeypatch.setattr(get_settings(), "now", lambda: when - timedelta(hours=23))
    scheduler.tick()
    assert any("reminder of your visit" in t for t in to(fresh, lead["phone"]))
    assert any(t.startswith("Tomorrow: site visit") for t in to(fresh, site_phone()))
    assert any("visits Sunrise Meadows" in t and "confirmation call" in t for t in to(fresh, rm_phone()))
    assert db.q1("SELECT purpose FROM call_tasks WHERE lead_id = ?", (lead["id"],))["purpose"].startswith("Confirm tomorrow")
    monkeypatch.setattr(get_settings(), "now", lambda: when - timedelta(hours=1, minutes=50))
    scheduler.tick()
    assert any(t.startswith("In 2 hours: site visit") for t in to(fresh, site_phone()))
    assert any(t.startswith("In 2 hours:") for t in to(fresh, rm_phone()))
    n = len(fresh.sent)
    scheduler.tick()
    assert not any("reminder of your visit" in t or "In 2 hours" in t for _, t in fresh.sent[n:])   # no repeats


def test_no_reply_sequence_alternates_message_and_call_then_nurture(fresh):
    lead = mk_lead()
    team.assign_rm(lead["id"])
    pipeline.move(lead["id"], "contacted", "system")
    fresh.fake.queue([tool_use("send_message", text="Here's a 2BHK that fits — shall I send the plan?", channel="whatsapp")])
    events.followup_due(lead["id"])                                      # 1: message
    assert "follow-up 1 of 5" in fresh.fake.briefings[-1]
    db.q("UPDATE call_tasks SET status = 'done' WHERE lead_id = ?", (lead["id"],))
    n_calls = len(fresh.fake.briefings)
    events.followup_due(lead["id"])                                      # 2: call task, no AI message
    assert len(fresh.fake.briefings) == n_calls
    task = db.q1("SELECT * FROM call_tasks WHERE lead_id = ? AND status = 'open'", (lead["id"],))
    assert "reconnect by phone" in task["purpose"] and db.get_lead(lead["id"])["next_followup_at"]
    db.q("UPDATE call_tasks SET status = 'done' WHERE lead_id = ?", (lead["id"],))
    events.followup_due(lead["id"])                                      # 3: message with something new
    assert "something NEW" in fresh.fake.briefings[-1]
    db.q("UPDATE call_tasks SET status = 'done' WHERE lead_id = ?", (lead["id"],))
    events.followup_due(lead["id"])                                      # 4: call at a different time
    assert "different time of day" in db.q1("SELECT purpose FROM call_tasks WHERE lead_id = ? AND status = 'open'",
                                            (lead["id"],))["purpose"]
    events.followup_due(lead["id"])                                      # 5: close the loop → nurture
    assert "reply 1" in fresh.fake.briefings[-1]
    assert db.get_lead(lead["id"])["stage"] == "nurture"
    # a reply resets the sequence
    events.inbound_message(lead["phone"], None, "1", "whatsapp")
    assert db.get_lead(lead["id"])["followup_attempts"] == 0


# ------------------------------------------------------------------ automatic lead sources

class _Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code, self.text = data, code, json.dumps(data)

    def json(self):
        return self._d


def test_meta_lead_ads_webhook(fresh, monkeypatch):
    import hashlib
    import hmac as _hmac

    from fastapi.testclient import TestClient

    from salesagent import inventory, lead_sources
    from salesagent.server import app
    inventory.load_sample()
    monkeypatch.setenv("META_PAGE_TOKEN", "page-token")
    monkeypatch.setenv("META_APP_SECRET", "appsecret")
    monkeypatch.setenv("META_VERIFY_TOKEN", "verify-me")
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp({"field_data": [{"name": "full_name", "values": ["Karthik R"]},
                                     {"name": "phone_number", "values": ["+91 98450 77777"]},
                                     {"name": "what_is_your_budget?", "values": ["90_lakhs"]},
                                     {"name": "which_configuration?", "values": ["2_bhk"]}],
                      "ad_name": "Whitefield Skyline lake view C3-V2", "campaign_name": "BLR ready homes",
                      "form_id": "F1"})
    monkeypatch.setattr(lead_sources.requests, "get", fake_get)
    fresh.fake.queue([tool_use("send_message", text="Hi Karthik, Skyline Realty's assistant here", channel="whatsapp")])
    payload = {"entry": [{"changes": [{"field": "leadgen", "value": {"leadgen_id": "L123", "form_id": "F1"}}]}]}
    body = json.dumps(payload).encode()
    sig = "sha256=" + _hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    with TestClient(app) as c:
        assert c.get("/webhook/meta", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                              "hub.challenge": "42"}).text == "42"
        assert c.post("/webhook/meta", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
        assert c.post("/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig}).status_code == 200
        c.post("/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig})          # Meta retry: ignored
    lead = db.find_lead_by_phone("9845077777")
    assert lead["name"] == "Karthik R" and lead["source"] == "meta_ads" and lead["campaign"] == "C3-V2"
    assert lead["unit_type"] == "2BHK" and lead["budget_max"] == 9000000
    assert lead["project_interest"] == "Whitefield Skyline (sample)" and "Meta" in lead["consent_text"]
    assert len(calls) == 1 and db.q1("SELECT COUNT(*) n FROM leads")["n"] == 1
    assert "Came from Meta lead ad" in fresh.fake.briefings[-1]


def test_click_to_whatsapp_ad_tags_lead(fresh):
    from fastapi.testclient import TestClient

    from salesagent import inventory
    from salesagent.server import app
    inventory.load_sample()
    fresh.fake.queue([tool_use("send_message", text="Hi! Porur Greens 2BHKs start at ₹78 L.", channel="whatsapp")])
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "919845066666", "profile": {"name": "Lakshmi"}}],
        "messages": [{"from": "919845066666", "type": "text", "text": {"body": "Hi, is this available?"},
                      "referral": {"source_type": "ad", "source_id": "AD9", "headline": "Porur Greens 2BHK from 78L C4-V1",
                                   "body": "Near DLF IT park", "source_url": "https://fb.me/x"}}]}}]}]}
    with TestClient(app) as c:
        assert c.post("/webhook/whatsapp", json=payload).status_code == 200
    lead = db.find_lead_by_phone("+919845066666")
    assert lead["source"] == "meta_ctwa" and lead["campaign"] == "C4-V1" and lead["name"] == "Lakshmi"
    assert lead["project_interest"] == "Porur Greens (sample)"
    assert "Click-to-WhatsApp ad" in fresh.fake.briefings[-1] and "is this available" in fresh.fake.briefings[-1]


SAMPLE_99 = """From: 99acres <noreply@99acres.com>
Subject: You have received a response for Porur Greens

Dear Advertiser,
A buyer is interested in your property Porur Greens, Porur, Chennai.

Name: Suresh Kumar
Mobile: +91-9840123456
Email: suresh.k@example.com
Budget: 80 Lac
Configuration: 2 BHK

Regards, 99acres team"""


def test_portal_email_becomes_lead(fresh):
    from salesagent import inventory, lead_sources
    inventory.load_sample()
    body = SAMPLE_99.split("\n\n", 1)[1]
    fresh.fake.queue([tool_use("send_message", text="Hi Suresh, Skyline Realty's assistant here", channel="whatsapp")])
    lid = lead_sources.process_email("99acres <noreply@99acres.com>", "You have received a response for Porur Greens",
                                     body, "<m1@99acres>")
    lead = db.get_lead(lid)
    assert lead["name"] == "Suresh Kumar" and lead["phone"] == "+919840123456" and lead["email"] == "suresh.k@example.com"
    assert lead["source"] == "portal" and lead["campaign"] == "99acres" and lead["unit_type"] == "2BHK"
    assert lead["budget_max"] == 8000000 and lead["project_interest"] == "Porur Greens (sample)"
    assert lead_sources.process_email("99acres", "x", body, "<m1@99acres>") is None              # duplicate
    assert lead_sources.process_email("friend@gmail.com", "Lunch?", "Call me 9876501234", "<m2>") is None  # not a portal
    html = "<html><body><p>MagicBricks lead</p><table><tr><td>Name: Anu</td></tr><tr><td>Phone: 9988776655</td></tr>" \
           "</table></body></html>"
    lid2 = lead_sources.process_email("alerts@magicbricks.com", "New enquiry", html, "<m3>")
    assert db.get_lead(lid2)["campaign"] == "magicbricks" and db.get_lead(lid2)["phone"] == "+919988776655"


def test_portal_email_webhook_and_mailbox_poll(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent import lead_sources
    from salesagent.server import app
    monkeypatch.setenv("LEAD_WEBHOOK_SECRET", "s3")
    body = SAMPLE_99.split("\n\n", 1)[1]
    with TestClient(app) as c:
        assert c.post("/webhook/portal-email", json={"from": "99acres", "subject": "x", "text": body}).status_code == 401
        r = c.post("/webhook/portal-email", headers={"X-Webhook-Secret": "s3"},
                   json={"from": "noreply@99acres.com", "subject": "Response", "text": body, "message_id": "w1"})
        assert r.json()["lead_id"]

    raw = ("From: Housing.com <leads@housing.com>\r\nSubject: New lead\r\nMessage-ID: <h1@housing>\r\n"
           "Content-Type: text/plain; charset=utf-8\r\n\r\nName: Priya M\r\nPhone: 9123456780\r\nBudget: 1.2 Cr\r\n").encode()

    class FakeIMAP:
        stored = []

        def __init__(self, host, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, p): assert (u, p) == ("leads@x.com", "app-pass")
        def select(self, box): pass
        def search(self, *a): return "OK", [b"1"]
        def fetch(self, num, what): return "OK", [(b"1 (RFC822)", raw)]
        def store(self, num, flags, val): FakeIMAP.stored.append(num)
    monkeypatch.setattr(lead_sources.imaplib, "IMAP4_SSL", FakeIMAP)
    assert lead_sources.poll_mailbox() == {"configured": False}
    monkeypatch.setenv("LEADS_IMAP_USER", "leads@x.com")
    monkeypatch.setenv("LEADS_IMAP_PASSWORD", " app-pass ")
    assert lead_sources.poll_mailbox()["leads"] == 1 and FakeIMAP.stored == [b"1"]
    lead = db.find_lead_by_phone("9123456780")
    assert lead["campaign"] == "housing" and lead["budget_max"] == 12000000


def test_meta_spend_sync_and_google_csv(fresh, monkeypatch, tmp_path):
    from salesagent import lead_sources, marketing
    month = get_settings().now().strftime("%Y-%m")
    page2 = {"data": [{"campaign_name": "Chennai search", "spend": "4000.4", "date_start": f"{month}-01"}]}

    def fake_graph(path, params, token):
        assert path.startswith("act_123/insights") and params["level"] == "campaign"
        return {"data": [{"campaign_name": "BLR ready homes C3-V2", "spend": "15000", "date_start": f"{month}-01"}],
                "paging": {"next": "https://graph/next"}}
    monkeypatch.setattr(lead_sources, "_graph_get", fake_graph)
    monkeypatch.setattr(lead_sources.requests, "get", lambda url, timeout=None: _Resp(page2))
    assert lead_sources.sync_meta_spend() == {"configured": False}
    monkeypatch.setenv("META_ADS_TOKEN", "t")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "act_123")
    res = lead_sources.sync_meta_spend()
    assert res["total"] == 19000 and res["rows"] == 2
    lead_sources.sync_meta_spend()                                         # re-sync replaces, doesn't double
    assert db.q1("SELECT SUM(amount) s FROM ad_spend WHERE notes = 'auto:meta'")["s"] == 19000
    assert db.q1("SELECT campaign FROM ad_spend WHERE amount = 15000")["campaign"] == "C3-V2"
    csv_path = tmp_path / "g.csv"
    csv_path.write_text("Campaign report\nAll time\nCampaign,Clicks,Cost\nChennai 2BHK C5-V1,120,\"12,345.60\"\n"
                        "Bangalore search,80,6000\nTotal: Account,200,\"18,345.60\"\n")
    res = lead_sources.import_google_csv(str(csv_path), month)
    assert res["rows"] == 2
    row = next(r for r in marketing.spend_report("source") if r["key"] == "google_ads")
    assert row["spend"] == 18346


def test_lead_sources_page(monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent.server import app
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    with TestClient(app) as c:
        html = c.get("/sources", auth=("owner", "pw")).text
        assert "Meta lead ads" in html and "/webhook/meta" in html and "Click-to-WhatsApp" in html
        assert "LEADS_IMAP_PASSWORD" in html and "Upload Google Ads CSV" in html
        r = c.post("/sources/mail", auth=("owner", "pw"))
        assert "Mailbox not set up yet" in r.text


def test_landing_and_registration_show_city_rera(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from salesagent import inventory, partners
    from salesagent.server import app
    monkeypatch.setitem(get_settings().business, "rera_by_city",
                        "Chennai: TN/Agent/0123 (Vijay)\nBangalore: PRM/KA/RERA/1251 (Wife)")
    inventory.load_sample()
    with TestClient(app) as c:
        blr = c.get("/p/whitefield-skyline-sample").text
        chn = c.get("/p/porur-greens-sample").text
    assert "PRM/KA/RERA/1251" in blr and "TN/Agent/0123" not in blr
    assert "TN/Agent/0123" in chn and "PRM/KA/RERA/1251" not in chn
    lead = mk_lead(city="Bangalore")
    partners.register_client(lead["id"], inventory.get_project("Whitefield Skyline (sample)")["id"])
    msg = db.q1("SELECT message FROM registrations")["message"]
    assert "Our RERA agent registration: PRM/KA/RERA/1251 (Wife)" in msg
