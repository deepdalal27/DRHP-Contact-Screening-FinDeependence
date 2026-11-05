"""Where new draft offer documents come from.

  * SEBI  – "Draft Offer Documents filed with SEBI" listing (mainboard DRHPs, UDRHPs, addenda)
  * NSE   – offer-document feed for Mainboard (index=equities) and NSE Emerge SME (index=sme)
  * BSE   – BSE SME draft offer documents (best effort: BSE's API changes often)

Each source returns filings: {id, company, board, source, filed_on (YYYY-MM-DD), doc_type, url, page_url}
"""
import datetime as dt
import html
import json
import re
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_jar = CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
ERRORS = []


def http_get(url, referer=None, timeout=60, retries=3, accept="*/*"):
    last = None
    for k in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9",
                                                       **({"Referer": referer} if referer else {})})
            with _opener.open(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # network hiccups are common on these sites
            last = e
            time.sleep(2 * (2 ** k))
    raise RuntimeError(f"GET {url[:120]} failed: {last}")


def company_key(name):
    t = (name or "").lower()
    t = re.sub(r"\(formerly[^)]*\)", "", t)
    t = re.sub(r"\b(limited|ltd|private|pvt|the)\b", "", t)
    return re.sub(r"[^a-z0-9]", "", t)


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _date(s):
    s = (s or "").strip()
    for fmt in ("%d-%b-%Y", "%b %d, %Y", "%d %b %Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def doc_type_of(title):
    t = title.lower()
    if "addendum" in t or "corrigendum" in t:
        return "Addendum"
    if "udrhp" in t or "updated draft" in t:
        return "UDRHP"
    if "drhp" in t or "draft red herring" in t or "draft prospectus" in t or "draft letter of offer" in t:
        return "DRHP"
    if "notice" in t:
        return "Notice"
    if re.fullmatch(r"[\w&.,()' -]+\b(limited|ltd\.?)", t.strip()):
        return "DRHP"  # SEBI sometimes lists a DRHP under the bare company name
    return "Other"


# ------------------------------------------------------------------ SEBI
SEBI_LIST = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=10"
SEBI_AJAX = "https://www.sebi.gov.in/sebiweb/ajax/home/getnewslistinfo.jsp"


def sebi_filings(pages=2):
    out = []
    htmls = []
    try:
        htmls.append(http_get(SEBI_LIST).decode("utf-8", "replace"))
        for p in range(1, pages):
            data = urllib.parse.urlencode({"nextValue": str(p), "next": "n", "search": "", "fromDate": "", "toDate": "",
                                           "fromYear": "", "toYear": "", "deptId": "", "sid": "3", "ssid": "15", "smid": "10",
                                           "ssidhidden": "15", "intmid": "-1", "sText": "Public Issues", "ssText": "Draft Offer Documents filed with SEBI",
                                           "smText": "", "doDirect": "-1"}).encode()
            req = urllib.request.Request(SEBI_AJAX, data=data, headers={"User-Agent": UA, "Referer": SEBI_LIST})
            try:
                with _opener.open(req, timeout=60) as r:
                    htmls.append(r.read().decode("utf-8", "replace"))
            except Exception as e:
                ERRORS.append(f"SEBI page {p + 1}: {e}")
    except Exception as e:
        ERRORS.append(f"SEBI listing: {e}")
        return out
    seen = set()
    for h in htmls:
        for m in re.finditer(r"<tr[^>]*>\s*<td[^>]*>([A-Za-z]{3} \d{1,2}, \d{4})</td>\s*<td[^>]*>\s*<a href=['\"]([^'\"]+/filings/public-issues/[^'\"]+)['\"][^>]*title=['\"]([^'\"]+)['\"]", h, re.S):
            date, link, title = m.group(1), m.group(2), html.unescape(re.sub(r"<[^>]+>", " ", m.group(3)))
            title = re.sub(r"\s+", " ", title.split("<a")[0]).strip()
            if link in seen:
                continue
            seen.add(link)
            company = re.split(r"\s[-–]\s|\s[-–]|[-–]\s", title)[0].strip()
            company = re.sub(r"\s*-\s*$", "", company)
            out.append({"source": "SEBI", "company": company, "board": "Mainboard", "filed_on": _date(date),
                        "doc_type": doc_type_of(title), "title": title, "page_url": link, "url": None})
    return out


def sebi_pdf_url(page_url):
    h = http_get(page_url, referer=SEBI_LIST).decode("utf-8", "replace")
    m = re.search(r"file=(https://www\.sebi\.gov\.in/sebi_data/attachdocs/[^'\"&]+\.pdf)", h, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(https://www\.sebi\.gov\.in/sebi_data/attachdocs/[^'\"]+\.pdf)", h, re.I)
    return m.group(1) if m else None


# ------------------------------------------------------------------ NSE
NSE_API = "https://www.nseindia.com/api/corporates/offerdocs?index={index}"


def nse_filings(index):
    try:
        raw = http_get(NSE_API.format(index=index), referer="https://www.nseindia.com/companies-listing/public-issues-offer-documents",
                       accept="application/json")
        rows = json.loads(raw)
    except Exception as e:
        ERRORS.append(f"NSE {index}: {e}")
        return []
    out = []
    for r in rows:
        url = r.get("drhpAttach") or ""
        if not url or not r.get("drhpDate"):
            continue
        if r.get("rhpDate") or r.get("isin"):
            continue  # already moved past the draft stage
        out.append({"source": "NSE" if index == "equities" else "NSE Emerge", "company": (r.get("company") or "").strip(),
                    "board": "Mainboard" if index == "equities" else "SME", "filed_on": _date(r.get("drhpDate")),
                    "doc_type": "DRHP", "title": r.get("drhp") or "Draft offer document", "url": url, "page_url": None,
                    "status": r.get("drhpStatus"), "symbol": r.get("symbol")})
    return out


# ------------------------------------------------------------------ BSE SME via Chittorgarh
# BSE (bseindia.com / bsesme.com) refuses connections from cloud servers, so BSE SME draft filings are
# discovered through Chittorgarh's "Upcoming SME IPO - DRHP filed" report, and the company details come
# from Chittorgarh's IPO page (the DRHP itself sits on bsesme.com, which cloud servers cannot download).
CG_LIST = "https://webnodejs.chittorgarh.com/cloud/report/data-read/154/1/11/{y}/{y}-{y2}/0/all/0?search="
CG_HEADERS_REF = "https://www.chittorgarh.com/report/upcoming-sme-ipo-drhp-filed/154/all/"


def _strip(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h or ""))).strip()


def bse_sme_filings():
    y = dt.date.today().year
    try:
        rows = json.loads(http_get(CG_LIST.format(y=y, y2=str(y + 1)[2:]), referer=CG_HEADERS_REF, accept="application/json"))["reportTableData"]
    except Exception as e:
        ERRORS.append(f"Chittorgarh (BSE SME list): {e}")
        return []
    out = []
    for r in rows:
        if "BSE" not in (r.get("Exchange") or "") or not r.get("DRHP Filing Date"):
            continue
        name = _strip(r.get("Company")).replace("Ltd.", "Limited").replace("Ltd", "Limited").replace("Limitedd", "Limited")
        out.append({"source": "BSE SME", "company": name, "board": "SME", "filed_on": _date(r.get("DRHP Filing Date")),
                    "doc_type": "DRHP", "title": "Draft offer document (BSE SME)", "url": None,
                    "page_url": f"https://www.chittorgarh.com/ipo/{r.get('~URLRewrite_Folder_Name')}/{r.get('~id')}/",
                    "status": r.get("Status"), "lead_manager": _strip(r.get("Left Lead Manager")),
                    "industry": r.get("Industry"), "issue_size": _strip((r.get("Estimated Issue Size") or "").replace("<br>", "; ")),
                    "via": "chittorgarh"})
    return out


def chittorgarh_details(page_url):
    """Company contact details, promoters, lead managers, registrar, DRHP link and the financial snapshot
    from a Chittorgarh IPO page."""
    h = http_get(page_url, referer=CG_HEADERS_REF).decode("utf-8", "replace")
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S)
    txt = _strip(body)
    out = {"page_url": page_url}
    m = re.search(r'href="(https?://[^"]+)"[^>]*>[^<]*(?:DRHP|Draft)[^<]*<', body, re.I) or \
        re.search(r'href="(https?://[^"]*(?:DRHP|drhp|Draft)[^"]*\.(?:pdf|zip))"', body)
    out["drhp_url"] = html.unescape(m.group(1)) if m else None
    m = re.search(r"Company Promoters?:\s*(.+?)\.(?:\s|$)", txt)
    out["promoters"] = [x.strip() for x in re.split(r",\s*|\s+and\s+", m.group(1)) if x.strip()] if m else []
    m = re.search(r"IPO Lead Manager\(s\)\s*(.+?)\s*Lead Manager Reports", txt)
    out["lead_managers"] = [x.strip() for x in re.split(r"\s{2,}|(?<=Ltd\.)\s+(?=[A-Z])|(?<=Limited)\s+(?=[A-Z])", m.group(1)) if x.strip()] if m else []
    m = re.search(r"IPO Registrar\s*(.+?)\s*Visit Website", txt)
    if m:
        seg = m.group(1)
        em = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", seg)
        out["registrar"] = {"name": re.split(r"\s\d", seg)[0].strip(), "emails": em,
                            "phones": re.findall(r"\d[\d\- ]{8,}\d", seg)[:3]}
    m = re.search(r"Contact Details\s*(.+?)\s*Visit Website", txt)
    if m:
        seg = m.group(1)
        em = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", seg)
        ph = re.findall(r"(?<![\w,])(?:\+?91[\s-]?)?\d[\d\s-]{8,12}\d(?![\w])", seg)
        addr = seg
        for x in em + ph:
            addr = addr.replace(x, " ")
        out["contact"] = {"emails": [e.lower() for e in em], "phones": [p.strip() for p in ph], "address": re.sub(r"\s+", " ", addr).strip(" ,")}
    # company website: the link right after the "Contact Details" block
    i = body.find("Contact Details")
    if i >= 0:
        m = re.search(r'href="(https?://(?!www\.chittorgarh)[^"]+)"[^>]*>\s*Visit Website', body[i:i + 6000])
        out["website"] = m.group(1) if m else None
    # financial snapshot (₹ crore, as published by Chittorgarh)
    m = re.search(r"Period Ended\s+(.+?)\s+Amount in ₹ Crore", txt)
    if m:
        seg = m.group(1)
        dates = re.findall(r"\d{1,2} [A-Z][a-z]{2} \d{4}", seg)
        rest = seg
        for d in dates:
            rest = rest.replace(d, " ", 1)
        rows = []
        for lab, nums in re.findall(r"([A-Za-z][A-Za-z &/]+?)\s+((?:-?[\d,]+\.\d+\s*)+)", rest):
            vals = [float(x.replace(",", "")) for x in nums.split()]
            rows.append({"label": lab.strip(), "values": vals[:len(dates)]})
        out["financials"] = {"periods": dates, "rows": rows}
    m = re.search(r"(?:About|Business Overview)\s+" + re.escape(txt[:0]) + r"(.{40,900}?)(?:\+ Read More|Competitive Strengths|Company Financials)", txt)
    out["about"] = m.group(1).strip() if m else None
    m = re.search(r"(\S[^.]{0,120}?(?:is|are) (?:engaged|a |an |in the business)[^.]{20,400}\.)", txt)
    out["about"] = out["about"] or (m.group(1).strip() if m else None)
    return out


def all_filings(since_days=45):
    """New draft filings from every source, newest first, one entry per company (best document wins)."""
    ERRORS.clear()
    rows = sebi_filings() + nse_filings("equities") + nse_filings("sme") + bse_sme_filings()
    cutoff = (dt.date.today() - dt.timedelta(days=since_days)).isoformat()
    rows = [r for r in rows if r.get("doc_type") in ("DRHP", "UDRHP") and (r.get("filed_on") or "9999") >= cutoff]
    pref = {"SEBI": 0, "NSE": 1, "NSE Emerge": 1, "BSE SME": 2}
    best, alts = {}, {}
    for r in rows:
        k = company_key(r["company"])
        if not k:
            continue
        r["key"] = k
        alts.setdefault(k, []).append({"source": r["source"], "url": r.get("url"), "page_url": r.get("page_url")})
        cur = best.get(k)
        if cur is None or (r["filed_on"] or "") > (cur["filed_on"] or "") or \
                ((r["filed_on"] or "") == (cur["filed_on"] or "") and pref[r["source"]] < pref[cur["source"]]):
            if cur:
                r.setdefault("also_on", []).append(cur["source"])
            best[k] = r
        else:
            cur.setdefault("also_on", []).append(r["source"])
    for k, r in best.items():
        r["alternates"] = [a for a in alts.get(k, []) if (a["url"] or a["page_url"]) != (r.get("url") or r.get("page_url"))]
    return sorted(best.values(), key=lambda r: r.get("filed_on") or "", reverse=True)
