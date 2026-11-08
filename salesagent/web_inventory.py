"""Dashboard pages: Inventory (builders, projects, units, CSV upload), Commissions, Client registrations."""
from __future__ import annotations

import tempfile
from html import escape

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from . import db, inventory, partners, sales_kit
from .pricing import fmt_money
from .settings_form import CSS as FORM_CSS
from .settings_form import JS as FORM_JS
from .settings_form import area, days, inp, money, sel

router = APIRouter()
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def auth(request: Request) -> str:
    from .server import check_auth_header, client_ip
    return check_auth_header(request.headers.get("authorization"), client_ip(request))


UNITS_CSS = """@media (max-width:800px){table.units tr:first-child{display:none}
table.units tr{display:block;border:1px solid #e3e6ec;border-radius:8px;margin:8px 0;padding:8px}
table.units td{display:inline-block;border:0;padding:2px 6px}table.units td:last-child{display:block;margin-top:6px}
table.units input,table.units select{width:auto}}"""


def page(title: str, body: str) -> HTMLResponse:
    from .server import page as base_page
    return base_page(title, f"<style>{FORM_CSS}{UNITS_CSS}</style>{FORM_JS}" + body)


def _amt(v: str):
    from .events import parse_amount
    v = (v or "").strip()
    return parse_amount(v) if v else None


def _num(v: str):
    try:
        return float(v) if str(v).strip() != "" else None
    except ValueError:
        return None


def _phone(v: str) -> str:
    return db.normalize_phone(v) if (v or "").strip() else ""


# ============================================================ overview

@router.get("/inventory", response_class=HTMLResponse)
def inventory_home(_: str = Depends(auth)):
    builders = db.q("SELECT * FROM builders ORDER BY is_own DESC, name")
    brows = "".join(
        f"""<tr><td><a href="/inventory/builder/{b['id']}">{escape(b['name'] or '')}</a></td>
<td>{'Own projects' if b['is_own'] else 'Partner'}</td>
<td>{'' if b['is_own'] else (f"{b['commission_value'] or 0:g}%" if b['commission_type'] == 'pct' else fmt_money(b['commission_value']))}</td>
<td>{escape(b['contact_name'] or '')} {escape(b['contact_phone'] or '')}</td>
<td>{'' if b['is_own'] or (b['bank_account'] and b['bank_ifsc']) else '<span class="pill hot">bank details missing</span>'}
{'' if b['is_own'] or b['contact_phone'] or b['contact_email'] else '<span class="pill hot">no contact for registrations</span>'}</td></tr>"""
        for b in builders)
    cards = ""
    for city in sorted({p["city"] or "(no city)" for p in inventory.list_projects(active_only=False)}):
        rows = ""
        for p in inventory.list_projects(active_only=False):
            if (p["city"] or "(no city)") != city:
                continue
            types = inventory.type_summary(p["id"])
            avail = sum(t["available"] for t in types)
            rng = ", ".join(f"{t['type']} {fmt_money(t['price_min'])}" + (f"–{fmt_money(t['price_max'])}"
                            if t['price_max'] != t['price_min'] else "") for t in types if t["available"])
            rows += (f"<tr><td><a href=\"/inventory/project/{p['id']}\">{escape(p['name'])}</a>"
                     f"{'' if p['active'] else ' <span class=\"pill\">paused</span>'}</td>"
                     f"<td>{escape(p['locality'] or '')}</td><td>{escape(p['builder'])}</td>"
                     f"<td><b>{avail}</b> available</td><td>{escape(rng)}</td>"
                     f"<td>{'' if p['site_host_phone'] or inventory.hosts_for(p['name']) else '<span class=\"pill hot\">no site host</span>'}</td></tr>")
        cards += f'<div class="card"><h3>{escape(city)}</h3><table>{rows}</table></div>'
    return page("Inventory", f"""<div class="card"><h3>Builders</h3>
<p><small>Your own company and every partner builder whose projects you sell. Commission, contacts for client
registration, and their bank account for customers' booking advance.</small></p>
<table><tr><th>Builder</th><th></th><th>Commission</th><th>Contact</th><th></th></tr>{brows}</table>
<a href="/inventory/builder/new"><button>+ Add partner builder</button></a></div>
{cards or '<div class="card">No projects yet.</div>'}
<div class="card"><a href="/inventory/project/new"><button>+ Add project</button></a></div>
<div class="card"><h3>Trial inventory</h3><p><small>Four sample projects in Chennai and Bangalore (one own, three from two
fictional partner builders) with units, prices and charges, so you can test matching, cost sheets, client
registration and commissions. Sample registrations and site visits go to your own WhatsApp number. Remove them
before going live.</small></p>
<form method="post" action="/inventory/sample" style="display:flex;gap:8px">
<button name="action" value="load" class="grey">Load sample inventory</button>
<button name="action" value="remove" class="red" onclick="return confirm('Remove all sample projects and builders?')">Remove sample inventory</button>
</form></div>""")


