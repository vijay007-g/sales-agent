# Skyline Realty — AI + human sales system (own projects + channel partner)

An AI sales assistant works alongside your human sales team:

- **Salespeople (relationship managers)** phone the customer at every stage.
- **The AI** writes the WhatsApp messages in that salesperson's name, from their number. It also plans every
  call with a brief, analyses site visits, builds a conversion strategy for each lead, and makes sure no lead
  goes quiet.
- **The site person** shows the site and fills a 2-minute visit report on their phone.
- **Management** approves every price change, confirms bookings, and records the advance payment.
- **The system learns** every week from won and lost deals and feeds that back into messages, calls and new
  ad campaigns.

```
Lead sources ─► NEW ─► CONTACTED ─► QUALIFIED ─► VISIT SCHEDULED ─► VISIT DONE ─► NEGOTIATION ─► BOOKING PENDING ─► PAYMENT PENDING ─► BOOKED
(ads, portals,  📞 intro   📞 needs      📞 confirm      Site person:     AI: strategy    every price     Management:       AI: official bank      Management:
 website,       call +     + visit       visit          visit report     📞 post-visit   needs approval  CONFIRM B<n>      details or office      PAID B<n>
 walk-ins,      message    invitation                   form             call            📞 offer call                     visit 📞 payment call  (money received)
 referrals)
                └─ quiet leads: calls + messages alternate on a fixed cadence ─► NURTURE ─► LOST (reason recorded)
```

## AI only, or AI + people?
**AI + people.** A flat is one of the biggest purchases a family makes. In India, buyers expect to speak to a
person, decisions are made by several family members, and price talks happen on the phone. Message-only
selling works for capturing and qualifying leads, reminders and follow-up discipline, where it is excellent.
Trust, objections and closing need a voice. So here:

| AI does | People do |
|---|---|
| Instant reply to every lead, 24×7 | Intro call within 10 minutes |
| Writes messages in the salesperson's voice, from their number | Every call at every stage (the AI writes a brief for each) |
| Remembers every detail; never forgets a follow-up | Site visit (site person) |
| Turns the visit report into a conversion strategy | Price decisions, booking confirmation, payment check (management) |
| Learns what works, writes campaigns | Approves campaigns and AI drafts (review mode) |

The customer only ever deals with **one person**: their salesperson calls them, and messages come from that
same salesperson's WhatsApp, continuing what was said on the call ("as we discussed…"). If a customer asks
whether they're talking to a bot, the AI answers honestly: the salesperson uses an assistant for messages and is
personally handling their enquiry. It then sets up a call.

## Stage by stage
| Stage | What happens |
|---|---|
| **Creating leads** | `Campaigns` writes Meta/Google ads, lead forms, WhatsApp templates, social posts, a 2-week content calendar, referral offers and bigger creative ideas (corporate tie-ups, NRI webinars, events…). It draws on the learned playbook and on which ad variants actually produced bookings. Each ad variant gets a tracking code (`C3-V2`); pass it as `campaign` in the lead webhook, and the Reports page shows which variant produced visits and bookings. Drafts wait for your approval. |
| **Capturing leads** | `POST /webhook/lead` (website, ad platforms via Zapier/Make, portals), CSV import, or walk-ins added on the dashboard. Duplicates merged; each lead is scored 0–100 and assigned to the salesperson with the lightest load. |
| **First contact** | A short, natural WhatsApp from the salesperson's number within seconds, plus a 📞 intro call task due in 10 minutes. The task arrives on the salesperson's WhatsApp with a brief and a one-tap call-log form. |
| **Calls** | Every call task has a 30-second brief: context, the one goal of the call, talking points, likely objections and suggested answers. After the call the salesperson taps the form link (or replies `CALLED C12 <notes>`). The AI updates the lead and sends a WhatsApp that continues the call. Missed calls get a "tried calling you" message and a retry at a different time. Overdue calls are chased. |
| **Site visit** | The AI offers two specific slots, books the site person and sends them the customer details plus the **visit report form** link (attended, who came, decision maker, units shown, liked, concerns, specific requirements, budget, financing, timeline, competitors, price reaction, interest, next step). Reminders go to the customer 24h/2h before, and the site person is nudged until the report is in. |
| **After the visit** | The AI analyses the report together with all calls and messages, and writes a **conversion strategy**: motivators, each objection with an answer, recommended unit, who decides, price plan (requests only, which need approval), dated next actions, and the main risk. It's sent to the salesperson and followed in every later message and call brief. |
| **Follow-ups** | Regular and consistent per stage. Every touch adds something new and pushes one step toward booking. Calls and messages alternate. After 5 unanswered attempts the lead moves to a 2-weekly nurture. |
| **Negotiation** | **Every** discount or extra goes to management **before** the customer hears it (`APPROVE` / `COUNTER` / `REJECT`). **Unit area is fixed**: area concessions are blocked in code. Floor prices are never visible to the AI. Approved prices are presented on a call first, then confirmed in writing. |
| **Booking** | Customer agrees → management `CONFIRM B5` → the AI sends the **official company bank details** (fixed text from config, never typed by the AI) and offers an **office visit** slot for paying in person. Payment call planned. When the customer says "paid", management is alerted to check the bank. Only `PAID B5 2L UTR123` marks the flat **booked**. |
| **Learning** | Weekly (or on demand) the system studies won vs lost leads: conversations, call notes, visit reports, offers, how salespeople rewrote AI drafts, and conversion by source and ad variant. It produces a playbook (what works in messages and on calls, the best answer to each objection, who converts, what to stop, new campaign ideas, experiments). The playbook is used in every message, call brief and campaign. |

