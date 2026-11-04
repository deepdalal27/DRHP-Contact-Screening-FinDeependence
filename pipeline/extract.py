"""Read one DRHP PDF and return company, contacts, offer details and financials.

Everything returned carries the DRHP page it came from, so it can be checked against the document.
Financial figures are validated in `validate.py`; nothing here guesses a number that is not printed.
"""
import re

from .textutil import pdf_to_pages, clean, find_emails, find_phones
from .tables import parse_table, norm_label


class Doc:
    def __init__(self, layout_pages, raw_pages):
        self.layout_pages = layout_pages
        self.raw_pages = raw_pages
        self.lines, self.line_page = [], []
        for p, txt in enumerate(layout_pages, 1):
            for ln in txt.split("\n"):
                self.lines.append(ln)
                self.line_page.append(p)
        self.raw = "\n".join(raw_pages)
        self.raw_page_starts = []
        pos = 0
        for txt in raw_pages:
            self.raw_page_starts.append(pos)
            pos += len(txt) + 1

    def page_of_line(self, i):
        return self.line_page[i] if 0 <= i < len(self.line_page) else None

    def page_of_raw(self, pos):
        lo = 0
        for k, s in enumerate(self.raw_page_starts):
            if s <= pos:
                lo = k
            else:
                break
        return lo + 1

    @classmethod
    def from_pdf(cls, path):
        return cls(pdf_to_pages(path, layout=True), pdf_to_pages(path, layout=False))


# ---------------------------------------------------------------- cover / company
def _is_toc_line(ln):
    return bool(re.search(r"\.{6,}\s*\d+\s*$", ln))


def cover_info(doc):
    first = "\n".join(doc.layout_pages[:2])
    raw_first = "\n".join(doc.raw_pages[:2])
    out = {"page": 1}
    head = first[:6000]
    m = re.search(r"\b(DRAFT RED HERRING PROSPECTUS|DRAFT PROSPECTUS|UPDATED DRAFT RED HERRING PROSPECTUS[- –]*I*|RED HERRING PROSPECTUS|PROSPECTUS)\b", head, re.I)
    out["document_type"] = clean(m.group(1)).title() if m else None
    m = re.search(r"Dated?:?\s*([A-Z][a-z]+ \d{1,2}, \d{4})", head)
    out["document_date"] = m.group(1) if m else None
    # company name: the first all-caps line ending in LIMITED
    for ln in first.split("\n")[:80]:
        t = clean(ln)
        if re.fullmatch(r"[A-Z0-9&.,'()\- ]{3,120}\bLIMITED", t) and "FORMERLY" not in t:
            out["company"] = t.title().replace("Limited", "Limited")
            out["company_caps"] = t
            break
    m = re.search(r"\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b", head)
    out["cin"] = m.group(1) if m else None
    m = re.search(r"((?:https?://)?www\.[A-Za-z0-9\-]+(?:\.[A-Za-z]{2,})+/?|https?://[A-Za-z0-9\-.]+\.[a-z]{2,}/?)", raw_first[:5000])
    out["website"] = m.group(1) if m else None
    out["promoters"] = promoters_from_cover(first)
    raw_up = raw_first.upper()
    if re.search(r"EMERGE PLATFORM OF NATIONAL STOCK EXCHANGE|NSE EMERGE|SME PLATFORM OF NATIONAL", raw_up):
        out["board"] = "SME"; out["exchange"] = "NSE Emerge"
    elif re.search(r"SME PLATFORM OF BSE|BSE SME", raw_up):
        out["board"] = "SME"; out["exchange"] = "BSE SME"
    else:
        out["board"] = "Mainboard"; out["exchange"] = "BSE & NSE" if ("BSE" in raw_up and "NATIONAL STOCK EXCHANGE" in raw_up) else None
    out["fresh_issue"] = bool(re.search(r"fresh issue", raw_first, re.I))
    out["ofs"] = bool(re.search(r"offer for sale", raw_first, re.I))
    out["pre_ipo_placement"] = bool(re.search(r"pre[- ]ipo placement", raw_first, re.I))
    m = re.search(r"pre[- ]ipo placement[^.]{0,400}?shall not exceed\s+(\d+)\s*%", re.sub(r"\s+", " ", raw_first), re.I)
    out["pre_ipo_limit_pct"] = int(m.group(1)) if m else None
    m = re.search(r"Regulation\s+(6\(1\)|6\(2\)|229\(1\)|229\(2\)|229\(3\))", raw_first)
    out["icdr_regulation"] = m.group(1) if m else None
    return out