@router.post("/inventory/sample")
async def sample_inventory(request: Request, _: str = Depends(auth)):
    f = await request.form()
    if f.get("action") == "remove":
        inventory.remove_sample()
    else:
        inventory.load_sample()
    return RedirectResponse("/inventory", status_code=303)


# ============================================================ builders

@router.get("/inventory/builder/{bid}", response_class=HTMLResponse)
def builder_form(bid: str, _: str = Depends(auth)):
    b = db.q1("SELECT * FROM builders WHERE id = ?", (int(bid),)) if bid.isdigit() else {}
    if bid.isdigit() and not b:
        raise HTTPException(404)
    b = b or {"is_own": 0, "commission_type": "pct", "payment_terms_days": 45, "registration_validity_days": 90}
    own = bool(b.get("is_own"))
    partner_fields = "" if own else f"""
<div class="card"><h3>Commission & payment terms</h3><div class="fields">
{sel("commission_type", "Commission type", b.get("commission_type"), [("pct", "% of deal value"), ("fixed", "Fixed amount per booking")])}
{inp("commission_value", "Commission (% or ₹)", b.get("commission_value"), hint="e.g. 2 for 2%, or 150000 for fixed")}
{inp("payment_terms_days", "Builder pays commission within (days)", b.get("payment_terms_days"), "number")}
{inp("registration_validity_days", "Client registration valid for (days)", b.get("registration_validity_days"), "number")}
</div></div>
<div class="card"><h3>Who receives client registrations</h3><div class="fields">
{inp("contact_name", "Contact name", b.get("contact_name"))}
{inp("contact_phone", "WhatsApp number", b.get("contact_phone"), "tel", "They reply ACK R<no> to confirm")}
{inp("contact_email", "Email", b.get("contact_email"), "email", "Registrations are also emailed here")}
</div></div>
<div class="card"><h3>Builder's bank account <small>customers pay the booking advance here for this builder's projects</small></h3><div class="fields">
{inp("bank_payee", "Account name", b.get("bank_payee"))}{inp("bank_name", "Bank", b.get("bank_name"))}
{inp("bank_account", "Account number", b.get("bank_account"))}{inp("bank_ifsc", "IFSC", b.get("bank_ifsc"))}
{inp("upi_id", "UPI (optional)", b.get("upi_id"))}
{inp("verify_phone", "Phone customers can call to verify the account", b.get("verify_phone"), "tel")}
{inp("office_address", "Builder's office address (to pay in person)", b.get("office_address"), wide=True)}
</div></div>"""
    note = ("<p><small>Your own company. Bank details for your own projects are under Settings → Booking advance."
            "</small></p>" if own else "")
    return page("Builder", f"""<form method="post"><div class="card"><h3>{'Your company' if own else 'Partner builder'}</h3>{note}
<div class="fields">{inp("name", "Builder name", b.get("name"), required=True)}
{area("notes", "Notes", b.get("notes") or "", "Agreement date, special terms…")}</div></div>
{partner_fields}
<div class="savebar"><button>Save</button><a href="/inventory">Back</a></div></form>""")


@router.post("/inventory/builder/{bid}")
async def builder_save(bid: str, request: Request, _: str = Depends(auth)):
    f = await request.form()
    g = lambda k: str(f.get(k, "") or "").strip()  # noqa: E731
    data = {"name": g("name"), "notes": g("notes")}
    existing = db.q1("SELECT * FROM builders WHERE id = ?", (int(bid),)) if bid.isdigit() else None
    if not (existing and existing["is_own"]):
        data.update({"commission_type": g("commission_type") or "pct",
                     "commission_value": _num(g("commission_value")) if g("commission_type") == "pct"
                     else (_amt(g("commission_value")) or _num(g("commission_value"))),
                     "payment_terms_days": int(_num(g("payment_terms_days")) or 45),
                     "registration_validity_days": int(_num(g("registration_validity_days")) or 90),
                     "contact_name": g("contact_name"), "contact_phone": _phone(g("contact_phone")),
                     "contact_email": g("contact_email"), "bank_payee": g("bank_payee"), "bank_name": g("bank_name"),
                     "bank_account": g("bank_account"), "bank_ifsc": g("bank_ifsc").upper(), "upi_id": g("upi_id"),
                     "verify_phone": _phone(g("verify_phone")), "office_address": g("office_address")})
    if not data["name"]:
        raise HTTPException(400, "Builder name is required")
    if existing:
        db.update("builders", existing["id"], data)
    else:
        db.insert("builders", {**data, "is_own": 0, "created_at": db.now_iso()})
    db.audit(None, "owner", "builder_saved", data["name"])
    return RedirectResponse("/inventory", status_code=303)


