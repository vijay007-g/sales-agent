"""Marketing Studio: AI-written, compliance-checked posters and reels from real project photos.

How it works
- Claude writes the words: 3 headline/copy variants per project and angle, plus a caption, hashtags and reel lines.
  It never writes prices; prices come from Inventory, so they can't be invented.
- The studio lays the words over the builder's REAL photos and renders (Inventory → project → Sales kit → photo).
  It never generates images of buildings: an invented building would be misleading advertising under RERA.
- Every creative carries the project RERA number, our agent RERA number, "marketed by", and a price footnote.
- Nothing goes public until you approve it. Partner projects also need the builder's written OK to market them.
- Approved posts are scheduled one a day. At the time: auto-posted to Facebook/Instagram (if connected and
  `marketing.auto_publish: true`); otherwise you get a WhatsApp with the image and caption ready to post. Story-size
  creatives also go to the salespeople for their WhatsApp status.
- Every Monday at 08:00 a weekly pack (3 projects × feed + story, plus 1 reel) is drafted for approval.

Settings (Admin → Settings → Advanced, all optional):
  marketing:
    weekly_pack: true
    auto_publish: false
    post_time: "19:30"
    cta_phone: ""        # number shown on posters; default = office phone, else your number
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import channels, db, inventory, sales_kit
from .config import DATA_DIR, env, get_settings, rera_for

FORMATS = {"feed": (1080, 1350), "story": (1080, 1920)}
FORMAT_LABEL = {"feed": "Feed post 4:5 (Instagram / Facebook)", "story": "Story / WhatsApp status 9:16",
                "reel": "Reel 9:16 video"}
ANGLES = {
    "ready": "Ready to move / near possession: see the finished home, move in soon, no waiting",
    "location": "Location and commute: time to IT parks, schools, hospitals, metro; everyday convenience",
    "lifestyle": "Lifestyle and amenities: what an ordinary weekday and weekend feel like living here",
    "value": "Value: sensible pricing, payment plan and any builder-approved offer (only facts given)",
    "family": "Family: space, safety, schools, room for parents, community",
}
THEMES = [
    {"name": "Navy & gold", "bg": (18, 30, 52), "bg2": (40, 64, 104), "accent": (236, 184, 72),
     "text": (255, 255, 255), "sub": (214, 222, 236), "on_accent": (24, 24, 24)},
    {"name": "Ivory & terracotta", "bg": (250, 246, 238), "bg2": (232, 222, 204), "accent": (182, 64, 46),
     "text": (30, 32, 40), "sub": (86, 90, 102), "on_accent": (255, 255, 255)},
    {"name": "Forest & sun", "bg": (14, 60, 48), "bg2": (30, 96, 76), "accent": (255, 208, 98),
     "text": (255, 255, 255), "sub": (208, 232, 222), "on_accent": (24, 24, 24)},
]
DESIGNS = ["overlay", "panel", "frame"]
RISKY = re.compile(r"\b(guarantee[ds]?|assured returns?|best|no\.?\s?1|number one|lowest|cheapest|100%|risk[- ]free|"
                   r"double your|appreciation of)\b", re.I)


def cfg() -> dict:
    c = get_settings().raw.get("marketing") or {}
    return {"weekly_pack": c.get("weekly_pack", True) is not False, "auto_publish": bool(c.get("auto_publish")),
            "post_time": str(c.get("post_time") or "19:30"), "cta_phone": str(c.get("cta_phone") or "")}


def creative_dir() -> Path:
    d = DATA_DIR / "creatives"
    d.mkdir(parents=True, exist_ok=True)
    return d


def creative_url(c: dict) -> str:
    from .team import base_url
    return f"{base_url()}/creative/{c['filename']}"


def publishing_ready() -> bool:
    return bool(env("META_PAGE_ID") and env("META_PAGE_TOKEN"))


# ------------------------------------------------------------------ project facts for posters

def cta_phone() -> str:
    s = get_settings()
    raw = cfg()["cta_phone"] or s.booking.get("office_phone") or s.owner.get("phone") or ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        return f"+91 {digits[2:7]} {digits[7:]}"
    return raw


def short_money(v: int | None) -> str:
    if not v:
        return ""
    if v >= 10_000_000:
        return f"₹{v / 10_000_000:.2f}".rstrip("0").rstrip(".") + " Cr"
    return f"₹{round(v / 100_000)} L"


def offer_line(proj: dict) -> str:
    types = [t for t in inventory.type_summary(proj["id"]) if t["available"]]
    if not types:
        return ""
    names = sorted({t["type"] for t in types}, key=lambda x: (len(x), x))
    pmin = min((t["price_min"] for t in types if t["price_min"]), default=None)
    label = " & ".join(names[:3]) if all(n[:1].isdigit() for n in names[:3]) else ", ".join(names[:3])
    label = re.sub(r"(\d)BHK & (\d)BHK & (\d)BHK", r"\1, \2 & \3 BHK", label)
    label = re.sub(r"(\d)BHK & (\d)BHK", r"\1 & \2 BHK", label)
    return f"{label} · from {short_money(pmin)}*" if pmin else label


def footer_text(proj: dict) -> str:
    s = get_settings()
    agent = rera_for(proj["city"])
    builder = "" if proj["is_own"] else f" for {proj['builder']}"
    return (f"{proj['name']}, {proj['locality'] or ''} {proj['city'] or ''} · Project RERA: {proj['rera'] or '—'} · "
            f"Marketed by {s.business['name']}{builder} (RERA agent: {agent or '—'}). *Starting price, excludes "
            f"registration, stamp duty & other charges; subject to availability. Pictures are actual project photos / "
            f"builder renders (artist's impression).").replace("  ", " ")


def blockers(proj: dict) -> list[str]:
    """Reasons a creative cannot be approved or published."""
    out = []
    if not (proj.get("rera") or "").strip():
        out.append("Project RERA number missing (Inventory → project)")
    if not rera_for(proj["city"]):
        out.append("Your RERA agent number missing (Settings → Company)")
    if proj.get("is_sample"):
        out.append("Sample project: not a real listing")
    if not proj["is_own"] and not proj.get("marketing_ok"):
        out.append("Builder's written permission to market this project not marked yet")
    return out


def photo_paths(proj: dict) -> list[str]:
    out = []
    for m in sales_kit.find_media(proj["id"], "photo"):
        if (m["mime"] or "").startswith("image/") and m["path"] and os.path.exists(m["path"]):
            out.append(m["path"])
    return out


# ------------------------------------------------------------------ copy (Claude)

COPY_SCHEMA = {
    "type": "object",
    "properties": {
        "variants": {"type": "array", "items": {"type": "object", "properties": {
            "headline": {"type": "string"}, "subline": {"type": "string"},
            "bullets": {"type": "array", "items": {"type": "string"}},
            "tag": {"type": "string"}, "cta": {"type": "string"}},
            "required": ["headline", "subline", "bullets", "tag", "cta"], "additionalProperties": False}},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "reel_lines": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["variants", "caption", "hashtags", "reel_lines"],
    "additionalProperties": False,
}


def _past_winners() -> str:
    rows = db.q("SELECT angle, COUNT(*) n FROM creatives WHERE status IN ('approved','published','reminded') "
                "GROUP BY angle ORDER BY n DESC LIMIT 5")
    return ", ".join(f"{r['angle']} ({r['n']} approved)" for r in rows) or "none yet"


def write_copy(proj: dict, angle: str, brief: str = "") -> dict:
    from .agent import get_client
    from .marketing import _playbook
    s = get_settings()
    facts = inventory.project_facts(proj, max_units=0)
    facts.pop("extras_needing_management_approval", None)
    prompt = f"""Write social-media poster copy for this home project, for buyers in {proj['city']}.

