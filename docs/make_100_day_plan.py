"""Generates docs/100-day-plan.html (run: python docs/make_100_day_plan.py .) (Skyline Realty: overall plan, builder CP playbook, 100-day plan)."""
import datetime as dt
import sys

ROOT = sys.argv[1]
css = open(f"{ROOT}/docs/workflow.html").read().split("<style>")[1].split("</style>")[0]
css += """
h2 { break-after: avoid; } body { font-size: 8.7pt; } th, td { padding: 0.8mm 1.6mm; }
table.days { break-inside: auto; } table.days tr { break-inside: avoid; } table.days thead { display: table-header-group; } .keep { break-inside: avoid; } .cover h1 { color: #fff; }
.warn { background:#fff8e6; border:1px solid #f0d48a; border-radius:2mm; padding:2mm 3mm; margin:2mm 0; break-inside: avoid; }
.ok { background:#eef8f1; border:1px solid #a9d8b8; border-radius:2mm; padding:2mm 3mm; margin:2mm 0; break-inside: avoid; }
ol, ul { margin: 1mm 0; padding-left: 5mm; } li { margin: 0.5mm 0; }
.days td { font-size: 8.3pt; padding: 0.9mm 1.5mm; } .days td:first-child { width: 8mm; text-align:center; font-weight:700; }
.days td:nth-child(2) { width: 16mm; white-space: nowrap; } .days td:nth-child(3) { width: 9mm; text-align:center; } .days td:nth-child(4) { width: 26mm; font-weight:600; }
.days td:nth-child(6) { width: 13mm; } .days td:nth-child(7) { width: 27mm; color:#145c33; }
.loc { display:inline-block; border-radius:2mm; padding:0 1.2mm; font-size:7.4pt; font-weight:700; }
.lB { background:#e8f0ff; color:#1d4aa8; } .lC { background:#fff0e0; color:#8a4b00; }
.tK { background:#ffe6cc; color:#8a4b00; }
.days tr.we td { background: #f6f8fb; } .days tr.rev td { background: #fff7d6; } .days tr.hol td { background: #f3f0ff; }
.wk { background:#1d2330 !important; color:#fff; font-weight:700; } .wk td { background:#1d2330 !important; color:#fff !important; }
.script { border-left: 3px solid #2b62e3; background:#f5f8ff; padding: 1.5mm 3mm; margin: 1mm 0 2mm; font-size: 8.8pt; break-inside: avoid; }
.tag { display:inline-block; border-radius:2mm; padding:0 1.5mm; font-size:7.6pt; font-weight:700; margin-right:0.6mm; }
.tY { background:#e1ecff; color:#1d4aa8; } .tW { background:#ffe1dc; color:#9b2215; } .tS { background:#fff0d6; color:#8a5300; }
.tA { background:#dcf3e4; color:#145c33; } .tC { background:#eceff4; color:#3b4252; } .tO { background:#f1e6ff; color:#5b2a8c; }
"""

TAGS = {"Y": "You", "S": "Sales", "K": "Site CHN", "A": "AI", "C": "Claude", "O": "Outsourced"}


def tags(s):
    return "".join(f'<span class="tag t{c}">{TAGS[c]}</span>' for c in s)


# You live and work in Bangalore and are in Chennai 2 days a week. Recommended: Thu–Fri in Chennai (weekday
# business: landowner, bank, architect, contractor, builders), weekends in Bangalore hosting visits.
# Exceptions (you stay in Chennai): the Thai booking weekend 16–17 Jan.
CHENNAI_OVERRIDES = {54, 55}       # day numbers
OFF_DAYS = {32, 39, 64}            # Christmas, New Year, Republic Day

