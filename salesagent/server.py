"""HTTP server: lead + WhatsApp webhooks, and the owner dashboard."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import tempfile
from contextlib import asynccontextmanager
from html import escape

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import (channels, db, events, learning, leads, marketing, pipeline, pricing, scheduler, settings_form, team,
               visits)
from .config import (config_path, env, get_settings, reload_settings, validate_config,
                     writable_config_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
security = HTTPBasic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.conn()
    t = None
    if env("DISABLE_SCHEDULER") != "1":
        t = scheduler.start_background(60)
    yield
    if t:
        t.stop.set()


app = FastAPI(title="AI Sales Agent", lifespan=lifespan)


def _include_routers() -> None:
    from .web_inventory import router as inventory_router
    from .web_portals import router as portals_router
    from .web_public import router as public_router
    app.include_router(inventory_router)
    app.include_router(public_router)
    app.include_router(portals_router)


def check_auth_header(header: str | None) -> str:
    """Accepts the browser's Basic login (password in either box, stray spaces ignored) or, for automation,
    `Authorization: Bearer <DASHBOARD_API_TOKEN>`. Raises 401/503 otherwise."""
    import base64
    pw = env("DASHBOARD_PASSWORD").strip().strip('"').strip("'")
    token = env("DASHBOARD_API_TOKEN").strip().strip('"').strip("'")
    if not pw and not token:
        raise HTTPException(503, "Set DASHBOARD_PASSWORD in .env first")
    scheme, _, value = (header or "").partition(" ")
    value = value.strip()
    if scheme.lower() == "bearer" and token and len(token) >= 16 and secrets.compare_digest(value.encode(), token.encode()):
        return "owner"
    if scheme.lower() == "basic" and pw:
        try:
            user, _, given = base64.b64decode(value).decode("utf-8", "replace").partition(":")
        except ValueError:
            user, given = "", ""
        if secrets.compare_digest(given.strip().encode(), pw.encode()) or \
                secrets.compare_digest(user.strip().encode(), pw.encode()):
            return "owner"
        raise HTTPException(401, "Wrong password", headers={"WWW-Authenticate": "Basic"})
    if scheme.lower() == "bearer":
        if not token:
            raise HTTPException(401, "DASHBOARD_API_TOKEN is not set", headers={"WWW-Authenticate": "Basic"})
        if len(token) < 16:
            raise HTTPException(401, "DASHBOARD_API_TOKEN is too short (use 16+ characters)",
                                headers={"WWW-Authenticate": "Basic"})
        raise HTTPException(401, "Wrong access key", headers={"WWW-Authenticate": "Basic"})
    raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Basic"})


def owner_auth(request: Request) -> str:
    return check_auth_header(request.headers.get("authorization"))


def _check_secret(given: str | None) -> None:
    want = env("LEAD_WEBHOOK_SECRET")
    if not want or not given or not secrets.compare_digest(given, want):
        raise HTTPException(401, "bad webhook secret")


# ============================ webhooks ============================

@app.post("/webhook/lead")
async def lead_webhook(request: Request, x_webhook_secret: str | None = Header(None)):
    """Website forms, Meta/Google lead ads (via Zapier/Make), property portals, etc."""
    _check_secret(x_webhook_secret)
    data = await request.json()
    consent = bool(data.pop("consent", True))
    try:
        lead, created = leads.upsert_lead(data, consent=consent)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if created and consent:
        events.dispatch(events.new_lead, lead["id"])
    return {"ok": True, "lead_id": lead["id"], "created": created}


@app.post("/webhook/email")
async def email_webhook(request: Request, x_webhook_secret: str | None = Header(None)):
    """Inbound email replies (from your mail provider's inbound-parse webhook): {from, text}."""
    _check_secret(x_webhook_secret)
    data = await request.json()
    events.dispatch(events.inbound_message, None, data["from"], data["text"], "email")
    return {"ok": True}


@app.get("/webhook/meta")
async def meta_verify(request: Request):
    p = request.query_params
    want = env("META_VERIFY_TOKEN") or env("WHATSAPP_VERIFY_TOKEN")
    if p.get("hub.mode") == "subscribe" and want and p.get("hub.verify_token") == want:
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise HTTPException(403)


@app.post("/webhook/meta")
async def meta_leads(request: Request, x_hub_signature_256: str | None = Header(None)):
    """Meta lead ads (Page 'leadgen' webhook)."""
    from . import lead_sources
    body = await request.body()
    if not lead_sources.meta_signature_ok(body, x_hub_signature_256):
        raise HTTPException(401, "bad signature")
    events.dispatch(lead_sources.handle_meta_webhook, json.loads(body or b"{}"))
    return {"ok": True}


@app.post("/webhook/portal-email")
async def portal_email(request: Request, x_webhook_secret: str | None = Header(None)):
    """Forwarded portal enquiry emails (from an email-forwarding service): {from, subject, text, message_id}."""
    from . import lead_sources
    _check_secret(x_webhook_secret)
    d = await request.json()
    lead_id = lead_sources.process_email(d.get("from", ""), d.get("subject", ""), d.get("text") or d.get("html") or "",
                                         d.get("message_id", ""))
    return {"ok": True, "lead_id": lead_id}


@app.get("/webhook/whatsapp")
async def wa_verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == env("WHATSAPP_VERIFY_TOKEN"):
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise HTTPException(403)


@app.post("/webhook/whatsapp")
async def wa_inbound(request: Request, x_hub_signature_256: str | None = Header(None)):
    body = await request.body()
    app_secret = env("WHATSAPP_APP_SECRET")
    if app_secret:
        digest = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        if not x_hub_signature_256 or not hmac.compare_digest(digest, x_hub_signature_256):
            raise HTTPException(401, "bad signature")
    payload = json.loads(body or b"{}")
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                phone = "+" + m.get("from", "")
                if m.get("type") == "text":
                    text = m["text"]["body"]
                elif m.get("type") == "button":
                    text = m["button"].get("text", "")
                elif m.get("type") == "interactive":
                    it = m["interactive"]
                    text = (it.get("button_reply") or it.get("list_reply") or {}).get("title", "")
                else:
                    text = f"[customer sent a {m.get('type')} message]"
                reply = events.staff_command(phone, text)
                if reply is not None:
                    channels.notify_staff(phone, reply)
                    continue
                from . import lead_sources
                ref = lead_sources.ctwa_referral(m)
                if ref:
                    lead_sources.tag_ctwa_lead(phone, names.get(m.get("from")) or "", ref)
                lead = db.find_lead_by_phone(phone)
                if not lead and names.get(m.get("from")):
                    leads.upsert_lead({"phone": phone, "name": names[m["from"]], "source": "inbound_whatsapp"})
                events.dispatch(events.inbound_message, phone, None, text, "whatsapp")
    return {"ok": True}


# ============================ dashboard ============================

CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}
header{background:#1d2330;color:#fff;padding:12px 24px;display:flex;gap:24px;align-items:center}
header a{color:#cfd6e4;text-decoration:none}header b{font-size:18px}
main{padding:20px 24px;max-width:1200px;margin:auto}
.card{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:16px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:7px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
.stages{display:flex;gap:8px;flex-wrap:wrap}.stage{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:10px 14px;min-width:90px}
.stage b{display:block;font-size:22px}.pill{display:inline-block;padding:2px 8px;border-radius:99px;background:#eef1f6;font-size:12px}
.hot{background:#ffe1dc}.warm{background:#fff2d6}.cold{background:#e1ecff}
button{background:#2b62e3;color:#fff;border:0;border-radius:6px;padding:6px 12px;cursor:pointer}
button.red{background:#c9372c}button.grey{background:#6b7385}
input,textarea,select{padding:6px;border:1px solid #cfd4dd;border-radius:6px;font:inherit}
.msg{padding:6px 10px;border-radius:8px;margin:4px 0;max-width:75%;white-space:pre-wrap}
.in{background:#eef1f6}.out{background:#dcf3e4;margin-left:auto}.sys{background:#fff7e0;margin-left:auto;font-size:13px}
.row{display:flex;flex-direction:column}
header{flex-wrap:wrap;row-gap:8px;position:sticky;top:0;z-index:5}
.card{overflow-x:auto}
.grid2{display:grid;grid-template-columns:1fr 1.4fr;gap:16px}.grid2>div{min-width:0}
.notice{background:#fff7e0;border:1px solid #f1d38a;border-radius:8px;padding:10px 14px;margin-bottom:16px}
@media (max-width:800px){
  header{padding:10px 12px;gap:14px;overflow-x:auto;flex-wrap:nowrap;white-space:nowrap}
  header b{font-size:15px}
  main{padding:12px}
  .grid2{grid-template-columns:1fr}
  .grid2>div:last-child{order:-1}
  .msg{max-width:90%}
  td,th{padding:6px 4px;font-size:13px}
  input,textarea,select{font-size:16px;max-width:100%}
  button{padding:10px 14px;font-size:15px}
  .stage{min-width:70px;padding:8px 10px}.stage b{font-size:18px}
}
"""


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#1d2330">
<link rel="manifest" href="/manifest.json"><link rel="icon" href="/icon.svg"><link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes"><style>{CSS}</style></head><body>
<header><b>{escape(get_settings().business['name'])} · AI Sales</b><a href="/">Overview</a><a href="/leads">Leads</a>
<a href="/calls">Calls</a><a href="/visits">Visits</a><a href="/team">Team</a><a href="/inventory">Inventory</a><a href="/commissions">Commissions</a>
<a href="/sources">Lead sources</a><a href="/campaigns">Campaigns</a><a href="/insights">Learning</a>
<a href="/reports">Reports</a>{'<a href="/test">Test</a>' if test_mode() else ''}<a href="/settings">Settings</a></header>
<main>{_storage_banner()}{'<div class="notice">TEST MODE — nothing is sent to real customers. Messages appear in the conversation and in <a href="/test/outbox">Outbox</a>.</div>' if test_mode() else ''}{body}</main></body></html>""")


def _storage_banner() -> str:
    from .config import storage_status
    st = storage_status()
    if st["persistent"]:
        return ""
    return ('<div class="notice" style="background:#ffe9e6;border-color:#f3b2a9"><b>⚠️ Data is not on a permanent '
            'disk.</b> Leads, inventory and settings are lost every time the app redeploys. In Railway: open the '
            'sales-agent service, attach a volume (right-click the service → Attach volume) and redeploy.</div>')


def test_mode() -> bool:
    return channels.mode() != "live"


def _temp(t: str) -> str:
    return f'<span class="pill {escape(t or "")}">{escape(t or "-")}</span>'


@app.get("/", response_class=HTMLResponse)
def overview(_: str = Depends(owner_auth)):
    counts = {r["stage"]: r["n"] for r in db.q("SELECT stage, COUNT(*) n FROM leads GROUP BY stage")}
    stages = "".join(f'<div class="stage">{s.replace("_", " ")}<b>{counts.get(s, 0)}</b></div>'
                     for s in pipeline.STAGES)
    offers = db.q("SELECT o.*, l.name, l.score, l.temperature FROM offers o JOIN leads l ON l.id = o.lead_id "
                  "WHERE o.status IN ('pending_approval','blocked_floor') ORDER BY o.id")
    s = get_settings()
    orows = ""
    for o in offers:
        unit = db.q1("SELECT floor_price FROM units WHERE id = ?", (o["unit_id"],)) if o.get("unit_id") else None
        floor = (unit or {}).get("floor_price")
        orows += f"""<tr><td>#{o['id']}<br>{'<span class="pill hot">below floor</span>' if o['status'] == 'blocked_floor' else ''}</td>
<td><a href="/leads/{o['lead_id']}">{escape(o['name'] or '')}</a><br>score {o['score']} {_temp(o['temperature'])}</td>
<td>{escape(o['unit_type'])} · {escape(o['project'])}<br>List {pricing.fmt_money(o['list_price'])}<br>
<b>Proposed {pricing.fmt_money(o['offered_price'])}</b> ({o['discount_pct']}% off)<br>
Floor {pricing.fmt_money(floor)} · Customer ask {pricing.fmt_money(o['customer_ask'])}</td>
<td>Extras: {escape(', '.join(json.loads(o['concessions'] or '[]')) or 'none')}<br>Terms: {escape(o['payment_terms'] or '-')}<br>
<i>{escape(o['justification'] or '')}</i></td>
<td><form method="post" action="/offers/{o['id']}/decide">
<input name="note" placeholder="note to AI (optional)" style="width:180px"><br>
<input name="counter_price" placeholder="counter price" style="width:120px"><br>
<button name="decision" value="approve">Approve</button> <button name="decision" value="counter" class="grey">Counter</button>
<button name="decision" value="reject" class="red">Reject</button></form></td></tr>"""
    bookings = db.q("SELECT b.*, l.name, o.unit_type, o.project, o.offered_price, o.owner_counter_price FROM bookings b "
                    "JOIN leads l ON l.id=b.lead_id JOIN offers o ON o.id=b.offer_id WHERE b.status='awaiting_owner'")
    brows = "".join(f"""<tr><td>B{b['id']}</td><td><a href="/leads/{b['lead_id']}">{escape(b['name'] or '')}</a></td>
<td>{escape(b['unit_type'])} · {escape(b['project'])} · {pricing.fmt_money(b['owner_counter_price'] or b['offered_price'])}</td>
<td>Token {pricing.fmt_money(b['token_amount'])}<br>{escape(b['notes'] or '')}</td>
<td><form method="post" action="/bookings/{b['id']}/decide"><input name="note" placeholder="note">
<button name="decision" value="confirm">Confirm booking</button> <button name="decision" value="hold" class="grey">Hold</button></form></td></tr>"""
                    for b in bookings)
    drafts = db.q("SELECT d.*, l.name FROM drafts d JOIN leads l ON l.id = d.lead_id WHERE d.status = 'pending' "
                  "ORDER BY d.id")
    drows = "".join(f"""<tr><td>D{d['id']}<br>{escape(d['rm_name'] or '')}</td><td><a href="/leads/{d['lead_id']}">{escape(d['name'] or '')}</a></td>
<td><form method="post" action="/drafts/{d['id']}"><textarea name="text" rows="3" style="width:100%">{escape(d['text'])}</textarea>
<button name="action" value="send">Send</button> <button name="action" value="drop" class="grey">Drop</button></form></td></tr>"""
                    for d in drafts)
    pays = db.q("SELECT b.*, l.name, l.phone FROM bookings b JOIN leads l ON l.id = b.lead_id WHERE b.status = 'confirmed'")
    prows = "".join(f"""<tr><td>B{b['id']}</td><td><a href="/leads/{b['lead_id']}">{escape(b['name'] or '')}</a> {escape(b['phone'] or '')}</td>
<td>Advance {pricing.fmt_money(b['token_amount'])}</td><td><form method="post" action="/bookings/{b['id']}/paid">
<input name="amount" placeholder="amount received" style="width:130px"> <input name="ref" placeholder="UTR / receipt no">
<button>Mark advance received</button></form></td></tr>""" for b in pays)
    human = db.q("SELECT id, name, stage, phone FROM leads WHERE needs_human = 1")
    hrows = "".join(f'<tr><td><a href="/leads/{h["id"]}">#{h["id"]} {escape(h["name"] or "")}</a></td><td>{escape(h["phone"] or "")}</td>'
                    f'<td>{h["stage"]}</td><td><form method="post" action="/leads/{h["id"]}/resume"><input name="note" placeholder="what happened">'
                    f'<button>Hand back to AI</button></form></td></tr>' for h in human)
    body = f"""<div class="card"><h3>Pipeline</h3><div class="stages">{stages}</div></div>
<div class="card"><h3>Price approvals waiting ({len(offers)})</h3><table>{orows or '<tr><td>Nothing waiting.</td></tr>'}</table></div>
<div class="card"><h3>Bookings to confirm ({len(bookings)})</h3><table>{brows or '<tr><td>Nothing waiting.</td></tr>'}</table></div>
<div class="card"><h3>Advance payments awaited ({len(pays)})</h3><table>{prows or '<tr><td>None.</td></tr>'}</table>
<small>Mark received only after checking the builder's bank account.</small></div>
<div class="card"><h3>Message drafts waiting for salespeople ({len(drafts)})</h3><table>{drows or '<tr><td>None.</td></tr>'}</table></div>
{_partner_alerts()}
<div class="card"><h3>Leads needing you ({len(human)})</h3><table>{hrows or '<tr><td>None.</td></tr>'}</table></div>"""
    return page("Overview", body)


def _partner_alerts() -> str:
    from . import partners
    disputed = db.q("SELECT r.id, r.lead_id, r.builder_note, l.name FROM registrations r JOIN leads l ON "
                    "l.id = r.lead_id WHERE r.status = 'disputed' ORDER BY r.id DESC LIMIT 20")
    t = partners.commission_totals()
    if not disputed and not t["outstanding"]:
        return ""
    rows = "".join(f'<li>R{d["id"]} <a href="/leads/{d["lead_id"]}">{escape(d["name"] or "")}</a>: '
                   f'{escape(d["builder_note"] or "")}</li>' for d in disputed)
    html = '<div class="card"><h3>Channel partner</h3>'
    if rows:
        html += f"<p><b>Builder disputed these client registrations:</b></p><ul>{rows}</ul>"
    if t["outstanding"]:
        overdue = f" — overdue {pricing.fmt_money(t['overdue'])}" if t["overdue"] else ""
        html += (f"<p>Commission outstanding: <b>{pricing.fmt_money(t['outstanding'])}</b>{overdue}"
                 f' · <a href="/commissions">Commissions</a></p>')
    return html + "</div>"


@app.post("/offers/{offer_id}/decide")
def decide_offer(offer_id: int, decision: str = Form(...), note: str = Form(""), counter_price: str = Form(""),
                 _: str = Depends(owner_auth)):
    price = events.parse_amount(counter_price) if counter_price else None
    if decision == "counter" and not price:
        raise HTTPException(400, "Enter a counter price")
    events.owner_offer_decision(offer_id, decision, price, note)
    return RedirectResponse("/", status_code=303)


@app.post("/bookings/{booking_id}/decide")
def decide_booking(booking_id: int, decision: str = Form(...), note: str = Form(""), _: str = Depends(owner_auth)):
    events.owner_booking_decision(booking_id, decision == "confirm", note)
    return RedirectResponse("/", status_code=303)


@app.get("/leads", response_class=HTMLResponse)
def lead_list(stage: str = "", city: str = "", _: str = Depends(owner_auth)):
    where, args = [], []
    if stage:
        where.append("stage = ?")
        args.append(stage)
    if city:
        where.append("lower(city) = lower(?)")
        args.append(city)
    rows = db.q("SELECT * FROM leads " + (("WHERE " + " AND ".join(where) + " ") if where else "") +
                "ORDER BY score DESC, id DESC LIMIT 500", tuple(args))
    trs = "".join(f"""<tr><td><a href="/leads/{r['id']}">#{r['id']} {escape(r['name'] or '(no name)')}</a></td>
<td>{escape(r['phone'] or r['email'] or '')}</td><td>{escape(r['source'] or '')}</td><td>{escape(r['rm_name'] or '')}</td><td>{r['stage']}</td><td>{r['score']}</td>
<td>{_temp(r['temperature'])}</td><td>{escape(r['unit_type'] or '')} {pricing.fmt_money(r['budget_max'])}</td>
<td>{escape((r['next_followup_at'] or '')[:16])}</td></tr>""" for r in rows)
    opts = "".join(f'<option {"selected" if s == stage else ""}>{s}</option>' for s in pipeline.STAGES)
    from . import inventory
    copts = "".join(f'<option {"selected" if c.lower() == city.lower() else ""}>{escape(c)}</option>'
                    for c in inventory.cities())
    body = f"""<div class="card"><form>Stage <select name="stage"><option value="">all</option>{opts}</select>
City <select name="city"><option value="">all</option>{copts}</select> <button>Filter</button></form></div>
<div class="card"><h3>Add a lead (walk-in, call, referral)</h3><form method="post" action="/leads/new">
<input name="name" placeholder="Name" required> <input name="phone" placeholder="Phone" required> <input name="email" placeholder="Email">
<input name="city" placeholder="City (Chennai / Bangalore)">
<select name="source"><option>walk_in</option><option>referral</option><option>website</option><option>portal</option><option>meta_ads</option><option>google_ads</option><option>other</option></select>
<input name="unit_type" placeholder="2BHK / 3BHK"> <input name="budget_max" placeholder="Budget"> <input name="notes" placeholder="Notes">
<label><input type="checkbox" name="consent" checked> Customer agreed to be contacted</label> <button>Add & let AI contact</button></form>
<form method="post" action="/import" enctype="multipart/form-data" style="margin-top:10px">Import portal/ads CSV:
<input type="file" name="file" accept=".csv" required> <input name="source" value="portal"> <button class="grey">Import</button></form></div>
<div class="card"><table><tr><th>Lead</th><th>Contact</th><th>Source</th><th>Sales</th><th>Stage</th><th>Score</th><th>Temp</th><th>Wants</th><th>Next follow-up</th></tr>{trs}</table></div>"""
    return page("Leads", body)


@app.post("/leads/new")
def add_lead(name: str = Form(...), phone: str = Form(...), email: str = Form(""), city: str = Form(""),
             source: str = Form("walk_in"),
             unit_type: str = Form(""), budget_max: str = Form(""), notes: str = Form(""), consent: str = Form(""),
             _: str = Depends(owner_auth)):
    lead, created = leads.upsert_lead({"name": name, "phone": phone, "email": email, "city": city.title(),
                                       "source": source,
                                       "unit_type": unit_type, "budget_max": events.parse_amount(budget_max)
                                       if budget_max else None}, consent=bool(consent))
    if notes:
        db.update("leads", lead["id"], {"memory": f"Owner note: {notes}"})
    if created and consent:
        events.dispatch(events.new_lead, lead["id"])
    return RedirectResponse(f"/leads/{lead['id']}", status_code=303)


@app.post("/import")
async def import_leads(file: UploadFile = File(...), source: str = Form("csv_import"), _: str = Depends(owner_auth)):
    with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as f:
        f.write(await file.read())
        path = f.name
    res = leads.import_csv(path, source=source)
    for lead_id in res["new_ids"]:
        events.dispatch(events.new_lead, lead_id)
    return page("Import", f'<div class="card">New: {res["created"]}, merged with existing: {res["merged"]}, '
                          f'skipped (no phone/email): {res["failed"]}. The AI is contacting the new leads now.'
                          f'</div><a href="/leads">Back</a>')


@app.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(lead_id: int, _: str = Depends(owner_auth)):
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(404)
    msgs = db.q("SELECT * FROM interactions WHERE lead_id = ? ORDER BY id", (lead_id,))
    chat = "".join(
        f'<div class="msg {"in" if m["direction"] == "in" else "sys" if m["author"] != "agent" else "out"}">'
        f'<small>{escape(m["created_at"][:16])} · {escape(m["author"])} · {escape(m["channel"])}</small><br>'
        f'{escape(m["content"])}</div>' for m in msgs)
    vis = db.q("SELECT * FROM site_visits WHERE lead_id = ? ORDER BY id", (lead_id,))
    vrows = "".join(f"<tr><td>#{v['id']}</td><td>{escape(v['scheduled_at'])}</td><td>{escape(v['site_person'])}</td>"
                    f"<td>{v['status']}</td><td>{escape(v['interest_level'] or '')} {escape(v['feedback'] or '')}</td></tr>"
                    for v in vis)
    offers = db.q("SELECT * FROM offers WHERE lead_id = ? ORDER BY id", (lead_id,))
    orows = "".join(f"<tr><td>#{o['id']}</td><td>{escape(o['unit_type'])}</td><td>{pricing.fmt_money(o['offered_price'])}"
                    f" ({o['discount_pct']}%)</td><td>{o['status']}</td><td>{pricing.fmt_money(o['owner_counter_price'])}"
                    f" {escape(o['owner_note'] or '')}</td></tr>" for o in offers)
    log = db.q("SELECT * FROM audit WHERE lead_id = ? ORDER BY id DESC LIMIT 40", (lead_id,))
    lrows = "".join(f"<tr><td>{escape(a['created_at'][5:16])}</td><td>{escape(a['actor'])}</td><td>{escape(a['action'])}</td>"
                    f"<td><small>{escape((a['detail'] or '')[:300])}</small></td></tr>" for a in log)
    strat = json.loads(lead["strategy"]) if lead.get("strategy") else None
    strat_html = "".join(f"<p><b>{escape(k.replace('_', ' '))}:</b> {escape(' | '.join(v) if isinstance(v, list) else str(v))}</p>"
                         for k, v in strat.items()) if strat else "No strategy yet (written after the site visit)."
    calls = db.q("SELECT * FROM call_tasks WHERE lead_id = ? ORDER BY id DESC", (lead_id,))
    crows = "".join(f"<tr><td>C{c['id']}</td><td>{escape(c['due_at'][5:16])}</td><td>{escape(c['purpose'])}</td>"
                    f"<td>{c['status']} {escape(c['outcome'] or '')}</td><td><small>{escape(c['notes'] or '')}</small></td></tr>"
                    for c in calls)
    reports = "".join(f"<details><summary>Visit #{v['id']} report</summary><table>" + "".join(
        f"<tr><th>{escape(lbl)}</th><td>{escape(str(json.loads(v['form_data']).get(f, '')))}</td></tr>"
        for f, lbl, _, _ in visits.VISIT_FORM) + "</table></details>" for v in vis if v.get("form_data"))
    prof = "".join(f"<tr><th>{k}</th><td>{escape(str(lead[k]))}</td></tr>" for k in (
        "phone", "email", "city", "rm_name", "source", "campaign", "stage", "score", "temperature", "project_interest", "unit_type",
        "budget_min", "budget_max", "timeline", "purpose", "financing", "language", "next_followup_at",
        "followup_purpose", "opted_out", "needs_human") if lead[k] not in (None, ""))
    pause = (f'<form method="post" action="/leads/{lead_id}/resume"><input name="note" placeholder="note for AI"><button>Hand back to AI</button></form>'
             if lead["needs_human"] else
             f'<form method="post" action="/leads/{lead_id}/pause"><button class="grey">Take over (pause AI)</button></form>')
    body = f"""<h2>#{lead['id']} {escape(lead['name'] or '')} {_temp(lead['temperature'])}</h2>
<div class="grid2"><div>
<div class="card"><table>{prof}</table>{pause}</div>
<div class="card"><h4>Conversion strategy</h4><div style="font-size:14px">{strat_html}</div></div>
<div class="card"><h4>Calls</h4><table>{crows or '<tr><td>none</td></tr>'}</table></div>
{_lead_registrations(lead_id)}
<div class="card"><h4>AI's notes</h4><div style="white-space:pre-wrap;font-size:14px">{escape(lead['memory'] or '-')}</div></div>
<div class="card"><h4>Site / office visits</h4><table>{vrows or '<tr><td>none</td></tr>'}</table>{reports}</div>
<div class="card"><h4>Offers</h4><table>{orows or '<tr><td>none</td></tr>'}</table></div></div>
<div><div class="card"><h4>Conversation</h4><div class="row">{chat or 'No messages yet.'}{_drafts_inline(lead_id)}</div></div>
{_test_tools(lead_id) if test_mode() else ''}
<div class="card"><h4>Message the customer yourself</h4>
<form method="post" action="/leads/{lead_id}/send"><textarea name="text" rows="2" style="width:100%"
placeholder="Goes to the customer on WhatsApp in {escape(team.rm_for(lead)['name'])}'s name"></textarea><button>Send to customer</button></form></div>
<div class="card"><h4>Activity log</h4><table>{lrows}</table></div></div></div>{AUTO_REFRESH}"""
    return page(lead["name"] or "Lead", body)


AUTO_REFRESH = """<script>setInterval(function(){var a=document.activeElement;
if(a&&/INPUT|TEXTAREA|SELECT/.test(a.tagName))return;
var f=document.querySelectorAll('textarea,input[type=text],input:not([type])');
for(var i=0;i<f.length;i++){if(f[i].value)return;}location.reload();},12000);</script>"""


def _lead_registrations(lead_id: int) -> str:
    from .web_inventory import lead_section
    return lead_section(lead_id)


def _drafts_inline(lead_id: int) -> str:
    out = ""
    for d in db.q("SELECT * FROM drafts WHERE lead_id = ? AND status = 'pending' ORDER BY id", (lead_id,)):
        out += f"""<div class="msg out" style="border:2px dashed #7bbf94;background:#f3fbf6">
<small>DRAFT D{d['id']} · waiting for {escape(d['rm_name'] or 'salesperson')} to approve</small>
<form method="post" action="/drafts/{d['id']}"><input type="hidden" name="back" value="/leads/{lead_id}">
<textarea name="text" rows="3" style="width:100%">{escape(d['text'])}</textarea>
<button name="action" value="send">Send</button> <button name="action" value="drop" class="grey">Drop</button>
<small>Edit the text before sending if you like.</small></form></div>"""
    return out


def _test_tools(lead_id: int) -> str:
    return f"""<div class="card" style="border-color:#f1d38a"><h4>Test: you play the customer and the team</h4>
<form method="post" action="/test/{lead_id}/customer"><textarea name="text" rows="2" style="width:100%"
placeholder="Reply as the CUSTOMER, e.g. Looking for 2BHK under 75L, can I visit Saturday?"></textarea>
<button>Send as customer</button></form>
<form method="post" action="/test/{lead_id}/command" style="margin-top:10px">
<select name="role"><option value="rm">Salesperson</option><option value="site">Site person</option>
<option value="owner">Management</option></select>
<input type="text" name="text" placeholder="e.g. CALLED C1 spoke, wants east facing" style="width:100%">
<button class="grey">Run team command</button></form>
<small>The AI takes 10–40 seconds to respond; this page refreshes itself. Call briefs, approvals and drafts sent to
the team are in <a href="/test/outbox">Outbox</a>.</small></div>"""


@app.post("/leads/{lead_id}/pause")
def pause(lead_id: int, _: str = Depends(owner_auth)):
    db.update("leads", lead_id, {"needs_human": 1})
    db.audit(lead_id, "owner", "pause", "")
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.post("/leads/{lead_id}/resume")
def resume(lead_id: int, note: str = Form(""), _: str = Depends(owner_auth)):
    db.update("leads", lead_id, {"needs_human": 0})
    db.audit(lead_id, "owner", "resume", note)
    events.dispatch(events._run, lead_id, "human_resumed",
                    f"The owner handed this lead back to you. Owner note: {note or '-'}. Continue from here.")
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.post("/leads/{lead_id}/send")
def owner_send(lead_id: int, text: str = Form(...), _: str = Depends(owner_auth)):
    lead = db.get_lead(lead_id)
    if lead and not lead["opted_out"]:
        team.deliver(lead_id, text, "whatsapp", author="owner")
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.get("/visits", response_class=HTMLResponse)
def visit_list(_: str = Depends(owner_auth)):
    rows = db.q("SELECT v.*, l.name, l.phone FROM site_visits v JOIN leads l ON l.id = v.lead_id "
                "ORDER BY v.scheduled_at DESC LIMIT 200")
    trs = "".join(f"""<tr><td>#{v['id']}</td><td>{escape(v['scheduled_at'])}</td><td><a href="/leads/{v['lead_id']}">{escape(v['name'] or '')}</a> {escape(v['phone'] or '')}</td>
<td>{escape(v['project'])}</td><td>{escape(v['site_person'])}</td><td>{v['status']}</td><td>{
        f'<a href="/f/visit/{v["form_token"]}">Fill visit report</a>' if v['status'] == 'scheduled' and v['kind'] == 'site'
        else escape((v['interest_level'] or '') + ' ' + (v['feedback'] or ''))}</td></tr>"""
                  for v in rows)
    return page("Visits", f'<div class="card"><table><tr><th></th><th>When</th><th>Customer</th><th>Project</th>'
                          f'<th>Site person</th><th>Status</th><th>Outcome</th></tr>{trs}</table></div>')




@app.get("/campaigns", response_class=HTMLResponse)
def campaigns(_: str = Depends(owner_auth)):
    rows = db.q("SELECT * FROM campaigns ORDER BY id DESC")
    cards = ""
    for c in rows:
        d = json.loads(c["content"])
        ads = "".join(f"<li><span class='pill'>{escape(a.get('tracking_code', ''))}</span> <b>{escape(a['headline'])}</b> — {escape(a['primary_text'])} <i>[{escape(a['call_to_action'])}]</i>"
                      f"<br><small>Creative: {escape(a['creative_idea'])}</small></li>" for a in d.get("ad_variants", []))
        personas = "".join(f"<li><b>{escape(p['persona'])}</b>: {escape(p['why_they_buy'])}<br><small>{escape(p['targeting'])}</small></li>"
                           for p in d.get("target_personas", []))
        approve = (f'<form method="post" action="/campaigns/{c["id"]}/approve"><button>Approve for publishing</button></form>'
                   if c["status"] == "draft" else "")
        cards += f"""<div class="card"><h3>{escape(c['name'])} <span class="pill">{c['status']}</span> <span class="pill">{escape(c['channel'])}</span></h3>
<h4>Who to target</h4><ul>{personas}</ul><h4>Ads</h4><ul>{ads}</ul>
<h4>Lead form</h4><ul>{''.join(f'<li>{escape(q)}</li>' for q in d.get('lead_form_questions', []))}</ul>
<h4>WhatsApp template</h4><pre style="white-space:pre-wrap">{escape(d.get('whatsapp_template', ''))}</pre>
<h4>Social posts</h4><ul>{''.join(f'<li style="white-space:pre-wrap">{escape(p)}</li>' for p in d.get('social_posts', []))}</ul>
<h4>Big creative ideas</h4><ul>{''.join(f"<li><b>{escape(i['idea'])}</b> — {escape(i['how_to_execute'])}<br><small>{escape(i['why_it_fits_our_buyers'])}</small></li>" for i in d.get('big_creative_ideas', []))}</ul>
<h4>Referral offer</h4><p>{escape(d.get('referral_offer_idea', ''))}</p>
<h4>2-week content calendar</h4><ol>{''.join(f'<li>{escape(x)}</li>' for x in d.get('two_week_content_calendar', []))}</ol>
<h4>Budget</h4><p>{escape(d.get('budget_split_advice', ''))}</p><h4>Compliance</h4><p>{escape(d.get('compliance_notes', ''))}</p>{approve}</div>"""
    from . import inventory
    projects = "".join(f"<option>{escape(p['name'])}</option>" for p in inventory.list_projects())
    form = f"""<div class="card"><h3>Create a lead-generation campaign</h3><form method="post" action="/campaigns/new">
<select name="project">{projects}</select> <select name="channel"><option>Meta (Facebook/Instagram) lead ads</option>
<option>Google search ads</option><option>Property portals</option><option>WhatsApp broadcast (opted-in list)</option><option>Instagram organic</option></select>
<input name="budget" placeholder="Monthly budget e.g. 1.5L"> <input name="brief" placeholder="Anything specific? e.g. target NRIs, Diwali offer" style="width:320px">
<button>Generate</button></form><small>Takes ~1 minute. Saved as a draft for your approval.</small></div>"""
    return page("Campaigns", form + cards)


@app.post("/campaigns/new")
def new_campaign(project: str = Form(...), channel: str = Form(...), budget: str = Form(""), brief: str = Form(""),
                 _: str = Depends(owner_auth)):
    marketing.generate_campaign(project, channel, brief, budget)
    return RedirectResponse("/campaigns", status_code=303)


@app.post("/campaigns/{cid}/approve")
def approve_campaign(cid: int, _: str = Depends(owner_auth)):
    db.update("campaigns", cid, {"status": "approved"})
    return RedirectResponse("/campaigns", status_code=303)


@app.get("/reports", response_class=HTMLResponse)
def reports(_: str = Depends(owner_auth)):
    def money(v):
        return pricing.fmt_money(v) if v else "—"

    def econ(rows, label):
        trs = "".join(f"<tr><td>{escape(r['month'])}</td><td>{escape(r['key'])}</td><td>{money(r['spend'])}</td>"
                      f"<td>{r['leads']}</td><td>{r['qualified']}</td><td>{r['visited']}</td><td>{r['booked']}</td>"
                      f"<td>{money(r['cpl'])}</td><td>{money(r['cpq'])}</td><td>{money(r['cpv'])}</td><td>{money(r['cpb'])}</td>"
                      f"<td>{money(r['commission'])}</td></tr>" for r in rows)
        return (f'<table><tr><th>Month</th><th>{label}</th><th>Spend</th><th>Leads</th><th>Qualified</th><th>Visited</th>'
                f'<th>Booked</th><th>Per lead</th><th>Per qualified</th><th>Per visit</th><th>Per booking</th>'
                f'<th>Commission</th></tr>{trs or "<tr><td colspan=12>No data yet.</td></tr>"}</table>')

    spends = db.q("SELECT * FROM ad_spend ORDER BY month DESC, id DESC LIMIT 60")
    srows = "".join(f"<tr><td>{escape(x['month'])}</td><td>{escape(x['source'] or '')}</td><td>{escape(x['campaign'] or '')}</td>"
                    f"<td>{escape(x['city'] or '')}</td><td>{pricing.fmt_money(x['amount'])}</td>"
                    f"<td><form method='post' action='/reports/spend/{x['id']}/delete'><button class='small red'>Delete</button>"
                    f"</form></td></tr>" for x in spends)
    month = get_settings().now().strftime("%Y-%m")
    sources = "".join(f"<option>{x}</option>" for x in ("meta_ads", "google_ads", "portal", "referral", "website",
                                                        "walk_in", "other"))
    from . import models as _models
    urows, total_cost, total_runs = "", 0.0, 0
    for r in db.q("SELECT COALESCE(NULLIF(model, ''), 'claude-opus-5-5') m, COUNT(*) runs, SUM(input_tokens) i, "
                  "SUM(output_tokens) o, SUM(cache_read) cr, SUM(cache_write) cw FROM usage GROUP BY m"):
        c = _models.cost_usd(r["m"], r["i"] or 0, r["o"] or 0, r["cr"] or 0, r["cw"] or 0)
        total_cost += c
        total_runs += r["runs"]
        urows += (f"<tr><td>{escape(_models.MODELS.get(r['m'], {}).get('label', r['m']))}</td><td>{r['runs']}</td>"
                  f"<td>${c:.2f}</td></tr>")
    month_runs = db.q1("SELECT COUNT(DISTINCT lead_id) n FROM usage WHERE substr(created_at,1,7) = ?",
                       (get_settings().now().strftime("%Y-%m"),))["n"]
    u = {"runs": total_runs}
    cost = total_cost
    return page("Reports", f"""<div class="card"><h3>Marketing spend</h3>
<p><small>Enter what you spent per channel each month (and per campaign code if you track ads individually). The tables
below turn it into cost per lead, per qualified lead, per site visit and per booking — so you can increase spend only
where bookings justify it.</small></p>
<form method="post" action="/reports/spend" style="display:flex;flex-wrap:wrap;gap:8px;align-items:end">
<label>Month<br><input type="month" name="month" value="{month}"></label>
<label>Channel<br><select name="source">{sources}</select></label>
<label>Campaign code (optional)<br><input name="campaign" placeholder="C3-V2"></label>
<label>City (optional)<br><input name="city" placeholder="Chennai"></label>
<label>Amount<br><input name="amount" placeholder="1.5L" required></label><button>Add spend</button></form>
<table style="margin-top:10px"><tr><th>Month</th><th>Channel</th><th>Campaign</th><th>City</th><th>Amount</th><th></th></tr>
{srows or '<tr><td colspan=6>No spend entered yet.</td></tr>'}</table></div>
<div class="card"><h3>Unit economics by channel</h3>{econ(marketing.spend_report("source"), "Channel")}</div>
<div class="card"><h3>By campaign / ad variant</h3>{econ(marketing.spend_report("campaign"), "Campaign")}</div>
<div class="card"><h3>AI usage</h3>Model calls: {u.get('runs') or 0} · approx. cost ${cost:.2f} (estimate at list prices)
· buyers handled this month: {month_runs}
<table style="margin-top:8px"><tr><th>Model</th><th>Calls</th><th>Approx. cost</th></tr>{urows or '<tr><td colspan=3>No AI calls yet.</td></tr>'}</table>
<small>Change which model handles each stage in Settings → AI quality &amp; cost.</small></div>""")


@app.post("/reports/spend")
def add_spend(month: str = Form(...), source: str = Form(...), campaign: str = Form(""), city: str = Form(""),
              amount: str = Form(...), _: str = Depends(owner_auth)):
    amt = events.parse_amount(amount) if amount else None
    if not amt or len(month) != 7:
        raise HTTPException(400, "Enter a month and an amount like 150000 or 1.5L")
    db.insert("ad_spend", {"month": month, "source": source, "campaign": campaign.strip(), "city": city.strip().title(),
                           "amount": amt, "created_at": db.now_iso()})
    return RedirectResponse("/reports", status_code=303)


@app.post("/reports/spend/{sid}/delete")
def delete_spend(sid: int, _: str = Depends(owner_auth)):
    db.q("DELETE FROM ad_spend WHERE id = ?", (sid,))
    return RedirectResponse("/reports", status_code=303)


@app.post("/drafts/{draft_id}")
def draft_action(draft_id: int, action: str = Form(...), text: str = Form(""), back: str = Form("/"),
                 _: str = Depends(owner_auth)):
    if action == "drop":
        team.drop_draft(draft_id)
    else:
        d = db.q1("SELECT text FROM drafts WHERE id = ?", (draft_id,))
        same = d and " ".join(text.split()) == " ".join(d["text"].split())
        edited = text.replace("\r\n", "\n").strip() if d and text.strip() and not same else None
        team.approve_draft(draft_id, edited, actor="owner")
    return RedirectResponse(back if back.startswith("/") and not back.startswith("//") else "/", status_code=303)


@app.post("/bookings/{booking_id}/paid")
def mark_paid(booking_id: int, amount: str = Form(""), ref: str = Form(""), _: str = Depends(owner_auth)):
    events.payment_received(booking_id, events.parse_amount(amount) if amount else None, ref)
    return RedirectResponse("/", status_code=303)


@app.get("/calls", response_class=HTMLResponse)
def call_list(_: str = Depends(owner_auth)):
    rows = db.q("SELECT c.*, l.name, l.phone, l.stage FROM call_tasks c JOIN leads l ON l.id = c.lead_id "
                "WHERE c.status IN ('open','attempted') ORDER BY c.due_at")
    trs = "".join(f"""<tr><td>C{c['id']}<br>{escape(c['rm_name'] or '')}</td><td>{escape(c['due_at'][5:16])}</td>
<td><a href="/leads/{c['lead_id']}">{escape(c['name'] or '')}</a><br>{escape(c['phone'] or '')}<br>{c['stage']}</td>
<td><b>{escape(c['purpose'])}</b><div style="white-space:pre-wrap;font-size:13px">{escape(c['brief'] or '')}</div></td>
<td><a href="/f/call/{c['form_token']}">Log call</a></td></tr>""" for c in rows)
    return page("Calls", f'<div class="card"><h3>Calls to make ({len(rows)})</h3><table><tr><th></th><th>Due</th>'
                         f'<th>Customer</th><th>Brief</th><th></th></tr>{trs}</table></div>')


@app.get("/insights", response_class=HTMLResponse)
def insights_page(_: str = Depends(owner_auth)):
    row = db.q1("SELECT * FROM insights WHERE kind = 'playbook' ORDER BY id DESC LIMIT 1")
    btn = ('<form method="post" action="/insights/run"><button>Learn from recent leads now</button> '
           '<small>Runs automatically every week. Takes 1-2 minutes.</small></form>')
    if not row:
        return page("Learning", f'<div class="card"><h3>Learned playbook</h3><p>Nothing learned yet: needs a few '
                                f'won or lost leads.</p>{btn}</div>')
    d = json.loads(row["content"])

    def lst(items):
        return "<ul>" + "".join(f"<li>{escape(i if isinstance(i, str) else ' — '.join(map(str, i.values())))}</li>"
                                for i in items) + "</ul>"
    body = f"""<div class="card"><h3>Learned playbook <small>({escape(row['created_at'][:10])}, from {row['based_on']} closed leads)</small></h3>
<p>{escape(d['summary'])}</p>{btn}</div>
<div class="card"><h4>What works in messages</h4>{lst(d['what_works_in_messages'])}<h4>What works on calls</h4>{lst(d['what_works_on_calls'])}
<h4>Objections and best answers</h4>{lst(d['objection_playbook'])}<h4>Who converts</h4>{lst(d['best_converting_profiles'])}
<h4>Lead sources</h4>{lst(d['lead_source_verdicts'])}<h4>Follow-up</h4>{lst(d['follow_up_insights'])}
<h4>Tone (from salespeople's edits)</h4>{lst(d['rm_tone_preferences'])}<h4>Stop doing</h4>{lst(d['things_to_stop'])}</div>
<div class="card"><h4>New campaign ideas</h4>{lst(d['creative_campaign_ideas'])}<h4>Experiments to run</h4>{lst(d['experiments_to_run'])}</div>"""
    return page("Learning", body)


@app.post("/insights/run")
def insights_run(_: str = Depends(owner_auth)):
    events.dispatch(learning.learn, True)
    return page("Learning", '<div class="card">Learning started. Refresh the Learning page in a couple of minutes.'
                            '</div><a href="/insights">Back</a>')


# ============================ no-login forms for the team (links sent on WhatsApp) ============================

def _form_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}
label{{display:block;margin:12px 0 4px;font-weight:600}}input,textarea,select{{width:100%;box-sizing:border-box}}
button{{margin-top:16px;width:100%;padding:12px;font-size:16px}}</style></head><body><main style="max-width:560px">
<div class="card">{body}</div></main></body></html>""")


@app.get("/f/visit/{token}", response_class=HTMLResponse)
def visit_form(token: str):
    v = db.q1("SELECT * FROM site_visits WHERE form_token = ?", (token,))
    if not v:
        raise HTTPException(404)
    lead = db.get_lead(v["lead_id"])
    if v["form_data"]:
        return _form_page("Done", "<h3>Thanks — this report was already submitted.</h3>")
    fields = ""
    for f, label, typ, opts in visits.VISIT_FORM:
        if typ == "choice":
            ctrl = f'<select name="{f}"><option></option>' + "".join(f"<option>{o}</option>" for o in opts) + "</select>"
        elif typ == "textarea":
            ctrl = f'<textarea name="{f}" rows="3"></textarea>'
        else:
            ctrl = f'<input name="{f}">'
        fields += f"<label>{escape(label)}</label>{ctrl}"
    return _form_page("Visit report", f"""<h3>Site visit report #{v['id']}</h3>
<p>{escape(lead['name'] or '')} · {escape(v['scheduled_at'][:16].replace('T', ' '))} · {escape(v['project'])}</p>
<form method="post">{fields}<button>Submit report</button></form>""")


@app.post("/f/visit/{token}", response_class=HTMLResponse)
async def visit_form_submit(token: str, request: Request):
    v = db.q1("SELECT * FROM site_visits WHERE form_token = ?", (token,))
    if not v:
        raise HTTPException(404)
    if v["form_data"]:
        return _form_page("Done", "<h3>Already submitted.</h3>")
    form = await request.form()
    data = {f: str(form.get(f, "")).strip() for f, _, _, _ in visits.VISIT_FORM}
    events.dispatch(events.visit_outcome, v["id"], data)
    return _form_page("Thanks", "<h3>Thank you! Report saved.</h3><p>The sales team will follow up with the customer.</p>")


@app.get("/f/call/{token}", response_class=HTMLResponse)
def call_form(token: str):
    t = db.q1("SELECT * FROM call_tasks WHERE form_token = ?", (token,))
    if not t:
        raise HTTPException(404)
    lead = db.get_lead(t["lead_id"])
    outcomes = "".join(f"<option>{o}</option>" for o in team.CALL_OUTCOMES)
    return _form_page("Call log", f"""<h3>Call C{t['id']} — {escape(lead['name'] or '')}</h3>
<p><a href="tel:{escape(lead['phone'] or '')}">📞 {escape(lead['phone'] or '')}</a> · {escape(t['purpose'])}</p>
<details open><summary>Brief</summary><div style="white-space:pre-wrap;font-size:14px">{escape(t['brief'] or '')}</div></details>
<form method="post"><label>Outcome</label><select name="outcome">{outcomes}</select>
<label>What did you discuss?</label><textarea name="summary" rows="4"></textarea>
<label>Customer's mood / interest</label><select name="mood"><option></option><option>hot</option><option>warm</option><option>cold</option><option>annoyed</option></select>
<label>New information (budget, family, loan, requirements)</label><textarea name="new_info" rows="2"></textarea>
<label>Objections raised</label><textarea name="objections" rows="2"></textarea>
<label>Next step agreed</label><input name="next_step">
<label>Call back / meet when?</label><input name="callback_time" placeholder="e.g. Saturday 11am">
<button>Save call</button></form>""")


@app.post("/f/call/{token}", response_class=HTMLResponse)
async def call_form_submit(token: str, request: Request):
    t = db.q1("SELECT * FROM call_tasks WHERE form_token = ?", (token,))
    if not t:
        raise HTTPException(404)
    form = await request.form()
    outcome = str(form.get("outcome", "spoke"))
    if outcome not in team.CALL_OUTCOMES:
        outcome = "spoke"
    data = {k: str(form.get(k, "")).strip() for k in ("summary", "mood", "new_info", "objections", "next_step",
                                                       "callback_time")}
    events.dispatch(events.call_logged, t["id"], outcome, data)
    return _form_page("Thanks", "<h3>Saved.</h3><p>The follow-up WhatsApp will go out in your name.</p>")


# ============================ lead sources ============================

@app.get("/sources", response_class=HTMLResponse)
def sources_page(msg: str = "", _: str = Depends(owner_auth)):
    from . import lead_sources
    st = lead_sources.status()
    url = team.base_url()

    def badge(ok):
        return ('<span class="pill" style="background:#dcf3e4">connected</span>' if ok else
                '<span class="pill hot">not set up</span>')
    month = get_settings().now().strftime("%Y-%m")
    return page("Lead sources", f"""{f'<div class="notice">{escape(msg)}</div>' if msg else ''}
<div class="card"><h3>1. Meta lead ads (Facebook & Instagram forms) {badge(st['meta_leads']['configured'])}</h3>
<p>New leads this week: <b>{st['meta_leads']['week']}</b>. Leads arrive in seconds, with the ad and campaign name.</p>
<ol><li>In your Meta app (developers.facebook.com) → <b>Webhooks</b> → <b>Page</b> → subscribe to <b>leadgen</b>.<br>
Callback URL: <code>{escape(url)}/webhook/meta</code> · Verify token: the value of <code>META_VERIFY_TOKEN</code>.</li>
<li>In Railway → Variables add <code>META_VERIFY_TOKEN</code> (any text), <code>META_APP_SECRET</code> (App settings → Basic)
and <code>META_PAGE_TOKEN</code> (a long-lived Page token with <i>leads_retrieval</i> and <i>pages_manage_metadata</i>).</li>
<li>Put the campaign code (e.g. <code>C3-V2</code>) in each ad's name so bookings are traced to the ad.</li></ol>
<p><small>Signature check: {'on' if st['meta_leads']['signed'] else 'off (add META_APP_SECRET)'}.</small></p></div>

<div class="card"><h3>2. Click-to-WhatsApp ads {badge(st['ctwa']['configured'])}</h3>
<p>New leads this week: <b>{st['ctwa']['week']}</b>. In Ads Manager choose the <b>Messaging → WhatsApp</b> destination with your
WhatsApp Business number. When a buyer taps the ad and sends a message, the AI sees the ad they came from and replies at
once. Works automatically once WhatsApp is connected (<code>WHATSAPP_TOKEN</code>). Put the campaign code in the ad's
headline or text (e.g. "… C4-V1") to track it.</p></div>

<div class="card"><h3>3. Property portal emails (99acres, MagicBricks, Housing, NoBroker…) {badge(st['portal_email']['configured'])}</h3>
<p>New leads this week: <b>{st['portal_email']['week']}</b>. Last mailbox check: {escape(st['portal_email']['last_poll'][:16].replace('T', ' ') or 'never')}.</p>
<ol><li>Create a mailbox just for leads (e.g. a new Gmail), turn on 2-step verification and create an <b>App password</b>.</li>
<li>In each portal's settings, send lead/enquiry emails to that address (or forward them there).</li>
<li>In Railway → Variables add <code>LEADS_IMAP_USER</code> (the address) and <code>LEADS_IMAP_PASSWORD</code> (the app password).
Optional <code>LEADS_IMAP_HOST</code> (default imap.gmail.com).</li></ol>
<p>The system checks the mailbox every 2 minutes and creates a lead from each portal enquiry. Other emails are ignored.</p>
<form method="post" action="/sources/mail"><button class="grey">Check mailbox now</button></form>
{_recent_emails_html()}
<p><small>Using an email-forwarding service instead? POST <code>{{from, subject, text}}</code> to
<code>{escape(url)}/webhook/portal-email</code> with header <code>X-Webhook-Secret</code>.</small></p></div>

<div class="card"><h3>4. Ad spend {badge(st['meta_spend']['configured'])}</h3>
<p><b>Meta:</b> spend per campaign is pulled every morning into Reports. Last sync:
{escape(st['meta_spend']['last_sync'][:16].replace('T', ' ') or 'never')}. Needs <code>META_AD_ACCOUNT_ID</code> and
<code>META_ADS_TOKEN</code> (a system-user token with <i>ads_read</i>) in Railway. Once on, don't type Meta spend by hand.</p>
<form method="post" action="/sources/meta-spend"><button class="grey">Sync Meta spend now</button></form>
<p style="margin-top:14px"><b>Google Ads:</b> in Google Ads → Campaigns → Download → CSV (with the Campaign and Cost columns),
then upload it here. (Google's API needs a separate developer approval; this keeps it simple.)</p>
<form method="post" action="/sources/google-csv" enctype="multipart/form-data">
<input type="file" name="file" accept=".csv" required> <input type="month" name="month" value="{month}">
<button class="grey">Upload Google Ads CSV</button></form></div>""")


def _recent_emails_html() -> str:
    from . import lead_sources
    rows = ""
    for e in lead_sources.recent_emails():
        if e["action"] == "lead_source":
            res = f'<a href="/leads/{e["lead_id"]}">lead created ✓</a>'
        elif e["action"] == "email_ignored":
            res = "not a portal email — ignored"
        else:
            res = ("<b>portal email, couldn't find a phone/email — will retry</b><br><small>"
                   + escape(e.get("snippet", "")[:400]) + "</small>")
        rows += (f"<tr><td>{escape(e['at'][5:16].replace('T', ' '))}</td><td>{escape(e.get('subject', '') or '')}"
                 f"<br><small>{escape(e.get('from', '') or e.get('via', '') or '')}</small></td><td>{res}</td></tr>")
    return ('<h4 style="margin-top:14px">Recent emails</h4><table><tr><th>When</th><th>Email</th><th>Result</th></tr>'
            + (rows or '<tr><td colspan=3>None yet.</td></tr>') + "</table>")


@app.post("/sources/mail")
def sources_mail(_: str = Depends(owner_auth)):
    from . import lead_sources
    try:
        res = lead_sources.poll_mailbox(recheck_ignored=True)
        msg = ("Mailbox not set up yet." if not res.get("configured") else
               f"Mailbox checked: {res['leads']} new lead(s).")
    except Exception as e:  # noqa: BLE001 - show the reason to the owner
        msg = f"Could not read the mailbox: {e}"
    return RedirectResponse(f"/sources?msg={msg}", status_code=303)


@app.post("/sources/meta-spend")
def sources_meta_spend(_: str = Depends(owner_auth)):
    from . import lead_sources
    try:
        res = lead_sources.sync_meta_spend()
        msg = ("Meta spend not set up yet." if not res.get("configured") else
               f"Synced {res['rows']} campaign rows ({', '.join(res['months']) or 'no spend'}).")
    except Exception as e:  # noqa: BLE001
        msg = f"Could not sync Meta spend: {e}"
    return RedirectResponse(f"/sources?msg={msg}", status_code=303)


@app.post("/sources/google-csv")
async def sources_google_csv(file: UploadFile = File(...), month: str = Form(""), _: str = Depends(owner_auth)):
    from . import lead_sources
    with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as f:
        f.write(await file.read())
        path = f.name
    try:
        res = lead_sources.import_google_csv(path, month or get_settings().now().strftime("%Y-%m"))
        msg = f"Imported {res['rows']} Google Ads campaign rows for {', '.join(res['months']) or '-'}."
    except Exception as e:  # noqa: BLE001
        msg = f"Could not read that file: {e}"
    return RedirectResponse(f"/sources?msg={msg}", status_code=303)


# ============================ team portals (links for salespeople and site team) ============================

@app.get("/team", response_class=HTMLResponse)
def team_page(msg: str = "", _: str = Depends(owner_auth)):
    from . import team_access
    rows = ""
    for m in team_access.members():
        url = team_access.portal_url(m["role"], m["token"])
        acc = db.q1("SELECT last_seen FROM team_access WHERE id = ?", (m["access_id"],))
        rows += f"""<tr><td><b>{escape(m['name'])}</b><br><small>{escape(m['phone'])}</small></td>
<td>{'Salesperson portal' if m['role'] == 'sales' else 'Site visit app'}</td>
<td><a href="{escape(url)}" target="_blank">Open</a><br><small>last used {escape((acc['last_seen'] or 'never')[:16].replace('T', ' '))}</small></td>
<td><form method="post" action="/team/{m['access_id']}" style="display:flex;gap:6px;flex-wrap:wrap">
<button name="action" value="send">Send link on WhatsApp</button>
<button name="action" value="new" class="grey" onclick="return confirm('Replace the link? The old one stops working.')">New link</button></form></td></tr>"""
    return page("Team", f"""{f'<div class="notice">{escape(msg)}</div>' if msg else ''}
<div class="card"><h3>Team portals</h3><p><small>Each salesperson and site team member has a personal link — no password.
Send it to them on WhatsApp; they open it and tap "Add to Home screen" so it works like an app. If a phone is lost or
someone leaves, click "New link" and the old one stops working. People come from Settings (sales team, site team) and
from project site hosts on the Inventory page.</small></p>
<table><tr><th>Person</th><th>Portal</th><th>Link</th><th></th></tr>{rows or '<tr><td>No team members yet — add them in Settings.</td></tr>'}</table></div>""")


@app.post("/team/{access_id}")
def team_action(access_id: int, action: str = Form(...), _: str = Depends(owner_auth)):
    from . import team_access
    if action == "new":
        team_access.regenerate(access_id)
        return RedirectResponse("/team?msg=New link created. Send it to them; the old link no longer works.", status_code=303)
    ok = team_access.send_link(access_id)
    return RedirectResponse("/team?msg=" + ("Link sent on WhatsApp." if ok else "Could not send — check the number."),
                            status_code=303)


# ============================ settings (edit config from any device) ============================

def _current_raw() -> dict:
    import yaml
    return yaml.safe_load(config_path().read_text()) or {}


def _save_raw_text(text: str) -> None:
    path = writable_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    reload_settings()
    db.audit(None, "owner", "settings_saved", "")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(saved: int = 0, _: str = Depends(owner_auth)):
    return page("Settings", settings_form.render(_current_raw(), saved=bool(saved)))


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request, _: str = Depends(owner_auth)):
    import yaml
    form = await request.form()
    sent_version = str(form.get("_version") or "")
    if sent_version and sent_version != settings_form._version():
        return page("Settings", '<div class="notice" style="background:#ffe9e6"><b>Not saved:</b> settings were changed '
                                'somewhere else after you opened this page (another tab or person). '
                                '<a href="/settings">Reload Settings</a>, then make your change again.</div>')
    raw, errs = settings_form.build([(k, v) for k, v in form.multi_items() if k != "_version"], _current_raw())
    if not errs:
        errs = validate_config(raw)
    if errs:
        return page("Settings", settings_form.render(raw, errors=errs))
    _save_raw_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.get("/settings/advanced", response_class=HTMLResponse)
def settings_advanced(msg: str = "", _: str = Depends(owner_auth)):
    text = config_path().read_text()
    return page("Advanced settings", f"""{f'<div class="notice">{escape(msg)}</div>' if msg else ''}
<div class="card"><h3>Advanced settings</h3><p>Everything in one text file, including follow-up timing, lead scoring and
AI settings. Most things are easier on the <a href="/settings">Settings form</a>. Keep the spaces at the start of lines.</p>
<form method="post"><textarea name="config" rows="30" style="width:100%;font-family:ui-monospace,monospace;
font-size:13px" spellcheck="false">{escape(text)}</textarea><button>Save</button></form>
<small>Saved to {escape(str(writable_config_path()))}</small></div>""")


@app.post("/settings/advanced", response_class=HTMLResponse)
def settings_advanced_save(config: str = Form(...), _: str = Depends(owner_auth)):
    import yaml
    try:
        raw = yaml.safe_load(config)
    except yaml.YAMLError as e:
        return page("Settings", f'<div class="notice">Not saved — formatting error: {escape(str(e))}</div>'
                                f'<a href="/settings/advanced">Back</a>')
    errs = validate_config(raw)
    if errs:
        return page("Settings", '<div class="notice">Not saved:<ul>' + "".join(f"<li>{escape(x)}</li>" for x in errs)
                    + '</ul></div><a href="/settings/advanced">Back</a>')
    _save_raw_text(config)
    return RedirectResponse("/settings/advanced?msg=Saved.", status_code=303)


# ============================ test mode (try everything from a phone before WhatsApp is live) ============================

@app.get("/test", response_class=HTMLResponse)
def test_page(_: str = Depends(owner_auth)):
    rows = db.q("SELECT id, name, stage, phone FROM leads WHERE campaign = 'test' ORDER BY id DESC")
    trs = "".join(f'<tr><td><a href="/leads/{r["id"]}">#{r["id"]} {escape(r["name"] or "")}</a></td><td>{r["stage"]}</td></tr>'
                  for r in rows)
    sources = "".join(f"<option>{x}</option>" for x in ("meta_ads", "website", "portal", "google_ads", "walk_in", "referral"))
    return page("Test", f"""<div class="card"><h3>Try the whole journey</h3>
<p>Create a pretend lead, then reply as the customer and play the salesperson, site person and management from the
lead's page.{'' if env('ANTHROPIC_API_KEY') else ' <b>Set ANTHROPIC_API_KEY first — the AI cannot reply without it.</b>'}</p>
<form method="post" action="/test/new"><input name="name" placeholder="Customer name" value="" required>
<select name="source">{sources}</select> <input name="unit_type" placeholder="2BHK / 3BHK">
<input name="budget" placeholder="Budget e.g. 75L"> <input name="city" placeholder="City">
<button>Create test lead</button></form></div>
<div class="card"><h3>Test leads</h3><table>{trs or '<tr><td>None yet.</td></tr>'}</table></div>""")


@app.post("/test/new")
def test_new(name: str = Form(...), source: str = Form("meta_ads"), unit_type: str = Form(""), budget: str = Form(""),
             city: str = Form(""), _: str = Depends(owner_auth)):
    n = db.q1("SELECT COUNT(*) n FROM leads WHERE campaign = 'test'")["n"]
    lead, _created = leads.upsert_lead({"name": name, "phone": f"+9190000{n + 1:05d}", "source": source,
                                        "campaign": "test", "unit_type": unit_type, "city": city.title(),
                                        "budget_max": events.parse_amount(budget) if budget else None})
    events.dispatch(events.new_lead, lead["id"])
    return RedirectResponse(f"/leads/{lead['id']}", status_code=303)


@app.post("/test/{lead_id}/customer")
def test_customer(lead_id: int, text: str = Form(...), _: str = Depends(owner_auth)):
    if not test_mode():
        raise HTTPException(403, "Only in test mode")
    lead = db.get_lead(lead_id)
    events.dispatch(events.inbound_message, lead["phone"], None, text, "whatsapp")
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.post("/test/{lead_id}/command", response_class=HTMLResponse)
def test_command(lead_id: int, role: str = Form(...), text: str = Form(...), _: str = Depends(owner_auth)):
    if not test_mode():
        raise HTTPException(403, "Only in test mode")
    s = get_settings()
    phone = {"owner": s.owner["phone"],
             "rm": (team.rm_for(db.get_lead(lead_id)) or {}).get("phone", s.owner["phone"]),
             "site": s.site_persons[0]["phone"] if s.site_persons else s.owner["phone"]}[role]
    reply = events.staff_command(phone, text) or "Not recognised."
    return page("Command", f'<div class="card"><b>Reply to {escape(role)}:</b><pre style="white-space:pre-wrap">'
                           f'{escape(reply)}</pre><a href="/leads/{lead_id}">Back to lead</a></div>')


@app.get("/test/outbox", response_class=HTMLResponse)
def test_outbox(_: str = Depends(owner_auth)):
    path = channels.outbox_path()
    text = path.read_text()[-60000:] if path.exists() else "Nothing sent yet."
    blocks = text.split("-" * 60 + "\n")[::-1]
    return page("Outbox", '<div class="card"><h3>Everything sent (newest first)</h3>' + "".join(
        f'<pre style="white-space:pre-wrap;border-bottom:1px solid #eee;padding:8px 0">{escape(b.strip())}</pre>'
        for b in blocks if b.strip()) + "</div>")


@app.get("/manifest.json")
def manifest():
    from fastapi.responses import JSONResponse
    return JSONResponse({"name": f"{get_settings().business['name']} Sales", "short_name": "Sales",
                         "start_url": "/", "display": "standalone", "background_color": "#f6f7f9",
                         "theme_color": "#1d2330",
                         "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]})


@app.get("/icon.svg")
def icon():
    from fastapi.responses import Response
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" '
           'fill="#1d2330"/><path d="M22 58 50 34l28 24v22H58V64H42v16H22z" fill="#fff"/></svg>')
    return Response(svg, media_type="image/svg+xml")


@app.get("/health")
def health():
    from .config import storage_status
    return {"ok": True, "storage": storage_status()}


_include_routers()