# ============================================================ projects

def _project_form(p: dict) -> str:
    builders = [(str(b["id"]), b["name"] + (" (own)" if b["is_own"] else "")) for b in
                db.q("SELECT id, name, is_own FROM builders ORDER BY is_own DESC, name")]
    vf, vt = (p.get("visit_hours") or "10:00-18:00").split("-")[:2]
    vd = [int(x) for x in (p.get("visit_days") or "0,1,2,3,4,5,6").split(",") if x.strip()]
    lines = lambda k: "\n".join(p.get(k) or []) if isinstance(p.get(k), list) else (p.get(k) or "")  # noqa: E731
    return f"""<div class="card"><h3>Project</h3><div class="fields">
{inp("name", "Project name", p.get("name"), required=True)}
<label class="f"><span>Builder</span><select name="builder_id" onchange="document.getElementById('newb').style.display=this.value==='new'?'grid':'none'">
{"".join(f'<option value="{escape(v)}"{" selected" if str(v) == str(p.get("builder_id") or inventory.own_builder_id()) else ""}>{escape(t)}</option>' for v, t in builders)}
<option value="new">+ New partner builder…</option></select><small>Partner project? Pick the builder, or add a new one here.</small></label>
<div id="newb" class="fields wide" style="display:none;border:1px dashed #9aa3b5;border-radius:8px;padding:10px">
{inp("new_builder_name", "New builder's name", "", placeholder="e.g. Greenfield Homes")}
{inp("new_builder_commission", "Commission %", "", placeholder="2")}
{inp("new_builder_phone", "Builder contact WhatsApp (for client registration)", "", "tel")}
{inp("new_builder_email", "Builder contact email", "", "email")}
<small class="wide">Add the builder's bank account later on their page (Inventory → builder name).</small></div>
{inp("city", "City", p.get("city"), placeholder="Chennai / Bangalore", required=True)}
{inp("locality", "Locality", p.get("locality"), placeholder="Vadapalani")}
{inp("type", "Type", p.get("type"), placeholder="Apartments / Villas / Plots")}
{inp("status", "Construction status", p.get("status"), placeholder="Under construction / Ready to move")}
{inp("possession", "Possession", p.get("possession"), placeholder="Dec 2027 / Ready")}
{inp("rera", "RERA number", p.get("rera"))}
{sel("active", "Selling now?", p.get("active", 1), [("1", "Yes — the AI recommends it"), ("0", "Paused — hidden from the AI")])}
{area("highlights", "Highlights (the AI only uses these facts)", lines("highlights"))}
{area("payment_plans", "Payment plans & loans", lines("payment_plans"))}
{area("approval_concessions", "Extras you might give (always need your approval)", lines("approval_concessions"))}
{area("free_concessions", "Extras the AI may offer without asking", lines("free_concessions"), "Usually leave empty")}
</div></div>
<div class="card"><h3>Site host <small>who receives buyers at this site (e.g. the partner builder's site staff)</small></h3><div class="fields">
{inp("site_host_name", "Name", p.get("site_host_name"))}
{inp("site_host_phone", "WhatsApp number", p.get("site_host_phone"), "tel", "Gets visit details and the visit report form")}
<div class="f"><span>Visit hours</span><div style="display:flex;gap:6px;align-items:center">
<input type="time" name="visit_from" value="{escape(vf.strip())}"> to <input type="time" name="visit_to" value="{escape(vt.strip())}"></div></div>
{inp("max_visits_per_day", "Max visits per day", p.get("max_visits_per_day") or 6, "number")}
{days("visit_days", "Visit days", vd)}
</div><p><small>Leave empty if your own site team from Settings covers this project.</small></p></div>
<div class="card"><h3>Charges for cost sheets <small>the AI sends exact cost sheets calculated from these</small></h3><div class="fields">
{inp("gst_pct", "GST %", p.get("gst_pct"), hint="e.g. 5 for under-construction, 0 for ready-to-move")}
{inp("stamp_duty_pct", "Stamp duty %", p.get("stamp_duty_pct"), hint="As applicable in the state")}
{inp("registration_pct", "Registration %", p.get("registration_pct"))}
{area("other_charges", "Other charges", p.get("other_charges") or "", "One per line as  Label: amount  e.g.  Car parking: 3L")}
</div><p><small>Leave a box empty if unknown — the cost sheet will say it will be confirmed.</small></p></div>
<div class="card"><h3>Commission override <small>only if this project differs from the builder's usual terms</small></h3><div class="fields">
{sel("commission_type", "Type", p.get("commission_type") or "", [("", "Use builder's terms"), ("pct", "% of deal value"), ("fixed", "Fixed amount")])}
{inp("commission_value", "Commission (% or ₹)", p.get("commission_value"))}
</div></div>"""