def promoters_from_cover(text):
    flat = re.sub(r"[ \t]+", " ", text)
    m = re.search(r"(?:OUR PROMOTERS?(?: ARE| IS)?|PROMOTERS? OF (?:OUR|THE) COMPANY|THE PROMOTERS? OF (?:OUR|THE) COMPANY (?:ARE|IS))\s*[:\-–]?\s*(.+?)(?:\n\s*(?:DETAILS OF|THE OFFER|OFFER|TYPE)\b|\n\s*\n)", flat, re.S | re.I)
    if not m:
        return []
    s = clean(m.group(1))
    s = re.sub(r"\s+AND\s+", ", ", s, flags=re.I)
    names = [clean(x).strip(".") for x in s.split(",")]
    out = []
    for n in names:
        if 2 < len(n) < 80 and not re.search(r"DETAILS|OFFER|ISSUE", n, re.I):
            out.append(_title_name(n))
    return out


def _title_name(n):
    words = []
    for w in n.split():
        if re.fullmatch(r"[A-Z]\.?", w) or w in ("HUF", "LLP", "PVT", "LTD"):
            words.append(w)
        elif w.upper() in ("TRUST", "PRIVATE", "LIMITED", "FAMILY"):
            words.append(w.title())
        else:
            words.append(w[:1].upper() + w[1:].lower() if w.isupper() else w)
    return " ".join(words)


# ---------------------------------------------------------------- general information (contacts)
GI_HEADS = [
    ("cs", r"Company Secretary and Compliance Officer(?: of our Company)?"),
    ("brlm", r"(?:Book Running Lead Managers?|Lead Managers? to the (?:Offer|Issue)|Book Running Lead Manager to the (?:Offer|Issue)|BRLMs?)"),
    ("end_brlm", r"(?:Statement of inter[- ]se allocation|Syndicate Members?|Legal (?:Counsel|Advisors?)|Registrar to the (?:Offer|Issue)|Statutory Auditors?|Bankers? to)"),
    ("registrar", r"Registrar to the (?:Offer|Issue)"),
]


def _gi_start(doc):
    """Character offset of the 'GENERAL INFORMATION' section body in the raw text (not the TOC entry)."""
    best = None
    for m in re.finditer(r"\n\s*GENERAL INFORMATION\s*\n", doc.raw):
        after = doc.raw[m.end():m.end() + 6000]
        if re.search(r"Registered (?:and Corporate )?Office", after, re.I) and doc.page_of_raw(m.start()) > 5:
            best = m.end()
            break
    return best


def _block_after(text, start_pat, end_pats, limit=2500):
    m = re.search(r"(?:^|\n)\s*" + start_pat + r"\s*\n", text, re.I)
    if not m:
        return None, None
    body = text[m.end():m.end() + limit]
    cut = len(body)
    for ep in end_pats:
        e = re.search(r"\n\s*" + ep, body, re.I)
        if e and e.start() < cut:
            cut = e.start()
    return body[:cut], m.start()


def _field(block, names):
    for n in names:
        m = re.search(r"(?:^|\n)\s*" + n + r"\s*[:\-–]?\s*(.+)", block, re.I)
        if m:
            return clean(m.group(1))
    return None


def _person_from_block(block):
    """Contact person line e.g. 'Contact person: Shravan Suthar / Suchit Dave'."""
    v = _field(block, [r"Contact [Pp]ersons?\(?s?\)?"])
    if not v:
        return []
    return [clean(x) for x in re.split(r"\s*/\s*|\s*,\s*|\s+and\s+", v) if clean(x)]


