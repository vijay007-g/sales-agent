"""Generates docs/15-year-plan.html (run: python docs/make_15_year_plan.py .), then render it to PDF.

The capital model is in this file, so the numbers in the document can be re-run when assumptions change.
"""
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."

# ------------------------------------------------------------------ the capital model (₹ Cr)
YEARS = list(range(2027, 2042))
DIST = {2027: 0.8, 2028: 1.5, 2029: 3, 2030: 5, 2031: 8, 2032: 11, 2033: 14, 2034: 18, 2035: 22, 2036: 26,
        2037: 31, 2038: 37, 2039: 44, 2040: 52, 2041: 60}            # post-tax profit of the sales business
AUM = {2027: 0, 2028: 0, 2029: 10, 2030: 25, 2031: 50, 2032: 90, 2033: 150, 2034: 230, 2035: 340, 2036: 480,
       2037: 700, 2038: 1000, 2039: 1400, 2040: 1900, 2041: 2500}     # investor capital (before the plan's 1.3x)
GMV = {2027: 80, 2028: 280, 2029: 600, 2030: 1000, 2031: 1500, 2032: 2100, 2033: 2800, 2034: 3600, 2035: 4500,
       2036: 5400, 2037: 6400, 2038: 7500, 2039: 8600, 2040: 9800, 2041: 11000}  # channel-partner sales value


def run(own_r, aum_scale, dist_scale=1.0, start=7.0, fee_r=0.05):
    own, rows = start, []
    for y in YEARS:
        if y == 2027:
            rows.append({"y": y, "own": own, "pat": DIST[y] * dist_scale, "aum": 0.0, "dev": 0.0})
            continue
        aum = AUM[y] * aum_scale
        pat = own * own_r + aum * fee_r + DIST[y] * dist_scale
        dev = (own * 0.85 + aum) * 1.4
        own += pat
        rows.append({"y": y, "own": own, "pat": pat, "aum": aum, "dev": dev})
    return rows


PLAN = run(0.24, 1.3)
BASE = run(0.18, 0.5, 0.7)
OWN_ONLY = run(0.27, 0.0, 0.0)          # your original idea: ₹7 Cr compounding at 27%, nothing else
OWN_ONLY_18 = run(0.18, 0.0, 0.0)


def cr(v):
    return f"₹{v:,.0f} Cr" if v >= 10 else f"₹{v:,.1f} Cr"


MILESTONES = {
    2027: "Two cities, lean team; 8–10 bookings a month by Q4; own JV project selling; ₹8 Cr capital by December",
    2028: "First own-capital site (₹6–8 Cr, or a plotted layout + a JV); exclusive mandates; Pvt Ltd in place",
    2029: "First project-company investors (₹10–15 Cr); first plotted layout sold out",
    2030: "3 own projects running; demand book of 10,000+ buyers",
    2031: "First own-capital project delivered on the RERA schedule (the track record investors need)",
    2032: "Third city; ₹100 Cr+ investor capital; platform licensed to other builders",
    2033: "Four cities; 10 projects running; in-house construction management",
    2034: "₹300 Cr investor capital; landowners approach Skyline first for JVs",
    2035: "5M sq ft development pipeline; a recognised brand in South India",
    2036: "₹100 Cr+ profit a year; company worth ~₹1,800 Cr",
    2037: "Five to six cities; first investment-fund partner (through a SEBI-registered AIF)",
    2038: "₹1,300 Cr investor capital; ₹10,000 Cr sales a year",
    2039: "Your own capital passes ₹1,000 Cr",
    2040: "₹14,500 Cr sales a year across sales and development",
    2041: "~₹590 Cr profit a year → ~₹8,800 Cr (~$1B) company, 100% owned",
}

ladder = ""
for i, r in enumerate(PLAN):
    y = r["y"]
    ladder += (f"<tr><td>{i + 1}</td><td>{y}</td><td>{cr(GMV[y] + r['dev'])}</td><td>{cr(r['dev']) if r['dev'] else '—'}</td>"
               f"<td>{cr(r['aum']) if r['aum'] else '—'}</td><td>{cr(r['own'] + (1 if y == 2027 else 0))}</td>"
               f"<td>{cr(r['pat'])}</td><td>{cr(r['pat'] * 15)}</td><td>{MILESTONES[y]}</td></tr>")