@router.get("/inventory/project/{pid}", response_class=HTMLResponse)
def project_page(pid: str, msg: str = "", _: str = Depends(auth)):
    if pid == "new":
        return page("New project", f"""<form method="post" action="/inventory/project/new">{_project_form({})}
<div class="savebar"><button>Create project</button><a href="/inventory">Back</a></div></form>""")
    p = inventory.get_project(int(pid)) if pid.isdigit() else None
    if not p:
        raise HTTPException(404)
    urows = ""
    for u in inventory.units_for(p["id"]):
        urows += f"""<tr><td>{escape(u['unit_no'] or '—')}</td><td>{escape(u['unit_type'])}</td><td>{('Fl ' + escape(u['floor'])) if u['floor'] else ''}</td>
<td>{escape(u['facing'] or '')}</td><td>{(str(u['size_sqft']) + ' sqft') if u['size_sqft'] else ''}</td><td>{fmt_money(u['list_price'])}</td>
<td>min {fmt_money(u['floor_price'])}</td>
<td><form method="post" action="/inventory/unit/{u['id']}" style="display:flex;gap:4px;flex-wrap:wrap">
<input name="quantity" type="number" min="0" value="{u['quantity'] or 0}" style="width:64px" title="How many like this">
<select name="status">{''.join(f'<option{" selected" if u["status"] == st else ""}>{st}</option>' for st in ("available", "held", "booked", "sold", "blocked"))}</select>
<input name="list_price" value="{u['list_price'] or ''}" style="width:110px" title="List price">
<input name="floor_price" value="{u['floor_price'] or ''}" style="width:110px" title="Floor price">
<button class="small">Save</button><button class="small red" name="delete" value="1" onclick="return confirm('Delete this unit?')">Delete</button></form></td></tr>"""
    body = f"""{f'<div class="notice">{escape(msg)}</div>' if msg else ''}
<h2>{escape(p['name'])} <small>{escape(p['city'] or '')} · {escape(p['builder'])}</small></h2>
{_landing_box(p)}
<div class="card"><h3>Units</h3><p><small>One row per flat (with unit number), or one row per type with a count
("2BHK × 12") if the builder only shares numbers. Booked units come off automatically when the advance is paid.</small></p>
<table class="units"><tr><th>Unit</th><th>Type</th><th>Floor</th><th>Facing</th><th>Sq ft</th><th>List</th><th>Floor price</th><th>Count · status · prices</th></tr>
{urows or '<tr><td colspan=8>No units yet.</td></tr>'}</table>
<h4>Add a unit (or a group of identical units)</h4>
<form method="post" action="/inventory/project/{p['id']}/units"><div class="fields">
{inp("unit_no", "Unit no (optional)", "", placeholder="A-504")}{inp("unit_type", "Type", "", placeholder="2BHK", required=True)}
{inp("floor", "Floor", "")}{inp("facing", "Facing", "", placeholder="East")}
{inp("size_sqft", "Size (sq ft)", "", "number")}{inp("carpet_sqft", "Carpet (sq ft)", "", "number")}
{money("list_price", "List price", None)}{money("floor_price", "Floor price (your lowest)", None, "Never shown to the AI")}
{inp("quantity", "How many like this", 1, "number")}</div><button>Add</button></form>
<h4>Upload a spreadsheet</h4>
<form method="post" action="/inventory/project/{p['id']}/import" enctype="multipart/form-data">
<input type="file" name="file" accept=".csv" required> <label><input type="checkbox" name="replace" value="1">
Replace all currently available units</label> <button class="grey">Upload CSV</button></form>
<small>Save your Excel sheet as CSV. Columns: unit_no, unit_type, floor, facing, size_sqft, carpet_sqft, list_price,
floor_price, quantity, status. Prices like 7500000, 75L or 1.02cr. <a href="/inventory/units-template.csv">Download template</a></small></div>
{_media_card(p)}
<form method="post" action="/inventory/project/{p['id']}">{_project_form(p)}
<div class="savebar"><button>Save project</button><a href="/inventory">Back</a></div></form>
<div class="card"><details><summary>Delete this project</summary><p><small>Removes the project, its units and
files. Projects with bookings or commissions can only be paused (set "Selling now?" to Paused).</small></p>
<form method="post" action="/inventory/project/{p['id']}/delete" onsubmit="return confirm('Delete this project permanently?')">
<button class="red">Delete project</button></form></details></div>"""
    return page(p["name"], body)


