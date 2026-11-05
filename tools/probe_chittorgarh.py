"""Diagnostic: capture the JSON calls Chittorgarh's report pages make (run in GitHub Actions)."""
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    def on_resp(r):
        ct = r.headers.get("content-type", "")
        if "json" in ct or "webnodejs" in r.url or "/api/" in r.url:
            try:
                body = r.text()
            except Exception as e:
                body = f"<{e}>"
            print(f"  RESP {r.status} {r.request.method} {r.url}\n    {body[:1500]}")
    pg.on("response", on_resp)
    for u in sys.argv[1:]:
        print("=== ", u)
        pg.goto(u, wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(4000)
        rows = pg.eval_on_selector_all("table tr", "els => els.slice(0,6).map(e => e.innerText.replace(/\\s+/g,' ') + ' || ' + [...e.querySelectorAll('a')].map(a=>a.href).join(' '))")
        for r in rows:
            print("  ROW", r[:400])
    b.close()
