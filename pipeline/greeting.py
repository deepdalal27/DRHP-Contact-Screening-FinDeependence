"""Festive greetings (e.g. Samvat New Year) to everyone the fund has already written to.

One mail per address, personalised with the person's name and the company / companies we wrote
about. Same letterhead and dark-mode-safe colours as the introduction email; no attachment.

    python -m pipeline.greeting --occasion samvat2083 --preview out.html   # render only
    python -m pipeline.greeting --occasion samvat2083 --send               # send (needs Gmail secrets)
"""
import argparse
import datetime as dt
import html
import json
import re
import time
from collections import OrderedDict
from pathlib import Path

from . import mailer
from .compose import GOLD, MUTED, LINK, LINE, SERIF, SANS, short_name, _join, _digits

ROOT = Path(__file__).resolve().parent.parent
OUTREACH = ROOT / "site" / "data" / "outreach.json"
LOG = ROOT / "data" / "greetings.json"
SUPPRESS = ROOT / "config" / "suppression.txt"

OCCASIONS = {
    "samvat2083": {
        "subject": "Wishing you a prosperous Samvat 2083 | Parshwanath Capital Ventures Fund",
        "banner": "Nutan Varshabhinandan",
        "banner_sub": "Happy New Year &middot; Vikram Samvat 2083",
        "wish": ("On the auspicious occasion of the New Year, Vikram Samvat 2083, all of us at Parshwanath Capital "
                 "Ventures Fund extend our warmest wishes to you, your family and your colleagues{at}."),
        "blessing": ("May the year ahead bring good health, happiness and prosperity, and may it be a year of "
                     "successful listings and lasting partnerships."),
    },
}


def recipients():
    """{email: {names, organisation, role, companies}} from every introduction mail actually sent."""
    sup = {x.strip().lower() for x in (SUPPRESS.read_text().splitlines() if SUPPRESS.exists() else [])
           if x.strip() and not x.startswith("#")}
    out = OrderedDict()
    for e in json.loads(OUTREACH.read_text())["entries"]:
        if e.get("status") != "sent":
            continue
        addr = e["email"].strip().lower()
        if addr in sup:
            continue
        r = out.setdefault(addr, {"email": e["email"], "names": [], "organisation": e.get("organisation"),
                                  "variant": e.get("variant"), "companies": []})
        for n in e.get("names") or []:
            if n and n not in r["names"]:
                r["names"].append(n)
        if e.get("company") and e["company"] not in r["companies"]:
            r["companies"].append(e["company"])
    return out