<project>{json.dumps(facts, default=str)}</project>
<angle>{ANGLES.get(angle, angle)}</angle>
<owner_brief>{brief or 'none'}</owner_brief>
<brand>{s.business['name']} — honest, warm, specific. Audience: salaried families aged 28–45, first home or upgrade.</brand>
<what_buyers_responded_to>{_playbook()}</what_buyers_responded_to>
<angles_owner_approved_before>{_past_winners()}</angles_owner_approved_before>

Give exactly 3 variants that each try a clearly different hook within the angle.
- headline: at most 6 words, concrete and specific to this project (no "dream home", no clichés).
- subline: at most 12 words.
- bullets: 3 short facts (at most 6 words each) taken ONLY from the project data.
- tag: 1–3 words for a corner badge, e.g. "Ready to move", "Near OMR IT parks".
- cta: at most 4 words, e.g. "WhatsApp for site visit".
- caption: 2–4 short lines for Instagram/Facebook, friendly, ending with a call to WhatsApp or book a visit.
- hashtags: 6–10, local and relevant (city, locality, BHK).
- reel_lines: 4 lines of at most 7 words each, telling a mini story for a 15-second reel.
Strict rules: never write any price or rupee amount (the studio adds verified prices itself); never promise returns,
appreciation, "guaranteed", "best", "lowest", "No.1" or anything not in the data; no emojis in headlines."""
    resp = get_client().beta.messages.create(
        model=s.agent.get("model", "claude-opus-5-5"),
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": COPY_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("The model declined to write this copy.")
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    if not data.get("variants"):
        raise RuntimeError("No copy variants returned.")
    return data


def fallback_copy(proj: dict, angle: str) -> dict:
    """Plain copy from the facts, used if the AI is unavailable, so the studio never stops working."""
    hl = (proj.get("highlights") or [])[:3]
    tag = "Ready to move" if inventory._possession_ok(proj, "ready") else (proj.get("possession") or "New launch")
    base = {"subline": f"{proj['locality'] or ''} {proj['city'] or ''}".strip(), "bullets": hl, "tag": tag,
            "cta": "WhatsApp for site visit"}
    return {"variants": [{**base, "headline": proj["name"]},
                         {**base, "headline": f"Homes in {proj['locality'] or proj['city']}"},
                         {**base, "headline": f"Visit {proj['name']} this weekend"}],
            "caption": f"{proj['name']} in {proj['locality'] or proj['city']}. Message us to plan a site visit.",
            "hashtags": [f"#{(proj['city'] or '').replace(' ', '')}Homes", f"#{(proj['locality'] or '').replace(' ', '')}"],
            "reel_lines": [proj["name"], *(hl[:2]), "Book your site visit"], "fallback": True}


def warnings_for(copy_variant: dict) -> list[str]:
    text = " ".join([copy_variant.get("headline", ""), copy_variant.get("subline", ""),
                     *copy_variant.get("bullets", []), copy_variant.get("tag", "")])
    out = []
    if RISKY.search(text):
        out.append(f"Claim to check: \"{RISKY.search(text).group(0)}\"")
    if "₹" in text or re.search(r"\b\d+(\.\d+)?\s?(L|lakh|Cr|crore)\b", text, re.I):
        out.append("Contains a price written by the AI — check it")
    return out


# ------------------------------------------------------------------ rendering

_FONT_FILES = {
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
}


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False):
    for f in _FONT_FILES[bold]:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def _wrap(draw, text: str, fnt, width: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=fnt) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, width, max_lines, start, smallest, bold=True):
    size = start
    while True:
        f = font(size, bold)
        lines = _wrap(draw, text, f, width)
        if len(lines) <= max_lines or size <= smallest:
            return f, lines[:max_lines], size
        size -= 4


def _gradient(size, top, bottom) -> Image.Image:
    w, h = size
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g.resize((w, h))


def _shade(size, start_frac, max_alpha) -> Image.Image:
    """Transparent → dark from start_frac of the height to the bottom (keeps text readable on photos)."""
    w, h = size
    a = Image.new("L", (1, h), 0)
    s0 = int(h * start_frac)
    for y in range(s0, h):
        a.putpixel((0, y), int(max_alpha * min(1, (y - s0) / max(h * 0.35, 1))))
    layer = Image.new("RGBA", (w, h), (8, 10, 16, 0))
    layer.putalpha(a.resize((w, h)))
    return layer


def render_poster(proj: dict, v: dict, fmt: str, design: str, theme: dict, photo: str | None) -> Image.Image:
    W, H = FORMATS[fmt]
    story = fmt == "story"
    pad = 64
    img = Image.new("RGBA", (W, H), theme["bg"] + (255,))
    pic = None
    if photo:
        try:
            pic = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
        except Exception:  # noqa: BLE001 - a broken upload falls back to a colour background
            pic = None

    if design == "overlay":
        img.paste(ImageOps.fit(pic, (W, H)) if pic else _gradient((W, H), theme["bg2"], theme["bg"]), (0, 0))
        img = Image.alpha_composite(img, _shade((W, H), 0.30, 235))
        top = Image.new("RGBA", (W, 170), (0, 0, 0, 90))
        img.alpha_composite(top, (0, 0))
        main, sub, text_top = (255, 255, 255), (228, 232, 240), int(H * (0.50 if not story else 0.52))
    elif design == "panel":
        split = int(H * (0.38 if not story else 0.46))
        img.paste(ImageOps.fit(pic, (W, split)) if pic else _gradient((W, split), theme["bg2"], theme["bg"]), (0, 0))
        img.alpha_composite(Image.new("RGBA", (W, 170), (0, 0, 0, 80)), (0, 0))
        main, sub, text_top = theme["text"], theme["sub"], split + 48
    else:  # frame
        img.paste(_gradient((W, H), theme["bg"], theme["bg2"]), (0, 0))
        main, sub, text_top = theme["text"], theme["sub"], 0

    d = ImageDraw.Draw(img)
    brand_color = (255, 255, 255) if design != "frame" else theme["text"]
    d.text((pad, 58), get_settings().business["name"].upper(), font=font(34, True), fill=brand_color)
    tag = (v.get("tag") or "").strip().upper()[:26]
    if tag:
        tf = font(26, True)
        tw = d.textlength(tag, font=tf)
        x1 = W - pad
        d.rounded_rectangle((x1 - tw - 40, 50, x1, 102), radius=26, fill=theme["accent"])
        d.text((x1 - tw - 20, 62), tag, font=tf, fill=theme["on_accent"])

    # footer (fixed at the bottom)
    ff = font(21 if not story else 23)
    flines = _wrap(d, footer_text(proj), ff, W - 2 * pad)[:5]
    fh = len(flines) * 29 + 36
    ftop = H - fh
    band = (0, 0, 0, 150) if design == "overlay" else theme["bg2"] + (255,)
    img.alpha_composite(Image.new("RGBA", (W, fh), band), (0, ftop))
    d = ImageDraw.Draw(img)
    fcol = (226, 230, 238) if design == "overlay" else theme["sub"]
    for i, ln in enumerate(flines):
        d.text((pad, ftop + 18 + i * 29), ln, font=ff, fill=fcol)

    # text block, measured first so it never runs into the footer
    width = W - 2 * pad
    hf, hl, hs = _fit(d, v.get("headline", ""), width, 3, 96 if story else 84, 52)
    sf = font(40 if story else 36)
    sl = _wrap(d, v.get("subline", ""), sf, width)[:2]
    bf = font(36 if story else 32)
    bullets = [b for b in (v.get("bullets") or []) if b][:3]
    price = offer_line(proj)
    pf = font(50 if story else 44, True)
    cta = f"{(v.get('cta') or 'WhatsApp us').strip()}  {cta_phone()}".strip()
    cf = font(32 if story else 30, True)

    def block_height(nb):
        return (len(hl) * int(hs * 1.12) + 18 + len(sl) * 48 + 16 + nb * 46 + (70 if price else 0) + 100)

    nb = len(bullets)
    if design == "frame":
        y = 150
        for ln in hl:
            d.text((pad, y), ln, font=hf, fill=main)
            y += int(hs * 1.12)
        for ln in sl:
            d.text((pad, y + 8), ln, font=sf, fill=sub)
            y += 48
        y += 30
        rest = nb * 46 + (70 if price else 0) + 100 + 40
        box_h = ftop - rest - y - 20
        while box_h < 260 and nb:
            nb -= 1
            rest = nb * 46 + (70 if price else 0) + 100 + 40
            box_h = ftop - rest - y - 20
        if box_h > 120:
            inner = ImageOps.fit(pic, (width, box_h)) if pic else _gradient((width, box_h), theme["bg2"], theme["bg"])
            mask = Image.new("L", (width, box_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, box_h), radius=28, fill=255)
            img.paste(inner, (pad, y), mask)
            d = ImageDraw.Draw(img)
            y += box_h + 30
    else:
        y = text_top
        limit = ftop - 24
        if y + block_height(nb) > limit and design == "overlay":
            y = max(int(H * 0.30), limit - block_height(nb))
        while y + block_height(nb) > limit and nb:
            nb -= 1
        if y + block_height(nb) > limit:
            y = max(190, limit - block_height(nb))
        for ln in hl:
            d.text((pad, y), ln, font=hf, fill=main)
            y += int(hs * 1.12)
        y += 6
        for ln in sl:
            d.text((pad, y), ln, font=sf, fill=sub)
            y += 48
        y += 16
    for b in bullets[:nb]:
        txt = f"•  {b}"
        while d.textlength(txt, font=bf) > width and len(txt) > 8:
            txt = txt[:-2]
        d.text((pad, y), txt, font=bf, fill=main)
        y += 46
    if price:
        y += 10
        d.text((pad, y), price, font=pf, fill=theme["accent"] if design != "overlay" or theme["name"] != "Ivory & terracotta"
               else (255, 210, 120))
        y += 66
    cw = min(d.textlength(cta, font=cf) + 56, width)
    d.rounded_rectangle((pad, y + 6, pad + cw, y + 76), radius=36, fill=theme["accent"])
    d.text((pad + 28, y + 24), cta, font=cf, fill=theme["on_accent"])
    return img.convert("RGB")


def _save(img: Image.Image, stem: str) -> str:
    name = f"{db.new_token()}_{stem}.jpg"
    img.save(creative_dir() / name, "JPEG", quality=90, optimize=True)
    return name


# ------------------------------------------------------------------ reels

def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - fall back to a system ffmpeg
        return shutil.which("ffmpeg")


def _reel_slide(proj: dict, line: str, theme: dict, photo: str | None, first: bool) -> Image.Image:
    W, H = FORMATS["story"]
    img = Image.new("RGBA", (W, H), theme["bg"] + (255,))
    pic = None
    if photo:
        try:
            pic = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
        except Exception:  # noqa: BLE001
            pic = None
    img.paste(ImageOps.fit(pic, (W, H)) if pic else _gradient((W, H), theme["bg2"], theme["bg"]), (0, 0))
    img = Image.alpha_composite(img, _shade((W, H), 0.45, 220))
    d = ImageDraw.Draw(img)
    d.text((64, 70), get_settings().business["name"].upper(), font=font(34, True), fill=(255, 255, 255))
    f, lines, size = _fit(d, line, W - 128, 3, 92, 56)
    y = int(H * 0.66)
    if first:
        d.text((64, y - 70), proj["name"], font=font(44, True), fill=theme["accent"])
    for ln in lines:
        d.text((64, y), ln, font=f, fill=(255, 255, 255))
        y += int(size * 1.15)
    return img.convert("RGB")


def render_reel(proj: dict, copy: dict, photos: list[str], end_card: Image.Image) -> str:
    exe = _ffmpeg()
    if not exe:
        raise RuntimeError("Video tool (ffmpeg) is not available on the server.")
    theme = THEMES[0]
    lines = [ln for ln in (copy.get("reel_lines") or []) if ln][:4] or [proj["name"]]
    with tempfile.TemporaryDirectory() as tmp:
        slides = []
        for i, ln in enumerate(lines):
            p = os.path.join(tmp, f"s{i}.jpg")
            _reel_slide(proj, ln, theme, photos[i % len(photos)] if photos else None, i == 0).save(p, quality=92)
            slides.append(p)
        endp = os.path.join(tmp, "end.jpg")
        end_card.save(endp, quality=92)
        slides.append(endp)
        args = [exe, "-y", "-loglevel", "error"]
        for p in slides:
            args += ["-i", p]
        parts = []
        for i in range(len(slides)):
            frames = 120 if i == len(slides) - 1 else 90
            parts.append(f"[{i}:v]scale=1080:1920,zoompan=z='min(zoom+0.0006,1.06)':d={frames}:s=1080x1920:fps=30,"
                         f"setsar=1[v{i}]")
        parts.append("".join(f"[v{i}]" for i in range(len(slides))) + f"concat=n={len(slides)}:v=1:a=0,format=yuv420p[out]")
        name = f"{db.new_token()}_reel.mp4"
        args += ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "26", "-movflags", "+faststart", str(creative_dir() / name)]
        r = subprocess.run(args, capture_output=True, text=True, timeout=240)
        if r.returncode != 0:
            raise RuntimeError(f"Video rendering failed: {r.stderr[-300:]}")
    return name


# ------------------------------------------------------------------ create / approve / post

def full_caption(proj: dict, copy: dict) -> str:
    from .team import base_url
    slug = inventory.ensure_slug(proj["id"])
    tags = " ".join(h if h.startswith("#") else f"#{h}" for h in (copy.get("hashtags") or [])[:10])
    price = offer_line(proj)
    return "\n".join(x for x in [
        copy.get("caption", "").strip(), price and f"{price}", f"📲 WhatsApp {cta_phone()} · Details: "
        f"{base_url()}/p/{slug}?src=instagram&c=STUDIO", tags,
        f"Project RERA: {proj['rera'] or '—'} · Agent RERA: {rera_for(proj['city']) or '—'} · "
        f"Marketed by {get_settings().business['name']}. *Excl. registration & other charges."] if x)


def create(project_ref, formats=("feed", "story"), angle: str = "ready", reel: bool = False, brief: str = "",
           pack: str = "") -> dict:
    proj = inventory.get_project(project_ref)
    if not proj:
        return {"ok": False, "error": "Project not found"}
    if not (proj.get("rera") or "").strip():
        return {"ok": False, "error": f"Add {proj['name']}'s RERA number in Inventory first — every ad must show it."}
    try:
        copy = write_copy(proj, angle, brief)
    except Exception as e:  # noqa: BLE001 - keep the studio working without the AI
        db.audit(None, "system", "studio_copy_fallback", str(e)[:200])
        copy = fallback_copy(proj, angle)
    photos = photo_paths(proj)
    caption = full_caption(proj, copy)
    ids = []
    for fmt in formats:
        if fmt not in FORMATS:
            continue
        for i, v in enumerate(copy["variants"][:3]):
            v = {**v, "warnings": warnings_for(v)}
            img = render_poster(proj, v, fmt, DESIGNS[i % 3], THEMES[i % 3], photos[i % len(photos)] if photos else None)
            name = _save(img, f"{inventory.slugify(proj['name'])}-{fmt}-{i + 1}")
            ids.append(db.insert("creatives", {
                "project_id": proj["id"], "kind": "poster", "format": fmt, "design": f"{DESIGNS[i % 3]} · "
                f"{THEMES[i % 3]['name']}", "angle": angle, "filename": name, "caption": caption,
                "copy": json.dumps(v, ensure_ascii=False), "pack": pack, "status": "draft",
                "created_at": db.now_iso()}))
    reel_error = ""
    if reel:
        try:
            end = render_poster(proj, copy["variants"][0], "story", "overlay", THEMES[0], photos[0] if photos else None)
            name = render_reel(proj, copy, photos, end)
            ids.append(db.insert("creatives", {
                "project_id": proj["id"], "kind": "reel", "format": "reel", "design": "slideshow", "angle": angle,
                "filename": name, "caption": caption,
                "copy": json.dumps({"reel_lines": copy.get("reel_lines", []), "warnings": []}, ensure_ascii=False),
                "pack": pack, "status": "draft", "created_at": db.now_iso()}))
        except Exception as e:  # noqa: BLE001 - posters are still useful without the reel
            reel_error = str(e)[:300]
    db.audit(None, "owner" if not pack else "system", "studio_created",
             {"project": proj["name"], "count": len(ids), "angle": angle})
    return {"ok": True, "ids": ids, "project": proj["name"], "photos": len(photos), "reel_error": reel_error,
            "fallback": bool(copy.get("fallback"))}


def get(cid: int) -> dict | None:
    return db.q1("SELECT * FROM creatives WHERE id = ?", (cid,))


def next_slot(fmt: str) -> str:
    """One feed post (or reel) a day and one story a day, at the configured time, from tomorrow if today's passed."""
    s = get_settings()
    hh, mm = (int(x) for x in cfg()["post_time"].split(":"))
    lane = ("story",) if fmt == "story" else ("feed", "reel")
    marks = ",".join("?" for _ in lane)
    taken = {r["post_at"][:10] for r in db.q(f"SELECT post_at FROM creatives WHERE status = 'approved' AND post_at "
                                             f"IS NOT NULL AND format IN ({marks})", lane)}
    day = s.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    if day <= s.now():
        day += timedelta(days=1)
    while day.date().isoformat() in taken:
        day += timedelta(days=1)
    return day.isoformat(timespec="seconds")


