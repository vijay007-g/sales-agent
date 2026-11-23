"""Marketing Studio pages: create posters/reels, approve, schedule, post. Owner-only, except the creative files
themselves (public, unguessable URLs, so Facebook/Instagram and WhatsApp can fetch them)."""
from __future__ import annotations

import json
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from . import db, inventory, studio

router = APIRouter()


def auth(request: Request) -> str:
    from .server import check_auth_header, client_ip
    return check_auth_header(request.headers.get("authorization"), client_ip(request))


def _page(title, body):
    from .server import page
    return page(title, body)


def _back(msg: str) -> RedirectResponse:
    return RedirectResponse(f"/studio?msg={quote(msg)}", status_code=303)


@router.get("/creative/{filename}")
def creative_file(filename: str, download: int = 0):
    if "/" in filename or ".." in filename:
        return HTMLResponse("Not found", status_code=404)
    row = db.q1("SELECT filename FROM creatives WHERE filename = ?", (filename,))
    path = studio.creative_dir() / filename
    if not row or not path.exists():
        return HTMLResponse("Not found", status_code=404)
    media = "video/mp4" if filename.endswith(".mp4") else "image/jpeg"
    return FileResponse(path, media_type=media, filename=filename.split("_", 1)[-1] if download else None)


def _card(c: dict, projects: dict) -> str:
    p = projects.get(c["project_id"]) or {}
    url = f"/creative/{escape(c['filename'])}"
    copy = json.loads(c["copy"] or "{}")
    warn = "".join(f"<div class='notice' style='padding:4px 8px;margin:4px 0'>⚠️ {escape(w)}</div>"
                   for w in copy.get("warnings", []))
    media = (f"<video src='{url}' controls preload='metadata' style='width:100%;border-radius:8px'></video>"
             if c["kind"] == "reel" else f"<a href='{url}' target='_blank'><img src='{url}' loading='lazy' "
                                        f"style='width:100%;border-radius:8px'></a>")
    when = (c["post_at"] or "")[:16].replace("T", " ")
    status = {"draft": "Draft", "approved": f"Scheduled {when}", "reminded": "Sent to you to post",
              "published": "Posted ✅", "rejected": "Rejected"}.get(c["status"], c["status"])
    btns = ""
    if c["status"] == "draft":
        btns += (f"<form method='post' action='/studio/{c['id']}/approve' style='display:inline'><button class='small'>"
                 f"Approve</button></form> <form method='post' action='/studio/{c['id']}/reject' style='display:inline'>"
                 f"<button class='small red'>Reject</button></form>")
    if c["status"] in ("approved", "reminded") and studio.publishing_ready() and c["format"] != "story":
        btns += (f" <form method='post' action='/studio/{c['id']}/publish' style='display:inline'><button class='small'>"
                 f"Post to FB/IG now</button></form>")
    if c["status"] in ("approved", "reminded"):
        btns += (f" <form method='post' action='/studio/{c['id']}/posted' style='display:inline'><button class='small'>"
                 f"I posted it</button></form>")
    btns += f" <a class='small' href='{url}?download=1'>Download</a>"
    cap = (f"<details><summary><small>Caption</small></summary><form method='post' action='/studio/{c['id']}/caption'>"
           f"<textarea name='caption' rows='7' style='width:100%'>{escape(c['caption'] or '')}</textarea>"
           f"<button class='small'>Save caption</button></form></details>")
    return (f"<div class='card' style='padding:10px'>{media}<p style='margin:6px 0'><b>{escape(p.get('name', '?'))}</b>"
            f"<br><small>{escape(studio.FORMAT_LABEL.get(c['format'], c['format']))} · {escape(c['design'] or '')} · "
            f"angle: {escape(c['angle'] or '')}<br>{escape(status)}</small></p>{warn}{btns}{cap}</div>")