# (focus, tasks, owners, done-when). Owners: Y = you, S = salesperson (Bangalore, phone for both cities),
# K = Chennai site coordinator, A = AI system, C = Claude, O = outsourced (accountant / CA).
DAYS = [
    # ---- week 1
    ("Foundation", "Settings: brand, firm name, RERA lines for Chennai and Bangalore, bank details, your number. Remove "
     "sample inventory and 'Sunrise Meadows'. ▸ PROJECT: list cash, FDs, receivables and loans; enter them as sources in "
     "Admin ▾ → Cash plan (the 3 payments are already there).", "Y", "Settings green · cash sources in"),
    ("Focus + Karnataka RERA", "Pick 2 micro-markets per city (Chennai: e.g. OMR, Pallikaranai–Medavakkam, GST Road, "
     "Porur; Bangalore: e.g. Sarjapur Road, Whitefield–Varthur, Hennur–Thanisandra, Electronic City). Call the CA and a "
     "RERA consultant: can the firm work in Karnataka under your wife's K-RERA registration while she's a sleeping "
     "partner, or is a fresh registration needed? ▸ PROJECT: read the landowner agreement (dates, penalties, cure "
     "period).", "Y", "Markets chosen · K-RERA question asked"),
    ("Chennai day", "Architect: planning-permission status, RERA documents, realistic dates. Set up your outskirts "
     "office: desk, Wi-Fi, a small signboard, a place to meet buyers. Visit 3 sales offices in your Chennai focus "
     "market.", "Y", "Office usable · 3 CP policies"),
    ("Chennai: money + paperwork", "CA: partners' authority letter (your wife signs once), accountant appointed "
     "(₹5–10k/month), funding structure. Enquire for loan against property at 2 banks (timelines in writing). "
     "Empanelment kit (PAN, GST, both RERA certificates, deed, cheque).", "YO", "Authority letter · LAP enquiries"),
    ("Field day — Bangalore", "Visit 5 Bangalore sales offices as a CP and collect CP policies, price sheets and floor "
     "plans. Note slow projects (pilot candidates).", "Y", "5 CP policies"),
    ("Builder longlist", "List 20 projects per city in builder-scorecard.csv (TN RERA / K-RERA search, portals, "
     "hoardings). Mark ready-to-move and near-possession projects.", "Y", "40-row longlist"),
    ("REVIEW #1", "Score the projects and pick the top 6 per city. WhatsApp Business SIM; start Meta verification. "
     "Post job ads: (1) Bangalore salesperson, phone-first, Tamil + English (Kannada/Hindi a plus), work from home or "
     "co-working; (2) Chennai site coordinator, local, two-wheeler, weekends. ▸ CASH: is the ₹2.5 Cr covered? If not, "
     "meet the landowner on Thursday.", "Y", "Shortlists · 2 job ads live"),
    # ---- week 2
    ("Builder calls", "Call 6 Bangalore + 6 Chennai CP managers (phone script, section 9). Book Bangalore meetings "
     "Tue/Wed and Chennai meetings Thu/Fri. Evening: screen CVs.", "Y", "8 meetings booked"),
    ("Bangalore meetings 1–3", "30-minute agenda (section 9); max 3 a day. K-RERA answer due: if a fresh registration "
     "is needed, apply now; Bangalore empanelments wait for it.", "Y", "3 meetings · K-RERA path known"),
    ("Chennai meetings + landowner", "Chennai meetings 1–2. ▸ PROJECT: meet the landowner and propose options before any "
     "delay (section 7).", "Y", "2 meetings · landowner met"),
    ("Chennai meetings + interviews", "Chennai meetings 3–4. Walk-in interviews for the site coordinator at your "
     "office: punctual, polite, knows the area, can fill a form on a phone. In every agreement email, ask for written "
     "permission to advertise plus photos.", "Y", "4 meetings · coordinator finalist"),
    ("Salesperson interviews", "Role play in Tamil and English: enquiry → visit booking; price objection; a "
     "follow-up call to a buyer who went silent.", "Y", "2 finalists"),
    ("Project learning + photos", "Walk 2 Bangalore projects end to end: 10 photos each (daylight, landscape), 5 "
     "highlights and 5 FAQs into Inventory.", "Y", "2 projects with photos"),
    ("REVIEW #2 — DECISION DAY", "Offer letters: salesperson and site coordinator, both joining 15 Dec. Sign the clean "
     "agreements and send price lists to Claude. ▸ CASH: ₹2.5 Cr confirmed? If not, start the backup (written revised "
     "schedule, documented loan, project-level partner) and pause builder wave 2.", "YC", "2 offers accepted"),
    # ---- week 3
    ("Portals + workspace", "Portal quotes for both cities' localities; 3-month trial. Salesperson's workspace: home "
     "(laptop, headset, quiet room) or a co-working seat (₹6–10k/month) near their home.", "Y", "Packages · seat decided"),
    ("Meta set-up", "Facebook Page + Instagram Business (linked), ad account, lead form with consent. Connect Meta lead "
     "ads (Claude guides).", "YC", "Test lead in dashboard"),
    ("Chennai: projects + photos", "Walk 2 Chennai projects: photos, highlights, FAQs. Chennai meetings 5–6. ▸ PROJECT: "
     "architect / bank follow-up.", "Y", "4 projects with photos"),
    ("Chennai: agreements + inventory", "Sign the next agreements; every signed project goes into Inventory with its "
     "landing page checked; mark builder permission in the Studio. ▸ CASH: loan sanction status.", "YC",
     "6+ projects live"),
    ("Warm network", "Personal WhatsApp to about 200 contacts in both cities + LinkedIn post + referral reward. From "
     "today: a Studio story on your WhatsApp status daily.", "Y", "200 messages"),
    ("FIRST STUDIO PACK", "Marketing Studio: top 2 projects per city, feed + story + 1 reel; pick the best designs, check "
     "claims, approve. Daily posting starts.", "YAC", "9+ creatives approved"),
    ("REVIEW #3", "Approve ad copy and creatives per city (3 designs = A/B/C test). Bangalore ads only once the K-RERA "
     "position is clear; otherwise Chennai only for now. ▸ CASH: sanction letters / transfers for 30 Dec in hand?", "Y",
     "Ads ready"),
    # ---- week 4
    ("Both hires join", "Salesperson with you in Bangalore: Workflow PDF, portal, call within 15 minutes, scripts for "
     "both cities. Settings: salesperson covers both cities; site team = Chennai coordinator (Chennai projects) + you "
     "(Bangalore projects). Coordinator gets their portal link. If Meta has verified you: WhatsApp live + "
     "Facebook/Instagram auto-posting.", "YSKC", "Both portals opened"),
    ("ADS LAUNCH", "Meta lead ads + Click-to-WhatsApp, ₹1,500–2,000/day in total, split by city; portals live. "
     "Salesperson: first calls while you listen.", "YS", "First 15 leads"),
    ("Coordinator training (Chennai)", "Routes to each site, introductions to builder site staff, register-before-visit, "
     "the visit report form, cab pickups. On days you're away, they also send you construction-site photos.", "YK",
     "Coordinator certified"),
    ("Chennai bank tie-ups", "Meet 2 home-loan branch managers in your Chennai focus market for a referral "
     "arrangement. ▸ PROJECT: site, architect, landowner touch-points.", "Y", "2 tie-ups"),
    ("First visit weekend", "Bangalore visits hosted by you; Chennai visits by the coordinator (you on the phone for "
     "questions and price talk). Salesperson confirms every visit the day before.", "YSK", "3–5 visits"),
    ("Visits", "Visits; reports filed the same day by you and the coordinator.", "YK", "Reports in"),
    ("REVIEW #4", "Approve this week's Studio pack (10 min). Cost per lead, % called within 15 minutes, lead → visit "
     "per city. ▸ CASH: 9 days to the land payment: money in the account; lawyer drafts the receipt.", "Y",
     "KPIs logged"),
    # ---- week 5
    ("Builder offers", "Year-end offers in writing from every builder; Studio 'Value' posters.", "YA", "Offers logged"),
    ("First builder reports", "Sales ▾ → Builder weekly reports: preview and send. Every Wednesday from now (15 min).",
     "YA", "Reports sent"),
    ("Chennai: pipeline + Google", "Pipeline review with the coordinator. Free Google Business Profile at your Chennai "
     "office address. ▸ PROJECT check.", "YK", "Profile live"),
    ("Christmas", "The AI handles replies; on call for hot leads only.", "A", "—"),
    ("Visits", "Holiday-week visits run high in both cities.", "YK", "—"),
    ("Visits", "Same as yesterday.", "YK", "—"),
    ("REVIEW #5", "Cash plan check. Approve the Studio pack. December spend into Reports; the accountant sets up the "
     "invoice template.", "YO", "December entered"),
    # ---- week 6
    ("Second builder wave", "Call 4 more CP managers per city (target 5 empanelled per city by day 50).", "Y",
     "Meetings booked"),
    ("PAY ₹2.5 Cr + targets", "▸ PAY THE LANDOWNER ₹2.5 Cr by bank transfer today (a day early: many banks work a half "
     "day on 31 Dec). Builder reports. 2027 targets and incentive slabs.", "YA", "Transfer done"),
    ("Chennai: receipt + Thai list", "Collect the landowner's signed receipt; mark Paid in Cash plan. Thai list with the "
     "coordinator: every warm Chennai buyer gets a mid-January booking follow-up.", "YK", "Receipt signed"),
    ("New Year", "Day off.", "", "—"),
    ("Visits", "Visits.", "YK", "—"),
    ("Visits", "Same as yesterday.", "YK", "—"),
    ("REVIEW #6", "Approve the Studio pack. ▸ PROJECT: construction ₹50 L: contractor schedule, stage payments, "
     "source confirmed?", "Y", "Logged"),
    # ---- week 7
    ("Bangalore wave 2", "Bangalore builder meetings (2).", "Y", "2 meetings"),
    ("Reports + meetings", "Builder reports; 1–2 more meetings.", "YA", "Sent"),
    ("Chennai: wave 2 + referrals", "Chennai meetings (2). Referral programme: ₹10–25k voucher per referred booking; "
     "ask visited buyers for Google reviews. ▸ PROJECT: RERA application filed if approvals are ready.", "YK",
     "Referral card live"),
    ("Chennai: corporate + banks", "Email or LinkedIn 10 HR heads at OMR IT companies offering a February home-buying "
     "session; follow up with the bank managers.", "Y", "2 replies"),
    ("Family second visits", "Bring warm Bangalore buyers back with the decision maker; coordinator does the same in "
     "Chennai.", "YK", "—"),
    ("Visits + phone reels", "Film a 30-second walk-through on a visit (you in Bangalore, the coordinator in Chennai) and "
     "post it as a reel with a Studio caption.", "YK", "2 reels"),
    ("REVIEW #7", "Cash plan check. Ad rule: increase only campaigns with cost per visit under ₹5,000. Studio: "
     "Pongal / Sankranti pack (builder-approved offers) for 13–17 Jan.", "Y", "Thai pack approved"),
    # ---- week 8
    ("Booking logistics", "Both cities: booking slots at builder offices, builders' payment details, cost sheets for "
     "hot buyers. Chennai bookings → the Thai weekend; Bangalore bookings → the following Tue/Wed.", "S", "Ready"),
    ("Reports", "Builder reports. Evening: travel to Chennai for the booking weekend.", "YA", "Sent"),
    ("Pongal / Sankranti", "Greeting + Thai offer message to warm Chennai leads; Sankranti message in Bangalore.", "A",
     "—"),
    ("Thai begins", "Call every hot Chennai buyer with the salesperson and fix booking appointments.", "YSK",
     "5+ appointments"),
    ("BOOKING WEEKEND (Chennai)", "You stay in Chennai: booking meetings at builder offices; approvals within 1 hour.",
     "YK", "1–3 bookings"),
    ("BOOKING WEEKEND (Chennai)", "Same as yesterday.", "YK", "—"),
    ("REVIEW #8", "Approve the Studio pack. Verify each booking: registration ACK and invoice date (accountant). "
     "▸ CASH: January construction ₹50 L confirmed?", "YO", "Verified"),
    # ---- week 9
    ("Negotiation + content review", "Which concessions closed? Approve the AI's lessons. Which ads and Studio angles "
     "brought visits, per city?", "Y", "Lessons approved"),
    ("Reports + collections", "Builder reports; collections calendar from the builders' CRM teams.", "YAO",
     "Calendar set"),
    ("Chennai: hire #2 decision", "If leads exceed 120/month, post the job ad for salesperson #2 (or a Bangalore site "
     "coordinator if your weekends are full). Chennai pipeline review with the coordinator.", "YK", "Decision"),
    ("Chennai: inventory refresh", "Update prices and availability in both cities; add projects matching the demand "
     "gaps (15-yr plan page).", "YC", "Inventory current"),
    ("Visits", "Visits.", "YK", "—"),
    ("Visits", "Same as yesterday.", "YK", "—"),
    ("REVIEW #9 — DAY-60 CHECK", "Approve the Studio pack. Check: 4+ builders per city? 500 leads? 3+ bookings? Fix the "
     "biggest miss first. ▸ CASH: February land ₹50 L source confirmed?", "Y", "Day-60 scorecard"),
    # ---- week 10
    ("Republic Day", "Day off.", "", "—"),
    ("Reports + pilot proposal", "Builder reports. Pick the builder with the most visits and slow stock (either city); "
     "Claude drafts the 60-day pilot from your data.", "YAC", "Proposal ready"),
    ("Chennai: pilot pitch", "Pitch the pilot to a Chennai builder's sales head.", "Y", "Agreed or next date"),
    ("Chennai: pay construction", "▸ PAY the January construction ₹50 L against the engineer's measurement, on site; "
     "mark Paid. Ad scale decision: if cost per booking ≤ 30% of earnings, raise to ₹2,500–3,000/day; swap in fresh "
     "Studio designs.", "Y", "Paid · budget set"),
    ("Visits", "Visits.", "YK", "—"),
    ("Visits", "Same as yesterday.", "YK", "—"),
    ("REVIEW #10 + January close", "Approve the Studio pack. January bookings vs target (4). Union Budget: if housing "
     "rules change, send a buyer message. ▸ PROJECT: RERA registered? Then start the pre-launch with Studio posters "
     "to demand-book buyers.", "Y", "January closed"),
    # ---- week 11
    ("Bangalore pilot pitch", "Pitch the pilot to the best Bangalore builder.", "Y", "Agreed or next date"),
    ("Reports + interviews", "Builder reports; interviews for hire #2 if triggered.", "YA", "Sent"),
    ("Chennai: banks round 2", "Meet 2 more home-loan managers and 1 DSA.", "Y", "3 more tie-ups"),
    ("Chennai: corporate prep", "Confirm the OMR session; ask a builder to co-fund the stall; Studio posters for the "
     "company's channels.", "Y", "Date fixed"),
    ("Visits", "Visits.", "YK", "—"),
    ("Visits", "Same as yesterday.", "YK", "—"),
    ("REVIEW #11", "Cash plan check. Approve the Studio pack. Pilot progress.", "Y", "Logged"),
    # ---- week 12
    ("Hire #2 offer", "Send the offer if the threshold is met (joins 16 Feb).", "Y", "Offer accepted"),
    ("Reports + pilot report", "Builder reports with the pilot's weekly numbers.", "YA", "Sent"),
    ("Chennai: corporate session", "Home-buying session at an OMR company with a builder; the coordinator collects "
     "enquiries.", "YK", "20+ leads"),
    ("Chennai: FY-end offers", "Ask Chennai builders for March targets and special offers. Check-in: is the outskirts "
     "office working for buyer meetings?", "Y", "Offers logged"),
    ("Visits", "Visits; ask Bangalore builders for FY-end offers too.", "YK", "—"),
    ("Visits", "Same as yesterday.", "YK", "—"),
    ("REVIEW #12", "Approve the Studio pack. Gate-1 view on the dashboard: the weakest line becomes this fortnight's "
     "focus. ▸ CASH: February land money in the account.", "Y", "Gap list"),
    # ---- week 13
    ("Hire #2 joins", "Onboarding and training.", "YS", "Portal opened"),
    ("Reports", "Builder reports.", "YA", "Sent"),
    ("Chennai: learning + preferred deal", "Read the AI's lessons and refresh scripts. Present results to the pilot "
     "builder and ask for preferred status.", "Y", "Scripts updated"),
    ("Chennai: PAY landowner ₹50 L", "▸ PAY the landowner ₹50 L (due 28 Feb) a week early, in person, with a signed "
     "receipt; mark Paid. March push prep with the coordinator.", "YK", "Paid · hot list"),
    ("BOOKING PUSH", "Visits + booking appointments in both cities.", "YSK", "—"),
    ("BOOKING PUSH", "Same as yesterday.", "YSK", "—"),
    ("REVIEW #13", "Cash plan check. Approve the Studio pack.", "Y", "Logged"),
    # ---- week 14
    ("Company structure", "CA: Pvt Ltd timeline, RERA registrations in the company's name (both states).", "YO",
     "Dates fixed"),
    ("Reports + pilot review", "Builder reports; pilot day-30 review.", "YA", "Reviewed"),
    ("Chennai: office + team decision", "Central Chennai office? Move only if Chennai runs at 4+ bookings a month and "
     "buyers keep asking to meet in the city. Bangalore: keep work-from-home, or move to co-working if call numbers "
     "or focus slip.", "Y", "Decisions written"),
    ("Chennai: AI review", "After 30+ real conversations: keep the Best AI preset or move to Balanced; switch Studio "
     "auto-posting on if Facebook/Instagram is connected.", "YC", "Decisions made"),
    ("BOOKING WEEKEND", "Booking visits in both cities.", "YSK", "—"),
    ("BOOKING WEEKEND", "Same as yesterday.", "YSK", "—"),
    ("REVIEW #14 + February close", "Approve the Studio pack. February bookings vs target (5). ▸ CASH: next 100 days of "
     "construction stage payments in Cash plan.", "Y", "February closed"),
    # ---- week 15
    ("100-day retrospective", "What worked (channels, builders, scripts, the 2-city rhythm) and what to stop.", "Y",
     "Retro notes"),
    ("Next 100 days", "Q2 targets, hiring (Bangalore site coordinator? Chennai office?), builder tiers. Send builder "
     "reports.", "YA", "Plan for days 101–200"),
]

