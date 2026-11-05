"""Diagnostic: inspect Chittorgarh SME DRHP reports (run in GitHub Actions)."""
import re, sys, urllib.request, json, html as H
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://www.chittorgarh.com/", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0), str(e)
for u in sys.argv[1:]:
    st, body = get(u)
    print(f"=== {u} -> {st} {len(body)}")
    if "webnodejs" in u:
        print(body[:2500]); continue
    print("  apis:", sorted(set(re.findall(r'webnodejs\.chittorgarh\.com/[^"\'\s<>]+', body)))[:10])
    tb = re.search(r"<table.*?</table>", body, re.S)
    if tb:
        rows = re.findall(r"<tr.*?</tr>", tb.group(0), re.S)
        print("  rows:", len(rows))
        for r in rows[:8]:
            cells = [H.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
            links = re.findall(r'href="([^"]+)"', r)
            print("   ", [re.sub(r"\s+", " ", c) for c in cells], links[:4])
    else:
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
        print("  next_data:", (nd.group(1)[:3000] if nd else "none"))
