"""The introduction email: wording, financial table and institutional HTML layout.

HTML is table-based with inline styles only, so it renders the same in Gmail, Outlook and
mobile mail apps, in light and dark mode.
"""
import html
import re

# Mid-tone colours chosen to stay readable on white AND on dark-mode backgrounds (contrast >= 3.5:1 on both).
GOLD = "#A07A35"     # headings, rules, fund name
MUTED = "#7B8491"    # secondary text
LINK = "#3B78B8"     # links
LINE = "#B9B2A5"     # table rules (visible on both)
SERIF = "Georgia, 'Times New Roman', Times, serif"
SANS = "'Segoe UI', Helvetica, Arial, sans-serif"


def short_name(company):
    t = re.sub(r"\s*\((?:formerly|earlier)[^)]*\)", "", company or "", flags=re.I)
    t = re.sub(r"\s+(?:Private\s+)?Limited\.?$|\s+Ltd\.?$", "", t.strip(), flags=re.I)
    return t.strip()


def _digits(x):
    return re.sub(r"\D", "", x or "")


def _join(names):
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _third_person_verb(v):
    v = v.lower()
    if re.search(r"(s|sh|ch|x|z|o)$", v):
        return v + "es"
    if re.search(r"[^aeiou]y$", v):
        return v[:-1] + "ies"
    return v + "s"


