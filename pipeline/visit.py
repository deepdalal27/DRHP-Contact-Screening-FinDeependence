"""Mumbai visit invitation (14-16 December 2026) to merchant bankers with a Mumbai office.

One mail per firm, addressed to the Managing Director / Head - Merchant Banking, personalised with the
firm's name and the IPOs we have written to them about. Same letterhead as the fund's other mails;
the fund profile is attached. A WhatsApp version (plain text with WhatsApp formatting) is produced per
firm for sharing by hand.

    python -m pipeline.visit --preview out.html --whatsapp out.txt
    python -m pipeline.visit --send            # needs the Gmail secrets; each firm once
"""
import argparse
import datetime as dt
import html
import json
import time
import urllib.parse
from pathlib import Path

from . import mailer
from .compose import GOLD, MUTED, LINK, LINE, SERIF, SANS, short_name, _join, _digits
from .mumbai_mbs import firms

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "campaigns.json"
CAMPAIGN = "mumbai_visit_dec2026"
SUPPRESS = ROOT / "config" / "suppression.txt"

VISIT = {
    "dates": "Monday, 14 December to Wednesday, 16 December 2026",
    "dates_short": "14 – 16 December 2026",
    "time": "10:00 am – 6:30 pm",
    "duration": "About 45 minutes",
    "venue": "At your office, Mumbai",
    "sponsor": "Mr. Jignesh Shah",
    "reply_by": "Friday, 11 December 2026",
}


def firm_short(name):
    n = short_name(name)
    return n.replace(" Private", "").replace(" Pvt", "").strip()


def deals_line(f):
    cos = [short_name(c) for c in f["deals"]]
    if not cos:
        return None
    if len(cos) > 3:
        return f"{', '.join(cos[:3])} and {len(cos) - 3} other issue{'s' if len(cos) > 4 else ''}"
    return _join(cos)


