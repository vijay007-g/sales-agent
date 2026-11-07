"""A friendly, form-based Settings page (no YAML editing). Renders the config as labelled fields with
add/remove buttons for repeatable items, and turns the submitted form back into the config."""
from __future__ import annotations

import copy
import re
from html import escape

from . import db
from .pricing import fmt_money

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TIMEZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "UTC"]

CSS = """
.fields{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px 14px}
.f{display:flex;flex-direction:column;gap:4px;font-size:14px}.f>span{font-weight:600}
.f small{color:#6b7385;font-weight:400}.f input,.f textarea,.f select{width:100%;box-sizing:border-box}
.wide{grid-column:1/-1}.item{border:1px solid #e3e6ec;border-radius:10px;padding:14px;margin:10px 0;background:#fbfcfd}
.item .item{background:#fff}.itemhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.days{display:flex;flex-wrap:wrap;gap:6px}.days label{border:1px solid #cfd4dd;border-radius:6px;padding:4px 8px;
font-weight:400}.addbtn{background:#eef1f6;color:#1d2330;border:1px dashed #9aa3b5}.small{padding:4px 10px;
font-size:13px}.savebar{position:sticky;bottom:0;background:#fff;border-top:1px solid #e3e6ec;padding:12px;
margin:0 -12px;display:flex;gap:12px;align-items:center;z-index:4}.errs{background:#ffe9e6;border:1px solid
#f3b2a9;border-radius:8px;padding:10px 14px;margin-bottom:16px}h3 small{font-weight:400;color:#6b7385}
"""

JS = """<script>
var _n=0;function uid(){_n++;return 'n'+Date.now()+_n;}
function addItem(btn,ph){var t=btn.parentElement.querySelector(':scope > template');
var d=document.createElement('div');d.innerHTML=t.innerHTML.split(ph).join(uid());
var el=d.firstElementChild;btn.parentElement.querySelector(':scope > .items').appendChild(el);
var f=el.querySelector('input');if(f)f.focus();}
function rm(btn,what){if(confirm('Remove this '+what+'?'))btn.closest('.item').remove();}
</script>"""


# ------------------------------------------------------------------ small field builders

def _v(x) -> str:
    return "" if x is None else escape(str(x))


def inp(name, label, value, kind="text", hint="", wide=False, placeholder="", required=False):
    return (f'<label class="f{" wide" if wide else ""}"><span>{escape(label)}</span>'
            f'<input type="{kind}" name="{name}" value="{_v(value)}" placeholder="{escape(placeholder)}"'
            f'{" required" if required else ""}>{f"<small>{escape(hint)}</small>" if hint else ""}</label>')


def money(name, label, value, hint=""):
    shown = fmt_money(value) if isinstance(value, (int, float)) else ""
    extra = (f"Now: {shown}. " if shown else "") + (hint or "Type 7500000, 75L or 1.02cr")
    return inp(name, label, value, hint=extra, placeholder="e.g. 75L")


def area(name, label, lines, hint="One per line"):
    text = "\n".join(lines or []) if isinstance(lines, list) else (lines or "")
    return (f'<label class="f wide"><span>{escape(label)}</span><textarea name="{name}" rows="3">{escape(text)}'
            f'</textarea><small>{escape(hint)}</small></label>')


def sel(name, label, value, options, hint=""):
    opts = "".join(f'<option value="{escape(v)}"{" selected" if str(v) == str(value) else ""}>{escape(t)}</option>'
                   for v, t in options)
    return (f'<label class="f"><span>{escape(label)}</span><select name="{name}">{opts}</select>'
            f'{f"<small>{escape(hint)}</small>" if hint else ""}</label>')


def days(name, label, selected):
    sel_set = {int(x) for x in (selected if selected is not None else range(7))}
    boxes = "".join(f'<label><input type="checkbox" name="{name}[]" value="{i}"{" checked" if i in sel_set else ""}> '
                    f'{d}</label>' for i, d in enumerate(DAYS))
    return f'<div class="f wide"><span>{escape(label)}</span><div class="days">{boxes}</div></div>'


