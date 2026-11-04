"""Compose and send the introduction email.

Recipient order (as instructed):
  1. Promoters' own email IDs, if the DRHP prints them      -> variant "promoter"
  2. otherwise each BRLM's deal contact, asking to connect us -> variant "brlm"
  3. otherwise the company's Company Secretary / IR mailbox   -> variant "company"

Only figures that passed the cross-checks in validate.py are quoted in an email.
"""
import html
import os
from pathlib import Path
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate


LOGO = Path(__file__).resolve().parent.parent / "assets" / "pcvf_logo.png"


def crore(v, to_cr):
    x = v * to_cr
    return f"₹{x:,.2f} crore" if abs(x) < 100 else f"₹{x:,.0f} crore"


def pct(x):
    return f"{x * 100:.1f}%"


def _join(names):
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def highlights(fin):
    """Up to four verified, factual data points for the latest full financial year."""
    if not fin or not fin.get("ok") or not fin.get("to_crore"):
        return [], None
    periods = fin["periods"]
    j = next((k for k, p in enumerate(periods) if not p.get("stub")), None)
    if j is None:
        return [], None
    fy = periods[j]["label"]
    items, ratios, to_cr = fin["items"], fin["ratios"], fin["to_crore"]

    def ok_item(k):
        it = items.get(k)
        return it and it["values"][j] is not None and it["status"][j] == "verified"

    def ok_ratio(k):
        r = ratios.get(k)
        return r and r["values"][j] is not None and r["status"][j] == "verified"

    out = []
    if ok_item("revenue"):
        line = f"Revenue from operations of {crore(items['revenue']['values'][j], to_cr)} in {fy}"
        if ok_ratio("Revenue growth") and ratios["Revenue growth"]["values"][j] > 0:
            line += f", up {pct(ratios['Revenue growth']['values'][j])} year-on-year"
        out.append(line)
    if ok_ratio("EBITDA margin") and ratios["EBITDA margin"]["values"][j] > 0:
        out.append(f"EBITDA margin of {pct(ratios['EBITDA margin']['values'][j])}")
    if ok_item("pat") and items["pat"]["values"][j] > 0:
        line = f"Profit after tax of {crore(items['pat']['values'][j], to_cr)}"
        if ok_ratio("RoNW (closing)") and ratios["RoNW (closing)"]["values"][j] >= 0.12:
            line += f" with a return on net worth of {pct(ratios['RoNW (closing)']['values'][j])}"
        out.append(line)
    if ok_ratio("Debt / Equity") and ratios["Debt / Equity"]["values"][j] <= 0.5:
        out.append(f"A conservative balance sheet, with debt-to-equity of {ratios['Debt / Equity']['values'][j]:.2f}x")
    return out, fy


def choose_recipients(rec, suppressed=()):
    """Return list of messages to send: [{variant, to:[...], names:[...], brlm}]"""
    sup = {s.lower() for s in suppressed}
    prom = rec.get("promoter_emails") or {}
    emails = []
    names = []
    for p, lst in prom.items():
        for e in lst:
            if e["email"] not in sup and e["email"] not in emails:
                emails.append(e["email"])
                names.append(p)
    if emails:
        return [{"variant": "promoter", "to": emails, "names": list(dict.fromkeys(names))}]
    out = []
    for b in (rec.get("general") or {}).get("brlms") or []:
        to = [e for e in b.get("emails", []) if e not in sup]
        if to:
            out.append({"variant": "brlm", "to": to[:2], "names": b.get("contact_persons") or [], "brlm": b.get("name")})
    if out:
        return out
    cs = (rec.get("general") or {}).get("cs") or {}
    to = [e for e in cs.get("emails", []) if e not in sup]
    if to:
        return [{"variant": "company", "to": to[:2], "names": [cs["name"]] if cs.get("name") else []}]
    return []


from .compose import compose  # noqa: E402,F401


def send(mail, sender, gmail_user, gmail_password, cc=(), bcc=()):
    m = EmailMessage()
    m["Subject"] = mail["subject"]
    m["From"] = formataddr((sender["name"], gmail_user))
    m["To"] = ", ".join(mail["to"])
    if cc:
        m["Cc"] = ", ".join(cc)
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=gmail_user.split("@")[-1])
    m.set_content(mail["text"])
    m.add_alternative(mail["html"], subtype="html")
    if LOGO.exists():  # the fund logo travels inside the mail (cid:pcvf-logo), so it shows without "load images"
        m.get_payload()[1].add_related(LOGO.read_bytes(), "image", "png", cid="<pcvf-logo>", filename="pcvf_logo.png",
                                       disposition="inline")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(gmail_user, gmail_password)
        s.send_message(m, to_addrs=list(mail["to"]) + list(cc) + list(bcc))
    return m["Message-ID"]


def credentials():
    u, p = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    return (u, p) if u and p else (None, None)