assert len(DAYS) == 100, len(DAYS)

start = dt.date(2026, 11, 24)
rows = ""
week = 0
for i, (focus, tasks, who, done) in enumerate(DAYS):
    d = start + dt.timedelta(days=i)
    if i % 7 == 0:
        week += 1
        end = min(start + dt.timedelta(days=i + 6), start + dt.timedelta(days=99))
        rows += f'<tr class="wk"><td colspan="7">Week {week} · {d:%d %b} – {end:%d %b}</td></tr>'
    cls = "rev" if focus.startswith("REVIEW") else "hol" if focus in ("Christmas", "New Year", "Republic Day",
                                                                       "Pongal / Sankranti") \
        else "we" if d.weekday() >= 5 else ""
    n = i + 1
    where = ("—" if n in OFF_DAYS else '<span class="loc lC">CHN</span>' if (d.weekday() in (3, 4) or
             n in CHENNAI_OVERRIDES) else '<span class="loc lB">BLR</span>')
    rows += (f'<tr class="{cls}"><td>{n}</td><td>{d:%a %d %b}</td><td>{where}</td><td>{focus}</td><td>{tasks}</td>'
             f'<td>{tags(who)}</td><td>{done}</td></tr>')

KPI = [  # week, builders met, empanelled, projects live, leads, visits, bookings (cumulative) — both cities
    (1, 10, 0, 0, 0, 0, 0), (2, 14, 2, 2, 0, 0, 0), (3, 16, 4, 4, 0, 0, 0), (4, 18, 5, 6, 40, 3, 0),
    (5, 18, 6, 7, 100, 9, 0), (6, 20, 6, 8, 170, 15, 0), (7, 22, 7, 9, 250, 22, 0), (8, 24, 8, 10, 340, 30, 1),
    (9, 25, 8, 11, 430, 38, 2), (10, 26, 9, 12, 520, 46, 3), (11, 27, 9, 13, 610, 54, 4),
    (12, 28, 10, 14, 700, 62, 6), (13, 29, 10, 15, 790, 70, 7), (14, 30, 10, 16, 880, 78, 9),
    (15, 30, 10, 16, 950, 84, 10)]
kpi = "".join(f"<tr><td>W{w}</td><td>{a}</td><td>{b}</td><td>{c}</td><td>{d:,}</td><td>{e}</td><td><b>{f}</b></td></tr>"
              for w, a, b, c, d, e, f in KPI)

MONTHS = [("Jan", 4, "Thai bookings in Chennai from mid-Jan; Sankranti in Bangalore"),
          ("Feb", 5, "Financial-year-end offers in both cities"), ("Mar", 7, "FY-end push; hire #2 productive"),
          ("Apr", 6, "Ugadi (Bangalore) / Tamil New Year"), ("May", 7, "Summer; NRI visits"),
          ("Jun", 8, "Appraisal and bonus season"), ("Jul", 6, "Aadi: slower in Chennai; push Bangalore"),
          ("Aug", 8, "Aadi ends"), ("Sep", 9, "Pre-festive"), ("Oct", 11, "Navratri / Dussehra / Diwali"),
          ("Nov", 9, "Post-Diwali"), ("Dec", 10, "Year-end offers")]