@router.get("/studio", response_class=HTMLResponse)
def studio_home(msg: str = "", show: str = "drafts", _: str = Depends(auth)):
    projects = {p["id"]: inventory.get_project(p["id"]) for p in inventory.list_projects(active_only=False)}
    c = studio.cfg()
    opts = "".join(f"<option value='{pid}'>{escape(p['name'])}</option>" for pid, p in projects.items()
                   if p and p.get("active"))
    angles = "".join(f"<option value='{k}'>{escape(v.split(':')[0])}</option>" for k, v in studio.ANGLES.items())
    ready_rows = ""
    for pid, p in projects.items():
        if not p or not p.get("active"):
            continue
        photos = len(studio.photo_paths(p))
        probs = studio.blockers(p)
        perm = ("own project" if p["is_own"] else
                ("✅ received" if p.get("marketing_ok") else
                 f"<form method='post' action='/studio/project/{pid}/permission'><button class='small'>Mark "
                 f"permission received</button></form>"))
        ready_rows += (f"<tr><td><a href='/inventory/project/{pid}'>{escape(p['name'])}</a></td>"
                       f"<td>{'✅' if (p.get('rera') or '').strip() else '❌ add RERA no.'}</td>"
                       f"<td>{photos or '⚠️ none (colour background)'}</td><td>{perm}</td>"
                       f"<td>{'✅ ready' if not probs else '<small>' + escape('; '.join(probs)) + '</small>'}</td></tr>")
    status_sql = {"drafts": "('draft')", "scheduled": "('approved','reminded')", "posted": "('published')",
                  "rejected": "('rejected')"}.get(show, "('draft')")
    items = db.q(f"SELECT * FROM creatives WHERE status IN {status_sql} ORDER BY id DESC LIMIT 60")
    counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM creatives GROUP BY status")}
    tabs = " · ".join(
        (f"<b>{label}</b>" if key == show else f"<a href='/studio?show={key}'>{label}</a>") + f" ({n})"
        for key, label, n in (("drafts", "Drafts", counts.get("draft", 0)),
                              ("scheduled", "Scheduled", counts.get("approved", 0) + counts.get("reminded", 0)),
                              ("posted", "Posted", counts.get("published", 0)),
                              ("rejected", "Rejected", counts.get("rejected", 0))))
    grid = "".join(_card(x, projects) for x in items) or "<p>Nothing here yet.</p>"
    pub = ("✅ connected — " + ("posts go out automatically at the scheduled time" if c["auto_publish"]
                               else "use “Post to FB/IG now”, or set <code>marketing.auto_publish: true</code>")
           if studio.publishing_ready() else
           "not connected — at the scheduled time you get a WhatsApp with the image and caption to post "
           "(connect later with META_PAGE_ID, META_PAGE_TOKEN and META_IG_USER_ID in Railway)")
    note = f'<div class="notice">{escape(msg)}</div>' if msg else ""
    return _page("Marketing Studio", f"""<h2>Marketing Studio</h2>{note}
<div class="card"><p>Claude writes the words; the studio lays them over the <b>builder's real photos</b> (upload them in
Inventory → project → Sales kit, kind “photo”). It never invents pictures of buildings. Every creative carries the
project RERA number, your agent RERA number and a price footnote. Prices come from Inventory, never from the AI.
Nothing is posted until you approve it.</p>
<p><small>Weekly pack: {'every Monday 08:00, drafted automatically' if c['weekly_pack'] else 'off'} · Posting time
{escape(c['post_time'])} (one feed post and one story a day) · Facebook/Instagram: {pub}</small></p>
<form method="post" action="/studio/pack" style="display:inline"><button>Make this week's pack now</button></form></div>

<div class="card"><h3>Create for one project</h3>
<form method="post" action="/studio/create" style="display:flex;flex-wrap:wrap;gap:10px;align-items:end">
<label>Project<br><select name="project_id">{opts}</select></label>
<label>Angle<br><select name="angle">{angles}</select></label>
<label><input type="checkbox" name="feed" value="1" checked> Feed posts</label>
<label><input type="checkbox" name="story" value="1" checked> Stories / WhatsApp status</label>
<label><input type="checkbox" name="reel" value="1"> Reel (15–20 s video)</label>
<label style="flex:1;min-width:220px">Your idea (optional)<br><input name="brief" placeholder="e.g. Pongal offer: free car park (builder approved)" style="width:100%"></label>
<button>Create 3 designs</button></form>
<p><small>Takes 20–60 seconds. Each run makes 3 different designs per format, so you can pick the best one.</small></p></div>

<div class="card"><h3>Projects ready for marketing</h3>
<table><tr><th>Project</th><th>RERA no.</th><th>Photos</th><th>Builder permission</th><th>Status</th></tr>
{ready_rows or '<tr><td colspan=5>No projects yet.</td></tr>'}</table>
<p><small>Partner projects need the builder's written OK to advertise their project (keep their email or letter).
Drafts can still be made, so you can show them to the builder for sign-off.</small></p></div>

<p>{tabs}</p>
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">{grid}</div>""")