def approve(cid: int, actor: str = "owner") -> dict:
    c = get(cid)
    if not c:
        return {"ok": False, "error": "Not found"}
    proj = inventory.get_project(c["project_id"])
    problems = blockers(proj) if proj else ["Project deleted"]
    if problems:
        return {"ok": False, "error": "Can't approve yet: " + "; ".join(problems)}
    when = next_slot(c["format"])
    db.update("creatives", cid, {"status": "approved", "approved_at": db.now_iso(), "post_at": when})
    db.audit(None, actor, "studio_approved", str(cid))
    return {"ok": True, "post_at": when}


def reject(cid: int) -> None:
    db.update("creatives", cid, {"status": "rejected"})


def set_caption(cid: int, caption: str) -> None:
    db.update("creatives", cid, {"caption": caption.strip()[:2200]})


def _graph_post(path: str, data: dict) -> dict:
    import requests

    from .lead_sources import GRAPH
    r = requests.post(f"{GRAPH}/{path}", data={**data, "access_token": env("META_PAGE_TOKEN")}, timeout=60)
    try:
        body = r.json()
    except ValueError:
        body = {"error": r.text[:200]}
    if r.status_code >= 400 or "error" in body:
        raise RuntimeError(str(body.get("error", body))[:300])
    return body


def _graph_get(path: str, params: dict) -> dict:
    import requests

    from .lead_sources import GRAPH
    return requests.get(f"{GRAPH}/{path}", params={**params, "access_token": env("META_PAGE_TOKEN")}, timeout=30).json()


