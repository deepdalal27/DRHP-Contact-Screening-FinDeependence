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
    m = re.search(r"file=(https://www\.sebi\.gov\.in/sebi_data/attachdocs/[^'\"&]+\.pdf)", h)
    if m:
        return m.group(1)
    m = re.search(r"(https://www\.sebi\.gov\.in/sebi_data/attachdocs/[^'\"]+\.pdf)", h)
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


# ------------------------------------------------------------------ BSE SME (best effort)
BSE_ENDPOINTS = [
    "https://api.bseindia.com/BseIndiaAPI/api/DraftOfferDoc/w?Type=SME",
    "https://api.bseindia.com/BseIndiaAPI/api/DRHPData/w?type=SME",
]


def bse_sme_filings():
    for url in BSE_ENDPOINTS:
        try:
            raw = http_get(url, referer="https://www.bseindia.com/", accept="application/json", retries=1)
            data = json.loads(raw)
        except Exception as e:
            ERRORS.append(f"BSE SME ({url.split('/api/')[-1]}): {e}")
            continue
        rows = data.get("Table") if isinstance(data, dict) else data
        out = []
        for r in rows or []:
            name = r.get("CompanyName") or r.get("Company_Name") or r.get("COMPANYNAME") or r.get("SCRIP_NAME")
            link = r.get("FileURL") or r.get("Attachment") or r.get("ATTACHMENTNAME") or r.get("DRHPLink")
            date = r.get("FilingDate") or r.get("Date") or r.get("DT_TM") or r.get("Filing_Date")
            if not name or not link:
                continue
            if not link.startswith("http"):
                link = "https://www.bseindia.com/" + link.lstrip("/")
            out.append({"source": "BSE SME", "company": name.strip(), "board": "SME", "filed_on": _date((date or "")[:10]) or _date(date),
                        "doc_type": "DRHP", "title": "Draft offer document", "url": link, "page_url": None})
        if out:
            return out
    return []


def all_filings(since_days=45):
    """New draft filings from every source, newest first, one entry per company (best document wins)."""
    ERRORS.clear()
    rows = sebi_filings() + nse_filings("equities") + nse_filings("sme") + bse_sme_filings()
    cutoff = (dt.date.today() - dt.timedelta(days=since_days)).isoformat()
    rows = [r for r in rows if r.get("doc_type") in ("DRHP", "UDRHP") and (r.get("filed_on") or "9999") >= cutoff]
    pref = {"SEBI": 0, "NSE": 1, "NSE Emerge": 1, "BSE SME": 2}
    best = {}
    for r in rows:
        k = company_key(r["company"])
        if not k:
            continue
        r["key"] = k
        cur = best.get(k)
        if cur is None or (r["filed_on"] or "") > (cur["filed_on"] or "") or \
                ((r["filed_on"] or "") == (cur["filed_on"] or "") and pref[r["source"]] < pref[cur["source"]]):
            if cur:
                r.setdefault("also_on", []).append(cur["source"])
            best[k] = r
        else:
            cur.setdefault("also_on", []).append(r["source"])
    return sorted(best.values(), key=lambda r: r.get("filed_on") or "", reverse=True)