def _landing_box(p: dict) -> str:
    from .team import base_url
    url = f"{base_url()}/p/{inventory.ensure_slug(p['id'])}"
    return (f'<div class="notice">Landing page: <a href="{escape(url)}" target="_blank">{escape(url)}</a><br><small>'
            f'Use it as the ad destination. Add <code>?src=meta_ads&amp;c=C3-V2</code> (source and campaign code) so '
            f'every lead is traced to the ad that produced it.</small></div>')


def _media_card(p: dict) -> str:
    files = db.q("SELECT * FROM media WHERE project_id = ? ORDER BY kind, id", (p["id"],))
    rows = "".join(f"""<tr><td>{escape(m['kind'])}</td><td><a href="{escape(sales_kit.media_url(m))}" target="_blank">{escape(m['title'])}</a></td>
<td>{escape(m['unit_type'] or 'all')}</td><td>{(m['size'] or 0) // 1024} KB</td>
<td><form method="post" action="/inventory/media/{m['id']}/delete" onsubmit="return confirm('Delete this file?')">
<button class="small red">Delete</button></form></td></tr>""" for m in files)
    kinds = "".join(f'<option value="{k}">{k.replace("_", " ")}</option>' for k in sales_kit.KINDS)
    return f"""<div class="card"><h3>Brochures, floor plans & photos <small>the AI sends these on WhatsApp</small></h3>
<table>{rows or '<tr><td>Nothing uploaded yet.</td></tr>'}</table>
<form method="post" action="/inventory/project/{p['id']}/media" enctype="multipart/form-data" style="margin-top:10px">
<div class="fields"><label class="f"><span>File (PDF, JPG, PNG)</span><input type="file" name="file" accept=".pdf,.jpg,.jpeg,.png,.webp" required></label>
<label class="f"><span>Kind</span><select name="kind">{kinds}</select></label>
{inp("title", "Title", "", placeholder="Brochure / 2BHK floor plan")}
{inp("unit_type", "For unit type (optional)", "", placeholder="2BHK")}</div><button>Upload</button></form>
<small>PDFs up to 16 MB, images up to 5 MB (WhatsApp limits).</small></div>"""


@router.post("/inventory/project/{pid}/media")
async def media_upload(pid: int, file: UploadFile = File(...), kind: str = Form("other"), title: str = Form(""),
                       unit_type: str = Form(""), _: str = Depends(auth)):
    res = sales_kit.save_media(pid, kind, title.strip(), file.filename or "", await file.read(), unit_type.strip())
    msg = "Uploaded." if res.get("ok") else f"Not uploaded: {res['error']}"
    return RedirectResponse(f"/inventory/project/{pid}?msg={msg}", status_code=303)


@router.post("/inventory/media/{mid}/delete")
def media_delete(mid: int, _: str = Depends(auth)):
    m = db.q1("SELECT project_id FROM media WHERE id = ?", (mid,))
    sales_kit.delete_media(mid)
    return RedirectResponse(f"/inventory/project/{m['project_id'] if m else ''}?msg=Deleted.", status_code=303)


@router.get("/m/{token}/{filename}")
def public_media(token: str, filename: str):
    """Public (unguessable) link so WhatsApp can fetch the file."""
    from fastapi.responses import FileResponse
    m = db.q1("SELECT * FROM media WHERE token = ? AND filename = ?", (token, filename))
    if not m:
        raise HTTPException(404)
    return FileResponse(m["path"], media_type=m["mime"], filename=m["filename"])