mrows = "".join(f"<tr><td>{m}</td><td>{n}</td><td>{note}</td></tr>" for m, n, note in MONTHS)

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Skyline Realty — 100-Day Plan v2 & Builder Playbook</title>
<style>{css}</style></head><body>

<!-- ============ PAGE: REVIEW ============ -->
<div class="sect">
<div class="cover"><h1>Skyline Realty — The Exact Plan (v3)</h1><p>Bangalore base + Chennai 2 days a week · Overall plan · AI marketing · Your construction project (Track B) · CP playbook · Day-by-day 100-day plan (24 Nov 2026 – 3 Mar 2027)</p></div>

<h2>1. How the plan fits the way you work</h2>
<table>
<tr><th style="width:18%"></th><th style="width:41%">Bangalore (you're here 5 days a week)</th><th>Chennai (you're here 2 days a week)</th></tr>
<tr><td><b>Who's on the ground</b></td><td><b>You</b> host the site visits (weekends and evenings). The <b>salesperson</b> works from
home or a co-working seat and makes the follow-up calls for <b>both</b> cities.</td><td>A <b>site coordinator</b> (local,
two-wheeler) hosts the visits, does cab pickups and registrations, files visit reports, and sends you
construction-site photos on days you're away.</td></tr>
<tr><td><b>Your days</b></td><td>Mon–Wed + Sat–Sun: review, Bangalore builders, Bangalore visits</td><td><b>Thu–Fri</b> (recommended): landowner,
bank, architect, contractor and builder offices all work weekdays. Stay over for the Thai booking weekend
(16–17 Jan).</td></tr>
<tr><td><b>Workplace</b></td><td>Salesperson: home (laptop, headset, quiet room) or a co-working seat (₹6–10k/month);
decide on day 94 from the call numbers</td><td>Your outskirts office for now. Move to a central office only when Chennai
runs at 4+ bookings a month and buyers keep asking to meet in the city (decided on day 94).</td></tr>
<tr><td><b>Approach</b></td><td colspan="2">Start lean, watch the numbers, add people and offices only when the data asks for them. The
dashboard shows each city's leads, visits and bookings, so every decision is made on facts.</td></tr>
</table>

<div class="cols">
<div class="keep"><h3>Why this set-up works</h3><ul>
<li><b>Calls don't need a location.</b> One good phone salesperson can follow up both cities, with the AI replying in
minutes and reminding them of every call.</li>
<li><b>Visits do.</b> A Chennai coordinator plus builder site staff cover Chennai. You cover Bangalore, where you live.</li>
<li><b>Your Chennai days line up with Track B.</b> The landowner, bank, architect and contractor all work Thu–Fri.</li>
<li><b>Low fixed cost:</b> no new office and no city lead until bookings justify them.</li></ul></div>
<div class="keep"><h3>Watch-outs</h3><ul>
<li><b>Chennai weekends without you:</b> the coordinator hosts, you take price and negotiation calls by phone, and
the AI routes every discount to you for approval. Big Chennai booking meetings go on your Thu/Fri.</li>
<li><b>A remote salesperson needs a rhythm:</b> a 30-minute 1:1 every Monday, listening to 3 calls a week, and the
portal's overdue-call alerts. If you record calls for coaching, tell buyers calls may be recorded.</li>
<li><b>Your weekends are full.</b> If Bangalore visits go past ~8 a weekend, hire a Bangalore site coordinator
(decided on day 59).</li></ul></div>
</div>

<div class="warn keep"><b>Karnataka RERA, now urgent (day 2):</b> the Karnataka agent registration is in your wife's
name. Ask your CA and a RERA consultant this week whether the firm can work in Karnataka under it while she is a
sleeping partner, or whether a fresh registration (firm or you) is needed. Until it's clear: build Bangalore relationships,
inventory and pipeline, but no Bangalore ads and no builder registrations. Chennai (your TN registration) starts
normally. The authority letter (day 4) covers the documents she would otherwise have to sign.</div>

<h2>2. What makes this plan likely to succeed</h2>
<table>
<tr><td style="width:4%"><b>1</b></td><td><b>Focus:</b> 2 micro-markets per city, ₹60 L–1.5 Cr homes. Builders, bankers and buyers start recognising
Skyline within weeks.</td></tr>
<tr><td><b>2</b></td><td><b>Hire early (both join 15 Dec):</b> the salesperson makes the calls and the coordinator handles Chennai visits.
You keep builders, closing and approvals.</td></tr>
<tr><td><b>3</b></td><td><b>Lead with ready-to-move and near-possession homes:</b> buyers decide faster when they can see the flat.</td></tr>
<tr><td><b>4</b></td><td><b>Warm channels before paid ones:</b> your network in both cities, referrals, home-loan managers, corporate sessions.</td></tr>
<tr><td><b>5</b></td><td><b>Builder trust on autopilot:</b> the weekly builder report goes out every Wednesday from week 5.</td></tr>
<tr><td><b>6</b></td><td><b>Speed and visit rate:</b> call within 15 minutes, free cab pickup, weekend slots.</td></tr>
<tr><td><b>7</b></td><td><b>AI marketing instead of a marketing team:</b> the Studio drafts posters, reels, tips and testimonials weekly.</td></tr>
<tr><td><b>8</b></td><td><b>Spend only behind proof:</b> more ads only below a 30% cost per booking; new hires and offices only on the numbers.</td></tr>
</table>
</div>

<!-- ============ PAGE: OVERALL PLAN ============ -->
<div class="sect">
<h2>3. The overall plan on one page</h2>
<table>
<tr><th style="width:24%">What we are</th><td><b>Skyline Realty, the AI-powered home advisor for Chennai and Bangalore.</b> Buyers get
honest, fast, curated options and are looked after until registration. Builders get qualified buyers, price
discipline and a weekly report.</td></tr>
<tr><th>Who we sell to</th><td>Salaried IT and professional families aged 28–45 buying a first home or upgrading, ₹60 L–₹1.5 Cr.
Second: NRIs from Tamil Nadu and Karnataka.</td></tr>
<tr><th>Where</th><td>2 micro-markets per city (chosen on day 2). Chennai starts now; Bangalore ads and registrations start
once the Karnataka RERA position is clear.</td></tr>
<tr><th>How we earn</th><td>Year 1: builder commission of 2–3% (+18% GST charged to the builder). Year 2: exclusive mandates at
3.5–5% plus fees. Your own construction project (Track B), once RERA-registered, is Skyline's best product: no
commission split.</td></tr>
<tr><th>Team, first 100 days</th><td><b>You</b> (Bangalore visits, builders, closing, approvals, Track B) · <b>salesperson</b>, Bangalore,
work from home / co-working, calls for both cities, from 15 Dec · <b>site coordinator</b>, Chennai, from 15 Dec · hire #2 from
16 Feb if triggered · <b>accountant</b> and <b>CA</b> (outsourced) · <b>Marketing Studio (AI)</b> for content · builders' site staff ·
<b>the AI system</b>, 24×7.</td></tr>
<tr><th>Year-1 target (2027)</th><td><b>90 bookings</b> (about half per city) · ~₹80 Cr sales · <b>~₹2.1 Cr commission</b> · estimated
costs ₹1.2–1.4 Cr · profit ₹0.7–0.9 Cr, reinvested. Plus your own project's sales once registered.</td></tr>
<tr><th>The ladder</th><td>2027 prove the engine in both cities → end-2027 first own-capital project (₹8 Cr capital) → 2029 investor
capital in project companies → 2032 platform licensing → 2041 ~$1B company, 100% owned (see the 15-Year Plan).</td></tr>
</table>

