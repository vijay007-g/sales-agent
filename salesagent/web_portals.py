"""Team portals (no owner access needed, personal secret link per person, installable like an app):

  /s/<token>                 Salesperson lobby: calls to make now, drafts to approve, upcoming visits, my buyers
  /s/<token>/lead/<id>       One buyer: step-by-step path to booking, what to do now, call brief, log the call
  /site/<token>              Site team app: today's / upcoming visits, reports due
  /site/<token>/visit/<id>   One visit: confirm → customer arrived → show these units → fill report
"""
from __future__ import annotations

import json
from datetime import timedelta
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import channels, db, events, pricing, team, team_access
from .config import get_settings

router = APIRouter()

CSS = """
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f4f6f9;color:#1d2330}
header{background:#1d2330;color:#fff;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:5}
header b{font-size:17px}header a{color:#cfd6e4;text-decoration:none;font-size:14px}
main{max-width:860px;margin:auto;padding:12px}
.card{background:#fff;border:1px solid #e3e6ec;border-radius:12px;padding:14px;margin:10px 0}
h2{font-size:19px;margin:4px 0 10px}h3{font-size:16px;margin:0 0 8px}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #eef0f4}
.row:last-child{border-bottom:0}.muted{color:#6b7385;font-size:13px}
a.lead{color:inherit;text-decoration:none;display:block}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;background:#eef1f6;font-size:12px;margin-right:4px}
.hot{background:#ffe1dc}.warm{background:#fff2d6}.cold{background:#e1ecff}.over{background:#c9372c;color:#fff}
.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#2b62e3;color:#fff;text-decoration:none;
border:0;font-size:15px;font-weight:600;cursor:pointer;text-align:center}.btn.g{background:#1f8f4e}.btn.grey{background:#6b7385}
.btn.red{background:#c9372c}.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.steps{list-style:none;padding:0;margin:0}.steps li{display:flex;gap:10px;padding:9px 0;align-items:flex-start}
.dot{width:26px;height:26px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;
font-size:13px;font-weight:700;background:#e3e6ec;color:#6b7385}.done .dot{background:#1f8f4e;color:#fff}
.now .dot{background:#2b62e3;color:#fff}.now{background:#eef4ff;border-radius:10px;padding:9px 8px!important}
.brief{white-space:pre-wrap;background:#f7f8fb;border-radius:8px;padding:10px;font-size:14px}
textarea,input,select{width:100%;padding:11px;border:1px solid #cfd4dd;border-radius:9px;font:inherit;font-size:16px}
label{font-weight:600;font-size:14px;display:block;margin:10px 0 4px}
.msg{padding:8px 10px;border-radius:9px;margin:5px 0;white-space:pre-wrap;font-size:14px;max-width:92%}
.in{background:#eef1f6}.out{background:#dcf3e4;margin-left:auto}.call{background:#fff7e0;margin-left:auto}
.badge{background:#c9372c;color:#fff;border-radius:99px;padding:1px 8px;font-size:12px;margin-left:6px}
"""


