"""Command line: serve | simulate | campaign | import | learn | digest | tick

    python -m salesagent.cli serve                 # webhooks + dashboard + scheduler
    python -m salesagent.cli simulate              # chat as a customer in the terminal
    python -m salesagent.cli campaign "Sunrise Meadows" "Meta lead ads" --budget 1.5L
    python -m salesagent.cli import leads.csv --source portal
    python -m salesagent.cli learn                 # rebuild the playbook from won/lost leads now
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def cmd_serve(a):
    import uvicorn
    uvicorn.run("salesagent.server:app", host=a.host, port=a.port)


def cmd_simulate(a):
    os.environ["SALESAGENT_SYNC"] = "1"
    os.environ["CHANNEL_MODE"] = "console"
    os.environ.setdefault("SALESAGENT_DB", os.path.join("data", "simulator.db"))
    from . import channels, db, events, leads, scheduler
    from .config import get_settings

    s = get_settings()
    owner = s.owner["phone"]
    site = s.site_persons[0]["phone"] if s.site_persons else owner
    rm = s.sales_team[0]["phone"] if s.sales_team else owner
    if not a.review:
        for r in s.sales_team:
            r["message_mode"] = "auto"   # in the simulator, skip draft approval unless --review
    customer_phone = a.phone

    def show(kind, to, text):
        n = db.normalize_phone(to)
        who = ("OWNER" if n == db.normalize_phone(owner) else "SITE PERSON" if n == db.normalize_phone(site)
               else "SALESPERSON" if n == db.normalize_phone(rm) else "CUSTOMER")
        colour = {"CUSTOMER": "\033[32m", "OWNER": "\033[35m", "SITE PERSON": "\033[36m",
                  "SALESPERSON": "\033[34m"}[who]
        print(f"\n{colour}── → {who} ({kind})\033[0m\n{text}\n")

    channels.CONSOLE_LISTENERS.append(show)
    lead = db.find_lead_by_phone(customer_phone)
    if not lead:
        lead, _ = leads.upsert_lead({"name": a.name, "phone": customer_phone, "source": a.source,
                                     "campaign": "simulator"})
        print(f"Created test lead #{lead['id']} ({a.name}). The AI is making first contact...\n")
        events.new_lead(lead["id"])
    print("Type as the CUSTOMER. Commands:\n"
          "  /rm <cmd>      salesperson, e.g. /rm CALLED C1 spoke, wants east facing 2BHK, visit Sat 11am\n"
          "                 /rm NOANSWER C1   /rm TASKS   /rm SEND D1   /rm EDIT D1 <text>\n"
          "  /site <cmd>    e.g. /site VISITED 1 hot loved the clubhouse, worried about traffic\n"
          "  /owner <cmd>   e.g. /owner APPROVE 1   /owner COUNTER 1 72L   /owner CONFIRM B1   /owner PAID B1 2L UTR123\n"
          "  /followup      pretend the customer went quiet (fires the follow-up now)\n"
          "  /tick          run the scheduler once     /lead   show lead record     /quit\n")
    while True:
        try:
            line = input("\033[33myou> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line.split(" ", 1)[0] in ("/owner", "/site", "/rm") and " " in line:
            who, cmd = line.split(" ", 1)
            reply = events.staff_command({"/owner": owner, "/site": site, "/rm": rm}[who], cmd)
            print(f"\033[35m[system → {who[1:]}]\033[0m {reply}")
        elif line == "/followup":
            events.followup_due(lead["id"])
        elif line == "/tick":
            print(scheduler.tick())
        elif line == "/lead":
            print(json.dumps(db.get_lead(lead["id"]), indent=1, default=str))
        else:
            events.inbound_message(customer_phone, None, line, "whatsapp")


def cmd_campaign(a):
    from .marketing import generate_campaign
    data = generate_campaign(a.project, a.channel, a.brief, a.budget)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_import(a):
    os.environ["SALESAGENT_SYNC"] = "1"
    from . import events, leads
    res = leads.import_csv(a.file, a.source)
    print(f"created {res['created']}, merged {res['merged']}, skipped {res['failed']}")
    if a.contact:
        for lid in res["new_ids"]:
            events.new_lead(lid)


def cmd_learn(a):
    from .learning import learn
    res = learn(force=True)
    print(json.dumps(res, indent=2, ensure_ascii=False) if res else "Not enough data yet.")


def cmd_digest(a):
    from .scheduler import digest
    print(digest())


def cmd_tick(a):
    os.environ["SALESAGENT_SYNC"] = "1"
    from .scheduler import tick
    print(tick())


def main(argv=None):
    p = argparse.ArgumentParser(prog="salesagent")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("serve"); sp.add_argument("--host", default="0.0.0.0"); sp.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    sp.set_defaults(fn=cmd_serve)
    sp = sub.add_parser("simulate"); sp.add_argument("--name", default="Karthik"); sp.add_argument("--phone", default="+919811111111")
    sp.add_argument("--source", default="meta_ads")
    sp.add_argument("--review", action="store_true", help="salesperson approves each AI draft (SEND D<no>)")
    sp.set_defaults(fn=cmd_simulate)
    sub.add_parser("learn").set_defaults(fn=cmd_learn)
    sp = sub.add_parser("campaign"); sp.add_argument("project"); sp.add_argument("channel")
    sp.add_argument("--brief", default=""); sp.add_argument("--budget", default=""); sp.set_defaults(fn=cmd_campaign)
    sp = sub.add_parser("import"); sp.add_argument("file"); sp.add_argument("--source", default="csv_import")
    sp.add_argument("--contact", action="store_true", help="let the AI contact new leads right away")
    sp.set_defaults(fn=cmd_import)
    sub.add_parser("digest").set_defaults(fn=cmd_digest)
    sub.add_parser("tick").set_defaults(fn=cmd_tick)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