<div class="cols">
<div class="keep"><h3>2027 month-by-month bookings (= 90)</h3>
<table><tr><th>Month</th><th>Bookings</th><th>Why</th></tr>{mrows}</table></div>
<div class="keep"><h3>Funnel maths for 8 bookings a month</h3>
<table>
<tr><td>Leads needed</td><td>~650 (both cities)</td></tr><tr><td>Lead → site visit</td><td>10% → 65 visits</td></tr>
<tr><td>Visit → booking</td><td>12–15% → 8 bookings</td></tr>
<tr><td>Commission earned</td><td>8 × ₹2.25 L ≈ ₹18 L</td></tr>
<tr><td>Marketing cap (30%)</td><td>≤ ₹5.4 L / month</td></tr></table>
<h3>Who does what</h3>
<table><tr><td>{tags('Y')}</td><td>Builders, Bangalore visits, closing, approvals, hiring, Track B, Monday review</td></tr>
<tr><td>{tags('S')}</td><td>Calls within 15 minutes for both cities, visit confirmations, follow-up, booking logistics</td></tr>
<tr><td>{tags('K')}</td><td>Chennai visits, pickups, registrations, visit reports, construction-site photos</td></tr>
<tr><td>{tags('A')}</td><td>Replies, follow-ups, reminders, builder reports, posters, reels, posting</td></tr>
<tr><td>{tags('O')}</td><td>Accountant: invoices, GST/TDS · CA: structure, RERA advice</td></tr>
<tr><td>{tags('C')}</td><td>Inventory uploads, set-up, proposals, system changes</td></tr></table></div>
</div>
</div>