def _shell(title: str, who: str, home: str, body: str, manifest: str) -> HTMLResponse:
    biz = get_settings().business.get("name", "")
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#1d2330">
<link rel="manifest" href="{manifest}"><link rel="icon" href="/icon.svg"><link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="robots" content="noindex">
<style>{CSS}</style></head><body><header><a href="{home}"><b>{escape(biz)}</b></a><span>{escape(who)}</span></header>
<main>{body}</main><script>setInterval(function(){{var a=document.activeElement;
if(a&&/INPUT|TEXTAREA|SELECT/.test(a.tagName))return;var f=document.querySelectorAll('textarea,input[type=text]');
for(var i=0;i<f.length;i++){{if(f[i].value)return;}}location.reload();}},30000);</script></body></html>""")


def _manifest(name: str, start: str) -> JSONResponse:
    return JSONResponse({"name": name, "short_name": name.split()[-1], "start_url": start, "display": "standalone",
                         "background_color": "#f4f6f9", "theme_color": "#1d2330",
                         "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]})


def _tel(phone: str) -> str:
    return escape(phone or "")


def _wa(phone: str) -> str:
    return "https://wa.me/" + "".join(ch for ch in (phone or "") if ch.isdigit())


def _temp(t: str) -> str:
    t = "" if t in (None, "", "unknown") else t
    return f'<span class="pill {escape(t)}">{escape(t or "new")}</span>'


def _when(iso: str | None) -> str:
    dt = db.parse_dt(iso)
    if not dt:
        return ""
    now = get_settings().now()
    day = "Today" if dt.date() == now.date() else "Tomorrow" if dt.date() == (now + timedelta(days=1)).date() \
        else f"{dt:%a %d %b}"
    return f"{day} {dt:%I:%M %p}".replace(" 0", " ")


# ============================================================ salesperson: the path to booking

STEP_HELP = {
    "intro": ("Intro call", "Call within 10 minutes of the enquiry. Introduce yourself, confirm what they need, and "
                            "promise to share matching options."),
    "qualify": ("Understand needs", "Budget, size, area, ready or under construction, loan or own funds, who decides."),
    "visit_booked": ("Book the site visit", "Offer two specific slots; ask them to bring the decision maker."),
    "visit_confirm": ("Confirmation call", "The day before: confirm time, who is coming, share the location."),
    "visit_done": ("Site visit", "The site team hosts it and fills the visit report."),
    "post_visit": ("Post-visit call", "Same day: thank them, use the AI's strategy, handle concerns, ask for a decision."),
    "price": ("Price agreed", "Price requests go to management. Present approved prices on a call first."),
    "booking": ("Booking confirmed", "Customer agrees → management confirms → official payment details are sent."),
    "advance": ("Advance received", "Management marks it received after checking the bank. The flat is booked."),
}


def lead_steps(lead: dict) -> list[dict]:
    lid = lead["id"]
    calls = db.q("SELECT * FROM call_tasks WHERE lead_id = ? ORDER BY id", (lid,))
    spoke = [c for c in calls if c["outcome"] == "spoke"]
    site = db.q("SELECT * FROM site_visits WHERE lead_id = ? AND kind = 'site' AND status != 'rescheduled' ORDER BY id",
                (lid,))
    visited = [v for v in site if v["status"] == "completed"]
    upcoming = [v for v in site if v["status"] == "scheduled"]
    offers = db.q("SELECT status FROM offers WHERE lead_id = ?", (lid,))
    bookings = db.q("SELECT status FROM bookings WHERE lead_id = ?", (lid,))
    after_visit = visited and any((c["done_at"] or "") > (visited[-1]["updated_at"] or "") for c in spoke)
    stage = lead["stage"]
    done = {
        "intro": bool(spoke) or stage in ("qualified", "visit_scheduled", "visit_done", "negotiation",
                                          "booking_pending", "payment_pending", "booked"),
        "qualify": bool(lead.get("budget_max") and lead.get("unit_type")),
        "visit_booked": bool(site),
        "visit_confirm": bool(visited) or bool(upcoming and upcoming[-1]["confirmed_at"]),
        "visit_done": bool(visited),
        "post_visit": bool(after_visit) or stage in ("booking_pending", "payment_pending", "booked"),
        "price": any(o["status"] in ("approved", "countered", "accepted", "auto_approved") for o in offers),
        "booking": any(b["status"] in ("confirmed", "paid") for b in bookings),
        "advance": stage == "booked",
    }
    steps, current_found = [], False
    for key, (title, how) in STEP_HELP.items():
        st = "done" if done[key] else ("now" if not current_found else "todo")
        if st == "now":
            current_found = True
        steps.append({"key": key, "title": title, "how": how, "state": st})
    return steps


def _rm_or_404(token: str) -> dict:
    rm = team_access.by_token(token, "sales")
    if not rm:
        raise HTTPException(404, "This link is not active. Ask management for a new one.")
    return rm


def _my_lead(rm: dict, lead_id: int) -> dict:
    lead = db.get_lead(lead_id)
    if not lead or (lead.get("rm_name") or "") != rm["name"]:
        raise HTTPException(404, "Not your buyer.")
    return lead


@router.get("/s/{token}/manifest.json")
def sales_manifest(token: str):
    _rm_or_404(token)
    return _manifest(f"{get_settings().business.get('name', '')} Sales", f"/s/{token}")


@router.get("/s/{token}", response_class=HTMLResponse)
def sales_lobby(token: str):
    rm = _rm_or_404(token)
    now = get_settings().now()
    base = f"/s/{token}"
    calls = db.q("SELECT c.*, l.name, l.phone, l.temperature, l.stage FROM call_tasks c JOIN leads l ON l.id = c.lead_id "
                 "WHERE c.status IN ('open','attempted') AND l.rm_name = ? ORDER BY c.due_at", (rm["name"],))
    due_rows = ""
    n_over = 0
    for c in calls:
        due = db.parse_dt(c["due_at"])
        if due > now + timedelta(hours=3):
            continue
        over = due < now
        n_over += over
        due_rows += (f'<div class="row"><a class="lead" href="{base}/lead/{c["lead_id"]}"><b>{escape(c["name"] or "")}</b> '
                     f'{_temp(c["temperature"])}{"<span class=\"pill over\">overdue</span>" if over else ""}<br>'
                     f'<span class="muted">{escape(c["purpose"])} · {_when(c["due_at"])}</span></a>'
                     f'<a class="btn g" href="tel:{_tel(c["phone"])}">Call</a></div>')
    drafts = db.q("SELECT d.*, l.name FROM drafts d JOIN leads l ON l.id = d.lead_id WHERE d.status = 'pending' "
                  "AND l.rm_name = ? ORDER BY d.id", (rm["name"],))
    draft_rows = "".join(f'<div class="row"><a class="lead" href="{base}/lead/{d["lead_id"]}#drafts"><b>{escape(d["name"] or "")}</b>'
                         f'<br><span class="muted">{escape(d["text"][:90])}…</span></a>'
                         f'<a class="btn grey" href="{base}/lead/{d["lead_id"]}#drafts">Review</a></div>' for d in drafts)
    vis = db.q("SELECT v.*, l.name FROM site_visits v JOIN leads l ON l.id = v.lead_id WHERE v.status = 'scheduled' "
               "AND l.rm_name = ? ORDER BY v.scheduled_at", (rm["name"],))
    vis_rows = "".join(f'<div class="row"><a class="lead" href="{base}/lead/{v["lead_id"]}"><b>{escape(v["name"] or "")}</b>'
                       f'<br><span class="muted">{escape(v["project"])} · {_when(v["scheduled_at"])} · host {escape(v["site_person"])}'
                       f'{" · confirmed ✓" if v["confirmed_at"] else ""}</span></a></div>' for v in vis)
    leads_ = db.q("SELECT * FROM leads WHERE rm_name = ? AND stage NOT IN ('lost') ORDER BY "
                  "CASE temperature WHEN 'hot' THEN 0 WHEN 'warm' THEN 1 ELSE 2 END, score DESC", (rm["name"],))
    lrows = ""
    for l in leads_:
        cur = next((s for s in lead_steps(l) if s["state"] == "now"), None)
        lrows += (f'<div class="row"><a class="lead" href="{base}/lead/{l["id"]}"><b>{escape(l["name"] or l["phone"] or "")}</b> '
                  f'{_temp(l["temperature"])}<br><span class="muted">Next: {escape(cur["title"] if cur else "Booked ✓")} · '
                  f'{escape(l["unit_type"] or "")} {pricing.fmt_money(l["budget_max"]) if l["budget_max"] else ""} · '
                  f'{escape(l["city"] or "")}</span></a></div>')
    body = f"""<h2>Hi {escape(rm['name'])} 👋</h2>