def pick(rows, y):
    return next(r for r in rows if r["y"] == y)


compare = ""
hand = ""
for y in (2031, 2036, 2041):
    o, b, pl = pick(OWN_ONLY, y), pick(BASE, y), pick(PLAN, y)
    hand += (f"<tr><td><b>{y}</b></td><td>{cr(o['own'])}</td><td>{cr(b['own'])}</td><td><b>{cr(pl['own'])}</b></td>"
             f"<td>{pl['own'] / o['own']:.1f}×</td></tr>")
    compare += (f"<tr><td><b>{y}</b></td><td>{cr(o['pat'] * 15)}</td>"
                f"<td>{cr(b['pat'] * 15)}</td><td><b>{cr(pl['pat'] * 15)}</b></td></tr>")
O42 = 7 * 1.27 ** 15

css = open(f"{ROOT}/docs/workflow.html").read().split("<style>")[1].split("</style>")[0]
css += """
h2 { break-after: avoid; } .keep { break-inside: avoid; } .cover h1 { color: #fff; } body { font-size: 8.9pt; }
.warn { background:#fff8e6; border:1px solid #f0d48a; border-radius:2mm; padding:2mm 3mm; margin:2mm 0; break-inside: avoid; }
.ok { background:#eef8f1; border:1px solid #a9d8b8; border-radius:2mm; padding:2mm 3mm; margin:2mm 0; break-inside: avoid; }
ol, ul { margin: 1mm 0; padding-left: 5mm; } li { margin: 0.5mm 0; } .big { font-size: 10.5pt; }
table.ladder td { font-size: 8pt; padding: 0.8mm 1.4mm; } table.ladder td:nth-child(-n+8) { white-space: nowrap; }
"""

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Skyline Realty — 15-Year Plan</title>
<style>{css}</style></head><body>

<div class="sect">
<div class="cover"><h1>Skyline Realty — 15-Year Plan (2027–2041)</h1><p>From an AI-powered channel partner to a ₹8,800 Cr (~$1B) real-estate company, 100% owned by the two partners · November 2026</p></div>

<h2>1. The goal</h2>
<p class="big"><b>By December 2041: a company worth about ₹8,800 Cr (~$1B at ₹88/$), owned 100% by the two partners.</b>
At about 15× profit (a normal value for a profitable, growing developer) that means <b>about ₹590 Cr profit a year</b>,
from about ₹17,000 Cr of homes sold a year across sales and development.</p>

<div class="warn"><b>Why 15 years, not 10.</b> Keeping 100% means growing only on profits, borrowing and investor money
inside individual projects, never by selling shares in the company. The capital model (section 4) shows this reaches
about $1B in <b>15 years</b>, not 10. The cautious case still reaches about <b>{cr(pick(BASE, 2041)['pat'] * 15)}</b>
(~${pick(BASE, 2041)['pat'] * 15 / 88 * 10:,.0f}M). Every stage is designed to be profitable on its own, so missing
the top target still leaves a large business that you own completely.</div>

<h2>2. Four engines, each funded by the one before</h2>
<table>
<tr><th style="width:23%">Engine</th><th style="width:12%">From</th><th>What it does</th></tr>
<tr><td><b>1 · Sales (channel partner → exclusive mandates)</b></td><td>2027</td><td>The AI + human sales engine: cash every month,
buyer data (the demand book), builder relationships. Later, sole-selling mandates at 3.5–5%.</td></tr>
<tr><td><b>2 · Development with your own capital</b></td><td>End-2027</td><td>₹8 Cr: ₹1 Cr personal, ₹7 Cr into the business
(₹1 Cr held back as a reserve). Land on deferred payment or JV wherever possible; plotted layouts for fast cycles;
pre-selling through Engine 1.</td></tr>
<tr><td><b>3 · Investor capital in project companies</b></td><td>2029</td><td>HNIs, and later investment funds, put 70–80% of each
project's equity into a separate project company. You earn a management fee plus a share of profits above their
agreed return. <b>Your main company stays 100% yours.</b></td></tr>
<tr><td><b>4 · Platform</b></td><td>2032</td><td>The sales system licensed to builders in cities you don't operate in.</td></tr>
</table>