def compose_visit(f, s):
    e = html.escape
    firm = f["firm"]
    fs = firm_short(firm)
    deals = deals_line(f)
    attn = f"Kind attention: Managing Director / Head – Merchant Banking, {firm}"
    p1 = ("Greetings from Parshwanath Capital Ventures Fund. Further to our recent correspondence with your team, "
          f"I am pleased to share that {VISIT['sponsor']}, Sponsor of the Fund, and I will be in Mumbai from {VISIT['dates']}.")
    p2 = (f"We would value the opportunity to call on you for a brief introductory meeting with the Promoter / Managing Director "
          f"of {fs} or, if more convenient, the Head of your Merchant Banking division.")
    agenda = [
        ("Introduction", "Parshwanath Capital Ventures Fund, a SEBI-registered Category III AIF, and our approach to primary-market participation."),
        ("Your pipeline", "An understanding of your upcoming Mainboard and SME IPO mandates, pre-IPO rounds and QIPs."),
        ("Working together", "A structured engagement for Pre-IPO placements, Anchor and QIB participation, and early sharing of opportunities."),
    ]
    rows = [("Dates", VISIT["dates_short"]), ("Attending", f"{VISIT['sponsor']}, Sponsor  ·  CA Deep Dalal, Fund Manager")]
    book = (f"To book a slot, kindly reply to this email or WhatsApp / call me on {s.get('phone')}, and we will agree a convenient "
            f"time and place over a call. As the available slots are limited, we would be grateful to hear from you by {VISIT['reply_by']}.")
    subject = f"Mumbai visit, 14–16 December 2026 | Request for an introductory meeting – {fs}"
    mail_subject = urllib.parse.quote(f"Meeting slot – {fs} – Parshwanath Capital Ventures Fund")
    reply_href = f"mailto:{s.get('email')}?subject={mail_subject}"
    wa_text = urllib.parse.quote(f"Dear Deep, regarding your Mumbai visit (14-16 Dec 2026): {fs} would like to meet on ")
    wa_href = f"https://wa.me/{_digits(s.get('phone'))}?text={wa_text}"
    prof = s.get("fund_profile") or {}

    # plain text
    t = [attn, "", "Dear Sir / Madam,", "", p1, "", p2, "", "PROPOSED AGENDA"]
    t += [f"  {k}. {h}: {b}" for k, (h, b) in enumerate(agenda, 1)]
    t += ["", "VISIT DETAILS"] + [f"  {k}: {v}" for k, v in rows] + ["", book]
    if prof.get("view_url"):
        t += ["", f"Our fund profile (also attached): {prof['view_url']}"]
    t += ["", "I look forward to meeting you.", "", "Warm regards,", "", s["name"], f"{s['designation']}, {s['fund']}",
          f"On behalf of {VISIT['sponsor']}, Sponsor"]
    t += [f"{k}: {x}" for k, x in [("Email", s.get("email")), ("WhatsApp", s.get("whatsapp")), ("Phone / WhatsApp", s.get("phone")),
                                   ("SEBI Reg. No.", s.get("sebi_registration"))] if x]
    text = "\n".join(t)

    P = f"margin:0 0 14px 0;font-family:{SANS};font-size:14.5px;line-height:1.7;"
    H = (f"margin:24px 0 10px 0;font-family:{SANS};font-size:11.5px;font-weight:700;letter-spacing:1.6px;"
         f"text-transform:uppercase;color:{GOLD};")
    parts = [
        f'<p style="margin:0 0 16px 0;font-family:{SANS};font-size:12.5px;letter-spacing:.3px;color:{MUTED}">{e(attn)}</p>',
        f'<p style="{P}">Dear Sir / Madam,</p>',
        # visit banner
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:4px 0 20px 0">'
        f'<tr><td align="center" style="border-top:1px solid {GOLD};border-bottom:1px solid {GOLD};padding:16px 10px;text-align:center">'
        f'<div style="font-family:{SANS};font-size:11px;letter-spacing:3px;text-transform:uppercase;color:{MUTED}">Mumbai Visit</div>'
        f'<div style="font-family:{SERIF};font-size:24px;font-weight:700;color:{GOLD};margin:6px 0 2px 0">{e(VISIT["dates_short"])}</div>'
        f'<div style="font-family:{SANS};font-size:12.5px;color:{MUTED}">{e(VISIT["sponsor"])}, Sponsor &nbsp;&middot;&nbsp; CA Deep Dalal, Fund Manager</div>'
        f'</td></tr></table>',
        f'<p style="{P}">{e(p1)}</p>',
        f'<p style="{P}">{e(p2)}</p>',
        f'<p style="{H}">Proposed agenda</p>',
    ]
    for k, (h, b) in enumerate(agenda, 1):
        parts.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 8px 0">'
            f'<tr><td width="34" valign="top" style="padding-top:1px"><div style="width:22px;height:22px;line-height:20px;border-radius:12px;'
            f'border:1.5px solid {GOLD};color:{GOLD};text-align:center;font-family:{SANS};font-size:12px;font-weight:700">{k}</div></td>'
            f'<td style="font-family:{SANS};font-size:14.5px;line-height:1.6"><b>{e(h)}.</b> {e(b)}</td></tr></table>')
    parts.append(f'<p style="{H}">Visit details</p>')
    parts.append(
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-top:2px solid {GOLD};border-bottom:2px solid {GOLD}">'
        + "".join(f'<tr><td style="padding:9px 12px 9px 0;font-family:{SANS};font-size:11.5px;letter-spacing:1px;text-transform:uppercase;'
                  f'color:{GOLD};white-space:nowrap;border-bottom:1px solid {LINE};width:120px">{e(k)}</td>'
                  f'<td style="padding:9px 0;font-family:{SANS};font-size:14px;border-bottom:1px solid {LINE}">{e(v)}</td></tr>' for k, v in rows)
        + '</table>')
    parts.append(f'<p style="{P}margin-top:18px">{e(book)}</p>')
    # booking buttons
    btn = (f'border:1.5px solid {GOLD};border-radius:6px;padding:10px 18px;font-family:{SANS};font-size:14px;font-weight:700;'
           f'color:{GOLD};text-decoration:none;display:inline-block')
    parts.append(
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:2px 0 8px 0"><tr>'
        f'<td style="padding:0 10px 8px 0"><a href="{e(reply_href)}" style="{btn}">Reply to book a slot &rarr;</a></td>'
        f'<td style="padding:0 0 8px 0"><a href="{e(wa_href)}" style="{btn}">Book on WhatsApp &rarr;</a></td></tr></table>')
    if prof.get("view_url"):
        parts.append(f'<p style="margin:4px 0 14px 0;font-family:{SANS};font-size:13px;color:{MUTED}">Our fund profile is attached for your reference, '
                     f'and also available <a href="{e(prof["view_url"])}" style="color:{LINK};text-decoration:none">here on Google Drive</a>.</p>')
    parts.append(f'<p style="{P}">I look forward to meeting you.</p>')
    parts.append(f'<p style="{P}margin-bottom:10px">Warm regards,</p>')
    contacts = [("Email", s.get("email")), ("WhatsApp", s.get("whatsapp")), ("Phone / WhatsApp", s.get("phone")),
                ("SEBI Reg. No.", s.get("sebi_registration"))]
    contact_rows = "".join(
        f'<tr><td style="padding:2px 14px 2px 0;font-family:{SANS};font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{GOLD};white-space:nowrap">{e(k)}</td>'
        f'<td style="padding:2px 0;font-family:{SANS};font-size:14px">'
        + (f'<a href="mailto:{e(x)}" style="color:{LINK};text-decoration:none">{e(x)}</a>' if "@" in x else
           f'<a href="https://wa.me/{_digits(x)}" style="color:{LINK};text-decoration:none">{e(x)}</a>' if "WhatsApp" in k else e(x))
        + "</td></tr>" for k, x in contacts if x)
    parts.append(
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0">'
        f'<tr><td valign="top" style="padding:2px 14px 0 0"><img src="cid:pcvf-logo" width="64" height="64" alt="PCVF" style="display:block;border:0;border-radius:32px"></td>'
        f'<td valign="top" style="border-left:2px solid {GOLD};padding:0 0 0 14px">'
        f'<div style="font-family:{SERIF};font-size:19px;font-weight:700">{e(s["name"])}</div>'
        f'<div style="font-family:{SANS};font-size:13px;color:{MUTED};margin:2px 0 2px 0">{e(s["designation"])}, {e(s["fund"])}</div>'
        f'<div style="font-family:{SANS};font-size:12.5px;color:{MUTED};margin:0 0 8px 0">On behalf of {e(VISIT["sponsor"])}, Sponsor</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{contact_rows}</table></td></tr></table>')
    body = "".join(parts)
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
        f'<div style="font-family:{SANS};font-size:11px;letter-spacing:1px;color:{MUTED};margin-top:4px">SEBI Regn. No. {e(s.get("sebi_registration", ""))}</div>'
        f'</td></tr><tr><td style="padding:24px 4px 22px 4px">{body}</td></tr>'
        f'<tr><td style="padding:12px 4px 8px 4px;border-top:1px solid {LINE};font-family:{SANS};font-size:11px;line-height:1.55;color:{MUTED}">'
        f'This email is addressed to a SEBI-registered intermediary for business purposes only and does not constitute an offer or '
        f'solicitation to subscribe to units of the Fund. To stop receiving emails from us, reply with &ldquo;unsubscribe&rdquo;.</td></tr>'
        f'</table></td></tr></table></body></html>')
    return {"subject": subject, "text": text, "html": page, "to": f["to"], "variant": "visit"}