@router.post("/inventory/project/{pid}")
async def project_save(pid: str, request: Request, _: str = Depends(auth)):
    f = await request.form()
    g = lambda k: str(f.get(k, "") or "").strip()  # noqa: E731
    if not g("name") or not g("city"):
        raise HTTPException(400, "Project name and city are required")
    builder_id = g("builder_id")
    if builder_id == "new":
        if not g("new_builder_name"):
            raise HTTPException(400, "Enter the new builder's name")
        existing_b = db.q1("SELECT id FROM builders WHERE lower(name) = lower(?)", (g("new_builder_name"),))
        builder_id = existing_b["id"] if existing_b else db.insert("builders", {
            "name": g("new_builder_name"), "is_own": 0, "commission_type": "pct",
            "commission_value": _num(g("new_builder_commission")) or 0, "contact_phone": _phone(g("new_builder_phone")),
            "contact_email": g("new_builder_email"), "payment_terms_days": 45, "registration_validity_days": 90,
            "created_at": db.now_iso()})
        db.audit(None, "owner", "builder_saved", g("new_builder_name"))
    vdays = sorted({int(x) for x in f.getlist("visit_days[]")})
    data = {"name": g("name"), "builder_id": int(builder_id or inventory.own_builder_id()), "city": g("city").title(),
            "locality": g("locality"), "type": g("type"), "status": g("status"), "possession": g("possession"),
            "rera": g("rera"), "active": 1 if g("active") != "0" else 0, "highlights": g("highlights"),
            "payment_plans": g("payment_plans"), "approval_concessions": g("approval_concessions"),
            "free_concessions": g("free_concessions"), "site_host_name": g("site_host_name"),
            "site_host_phone": _phone(g("site_host_phone")),
            "visit_hours": f"{g('visit_from') or '10:00'}-{g('visit_to') or '18:00'}",
            "visit_days": ",".join(map(str, vdays or range(7))), "max_visits_per_day": int(_num(g("max_visits_per_day")) or 6),
            "gst_pct": _num(g("gst_pct")), "stamp_duty_pct": _num(g("stamp_duty_pct")),
            "registration_pct": _num(g("registration_pct")), "other_charges": g("other_charges"),
            "commission_type": g("commission_type") or None,
            "commission_value": (_num(g("commission_value")) if g("commission_type") == "pct"
                                 else (_amt(g("commission_value")) if g("commission_value") else None)),
            "updated_at": db.now_iso()}
    clash = db.q1("SELECT id FROM inv_projects WHERE lower(name) = lower(?) AND id != ?",
                  (data["name"], int(pid) if pid.isdigit() else -1))
    if clash:
        raise HTTPException(400, "Another project already has this name")
    if pid.isdigit():
        db.update("inv_projects", int(pid), data)
        new_id = int(pid)
    else:
        new_id = db.insert("inv_projects", {**data, "created_at": db.now_iso()})
    inventory.ensure_slug(new_id)
    db.audit(None, "owner", "project_saved", data["name"])
    return RedirectResponse(f"/inventory/project/{new_id}?msg=Saved.", status_code=303)


@router.post("/inventory/project/{pid}/delete")
def project_delete(pid: int, _: str = Depends(auth)):
    used = db.q1("SELECT 1 x FROM commissions WHERE project_id = ? UNION SELECT 1 FROM bookings b JOIN units u "
                 "ON u.id = b.unit_id WHERE u.project_id = ?", (pid, pid))
    if used:
        db.update("inv_projects", pid, {"active": 0})
        return RedirectResponse(f"/inventory/project/{pid}?msg=This project has bookings, so it was paused instead.",
                                status_code=303)
    p = db.q1("SELECT name FROM inv_projects WHERE id = ?", (pid,))
    for m in db.q("SELECT id FROM media WHERE project_id = ?", (pid,)):
        sales_kit.delete_media(m["id"])
    db.q("DELETE FROM units WHERE project_id = ?", (pid,))
    db.q("DELETE FROM inv_projects WHERE id = ?", (pid,))
    db.audit(None, "owner", "project_deleted", (p or {}).get("name", str(pid)))
    return RedirectResponse("/inventory", status_code=303)


@router.post("/inventory/project/{pid}/units")
async def unit_add(pid: int, request: Request, _: str = Depends(auth)):
    f = await request.form()
    g = lambda k: str(f.get(k, "") or "").strip()  # noqa: E731
    lp, fp = _amt(g("list_price")), _amt(g("floor_price"))
    if not g("unit_type") or not lp or not fp:
        return RedirectResponse(f"/inventory/project/{pid}?msg=Not added: type, list price and floor price are required.",
                                status_code=303)
    if fp > lp:
        return RedirectResponse(f"/inventory/project/{pid}?msg=Not added: floor price is above list price.",
                                status_code=303)
    db.insert("units", {"project_id": pid, "unit_no": g("unit_no"), "unit_type": g("unit_type").upper().replace(" BHK", "BHK"),
                        "floor": g("floor"), "facing": g("facing").title(), "size_sqft": inventory._int(g("size_sqft")),
                        "carpet_sqft": inventory._int(g("carpet_sqft")), "list_price": lp, "floor_price": fp,
                        "quantity": inventory._int(g("quantity")) or 1, "status": "available", "updated_at": db.now_iso()})
    return RedirectResponse(f"/inventory/project/{pid}?msg=Unit added.", status_code=303)