<h2>3. How your own capital works (from end-2027)</h2>
<div class="cols">
<div class="keep"><h3>One typical project (land bought outright)</h3>
<table>
<tr><td>Sales value (~75 flats × ₹65 L)</td><td>₹50 Cr</td><td>100%</td></tr>
<tr><td>Land</td><td>₹10 Cr</td><td>20%</td></tr>
<tr><td>Construction (mostly paid from buyer payments in the RERA account)</td><td>₹22.5 Cr</td><td>45%</td></tr>
<tr><td>Approvals, marketing, interest, overheads</td><td>₹7.5 Cr</td><td>15%</td></tr>
<tr><th>Profit before tax / after tax (~25%)</th><th>₹10 Cr / ₹7.5 Cr</th><th>on ₹7 Cr</th></tr>
</table>
<p>₹7 Cr becomes about ₹14.5 Cr. Per year: <b>27%</b> if the money returns in 36 months, 23% in 42 months, 20% in 48
months. <b>Approval speed and pre-sales decide the return.</b></p></div>
<div class="keep"><h3>The rules that lift the return to ~24% a year</h3><ol>
<li><b>Land ≤ 20% of sales value</b>, bought where the demand book shows buyers waiting.</li>
<li><b>JV or deferred land payments</b> (instalments linked to approvals and sales) whenever possible.</li>
<li><b>Plotted layouts</b> (approved plots in Chennai/Bangalore growth corridors) for about 2-year cycles.</li>
<li><b>Launch within weeks of RERA approval; about 40% sold in 6 months</b>, so buyers fund construction.</li>
<li><b>Never more than about 60% of your capital in one project</b>, and keep the ₹1 Cr reserve.</li></ol>
<p><small><b>Finance facts:</b> banks generally can't fund land purchase by developers. Land loans come from NBFCs or
housing finance companies at about 14–18%, or a loan against property you own. Banks fund construction after
approvals (about 10–12%). Confirm terms with your banker and CA.</small></p></div>
</div>
</div>

<div class="sect" style="page-break-before:always">
<h2>4. The 15-year ladder (plan case)</h2>
<p><small>Plan case: own capital earns 24% a year after tax and is fully reinvested; investor capital grows from ₹13 Cr
(2029) to ₹3,250 Cr (2041), earning Skyline ~5% a year in fees and profit share; sales-business profit grows from
₹0.8 Cr to ₹60 Cr a year; company value = 15 × profit. Bookings from the channel-partner business are on the
dashboard's 15-yr plan page.</small></p>
<table class="ladder"><tr><th>Yr</th><th>Year</th><th>Sales value</th><th>Own development</th><th>Investor capital</th>
<th>Your capital</th><th>Profit</th><th>Value</th><th>Milestone</th></tr>{ladder}</table>

<h2>5. Three paths compared</h2>
<div class="keep"><h3>Capital in hand: money your company actually owns (land, projects, cash), not a valuation</h3>
<table>
<tr><th>End of</th><th>₹7 Cr compounding alone at 27%</th><th>Cautious case</th><th>Plan case</th><th>Plan vs alone</th></tr>
{hand}
</table>
<p><small>₹7 Cr goes in at end-2027, so by Dec 2041 it has compounded for 14 years; 15 full years (Dec 2042) gives
about {cr(O42)}. All profit is assumed reinvested: anything taken out beyond the ₹1 Cr set aside lowers every column.
Most of this capital is always working in projects, so it is not all cash at any one time.</small></p></div>
<div class="keep"><h3>Company value (15 × yearly profit)</h3>
<table>
<tr><th>End of</th><th>₹7 Cr compounding alone at 27%</th><th>Cautious case</th><th>Plan case</th></tr>
{compare}
</table>
<p><small>Cautious case: 18% on own capital, half the investor capital, 70% of the sales-business profit. The jump from
the first column comes from investor capital in project companies plus the sales engine.</small></p></div>
</div>

