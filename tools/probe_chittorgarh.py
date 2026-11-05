"""Diagnostic run in GitHub Actions: fund profile PDF download from Drive, and the BSE SME (Chittorgarh) source."""
import json, sys
sys.path.insert(0, ".")
from pipeline import sources as S, mailer
prof = json.load(open("config/settings.json"))["fund_profile"]
pdf = mailer.fund_profile_pdf(prof)
print("fund profile:", "OK %d bytes" % len(pdf) if pdf else "FAILED")
rows = S.bse_sme_filings()
print("BSE SME filings via Chittorgarh:", len(rows), S.ERRORS)
