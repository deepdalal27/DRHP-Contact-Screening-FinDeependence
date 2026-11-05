"""Diagnostic: BSE SME DRHPs via Chittorgarh: list feed, detail pages, PDF reachability (run in GitHub Actions)."""
import re, json, urllib.request, datetime as dt
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def get(u, raw=False):
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://www.chittorgarh.com/", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
        return r.status, (b if raw else b.decode("utf-8", "replace")), r.headers.get("content-type")
y = dt.date.today().year
st, body, _ = get(f"https://webnodejs.chittorgarh.com/cloud/report/data-read/154/1/11/{y}/{y}-{str(y+1)[2:]}/0/all/0?search=")
rows = json.loads(body)["reportTableData"]
print("rows", len(rows), "keys", list(rows[0].keys()))
from collections import Counter
print(Counter(r.get("Exchange") for r in rows), Counter(r.get("Status") for r in rows))
bse = [r for r in rows if "BSE" in (r.get("Exchange") or "")]
bse.sort(key=lambda r: dt.datetime.strptime(r["DRHP Filing Date"], "%d-%b-%Y") if r.get("DRHP Filing Date") else dt.datetime(1900,1,1), reverse=True)
for r in bse[:4]:
    print("BSE:", r["Company"], r["DRHP Filing Date"], r["Status"], re.sub("<[^>]+>", "", r.get("Left Lead Manager") or ""), r["~URLRewrite_Folder_Name"], r["~id"])
    u = f"https://www.chittorgarh.com/ipo/{r['~URLRewrite_Folder_Name']}/{r['~id']}/"
    try:
        st, page, _ = get(u)
        links = sorted(set(re.findall(r'href="(https?://[^"]+\.(?:pdf|PDF|zip)[^"]*)"', page)))
        dl = [l for l in re.findall(r'href="([^"]+)"[^>]*>[^<]*(?:DRHP|Draft|Prospectus)[^<]*<', page)]
        print("   page", st, len(page), "pdfs:", links[:6], "drhp-links:", dl[:6])
        for l in links[:2]:
            try:
                s2, b2, ct = get(l, raw=True)
                print("     fetch", l, s2, ct, len(b2), b2[:5])
            except Exception as e:
                print("     fetch", l, "ERR", e)
    except Exception as e:
        print("   page ERR", e)
st, body, _ = get(f"https://webnodejs.chittorgarh.com/cloud/report/data-read/20/1/11/{y}/{y}-{str(y+1)[2:]}/0/sme/0?search=")
p = json.loads(body)["reportTableData"]
print("prospectus rows", len(p), list(p[0].keys()))
for r in [x for x in p if "BSE" in x.get("Exchange", "")][:5]:
    print("  PROS", r["Company"], r["Opening Date"], re.findall(r'href=\\?"([^"\\]+)', r["Prospectus (pdf)"]))