def whatsapp(f, s):
    fs = firm_short(f["firm"])
    deals = deals_line(f)
    prof = (s.get("fund_profile") or {}).get("view_url")
    lines = [
        "*Parshwanath Capital Ventures Fund*",
        f"_SEBI-registered Category III AIF | Regn. No. {s.get('sebi_registration')}_",
        "",
        "Dear Sir / Madam,",
        "",
        "Greetings from Parshwanath Capital Ventures Fund. Further to our recent correspondence with your team, "
        f"I am pleased to share that *{VISIT['sponsor']}* (Sponsor of the Fund) and I will be in *Mumbai from {VISIT['dates_short']}*.",
        "",
        f"We would value a brief introductory meeting with the *Promoter / Managing Director* of {fs} or, if more convenient, the *Head – Merchant Banking*.",
        "",
        "*Agenda:* an introduction to our Fund, your upcoming IPO, pre-IPO and QIP mandates, and how we can work together on Pre-IPO, Anchor and QIB participation.",
        "",
        f"Kindly let me know a convenient day, and we will agree the time and place over a call. We would be grateful to hear from you by {VISIT['reply_by']}.",
    ]
    if prof:
        lines += ["", f"Fund profile: {prof}"]
    lines += ["", "Warm regards,", "*CA Deep Dalal*", "Fund Manager, Parshwanath Capital Ventures Fund",
              f"On behalf of {VISIT['sponsor']}, Sponsor", f"📞 {s.get('phone')} | WhatsApp {s.get('whatsapp')}", f"✉️ {s.get('email')}"]
    return "\n".join(lines)


def targets():
    sup = {x.strip().lower() for x in (SUPPRESS.read_text().splitlines() if SUPPRESS.exists() else []) if x.strip() and not x.startswith("#")}
    return [f for f in firms() if f["mumbai"] and f["to"] and f["to"][0].lower() not in sup]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview")
    ap.add_argument("--whatsapp")
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args(argv)
    st = json.loads((ROOT / "config" / "settings.json").read_text())
    sender = {**st["sender"], "fund_profile": st.get("fund_profile")}
    ts = targets()
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    done = log.setdefault(CAMPAIGN, {})
    print(f"{len(ts)} Mumbai merchant bankers; {len(done)} already invited")
    if args.preview:
        f = next(x for x in ts if len(x["deals"]) >= 2)
        Path(args.preview).write_text(compose_visit(f, sender)["html"])
        print("preview:", f["firm"], f["to"])
    if args.whatsapp:
        Path(args.whatsapp).write_text(json.dumps([{"firm": f["firm"], "phones": f["phones"], "email": f["to"][0],
                                                    "message": whatsapp(f, sender)} for f in ts], indent=1, ensure_ascii=False))
    if not args.send:
        return
    user, pw = mailer.credentials()
    if not (user and pw):
        raise SystemExit("Gmail credentials missing")
    for f in ts:
        key = f["domain"]
        if key in done:
            continue
        mail = compose_visit(f, sender)
        try:
            mid = mailer.send(mail, sender, user, pw)
            done[key] = {"firm": f["firm"], "to": f["to"], "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "message_id": mid}
            LOG.parent.mkdir(exist_ok=True)
            LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False))
            print("  sent", f["firm"], f["to"])
            time.sleep(1.5)
        except Exception as ex:
            print("  FAILED", f["firm"], ex)
    print(f"Invited {len(done)} firm(s) in total.")


if __name__ == "__main__":
    main()