def general_information(doc):
    out = {"cs": None, "brlms": [], "registrar": None, "page": None}
    start = _gi_start(doc)
    if start is None:
        return out
    gi = doc.raw[start:start + 60000]
    out["page"] = doc.page_of_raw(start)
    # Company secretary
    block, off = _block_after(gi, r"Company Secretary and Compliance Officer(?: of (?:our|the) Company)?",
                              [r"Investor grievances?", r"Filing of", r"Book Running", r"Chief Financial Officer", r"Lead Manager"], 1500)
    if block:
        name = None
        m = re.search(r"^\s*([A-Z][A-Za-z.\s]{2,60}?)\s+is the Company Secretary", block)
        if m:
            name = clean(m.group(1))
        else:
            first = clean(block.strip().split("\n")[0])
            if re.fullmatch(r"(?:(?:Mr|Ms|Mrs|Dr|CS)\.?\s+)?[A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,4}", first):
                name = first
        emails = find_emails(block)
        out["cs"] = {
            "name": name, "emails": emails,
            "phones": find_phones(_field(block, [r"Tel(?:ephone)?(?: No\.?)?", r"Phone", r"Mobile"]) or ""),
            "page": doc.page_of_raw(start + off),
        }
    # BRLMs
    block, off = _block_after(gi, GI_HEADS[1][1], [GI_HEADS[2][1]], 9000)
    if block:
        out["brlms"] = split_brlms(block, doc.page_of_raw(start + off))
    block, off = _block_after(gi, GI_HEADS[3][1], [r"Bankers? to", r"Syndicate", r"Statutory Auditor", r"Legal", r"Grading", r"Monitoring", r"Designated", r"Book Running", r"Lead Manager", r"Statement of inter", r"Expert", r"Credit Rating"], 1500)
    if block:
        lines = [clean(x) for x in block.strip().split("\n") if clean(x)]
        out["registrar"] = {
            "name": lines[0] if lines else None,
            "emails": find_emails(block),
            "phones": find_phones(_field(block, [r"Tel(?:ephone)?", r"Phone"]) or ""),
            "contact_persons": _person_from_block(block),
            "page": doc.page_of_raw(start + off),
        }
    return out


def split_brlms(block, page):
    """Split a 'Book Running Lead Manager(s)' block into one record per merchant banker."""
    parts = re.split(r"(SEBI [Rr]egistration (?:[Nn]o\.?|[Nn]umber)\s*[:\-–]?\s*INM\s*\d+)", block)
    recs = []
    for k in range(0, len(parts) - 1, 2):
        body = parts[k] + parts[k + 1]
        lines = [clean(x) for x in body.strip().split("\n") if clean(x)]
        name = None
        for ln in lines:
            if re.search(r"\b(Limited|LLP|Ltd\.?|Private Limited|Capital|Advisors|Securities)\b", ln) and not re.match(r"(Address|Tel|E-?mail|Website|Contact|Investor|SEBI)", ln, re.I):
                name = re.sub(r"^\(?\d+\)?\.?\s*", "", ln)
                break
        emails = find_emails(_field(body, [r"E-?mail(?: ID)?"]) or "")
        ig = find_emails(_field(body, [r"Investor [Gg]rievances? (?:[Ee]-?mail|ID|Id)(?: ID)?"]) or "")
        recs.append({
            "name": name,
            "contact_persons": _person_from_block(body),
            "emails": emails or [e for e in find_emails(body) if e not in ig],
            "grievance_emails": ig,
            "phones": find_phones(_field(body, [r"Tel(?:ephone)?(?: No\.?)?", r"Phone"]) or ""),
            "website": _field(body, [r"Website"]),
            "sebi_reg": re.search(r"INM\s*\d+", parts[k + 1]).group(0).replace(" ", ""),
            "page": page,
        })
    if not recs:  # format without SEBI numbers: keep whatever contacts are visible
        emails = find_emails(block)
        if emails:
            first = clean(block.strip().split("\n")[0])
            recs.append({"name": first, "contact_persons": _person_from_block(block), "emails": emails,
                         "grievance_emails": [], "phones": find_phones(block), "website": None, "sebi_reg": None, "page": page})
    return recs


