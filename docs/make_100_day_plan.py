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
.tA { background:#dcf3e4; color:#145c33; } .tC { background:#eceff4; color:#3b4252; }
"""

TAGS = {"Y": "You", "W": "Wife", "S": "Sales", "A": "AI", "C": "Claude"}


def tags(s):
    return "".join(f'<span class="tag t{c}">{TAGS[c]}</span>' for c in s)


# (focus, tasks, owners, done-when). Owners: Y = you, W = your wife, S = salespeople, A = AI system, C = Claude.
DAYS = [
    ("Foundation", "Finish Settings (brand, firm name, RERA for both cities, bank, team placeholders). Remove sample "
     "inventory and 'Sunrise Meadows'. Read the Workflow and 10-Year Plan PDFs together.", "YW", "Settings items green on Overview"),
    ("Roles & focus markets", "Agree the split (suggested): You = Chennai + builder relationships; Wife = Bangalore + "
     "finance, compliance, invoices. List 5 candidate micro-markets per city; rank them on ₹60 L–1.5 Cr fit, job hubs, "
     "supply depth and your network. Pick 2–3 per city.", "YW", "Focus sheet signed off"),
    ("Builder longlist", "Use the TN RERA / K-RERA project search for your focus localities, plus 99acres, MagicBricks "
     "and Housing listings and hoardings. List 25 projects per city in docs/builder-scorecard.csv.", "YW", "50-row longlist"),
    ("Empanelment kit", "One folder with PAN, GST certificate, both RERA agent certificates, partnership deed, "
     "cancelled cheque and letterhead. Order 500 visiting cards. Make a one-page 'About Skyline Realty' PDF. Book "
     "the CA meeting.", "W", "Kit ready (PDF + printed set)"),
    ("Field day — Chennai", "Visit 5 sales offices in your focus markets as a CP. Meet the CP manager. Collect the CP "
     "policy (commission %, payout trigger, tagging rules), price sheet, brochure and floor plans. Note walk-in "
     "traffic.", "Y", "5 CP policies + price sheets"),
    ("Field day — Bangalore", "Same in Bangalore. Note which projects look slow (quiet sales office, many unsold "
     "floors): slow inventory makes the best pilot candidates.", "W", "5 CP policies + price sheets"),
    ("REVIEW #1", "Score every project on the scorecard (page 4). Pick the top 12 per city. Buy a new SIM for "
     "WhatsApp Business. Start Meta Business verification with your GST certificate and partnership deed.", "YW",
     "Shortlist of 24 · SIM bought"),
    ("Hiring + builder calls", "Post salesperson job ads on Naukri, LinkedIn, Indeed and apna, plus referrals. Call 12 "
     "Chennai CP managers using the call script (page 5).", "Y", "6 meetings booked"),
    ("Builder meetings 1–3", "Chennai meetings using the 30-minute agenda. Leave the empanelment kit. Ask for the CP "
     "agreement draft and current offers.", "Y", "3 meetings, notes in scorecard"),
    ("Builder meetings 4–6", "Chennai meetings 4–6. Bangalore: call 12 CP managers and book 6 meetings.", "YW",
     "6 Chennai meetings done"),
    ("Agreements", "Check each CP agreement against the 12-point checklist (page 4). Negotiate the payout trigger, "
     "tagging validity and clawback, then sign the clean ones. Send the signed projects' price lists to Claude for "
     "the upload file.", "YWC", "3 agreements signed"),
    ("Interviews", "Walk-in interviews with a 30-minute role play (cold enquiry → visit booking, then a price "
     "objection). Shortlist 2 per city.", "Y", "2 Chennai finalists"),
    ("Project learning", "Walk 2 signed projects end to end: amenities, distance to IT parks and schools, common "
     "objections. Enter 5 highlights and 5 FAQs per project in Inventory.", "Y", "2 projects fully documented"),
    ("REVIEW #2", "Check: 6 meetings done, 3+ agreements, 3 projects live in Inventory. Meta verification status. "
     "CA outcome: Pvt Ltd plan, GST invoice format, TDS under 194H.", "YW", "Week-2 scorecard"),
    ("Bangalore meetings 1–3", "Wife: Bangalore meetings. You: send the offer letter to Chennai salesperson #1 "
     "(start 17 Dec).", "WY", "Offer accepted"),
    ("Bangalore meetings 4–6", "Meetings 4–6; collect agreements.", "W", "6 Bangalore meetings"),
    ("Portals", "Get quotes from 99acres, MagicBricks and Housing for your localities and negotiate a 3-month trial. "
     "Set every portal to forward leads to skylinerealty.leads@gmail.com.", "W", "Packages chosen"),
    ("Meta set-up", "Facebook page, Instagram, ad account. Lead form: name, phone, budget, city, timeline + consent. "
     "Connect Meta lead ads under Lead sources (Claude guides).", "YC", "Test lead lands in dashboard"),
    ("Field + inventory", "Chennai: 3 second-wave builder visits. Bangalore: walk 2 signed projects. Check every "
     "signed project's landing page (/p/…).", "YW", "6+ projects live"),
    ("Network seeding", "Personal WhatsApp to about 200 contacts (friends, ex-colleagues, relatives) announcing "
     "Skyline Realty with the referral reward. Post on LinkedIn.", "YW", "200 messages sent"),
    ("REVIEW #3", "Approve campaigns (Marketing → Campaigns) for the top 3 projects per city, with the RERA number "
     "on every ad. Margazhi plan: build pipeline now, book from Thai.", "YW", "Campaigns approved"),
    ("WhatsApp go-live", "If Meta verification is done: connect the WhatsApp Cloud API, set CHANNEL_MODE=live, and "
     "test with 3 friends end to end. If not: stay in test mode and have the salesperson send drafts by hand.", "YC",
     "Live message test passed"),
    ("ADS LAUNCH", "Meta lead ads + Click-to-WhatsApp, ₹2,000–2,500/day across both cities. Portals live. Check "
     "every lead gets an AI reply within 5 minutes and a call task.", "Y", "First 20 leads"),
    ("Salesperson #1 joins", "Onboarding: Workflow PDF, sales portal link, call discipline (call within 15 minutes), "
     "review-mode drafts, the 5 scripts.", "YS", "Portal opened, first calls made"),
    ("Training day 2", "Site training at 2 projects, role plays, and shadowing you on 5 calls.", "YS",
     "Certified on 2 projects"),
    ("First visit weekend", "Offer free cab pickup for visits (₹800–1,500) to lift the visit rate. Register every "
     "buyer with the builder before the visit and get the ACK.", "SY", "3–5 visits, all registered"),
    ("Visits", "Fill every visit report the same day; review the AI's strategy for each buyer.", "S", "Reports done"),
    ("REVIEW #4", "Look at cost per lead, % of leads called within 15 minutes, and lead → visit. Kill the worst ad, "
     "double the best.", "YW", "Week KPIs logged"),
    ("Builder offers", "Ask every builder for year-end / New Year offers in writing (payment plans, freebies) and "
     "add them to the project highlights.", "YW", "Offers logged"),
    ("Bangalore salesperson", "Send the offer to the Bangalore salesperson (start 4 Jan). Wife handles Bangalore "
     "calls until then.", "W", "Offer accepted"),
    ("Pipeline hygiene", "Every open lead has a next step and a date. Clear drafts; no call older than 24 hours.",
     "SY", "0 overdue"),
    ("Christmas", "Light day. The AI handles replies; on call only for hot leads.", "A", "—"),
    ("Visits", "Holiday-week visits run high: plan visits at 2–3 projects.", "S", "Visits done"),
    ("Visits", "Same as yesterday.", "S", "Reports in"),
    ("REVIEW #5", "Enter December ad and portal spend in Reports; first unit-economics look. Send builders their "
     "weekly reports.", "YW", "Spend entered"),
    ("Commission machine", "Invoice template (GST 18%), registration ACKs tracked, payout triggers per builder in "
     "Commissions. Keep a working-capital buffer, because payouts take 30–90 days.", "W", "Process written down"),
    ("Builder updates", "Send every builder a one-page update: buyers registered, visits, buyer feedback on price "
     "and product. This builds the trust you need for a mandate later.", "Y", "Updates sent"),
    ("2027 targets", "Set 2027 monthly targets (page 2) and incentive slabs; announce them to the team.", "YW",
     "Targets shared"),
    ("New Year", "Day off. Send a New Year greeting to opted-in leads only.", "A", "—"),
    ("Visits", "New Year visits; move serious buyers onto the 'book from Thai' plan.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #6 + Bangalore joins", "Onboard the Bangalore salesperson (same 2-day training); review the week's "
     "KPIs.", "WS", "Bangalore portal opened"),
    ("Bangalore training day 2", "Site training on the Bangalore projects; role plays.", "WS", "Certified"),
    ("Second builder wave", "Call 10 more builders per city; target 8 active builders per city by day 60.", "YW",
     "6 meetings booked"),
    ("Thai booking drive plan", "List every lead who visited in Dec–Jan and is warm or hot. Prepare builder-approved "
     "offers for bookings from 15 Jan and pre-agree price ranges for approvals.", "YS", "Hot list of 15–25"),
    ("Referral programme", "Formalise a ₹10k–25k voucher on every referred booking. Share the card with every "
     "visited and booked buyer.", "Y", "Referral card live"),
    ("Visits", "Weekend visits; invite hot buyers for a second visit with family.", "S", "—"),
    ("Content", "Shoot 4 short site walk-through videos for Instagram and YouTube Shorts (get builder permission).",
     "SY", "4 videos"),
    ("REVIEW #7", "Ad budget rule: increase only campaigns with cost per visit under ₹5,000. Plan the wave-2 "
     "builder meetings.", "YW", "Budget reset"),
    ("Builder meetings (wave 2)", "Wave-2 meetings in both cities.", "YW", "4+ meetings"),
    ("Booking logistics", "Confirm booking-day slots at builder offices and the builders' payment details (payments go "
     "to the builder's account only).", "S", "Slots fixed"),
    ("Pongal / Sankranti", "Greeting + Thai offer message to warm leads. Light day.", "A", "—"),
    ("Thai begins", "Call every hot lead and fix booking visits for the weekend.", "SY", "8+ booking appointments"),
    ("BOOKING WEEKEND", "Booking visits at builder offices. Management approvals within 1 hour.", "SYW", "2–4 bookings"),
    ("BOOKING WEEKEND", "Same as yesterday.", "SYW", "—"),
    ("REVIEW #8", "Celebrate the first bookings. For each booking check the registration ACK and the invoice due "
     "date.", "YW", "Bookings verified"),
    ("Negotiation review", "Read every offer and approval: were approvals fast, and which concessions closed? Approve "
     "what the AI learned (Learning page).", "Y", "Lessons approved"),
    ("Collections", "Get agreement registration dates from each builder's CRM and set invoice dates.", "W",
     "Invoice calendar"),
    ("Pilot proposal", "Pick the best builder relationship with slow inventory. Prepare the 60-day pilot proposal "
     "(page 6) using your own data.", "YC", "Proposal ready"),
    ("Pilot pitch — Chennai", "Meet the sales head and propose the pilot: booking target, higher slab, "
     "co-marketing.", "Y", "Pilot agreed or next date"),
    ("Visits", "Weekend visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #9 — DAY-60 CHECK", "Check: 8 builders per city? 1,000 leads? 6+ bookings? Fix the biggest miss "
     "first.", "YW", "Day-60 scorecard"),
    ("Republic Day", "Day off.", "", "—"),
    ("Pilot pitch — Bangalore", "Wife pitches the pilot to the best Bangalore builder.", "W", "Pilot agreed or next date"),
    ("Inventory refresh", "Update prices and availability for every project (stale prices kill trust). Add 3–5 "
     "projects that match the demand gaps on the 10-yr plan page.", "YWC", "Inventory current"),
    ("Ad scale decision", "If cost per booking ≤ 30% of earnings per booking, raise the budget to ₹3,500–4,000/day.",
     "Y", "Budget set"),
    ("Visits", "Weekend visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #10 + January close", "Enter January spend; bookings vs target (6). Union Budget day: if housing tax "
     "rules change, prepare a buyer message.", "YW", "January closed"),
    ("Hire #3?", "Hire a second Chennai salesperson if leads exceed 150/month per salesperson.", "Y", "Decision made"),
    ("Builder reports", "Weekly builder reports. From now on this is routine every Wednesday.", "YW", "Reports sent"),
    ("Ops executive", "Job ad for a CRM/ops executive (invoices, registrations, builder reports, data hygiene). Hire "
     "by day 100.", "W", "Job ad live"),
    ("Referral tie-ups", "Meet 3 home-loan bank/DSA managers and 2 corporate HR teams per city (employee home-buying "
     "day).", "YW", "5 tie-up meetings"),
    ("Visits", "Weekend visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #11", "Weekly KPIs; check pilot progress against target.", "YW", "Logged"),
    ("Pilot report", "Weekly pilot report to each pilot builder.", "YW", "Sent"),
    ("Corporate activation", "One home-buying-day stall at an IT park or company, co-funded by a builder.", "SY",
     "30+ leads"),
    ("Learning review", "Read the AI's weekly lessons, approve them and refresh the call scripts.", "Y",
     "Scripts updated"),
    ("FY-end deals", "Ask builders for their March (financial-year-end) targets and special offers; builders push "
     "hardest in Feb–Mar.", "YW", "Offers logged"),
    ("Visits", "Weekend visits.", "S", "—"),
    ("Visits", "Same as yesterday.", "S", "—"),
    ("REVIEW #12", "Open the Gate-1 view on the dashboard; list the weakest line and an owner for it.", "YW",
     "Gap list"),
    ("Interviews", "Interview for the second salesperson and the ops executive.", "YW", "Offers out"),
    ("Builder reports", "Weekly builder reports.", "YW", "Sent"),
    ("Preferred-partner case", "Draft the preferred-partner proposal for the pilot builders, with results.", "YC",
     "Proposal ready"),
    ("Mandate meetings", "Present the results. Ask for preferred status: higher slab, priority inventory, marketing "
     "co-funding.", "YW", "1 preferred deal"),
    ("FY-end booking push", "Visits + booking appointments.", "S", "—"),
    ("FY-end booking push", "Same as yesterday.", "S", "—"),
    ("REVIEW #13", "Weekly KPIs.", "YW", "Logged"),
    ("Company structure", "Finalise the Pvt Ltd incorporation timeline and RERA transfer plan with the CA.", "W",
     "Dates fixed"),
    ("Builder reports", "Weekly builder reports.", "YW", "Sent"),
    ("AI preset review", "After 30+ real conversations, keep Best or move to Balanced, based on conversion "
     "numbers.", "YC", "Decision"),
    ("March push prep", "Financial-year-end booking drive: hot list and messaging.", "S", "Hot list"),
    ("BOOKING WEEKEND", "Booking visits.", "SYW", "—"),
    ("BOOKING WEEKEND", "Same as yesterday.", "SYW", "—"),
    ("REVIEW #14 + February close", "Enter February spend; bookings vs target (8).", "YW", "February closed"),
    ("100-day retrospective", "What worked (channels, builders, scripts) and what to stop. Update the plan.", "YW",
     "Retro notes"),
    ("Next 100 days", "Set Q2 targets, the hiring plan and builder tiers; write the Gate-1 gap list.", "YW",
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
    cls = "rev" if focus.startswith("REVIEW") else "hol" if focus in ("Christmas", "New Year", "Republic Day",
                                                                       "Pongal / Sankranti") \
        else "we" if d.weekday() >= 5 else ""
    rows += (f'<tr class="{cls}"><td>{i + 1}</td><td>{d:%a %d %b}</td><td>{focus}</td><td>{tasks}</td>'
             f'<td>{tags(who)}</td><td>{done}</td></tr>')

KPI = [  # week, builders met, empanelled, projects live, leads, visits, bookings (cumulative)
    (1, 10, 0, 0, 0, 0, 0), (2, 16, 3, 3, 0, 0, 0), (3, 22, 6, 6, 0, 0, 0), (4, 24, 8, 8, 60, 5, 0),
    (5, 24, 9, 10, 160, 15, 0), (6, 26, 10, 12, 280, 25, 0), (7, 30, 11, 14, 420, 38, 1), (8, 34, 12, 16, 580, 52, 3),
    (9, 36, 13, 18, 750, 65, 6), (10, 38, 14, 20, 920, 78, 8), (11, 40, 15, 22, 1100, 92, 10),
    (12, 42, 16, 24, 1300, 108, 12), (13, 44, 16, 26, 1500, 124, 14), (14, 46, 16, 28, 1700, 140, 16),
    (15, 46, 16, 30, 1850, 150, 18)]
kpi = "".join(f"<tr><td>W{w}</td><td>{a}</td><td>{b}</td><td>{c}</td><td>{d:,}</td><td>{e}</td><td><b>{f}</b></td></tr>"
              for w, a, b, c, d, e, f in KPI)

MONTHS = [("Jan", 6, "Margazhi ends; Thai bookings from mid-Jan"), ("Feb", 8, "Financial-year-end offers begin"),
          ("Mar", 10, "Financial-year-end push by builders"), ("Apr", 8, "Ugadi / Tamil New Year"),
          ("May", 9, "Summer; NRI visits"), ("Jun", 10, "Appraisal and bonus season"),
          ("Jul", 7, "Aadi month: slower in TN — build pipeline"), ("Aug", 10, "Aadi ends; Independence Day offers"),
          ("Sep", 12, "Pre-festive"), ("Oct", 14, "Navratri / Dussehra / Diwali"), ("Nov", 12, "Post-Diwali"),
          ("Dec", 14, "Year-end offers")]
mrows = "".join(f"<tr><td>{m}</td><td>{n}</td><td>{note}</td></tr>" for m, n, note in MONTHS)

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Skyline Realty — 100-Day Plan & Builder Playbook</title>
<style>{css}</style></head><body>

<!-- ============ PAGE: OVERALL PLAN ============ -->
<div class="page">
<div class="cover"><h1>Skyline Realty — The Exact Plan</h1><p>Overall plan · Channel-partner (CP) playbook with builders · Day-by-day 100-day plan (24 Nov 2026 – 3 Mar 2027)</p></div>

<h2>1. The overall plan on one page</h2>
<table>
<tr><th style="width:24%">What we are</th><td><b>Skyline Realty — Chennai and Bangalore's AI-powered home advisor.</b>
Buyers get honest, fast, curated options and are looked after until registration. Builders get qualified buyers,
price discipline and weekly market intelligence.</td></tr>
<tr><th>Who we sell to</th><td>Salaried IT and professional families aged 28–45 buying a first home or upgrading,
budget ₹60 L–₹1.5 Cr. Second: NRIs from Tamil Nadu and Karnataka buying back home.</td></tr>
<tr><th>Where</th><td>Chennai and Bangalore only, in 2–3 focus micro-markets per city (chosen on day 2). Nothing
outside them until Gate 1.</td></tr>
<tr><th>How we earn</th><td>Year 1: builder commission of 2–3% of the agreement value (+18% GST charged to the
builder). Year 2: exclusive mandates at 3.5–5% plus marketing fees. Year 3+: own projects through joint development
(see 10-Year Plan).</td></tr>
<tr><th>How we win</th><td>Every enquiry answered in 5 minutes and followed up until a decision (AI + salesperson).
Only qualified buyers visit. Registration before every visit. Management approves every price. Lowest cost per
booking in the market.</td></tr>
<tr><th>Team, year 1</th><td>You (Chennai, builders) · Wife (Bangalore, finance and compliance) · 1 salesperson per city
by day 45 → 2 per city by month 6 · 1 ops executive by day 100 · site visits hosted by builders' site teams · the AI
system (24×7).</td></tr>
<tr><th>Year-1 target (2027)</th><td><b>120 bookings · ~₹108 Cr sales · ~₹2.8 Cr commission</b> (at ₹90 L average and 2.6%)
· estimated costs ₹1.3–1.6 Cr · profit ₹1.2–1.5 Cr, reinvested.</td></tr>
<tr><th>The ladder</th><td>Year 1 prove the engine → Year 2 exclusive mandates → Year 3–4 first own project (JDA) → Year 6+
platform licensing → Year 10 ₹15,000 Cr sales/yr, ~$1B value, 100% owned.</td></tr>
</table>

<div class="cols">
<div class="keep"><h3>2027 month-by-month bookings (= 120)</h3>
<table><tr><th>Month</th><th>Bookings</th><th>Why</th></tr>{mrows}</table></div>
<div class="keep"><h3>Funnel maths for 10 bookings a month</h3>
<table>
<tr><td>Leads needed</td><td>~800</td></tr><tr><td>Lead → site visit</td><td>10%  → 80 visits</td></tr>
<tr><td>Visit → booking</td><td>12–15% → 10 bookings</td></tr>
<tr><td>Commission earned</td><td>10 × ₹2.25 L ≈ ₹22.5 L</td></tr>
<tr><td>Marketing cap (30%)</td><td>≤ ₹6.75 L / month</td></tr></table>
<p><small>Leads come from Meta ads, portals, Click-to-WhatsApp, referrals, landing pages and corporate tie-ups. Raise
spend only while cost per booking stays below 30% of earnings per booking (shown on the 10-yr plan page).</small></p>
<h3>Who does what</h3>
<table><tr><td>{tags('Y')}</td><td>Chennai builders, pilots, approvals, Chennai team</td></tr>
<tr><td>{tags('W')}</td><td>Bangalore builders and team, invoices, GST/TDS, CA, compliance</td></tr>
<tr><td>{tags('S')}</td><td>Calls within 15 min, visits, closing, visit reports</td></tr>
<tr><td>{tags('A')}</td><td>Replies, qualification, follow-ups, reminders, strategy</td></tr>
<tr><td>{tags('C')}</td><td>Inventory uploads, set-up, proposals, system changes</td></tr></table></div>
</div>
</div>

<!-- ============ PAGE: BUDGET + KPI ============ -->
<div class="page">
<h2>2. 100-day budget (estimates; get real quotes)</h2>
<table>
<tr><th>Item</th><th>100 days</th><th>Notes</th></tr>
<tr><td>Meta ads (lead ads + Click-to-WhatsApp)</td><td>₹3.5–5 L</td><td>₹2,000–2,500/day from 16 Dec, up to ₹3,500–4,000/day only if the 30% rule holds</td></tr>
<tr><td>Portals (99acres / MagicBricks / Housing)</td><td>₹1.5–3 L</td><td>3-month trial packages for focus localities; negotiate</td></tr>
<tr><td>Salespeople (2) — fixed</td><td>₹1.5–2 L</td><td>₹25–35k/month each</td></tr>
<tr><td>Sales incentives</td><td>₹2–3 L</td><td>₹10–15k per booking (or 0.1–0.15% of deal value)</td></tr>
<tr><td>Free cab pickup for site visits</td><td>₹0.6–1 L</td><td>~₹1,000 per visit for about half the visits; lifts the visit rate</td></tr>
<tr><td>CA, legal, CP agreements, Pvt Ltd groundwork</td><td>₹0.75–1.5 L</td><td></td></tr>
<tr><td>Brand: cards, standee, one-pager, video shoots</td><td>₹0.3–0.5 L</td><td></td></tr>
<tr><td>AI + hosting + WhatsApp messages</td><td>₹0.4–0.6 L</td><td>Claude ~₹10–25k/month at current volume</td></tr>
<tr><td>Contingency</td><td>₹1 L</td><td></td></tr>
<tr><th>Total</th><th>₹11.5–17.5 L</th><th>Plus keep a <b>₹10 L working-capital buffer</b>: commissions arrive 30–90 days after booking.</th></tr>
</table>

<h2>3. Weekly scorecard — cumulative targets</h2>
<table><tr><th>Week</th><th>Builders met</th><th>Empanelled</th><th>Projects live</th><th>Leads</th><th>Site visits</th><th>Bookings</th></tr>{kpi}</table>
<div class="ok"><b>Day-100 targets:</b> 16 builders empanelled (8 per city) · 30 projects live · ~1,850 leads · ~150 site
visits · <b>15–20 bookings</b> (≈ ₹35–45 L commission earned) · 2 pilots running · 1 preferred-partner deal · WhatsApp
live · 2 salespeople + ops executive hired · Pvt Ltd plan fixed with the CA.</div>

<div class="keep"><h3>Daily rhythm (from day 23)</h3>
<table>
<tr><td style="width:18%">9:00</td><td>Salespeople open their portal: overdue calls first, then today's tasks and drafts. Founders read the morning digest.</td></tr>
<tr><td>9:30–13:00</td><td>Calls: new leads within 15 minutes, visit confirmations, follow-ups.</td></tr>
<tr><td>14:00–18:00</td><td>Weekdays: visits / builder meetings. <b>Weekends are visit days</b>; the team's weekly off is Tuesday.</td></tr>
<tr><td>Same day</td><td>Visit report filled for every visit; approvals answered within 1 hour (the AI waits for you).</td></tr>
<tr><td>Monday</td><td>Founders' review (30–45 min): 10-yr plan page, Reports, Gate-1 weakest line, ad budget moves.</td></tr>
<tr><td>Wednesday</td><td>Weekly report to every builder.</td></tr>
</table></div>

<div class="warn"><b>Local calendar that drives sales (verify the exact dates each year):</b>
<ul><li><b>Margazhi (mid-Dec → mid-Jan)</b> is seen by many Tamil families as a poor month to buy: use it for visits and
pipeline, and close from Thai (mid-January).</li>
<li><b>Feb–Mar:</b> builders push for financial-year-end targets, the best time to ask for offers and higher slabs.</li>
<li><b>Aadi (mid-Jul → mid-Aug)</b> is slow in Tamil Nadu.</li>
<li><b>Navratri / Dussehra / Diwali</b> are the peak.</li></ul></div>
</div>

<!-- ============ PAGE: CP PLAN — STRATEGY ============ -->
<div class="page">
<h2>4. CP plan with builders — the strategy</h2>
<p>Most channel partners are one of 100–300 brokers a builder works with, competing on discounts. <b>Skyline's plan is to
become the builder's most reliable sales partner in each focus market, then convert that into preferred and exclusive
deals.</b> We earn that with data, not discounts.</p>

<h3>The four relationship tiers</h3>
<table>
<tr><th style="width:17%">Tier</th><th>What it is</th><th style="width:20%">Typical terms*</th><th style="width:24%">How to reach it</th></tr>
<tr><td><b>1 · Empanelled CP</b></td><td>Standard CP agreement; we can bring buyers to the project.</td><td>2–3% of agreement value</td><td>Empanelment kit + meeting (week 2–4)</td></tr>
<tr><td><b>2 · Pilot</b></td><td>60-day focused push on one slow tower or configuration, with targets both sides.</td><td>+0.5% slab above target, priority holds</td><td>After first bookings with the builder (day 55–70)</td></tr>
<tr><td><b>3 · Preferred partner</b></td><td>Priority inventory, volume slabs, co-funded marketing, early access to launches.</td><td>3–3.5% slabs + co-marketing</td><td>Pilot delivered; ~4+ bookings/month with them</td></tr>
<tr><td><b>4 · Exclusive mandate</b></td><td>Sole sales and marketing for a phase or launch; input on pricing; pre-launch EOIs from our demand book.</td><td>3.5–5% + marketing retainer</td><td>Year 2: ≥25% of the project's monthly sales come from us</td></tr>
</table>
<p><small>*Typical ranges for mid-segment projects; real terms vary by builder and project. Never put your own money into
bulk inventory purchases in years 1–2.</small></p>

<h3>Which builders to approach — scorecard (out of 100; approach only at 65+)</h3>
<table>
<tr><th>Must pass (else skip)</th><td colspan="2">RERA-registered project with approvals · no stalled construction · no serious complaints on the RERA page · will sign a written CP agreement · asks for no deposit or fee for empanelment</td></tr>
<tr><td>Delivery track record (past projects on time)</td><td>20</td><td rowspan="7" style="width:38%"><small><b>How to check:</b> RERA project page (quarterly progress, complaints), visit 1 completed project and talk to residents, ask 2 other CPs about payouts, Google reviews, site visit to see actual progress vs the RERA schedule.<br><br><b>Mix to aim for per city:</b> 2–3 "anchor" builders (strong brand, steady demand) for credibility, plus 4–5 mid-size builders with slow inventory (where pilots and higher slabs come from).</small></td></tr>
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
<li><b>Term, termination, jurisdiction</b> (Chennai / Bangalore courts)</li>
</ol>
<div class="warn"><b>Red flags, walk away:</b> fee or deposit for empanelment · project not RERA-registered · stalled
site · reports of delayed CP payouts · builder wants buyer details before agreeing to protect your registration ·
"commission only after the full payment".</div>
</div>

<!-- ============ PAGE: APPROACH + SCRIPTS ============ -->
<div class="page">
<h2>5. How to approach builders</h2>
<div class="cols">
<div class="keep"><h3>Ways in, best first</h3><ol>
<li><b>Warm introduction</b>: bankers (home-loan managers know every builder), architects, other CPs, friends in the
industry. Best response rate.</li>
<li><b>Walk into the project sales office</b> and ask for the CP manager. Weekday mornings are quiet; weekends are busy.</li>
<li><b>CP meets and launch events</b>: builders invite CPs at launches. Get added to each builder's CP WhatsApp group.</li>
<li><b>CREDAI chapters and property expos</b> in Chennai and Bangalore: meet many builders in one day.</li>
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
channel partner (TN: <i>[no.]</i> · KA: <i>[no.]</i>) focused on <i>[micro-markets]</i>. What we offer partners: replies to
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
<h2>6. Objections, pilot and mandate</h2>
<h3>Handling builder objections</h3>
<table>
<tr><th style="width:30%">They say</th><th>You say</th></tr>
<tr><td>"We already have 200 CPs."</td><td>"That's why we focus on qualified buyers and reporting, not volume of brokers. Judge us on bookings in 60 days. There's no cost to you unless we deliver."</td></tr>
<tr><td>"You're a new company."</td><td>"New firm, experienced founders, RERA-registered in both states. Our system answers every buyer in 5 minutes. Let our first 60 days speak; you lose nothing by empanelling us."</td></tr>
<tr><td>"Commission is fixed at 2%."</td><td>"Agreed for now. Can we add a slab if we cross 3 bookings a quarter? It only costs you when we outperform."</td></tr>
<tr><td>"CPs give away commission as discount."</td><td>"Not us. Every price is approved by management, and we can put no-discount-passing in the agreement."</td></tr>
<tr><td>"Payout only after full registration."</td><td>"Can we split it: 50% at agreement registration and 50% at 20% collection? That keeps us both aligned."</td></tr>
<tr><td>"Send the buyer, we'll see."</td><td>"Happy to. We just need the registration ACK before the visit, so there's never a dispute. It protects your team's time too."</td></tr>
<tr><td>"No exclusive deals."</td><td>"Not asking for one now. Let's start with a 60-day pilot on one tower; exclusivity only if the numbers justify it."</td></tr>
<tr><td>"How do I know you won't take our buyers elsewhere?"</td><td>"A registered buyer stays registered with you, and we show you every registered buyer's status in the weekly report."</td></tr>
</table>

<h3>The 60-day pilot proposal (one page to hand over, from day 59)</h3>
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
<tr><td>Weekly (Wed)</td><td>Report: registered buyers, visits, feedback, bookings, payments due</td></tr>
<tr><td>Monthly</td><td>15-minute call with the sales head: what's slow, new offers, upcoming launches</td></tr>
<tr><td>Each booking</td><td>Invoice on the trigger date; chase from day 31 (the system reminds you every Monday)</td></tr>
<tr><td>Quarterly</td><td>Slab review: show your numbers, ask for the next slab or tier</td></tr>
</table>
</div>

<!-- ============ PAGES: 100 DAYS ============ -->
<div class="page">
<h2>7. The 100-day plan — day by day</h2>
<p><small>Shading: <span style="background:#fff7d6;padding:0 2mm">weekly review</span>
<span style="background:#f6f8fb;padding:0 2mm">weekend (visit days)</span>
<span style="background:#f3f0ff;padding:0 2mm">holiday</span>. Owners: {tags('YWSAC')}. If you fall behind, keep the
Monday review and the "done when" column honest; push dates, don't skip steps.</small></p>
<table class="days"><thead><tr><th>Day</th><th>Date</th><th>Focus</th><th>Tasks</th><th>Who</th><th>Done when</th></tr></thead>
{rows}
</table>
</div>

<div class="page">
<h2>8. After day 100 — what success unlocks</h2>
<table>
<tr><th style="width:30%">If by day 100…</th><th>Then in days 101–200…</th></tr>
<tr><td>15+ bookings and cost per booking ≤ 30% of earnings</td><td>Raise ads gradually, hire salesperson #3–4, add 1 micro-market per city</td></tr>
<tr><td>A pilot hit its target</td><td>Convert it to preferred partner; start a second pilot per city</td></tr>
<tr><td>Fewer than 10 bookings</td><td>Don't increase spend. Check the weakest funnel step (contact speed? visit rate? visit → booking?) and fix it first</td></tr>
<tr><td>One builder is more than 40% of commission</td><td>Push the second and third builders in that micro-market</td></tr>
<tr><td>Commission is collected late</td><td>Tighten payout terms in renewals; prefer builders who pay on time</td></tr>
</table>
<div class="cover" style="margin-top:4mm"><h1 style="font-size:13pt">The 100-day promise</h1>
<p>By 3 March 2027: 16 builders signed, 30 projects live, WhatsApp live, a 2-city team, 15–20 bookings, 2 pilots and a
first preferred deal. That's the proof you need to start Year 2's exclusive mandates.</p></div>
</div>
</body></html>"""
open(f"{ROOT}/docs/100-day-plan.html", "w").write(html)
print("ok")