def compose_greeting(r, sender, occ):
    e = html.escape
    o = OCCASIONS[occ]
    s = sender
    firm = r.get("organisation") if r.get("variant") == "brlm" else None
    if r["names"]:
        greet = "Dear " + _join(r["names"][:3]) + ","
    elif firm:
        greet = f"Dear {firm} team,"
    else:
        greet = "Dear Sir / Madam,"
    at = f" at {firm}" if firm else (f" at {r['companies'][0]}" if r.get("companies") else "")
    wish = o["wish"].format(at=at)
    cos = [short_name(c) for c in r["companies"]]
    if r.get("variant") == "brlm":
        rel = (f"It was a pleasure to connect with you regarding the proposed IPO{'s' if len(cos) > 1 else ''} of {_join(cos)}. "
               f"We look forward to working closely with you on {'these' if len(cos) > 1 else 'this'} and on many more opportunities in the year ahead.")
    else:
        rel = (f"It was a pleasure to connect with {_join(cos)} on its proposed IPO. We look forward to staying in touch "
               "and to supporting the Company's journey in the year ahead.")
    contacts = [("Email", s.get("email")), ("WhatsApp", s.get("whatsapp")), ("Phone / WhatsApp", s.get("phone"))]
    contacts = [(k, x) for k, x in contacts if x]
    if s.get("sebi_registration"):
        contacts.append(("SEBI Reg. No.", s["sebi_registration"]))

    text = "\n".join([greet, "", o["banner"] + " | " + html.unescape(o["banner_sub"]).replace("\u00b7", "-"), "",
                      wish, "", o["blessing"], "", rel, "", "Warm regards,", "", s["name"], f"{s['designation']}, {s['fund']}",
                      s.get("fund_type_short", "")] + [f"{k}: {x}" for k, x in contacts])

    P = f"margin:0 0 14px 0;font-family:{SANS};font-size:14.5px;line-height:1.7;"
    contact_rows = "".join(
        f'<tr><td style="padding:2px 14px 2px 0;font-family:{SANS};font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{GOLD};white-space:nowrap">{e(k)}</td>'
        f'<td style="padding:2px 0;font-family:{SANS};font-size:14px">'
        + (f'<a href="mailto:{e(x)}" style="color:{LINK};text-decoration:none">{e(x)}</a>' if "@" in x else
           f'<a href="https://wa.me/{_digits(x)}" style="color:{LINK};text-decoration:none">{e(x)}</a>' if "WhatsApp" in k else e(x))
        + "</td></tr>" for k, x in contacts)
    body = (
        f'<p style="{P}">{e(greet)}</p>'
        # festive banner: gold rules and a centred serif greeting, readable on light and dark backgrounds
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:8px 0 22px 0">'
        f'<tr><td align="center" style="border-top:1px solid {GOLD};border-bottom:1px solid {GOLD};padding:20px 10px;text-align:center">'
        f'<div style="font-family:{SERIF};font-size:13px;letter-spacing:6px;color:{GOLD}">&#10022; &#10022; &#10022;</div>'
        f'<div style="font-family:{SERIF};font-size:27px;font-weight:700;letter-spacing:1px;color:{GOLD};margin:8px 0 4px 0">{o["banner"]}</div>'
        f'<div style="font-family:{SANS};font-size:12px;letter-spacing:2.4px;text-transform:uppercase;color:{MUTED}">{o["banner_sub"]}</div>'
        f'<div style="font-family:{SERIF};font-size:13px;letter-spacing:6px;color:{GOLD};margin-top:8px">&#10022; &#10022; &#10022;</div>'
        f'</td></tr></table>'
        f'<p style="{P}">{e(wish)}</p>'
        f'<p style="{P}">{e(o["blessing"])}</p>'
        f'<p style="{P}">{e(rel)}</p>'
        f'<p style="{P}margin-bottom:10px">Warm regards,</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0">'
        f'<tr><td valign="top" style="padding:2px 14px 0 0"><img src="cid:pcvf-logo" width="64" height="64" alt="PCVF" style="display:block;border:0;border-radius:32px"></td>'
        f'<td valign="top" style="border-left:2px solid {GOLD};padding:0 0 0 14px">'
        f'<div style="font-family:{SERIF};font-size:19px;font-weight:700">{e(s["name"])}</div>'
        f'<div style="font-family:{SANS};font-size:13px;color:{MUTED};margin:2px 0 8px 0">{e(s["designation"])}, {e(s["fund"])} &middot; {e(s.get("fund_type_short", ""))}</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{contact_rows}</table>'
        f'</td></tr></table>')
    page = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light dark">'
        '<meta name="supported-color-schemes" content="light dark"></head><body style="margin:0;padding:0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr><td align="center" style="padding:20px 12px">'
        f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:100%;max-width:640px;border-collapse:collapse">'
        f'<tr><td align="center" style="padding:0 4px 16px 4px;border-bottom:3px double {GOLD};text-align:center">'
        f'<img src="cid:pcvf-logo" width="96" height="96" alt="Parshwanath Capital Ventures Fund logo" '
        f'style="display:block;margin:0 auto 10px auto;border:0;width:96px;height:96px;border-radius:48px">'
        f'<div style="font-family:{SERIF};font-size:24px;font-weight:700;letter-spacing:1.2px;color:{GOLD};line-height:1.25">Parshwanath Capital Ventures Fund</div>'
        f'<div style="font-family:{SANS};font-size:10.5px;letter-spacing:2.2px;text-transform:uppercase;color:{MUTED};margin-top:6px">'
        f'SEBI-registered Category III AIF &middot; Pre-IPO &middot; Anchor &middot; QIB &middot; QIP</div>'
        + (f'<div style="font-family:{SANS};font-size:11px;letter-spacing:1px;color:{MUTED};margin-top:4px">SEBI Regn. No. {e(s["sebi_registration"])}</div>' if s.get("sebi_registration") else "")
        + f'</td></tr><tr><td style="padding:24px 4px 22px 4px">{body}</td></tr>'
        f'<tr><td style="padding:12px 4px 8px 4px;border-top:1px solid {LINE};font-family:{SANS};font-size:11px;line-height:1.55;color:{MUTED}">'
        f'To stop receiving emails from us, reply with &ldquo;unsubscribe&rdquo;.</td></tr>'
        f'</table></td></tr></table></body></html>')
    return {"subject": OCCASIONS[occ]["subject"], "text": text, "html": page, "to": [r["email"]], "variant": "greeting"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--occasion", default="samvat2083", choices=sorted(OCCASIONS))
    ap.add_argument("--preview")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--limit", type=int, default=450)  # Gmail allows about 500 mails a day
    args = ap.parse_args(argv)

    settings = json.loads((ROOT / "config" / "settings.json").read_text())
    sender = {**settings["sender"], "fund_profile": None}  # greetings carry no attachment
    rec = recipients()
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    done = log.setdefault(args.occasion, {})
    todo = [r for a, r in rec.items() if a not in done]
    print(f"{len(rec)} recipients; {len(done)} already greeted; {len(todo)} to send")
    if args.preview:
        r = next((x for x in rec.values() if len(x["companies"]) > 1 and x["variant"] == "brlm"), next(iter(rec.values())))
        Path(args.preview).write_text(compose_greeting(r, sender, args.occasion)["html"])
        print("preview for", r["email"], r["companies"])
    if not args.send:
        return
    user, pw = mailer.credentials()
    if not (user and pw):
        raise SystemExit("Gmail credentials missing")
    sent = 0
    for r in todo[:args.limit]:
        mail = compose_greeting(r, sender, args.occasion)
        try:
            mid = mailer.send(mail, sender, user, pw)
            done[r["email"].lower()] = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "message_id": mid,
                                        "companies": r["companies"]}
            sent += 1
            LOG.parent.mkdir(exist_ok=True)
            LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False))  # saved after every mail: never sent twice
            print("  sent", r["email"])
            time.sleep(1.5)
        except Exception as ex:
            print("  FAILED", r["email"], ex)
    print(f"Sent {sent} greeting(s).")


if __name__ == "__main__":
    main()