def publish(cid: int) -> dict:
    """Post to the Facebook Page (and Instagram if META_IG_USER_ID is set). Stories are not auto-posted."""
    import time
    c = get(cid)
    if not c or not publishing_ready():
        return {"ok": False, "error": "Facebook/Instagram publishing is not connected (META_PAGE_ID, META_PAGE_TOKEN)."}
    if c["format"] == "story":
        return {"ok": False, "error": "Stories are posted by hand (Instagram app / WhatsApp status)."}
    url, cap, page, ig = creative_url(c), c["caption"] or "", env("META_PAGE_ID"), env("META_IG_USER_ID")
    done = {}
    try:
        if c["kind"] == "reel":
            done["facebook"] = _graph_post(f"{page}/videos", {"file_url": url, "description": cap}).get("id")
        else:
            done["facebook"] = _graph_post(f"{page}/photos", {"url": url, "caption": cap}).get("id")
        if ig:
            params = {"caption": cap}
            params.update({"media_type": "REELS", "video_url": url} if c["kind"] == "reel" else {"image_url": url})
            container = _graph_post(f"{ig}/media", params)["id"]
            for _ in range(18 if c["kind"] == "reel" else 1):
                if c["kind"] != "reel" or _graph_get(container, {"fields": "status_code"}).get("status_code") == "FINISHED":
                    break
                time.sleep(5)
            done["instagram"] = _graph_post(f"{ig}/media_publish", {"creation_id": container}).get("id")
    except Exception as e:  # noqa: BLE001 - report the platform's error to the owner
        db.update("creatives", cid, {"publish_result": json.dumps({"error": str(e), **done})})
        return {"ok": False, "error": str(e), **done}
    db.update("creatives", cid, {"status": "published", "published_at": db.now_iso(),
                                 "publish_result": json.dumps(done)})
    db.audit(None, "system", "studio_published", str(cid))
    return {"ok": True, **done}