## Channel partner: inventory, matchmaking, commission protection
- **Inventory** (dashboard → Inventory): your own company and every **partner builder** (commission %, payment terms,
  contact for client registration, and their bank account for customers' advance). Projects in any city
  (Chennai, Bangalore, …) with a site host (your staff or the builder's site team), and **units** — one row per flat
  (A-504, 5th floor, East) or one row per type with a count when a builder only shares numbers. Upload a CSV saved
  from Excel (template on the page; prices like 75L / 1.2cr). Floor prices are never visible to the AI.
- **Matchmaker:** the AI searches all live inventory by the buyer's city, budget, size, locality and possession
  (`search_properties`), recommends the best 2–3 real units with reasons, and quotes details only from
  `get_project_details`. Held and booked units disappear from search automatically.
- **Client registration:** before every site visit to a partner project, the buyer is registered with that builder
  in writing (WhatsApp + email, timestamped, "R12"). The builder replies `ACK R12` or `DISPUTE R12 <reason>`
  (you're alerted on disputes). Registrations renew automatically before expiry while the buyer is active.
  Pages: Registrations; each lead shows its registrations and a "Register with builder" button.
- **Commission ledger:** when the advance is paid on a partner unit, a commission entry is created (deal value ×
  builder's %, or fixed), due by the builder's payment terms. Mark Invoiced / Received / Dispute on the
  Commissions page; overdue amounts are in the morning summary and a Monday reminder.
- **Payments go to the right account:** for partner projects the AI sends the **builder's** official bank details
  (fixed text from the builder's record); for your own projects, your company account from Settings.
- **City routing:** set "Cities they handle" for each salesperson in Settings; leads from that city go to them.
- **AI disclosure:** the AI introduces itself as "Skyline Realty's assistant, working with <salesperson>" in the first
  message, never pretends to be a person, and arranges a human immediately on request. Change the wording in
  Settings → "How the AI introduces itself".

## Sales kit, landing pages, marketing spend
- **Brochures, floor plans, photos:** upload per project on its Inventory page (PDF ≤ 16 MB, images ≤ 5 MB). The AI
  sends them as WhatsApp attachments (`send_brochure`); in review mode they go to the salesperson as drafts first.
- **Cost sheets:** set GST %, stamp duty %, registration % and other charges ("Car parking: 3L") per project. The AI
  sends an exact cost sheet (`send_cost_sheet`) using the list price — or the price management approved for that
  buyer — and never types figures itself.
- **EMI illustrations:** `send_emi_illustration`, calculated by code with the rate, tenure and down payment from
  Settings → Messaging & loan illustrations; always labelled illustrative.
- **Landing pages:** every project has a public, phone-friendly page at `/p/<project>` and there's an all-projects
  page at `/enquire?city=Chennai`. Use them as ad destinations with `?src=meta_ads&c=C3-V2`. The form records consent
  (exact wording, time and page) for India's DPDP rules, filters spam (hidden field + 5 per hour per connection),
  and hands the lead to the AI instantly. A privacy page is at `/privacy`.
- **Marketing spend:** Reports → enter monthly spend per channel (and per campaign code). The tables show leads,
  qualified, visited, booked and **cost per lead / qualified lead / visit / booking**, plus commission earned —
  so spend goes up only where bookings justify it. The weekly learning also sees these numbers.
- **Trial inventory:** Inventory → "Load sample inventory" adds four sample projects (Chennai and Bangalore, own and
  partner) with units and charges; "Remove sample inventory" deletes them before go-live.

## Team portals, call discipline, visit reminders, silent buyers
- **Team page** (dashboard → Team): each salesperson and site team member gets a personal link — no password. Send it
  on WhatsApp; they tap "Add to Home screen" and it works like an app. "New link" revokes the old one.
- **Salesperson portal** (`/s/<link>`): a lobby with calls to make now (overdue flagged), messages to approve,
  upcoming visits and all their buyers. Each buyer has a **path to booking** (intro call → needs → visit booked →
  confirmation call → visit → post-visit call → price → booking → advance) with the current step highlighted, the AI's
  call brief, Call / WhatsApp buttons and a one-tap call log. Salespeople only see their own buyers.
- **Site team app** (`/site/<link>`): today's and upcoming visits and reports due. Each visit has steps: confirm with the
  customer → customer arrived → show the right homes → fill the report. "Confirmed" and "Arrived" notify the
  salesperson instantly.
- **Call discipline:** heads-up 15 min before each call, positive nudges 20 and 60 min after it's due, and management
  is told if a call is still not done after 3 hours.
- **Visit reminders to everyone:** buyer, site coordinator and salesperson the day before and 2 hours before; the
  salesperson automatically gets a confirmation-call task the day before; missing visit reports are chased.
- **When a buyer goes quiet:** 1) a useful WhatsApp with one easy question → 2) reconnect call → 3) a WhatsApp with
  something new → 4) another call at a different time of day → 5) a polite "reply 1 to continue, 2 to pause" → nurture
  (a useful update every 2 weeks; warm buyers also get a periodic check-in call). Any reply restarts the conversation.

