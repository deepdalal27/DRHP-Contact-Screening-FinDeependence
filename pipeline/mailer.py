"""Compose and send the introduction email.

Recipient order (as instructed):
  1. Promoters' own email IDs, if the DRHP prints them      -> variant "promoter"
  2. otherwise each BRLM's deal contact, asking to connect us -> variant "brlm"
  3. otherwise the company's Company Secretary / IR mailbox   -> variant "company"

Only figures that passed the cross-checks in validate.py are quoted in an email.
"""
import html
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate


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


def compose(rec, fin, sender, msg):
    """Return {subject, text, html} for one recipient group."""
    cover = rec["cover"]
    company = rec.get("display_name") or cover.get("company") or "your Company"
    promoters = cover.get("promoters") or []
    people_promoters = [p for p in promoters if "trust" not in p.lower() and "limited" not in p.lower() and "llp" not in p.lower()]
    board = cover.get("board") or "Mainboard"
    filed_with = "SEBI" if board == "Mainboard" else (rec.get("exchange_filed") or cover.get("exchange") or "the SME platform")
    listing = "the Main Board of BSE and NSE" if board == "Mainboard" else (cover.get("exchange") or "the SME platform") + " (SME platform)"
    doc_date = cover.get("document_date")
    doc_name = cover.get("document_type") or "Draft Red Herring Prospectus"
    biz = (rec.get("business") or {}).get("text")
    if biz and len(biz) > 320:  # keep the quote short: first sentence only
        biz = biz.split(". ")[0]
        if len(biz) > 320:
            biz = None
    hl, fy = highlights(fin)
    pre_ipo = cover.get("pre_ipo_placement")
    limit = cover.get("pre_ipo_limit_pct")

    v = msg["variant"]
    if v == "promoter":
        greet = "Dear " + _join(msg["names"]) + ","
    elif v == "brlm":
        greet = "Dear " + (_join(msg["names"]) if msg["names"] else f"{msg.get('brlm')} team") + ","
    else:
        greet = "Dear " + (msg["names"][0] if msg["names"] else "Investor Relations team") + ","

    s = sender
    fund = s["fund"]
    me = s["name"]
    paras = []
    intro = (f"I am {me}, {s['designation']} of {fund}, {s['fund_type']}.")
    if v == "brlm":
        paras.append(intro + f" I am writing to you as the Book Running Lead Manager to the proposed IPO of {company}.")
    elif v == "company":
        paras.append(intro + f" I am writing in connection with the proposed IPO of {company}.")
    else:
        paras.append(intro)

    filed = f"Congratulations on filing the {doc_name}" + (f" dated {doc_date}" if doc_date else "") + f" with {filed_with}" + \
            f" for the proposed listing on {listing}."
    if v == "brlm":
        filed = f"We have reviewed the {doc_name}" + (f" dated {doc_date}" if doc_date else "") + f" of {company} filed with {filed_with}" + \
                f" for the proposed listing on {listing}."
    paras.append(filed)
    if biz:
        paras.append(f"From the DRHP, we understand the business as follows: “{biz.rstrip('.')}.”")

    hl_intro = f"A few points from the restated financials that stood out to us ({fy}):" if hl else None

    interest = []
    if pre_ipo:
        interest.append(("Pre-IPO placement", "We note that the DRHP contemplates a Pre-IPO Placement"
                         + (f" of up to {limit}% of the Fresh Issue" if limit else "") +
                         ". We would welcome the opportunity to participate in this round."))
    else:
        interest.append(("Pre-IPO round", "Should the Company consider a pre-IPO placement before filing the RHP, "
                         "we would welcome the opportunity to participate."))
    if board == "Mainboard":
        interest.append(("IPO – Anchor / QIB portion", "As a SEBI-registered Category III AIF, we are eligible to bid as a "
                         "Qualified Institutional Buyer, including in the Anchor Investor portion."))
    else:
        interest.append(("IPO – Anchor / QIB portion", "As a SEBI-registered Category III AIF, we are eligible to bid as a "
                         "Qualified Institutional Buyer, including in the Anchor Investor portion of the SME IPO."))

    if v == "promoter":
        ask = ("I would be grateful for a short introductory call or meeting with you and the management team "
               "at your convenience over the coming weeks, to understand the growth plans better.")
    elif v == "brlm":
        pr = _join(people_promoters[:3]) if people_promoters else "the promoters"
        ask = (f"I would be grateful if you could connect us with the promoters of {company} ({pr}), and keep us informed of "
               "the pre-IPO and anchor book discussions. A short introductory call at your convenience would be very helpful.")
    else:
        pr = _join(people_promoters[:3]) if people_promoters else "the promoters"
        ask = (f"I would be grateful if you could forward this email to the promoters ({pr}) and help us connect with them "
               "for a short introductory call at their convenience.")

    close = "I look forward to hearing from you."
    sig = [s["name"], f"{s['designation']}, {fund}"]
    if s.get("fund_type_short"):
        sig.append(s["fund_type_short"])
    if s.get("sebi_registration"):
        sig.append(f"SEBI Registration No.: {s['sebi_registration']}")
    contact = " | ".join(x for x in [s.get("phone"), s.get("email"), s.get("website")] if x)
    if contact:
        sig.append(contact)
    disclaimer = ("This email is for introduction purposes only and does not constitute an offer, solicitation or commitment "
                  "to invest. Any participation will be subject to the Fund's internal due diligence and investment committee "
                  "approval, and to applicable SEBI regulations. If you would prefer not to receive further emails from us, "
                  "please reply with “unsubscribe”.")

    subject = f"Introduction: {fund} (Cat III AIF), interest in the Pre-IPO and IPO of {company}"

    # plain text
    t = [greet, ""]
    for p in paras:
        t += [p, ""]
    if hl:
        t.append(hl_intro)
        t += [f"  • {h}" for h in hl]
        t.append("")
    t.append("We would be keen to explore:")
    for k, (head, body) in enumerate(interest, 1):
        t.append(f"  {k}. {head}: {body}")
    t += ["", ask, "", close, "", "Warm regards,", *sig, "", "—", disclaimer]
    text = "\n".join(t)

    e = html.escape
    navy, teal, ink, muted = "#0E2740", "#2C8F93", "#14273D", "#5D6B7A"
    h = [f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.55;color:{ink};max-width:640px">',
         f"<p>{e(greet)}</p>"]
    for p in paras:
        h.append(f"<p>{e(p)}</p>")
    if hl:
        h.append(f"<p style=\"margin-bottom:4px\">{e(hl_intro)}</p><ul style=\"margin-top:0\">")
        h += [f"<li>{e(x)}</li>" for x in hl]
        h.append("</ul>")
    h.append("<p style=\"margin-bottom:4px\">We would be keen to explore:</p><ol style=\"margin-top:0\">")
    h += [f"<li><b>{e(head)}:</b> {e(body)}</li>" for head, body in interest]
    h.append("</ol>")
    h += [f"<p>{e(ask)}</p>", f"<p>{e(close)}</p>", "<p>Warm regards,</p>",
          f'<table cellpadding="0" cellspacing="0" style="border-left:3px solid {teal};padding-left:10px">'
          f'<tr><td style="padding-left:10px"><b style="color:{navy};font-size:15px">{e(sig[0])}</b><br>'
          + "<br>".join(e(x) for x in sig[1:]) + "</td></tr></table>",
          f'<p style="font-size:11px;color:{muted};margin-top:22px;border-top:1px solid #E2DACA;padding-top:8px">{e(disclaimer)}</p>',
          "</div>"]
    return {"subject": subject, "text": text, "html": "".join(h), "variant": v, "to": msg["to"]}


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
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(gmail_user, gmail_password)
        s.send_message(m, to_addrs=list(mail["to"]) + list(cc) + list(bcc))
    return m["Message-ID"]


def credentials():
    u, p = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    return (u, p) if u and p else (None, None)
