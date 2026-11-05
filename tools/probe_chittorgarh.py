"""Diagnostic: Chittorgarh IPO page contact details; bsesme download with long timeout (run in GitHub Actions)."""
import re, urllib.request, html as H, subprocess
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://www.chittorgarh.com/"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")
for u in ["https://www.chittorgarh.com/ipo/srgnarrow-fab-ipo/3379/", "https://www.chittorgarh.com/ipo/pradeepit-global-consulting-ipo/3396/",
          "https://www.chittorgarh.com/report/ipo-lead-manager-review/99/all/76/"]:
    page = get(u)
    txt = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S))))
    print("===", u, len(page))
    print("  emails:", sorted(set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", txt)))[:15])
    for kw in ("Contact Details", "Lead Manager", "Registrar", "Promoter"):
        for m in list(re.finditer(kw, txt))[:2]:
            print(f"  [{kw}]", txt[m.start():m.start()+600])
for u in ["https://www.bsesme.com/download/379941/SME_IPO%20InPrinciple/DRHPSRGNarrowBSE_20261001001108.pdf"]:
    r = subprocess.run(["curl", "-sS", "-4", "-L", "-m", "240", "--connect-timeout", "120", "-A", UA, "-H", "Referer: https://www.bsesme.com/",
                        "-o", "/tmp/x.pdf", "-w", "%{http_code} %{size_download} %{content_type} %{time_connect}", u], capture_output=True, text=True)
    print("curl bsesme:", r.stdout, r.stderr[:300])