@router.post("/inventory/unit/{uid}")
async def unit_update(uid: int, request: Request, _: str = Depends(auth)):
    f = await request.form()
    u = db.q1("SELECT * FROM units WHERE id = ?", (uid,))
    if not u:
        raise HTTPException(404)
    if f.get("delete"):
        db.q("DELETE FROM units WHERE id = ?", (uid,))
        return RedirectResponse(f"/inventory/project/{u['project_id']}?msg=Unit deleted.", status_code=303)
    lp = _amt(str(f.get("list_price", ""))) or u["list_price"]
    fp = _amt(str(f.get("floor_price", ""))) or u["floor_price"]
    if fp > lp:
        return RedirectResponse(f"/inventory/project/{u['project_id']}?msg=Not saved: floor price above list price.",
                                status_code=303)
    status = str(f.get("status") or u["status"])
    db.update("units", uid, {"quantity": inventory._int(f.get("quantity")) or 0, "status": status,
                             "list_price": lp, "floor_price": fp, "updated_at": db.now_iso()})
    return RedirectResponse(f"/inventory/project/{u['project_id']}?msg=Saved.", status_code=303)


@router.post("/inventory/project/{pid}/import")
async def unit_import(pid: int, file: UploadFile = File(...), replace: str = Form(""), _: str = Depends(auth)):
    with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as fh:
        fh.write(await file.read())
        path = fh.name
    res = inventory.import_units_csv(pid, path, replace=bool(replace))
    msg = f"Imported: {res['added']} added, {res['updated']} updated."
    if res["errors"]:
        msg += " Skipped — " + "; ".join(res["errors"][:8]) + (" …" if len(res["errors"]) > 8 else "")
    return RedirectResponse(f"/inventory/project/{pid}?msg={msg}", status_code=303)