<!-- ============ PAGE: BUDGET + KPI + WEEK ============ -->
<div class="sect">
<h2>4. 100-day budget, two cities, lean (estimates; get real quotes)</h2>
<table>
<tr><th>Item</th><th>100 days</th><th>Notes</th></tr>
<tr><td>Meta ads (lead ads + Click-to-WhatsApp)</td><td>₹2.5–3.5 L</td><td>₹1,500–2,000/day in total from 16 Dec, split by city; more only if the 30% rule holds</td></tr>
<tr><td>Portals (both cities)</td><td>₹1.25–2.5 L</td><td>3-month trials for your localities</td></tr>
<tr><td>Salesperson, Bangalore — fixed</td><td>₹0.65–1.25 L</td><td>₹25–35k/month from 15 Dec (+ hire #2 from 16 Feb if triggered)</td></tr>
<tr><td>Site coordinator, Chennai — fixed + fuel</td><td>₹0.5–0.75 L</td><td>₹18–25k/month + ~₹3k fuel</td></tr>
<tr><td>Incentives</td><td>₹1–1.8 L</td><td>Salesperson ₹8–12k per booking; coordinator ₹3–5k per booking from their visits</td></tr>
<tr><td>Co-working seat (optional)</td><td>₹0.15–0.25 L</td><td>Or work from home: ₹0</td></tr>
<tr><td>Chennai outskirts office</td><td>₹0.1 L</td><td>Yours: Wi-Fi, signboard</td></tr>
<tr><td>Extra Bangalore–Chennai travel</td><td>₹0.3–0.6 L</td><td>Mostly shared with Track B trips</td></tr>
<tr><td>Free cab pickup for visits</td><td>₹0.4–0.6 L</td><td>~₹1,000 per visit, about half the visits</td></tr>
<tr><td>Accountant · CA, legal, K-RERA advice</td><td>₹0.8–1.5 L</td><td></td></tr>
<tr><td>Cards, one-pager, standee · AI + hosting + WhatsApp</td><td>₹0.5–0.85 L</td><td>Content from the Marketing Studio, no freelancer</td></tr>
<tr><td>Contingency</td><td>₹0.75 L</td><td></td></tr>
<tr><th>Total</th><th>₹8.9–14.5 L</th><th>Plus keep an <b>₹8 L buffer</b>: commission arrives 30–90 days after booking. Track B money is separate (section 7).</th></tr>
</table>

<h2>5. Weekly scorecard — cumulative targets (both cities)</h2>
<table><tr><th>Week</th><th>Builders met</th><th>Empanelled</th><th>Projects live</th><th>Leads</th><th>Site visits</th><th>Bookings</th></tr>{kpi}</table>
<div class="ok"><b>Day-100 targets:</b> 10 builders empanelled (about 5 per city) · 16 projects live · ~950 leads · ~85 site visits ·
<b>8–12 bookings</b> (≈ ₹18–27 L commission earned) · 1 pilot running · WhatsApp live · salesperson + Chennai coordinator
working · Karnataka RERA settled · office decisions made · <b>all three project payments made on time</b>.</div>

<div class="keep"><h3>Your week: 5 days Bangalore, 2 days Chennai</h3>
<table>
<tr><td style="width:15%"><b>Mon</b> · BLR</td><td>9:00 digest · <b>review</b> (15-yr plan, Reports, Cash plan) + approve the Studio pack · 30-min 1:1 with the salesperson (listen to 3 calls) · afternoon: builder meeting</td></tr>
<tr><td><b>Tue</b> · BLR</td><td>Bangalore builder meetings (max 3) · accountant by phone when needed</td></tr>
<tr><td><b>Wed</b> · BLR</td><td>10:00 <b>send builder reports</b> (15 min) · meetings · marketing · evening: travel to Chennai</td></tr>
<tr><td><b>Thu</b> · CHN</td><td>Morning: construction site, landowner, bank, architect (Track B) · afternoon: Chennai builders · coordinator 1:1</td></tr>
<tr><td><b>Fri</b> · CHN</td><td>Chennai builder / booking meetings at builder offices · coordinator pipeline review · evening: back to Bangalore</td></tr>
<tr><td><b>Sat–Sun</b> · BLR</td><td>You host Bangalore visits and closings · the coordinator hosts Chennai visits; you take price calls by phone</td></tr>
<tr><td><b>Daily</b></td><td>Approvals within 1 hour · 7 PM pipeline check (10 min) · 7:30 PM post today's creative + WhatsApp status · protect one half-day a week for yourself</td></tr>
</table></div>

<div class="warn"><b>Local calendar (verify the dates each year):</b>
<ul><li><b>Margazhi (mid-Dec → mid-Jan):</b> Chennai buyers visit, then book from Thai (mid-Jan).</li>
<li><b>Sankranti and Ugadi</b> are good moments in Bangalore.</li>
<li><b>Feb–Mar:</b> builders' financial-year-end push in both cities.</li>
<li><b>Aadi (mid-Jul → mid-Aug):</b> slow in Chennai.</li>
<li><b>Navratri → Diwali:</b> peak.</li></ul></div>
</div>

<!-- ============ PAGE: AI MARKETING ============ -->
<div class="sect">
<h2>6. Marketing with AI — no marketing hire</h2>
<p>All marketing content comes from the <b>Marketing Studio</b> in your dashboard (Marketing ▾ → Marketing Studio).
Claude writes the words, the studio lays them over the builders' <b>real</b> photos, and it tracks which angles bring
leads. You spend about <b>1.5 hours a week</b> on marketing in total.</p>

<div class="cols">
<div class="keep"><h3>The weekly loop</h3><table>
<tr><td style="width:24%"><b>Mon 08:00</b></td><td>{tags('A')} The weekly pack is drafted: 3 projects × (3 feed designs + 3 story designs) + 1 reel. You get a WhatsApp.</td></tr>
<tr><td><b>Mon review</b></td><td>{tags('Y')} 10 min: pick the best design per project, read every claim, approve. Rejected designs teach it your taste.</td></tr>
<tr><td><b>Daily 19:30</b></td><td>{tags('A')} One feed post + one story go out. Before auto-posting is connected, you get the image + caption on WhatsApp (2 min to post).</td></tr>
<tr><td><b>Daily</b></td><td>{tags('S')} The story goes to the salespeople for their WhatsApp status; you post it too.</td></tr>
<tr><td><b>Every 2 weeks</b></td><td>{tags('Y')} 20 min: swap fresh Studio designs into Meta ads (ads tire after ~2 weeks).</td></tr>
<tr><td><b>Monthly</b></td><td>{tags('Y')} 30 min: Reports + 15-yr plan page: which angles and ads brought <i>visits</i>, not just leads? Keep those.</td></tr>
</table></div>
<div class="keep"><h3>What the studio guarantees</h3><ul>
<li><b>Real pictures only:</b> no AI-invented buildings (that would be misleading under RERA)</li>
<li><b>Prices from Inventory</b>, never written by the AI; "starting price" footnote on every creative</li>
<li><b>Project RERA + your agent RERA</b> + "marketed by Skyline Realty for [builder]" on every creative and caption</li>
<li><b>Risky claims flagged:</b> "guaranteed", "best", "lowest", returns, AI-written prices</li>
<li><b>Builder permission required</b> before a partner project can be approved</li>
<li><b>Nothing goes out without your approval</b></li>
<li><b>Tracking:</b> every caption links to the project's landing page, so leads are traced to the content</li></ul></div>
</div>

<div class="keep"><h3>Channels — who does what</h3>
<table>
<tr><th style="width:20%">Channel</th><th>AI does</th><th>You do</th><th style="width:12%">Cost</th><th style="width:17%">Day-100 goal</th></tr>
<tr><td><b>Meta lead ads + Click-to-WhatsApp</b></td><td>Ad copy (Campaigns), poster and reel creatives (Studio), replies to every lead in 5 min</td><td>Set budget, swap creatives fortnightly, apply the 30% rule</td><td>₹1.5–3k/day</td><td>~55% of leads</td></tr>
<tr><td><b>Instagram + Facebook page</b></td><td>1 post + 1 story a day, captions, hashtags; auto-posting once connected</td><td>Approve Monday; reply to comments with "WhatsApp us"</td><td>Free</td><td>60+ posts, 14+ reels</td></tr>
<tr><td><b>WhatsApp status</b> (you + salespeople)</td><td>Sends the day's story to every phone</td><td>Post it (10 seconds)</td><td>Free</td><td>Daily, from day 19</td></tr>
<tr><td><b>Portals</b> (99acres, MagicBricks, Housing)</td><td>Reads portal lead emails into the system (built); listing text from Campaigns</td><td>List projects; keep prices current</td><td>₹0.75–1.5 L</td><td>~20% of leads</td></tr>
<tr><td><b>Landing pages</b> /p/project</td><td>Built automatically with consent + tracking</td><td>Share links</td><td>Free</td><td>Every ad and post links here</td></tr>
<tr><td><b>Google Business Profile</b></td><td>Weekly poster to post there</td><td>Create the profile (day 31); ask visited buyers for reviews</td><td>Free</td><td>15+ reviews</td></tr>
<tr><td><b>Referrals, bankers, corporate sessions</b></td><td>Referral and session posters</td><td>Meetings and relationships</td><td>Low</td><td>~25% of leads</td></tr>
<tr><td><b>YouTube Shorts</b></td><td>Studio reels</td><td>Upload weekly (2 min)</td><td>Free</td><td>12+ shorts</td></tr>
</table></div>

<div class="cols">
<div class="keep"><h3>Content mix each week</h3><ul>
<li><b>7 feed posts:</b> 5 project posters (rotating angles: ready to move, location, lifestyle, value, family) + 2
from your phone (site progress, a happy-buyer photo <i>with their consent</i>)</li>
<li><b>7 stories / WhatsApp status:</b> Studio story designs</li>
<li><b>1–2 reels:</b> one Studio slideshow + one 30-second phone walk-through by the salesperson</li>
<li><b>Seasonal packs:</b> Pongal/Thai (Jan), financial-year-end offers (Feb–Mar), only with builder-approved offers</li></ul></div>
<div class="keep"><h3>What still needs a human (and why)</h3><ul>
<li><b>Approval:</b> RERA rules and the builder's brand are your responsibility, so every creative needs a human yes</li>
<li><b>Real photos and videos:</b> 10 phone photos per project on your first walk-through (day 13), plus builder renders</li>
<li><b>Ad budget:</b> the AI never spends money on its own</li>
<li><b>Builder permission:</b> written OK to advertise each partner project (ask with the CP agreement)</li>
<li><b>Meta setting:</b> check whether property ads must use the "Housing" special ad category (limits age, gender and
postcode targeting); broad targeting with strong creatives works well</li></ul></div>
</div>
<div class="ok"><b>Marketing time budget:</b> Monday approval 10 min · daily posting 2 min (until auto-posting) · ad swap
20 min a fortnight · monthly review 30 min ≈ <b>1.5 hours a week</b>. No marketing salary, no freelancer.</div>
</div>

<!-- ============ PAGE: TRACK B ============ -->
<div class="sect" style="page-break-before:always">
<h2>7. Track B — your Chennai construction project and its payments</h2>
<p><b>Should it be part of this plan or separate?</b> Both. You are one person with one calendar, so the payment
dates, the weekly cash check and the project tasks are in the day-by-day plan below (marked <b>▸ PROJECT</b>, <b>▸ CASH</b>
and <b>▸ PAY</b>). A detailed <b>Project & Cash Plan</b> (sales, approvals, construction schedule, funding) should be its own
document, built once the facts below are in. Until these three payments are secured, <b>Track B comes first</b>:
losing the land would hurt far more than a slower channel-partner launch.</p>

<table>
<tr><th>Payment</th><th style="width:16%">Amount</th><th style="width:20%">Due</th><th style="width:26%">Pay on (plan)</th></tr>
<tr><td>Landowner, instalment 1</td><td><b>₹2.50 Cr</b></td><td>31 Dec 2026</td><td>Wed 30 Dec (day 37)</td></tr>
<tr><td>Construction start</td><td><b>₹0.50 Cr</b></td><td>January 2027</td><td>Fri 29 Jan (day 67)</td></tr>
<tr><td>Landowner, instalment 2</td><td><b>₹0.50 Cr</b></td><td>February 2027</td><td>Fri 19 Feb (day 88)</td></tr>
<tr><th>Total in 97 days</th><th>₹3.50 Cr</th><th colspan="2">Tracked live in Admin ▾ → Cash plan, with WhatsApp reminders 30/14/7/3/1 days before each</th></tr>
</table>

<div class="warn keep"><b>The honest picture.</b> The channel-partner business can't fund this. By day 100 it should have
earned ₹18–27 L of commission, and most of that is collected in Feb–Apr. The <b>₹2.5 Cr for December must come from
outside the sales business</b>: your own funds, a loan, a renegotiated schedule, or a project-level partner. Start on it
this week, not in December.</div>

<div class="cols">
<div class="keep"><h3>RERA rules that shape the funding (confirm with your CA / lawyer)</h3><ul>
<li><b>No advertising or booking before RERA registration</b> of the new project (for land over 500 m² or more than 8
flats). The Marketing Studio blocks posters for projects without a RERA number.</li>
<li><b>After registration, 70% of buyer payments go to the project's RERA account</b>, usable only for that project's
construction <i>and land cost</i>. So pre-sales can help the <b>February</b> land payment, and only if registration
comes through by about mid-January.</li>
<li><b>Advance capped at 10%</b> of the flat cost before a registered agreement for sale.</li>
<li><b>Money in one project's RERA account can't pay for another project.</b> If you also have an ongoing project with
unsold flats, its collections help this one only from the money you're allowed to withdraw.</li></ul></div>
<div class="keep"><h3>Ways to cover ₹2.5 Cr by December (keeping 100% of the company)</h3><ol>
<li><b>Renegotiate early (week 2):</b> split the instalment (part in Dec, rest when plan approval or RERA comes), or give
the landowner part of the value as built-up area / flats (joint-development style) instead of cash. Get any change
in a written, properly executed supplementary agreement.</li>
<li><b>Loan against property</b> you or the firm own: usually 3–6 weeks, so apply in week 1.</li>
<li><b>Documented private loans</b> (family, friends, business contacts) at a fixed interest rate and term, with no shares
in the company.</li>
<li><b>Project-level partner:</b> an investor funds this project for a share of <i>this project's</i> profit only.</li>
<li><b>NBFC land or project finance</b> (banks rarely fund land purchase by developers): compare the true cost
carefully, as rates are high.</li></ol>
<p><small><b>Avoid:</b> unregulated money-lenders, open-ended personal guarantees, and selling shares in the main company.</small></p></div>
</div>

<div class="cols">
<div class="keep"><h3>Facts I need to build the detailed Project & Cash Plan</h3><ul>
<li>Project: location, land area, number of flats and sizes, expected prices</li>
<li>Deal: outright purchase or joint development; total land cost; schedule; penalty clauses</li>
<li>Approvals: planning-permission status; RERA registration status or expected date</li>
<li>Money: cash available now, other assets that could secure a loan, existing loans</li>
<li>Construction: contractor, total budget, stage-wise schedule</li>
<li>Any other ongoing project with unsold flats (the fastest sales cash, within RERA rules)</li></ul></div>
<div class="keep"><h3>How it changes your 100 days</h3><ul>
<li><b>Your Chennai days (Thu–Fri) carry Track B:</b> landowner, bank, architect and contractor mornings; Chennai builders in the
afternoons. The salesperson and coordinator still join on 15 Dec and ads still launch on 16 Dec.</li>
<li><b>If ₹2.5 Cr isn't confirmed by 7 Dec (day 14):</b> pause builder wave 2 (day 36) and the corporate outreach (day 46);
use that time on financing.</li>
<li><b>Every Monday review:</b> a 5-minute check on the Cash plan page.</li>
<li><b>Once RERA-registered:</b> your own project becomes Skyline's best product, with no commission split and no builder
permission needed. The AI sales engine and the Studio can sell it from day one of registration.</li></ul></div>
</div>
</div>

<!-- ============ PAGE: CP PLAN — STRATEGY ============ -->
<div class="page" style="page-break-before:always">
<h2>8. CP plan with builders — the strategy</h2>
<p>Most channel partners are one of 100–300 brokers a builder works with, competing on discounts. <b>Skyline's plan is to
become the builder's most reliable sales partner in each focus market, then convert that into preferred and exclusive
deals.</b> We earn that with data, not discounts.</p>

<h3>The four relationship tiers</h3>
<table>
<tr><th style="width:17%">Tier</th><th>What it is</th><th style="width:20%">Typical terms*</th><th style="width:24%">How to reach it</th></tr>
<tr><td><b>1 · Empanelled CP</b></td><td>Standard CP agreement; we can bring buyers to the project.</td><td>2–3% of agreement value</td><td>Empanelment kit + meeting (week 2–4)</td></tr>
<tr><td><b>2 · Pilot</b></td><td>60-day focused push on one slow tower or configuration, with targets both sides.</td><td>+0.5% slab above target, priority holds</td><td>After first bookings with the builder (day 66–71)</td></tr>
<tr><td><b>3 · Preferred partner</b></td><td>Priority inventory, volume slabs, co-funded marketing, early access to launches.</td><td>3–3.5% slabs + co-marketing</td><td>Pilot delivered; ~4+ bookings/month with them</td></tr>
<tr><td><b>4 · Exclusive mandate</b></td><td>Sole sales and marketing for a phase or launch; input on pricing; pre-launch EOIs from our demand book.</td><td>3.5–5% + marketing retainer</td><td>Year 2: ≥25% of the project's monthly sales come from us</td></tr>
</table>
<p><small>*Typical ranges for mid-segment projects; real terms vary by builder and project. Never put your own money into
bulk inventory purchases in years 1–2.</small></p>

<h3>Which builders to approach — scorecard (out of 100; approach only at 65+)</h3>
<table>
<tr><th>Must pass (else skip)</th><td colspan="2">RERA-registered project with approvals · no stalled construction · no serious complaints on the RERA page · will sign a written CP agreement · asks for no deposit or fee for empanelment</td></tr>
<tr><td>Delivery track record (past projects on time)</td><td>20</td><td rowspan="7" style="width:38%"><small><b>How to check:</b> RERA project page (quarterly progress, complaints), visit 1 completed project and talk to residents, ask 2 other CPs about payouts, Google reviews, site visit to see actual progress vs the RERA schedule.<br><br><b>Mix to aim for per city (first 100 days):</b> 1–2 "anchor" builders (strong brand, steady demand) for credibility, plus 2–3 mid-size builders with slow inventory (where pilots and higher slabs come from). About 5 empanelled per city.</small></td></tr>
<tr><td>Pays CPs on time (ask other CPs)</td><td>20</td></tr>
<tr><td>Fits our price band and focus micro-markets</td><td>15</td></tr>
<tr><td>Product value vs neighbouring projects</td><td>15</td></tr>
<tr><td>Inventory depth (enough unsold units to matter)</td><td>10</td></tr>
<tr><td>Commission and terms</td><td>10</td></tr>
<tr><td>Sales-team discipline (doesn't undercut or poach CP buyers)</td><td>10</td></tr>
</table>
<p><small>Use the template <code>docs/builder-scorecard.csv</code> (open in Excel or Google Sheets).</small></p>

<h3>The 12-point CP agreement checklist</h3>
<ol style="columns:2;column-gap:6mm">
<li><b>Commission %</b> and volume slabs in writing (e.g. 2% base → 2.5% after 3 bookings/quarter → 3% after 6)</li>
<li><b>Basis</b>: % of what? Basic price or agreement value; excluding GST, registration, maintenance, car park?</li>
<li><b>Payout trigger and days</b> (often: agreement registered + 10–20% collected; payment within 30–45 days)</li>
<li><b>Client tagging</b>: how (email/portal), ACK within 24 h, validity 60–90 days</li>
<li><b>Disputes</b>: first registered CP wins; a buyer walking in directly within validity is still ours</li>
<li><b>Cancellation / clawback</b>: only if cancelled before payout; no clawback after</li>
<li><b>Spot incentives and offers</b> passed to us in writing</li>
<li><b>Price discipline</b>: the builder's team won't undercut a buyer we registered</li>
<li><b>Site support</b>: site staff for our visits, sample flat, brochures, floor plans, price sheets</li>
<li><b>Invoicing</b>: GST 18% on commission; TDS under Sec. 194H (confirm the current rate with your CA); NEFT</li>
<li><b>Buyer data</b> used only for registration; no poaching of our buyers for other projects</li>
<li><b>Term, termination, jurisdiction</b> (Chennai / Bengaluru courts)</li>
</ol>
<div class="warn"><b>Red flags, walk away:</b> fee or deposit for empanelment · project not RERA-registered · stalled
site · reports of delayed CP payouts · builder wants buyer details before agreeing to protect your registration ·
"commission only after the full payment".</div>
</div>

<!-- ============ PAGE: APPROACH + SCRIPTS ============ -->
<div class="page">
<h2>9. How to approach builders</h2>
<div class="cols">
<div class="keep"><h3>Ways in, best first</h3><ol>
<li><b>Warm introduction</b>: bankers (home-loan managers know every builder), architects, other CPs, friends in the
industry. Best response rate.</li>
<li><b>Walk into the project sales office</b> and ask for the CP manager. Weekday mornings are quiet; weekends are busy.</li>
<li><b>CP meets and launch events</b>: builders invite CPs at launches. Get added to each builder's CP WhatsApp group.</li>
<li><b>CREDAI chapters and property expos</b> in Chennai and Bengaluru: meet many builders in one day.</li>
<li><b>LinkedIn</b> to Sales Heads / VP Sales, short message + one-pager.</li>
<li><b>Cold call</b> the CP desk numbers listed on websites and hoardings.</li></ol></div>
<div class="keep"><h3>Who to meet, for what</h3><table>
<tr><td><b>CP manager</b></td><td>Empanelment, agreement, tagging</td></tr>
<tr><td><b>Sales head / GM sales</b></td><td>Pilots, slabs, slow inventory</td></tr>
<tr><td><b>CRM / accounts head</b></td><td>Payout timing, invoices, agreement dates</td></tr>
<tr><td><b>MD / founder</b></td><td>Preferred and exclusive deals (from month 3)</td></tr></table>
<h3>What builders actually want</h3><ul>
<li>Steady bookings, especially on slow towers and configurations</li><li>Footfall that is qualified, not time-wasters</li>
<li>Price discipline: CPs who don't pass commission as a discount</li><li>No disputes and no extra work for their team</li>
<li>Honest feedback on why buyers don't buy</li></ul></div>
</div>

<h3>Skyline's four promises to a builder (say these in every meeting)</h3>
<table>
<tr><td style="width:4%"><b>1</b></td><td><b>Every enquiry answered in 5 minutes and followed up until a decision.</b> AI + a salesperson, 7 days a week, every follow-up logged.</td></tr>
<tr><td><b>2</b></td><td><b>Only qualified buyers visit.</b> Budget, timeline and loan readiness are checked first, and every buyer is registered with you before the visit.</td></tr>
<tr><td><b>3</b></td><td><b>We never pass our commission as a discount.</b> Every price goes through management approval. Your pricing stays protected.</td></tr>
<tr><td><b>4</b></td><td><b>A weekly report:</b> buyers registered, visits, and what buyers say about your price, product and competitors. Free market intelligence.</td></tr>
</table>

<h3>Phone script — calling a CP manager</h3>
<div class="script">"Good morning, am I speaking with the CP manager for <i>[project]</i>? I'm <i>[name]</i> from <b>Skyline
Realty</b>, a RERA-registered channel partner focused only on <i>[micro-market]</i>. We work with home buyers in the
₹60 L–1.5 Cr range. Every enquiry gets a reply within 5 minutes and is followed up until a decision, and we register
every buyer with you before the visit. We currently have buyers asking for <i>[2BHK under ₹80 L near X]</i>, which fits
your project. Could I meet you for 20 minutes this week to get empanelled? Would Wednesday or Thursday morning
suit you?"</div>

<h3>WhatsApp / email intro (send after the call, with the one-pager)</h3>
<div class="script">Dear <i>[name]</i>, thank you for your time today. As discussed, Skyline Realty is a RERA-registered
channel partner (TN RERA: <i>[no.]</i> · K-RERA: <i>[no.]</i>) focused on <i>[micro-markets]</i>. What we offer partners: replies to
every enquiry within 5 minutes · only qualified, registered buyers at your site · no discount-passing · a weekly
buyer-feedback report. Our empanelment documents are attached. Looking forward to meeting on <i>[date]</i>.
— <i>[name]</i>, Skyline Realty, <i>[phone]</i></div>

<h3>The 30-minute first meeting</h3>
<table>
<tr><td style="width:15%">0–5 min</td><td>Who we are: focus markets, the four promises. Show the dashboard on your phone (a real lead timeline).</td></tr>
<tr><td>5–15 min</td><td><b>Ask, then listen:</b> Which towers or configurations are slow? What % of sales come through CPs? What's your
biggest problem with CPs? How do tagging and payouts work? Any offers running now? Is a launch coming?</td></tr>
<tr><td>15–25 min</td><td>Agreement terms (12-point checklist), sales kit, site-visit process, who to contact for registration.</td></tr>
<tr><td>25–30 min</td><td>Close: "Can we sign the empanelment this week? We'll bring our first buyers for visits next weekend." Fix the next date.</td></tr>
</table>
</div>

<!-- ============ PAGE: OBJECTIONS + PILOT ============ -->
<div class="page">
<h2>10. Objections, pilot and mandate</h2>
<h3>Handling builder objections</h3>
<table>
<tr><th style="width:30%">They say</th><th>You say</th></tr>
<tr><td>"We already have 200 CPs."</td><td>"That's why we focus on qualified buyers and reporting, not volume of brokers. Judge us on bookings in 60 days. There's no cost to you unless we deliver."</td></tr>
<tr><td>"You're a new company."</td><td>"New firm, experienced founder, RERA-registered. Our system answers every buyer in 5 minutes. Let our first 60 days speak; you lose nothing by empanelling us."</td></tr>
<tr><td>"Commission is fixed at 2%."</td><td>"Agreed for now. Can we add a slab if we cross 3 bookings a quarter? It only costs you when we outperform."</td></tr>
<tr><td>"CPs give away commission as discount."</td><td>"Not us. Every price is approved by management, and we can put no-discount-passing in the agreement."</td></tr>
<tr><td>"Payout only after full registration."</td><td>"Can we split it: 50% at agreement registration and 50% at 20% collection? That keeps us both aligned."</td></tr>
<tr><td>"Send the buyer, we'll see."</td><td>"Happy to. We just need the registration ACK before the visit, so there's never a dispute. It protects your team's time too."</td></tr>
<tr><td>"No exclusive deals."</td><td>"Not asking for one now. Let's start with a 60-day pilot on one tower; exclusivity only if the numbers justify it."</td></tr>
<tr><td>"How do I know you won't take our buyers elsewhere?"</td><td>"A registered buyer stays registered with you, and we show you every registered buyer's status in the weekly report."</td></tr>
</table>

<h3>The 60-day pilot proposal (one page to hand over, from day 66)</h3>
<div class="cols">
<div class="card"><h3>Skyline commits</h3><ul>
<li>Focus marketing on <i>[tower / config]</i>: ₹<i>[X]</i> ad spend over 60 days</li>
<li>Target: <i>[N]</i> qualified site visits and <i>[M]</i> bookings</li>
<li>Free cab pickup for every visit</li>
<li>Weekly report every Wednesday: leads, visits, feedback, objections</li>
<li>No discount-passing; management-approved pricing only</li></ul></div>
<div class="card"><h3>Builder commits</h3><ul>
<li>+0.5% slab on every booking above target <i>[M]</i></li>
<li>Priority block: 10 units with a 7-day hold for our buyers</li>
<li>Co-marketing: content access, sample-flat slot on weekends, ₹<i>[Y]</i> co-funding (optional)</li>
<li>Payout within 30 days of agreement registration</li>
<li>Review meeting on day 30 and day 60</li></ul></div>
</div>
<p><b>Graduation:</b> pilot target hit → <b>preferred partner</b> (slabs, priority inventory, early launch access).
Consistently ≥25% of the project's monthly sales → pitch an <b>exclusive mandate</b> for the next phase (Year 2).</p>

<h3>Exclusive mandate — what to ask for (Year 2)</h3>
<table>
<tr><td style="width:28%">Scope</td><td>Sole sales and marketing for one phase or launch, 12–18 months</td></tr>
<tr><td>Fees</td><td>3.5–5% commission + monthly marketing retainer (or builder-funded marketing budget we run)</td></tr>
<tr><td>Pricing</td><td>Joint pricing committee; launch price guided by our demand book</td></tr>
<tr><td>Pre-launch</td><td>Expressions of interest (EOIs) from our demand-book buyers before the public launch</td></tr>
<tr><td>Performance clause</td><td>Minimum bookings per quarter; the builder can exit if missed (shows confidence)</td></tr>
<tr><td>Never</td><td>Pay deposits or buy bulk inventory with our money; take on construction risk</td></tr>
</table>

<h3>Builder relationship rhythm (every empanelled builder)</h3>
<table>
<tr><td style="width:18%">Before each visit</td><td>Register the buyer, get the ACK (built into the system: Builder registrations page)</td></tr>
<tr><td>Weekly (Wed)</td><td>Automatic report from the system (Sales ▾ → Builder weekly reports): registered buyers, visits, feedback, bookings, payments due</td></tr>
<tr><td>Monthly</td><td>15-minute call with the sales head: what's slow, new offers, upcoming launches</td></tr>
<tr><td>Each booking</td><td>Invoice on the trigger date; chase from day 31 (the system reminds you every Monday)</td></tr>
<tr><td>Quarterly</td><td>Slab review: show your numbers, ask for the next slab or tier</td></tr>
</table>
</div>

<!-- ============ PAGES: 100 DAYS ============ -->
<div class="page">
<h2>11. The 100-day plan — day by day</h2>
<p><small>Shading: <span style="background:#fff7d6;padding:0 2mm">weekly review</span>
<span style="background:#f6f8fb;padding:0 2mm">weekend (visit days)</span>
<span style="background:#f3f0ff;padding:0 2mm">holiday</span>. Owners: {tags('YSAOC')}. If you fall behind, keep the
Monday review and the "done when" column honest; push dates, don't skip steps.</small></p>
<table class="days"><thead><tr><th>Day</th><th>Date</th><th>Where</th><th>Focus</th><th>Tasks</th><th>Who</th><th>Done when</th></tr></thead>
{rows}
</table>
</div>

<div class="page">
<h2>12. After day 100 — what success unlocks</h2>
<table>
<tr><th style="width:30%">If by day 100…</th><th>Then in days 101–200…</th></tr>
<tr><td>8+ bookings and cost per booking ≤ 30% of earnings</td><td>Raise ads gradually, hire a Bangalore site coordinator so your weekends free up, add 1 micro-market per city, consider a central Chennai office</td></tr>
<tr><td>A pilot hit its target</td><td>Convert it to preferred partner; start a second pilot</td></tr>
<tr><td>Fewer than 6 bookings</td><td>Don't increase spend. Check the weakest funnel step (contact speed? visit rate? visit → booking?) and fix it first</td></tr>
<tr><td>One builder is more than 40% of commission</td><td>Push the second and third builders in that micro-market</td></tr>
<tr><td>Commission is collected late</td><td>Tighten payout terms in renewals; prefer builders who pay on time</td></tr>
</table>
<div class="cover" style="margin-top:4mm"><h1 style="font-size:13pt">The 100-day promise</h1>
<p>By 3 March 2027: 10 builders signed across both cities, 16 projects live, WhatsApp live, a salesperson and a Chennai
coordinator working, 8–12 bookings, a pilot running, all three land and construction payments made, and builders
receiving your weekly report. That's the proof you need for Year 2's exclusive mandates.</p></div>
</div>
</body></html>"""
open(f"{ROOT}/docs/100-day-plan.html", "w").write(html)
print("ok")