<div class="card"><h3>📞 Calls to make now{f'<span class="badge">{n_over} overdue</span>' if n_over else ''}</h3>
{due_rows or '<p class="muted">No calls due right now. Great job!</p>'}</div>
<div class="card"><h3>✍️ Messages to approve{f'<span class="badge">{len(drafts)}</span>' if drafts else ''}</h3>
{draft_rows or '<p class="muted">Nothing waiting.</p>'}</div>
<div class="card"><h3>🏠 Upcoming site visits</h3>{vis_rows or '<p class="muted">None booked.</p>'}</div>
<div class="card"><h3>My buyers ({len(leads_)})</h3>{lrows or '<p class="muted">No buyers assigned yet.</p>'}</div>"""
    return _shell("Sales portal", rm["name"], base, body, f"{base}/manifest.json")


@router.get("/s/{token}/lead/{lead_id}", response_class=HTMLResponse)
def sales_lead(token: str, lead_id: int, msg: str = ""):
    rm = _rm_or_404(token)
    lead = _my_lead(rm, lead_id)
    base = f"/s/{token}"
    steps = lead_steps(lead)
    step_html = "".join(f'<li class="{s["state"]}"><span class="dot">{"✓" if s["state"] == "done" else i}</span>'
                        f'<div><b>{escape(s["title"])}</b>{"<br><span class=muted>" + escape(s["how"]) + "</span>" if s["state"] == "now" else ""}'
                        f'</div></li>' for i, s in enumerate(steps, 1))
    task = db.q1("SELECT * FROM call_tasks WHERE lead_id = ? AND status IN ('open','attempted') ORDER BY id DESC LIMIT 1",
                 (lead_id,))
    task_html = ""
    if task:
        outcomes = "".join(f'<option value="{o}">{o.replace("_", " ")}</option>' for o in team.CALL_OUTCOMES)
        task_html = f"""<div class="card" style="border:2px solid #2b62e3"><h3>📞 Your next call — {escape(task['purpose'])}</h3>