# ---------------------------------------------------------------- promoters' contacts and designations
SKIP_DOMAINS = ("sebi.gov.in", "nseindia.com", "bseindia.com", "mca.gov.in", "rbi.org.in", "nsdl.co.in", "cdslindia.com", "npci.org.in")


PERSONAL_DOMAINS = ("gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com", "rediffmail.com", "live.com", "icloud.com")
ENTITY_WORDS = re.compile(r"\b(limited|ltd|llp|pte|a/s|inc|trust|huf|government|ministry|president|acting|through|corporation|company|holdings?|ventures|fund|bank)\b", re.I)


def is_person(name):
    return bool(name) and not ENTITY_WORDS.search(name)


def domain_of(url_or_email):
    t = (url_or_email or "").lower().strip()
    if "@" in t:
        return t.split("@", 1)[1]
    t = re.sub(r"^https?://", "", t).split("/")[0]
    return re.sub(r"^www\.", "", t)


def promoter_contacts(doc, promoters, company_domains):
    """Return {promoter: [emails]} only where the address clearly belongs to that person.

    Accepted only if BOTH hold:
      * the domain is the company's own domain (from its website / CS email) or a personal mailbox
        (gmail, yahoo, outlook ...): bankers', lawyers', auditors' and registrars' domains never qualify;
      * the local part contains the promoter's first name and, for personal mailboxes, also the surname.
    """
    found = {}
    all_emails = {}
    for m in re.finditer(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+", doc.raw):
        e = m.group(0).lower().strip(".")
        all_emails.setdefault(e, doc.page_of_raw(m.start()))
    own = {d for d in company_domains if d}
    for p in promoters:
        if not is_person(p):
            continue
        toks = [t.lower() for t in re.findall(r"[A-Za-z]{3,}", p)]
        if len(toks) < 1:
            continue
        first, last = toks[0], toks[-1]
        for e, pg in all_emails.items():
            local, dom = e.split("@", 1)
            if dom in own:
                ok = first in local or (len(last) >= 4 and last in local and local[:1] == first[:1])
            elif dom in PERSONAL_DOMAINS:
                ok = first in local and (last in local or len(toks) == 1)
            else:
                ok = False
            if ok:
                found.setdefault(p, []).append({"email": e, "page": pg})
    return found


def designations(doc, promoters, gi_page):
    """Find each promoter's board designation in the General Information board table."""
    out = {}
    if not gi_page:
        return out
    lo = gi_page - 1
    text = "\n".join(doc.layout_pages[lo:lo + 4])
    flat = re.sub(r"\s+", " ", text)
    for p in promoters:
        first = p.split()[0]
        flat2 = re.sub(r"\b(Chairman|Managing|Whole[- ]?time|Executive)\s+(?:and|&)?\s*\d{8}\s+", r"\1 and ", flat)
        m = re.search(re.escape(first) + r".{0,80}?\b(Chairman (?:and|&) Managing Director|Chairman(?: and|&)? Managing Director|Managing Director(?: and| &)? (?:Chief Executive Officer|CEO)|Managing Director|Whole[- ]?time Director|Executive Director|Chairman|Non[- ]Executive Director|Joint Managing Director)", flat2, re.I)
        if m:
            out[p] = clean(m.group(1)).title().replace("And", "and")
    return out


# ---------------------------------------------------------------- business summary
def business_summary(doc):
    """First two sentences of 'Our Business' > 'Overview' (falls back to the offer-document summary)."""
    raw = doc.raw
    starts = []
    for m in re.finditer(r"\n\s*OUR BUSINESS\s*\n", raw):
        if doc.page_of_raw(m.start()) > 8:
            starts.append(m.end())
    for m in re.finditer(r"Summary of (?:the )?primary business(?: of (?:our|the) Company)?|Primary business of (?:our|the) Company", raw, re.I):
        if doc.page_of_raw(m.start()) > 8:
            starts.append(m.end())
    for st in starts:
        seg = raw[st:st + 12000]
        ov = re.search(r"\n\s*(?:Overview|Business Overview|OVERVIEW)\s*\n", seg)
        body = seg[ov.end():] if ov else seg
        text = clean(body[:3000])
        sentences = re.split(r"(?<=[a-z0-9\)%])\.\s+(?=[A-Z“\"(])", text)
        picked = [s.strip() for s in sentences[:4] if s.strip()]
        picked = [re.sub(r"\s*\((?:Source|Note)[^)]*\)", "", s) for s in picked
                  if not re.search(r"\bon page\b|\bsee “|\bpages? \d", s)]
        if picked and re.search(r"\b(we|our|company)\b", " ".join(picked[:2]), re.I):
            summ = ". ".join(picked[:2])
            if not summ.endswith("."):
                summ += "."
            return {"text": summ[:700], "page": doc.page_of_raw(st + (ov.end() if ov else 0))}
    return None


# ---------------------------------------------------------------- financial tables
TITLE_PATS = {
    "bs": r"(?:STATEMENTS? OF|STATEMENT OF) (?:THE )?ASSETS (?:AND|&) LIABILITIES|BALANCE SHEET",
    "pl": r"(?:STATEMENTS? OF) PROFIT (?:AND|&) LOSS|PROFIT (?:AND|&) LOSS (?:STATEMENT|ACCOUNT)",
    "cf": r"(?:STATEMENTS? OF) CASH FLOWS?|CASH FLOW STATEMENTS?",
}


def find_summary_section(doc):
    """Line index where the SUMMARY (OF) FINANCIAL INFORMATION section body starts (skipping the TOC)."""
    for i, ln in enumerate(doc.lines):
        if re.search(r"^\s*SUMMARY (?:OF )?(?:RESTATED |THE )?(?:CONSOLIDATED |STANDALONE )?FINANCIAL (?:INFORMATION|STATEMENTS)\s*$", ln, re.I) \
                and not _is_toc_line(ln) and doc.page_of_line(i) > 5:
            return i
    return None


def find_tables(doc, start):
    """Locate BS / P&L / CF tables after `start`; return {kind: (lo, hi)} line ranges."""
    found = {}
    order = []
    end = min(len(doc.lines), start + 1600)
    for i in range(start, end):
        ln = doc.lines[i]
        if _is_toc_line(ln) or len(clean(ln)) > 140:
            continue
        for kind, pat in TITLE_PATS.items():
            if kind not in found and re.search(pat, ln, re.I) and not re.search(r"\b(?:read|see|refer|derived|conjunction|page)\b", ln, re.I):
                found[kind] = i
                order.append((i, kind))
    order.sort()
    out = {}
    for k, (i, kind) in enumerate(order):
        hi = order[k + 1][0] if k + 1 < len(order) else min(len(doc.lines), i + 220)
        out[kind] = (i, min(hi, i + 260))
    return out


def parse_fin_table(doc, lo, hi):
    lines = doc.lines[lo:hi]
    t = parse_table(lines, first_line_no=lo, page_of=doc.page_of_line)
    head = " ".join(lines[:12]).lower()
    if "lakh" in head:
        t["unit"] = "lakhs"
    elif "million" in head or "mn" in re.findall(r"\b(mn)\b", head):
        t["unit"] = "million"
    elif "crore" in head:
        t["unit"] = "crore"
    else:
        t["unit"] = None
    t["title"] = clean(lines[0])
    t["page"] = doc.page_of_line(lo)
    return t


def _unit_from_context(doc, lo):
    txt = " ".join(doc.lines[max(0, lo - 40):lo + 15]).lower()
    for u in ("lakh", "million", "crore"):
        if u in txt:
            return {"lakh": "lakhs"}.get(u, u)
    return None


METRICS = {
    "pl": [
        ("revenue", r"^revenue from operations?$|^revenue from operations? \(net\)|^net revenue from operations"),
        ("other_income", r"^other income$"),
        ("total_income", r"^total (?:income|revenue)"),
        ("finance_cost", r"^finance (?:costs?|charges)|^interest (?:and|&) finance (?:costs?|charges)"),
        ("depreciation", r"^depreciation"),
        ("total_expenses", r"^total expenses?"),
        ("pbt_before_exceptional", r"before exceptional items?"),
        ("pbt", r"^(?:restated )?(?:net )?profit\s*/?\s*(?:\(loss\))?\s*before tax|^profit/\(loss\) before tax|^\(loss\)/profit before tax|^profit before tax"),
        ("tax", r"^total tax(?: expenses?)?|^tax expenses?$|^total income tax expense"),
        ("pat", r"^(?:restated )?(?:net )?(?:profit|\(loss\))\s*/?\s*(?:\(loss\)|profit)?\s*(?:after tax|for the (?:year|period)|from the (?:period|year)|from continuing operations)(?!.*comprehensive)"),
        ("eps_basic", r"\bbasic\b"),
        ("eps_diluted", r"\bdiluted\b"),
    ],
    "bs": [
        ("total_assets", r"^total assets"),
        ("share_capital", r"^equity share capital|^share capital"),
        ("other_equity", r"^other equity|^reserves (?:and|&) surplus"),
        ("total_equity", [r"^total equity$", r"^total equity \(", r"^total equity attributable", r"^total shareholders'? (?:funds|equity)", r"^net worth", r"^equity attributable to (?:the )?(?:owners|equity holders)"]),
        ("total_equity_liabilities", r"^total equity (?:and|&) liabilities|^total liabilities (?:and|&) equity"),
        ("inventories", r"^inventor(?:y|ies)"),
        ("trade_receivables", r"trade receivables"),
        ("cash", r"^cash (?:and|&) cash equivalents"),
    ],
    "cf": [
        ("cfo", r"^net cash.*operating activit(?!.*before)"),
        ("cfi", r"^net cash.*invest(?:ing|ment)"),
        ("cff", r"^net cash.*financing"),
    ],
}


def pick_metrics(table, kind):
    rows = table.get("rows", [])
    out = {}
    for key, pats in METRICS[kind]:
        r = None
        for pat in (pats if isinstance(pats, list) else [pats]):
            r = _first_row(rows, key, pat)
            if r:
                break
        if r:
            out[key] = r
    return _extras(rows, kind, out)


def _first_row(rows, key, pat):
    if True:
        for r in rows:
            lab = norm_label(r["label"])
            if re.search(pat, lab):
                if key == "pbt" and "exceptional" in lab and "after" not in lab:
                    continue
                if key == "total_equity" and "liabilities" in lab:
                    continue
                if key == "trade_receivables" and ("provision" in lab or "loss" in lab):
                    continue
                if key in ("eps_basic", "eps_diluted") and not any(v not in (None, 0.0) for v in r["values"]):
                    continue
                return r
    return None


def _extras(rows, kind, out):
    if kind == "bs":
        borrow = [r for r in rows if re.search(r"\bborrowings?\b", norm_label(r["label"])) and not norm_label(r["label"]).startswith("total")]
        if borrow:
            out["borrowings_rows"] = borrow
        cur = [r for r in rows if re.search(r"^(?:total |subtotal: )current assets", norm_label(r["label"]))]
        if cur:
            out["current_assets"] = cur[0]
        curl = [r for r in rows if re.search(r"^(?:total |subtotal: )current liabilities", norm_label(r["label"]))]
        if curl:
            out["current_liabilities"] = curl[0]
    if kind == "pl" and "tax" not in out:
        tx = [r for r in rows if re.search(r"^(?:current tax|deferred tax|tax(?:es)? (?:of|for|relating to) (?:earlier|prior) (?:years?|periods?)|mat credit)", norm_label(r["label"]))]
        if tx:
            out["tax_rows"] = tx
    return out


def kpi_table(doc):
    """The KPI table in 'Basis for Offer Price' (every DRHP must disclose it)."""
    for i, ln in enumerate(doc.lines):
        if doc.page_of_line(i) <= 8 or _is_toc_line(ln):
            continue
        if re.search(r"(details of (?:our )?KPIs|key performance indicators?\s*(?:\(“?KPIs?”?\))?\s*$|set forth (?:the )?details of (?:the |our )?KPIs)", ln, re.I):
            # the table should follow within 40 lines
            for j in range(i, min(i + 60, len(doc.lines))):
                if re.search(r"Revenue from operations|Total income", doc.lines[j], re.I) and re.search(r"\d", doc.lines[j]):
                    lo = max(i, j - 14)
                    hi = j
                    while hi < min(len(doc.lines), j + 80) and not re.match(r"\s*(?:Notes?|Source|\*|#|\(\d\))\b", doc.lines[hi], re.I):
                        hi += 1
                    t = parse_table(doc.lines[lo:hi], first_line_no=lo, page_of=doc.page_of_line)
                    if len(t["rows"]) >= 3:
                        t["page"] = doc.page_of_line(j)
                        t["unit"] = _unit_from_context(doc, j)
                        return t
                    break
    return None


def financials(doc):
    start = find_summary_section(doc)
    tables = {}
    source = "Summary Financial Information"
    if start is not None:
        for kind, (lo, hi) in find_tables(doc, start).items():
            tables[kind] = parse_fin_table(doc, lo, hi)
    if "pl" not in tables or "bs" not in tables:
        # fall back to the full restated statements
        for i, ln in enumerate(doc.lines):
            if doc.page_of_line(i) > 30 and re.search(r"^\s*RESTATED (?:CONSOLIDATED |STANDALONE )?STATEMENT OF ASSETS", ln, re.I):
                for kind, (lo, hi) in find_tables(doc, i).items():
                    tables.setdefault(kind, parse_fin_table(doc, lo, hi))
                source = "Restated Financial Information"
                break
    for kind, t in tables.items():
        if not t.get("unit"):
            t["unit"] = _unit_from_context(doc, t.get("rows", [{}])[0].get("line", 0) if t.get("rows") else 0)
    picked = {k: pick_metrics(t, k) for k, t in tables.items()}
    return {"source": source, "tables": tables, "picked": picked}


def company_domains(cover, gi):
    doms = {domain_of(cover.get("website"))}
    for e in ((gi.get("cs") or {}).get("emails") or []):
        d = domain_of(e)
        if d not in PERSONAL_DOMAINS:
            doms.add(d)
    return {d for d in doms if d}


def clean_cs_emails(gi, cover):
    """The CS block sometimes runs into auditors' / lawyers' details: keep only the company's own address(es)."""
    cs = gi.get("cs")
    if not cs or not cs.get("emails"):
        return
    site = domain_of(cover.get("website"))
    stem = re.sub(r"[^a-z]", "", (cover.get("company") or "").lower().replace("limited", ""))[:6]
    own = [e for e in cs["emails"] if site and domain_of(e).endswith(site)] or \
          [e for e in cs["emails"] if stem and stem in re.sub(r"[^a-z]", "", domain_of(e))]
    cs["emails"] = own or cs["emails"][:1]


# ---------------------------------------------------------------- entry point
def extract(pdf_path):
    doc = Doc.from_pdf(pdf_path)
    return extract_doc(doc)


def extract_doc(doc):
    cover = cover_info(doc)
    gi = general_information(doc)
    clean_cs_emails(gi, cover)
    excl = set()
    for b in gi.get("brlms", []):
        for e in b.get("emails", []) + b.get("grievance_emails", []):
            excl.add(e.split("@", 1)[1])
    if gi.get("registrar"):
        for e in gi["registrar"].get("emails", []):
            excl.add(e.split("@", 1)[1])
    fin = financials(doc)
    kpi = kpi_table(doc)
    return {
        "pages": len(doc.layout_pages),
        "cover": cover,
        "general": gi,
        "promoter_emails": promoter_contacts(doc, cover.get("promoters", []), company_domains(cover, gi)),
        "designations": designations(doc, cover.get("promoters", []), gi.get("page")),
        "business": business_summary(doc),
        "financials": fin,
        "kpi": kpi,
        "_doc": doc,
    }