def post_due() -> int:
    """Called by the scheduler: approved creatives whose time has come are posted or handed to people to post."""
    s = get_settings()
    now = s.now().isoformat()
    n = 0
    for c in db.q("SELECT * FROM creatives WHERE status = 'approved' AND post_at IS NOT NULL AND post_at <= ?", (now,)):
        proj = inventory.get_project(c["project_id"])
        name = proj["name"] if proj else "project"
        if c["format"] != "story" and cfg()["auto_publish"] and publishing_ready():
            r = publish(c["id"])
            msg = (f"✅ Posted today's {name} {c['kind']} to Facebook/Instagram." if r["ok"]
                   else f"⚠️ Couldn't auto-post the {name} {c['kind']}: {r['error']}. Post it by hand: {creative_url(c)}")
            channels.notify_staff(s.owner["phone"], msg)
        else:
            where = "your WhatsApp status and Instagram story" if c["format"] == "story" else "Instagram and Facebook"
            text = (f"📣 Time to post today's {name} {c['kind']} on {where}.\nImage/video: {creative_url(c)}\n\n"
                    f"Caption (copy & paste):\n{c['caption']}")
            channels.notify_staff(s.owner["phone"], text)
            if c["format"] == "story":
                for rm in s.sales_team:
                    if rm.get("phone"):
                        channels.notify_staff(rm["phone"], f"📣 {rm['name']}, please put this on your WhatsApp status "
                                                           f"today (buyers see it): {creative_url(c)}")
            db.update("creatives", c["id"], {"status": "reminded", "published_at": db.now_iso()})
        n += 1
    return n


