"""Diagnostic: discover Chittorgarh's DRHP report pages and data feed (run in GitHub Actions)."""
import re, sys, urllib.request, json
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://www.chittorgarh.com/"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0), str(e)
for u in sys.argv[1:]:
    st, body = get(u)
    print(f"=== {u} -> {st} {len(body)}")
    links = sorted(set(re.findall(r'href="([^"]*(?:drhp|DRHP|draft)[^"]*)"', body)))
    for l in links[:60]:
        print("  link", l)
    for m in re.findall(r'(https://webnodejs\.chittorgarh\.com/[^"\'\s]+)', body)[:10]:
        print("  api", m)
    for m in re.findall(r'data-read/(\d+)/', body)[:10]:
        print("  report-id", m)
    if u.endswith(".json") or "webnodejs" in u:
        print(body[:3000])