def hours(name, label, pair, default=("10:00", "18:00")):
    a, b = (pair or default)[:2] if pair and len(pair) >= 2 else default
    return (f'<div class="f"><span>{escape(label)}</span><div style="display:flex;gap:6px;align-items:center">'
            f'<input type="time" name="{name}[from]" value="{_v(a)}"> to '
            f'<input type="time" name="{name}[to]" value="{_v(b)}"></div></div>')


def item(title, body, what):
    return (f'<div class="item"><div class="itemhead"><b>{title}</b><button type="button" class="red small" '
            f'onclick="rm(this,\'{what}\')">Remove</button></div><div class="fields">{body}</div></div>')


def repeat(items_html, template_html, add_label, placeholder):
    return (f'<div><div class="items">{"".join(items_html)}</div><template>{template_html}</template>'
            f'<button type="button" class="addbtn" onclick="addItem(this,\'{placeholder}\')">+ {escape(add_label)}'
            f'</button></div>')


# ------------------------------------------------------------------ sections

def _rm(i, r):
    p = f"sales_team[{i}]"
    body = (inp(f"{p}[name]", "Name", r.get("name"), required=True)
            + inp(f"{p}[phone]", "Personal WhatsApp number", r.get("phone"), "tel",
                  "Gets call tasks and message drafts", placeholder="+91…")
            + sel(f"{p}[message_mode]", "AI messages", r.get("message_mode", "review"),
                  [("review", "Salesperson approves each one"), ("auto", "Send automatically")])
            + inp(f"{p}[languages]", "Languages", ", ".join(r.get("languages") or []), placeholder="English, Tamil")
            + inp(f"{p}[cities]", "Cities they handle", ", ".join(r.get("cities") or []), placeholder="Chennai",
                  hint="Leads from these cities go to them. Empty = any city")
            + inp(f"{p}[max_active_leads]", "Max active leads", r.get("max_active_leads", 80), "number")
            + inp(f"{p}[whatsapp_phone_number_id]", "WhatsApp Business number ID", r.get("whatsapp_phone_number_id"),
                  hint="From Meta, later. Leave empty for now.")
            + area(f"{p}[style]", "How they talk to customers", r.get("style", ""),
                   "e.g. Warm, polite, says 'sir/madam', short sentences, some Tamil words"))
    return item(escape(r.get("name") or "New salesperson"), body, "salesperson")


def _site(i, sp):
    p = f"site_persons[{i}]"
    body = (inp(f"{p}[name]", "Name", sp.get("name"), required=True)
            + inp(f"{p}[phone]", "WhatsApp number", sp.get("phone"), "tel", "Gets visit details and the report form",
                  placeholder="+91…")
            + inp(f"{p}[projects]", "Projects they handle", ", ".join(sp.get("projects") or []),
                  hint="Project names, comma separated. Empty = all projects", wide=True)
            + hours(f"{p}[visit_hours]", "Visit hours", sp.get("visit_hours"))
            + inp(f"{p}[max_visits_per_day]", "Max visits per day", sp.get("max_visits_per_day", 6), "number")
            + days(f"{p}[working_days]", "Working days", sp.get("working_days")))
    return item(escape(sp.get("name") or "New site person"), body, "site person")


def _unit(pi, j, u):
    p = f"projects[{pi}][units][{j}]"
    body = (inp(f"{p}[type]", "Unit type", u.get("type"), placeholder="2BHK", required=True)
            + inp(f"{p}[size_sqft]", "Size (sq ft)", u.get("size_sqft"), "number", "Fixed, never negotiable")
            + inp(f"{p}[carpet_sqft]", "Carpet area (sq ft)", u.get("carpet_sqft"), "number")
            + money(f"{p}[list_price]", "List price", u.get("list_price"))
            + money(f"{p}[floor_price]", "Floor price (your lowest)", u.get("floor_price"),
                    "Never shown to the AI or customers")
            + inp(f"{p}[available]", "Units available", u.get("available"), "number",
                  "Reduce after each booking")
            + inp(f"{p}[auto_approve_discount_pct]", "Discount AI may give without asking (%)",
                  u.get("auto_approve_discount_pct", 0), "number", "Keep 0 so every discount needs your approval"))
    return item(escape(u.get("type") or "New unit type"), body, "unit type")


