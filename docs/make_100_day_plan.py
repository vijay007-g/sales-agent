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
.days td:nth-child(2) { width: 17mm; white-space: nowrap; } .days td:nth-child(3) { width: 27mm; font-weight:600; }
.days td:nth-child(5) { width: 13mm; } .days td:nth-child(6) { width: 30mm; color:#145c33; }
.days tr.we td { background: #f6f8fb; } .days tr.rev td { background: #fff7d6; } .days tr.hol td { background: #f3f0ff; }
.wk { background:#1d2330 !important; color:#fff; font-weight:700; } .wk td { background:#1d2330 !important; color:#fff !important; }
.script { border-left: 3px solid #2b62e3; background:#f5f8ff; padding: 1.5mm 3mm; margin: 1mm 0 2mm; font-size: 8.8pt; break-inside: avoid; }
.tag { display:inline-block; border-radius:2mm; padding:0 1.5mm; font-size:7.6pt; font-weight:700; margin-right:0.6mm; }
.tY { background:#e1ecff; color:#1d4aa8; } .tW { background:#ffe1dc; color:#9b2215; } .tS { background:#fff0d6; color:#8a5300; }
.tA { background:#dcf3e4; color:#145c33; } .tC { background:#eceff4; color:#3b4252; } .tO { background:#f1e6ff; color:#5b2a8c; }
"""

TAGS = {"Y": "You", "S": "Sales", "A": "AI", "C": "Claude", "O": "Outsourced"}


def tags(s):
    return "".join(f'<span class="tag t{c}">{TAGS[c]}</span>' for c in s)


# (focus, tasks, owners, done-when). Owners: Y = you, S = salespeople, A = AI system, C = Claude,
# O = outsourced (accountant / CA / freelancer).
DAYS = [
    ("Foundation", "Finish Settings: brand, firm name, TN RERA, bank details, your number. Remove sample inventory and "
     "'Sunrise Meadows'. Bangalore waits: keep its RERA line, but add no Bangalore projects or ads yet.", "Y",
     "Settings items green on Overview"),
    ("Focus markets", "Pick 2–3 Chennai micro-markets from a shortlist such as OMR (Perungudi–Sholinganallur), "
     "Pallikaranai–Medavakkam, GST Road (Guduvanchery–Urapakkam) and Porur. Rank on ₹60 L–1.5 Cr fit, IT jobs nearby, "
     "unsold stock, your network, and travel time from home.", "Y", "2–3 markets chosen"),
    ("Builder longlist", "List 30 projects in those markets from the TN RERA search, portals and hoardings, in "
     "builder-scorecard.csv. Mark which are ready to move or near possession.", "Y", "30-row longlist"),
    ("Paperwork & helpers", "Build the empanelment kit. Have the CA draft a partners' authority letter making you the "
     "sole authorised signatory (your wife signs once). Appoint an accountant (₹5–10k/month) for GST invoices, TDS and "
     "books. No marketing hire: the Marketing Studio (AI) makes the content.", "YO", "Kit + signed authority + accountant"),
    ("Field day 1", "Visit 5 sales offices as a CP. Meet the CP managers and collect their CP policy, price sheet, "
     "brochure and floor plans. Note weekend walk-in traffic.", "Y", "5 CP policies"),
    ("Field day 2", "Visit 5 more, prioritising ready-to-move and near-possession projects (buyers decide faster).",
     "Y", "10 CP policies"),
    ("REVIEW #1", "Score all 30 projects (page 5) and pick the top 10. Buy the WhatsApp Business SIM; start Meta "
     "Business verification. Post salesperson job ads (Naukri, LinkedIn, apna, referrals).", "Y",
     "Shortlist of 10 · job ads live"),
    ("Builder calls", "Call the 10 CP managers using the phone script and book 6 meetings over the next 10 days. "
     "Evening: screen CVs.", "Y", "6 meetings booked"),
    ("Builder meetings 1–2", "Use the 30-minute agenda. Ask for the agreement draft, current offers and the slow towers. "
     "Max 3 meetings a day.", "Y", "Notes in scorecard"),
    ("Builder meetings 3–4", "Meetings 3–4. Phone-screen 10 salesperson candidates.", "Y", "4 meetings done"),
    ("Agreements", "Check each agreement against the 12-point checklist, negotiate, and sign the clean ones. In the same "
     "email ask for: written permission to advertise the project, their photos and renders, and brand rules. Send the "
     "price lists to Claude for the upload file.", "YC", "2 agreements signed"),
    ("Interviews", "Walk-in interviews with role plays (enquiry → visit booking; price objection). Shortlist 2.", "Y",
     "2 finalists"),
    ("Project learning + photos", "Walk 2 signed projects end to end. Enter 5 highlights and 5 FAQs per project. Shoot "
     "10 phone photos each (daylight, landscape: entrance, amenities, sample flat, views) and upload them with the "
     "builder's renders as kind 'photo' in Inventory.", "Y", "2 projects with photos"),
    ("REVIEW #2 + CA", "With the CA: Pvt Ltd timeline, GST invoice format, TDS under 194H. Send the offer letter to "
     "salesperson #1 (joins 15 Dec).", "YO", "Offer accepted"),
    ("Builder meetings 5–6", "Meetings 5–6.", "Y", "6 meetings in total"),
    ("Portals", "Get quotes from 99acres, MagicBricks and Housing for your Chennai localities only and negotiate a "
     "3-month trial. Set lead forwarding to the leads mailbox.", "Y", "Package chosen"),
    ("Meta set-up", "Facebook Page + Instagram Business account (linked), ad account, lead form with consent. "
     "Connect Meta lead ads (Claude guides). Use the same logo and Skyline name everywhere.", "YC", "Test lead in dashboard"),
    ("Agreements + inventory", "Sign the next 2 agreements. Put every signed project in Inventory and check its "
     "landing page. Marketing Studio → mark builder permission for each project that gave it in writing.", "YC",
     "4 projects live + ready for Studio"),
    ("Warm network", "Personal WhatsApp to about 200 contacts, a LinkedIn post, and the referral reward. Ask each "
     "contact for one name. From today put a Studio story on your WhatsApp status every day.", "Y", "200 messages sent"),
    ("FIRST STUDIO PACK", "Marketing ▾ → Marketing Studio: create for the top 3 projects (angle 'Ready to move'), feed "
     "+ story, plus a reel for the best one. Pick the best design of each, check every claim, approve. Daily posting "
     "starts (19:30).", "YAC", "9+ creatives approved"),
    ("REVIEW #3", "Approve ad copy (Marketing ▾ → Campaigns) for the top 3 projects and use the approved Studio posters "
     "and reel as the ad images (3 designs = an A/B/C test). RERA number on every ad. Margazhi plan: visits now, "
     "bookings from Thai.", "Y", "Ads ready to launch"),
    ("Salesperson #1 joins", "Onboarding: Workflow PDF, portal link, call within 15 minutes, scripts. If Meta has "
     "verified you: WhatsApp live (CHANNEL_MODE=live), a test with friends, and connect Facebook/Instagram auto-posting "
     "for the Studio (page token; Claude guides).", "YSC", "Portal opened"),
    ("ADS LAUNCH", "Meta lead ads + Click-to-WhatsApp at ₹1,500–2,000/day, Chennai only, with the 3 Studio designs "
     "per project as variants. Portals live. Training day 2 at the sites.", "YS", "First 15 leads"),
    ("Shadowing", "The salesperson listens to you on 5 calls, then you listen to theirs. Fix the gaps the same day.",
     "YS", "Certified on 2 projects"),
    ("Bank tie-ups", "Meet 2 home-loan branch managers in your focus markets; they meet buyers before builders do. "
     "Agree a referral arrangement.", "Y", "2 tie-ups"),
    ("First visit weekend", "Free cab pickup; register every buyer before the visit. You attend every visit for the "
     "first 3 weekends.", "YS", "2–4 visits"),
    ("Visits", "Visits; reports filed the same day.", "YS", "Reports in"),
    ("REVIEW #4", "Approve this week's Studio pack (10 min). Check cost per lead, % called within 15 minutes, and lead → visit. Kill the worst ad.", "Y",
     "KPIs logged"),
    ("Builder offers", "Get year-end offers and payment plans from every builder in writing; add them to Inventory. "
     "Studio: 'Value' angle posters with the approved offer (type it in 'Your idea').", "YA", "Offers logged + posters"),
    ("First builder reports", "Sales ▾ → Builder weekly reports: preview, send. From now on every Wednesday "
     "(15 minutes).", "YA", "Reports sent"),
    ("Pipeline hygiene + Google", "Salesperson: every lead has a next step; no call older than 24 hours. You: create the "
     "free Google Business Profile for Skyline Realty (office address, photos, phone); post one Studio poster a week "
     "there.", "SY", "0 overdue · profile live"),
    ("Christmas", "The AI handles replies; you're on call for hot leads only.", "A", "—"),
    ("Visits", "Holiday week: visits run high.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #5", "Approve this week's Studio pack (10 min). Enter December spend in Reports. The accountant sets up the invoice template and commission "
     "tracking.", "YO", "December entered"),
    ("Second builder wave", "Call 6 more CP managers; target 8 empanelled by day 50.", "Y", "4 meetings booked"),
    ("Reports + 2027 targets", "Builder reports. Set the 2027 targets and the salesperson's incentive slabs.", "YA",
     "Targets shared"),
    ("Thai list", "Tag every warm or visited buyer for a mid-January booking follow-up. Pre-agree price ranges for "
     "approvals.", "YS", "Hot list"),
    ("New Year", "Day off.", "", "—"),
    ("Visits", "Visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #6", "Approve this week's Studio pack (10 min). Weekly KPIs; agenda for the wave-2 meetings.", "Y", "Logged"),
    ("Builder meetings", "Wave-2 meetings (2).", "Y", "2 meetings"),
    ("Reports + meetings", "Builder reports; 2 more meetings.", "YA", "Sent"),
    ("Referral programme", "₹10–25k voucher per referred booking. Card to every visited buyer and to your network. Ask "
     "every visited buyer for a Google review.", "Y", "Referral card live"),
    ("Corporate outreach", "Email or LinkedIn 10 HR heads at IT companies near your markets, offering a free "
     "home-buying session in February.", "Y", "2 replies"),
    ("Family second visits", "Bring warm buyers back with the decision maker (spouse, parents).", "YS", "—"),
    ("Visits + phone reels", "The salesperson films two 30-second walk-throughs on visits; post them as reels with a "
     "Studio caption (also on YouTube Shorts).", "S", "2 reels"),
    ("REVIEW #7", "Ad rule: increase only campaigns with cost per visit under ₹5,000. Studio: make the Pongal/Thai pack "
     "(builder-approved offers) to post 13–17 Jan.", "Y", "Budget reset · Thai pack approved"),
    ("Booking logistics", "Booking slots at builder offices, builders' payment details, and cost sheets ready for hot "
     "buyers.", "S", "Ready"),
    ("Reports", "Builder reports.", "YA", "Sent"),
    ("Pongal", "Greeting + Thai offer message to warm leads.", "A", "—"),
    ("Thai begins", "Call every hot buyer and fix booking appointments.", "YS", "5+ appointments"),
    ("BOOKING WEEKEND", "Booking visits. Approvals within 1 hour.", "YS", "1–3 bookings"),
    ("BOOKING WEEKEND", "Same as yesterday.", "YS", "—"),
    ("REVIEW #8", "Approve this week's Studio pack (10 min). Verify each booking: registration ACK and invoice date (with the accountant).", "YO", "Verified"),
    ("Negotiation + content review", "Which concessions closed? Approve the AI's lessons. Reports: which ads and "
     "Studio angles brought visits (campaign STUDIO / ad codes)? Do more of those.", "Y", "Lessons approved"),
    ("Reports + collections", "Builder reports; collections calendar from the builders' CRM teams.", "YAO",
     "Calendar set"),
    ("Hire #2 decision", "If leads exceed 120/month, post the job ad for salesperson #2.", "Y", "Decision"),
    ("Inventory refresh", "Update prices and availability. Add projects that match the demand gaps (10-yr plan page).",
     "YC", "Inventory current"),
    ("Visits", "Visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #9 — DAY-60 CHECK", "Approve this week's Studio pack (10 min). Check: 8 builders? 500 leads? 3+ bookings? Fix the biggest miss first.", "Y",
     "Day-60 scorecard"),
    ("Republic Day", "Day off.", "", "—"),
    ("Reports", "Builder reports.", "YA", "Sent"),
    ("Pilot proposal", "Pick the builder with your most visits and slow inventory. Claude drafts the 60-day pilot from "
     "your data.", "YC", "Proposal ready"),
    ("Ad scale decision", "If cost per booking ≤ 30% of earnings per booking, raise to ₹2,500–3,000/day. Swap in fresh "
     "Studio designs (ads tire after about 2 weeks).", "Y", "Budget set · new creatives live"),
    ("Visits", "Visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #10 + January close", "Approve this week's Studio pack (10 min). January bookings vs target (4). Union Budget: if housing tax rules change, send "
     "a buyer message.", "Y", "January closed"),
    ("Pilot pitch", "Meet the sales head and propose the pilot.", "Y", "Agreed or next date"),
    ("Reports + interviews", "Builder reports; interviews for salesperson #2.", "YA", "Sent"),
    ("Bank tie-ups 2", "Meet 2 more home-loan managers and 1 DSA.", "Y", "3 more tie-ups"),
    ("Corporate session prep", "Confirm the session and ask a builder to co-fund the stall. Studio: posters for the "
     "company's internal channels and the stall.", "Y", "Date fixed"),
    ("Visits", "Visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #11", "Approve this week's Studio pack (10 min). Weekly KPIs; pilot progress.", "Y", "Logged"),
    ("Salesperson #2 offer", "Send the offer (joins 16 Feb) if the threshold is met.", "Y", "Offer accepted"),
    ("Reports + pilot report", "Builder reports, including the pilot's weekly numbers.", "YA", "Sent"),
    ("Corporate session", "Home-buying session with a builder.", "YS", "20+ leads"),
    ("FY-end offers", "Ask builders for their March targets and special offers.", "Y", "Offers logged"),
    ("Visits", "Visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #12", "Approve this week's Studio pack (10 min). Gate-1 view on the dashboard: the weakest line becomes this fortnight's focus.", "Y", "Gap list"),
    ("Salesperson #2 joins", "Onboarding and site training.", "YS", "Portal opened"),
    ("Reports", "Builder reports.", "YA", "Sent"),
    ("Learning review", "Read the AI's lessons and refresh the call scripts. Content check: which angles do you approve "
     "most, and which bring leads? Keep those in the weekly pack.", "Y", "Scripts updated"),
    ("March push prep", "Hot list + financial-year-end offer messaging.", "S", "Hot list"),
    ("BOOKING PUSH", "Visits + booking appointments.", "YS", "—"),
    ("BOOKING PUSH", "Same as yesterday.", "YS", "—"),
    ("REVIEW #13", "Approve this week's Studio pack (10 min). Weekly KPIs.", "Y", "Logged"),
    ("Company structure", "With the CA: Pvt Ltd timeline, RERA transfer, and the Karnataka RERA question (page 1).",
     "YO", "Dates fixed"),
    ("Reports + pilot review", "Builder reports; pilot day-30 review meeting.", "YA", "Reviewed"),
    ("Bangalore go / no-go", "Go only if Chennai runs at 6+ bookings a month without you on every call. Model: hire "
     "an experienced Bangalore city lead on salary plus profit share (no equity). Shortlist 10 builders by phone.",
     "Y", "Decision + shortlist"),
    ("AI preset review", "After 30+ real conversations: keep Best or move to Balanced. If Facebook/Instagram is "
     "connected, switch Studio auto-posting on (marketing.auto_publish).", "YC", "Decisions made"),
    ("BOOKING WEEKEND", "Booking visits.", "YS", "—"),
    ("BOOKING WEEKEND", "Same as yesterday.", "YS", "—"),
    ("REVIEW #14 + February close", "Approve this week's Studio pack (10 min). February bookings vs target (5).", "Y", "February closed"),
    ("100-day retrospective", "What worked (channels, builders, scripts) and what to stop.", "Y", "Retro notes"),
    ("Next 100 days", "Q2 targets, hiring, builder tiers and the Bangalore timeline. Send builder reports.", "YA",
     "Plan for days 101–200"),
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
        rows += f'<tr class="wk"><td colspan="6">Week {week} · {d:%d %b} – {end:%d %b}</td></tr>'
    cls = "rev" if focus.startswith("REVIEW") else "hol" if focus in ("Christmas", "New Year", "Republic Day", "Pongal") \
        else "we" if d.weekday() >= 5 else ""
    rows += (f'<tr class="{cls}"><td>{i + 1}</td><td>{d:%a %d %b}</td><td>{focus}</td><td>{tasks}</td>'
             f'<td>{tags(who)}</td><td>{done}</td></tr>')

KPI = [  # week, builders met, empanelled, projects live, leads, visits, bookings (cumulative) — Chennai only
    (1, 10, 0, 0, 0, 0, 0), (2, 14, 2, 2, 0, 0, 0), (3, 16, 4, 4, 0, 0, 0), (4, 18, 5, 6, 40, 3, 0),
    (5, 18, 6, 7, 100, 9, 0), (6, 20, 6, 8, 170, 15, 0), (7, 22, 7, 9, 250, 22, 0), (8, 24, 8, 10, 340, 30, 1),
    (9, 25, 8, 11, 430, 38, 2), (10, 26, 9, 12, 520, 46, 3), (11, 27, 9, 13, 610, 54, 4),
    (12, 28, 10, 14, 700, 62, 6), (13, 29, 10, 15, 790, 70, 7), (14, 30, 10, 16, 880, 78, 9),
    (15, 30, 10, 16, 950, 84, 10)]
kpi = "".join(f"<tr><td>W{w}</td><td>{a}</td><td>{b}</td><td>{c}</td><td>{d:,}</td><td>{e}</td><td><b>{f}</b></td></tr>"
              for w, a, b, c, d, e, f in KPI)

MONTHS = [("Jan", 4, "Chennai · Thai bookings from mid-Jan"), ("Feb", 5, "Chennai · financial-year-end offers"),
          ("Mar", 7, "Chennai · FY-end push; 2nd salesperson productive"), ("Apr", 6, "Bangalore city lead starts (if go)"),
          ("May", 7, "Summer; NRI visits"), ("Jun", 8, "Appraisal and bonus season"),
          ("Jul", 6, "Aadi month: slower in TN"), ("Aug", 8, "Aadi ends"), ("Sep", 9, "Pre-festive"),
          ("Oct", 11, "Navratri / Dussehra / Diwali"), ("Nov", 9, "Post-Diwali"), ("Dec", 10, "Year-end offers")]
mrows = "".join(f"<tr><td>{m}</td><td>{n}</td><td>{note}</td></tr>" for m, n, note in MONTHS)

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Skyline Realty — 100-Day Plan v2 & Builder Playbook</title>
<style>{css}</style></head><body>

<!-- ============ PAGE: REVIEW ============ -->
<div class="sect">
<div class="cover"><h1>Skyline Realty — The Exact Plan (v2, solo founder)</h1><p>Review of the first plan · Overall plan · Channel-partner (CP) playbook · Day-by-day 100-day plan (24 Nov 2026 – 3 Mar 2027) · Chennai first</p></div>

<h2>1. Review of the first 100-day plan: what was unrealistic</h2>
<table>
<tr><th style="width:30%">In version 1</th><th style="width:34%">Why it would not work</th><th>Version 2 (this plan)</th></tr>
<tr><td>Two cities from day 1</td><td>One person can't build builder trust, hire, train and close in two cities 350 km apart.
Attention splits, travel eats days.</td><td><b>Chennai only for 100 days.</b> Bangalore gets a go/no-go on day 94 and
starts in April with a hired city lead.</td></tr>
<tr><td>Your wife ran Bangalore, finance and compliance</td><td>She is a sleeping partner.</td><td>You own every
decision. <b>Admin is outsourced</b>: an accountant (GST invoices, TDS, books) and the CA (structure).
The <b>Marketing Studio (AI)</b> makes the posters and reels, so there's no marketing hire. Your wife signs one authority letter on day 4.</td></tr>
<tr><td>16 builders empanelled</td><td>Each builder needs real relationship time. Spreading thin means nobody
prioritises you.</td><td><b>10 empanelled, 4–5 deeply active</b>: 2 anchor brands for credibility plus 3 builders with
slow stock, where pilots come from.</td></tr>
<tr><td>15–20 bookings by day 100</td><td>Ads start 16 Dec. Buyers take 30–90 days from enquiry to booking, and many
Tamil families avoid booking in Margazhi.</td><td><b>8–12 bookings</b>, starting from the Thai weekend (16–17 Jan).
The aim is a run rate of 5–7 a month by March.</td></tr>
<tr><td>Ops executive by day 100</td><td>A fixed cost before the revenue exists.</td><td>The system plus the accountant
do this work. Hire only after about 8 bookings a month.</td></tr>
<tr><td>Every day fully loaded</td><td>Burnout, then dropped follow-ups.</td><td>Tasks sized for about 4 focused hours plus calls
and visits. Max 3 builder meetings a day. Friday afternoons protected.</td></tr>
</table>

<h2>2. What makes version 2 more likely to succeed</h2>
<table>
<tr><td style="width:4%"><b>1</b></td><td><b>Focus beats spread.</b> In 2–3 Chennai micro-markets, builders, bankers and buyers start recognising
Skyline within weeks.</td></tr>
<tr><td><b>2</b></td><td><b>Hire the salesperson first (joins day 22).</b> They make the calls and handle visits; you handle builders,
closing and approvals, the things only you can do.</td></tr>
<tr><td><b>3</b></td><td><b>Lead with ready-to-move and near-possession homes.</b> Buyers decide faster when they can see the finished
flat and plan a move-in date. Completed projects with an occupancy certificate also attract no GST, a strong talking
point (confirm per project).</td></tr>
<tr><td><b>4</b></td><td><b>Warm channels before paid ones:</b> your network, referrals, home-loan branch managers and corporate HR
sessions. Cheaper leads, higher trust, faster bookings. Ads add volume on top.</td></tr>
<tr><td><b>5</b></td><td><b>Builder trust on autopilot:</b> the weekly builder report (now built into the system) goes out every
Wednesday from week 5. That's how pilots and better slabs are earned.</td></tr>
<tr><td><b>6</b></td><td><b>Speed and visit rate:</b> call within 15 minutes, free cab pickup, weekend slots, and you at every visit for
the first 3 weekends to learn what closes.</td></tr>
<tr><td><b>7</b></td><td><b>AI marketing instead of a marketing team:</b> the Marketing Studio drafts a weekly pack of posters
and reels from real project photos. You approve in 10 minutes; it posts daily and tracks which angles bring
leads.</td></tr>
<tr><td><b>8</b></td><td><b>Spend only behind proof:</b> ads rise only while cost per booking stays below 30% of earnings, and salesperson
#2 joins only above 120 leads a month.</td></tr>
</table>

<div class="warn keep"><b>Bangalore and the Karnataka RERA registration:</b> it is in your wife's name. Before any Bangalore
activity, ask your CA and a RERA consultant whether the firm can trade there under her registration while she is a
sleeping partner, or whether the firm (or the new Pvt Ltd) should register in Karnataka itself. Until then: no
Bangalore ads or registrations. The authority letter (day 4) covers the documents she would otherwise have to
sign.</div>
</div>

<!-- ============ PAGE: OVERALL PLAN ============ -->
<div class="sect">
<h2>3. The overall plan on one page</h2>
<table>
<tr><th style="width:24%">What we are</th><td><b>Skyline Realty, Chennai's AI-powered home advisor</b> (Bangalore next). Buyers get honest,
fast, curated options and are looked after until registration. Builders get qualified buyers, price discipline and
a weekly report.</td></tr>
<tr><th>Who we sell to</th><td>Salaried IT and professional families aged 28–45 buying a first home or upgrading, ₹60 L–₹1.5 Cr.
Second: NRIs from Tamil Nadu buying back home.</td></tr>
<tr><th>Where</th><td>Chennai, 2–3 micro-markets (chosen on day 2). Bangalore from April 2027 only if the day-94 test is
passed.</td></tr>
<tr><th>How we earn</th><td>Year 1: builder commission of 2–3% of the agreement value (+18% GST charged to the builder). Year 2:
exclusive mandates at 3.5–5% plus fees. Year 3+: own projects through joint development (see 10-Year Plan).</td></tr>
<tr><th>How we win</th><td>Replies in 5 minutes and follow-up until a decision (AI + salesperson) · only qualified buyers visit
· registration before every visit · every price approved by you · weekly builder reports · lowest cost per
booking.</td></tr>
<tr><th>Team, first 100 days</th><td><b>You</b> (builders, closing, approvals, hiring) · <b>salesperson #1</b> from 15 Dec ·
<b>salesperson #2</b> from 16 Feb if leads exceed 120/month · <b>accountant</b> (part-time, outsourced) · <b>CA</b> ·
<b>Marketing Studio (AI)</b> for all content, no marketing hire · builders' site teams host visits · <b>the AI system</b>, 24×7.</td></tr>
<tr><th>Year-1 target (2027)</th><td><b>90 bookings</b> (Chennai about 75, Bangalore about 15 from Q2) · ~₹80 Cr sales · <b>~₹2.1 Cr
commission</b> · estimated costs ₹1.1–1.3 Cr · profit ₹0.8–1 Cr, reinvested.</td></tr>
<tr><th>The ladder</th><td>Year 1 prove the engine in Chennai → Year 2 Bangalore + exclusive mandates → Year 3–4 first own project
(JDA) → Year 6+ platform licensing → Year 10 ~$1B company, 100% owned by the partners.</td></tr>
</table>

<div class="cols">
<div class="keep"><h3>2027 month-by-month bookings (= 90)</h3>
<table><tr><th>Month</th><th>Bookings</th><th>Why</th></tr>{mrows}</table></div>
<div class="keep"><h3>Funnel maths for 8 bookings a month</h3>
<table>
<tr><td>Leads needed</td><td>~650</td></tr><tr><td>Lead → site visit</td><td>10% → 65 visits</td></tr>
<tr><td>Visit → booking</td><td>12–15% → 8 bookings</td></tr>
<tr><td>Commission earned</td><td>8 × ₹2.25 L ≈ ₹18 L</td></tr>
<tr><td>Marketing cap (30%)</td><td>≤ ₹5.4 L / month</td></tr></table>
<p><small>At ₹90 L average and 2.5%. Warm channels (referrals, bankers, corporate sessions) lower the cost per booking
the most.</small></p>
<h3>Who does what</h3>
<table><tr><td>{tags('Y')}</td><td>Builders, closing, approvals, hiring, Monday review</td></tr>
<tr><td>{tags('S')}</td><td>Calls within 15 minutes, visits, follow-up, visit reports</td></tr>
<tr><td>{tags('A')}</td><td>Replies, follow-ups, reminders, builder reports, <b>posters, reels, captions, posting</b></td></tr>
<tr><td>{tags('O')}</td><td>Accountant: invoices, GST/TDS · CA: structure</td></tr>
<tr><td>{tags('C')}</td><td>Inventory uploads, set-up, proposals, system changes</td></tr></table></div>
</div>
</div>

<!-- ============ PAGE: BUDGET + KPI + WEEK ============ -->
<div class="sect">
<h2>4. 100-day budget, Chennai only (estimates; get real quotes)</h2>
<table>
<tr><th>Item</th><th>100 days</th><th>Notes</th></tr>
<tr><td>Meta ads (lead ads + Click-to-WhatsApp)</td><td>₹2.5–3.5 L</td><td>₹1,500–2,000/day from 16 Dec; up to ₹2,500–3,000/day only if the 30% rule holds</td></tr>
<tr><td>Portals (one city)</td><td>₹0.75–1.5 L</td><td>3-month trial for your localities</td></tr>
<tr><td>Salespeople — fixed</td><td>₹1.2–1.6 L</td><td>#1 from 15 Dec, #2 from 16 Feb (if triggered); ₹25–35k/month</td></tr>
<tr><td>Sales incentives</td><td>₹1–1.8 L</td><td>₹10–15k per booking</td></tr>
<tr><td>Free cab pickup</td><td>₹0.4–0.6 L</td><td>~₹1,000 per visit, about half the visits</td></tr>
<tr><td>Accountant (outsourced)</td><td>₹0.2–0.3 L</td><td>GST invoices, TDS, books</td></tr>
<tr><td>CA, legal, agreements, Pvt Ltd groundwork</td><td>₹0.5–1 L</td><td>incl. authority letter, RERA advice</td></tr>
<tr><td>Visiting cards, one-pager, standee</td><td>₹0.15–0.25 L</td><td>No freelancer: content comes from the Marketing Studio</td></tr>
<tr><td>AI (incl. Marketing Studio) + hosting + WhatsApp</td><td>₹0.35–0.6 L</td><td>The studio adds only a few hundred rupees a month</td></tr>
<tr><td>Contingency</td><td>₹0.75 L</td><td></td></tr>
<tr><th>Total</th><th>₹7.8–11.9 L</th><th>Plus keep an <b>₹8 L buffer</b>: commission arrives 30–90 days after booking.</th></tr>
</table>

<h2>5. Weekly scorecard — cumulative targets (Chennai)</h2>
<table><tr><th>Week</th><th>Builders met</th><th>Empanelled</th><th>Projects live</th><th>Leads</th><th>Site visits</th><th>Bookings</th></tr>{kpi}</table>
<div class="ok"><b>Day-100 targets:</b> 10 builders empanelled (4–5 active) · 16 projects live · ~950 leads · ~85 site visits ·
<b>8–12 bookings</b> (≈ ₹18–27 L commission earned) · 1 pilot running · WhatsApp live · 2 salespeople · accountant in
place · Bangalore go/no-go decided.</div>

<div class="keep"><h3>Your week as a solo founder (from week 4)</h3>
<table>
<tr><td style="width:13%"><b>Mon</b></td><td>9:00 digest · 9:30–10:30 <b>review</b> (10-yr plan page, Reports) + <b>approve the Studio pack</b> (10 min) · calls and approvals · afternoon: builder meeting</td></tr>
<tr><td><b>Tue</b></td><td>Builder prospecting and meetings (max 3) · 30 minutes with the accountant when needed</td></tr>
<tr><td><b>Wed</b></td><td>10:00 <b>send builder reports</b> (15 min) · meetings · marketing (ads, content)</td></tr>
<tr><td><b>Thu</b></td><td>Coach the salesperson (listen to 3 calls) · closing calls · bank and corporate tie-ups</td></tr>
<tr><td><b>Fri</b></td><td>Morning: booking logistics and hot list for the weekend · <b>afternoon off</b> (protect it)</td></tr>
<tr><td><b>Sat–Sun</b></td><td>Site visits and closing, the peak days · visit reports the same evening</td></tr>
<tr><td><b>Daily</b></td><td>Approvals within 1 hour (the AI waits for you) · 7 PM: 10-minute pipeline check · 7:30 PM: post today's creative (2 min, until auto-posting is on) + WhatsApp status · salesperson's weekly off: Tuesday</td></tr>
</table></div>

<div class="warn"><b>Local calendar (verify the dates each year):</b>
<ul><li><b>Margazhi (mid-Dec → mid-Jan):</b> visits and pipeline; close from Thai.</li>
<li><b>Feb–Mar:</b> builders' financial-year-end push, the best time to ask for offers and slabs.</li>
<li><b>Aadi (mid-Jul → mid-Aug):</b> slow.</li>
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
<tr><td><b>Monthly</b></td><td>{tags('Y')} 30 min: Reports + 10-yr plan page: which angles and ads brought <i>visits</i>, not just leads? Keep those.</td></tr>
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

<!-- ============ PAGE: CP PLAN — STRATEGY ============ -->
<div class="page" style="page-break-before:always">
<h2>7. CP plan with builders — the strategy</h2>
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
<tr><td>Delivery track record (past projects on time)</td><td>20</td><td rowspan="7" style="width:38%"><small><b>How to check:</b> RERA project page (quarterly progress, complaints), visit 1 completed project and talk to residents, ask 2 other CPs about payouts, Google reviews, site visit to see actual progress vs the RERA schedule.<br><br><b>Mix to aim for in Chennai (first 100 days):</b> 2 "anchor" builders (strong brand, steady demand) for credibility, plus 3 mid-size builders with slow inventory (where pilots and higher slabs come from). 10 empanelled, 4–5 truly active.</small></td></tr>
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
<li><b>Term, termination, jurisdiction</b> (Chennai courts)</li>
</ol>
<div class="warn"><b>Red flags, walk away:</b> fee or deposit for empanelment · project not RERA-registered · stalled
site · reports of delayed CP payouts · builder wants buyer details before agreeing to protect your registration ·
"commission only after the full payment".</div>
</div>

<!-- ============ PAGE: APPROACH + SCRIPTS ============ -->
<div class="page">
<h2>8. How to approach builders</h2>
<div class="cols">
<div class="keep"><h3>Ways in, best first</h3><ol>
<li><b>Warm introduction</b>: bankers (home-loan managers know every builder), architects, other CPs, friends in the
industry. Best response rate.</li>
<li><b>Walk into the project sales office</b> and ask for the CP manager. Weekday mornings are quiet; weekends are busy.</li>
<li><b>CP meets and launch events</b>: builders invite CPs at launches. Get added to each builder's CP WhatsApp group.</li>
<li><b>CREDAI chapters and property expos</b> in Chennai: meet many builders in one day.</li>
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
channel partner (TN RERA: <i>[no.]</i>) focused on <i>[micro-markets]</i>. What we offer partners: replies to
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
<h2>9. Objections, pilot and mandate</h2>
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
<h2>10. The 100-day plan — day by day</h2>
<p><small>Shading: <span style="background:#fff7d6;padding:0 2mm">weekly review</span>
<span style="background:#f6f8fb;padding:0 2mm">weekend (visit days)</span>
<span style="background:#f3f0ff;padding:0 2mm">holiday</span>. Owners: {tags('YSAOC')}. If you fall behind, keep the
Monday review and the "done when" column honest; push dates, don't skip steps.</small></p>
<table class="days"><thead><tr><th>Day</th><th>Date</th><th>Focus</th><th>Tasks</th><th>Who</th><th>Done when</th></tr></thead>
{rows}
</table>
</div>

<div class="page">
<h2>11. After day 100 — what success unlocks</h2>
<table>
<tr><th style="width:30%">If by day 100…</th><th>Then in days 101–200…</th></tr>
<tr><td>8+ bookings and cost per booking ≤ 30% of earnings</td><td>Raise ads gradually, hire salesperson #3, add 1 micro-market, start Bangalore with a city lead</td></tr>
<tr><td>A pilot hit its target</td><td>Convert it to preferred partner; start a second pilot</td></tr>
<tr><td>Fewer than 6 bookings</td><td>Don't increase spend. Check the weakest funnel step (contact speed? visit rate? visit → booking?) and fix it first</td></tr>
<tr><td>One builder is more than 40% of commission</td><td>Push the second and third builders in that micro-market</td></tr>
<tr><td>Commission is collected late</td><td>Tighten payout terms in renewals; prefer builders who pay on time</td></tr>
</table>
<div class="cover" style="margin-top:4mm"><h1 style="font-size:13pt">The 100-day promise</h1>
<p>By 3 March 2027: 10 builders signed (4–5 active), 16 projects live, WhatsApp live, 2 salespeople, 8–12 bookings, a
pilot running and builders receiving your weekly report. That's the proof you need to open Bangalore and start
Year 2's exclusive mandates.</p></div>
</div>
</body></html>"""
open(f"{ROOT}/docs/100-day-plan.html", "w").write(html)
print("ok")