@router.post("/studio/create")
def studio_create(project_id: int = Form(...), angle: str = Form("ready"), feed: str = Form(""), story: str = Form(""),
                  reel: str = Form(""), brief: str = Form(""), _: str = Depends(auth)):
    formats = tuple(f for f, on in (("feed", feed), ("story", story)) if on)
    if not formats and not reel:
        return _back("Pick at least one format.")
    r = studio.create(project_id, formats, angle, reel=bool(reel), brief=brief)
    if not r["ok"]:
        return _back(r["error"])
    msg = f"Created {len(r['ids'])} drafts for {r['project']}."
    if not r["photos"]:
        msg += " No photos uploaded for this project, so colour backgrounds were used: upload builder photos for better results."
    if r["fallback"]:
        msg += " (The AI was unavailable, so simple copy from the project facts was used.)"
    if r["reel_error"]:
        msg += f" Reel failed: {r['reel_error']}"
    return _back(msg)


@router.post("/studio/pack")
def studio_pack(_: str = Depends(auth)):
    r = studio.weekly_pack()
    if not r["ok"]:
        return _back("No project is ready yet: each needs a RERA number, available units and (for partner projects) "
                     "the builder's permission. See the table below.")
    return _back(f"This week's pack: {r['creatives']} drafts for {r['projects']} project(s).")


@router.post("/studio/{cid}/approve")
def studio_approve(cid: int, _: str = Depends(auth)):
    r = studio.approve(cid)
    return _back(f"Approved — scheduled for {r['post_at'][:16].replace('T', ' ')}." if r["ok"] else r["error"])


@router.post("/studio/{cid}/reject")
def studio_reject(cid: int, _: str = Depends(auth)):
    studio.reject(cid)
    return _back("Rejected.")


@router.post("/studio/{cid}/caption")
def studio_caption(cid: int, caption: str = Form(""), _: str = Depends(auth)):
    studio.set_caption(cid, caption)
    return _back("Caption saved.")


@router.post("/studio/{cid}/publish")
def studio_publish(cid: int, _: str = Depends(auth)):
    r = studio.publish(cid)
    return _back("Posted to Facebook" + (" and Instagram" if r.get("instagram") else "") + "." if r["ok"]
                 else f"Couldn't post: {r['error']}")


@router.post("/studio/{cid}/posted")
def studio_posted(cid: int, _: str = Depends(auth)):
    studio.mark_posted(cid)
    return _back("Marked as posted.")


@router.post("/studio/project/{pid}/permission")
def studio_permission(pid: int, _: str = Depends(auth)):
    db.update("inv_projects", pid, {"marketing_ok": 1})
    db.audit(None, "owner", "marketing_permission", str(pid))
    return _back("Builder permission recorded. Keep their written OK (email/letter) on file.")