<p class="muted">Due {_when(task['due_at'])}</p><div class="brief">{escape(task['brief'] or '')}</div>
<div class="btns"><a class="btn g" href="tel:{_tel(lead['phone'])}">Call {escape(lead['name'] or '')}</a>
<a class="btn grey" href="{_wa(lead['phone'])}">WhatsApp</a></div>
<form method="post" action="{base}/call/{task['id']}"><label>How did the call go?</label><select name="outcome">{outcomes}</select>
<label>What did you discuss?</label><textarea name="summary" rows="3" placeholder="e.g. Wife decides, wants east facing, visit Saturday 11am"></textarea>
<label>Next step agreed</label><input type="text" name="next_step" placeholder="e.g. Site visit Sat 11am">
<label>Call back when? (if needed)</label><input type="text" name="callback_time" placeholder="e.g. Tomorrow 6pm">
<div class="btns"><button class="btn">Save call</button></div></form></div>"""
    drafts = db.q("SELECT * FROM drafts WHERE lead_id = ? AND status = 'pending' ORDER BY id", (lead_id,))
    draft_html = "".join(f"""<form method="post" action="{base}/draft/{d['id']}" class="card" id="drafts">
<h3>✍️ AI draft — check and send</h3><textarea name="text" rows="4">{escape(d['text'])}</textarea>
<div class="btns"><button class="btn" name="action" value="send">Send</button>
<button class="btn grey" name="action" value="drop">Drop</button></div></form>""" for d in drafts)
    strat = json.loads(lead["strategy"]) if lead.get("strategy") else None
    strat_html = ""
    if strat:
        strat_html = '<div class="card"><h3>🎯 AI strategy for this buyer</h3>' + "".join(
            f"<p><b>{escape(k.replace('_', ' ').capitalize())}:</b> {escape(' · '.join(v) if isinstance(v, list) else str(v))}</p>"
            for k, v in strat.items() if k in ("situation", "buying_motivators", "objections_and_answers",
                                               "recommended_unit", "price_plan", "next_actions", "risk")) + "</div>"
    msgs = db.q("SELECT * FROM (SELECT * FROM interactions WHERE lead_id = ? ORDER BY id DESC LIMIT 25) ORDER BY id",
                (lead_id,))
    chat = "".join(f'<div class="msg {"in" if m["direction"] == "in" else "call" if m["direction"] == "call" else "out"}">'
                   f'<span class="muted">{_when(m["created_at"])} · {escape(m["author"])}</span><br>{escape(m["content"])}</div>'
                   for m in msgs)
    body = f"""<p><a href="{base}">← All my buyers</a></p>{f'<div class="card" style="background:#e9f7ef">{escape(msg)}</div>' if msg else ''}