def mark_posted(cid: int) -> None:
    db.update("creatives", cid, {"status": "published", "published_at": db.now_iso()})


# ------------------------------------------------------------------ weekly pack

def candidates() -> list[dict]:
    out = []
    for p in inventory.list_projects():
        full = inventory.get_project(p["id"])
        if full and not blockers(full) and any(t["available"] for t in inventory.type_summary(full["id"])):
            out.append(full)
    last = {r["project_id"]: r["at"] for r in db.q("SELECT project_id, MAX(created_at) at FROM creatives "
                                                    "GROUP BY project_id")}
    out.sort(key=lambda p: last.get(p["id"]) or "")
    return out


def weekly_pack(max_projects: int = 3) -> dict:
    from .team import base_url
    s = get_settings()
    picks = candidates()[:max_projects]
    if not picks:
        return {"ok": False, "projects": 0}
    week = s.now().strftime("%G-W%V")
    angles = list(ANGLES)
    start = s.now().isocalendar()[1]
    made, names = 0, []
    for k, p in enumerate(picks):
        r = create(p["id"], ("feed", "story"), angles[(start + k) % len(angles)], reel=(k == 0), pack=week)
        if r["ok"]:
            made += len(r["ids"])
            names.append(p["name"])
    channels.notify_staff(s.owner["phone"], f"🎨 This week's content pack is ready: {made} creatives for "
                                            f"{', '.join(names)}. Pick your favourites (about 10 minutes): "
                                            f"{base_url()}/studio")
    return {"ok": True, "projects": len(picks), "creatives": made, "week": week}


