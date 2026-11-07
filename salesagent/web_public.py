"""Public landing pages and enquiry forms (no login). Each project gets /p/<slug>; /enquire lists all projects.

Ads point here with ?src=<source>&c=<campaign code>. Consent is captured with its exact wording, time and page
(DPDP), spam is filtered (hidden honeypot field + per-IP rate limit), and the lead goes straight to the AI.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import db, events, inventory, leads, sales_kit
from .config import get_settings
from .pricing import fmt_money

router = APIRouter()
_hits: dict[str, deque] = defaultdict(deque)
RATE_LIMIT = 5          # submissions per IP per hour

SOURCE_MAP = {"facebook": "meta_ads", "fb": "meta_ads", "instagram": "meta_ads", "ig": "meta_ads", "meta": "meta_ads",
              "google": "google_ads", "adwords": "google_ads", "gads": "google_ads", "portal": "portal",
              "whatsapp": "whatsapp", "referral": "referral", "website": "website"}

CSS = """
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#1d2330;background:#f6f7f9}
.hero{background:#1d2330;color:#fff;padding:28px 18px}.hero h1{margin:0 0 6px;font-size:26px}.hero p{margin:0;color:#cfd6e4}
.wrap{max-width:760px;margin:auto;padding:16px}.card{background:#fff;border:1px solid #e3e6ec;border-radius:12px;padding:18px;margin:14px 0}
.photo{width:100%;border-radius:12px;display:block}.types{display:flex;flex-wrap:wrap;gap:10px}
.type{border:1px solid #e3e6ec;border-radius:10px;padding:10px 14px;flex:1;min-width:140px}.type b{display:block;font-size:18px}
ul{padding-left:20px}label{display:block;font-weight:600;margin:12px 0 4px;font-size:15px}
input,select{width:100%;padding:12px;border:1px solid #cfd4dd;border-radius:8px;font:inherit;font-size:16px}
.consent{display:flex;gap:10px;align-items:flex-start;font-weight:400;font-size:14px;color:#3b4252}
.consent input{width:auto;margin-top:3px}button{width:100%;margin-top:16px;padding:14px;border:0;border-radius:10px;
background:#2b62e3;color:#fff;font-size:17px;font-weight:600;cursor:pointer}.small{font-size:13px;color:#6b7385}
.hp{position:absolute;left:-5000px}.proj{display:block;color:inherit;text-decoration:none}.err{background:#ffe9e6;
border-radius:8px;padding:10px;margin-bottom:10px}
"""


def consent_text() -> str:
    name = get_settings().business.get("name", "us")
    return (f"I agree that {name} and its partner builders may contact me by phone, WhatsApp, SMS or email about "
            f"properties, including through an AI assistant. I can opt out anytime by replying STOP.")


def _shell(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="index,follow">
<style>{CSS}</style></head><body>{body}
<div class="wrap small" style="text-align:center">© {escape(get_settings().business.get('name', ''))} ·
Prices and availability subject to change · <a href="/privacy">Privacy</a></div></body></html>""")


def _types_html(p: dict) -> str:
    out = ""
    for t in inventory.type_summary(p["id"]):
        if not t["available"]:
            continue
        size = f"{t['size_min']}" + (f"–{t['size_max']}" if t["size_max"] != t["size_min"] else "") + " sq ft" \
            if t["size_min"] else ""
        out += f'<div class="type">{escape(t["type"])}<b>from {fmt_money(t["price_min"])}</b><span class="small">{size}</span></div>'
    return f'<div class="types">{out}</div>' if out else '<p class="small">Contact us for current availability.</p>'


def _form(action: str, params: dict, project: dict | None, error: str = "", values: dict | None = None) -> str:
    v = values or {}
    types = sorted({t["type"] for p in ([project] if project else inventory.list_projects())
                    for t in inventory.type_summary(p["id"]) if t["available"]})
    cities = inventory.cities()
    city_field = "" if project else (
        '<label>City</label><select name="city">' + "".join(
            f'<option{" selected" if c == v.get("city") else ""}>{escape(c)}</option>' for c in cities) + "</select>")
    hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(str(val))}">' for k, val in params.items() if val)
    opts = "".join(f'<option{" selected" if t == v.get("unit_type") else ""}>{escape(t)}</option>' for t in types)
    return f"""<div class="card" id="enquire"><h2 style="margin-top:0">Get prices, floor plans & a site visit</h2>
{f'<div class="err">{escape(error)}</div>' if error else ''}
<form method="post" action="{action}">{hidden}
<div class="hp"><label>Website</label><input name="website" tabindex="-1" autocomplete="off"></div>
<label>Your name</label><input name="name" required value="{escape(v.get('name', ''))}" autocomplete="name">
<label>Mobile number (WhatsApp)</label><input name="phone" type="tel" required inputmode="tel" placeholder="98765 43210"
value="{escape(v.get('phone', ''))}" autocomplete="tel">
{city_field}
<label>Looking for</label><select name="unit_type"><option value="">Any</option>{opts}</select>
<label>Budget</label><select name="budget">{''.join(f'<option value="{b}"{" selected" if b == v.get("budget") else ""}>{lbl}</option>' for b, lbl in (("", "Select"), ("50L", "Up to ₹50 L"), ("75L", "₹50–75 L"), ("1cr", "₹75 L–1 Cr"), ("1.5cr", "₹1–1.5 Cr"), ("2cr", "₹1.5–2 Cr"), ("3cr", "Above ₹2 Cr")))}</select>
<label>When are you planning to buy?</label><select name="timeline">{''.join(f'<option{" selected" if t == v.get("timeline") else ""}>{t}</option>' for t in ("Within 3 months", "3–6 months", "6–12 months", "Just exploring"))}</select>
<label class="consent"><input type="checkbox" name="consent" value="1" required> <span>{escape(consent_text())}</span></label>
<button>Send enquiry</button>
<p class="small">We reply on WhatsApp within minutes, and a member of our team will call you.</p></form></div>"""


def _params(request: Request) -> dict:
    q = request.query_params
    src = (q.get("src") or q.get("utm_source") or "").lower()
    return {"src": SOURCE_MAP.get(src, src), "c": q.get("c") or q.get("utm_campaign") or ""}


@router.get("/p/{slug}", response_class=HTMLResponse)
def project_landing(slug: str, request: Request):
    p = inventory.by_slug(slug)
    if not p:
        raise HTTPException(404)
    return _render_project(p, _params(request))


def _render_project(p: dict, params: dict, error: str = "", values: dict | None = None) -> HTMLResponse:
    photos = sales_kit.find_media(p["id"], "photo")
    photo = (f'<img class="photo" src="{escape(sales_kit.media_url(photos[0]))}" alt="{escape(p["name"])}">'
             if photos else "")
    hl = "".join(f"<li>{escape(h)}</li>" for h in p["highlights"])
    plans = "".join(f"<li>{escape(x)}</li>" for x in p["payment_plans"])
    body = f"""<div class="hero"><div class="wrap"><h1>{escape(p['name'].replace(' (sample)', ''))}</h1>
<p>{escape(p['locality'] or '')}{', ' if p['locality'] else ''}{escape(p['city'] or '')} · {escape(p['possession'] or p['status'] or '')}</p></div></div>
<div class="wrap">{photo}
<div class="card"><h2 style="margin-top:0">Homes available</h2>{_types_html(p)}
{f'<h3>Why buyers choose it</h3><ul>{hl}</ul>' if hl else ''}{f'<h3>Payment</h3><ul>{plans}</ul>' if plans else ''}
<p class="small">{('RERA: ' + escape(p['rera'])) if p['rera'] else ''}{' · Builder: ' + escape(p['builder']) if not p['is_own'] else ''}</p></div>
{_form(f"/p/{p['slug']}", params, p, error, values)}</div>"""
    return _shell(p["name"], body)


@router.get("/enquire", response_class=HTMLResponse)
def all_projects(request: Request):
    return _render_all(_params(request), request.query_params.get("city", ""))


def _render_all(params: dict, city: str = "", error: str = "", values: dict | None = None) -> HTMLResponse:
    cards = ""
    for p in inventory.list_projects(city=city or None):
        if not any(t["available"] for t in inventory.type_summary(p["id"])):
            continue
        slug = inventory.ensure_slug(p["id"])
        q = "&".join(f"{k}={v}" for k, v in params.items() if v)
        cards += (f'<a class="proj card" href="/p/{slug}{"?" + q if q else ""}"><b>{escape(p["name"].replace(" (sample)", ""))}</b>'
                  f'<div class="small">{escape(p["locality"] or "")}, {escape(p["city"])} · {escape(p["possession"] or "")}</div>'
                  f'{_types_html(p)}</a>')
    name = get_settings().business.get("name", "")
    body = f"""<div class="hero"><div class="wrap"><h1>{escape(name)}</h1><p>New homes in {escape(city or ', '.join(inventory.cities()))}</p></div></div>
<div class="wrap">{cards or '<div class="card">New projects coming soon.</div>'}
{_form("/enquire", params, None, error, values or {"city": city})}</div>"""
    return _shell(f"{name} — homes", body)


async def _submit(request: Request, project: dict | None) -> HTMLResponse:
    f = await request.form()
    v = {k: str(f.get(k, "") or "").strip() for k in ("name", "phone", "city", "unit_type", "budget", "timeline",
                                                         "src", "c", "website", "consent")}
    params = {"src": v["src"], "c": v["c"]}

    def again(msg):
        return _render_project(project, params, msg, v) if project else _render_all(params, v["city"], msg, v)

    if v["website"]:                       # honeypot filled in: a bot
        return _thanks()
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return again("Too many enquiries from this connection. Please try again later or call us.")
    phone = db.normalize_phone(v["phone"])
    if len("".join(ch for ch in phone if ch.isdigit())) < 11:
        return again("Please enter a valid 10-digit mobile number.")
    if not v["consent"]:
        return again("Please tick the consent box so we can contact you.")
    if not v["name"]:
        return again("Please enter your name.")
    q.append(now)
    budget = events.parse_amount(v["budget"]) if v["budget"] else None
    page_url = str(request.url.path) + (f"?src={v['src']}&c={v['c']}" if v["src"] or v["c"] else "")
    lead, created = leads.upsert_lead({
        "name": v["name"], "phone": phone, "source": v["src"] or "website", "campaign": v["c"],
        "city": (project["city"] if project else v["city"]).title(),
        "project_interest": project["name"] if project else "", "unit_type": v["unit_type"],
        "budget_max": budget, "timeline": v["timeline"]}, consent=True)
    db.update("leads", lead["id"], {"consent_at": db.now_iso(), "consent_text": consent_text(),
                                    "consent_source": page_url})
    db.audit(lead["id"], "customer", "consent", {"text": consent_text(), "page": page_url})
    if created:
        events.dispatch(events.new_lead, lead["id"])
    else:
        events.dispatch(events.inbound_message, phone, None,
                        f"[Filled the enquiry form again: {project['name'] if project else 'all projects'}, "
                        f"{v['unit_type'] or 'any size'}, budget {v['budget'] or '-'}, {v['timeline']}]", "web")
    return _thanks()


def _thanks() -> HTMLResponse:
    return _shell("Thank you", """<div class="hero"><div class="wrap"><h1>Thank you!</h1>
<p>We've received your enquiry.</p></div></div><div class="wrap"><div class="card">
<p>You'll get a WhatsApp message from us in a few minutes, and a member of our team will call you shortly.</p>
<p class="small">Didn't expect this? Reply STOP to our message and we won't contact you again.</p></div></div>""")


@router.post("/p/{slug}", response_class=HTMLResponse)
async def project_submit(slug: str, request: Request):
    p = inventory.by_slug(slug)
    if not p:
        raise HTTPException(404)
    return await _submit(request, p)


@router.post("/enquire", response_class=HTMLResponse)
async def all_submit(request: Request):
    return await _submit(request, None)


@router.get("/privacy", response_class=HTMLResponse)
def privacy():
    s = get_settings()
    return _shell("Privacy", f"""<div class="wrap"><div class="card"><h2>How we use your details</h2>
<p>When you send an enquiry, {escape(s.business.get('name', ''))} uses your name, mobile number and requirements only to help
you find a home: to reply on WhatsApp (partly through an AI assistant), to call you, to arrange site visits, and — if
you visit a partner builder's project — to share your name and number with that builder so they can host you.</p>
<p>We record when and where you gave consent. You can stop all contact at any time by replying STOP, and ask us to
delete your details by writing to {escape(s.owner.get('email', ''))}.</p></div></div>""")