<div class="sect">
<h2>6. Investor capital in project companies: how it works</h2>
<div class="cols">
<div class="keep"><h3>Structure</h3><ul>
<li><b>Skyline Realty Pvt Ltd</b> (holding company): 100% you and your wife. It owns the brand, the sales engine,
the platform and Skyline's share of every project.</li>
<li><b>One company per project:</b> Skyline puts in 20–30% of the equity; investors put in 70–80%.</li>
<li><b>Typical terms:</b> investors get their money back first plus an agreed return (about 12–14% a year). Above that,
profits are shared, with Skyline getting a larger share (often 20–30% extra, the "promote"). Skyline also earns a
development management fee (about 3–5% of sales).</li>
<li><b>Later (around 2037):</b> a SEBI-registered alternative investment fund (AIF) run with a licensed partner, so
larger investors can join.</li></ul></div>
<div class="keep"><h3>The order to build trust</h3><ol>
<li><b>2027–28:</b> deliver your current JV project well and record every number.</li>
<li><b>2029:</b> first ₹10–15 Cr from people who know you (with written agreements, lawyer-drafted terms and proper
compliance).</li>
<li><b>2031:</b> first own-capital project delivered on time: a full track record.</li>
<li><b>2032–36:</b> HNIs, family offices, NBFC partnerships; quarterly investor reports from the dashboard.</li>
<li><b>2037+:</b> the fund vehicle; institutional co-investors.</li></ol>
<p><small>Raising money from investors is regulated (company law, SEBI rules on public offers and funds). Take legal advice
before every raise. Never advertise for investors without it.</small></p></div>
</div>

<h2>7. Gates: move to the next step only when the current one is proven</h2>
<table>
<tr><th style="width:15%">Gate</th><th>Must be true (from real data)</th><th style="width:26%">Unlocks</th></tr>
<tr><td><b>G1</b> · Dec 2027</td><td>8+ bookings a month for 3 months (both cities) · ads + AI ≤ 30% of earnings per booking ·
₹8 Cr capital ready · Pvt Ltd plan done</td><td>First own-capital site</td></tr>
<tr><td><b>G2</b> · Dec 2028</td><td>Land deal inside the rules (≤ 20% of sales value, deferred/JV where possible) · 2+ exclusive
mandates · 6 months of costs in the bank</td><td>Plotted layout + second project</td></tr>
<tr><td><b>G3</b> · Dec 2029</td><td>First plotted layout sold out · first project 40% pre-sold within 6 months of RERA ·
first investors on lawyer-drafted terms</td><td>3 projects at once</td></tr>
<tr><td><b>G4</b> · 2031</td><td>First own-capital project delivered on the RERA schedule with ≥ 20% a year after tax</td>
<td>Third city, ₹100 Cr investor capital</td></tr>
<tr><td><b>G5</b> · 2034</td><td>₹300 Cr investor capital · 4 cities · no project behind schedule by more than 6 months</td>
<td>Fund partner, 5–6 cities</td></tr>
<tr><td><b>G6</b> · 2038</td><td>₹1,000 Cr+ investor capital · ₹200 Cr+ profit a year</td><td>The final push to 2041</td></tr>
</table>

<div class="cols">
<div class="keep"><h3>Biggest risks and the answer to each</h3><table>
<tr><td style="width:38%">Property downturn</td><td>₹1 Cr reserve, plotted layouts, no single project above ~60% of capital, JVs</td></tr>
<tr><td>Approval delays (the main return killer)</td><td>Buy land with clear titles and approvals in sight; experienced liaison</td></tr>
<tr><td>Expensive land loans</td><td>Deferred land payments first; NBFC loans only for short gaps</td></tr>
<tr><td>Slow sales</td><td>The sales engine pre-sells; build only what the demand book shows buyers want</td></tr>
<tr><td>Depending on you alone</td><td>City heads by 2030, a CFO by 2032, the dashboard as the operating system</td></tr>
</table></div>
<div class="keep"><h3>What we will not do</h3><ul>
<li>Sell shares in the main company (the reason for 15 years)</li>
<li>Put all capital into one site, or buy land without the demand data</li>
<li>Borrow from unregulated lenders or give open-ended personal guarantees</li>
<li>Launch before RERA registration or take more than 10% before a registered agreement</li>
<li>Raise investor money without lawyer-drafted, compliant terms</li></ul></div>
</div>

<div class="cover" style="margin-top:3mm"><h1 style="font-size:13pt">The one-line strategy</h1>
<p>Win buyers more cheaply than anyone with AI. Use that demand to build your own projects fast and safely. Then
let investors fund projects, not the company. Grow only through gates you have proven, and never sell a share.</p></div>
</div>
</body></html>"""
open(f"{ROOT}/docs/15-year-plan.html", "w").write(html)
print("ok", round(PLAN[-1]["pat"]), round(PLAN[-1]["pat"] * 15), round(BASE[-1]["pat"] * 15))