<div class="card"><h2>{escape(lead['name'] or '')} {_temp(lead['temperature'])}</h2>
<p class="muted">{escape(lead['phone'] or '')} · {escape(lead['city'] or '')} · {escape(lead['unit_type'] or '?')} ·
budget {pricing.fmt_money(lead['budget_max'])} · {escape(lead['timeline'] or '')}</p>
<div class="btns"><a class="btn g" href="tel:{_tel(lead['phone'])}">Call</a><a class="btn grey" href="{_wa(lead['phone'])}">WhatsApp</a></div></div>
{task_html}{draft_html}
<div class="card"><h3>Path to booking</h3><ul class="steps">{step_html}</ul></div>
{strat_html}
<div class="card"><h3>Conversation</h3>{chat or '<p class="muted">No messages yet.</p>'}
<form method="post" action="{base}/lead/{lead_id}/message"><label>Send a WhatsApp yourself</label>
<textarea name="text" rows="2"></textarea><div class="btns"><button class="btn grey">Send</button></div></form></div>
<div class="card"><h3>Notes</h3><div class="brief">{escape(lead.get('memory') or '-')}</div></div>"""
    return _shell(lead["name"] or "Buyer", rm["name"], base, body, f"{base}/manifest.json")


@router.post("/s/{token}/call/{task_id}")
async def sales_log_call(token: str, task_id: int, request: Request):
    rm = _rm_or_404(token)
    t = db.q1("SELECT * FROM call_tasks WHERE id = ?", (task_id,))
    if not t:
        raise HTTPException(404)
    _my_lead(rm, t["lead_id"])
    f = await request.form()
    outcome = str(f.get("outcome") or "spoke")
    if outcome not in team.CALL_OUTCOMES:
        outcome = "spoke"
    data = {k: str(f.get(k, "") or "").strip() for k in ("summary", "next_step", "callback_time")}
    events.dispatch(events.call_logged, task_id, outcome, data)
    note = "Call saved — the AI will follow up on WhatsApp." if outcome == "spoke" else \
        "Saved — the AI will message them and set another call at a different time."
    return RedirectResponse(f"/s/{token}/lead/{t['lead_id']}?msg={note}", status_code=303)


@router.post("/s/{token}/draft/{draft_id}")
async def sales_draft(token: str, draft_id: int, request: Request):
    rm = _rm_or_404(token)
    d = db.q1("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    if not d:
        raise HTTPException(404)
    _my_lead(rm, d["lead_id"])
    f = await request.form()
    if f.get("action") == "drop":
        res = team.drop_draft(draft_id)
    else:
        text = str(f.get("text") or "")
        same = " ".join(text.split()) == " ".join(d["text"].split())
        res = team.approve_draft(draft_id, None if same or not text.strip() else text.replace("\r\n", "\n").strip())
    return RedirectResponse(f"/s/{token}/lead/{d['lead_id']}?msg={res}", status_code=303)


@router.post("/s/{token}/lead/{lead_id}/message")
async def sales_message(token: str, lead_id: int, request: Request):
    rm = _rm_or_404(token)
    lead = _my_lead(rm, lead_id)
    text = str((await request.form()).get("text") or "").strip()
    if text and not lead["opted_out"]:
        team.deliver(lead_id, text, "whatsapp", author="rm")
    return RedirectResponse(f"/s/{token}/lead/{lead_id}?msg=Sent.", status_code=303)


# ============================================================ site team app

def _host_or_404(token: str) -> dict:
    h = team_access.by_token(token, "site")
    if not h:
        raise HTTPException(404, "This link is not active. Ask management for a new one.")
    return h


def _my_visits(h: dict) -> list[dict]:
    rows = db.q("SELECT v.*, l.name, l.phone, l.unit_type, l.budget_max, l.rm_name FROM site_visits v "
                "JOIN leads l ON l.id = v.lead_id WHERE v.kind = 'site' AND v.status != 'rescheduled' "
                "ORDER BY v.scheduled_at")
    return [r for r in rows if db.normalize_phone(r["site_person_phone"]) == h["phone"]]


def _my_visit(h: dict, visit_id: int) -> dict:
    v = next((x for x in _my_visits(h) if x["id"] == visit_id), None)
    if not v:
        raise HTTPException(404, "Not your visit.")
    return v


@router.get("/site/{token}/manifest.json")
def site_manifest(token: str):
    _host_or_404(token)
    return _manifest(f"{get_settings().business.get('name', '')} Site", f"/site/{token}")


@router.get("/site/{token}", response_class=HTMLResponse)
def site_lobby(token: str):
    h = _host_or_404(token)
    base = f"/site/{token}"
    now = get_settings().now()
    today, upcoming, report_due = [], [], []
    for v in _my_visits(h):
        when = db.parse_dt(v["scheduled_at"])
        if v["status"] == "scheduled" and when < now - timedelta(minutes=30):
            report_due.append(v)
        elif v["status"] == "scheduled" and when.date() == now.date():
            today.append(v)
        elif v["status"] == "scheduled" and when < now + timedelta(days=8):
            upcoming.append(v)

    def rows(vs, extra=""):
        return "".join(f'<div class="row"><a class="lead" href="{base}/visit/{v["id"]}"><b>{_when(v["scheduled_at"])}</b> · '
                       f'{escape(v["name"] or "")}<br><span class="muted">{escape(v["project"])} · {escape(v["unit_type"] or "")}'
                       f'{" · confirmed ✓" if v["confirmed_at"] else ""}{" · arrived ✓" if v["arrived_at"] else ""}</span></a>'
                       f'{extra}<a class="btn g" href="tel:{_tel(v["phone"])}">Call</a></div>' for v in vs)
    body = f"""<h2>Hi {escape(h['name'])} 👋</h2>
{f'<div class="card" style="border:2px solid #c9372c"><h3>📝 Reports to fill</h3>{rows(report_due)}</div>' if report_due else ''}
<div class="card"><h3>🏠 Today's visits</h3>{rows(today) or '<p class="muted">No visits today.</p>'}</div>
<div class="card"><h3>📅 Coming up</h3>{rows(upcoming) or '<p class="muted">Nothing booked yet.</p>'}</div>"""
    return _shell("Site visits", h["name"], base, body, f"{base}/manifest.json")


@router.get("/site/{token}/visit/{visit_id}", response_class=HTMLResponse)
def site_visit(token: str, visit_id: int, msg: str = ""):
    h = _host_or_404(token)
    v = _my_visit(h, visit_id)
    base = f"/site/{token}"
    rm = team.rm_for(db.get_lead(v["lead_id"]))
    reported = bool(v["form_data"]) or v["status"] in ("completed", "no_show")
    steps = [("Confirm with the customer", "Call the day before: confirm time, who is coming, share the location.",
              bool(v["confirmed_at"]), f'<form method="post" action="{base}/visit/{visit_id}/confirm"><button class="btn">Called &amp; confirmed</button></form>'),
             ("Customer arrived", "Tap when they reach the site — the salesperson is told instantly.",
              bool(v["arrived_at"]), f'<form method="post" action="{base}/visit/{visit_id}/arrived"><button class="btn g">They have arrived</button></form>'),
             ("Show the right homes", f"Looking for: {v['unit_type'] or '?'}, budget {pricing.fmt_money(v['budget_max'])}. "
                                      f"Notes: {v['feedback'] or '-'}", reported or bool(v["arrived_at"]), ""),
             ("Fill the visit report", "2 minutes, right after the visit. The AI uses it to plan the close.",
              reported, f'<a class="btn" href="/f/visit/{v["form_token"]}">Fill visit report</a> '
                        f'<form method="post" action="{base}/visit/{visit_id}/noshow" style="display:inline">'
                        f'<button class="btn red">Customer didn\'t come</button></form>')]
    cur = next((i for i, s in enumerate(steps) if not s[2]), None)
    sh = ""
    for i, (title, how, done, action) in enumerate(steps):
        state = "done" if done else ("now" if i == cur else "todo")
        sh += (f'<li class="{state}"><span class="dot">{"✓" if done else i + 1}</span><div><b>{escape(title)}</b><br>'
               f'<span class="muted">{escape(how)}</span>{"<div class=btns>" + action + "</div>" if state == "now" and action else ""}'
               f'</div></li>')
    body = f"""<p><a href="{base}">← All visits</a></p>{f'<div class="card" style="background:#e9f7ef">{escape(msg)}</div>' if msg else ''}
