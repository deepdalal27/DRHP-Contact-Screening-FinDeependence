"""Diagnostic: inspect Chittorgarh SME DRHP reports (run in GitHub Actions)."""
import re, sys, urllib.request, html as H
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
    print("  scripts:", re.findall(r'<script[^>]+src="([^"]+)"', body)[:15])
    for kw in ("reportTableData", "data-read", "webnodejs", "api/", "__NUXT", "self.__next_f", "application/json", "drhp_status", "Filing Date"):
        i = body.find(kw)
        print(f"  [{kw}] at {i}:", body[max(0, i-200):i+400].replace("\n", " ") if i >= 0 else "-")
    i = body.find("<table")
    print("  table at", i, body[i:i+1500].replace("\n", " ") if i >= 0 else "")
    txt = H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)))
    txt = re.sub(r"\s+", " ", txt)
    j = txt.find("DRHP")
    print("  text:", txt[j:j+2500])
