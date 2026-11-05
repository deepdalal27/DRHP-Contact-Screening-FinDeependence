# DRHP Contact Screener · FinDeependence

For **Parshwanath Capital Ventures Fund** (SEBI-registered Category III AIF) · CA Deep Dalal, Fund Manager.

Whenever a company files a DRHP, this app:

1. **Finds the filing.** Every 3 hours it checks SEBI's *Draft Offer Documents* page, NSE's offer-document feeds (Mainboard and NSE Emerge SME) and, for BSE SME, Chittorgarh's *Upcoming SME IPO – DRHP filed* report. BSE blocks cloud servers, so a BSE SME DRHP PDF cannot be read automatically: those companies are listed with Chittorgarh's contact details and financial snapshot (marked as not cross-checked), and their mail goes to the company's compliance email.
2. **Reads the whole DRHP PDF** and extracts:
   - company details, CIN, website, promoters and their board designations, and the business overview;
   - the **Company Secretary**, every **BRLM** (contact persons, deal email, phone, SEBI registration) and the **Registrar**;
   - the **restated financial statements** (P&L, balance sheet, cash flow), the DRHP's own KPI table, and ratios computed from the statements.
3. **Cross-checks every figure.** A figure counts as verified only when one of these holds:
   - it satisfies an accounting identity (total assets = equity + liabilities, PBT − tax = PAT, revenue + other income = total income);
   - the same printed number appears elsewhere in the DRHP;
   - it matches the DRHP's KPI table.

   Each figure shows its DRHP page number. Emails quote **only verified figures**.
4. **Sends a personalised introduction mail** from `fundmanager.pcvf@gmail.com`:
   - to the **promoters' own email** if the DRHP prints one;
   - otherwise one personalised mail **to each BRLM's deal contact**, asking them to connect us with the promoters;
   - otherwise to the **Company Secretary / IR**, asking them to forward it to the promoters.

   Each address is mailed **once only**. Addresses in `config/suppression.txt` are never mailed.
5. **Keeps an outreach report** in the webapp: whom each mail went to, for which company, their role, email and phone, the BRLM, the promoters and the DRHP link. You can track the follow-up stage, next follow-up date and notes, export everything to Excel, and browse a directory of all BRLMs and company contacts.

**Open the app:** https://deepdalal27.github.io/DRHP-Contact-Screening-FinDeependence/ (published from the `gh-pages` branch by every workflow run)

## One-time setup

1. **Gmail App Password** for `fundmanager.pcvf@gmail.com`:
   - Google Account → Security → turn on 2-Step Verification.
   - Go to https://myaccount.google.com/apppasswords → create one named "DRHP Screener" → copy the 16-character password.
2. **Repository secrets:** in the repository, go to Settings → Secrets and variables → Actions → New repository secret:
   - `GMAIL_ADDRESS` = `fundmanager.pcvf@gmail.com`
   - `GMAIL_APP_PASSWORD` = the 16-character app password
3. **GitHub Pages:** published from the `gh-pages` branch (Settings → Pages → Source: Deploy from a branch → `gh-pages` / root).
Sending is switched on (`"approved": true` in `config/settings.json`). Until the two secrets exist, mails are prepared
and shown in the app as **queued**. The first run after the secrets are added sends them (at most `daily_cap` per day).
Set `"approved": false` to pause sending at any time.

Every mail carries the fund's SEBI registration number, a **View Fund Profile** button (the Pitch Deck on Google Drive, shared view-only with anyone who has the link), and the same PDF as an attachment. Change it under `fund_profile` in `config/settings.json`.

Every mail carries the Parshwanath Capital Ventures Fund logo inline (`assets/pcvf_logo.png`). The layout uses mid-tone
gold and slate colours and the mail app's own text colour, so it reads in both light and dark mode.

## Running by hand

- **Actions → Screen new DRHPs and publish → Run workflow** runs the job now. Optionally paste a DRHP link (PDF or ZIP) to process one company, or tick *send nothing* to only refresh the data.
- Locally: `sudo apt-get install poppler-utils`, then `python -m pipeline.run --no-send`. Tests: `python -m unittest discover -s tests`.

## Files

| Path | What it is |
|---|---|
| `pipeline/sources.py` | SEBI, NSE (Mainboard and Emerge) and BSE SME filing lists |
| `pipeline/extract.py`, `tables.py` | DRHP reading: cover, contacts, financial tables |
| `pipeline/validate.py` | cross-checks and ratios |
| `pipeline/compose.py`, `mailer.py` | email wording, layout, recipients, Gmail sending |
| `pipeline/run.py` | the scheduled run |
| `config/settings.json` | sender details, fund introduction, sending switch and limits |
| `site/` | the webapp (GitHub Pages); `site/data/` is written by the workflow |

Follow-up notes you type in the Outreach tab are stored in your browser only, so use **Backup notes** now and then.
The repository is public, so `site/data/outreach.json` (who was mailed, with contacts taken from public DRHPs) is publicly readable.

## Operating guide (day to day)

| You want to… | Do this |
|---|---|
| See new DRHPs, figures and contacts | Open the app (link above). It refreshes every 3 hours. |
| See who was mailed | App → **Outreach** tab. Set the follow-up stage, next date and notes there; **Download Excel** for a copy. Use **Backup notes** now and then (notes live in your browser). |
| Pause all mailing | In `config/settings.json` set `"approved": false` under `"sending"` and commit. Set it back to `true` to resume. |
| Stop mailing one person | Add their email on a new line in `config/suppression.txt` (e.g. after an "unsubscribe" reply). |
| Change the fund profile PDF | Upload the new PDF to Drive, share it "Anyone with the link – Viewer", and put its file id in `config/settings.json` → `fund_profile.drive_file_id` and `view_url`. |
| Change the wording, contacts or SEBI no. | `config/settings.json` → `sender` (intro text, phone, WhatsApp, email, registration). Layout/wording lives in `pipeline/compose.py`. |
| Change the daily limit | `config/settings.json` → `sending.daily_cap` (default 40; Gmail allows ~500/day). |
| Run now instead of waiting | GitHub → **Actions** → *Screen new DRHPs and publish* → **Run workflow**. Optionally paste a DRHP link (PDF/ZIP) to add one company by hand. |
| Gmail password changed / mails show "failed" | Create a new App Password and update the `GMAIL_APP_PASSWORD` secret (Settings → Secrets and variables → Actions). |

Mail is sent only when `approved` is `true` **and** both secrets `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` exist. Until then mails wait as **queued** in the Outreach tab and go out on the first run after the secrets are added.