def summarise_business(text, company):
    """Turn the DRHP's first 'Overview' sentence into one short third-person line about the company."""
    if not text:
        return None
    s = re.split(r"(?<=[a-z0-9\)%”])\.\s+(?=[A-Z“\"(])", text.strip())[0].rstrip(". ")
    s = re.sub(r"\s*\((?:i{1,3}|iv|v|vi{0,3}|[a-h])\)\s*", " ", s)          # (i) (ii) (a)
    s = re.sub(r"\s*\(“[^)]*”\)", "", s)                                  # (“Burma Burma”)
    s = re.sub(r"\s*\((?:the )?“?[A-Z][A-Za-z&\- ]{1,30}”?\)", "", s)    # ("Company"), ("FMEG")
    s = re.sub(r"\s*\((?:Source|Note)[^)]*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    name = short_name(company)
    m = re.match(r"^We\s+(are|were|have|own and operate|own|operate|design|manufacture|provide|offer|develop|"
                 r"specialise|specialize|serve|engage|run|deliver|supply|build|focus|cater|process|produce|trade|market|"
                 r"distribute|export|import|retail|sell)\b", s)
    if m:
        verb = m.group(1)
        rep = {"are": "is", "were": "was", "have": "has", "own and operate": "owns and operates"}.get(verb) or _third_person_verb(verb)
        s = f"{name} {rep}" + s[m.end():]
    elif re.match(r"^Our Company\b", s):
        s = name + s[len("Our Company"):]
    elif not s.lower().startswith(name.lower()[:6]):
        return None  # not a sentence about the company itself: leave it out rather than guess
    s = re.sub(r"\bour\b", "its", s)
    s = re.sub(r"\bOur\b", "Its", s)
    s = re.sub(r"\bwe\b", "it", s)
    words = s.split()
    if len(words) > 32:
        cut = None
        for pat in (r",\s+(?:offering|with|which|through|including|along|primarily|and has|having)\b", r";", r"\s+through\s+"):
            m2 = re.search(pat, s)
            if m2 and 8 <= len(s[:m2.start()].split()) <= 32:
                cut = m2.start()
                break
        if cut is None:
            parts = s.split(",")
            acc = ""
            for part in parts:
                if len((acc + part).split()) > 32:
                    break
                acc = (acc + "," + part) if acc else part
            cut = len(acc) if len(acc.split()) >= 8 else None
        if cut is None:
            return None
        s = s[:cut].rstrip(" ,;")
    return s + "."


# ------------------------------------------------------------------ financial table
TABLE_ROWS = [
    ("item", "revenue", "Revenue from operations", "cr"),
    ("ratio", "Revenue growth", "Growth (YoY)", "pct"),
    ("ratio", "EBITDA", "EBITDA", "cr"),
    ("ratio", "EBITDA margin", "EBITDA margin", "pct"),
    ("item", "pat", "Profit after tax", "cr"),
    ("ratio", "PAT margin", "PAT margin", "pct"),
    ("item", "total_equity", "Net worth", "cr"),
    ("ratio", "RoNW (closing)", "Return on net worth", "pct"),
    ("ratio", "Debt / Equity", "Debt / Equity", "x"),
]


def fin_table(fin, max_years=3):
    """Rows of verified figures only; a cell that did not pass the checks shows '–'."""
    if not fin or not fin.get("ok") or not fin.get("to_crore"):
        return None
    periods = fin["periods"]
    cols = [j for j, p in enumerate(periods) if not p.get("stub")][:max_years]
    stub = [j for j, p in enumerate(periods) if p.get("stub")][:1]
    cols = stub + cols
    if not cols:
        return None
    to_cr = fin["to_crore"]
    rows = []
    for kind, key, label, fmt in TABLE_ROWS:
        src = (fin["items"] if kind == "item" else fin["ratios"]).get(key)
        if not src:
            continue
        cells = []
        for j in cols:
            val, st = src["values"][j], src["status"][j]
            if val is None or st != "verified" or (fmt == "pct" and key.endswith("growth") and periods[j].get("stub")):
                cells.append("–")
            elif fmt == "cr":
                x = val * to_cr
                cells.append(f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}")
            elif fmt == "pct":
                cells.append(f"{val * 100:.1f}%")
            else:
                cells.append(f"{val:.2f}x")
        if any(c != "–" for c in cells):
            rows.append((label + (" (₹ cr)" if fmt == "cr" else ""), cells))
    if len(rows) < 2:
        return None
    heads = []
    for j in cols:
        p = periods[j]
        heads.append(f"{p['label']}*" if p.get("stub") else p["label"])
    return {"heads": heads, "rows": rows, "has_stub": bool(stub),
            "stub_label": periods[stub[0]]["label"] if stub else None}


# ------------------------------------------------------------------ compose
def compose(rec, fin, sender, msg):
    cover = rec["cover"]
    company = rec.get("display_name") or cover.get("company") or "the Company"
    short = short_name(company)
    promoters = cover.get("promoters") or []
    people = [p for p in promoters if not re.search(r"\b(trust|limited|ltd|llp|huf|private|pte|a/s|inc|government|ministry|president|acting|through|corporation|holdings?)\b", p, re.I)]
    board = cover.get("board") or "Mainboard"
    sme = board == "SME"
    filed_with = "SEBI" if not sme else (rec.get("exchange_filed") or cover.get("exchange") or "the Stock Exchange")
    listing = "the Main Board of BSE and NSE" if not sme else f"{cover.get('exchange') or 'the SME platform'}"
    doc_date = cover.get("document_date")
    biz = summarise_business((rec.get("business") or {}).get("text"), company)
    table = fin_table(fin)
    pre_ipo = cover.get("pre_ipo_placement")
    limit = cover.get("pre_ipo_limit_pct")
    s = sender
    fund = s["fund"]
    v = msg["variant"]

    if v == "promoter":
        greet = "Dear " + _join(msg["names"]) + ","
    elif v == "brlm":
        greet = "Dear " + (_join(msg["names"]) if msg["names"] else f"{msg.get('brlm')} team") + ","
    else:
        greet = "Dear " + (msg["names"][0] if msg["names"] else "Investor Relations team") + ","

    when = f" dated {doc_date}" if doc_date else ""
    if v == "promoter":
        opening = (f"Congratulations on filing the Draft Red Herring Prospectus{when} with {filed_with} for the proposed listing of "
                   f"{short} on {listing}. I am {s['name']}, {s['designation']} of {fund}, and I am writing to introduce our Fund "
                   f"and express our interest in participating in {short}'s fund-raise.")
    elif v == "brlm":
        opening = (f"I am {s['name']}, {s['designation']} of {fund}. I am writing to you as the Book Running Lead Manager to the "
                   f"proposed IPO of {company}, whose Draft Red Herring Prospectus{when} has been filed with {filed_with} for listing on {listing}.")
    else:
        opening = (f"I am {s['name']}, {s['designation']} of {fund}. I am writing in connection with the proposed IPO of {company}, "
                   f"following the filing of its Draft Red Herring Prospectus{when} with {filed_with} for listing on {listing}.")

    about_us = s["intro"]
    view = None
    if biz:
        view = biz + (" We have studied the DRHP closely, and the business and its growth trajectory fit well with our investment focus."
                      if table else " We have studied the DRHP closely and the business fits well with our investment focus.")
    elif table:
        view = f"We have studied the DRHP of {short} closely, and the business and its growth trajectory fit well with our investment focus."

    interest = []
    if pre_ipo:
        interest.append(("Pre-IPO placement", "The DRHP contemplates a Pre-IPO Placement" + (f" of up to {limit}% of the Fresh Issue" if limit else "")
                         + ". We would be keen to participate in this round."))
    else:
        interest.append(("Pre-IPO round", "Should the Company consider a pre-IPO placement ahead of the RHP, we would be keen to participate."))
    interest.append(("Anchor Investor portion", "As a SEBI-registered Category III AIF, we qualify as a QIB and would like to be considered for the anchor book" + (" of the SME IPO." if sme else ".")))
    interest.append(("QIB portion", "We would also look to participate in the QIB portion of the IPO."))

    pr = _join(people[:3]) if people else "the promoters"
    if v == "promoter":
        ask = "I would value a short introductory call or meeting with you and the management team at your convenience over the coming weeks."
    elif v == "brlm":
        ask = (f"I would be grateful if you could introduce us to the promoters of {short} ({pr}) and keep us informed as the pre-IPO "
               "and anchor book discussions progress. A short call at your convenience would be much appreciated.")
    else:
        ask = (f"I would be grateful if you could forward this email to the promoters ({pr}) and help us set up a short introductory call "
               "at their convenience.")

    subject = f"{fund} | Pre-IPO & Anchor interest – {company}"
    disclaimer = ("This email is for introduction purposes only and does not constitute an offer, solicitation or commitment to invest. "
                  "Any investment is subject to the Fund's due diligence, investment committee approval and applicable SEBI regulations. "
                  "To stop receiving emails from us, reply with “unsubscribe”.")
    contacts = [("Email", s.get("email")), ("WhatsApp", s.get("whatsapp")), ("Phone / WhatsApp", s.get("phone"))]
    contacts = [(k, x) for k, x in contacts if x]
    if s.get("sebi_registration"):
        contacts.append(("SEBI Reg. No.", s["sebi_registration"]))
    if s.get("website"):
        contacts.append(("Website", s["website"]))

    # ---------------- plain text
    t = [greet, "", opening, "", "ABOUT US", about_us, ""]
    if view:
        t += [f"OUR VIEW ON {short.upper()}", view, ""]
    if table:
        t.append("Key financials (restated, ₹ crore unless stated)")
        w = max(len(r[0]) for r in table["rows"])
        t.append(" " * (w + 2) + "".join(h.rjust(11) for h in table["heads"]))
        for label, cells in table["rows"]:
            t.append(label.ljust(w + 2) + "".join(c.rjust(11) for c in cells))
        if table["has_stub"]:
            t.append(f"* {table['stub_label']}: interim period, not annualised.")
        t.append("Source: restated financial information in the DRHP; EBITDA and ratios computed from it.")
        t.append("")
    t.append("HOW WE WOULD LIKE TO PARTICIPATE")
    t += [f"  {k}. {h}: {b}" for k, (h, b) in enumerate(interest, 1)]
    t += ["", ask, "", "I look forward to hearing from you.", "", "Warm regards,", "", s["name"], f"{s['designation']}, {fund}",
          s.get("fund_type_short", "")]
    t += [f"{k}: {x}" for k, x in contacts]
    t += ["", disclaimer]
    text = "\n".join(t)

    # ---------------- HTML (dark-mode safe)
    # No dark panels with light text and no light panels with dark text: body text takes the mail app's own
    # default colour (black on white, white on dark), and accents use mid-tone gold / slate that read on both.
    e = html.escape
    P = f"margin:0 0 14px 0;font-family:{SANS};font-size:14.5px;line-height:1.65;"
    H = (f"margin:24px 0 8px 0;font-family:{SANS};font-size:11.5px;font-weight:700;letter-spacing:1.6px;"
         f"text-transform:uppercase;color:{GOLD};")
    parts = []
    parts.append(f'<p style="{P}">{e(greet)}</p>')
    parts.append(f'<p style="{P}">{e(opening)}</p>')
    parts.append(f'<p style="{H}">About us</p>')
    parts.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 6px 0">'
                 f'<tr><td style="border-left:3px solid {GOLD};padding:4px 0 4px 16px;font-family:{SANS};font-size:14.5px;line-height:1.65">'
                 f'{e(about_us)}</td></tr></table>')
    if view:
        parts.append(f'<p style="{H}">Our view on {e(short)}</p>')
        parts.append(f'<p style="{P}">{e(view)}</p>')
    if table:
        th = (f"padding:9px 10px;font-family:{SANS};font-size:11.5px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;"
              f"color:{GOLD};text-align:right;border-top:2px solid {GOLD};border-bottom:2px solid {GOLD};")
        td = f"padding:8px 10px;font-family:{SANS};font-size:13.5px;border-bottom:1px solid {LINE};"
        rows_html = []
        for label, cells in table["rows"]:
            rows_html.append(
                f'<tr><td style="{td}text-align:left">{e(label)}</td>'
                + "".join(f'<td style="{td}text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums">{e(c)}</td>' for c in cells)
                + "</tr>")
        note = (f"* {e(table['stub_label'])}: interim period, not annualised. " if table["has_stub"] else "") + \
            "Source: restated financial information in the DRHP; EBITDA and ratios computed from it."
        parts.append(f'<p style="{H}">Key financials <span style="color:{MUTED};letter-spacing:.4px;text-transform:none;font-weight:400">'
                     f'(₹ crore unless stated)</span></p>')
        parts.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 6px 0">'
                     f'<tr><th style="{th}text-align:left">Particulars</th>'
                     + "".join(f'<th style="{th}">{e(h)}</th>' for h in table["heads"]) + "</tr>" + "".join(rows_html) + "</table>")
        parts.append(f'<p style="margin:0 0 6px 0;font-family:{SANS};font-size:11.5px;color:{MUTED}">{note}</p>')
    parts.append(f'<p style="{H}">How we would like to participate</p>')
    for k, (h, b) in enumerate(interest, 1):
        parts.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 8px 0">'
                     f'<tr><td width="34" valign="top" style="padding-top:1px"><div style="width:22px;height:22px;line-height:20px;border-radius:12px;'
                     f'border:1.5px solid {GOLD};color:{GOLD};text-align:center;font-family:{SANS};font-size:12px;font-weight:700">{k}</div></td>'
                     f'<td style="font-family:{SANS};font-size:14.5px;line-height:1.6"><b>{e(h)}.</b> {e(b)}</td></tr></table>')
    parts.append(f'<p style="{P}margin-top:16px">{e(ask)}</p>')
    parts.append(f'<p style="{P}">I look forward to hearing from you.</p>')
    parts.append(f'<p style="{P}margin-bottom:10px">Warm regards,</p>')
    contact_rows = "".join(
        f'<tr><td style="padding:2px 14px 2px 0;font-family:{SANS};font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{GOLD};white-space:nowrap">{e(k)}</td>'
        f'<td style="padding:2px 0;font-family:{SANS};font-size:14px">'
        + (f'<a href="mailto:{e(x)}" style="color:{LINK};text-decoration:none">{e(x)}</a>' if "@" in x else
           f'<a href="https://wa.me/{_digits(x)}" style="color:{LINK};text-decoration:none">{e(x)}</a>' if "WhatsApp" in k else e(x))
        + "</td></tr>" for k, x in contacts)
    parts.append(
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0">'
        f'<tr><td valign="top" style="padding:2px 14px 0 0"><img src="cid:pcvf-logo" width="64" height="64" alt="PCVF" style="display:block;border:0;border-radius:32px"></td>'
        f'<td valign="top" style="border-left:2px solid {GOLD};padding:0 0 0 14px">'
        f'<div style="font-family:{SERIF};font-size:19px;font-weight:700">{e(s["name"])}</div>'
        f'<div style="font-family:{SANS};font-size:13px;color:{MUTED};margin:2px 0 8px 0">{e(s["designation"])}, {e(fund)} &middot; {e(s.get("fund_type_short", ""))}</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{contact_rows}</table>'
        f'</td></tr></table>')

    body = "".join(parts)
    page = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light dark">'
        '<meta name="supported-color-schemes" content="light dark"></head><body style="margin:0;padding:0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
        f'<tr><td align="center" style="padding:20px 12px">'
        f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:100%;max-width:640px;border-collapse:collapse">'
        # letterhead: logo + fund name in gold, gold rules
        f'<tr><td style="padding:0 4px 14px 4px;border-bottom:3px double {GOLD}">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr>'
        f'<td valign="middle" style="padding-right:14px"><img src="cid:pcvf-logo" width="72" height="72" alt="Parshwanath Capital Ventures Fund" style="display:block;border:0;border-radius:36px"></td>'
        f'<td valign="middle"><div style="font-family:{SERIF};font-size:23px;font-weight:700;letter-spacing:.6px;color:{GOLD}">PARSHWANATH</div>'
        f'<div style="font-family:{SERIF};font-size:15px;letter-spacing:1.4px;color:{GOLD}">CAPITAL VENTURES FUND</div>'
        f'<div style="font-family:{SANS};font-size:10.5px;letter-spacing:2px;text-transform:uppercase;color:{MUTED};margin-top:5px">'
        f'SEBI-registered Category III AIF &middot; Pre-IPO &middot; Anchor &middot; QIB &middot; QIP</div></td></tr></table></td></tr>'
        f'<tr><td style="padding:10px 4px;font-family:{SANS};font-size:12px;letter-spacing:.4px;color:{MUTED};border-bottom:1px solid {LINE}">'
        f'Re: <b style="color:{GOLD}">{e(company)}</b> &nbsp;|&nbsp; {"SME IPO" if sme else "Mainboard IPO"} &nbsp;|&nbsp; DRHP{(" dated " + e(doc_date)) if doc_date else ""}</td></tr>'
        f'<tr><td style="padding:24px 4px 22px 4px">{body}</td></tr>'
        f'<tr><td style="padding:12px 4px 8px 4px;border-top:1px solid {LINE};font-family:{SANS};font-size:11px;line-height:1.55;color:{MUTED}">{e(disclaimer)}</td></tr>'
        f'</table></td></tr></table></body></html>')
    return {"subject": subject, "text": text, "html": page, "variant": v, "to": msg["to"], "names": msg.get("names", []),
            "brlm": msg.get("brlm")}