@router.get("/inventory/units-template.csv")
def units_template(_: str = Depends(auth)):
    return PlainTextResponse(",".join(inventory.CSV_COLUMNS) + "\nA-504,2BHK,5,East,1150,820,75L,69L,1,available\n"
                             ",3BHK,,,1550,1110,1.02cr,94L,6,available\n", media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=units-template.csv"})


# ============================================================ commissions

@router.get("/commissions", response_class=HTMLResponse)
def commissions_page(_: str = Depends(auth)):
    t = partners.commission_totals()
    rows = db.q("SELECT c.*, l.name lead_name, p.name project, b.name builder FROM commissions c "
                "LEFT JOIN leads l ON l.id = c.lead_id LEFT JOIN inv_projects p ON p.id = c.project_id "
                "LEFT JOIN builders b ON b.id = c.builder_id ORDER BY c.id DESC")
    trs = ""
    for c in rows:
        overdue = c["status"] in ("earned", "invoiced", "part_collected") and c["due_at"] and \
            db.parse_dt(c["due_at"]) < db.parse_dt(db.now_iso())
        trs += f"""<tr><td>C{c['id']}</td><td><a href="/leads/{c['lead_id']}">{escape(c['lead_name'] or '')}</a><br>
<small>{escape(c['project'] or '')}</small></td><td>{escape(c['builder'] or '')}</td>
<td>{fmt_money(c['deal_value'])}</td><td><b>{fmt_money(c['amount'])}</b></td>
<td>{c['status']}{' <span class="pill hot">overdue</span>' if overdue else ''}<br><small>due {escape((c['due_at'] or '')[:10])}
{(' · inv ' + escape(c['invoice_no'])) if c['invoice_no'] else ''}{(' · got ' + fmt_money(c['collected_amount'])) if c['collected_amount'] else ''}</small></td>
<td><form method="post" action="/commissions/{c['id']}" style="display:flex;gap:4px;flex-wrap:wrap">
<input name="invoice_no" placeholder="invoice no" style="width:100px"><button class="small" name="action" value="invoiced">Invoiced</button>
<input name="amount" placeholder="amount" style="width:90px"><button class="small" name="action" value="collected">Received</button>
<button class="small red" name="action" value="disputed">Dispute</button></form></td></tr>"""
    return page("Commissions", f"""<div class="card"><h3>Commission summary</h3><div class="stages">
<div class="stage">Earned<b>{fmt_money(t['earned'])}</b></div><div class="stage">Collected<b>{fmt_money(t['collected'])}</b></div>
<div class="stage">Outstanding<b>{fmt_money(t['outstanding'])}</b></div>
<div class="stage">Overdue<b>{fmt_money(t['overdue'])}</b></div></div></div>
<div class="card"><table><tr><th></th><th>Buyer</th><th>Builder</th><th>Deal</th><th>Commission</th><th>Status</th><th></th></tr>
{trs or '<tr><td colspan=7>No partner bookings yet.</td></tr>'}</table></div>
<p><a href="/registrations">Client registrations →</a></p>""")


@router.post("/commissions/{cid}")
async def commission_action(cid: int, request: Request, _: str = Depends(auth)):
    f = await request.form()
    partners.update_commission(cid, str(f.get("action")), str(f.get("invoice_no") or ""),
                               _amt(str(f.get("amount") or "")), str(f.get("note") or ""))
    return RedirectResponse("/commissions", status_code=303)


# ============================================================ registrations

@router.get("/registrations", response_class=HTMLResponse)
def registrations_page(_: str = Depends(auth)):
    rows = db.q("SELECT r.*, l.name lead_name, p.name project, b.name builder FROM registrations r "
                "LEFT JOIN leads l ON l.id = r.lead_id LEFT JOIN inv_projects p ON p.id = r.project_id "
                "LEFT JOIN builders b ON b.id = r.builder_id ORDER BY r.id DESC LIMIT 300")
    trs = "".join(f"""<tr><td>R{r['id']}</td><td><a href="/leads/{r['lead_id']}">{escape(r['lead_name'] or '')}</a></td>
<td>{escape(r['project'] or '')}<br><small>{escape(r['builder'] or '')}</small></td>
<td>{escape((r['sent_at'] or '')[:16].replace('T', ' '))}</td><td>{escape((r['valid_until'] or '')[:10])}</td>
<td>{r['status']}{'<br><small>' + escape(r['builder_note']) + '</small>' if r['builder_note'] else ''}</td>
<td><form method="post" action="/registrations/{r['id']}"><button class="small" name="action" value="acknowledged">Mark confirmed</button>
<button class="small grey" name="action" value="resend">Resend</button></form></td></tr>""" for r in rows)
    return page("Registrations", f"""<div class="card"><h3>Client registrations with partner builders</h3>
<p><small>Sent automatically in writing before each partner site visit, and renewed before they expire while the client
is active. Builders confirm with ACK R&lt;no&gt;. Keep this as proof for your commission.</small></p>
<table><tr><th></th><th>Client</th><th>Project</th><th>Sent</th><th>Valid until</th><th>Status</th><th></th></tr>
{trs or '<tr><td colspan=7>None yet.</td></tr>'}</table></div>""")


@router.post("/registrations/{rid}")
async def registration_action(rid: int, request: Request, _: str = Depends(auth)):
    f = await request.form()
    r = db.q1("SELECT * FROM registrations WHERE id = ?", (rid,))
    if not r:
        raise HTTPException(404)
    if f.get("action") == "resend":
        partners.register_client(r["lead_id"], r["project_id"], reason=f"resent (earlier R{rid})", force=True)
    else:
        db.update("registrations", rid, {"status": "acknowledged", "ack_at": db.now_iso(),
                                         "builder_note": "confirmed manually"})
    return RedirectResponse("/registrations", status_code=303)


@router.post("/leads/{lead_id}/register")
async def register_lead(lead_id: int, request: Request, _: str = Depends(auth)):
    f = await request.form()
    partners.register_client(lead_id, str(f.get("project") or ""), reason="registered manually by management",
                             force=True)
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


def lead_section(lead_id: int) -> str:
    """Registrations + 'register with builder' box for the lead page."""
    regs = db.q("SELECT r.*, p.name project FROM registrations r LEFT JOIN inv_projects p ON p.id = r.project_id "
                "WHERE r.lead_id = ? ORDER BY r.id DESC", (lead_id,))
    partner_projects = [p for p in inventory.list_projects() if not p["is_own"]]
    rows = "".join(f"<tr><td>R{r['id']}</td><td>{escape(r['project'] or '')}</td><td>{r['status']}</td>"
                   f"<td>{escape((r['valid_until'] or '')[:10])}</td></tr>" for r in regs)
    form = ("" if not partner_projects else
            f'<form method="post" action="/leads/{lead_id}/register" style="margin-top:8px">'
            '<select name="project">' + "".join(f"<option>{escape(p['name'])}</option>" for p in partner_projects)
            + '</select> <button class="small grey">Register with builder</button></form>')
    if not rows and not form:
        return ""
    return (f'<div class="card"><h4>Builder registrations</h4><table>{rows or "<tr><td>None yet.</td></tr>"}</table>'
            f'{form}</div>')