<div class="card"><h2>{escape(v['name'] or '')}</h2><p class="muted">{_when(v['scheduled_at'])} · {escape(v['project'])}</p>
<div class="btns"><a class="btn g" href="tel:{_tel(v['phone'])}">Call customer</a><a class="btn grey" href="{_wa(v['phone'])}">WhatsApp</a>
<a class="btn grey" href="tel:{_tel(rm.get('phone'))}">Call {escape(rm.get('name', 'salesperson'))}</a></div></div>
<div class="card"><h3>Steps</h3><ul class="steps">{sh}</ul></div>"""
    return _shell("Visit", h["name"], base, body, f"{base}/manifest.json")


def _tell_rm(v: dict, text: str) -> None:
    rm = team.rm_for(db.get_lead(v["lead_id"]))
    if rm.get("phone"):
        channels.notify_staff(rm["phone"], text)


@router.post("/site/{token}/visit/{visit_id}/confirm")
def site_confirm(token: str, visit_id: int):
    h = _host_or_404(token)
    v = _my_visit(h, visit_id)
    db.update("site_visits", visit_id, {"confirmed_at": db.now_iso()})
    db.audit(v["lead_id"], "site_person", "visit_confirmed", {"visit_id": visit_id, "by": h["name"]})
    _tell_rm(v, f"✓ {h['name']} confirmed {v['name']}'s visit to {v['project']} ({_when(v['scheduled_at'])}).")
    return RedirectResponse(f"/site/{token}/visit/{visit_id}?msg=Confirmed. The salesperson has been told.", status_code=303)


@router.post("/site/{token}/visit/{visit_id}/arrived")
def site_arrived(token: str, visit_id: int):
    h = _host_or_404(token)
    v = _my_visit(h, visit_id)
    db.update("site_visits", visit_id, {"arrived_at": db.now_iso()})
    db.audit(v["lead_id"], "site_person", "visit_arrived", {"visit_id": visit_id, "by": h["name"]})
    _tell_rm(v, f"🏠 {v['name']} has arrived at {v['project']} — {h['name']} is with them now.")
    return RedirectResponse(f"/site/{token}/visit/{visit_id}?msg=Noted. After the visit, please fill the report.",
                            status_code=303)


@router.post("/site/{token}/visit/{visit_id}/noshow")
def site_noshow(token: str, visit_id: int):
    h = _host_or_404(token)
    v = _my_visit(h, visit_id)
    events.dispatch(events.visit_outcome, visit_id, {"attended": "no", "notes": f"no-show reported by {h['name']}"})
    return RedirectResponse(f"/site/{token}?", status_code=303)