## Automatic lead sources (dashboard → Lead sources)
- **Meta lead ads:** subscribe your Page's `leadgen` webhook to `/webhook/meta`; set `META_VERIFY_TOKEN`,
  `META_APP_SECRET`, `META_PAGE_TOKEN` in Railway. Leads arrive in seconds with the ad/campaign name (put `C3-V2` in ad
  names), duplicates from Meta retries are ignored.
- **Click-to-WhatsApp ads:** nothing extra once WhatsApp is connected — the lead is tagged with the ad and the AI sees
  what the buyer clicked.
- **Portal emails:** a dedicated mailbox (`LEADS_IMAP_USER`, `LEADS_IMAP_PASSWORD`, optional `LEADS_IMAP_HOST`) is
  checked every 2 minutes; 99acres / MagicBricks / Housing / NoBroker / SquareYards… enquiries become leads. Or POST
  forwarded emails to `/webhook/portal-email`.
- **Ad spend:** Meta spend per campaign is pulled every morning (`META_AD_ACCOUNT_ID`, `META_ADS_TOKEN` with ads_read);
  Google Ads spend via CSV upload on the Lead sources page.

## WhatsApp commands
```
Management:  APPROVE 7 | REJECT 7 <note> | COUNTER 7 97.5L <note> | CONFIRM B3 | HOLD B3 <note>
             PAID B3 2L UTR12345 | PAUSE 15 | RESUME 15 <note> | STATUS | LEAD 15
Salesperson: TASKS | CALLED C12 <what happened> | NOANSWER C12 | SEND D4 | EDIT D4 <your text> | DROP D4
Site person: TODAY | VISITED 9 hot <notes> | NOSHOW 9      (or the full visit-report form link)
Builder:     ACK R12 | DISPUTE R12 <reason>                  (client registration replies)
```
In **review mode** (`message_mode: review`, recommended for the first weeks), every AI message comes to the
salesperson as a draft: `SEND D4`, or `EDIT D4 <better text>`. Edits are learned from. Switch to `auto` once
you trust the tone.

## Deploy to the cloud (Railway) — use it from phone, laptop, any device
1. Go to https://railway.com, sign in with GitHub, and pick the Hobby plan.
2. **New Project → Deploy from GitHub repo → `vijay007-g/sales-agent`.** Railway finds the `Dockerfile` and
   builds it.
3. In the service, open **Settings → Volumes → Add volume** and set the mount path to **`/data`**. This is
   where the database, your settings and the message log are kept; without it, data is lost on every redeploy.
