"""Diagnostic: run the BSE SME (Chittorgarh) source on GitHub's servers and print what it extracts."""
import json, sys
sys.path.insert(0, ".")
from pipeline import sources as S
rows = S.bse_sme_filings()
print("BSE SME filings:", len(rows), S.ERRORS)
rows.sort(key=lambda r: r["filed_on"] or "", reverse=True)
for r in rows[:5]:
    print("##", r["company"], r["filed_on"], r["status"], r["lead_manager"], r["page_url"])
    d = S.chittorgarh_details(r["page_url"])
    print(json.dumps(d, indent=1, ensure_ascii=False)[:2500])