def _project(i, pr):
    p = f"projects[{i}]"
    units = [_unit(i, j, u) for j, u in enumerate(pr.get("units") or [])]
    body = (inp(f"{p}[name]", "Project name", pr.get("name"), required=True)
            + inp(f"{p}[location]", "Location", pr.get("location"), placeholder="OMR, Chennai")
            + inp(f"{p}[type]", "Type", pr.get("type"), placeholder="Gated community apartments")
            + inp(f"{p}[status]", "Status / possession", pr.get("status"), placeholder="Possession Dec 2027")
            + inp(f"{p}[rera]", "RERA number", pr.get("rera"))
            + area(f"{p}[highlights]", "Highlights", pr.get("highlights"), "One per line — the AI only uses these facts")
            + area(f"{p}[payment_plans]", "Payment plans & loans", pr.get("payment_plans"))
            + area(f"{p}[approval_concessions]", "Extras you might give (always need your approval)",
                   pr.get("approval_concessions"), "One per line, e.g. Free car parking")
            + area(f"{p}[free_concessions]", "Extras the AI may offer without asking", pr.get("free_concessions"),
                   "Usually leave empty")
            + f'<div class="wide"><b>Unit types</b>'
            + repeat(units, _unit(i, "__J__", {}), "Add unit type", "__J__") + "</div>")
    return item(escape(pr.get("name") or "New project"), body, "project")


def render(raw: dict, errors: list[str] | None = None, saved: bool = False) -> str:
    b = raw.get("business", {})
    o = raw.get("owner", {})
    bk = raw.get("booking", {})
    msg = raw.get("messaging", {})
    fin = raw.get("finance", {})
    tz = b.get("timezone", "Asia/Kolkata")
    tzs = TIMEZONES if tz in TIMEZONES else [tz] + TIMEZONES
    top = ""
    if errors:
        top = '<div class="errs"><b>Not saved — please fix:</b><ul>' + "".join(
            f"<li>{escape(e)}</li>" for e in errors) + "</ul></div>"
    elif saved:
        top = '<div class="notice">✅ Saved. The AI uses the new settings from now on.</div>'
    return f"""<style>{CSS}</style>{JS}{top}
<form method="post" action="/settings">
<div class="card"><h3>Company</h3><div class="fields">
{inp("business[name]", "Company name", b.get("name"), required=True)}
{inp("business[website]", "Website", b.get("website"), "url", placeholder="https://")}
{inp("business[languages]", "Languages customers use", ", ".join(b.get("languages") or []), placeholder="English, Tamil, Hindi")}
{sel("business[timezone]", "Time zone", tz, [(t, t) for t in tzs])}
{inp("business[currency]", "Currency", b.get("currency", "INR"))}
{inp("business[assistant_intro]", "How the AI introduces itself",
     b.get("assistant_intro") or f"{(b.get('name') or 'Our').split()[0]}'s assistant",
     hint="Used in the first message, e.g. \"Hi Ravi, I'm Saikrupa's assistant, working with Anitha\"")}
</div></div>

<div class="card"><h3>You (management) <small>approvals, booking confirmations, daily summary</small></h3><div class="fields">
{inp("owner[name]", "Name", o.get("name"))}
{inp("owner[phone]", "WhatsApp number", o.get("phone"), "tel", placeholder="+91…", required=True)}
{inp("owner[email]", "Email", o.get("email"), "email")}
</div></div>

<div class="card"><h3>Sales team <small>they call customers; messages go out in their name</small></h3>
{repeat([_rm(i, r) for i, r in enumerate(raw.get("sales_team") or [])], _rm("__I__", {}), "Add salesperson", "__I__")}
</div>

<div class="card"><h3>Site team <small>they show the site and fill the visit report</small></h3>
{repeat([_site(i, sp) for i, sp in enumerate(raw.get("site_persons") or [])], _site("__I__", {}), "Add site person", "__I__")}
</div>

<div class="card"><h3>Projects, units & partner builders</h3><p>Managed on the
<a href="/inventory">Inventory page</a>: your own and partner projects in every city, unit-by-unit availability,
spreadsheet upload, builders' commission and contacts.</p></div>

<div class="card"><h3>Booking advance & payment <small>for your own projects (partner builders' accounts are on the Inventory page)</small></h3><div class="fields">
{money("booking[advance_amount]", "Standard booking advance", bk.get("advance_amount"))}
{inp("booking[payee_name]", "Account name", bk.get("payee_name"))}
{inp("booking[bank_name]", "Bank", bk.get("bank_name"))}
{inp("booking[account_number]", "Account number", bk.get("account_number"))}
{inp("booking[ifsc]", "IFSC", bk.get("ifsc"))}
{inp("booking[upi_id]", "UPI ID (optional)", bk.get("upi_id"))}
{inp("booking[verify_phone]", "Office phone (customers call to verify the account)", bk.get("verify_phone"), "tel")}
{inp("booking[office_address]", "Office address", bk.get("office_address"), wide=True)}
{hours("booking[office_hours]", "Office hours", bk.get("office_hours"))}
{inp("booking[office_visit_slots_per_hour]", "Office visits per hour", bk.get("office_visit_slots_per_hour", 2), "number")}
{days("booking[office_days]", "Office open days", bk.get("office_days", [0, 1, 2, 3, 4, 5]))}
</div></div>

<div class="card"><h3>Messaging & loan illustrations</h3><div class="fields">
{hours("messaging[quiet_hours]", "No messages to customers between", msg.get("quiet_hours"), ("20:30", "09:00"))}
{inp("finance[default_rate_pct]", "Home-loan rate for EMI illustrations (%)", fin.get("default_rate_pct", 8.5), hint="Illustrative; banks decide")}
{inp("finance[default_tenure_years]", "Default loan tenure (years)", fin.get("default_tenure_years", 20), "number")}
{inp("finance[default_down_payment_pct]", "Default down payment (%)", fin.get("default_down_payment_pct", 20), "number")}
</div><p><small>Follow-up timing, lead scoring and AI settings: <a href="/settings/advanced">Advanced settings</a>.</small></p></div>

<div class="savebar"><button>Save settings</button><a href="/settings">Discard changes</a></div>
</form>"""