4. **Variables** tab, add:
   | Name | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | from console.anthropic.com |
   | `DASHBOARD_PASSWORD` | a strong password (you log in as user `owner`) |
   | `LEAD_WEBHOOK_SECRET` | any long random text |
   | `CHANNEL_MODE` | `console` for now (test mode; nothing reaches customers) |
   | `PUBLIC_BASE_URL` | the address from step 5, e.g. `https://sales-agent-production.up.railway.app` |
5. **Settings → Networking → Generate Domain.** That address is your app. Open it on any device and log in.
6. **Phone:** open the address in Chrome (Android) → menu → *Add to Home screen*, or in Safari (iPhone) →
   Share → *Add to Home Screen*. It opens like an app.
7. Open **Settings** in the app and enter your real projects, prices, floor prices, team and bank details.
8. Open **Test**: create a pretend lead and play the customer, salesperson, site person and management, all
   from your phone.
9. When WhatsApp Business is approved, add `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`,
   `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` and `WHATSAPP_TEMPLATE_NAME`, set `CHANNEL_MODE` to `live`,
   and set the Meta webhook to `<your address>/webhook/whatsapp`.

Keep it at **one replica** (already set in `railway.json`): the database and the follow-up clock run inside
the app. Every push to GitHub redeploys automatically; your data on `/data` is kept.

## Local setup (optional, for developers)
```bash
cd sales-agent
pip install -r requirements.txt
cp config.example.yaml config.yaml   # projects, prices, floors, salespeople, site persons, bank details
cp .env.example .env                 # Claude API key, dashboard password, WhatsApp keys, PUBLIC_BASE_URL
```
Try it in the terminal first. It needs only `ANTHROPIC_API_KEY`, and nothing is really sent:
```bash
python -m salesagent.cli simulate
```
In the simulator you type as the customer, and play the others with `/rm CALLED C1 …`, `/site VISITED 1 hot …`
and `/owner APPROVE 1`.

Run it for real:
```bash
python -m salesagent.cli serve
```
The dashboard is at `PUBLIC_BASE_URL` (user `owner`).
1. **WhatsApp:** set up the WhatsApp Business Cloud API. Add one phone number per salesperson and put each
   number's ID in `sales_team[].whatsapp_phone_number_id`, so the customer sees the same person who calls them.
   Set the webhook to `<PUBLIC_BASE_URL>/webhook/whatsapp`. Create one approved template with a `{{1}}` body
   variable (`WHATSAPP_TEMPLATE_NAME`); it is used for follow-ups sent more than 24h after the customer's last
   message.
2. **Lead sources:** point them at `POST /webhook/lead` with header `X-Webhook-Secret` and a JSON body such as
   `{"name","phone","email","source","campaign":"C3-V2","budget_max","unit_type","timeline"}`.
3. **Hosting:** any small server with HTTPS. Back up `data/`.

Other commands: `campaign "<project>" "<channel>" --budget 1.5L`, `import leads.csv --source portal --contact`,
`learn`, `digest`, `tick`.

## Safety rails (enforced in code)
- The AI never sees floor prices. Every discount or extra needs management approval first, and below-floor
  asks are blocked.
- Unit area can never be offered or changed.
- Only the site person can mark a visit done. Only management can confirm a booking or mark the advance as
  received.
- Payment details are fixed text from config, sent only after management confirms. Customers are told to
  verify by calling the office and never to pay into a personal account.
- "STOP" opts a customer out instantly, without the AI. Max 3 messages per turn. No proactive messages in
  quiet hours.
- Complaints, anger, legal, refund or RERA questions hand the lead to a person.
- Every action is in each lead's activity log.

## Model and cost
Uses Claude (`claude-opus-5-5`) via the Anthropic API. Routine replies run at medium effort; post-visit
strategy and negotiation run at high effort. Prompts are cached. If the model declines a request, the API
automatically retries on a fallback model (`fallbacks: "default"`). Estimated spend is on the Reports page.

## Compliance
Message only people who enquired or agreed to be contacted. Show your RERA number in ads. Honour opt-outs.
Follow TRAI/DND rules for calls, and India's DPDP Act for personal data. Don't buy or scrape contact lists;
this system deliberately has no cold-messaging or scraping features.

## Tests
```bash
python -m pytest -q    # 65 end-to-end tests with a scripted fake model, no API key needed
```