# ------------------------------------------------------------------ parsing the submitted form

def _tree(items) -> dict:
    root: dict = {}
    for key, val in items:
        m = re.match(r"^([^\[]+)((?:\[[^\]]*\])*)$", key)
        if not m:
            continue
        parts = [m.group(1)] + re.findall(r"\[([^\]]*)\]", m.group(2))
        node = root
        if parts[-1] == "":
            for p in parts[:-2]:
                node = node.setdefault(p, {})
            node.setdefault(parts[-2], []).append(val)
        else:
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = val
    return root


def _s(d, k):
    return str(d.get(k, "") or "").strip()


def _lines(d, k):
    return [x.strip() for x in str(d.get(k, "") or "").splitlines() if x.strip()]


def _csv(d, k):
    return [x.strip() for x in str(d.get(k, "") or "").split(",") if x.strip()]


def _hours(d, k, default):
    h = d.get(k) or {}
    return [h.get("from") or default[0], h.get("to") or default[1]]


def build(items, old: dict) -> tuple[dict, list[str]]:
    """Turn submitted form fields into a config dict. Sections the form doesn't show are kept from `old`."""
    from .events import parse_amount
    t = _tree(items)
    raw = copy.deepcopy(old)
    errs: list[str] = []

    def num(val, what, required=False):
        s = str(val or "").strip()
        if not s:
            if required:
                errs.append(f"{what} is required.")
            return None
        try:
            return int(float(s))
        except ValueError:
            errs.append(f"{what}: '{s}' is not a number.")
            return s

    def amt(val, what, required=False):
        s = str(val or "").strip()
        if not s:
            if required:
                errs.append(f"{what} is required.")
            return None
        a = parse_amount(s)
        if a is None:
            errs.append(f"{what}: couldn't read '{s}'. Use 7500000, 75L or 1.02cr.")
            return s
        return a

    def phone(val, what, required=True):
        s = str(val or "").strip()
        if not s:
            if required:
                errs.append(f"{what}: phone number is required.")
            return ""
        p = db.normalize_phone(s)
        if len(p) < 11:
            errs.append(f"{what}: '{s}' doesn't look like a full phone number (include the country code).")
            return s
        return p

    b = t.get("business", {})
    raw["business"] = {**old.get("business", {}), "name": _s(b, "name"), "website": _s(b, "website"),
                       "languages": _csv(b, "languages") or ["English"], "timezone": _s(b, "timezone") or "Asia/Kolkata",
                       "currency": _s(b, "currency") or "INR",
                       "assistant_intro": _s(b, "assistant_intro") or f"{(_s(b, 'name') or 'Our').split()[0]}'s assistant"}
    if not raw["business"]["name"]:
        errs.append("Company name is required.")
    o = t.get("owner", {})
    raw["owner"] = {"name": _s(o, "name"), "phone": phone(o.get("phone"), "Your WhatsApp number"),
                    "email": _s(o, "email")}

    team = []
    for r in (t.get("sales_team") or {}).values():
        if not _s(r, "name"):
            continue
        team.append({"name": _s(r, "name"), "phone": phone(r.get("phone"), f"Salesperson {_s(r, 'name')}"),
                     "whatsapp_phone_number_id": _s(r, "whatsapp_phone_number_id"),
                     "message_mode": "auto" if _s(r, "message_mode") == "auto" else "review",
                     "languages": _csv(r, "languages"), "cities": _csv(r, "cities"), "style": _s(r, "style"),
                     "max_active_leads": num(r.get("max_active_leads"), f"{_s(r, 'name')} max leads") or 80})
    raw["sales_team"] = team

    if "projects" in t:   # older form posts (kept for compatibility)
        pass
    from . import inventory
    names = set(inventory.project_names())

    sites = []
    for sp in (t.get("site_persons") or {}).values():
        if not _s(sp, "name"):
            continue
        n = _s(sp, "name")
        wd = sorted({int(x) for x in sp.get("working_days", [])})
        if not wd:
            errs.append(f"Site person {n}: tick at least one working day.")
        projs = _csv(sp, "projects")
        for x in projs:
            if x not in names:
                errs.append(f"Site person {n}: project '{x}' doesn't exist (check the spelling).")
        sites.append({"name": n, "phone": phone(sp.get("phone"), f"Site person {n}"), "projects": projs,
                      "working_days": wd, "visit_hours": _hours(sp, "visit_hours", ("10:00", "18:00")),
                      "max_visits_per_day": num(sp.get("max_visits_per_day"), f"{n} visits per day") or 6})
    raw["site_persons"] = sites

    bk = t.get("booking", {})
    raw["booking"] = {**old.get("booking", {}),
                      "advance_amount": amt(bk.get("advance_amount"), "Booking advance", True),
                      "payee_name": _s(bk, "payee_name"), "bank_name": _s(bk, "bank_name"),
                      "account_number": _s(bk, "account_number"), "ifsc": _s(bk, "ifsc").upper(),
                      "upi_id": _s(bk, "upi_id"),
                      "verify_phone": phone(bk.get("verify_phone"), "Office phone", required=False),
                      "office_address": _s(bk, "office_address"),
                      "office_hours": _hours(bk, "office_hours", ("10:00", "18:00")),
                      "office_days": sorted({int(x) for x in bk.get("office_days", [])}),
                      "office_visit_slots_per_hour": num(bk.get("office_visit_slots_per_hour"), "Office visits per hour") or 2}
    if not raw["booking"]["office_days"]:
        errs.append("Booking: tick at least one office open day.")
    for k, label in (("payee_name", "Account name"), ("account_number", "Account number"), ("ifsc", "IFSC")):
        if not raw["booking"][k]:
            errs.append(f"Booking: {label} is required (customers pay the advance into this account).")

    msg = t.get("messaging", {})
    raw["messaging"] = {**old.get("messaging", {}), "quiet_hours": _hours(msg, "quiet_hours", ("20:30", "09:00"))}
    fn = t.get("finance", {})
    try:
        raw["finance"] = {"default_rate_pct": float(_s(fn, "default_rate_pct") or 8.5),
                          "default_tenure_years": float(_s(fn, "default_tenure_years") or 20),
                          "default_down_payment_pct": float(_s(fn, "default_down_payment_pct") or 20)}
    except ValueError:
        errs.append("Loan illustration defaults must be numbers.")
    return raw, errs
