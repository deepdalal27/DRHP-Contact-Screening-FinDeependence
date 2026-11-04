"""Find new DRHPs, extract them, publish the data for the webapp and (once approved) send the emails.

    python -m pipeline.run                 # normal scheduled run
    python -m pipeline.run --url <pdf|zip> --company "Name Limited" --board SME   # one document by hand
    python -m pipeline.run --no-send       # never send, only build data and drafts

Sending happens only when config/settings.json has "sending": {"approved": true} AND the
GMAIL_ADDRESS / GMAIL_APP_PASSWORD environment variables (GitHub secrets) are set.
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import traceback
import zipfile
from pathlib import Path

from . import sources, mailer
from .extract import extract
from .validate import build
from .compose import summarise_business, short_name

ROOT = Path(__file__).resolve().parent.parent
SITE_DATA = ROOT / "site" / "data"
COMPANIES = SITE_DATA / "companies"
CACHE = ROOT / ".cache"
STATE = ROOT / "data" / "state.json"
OUTREACH = SITE_DATA / "outreach.json"
SUPPRESS = ROOT / "config" / "suppression.txt"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def now():
    return dt.datetime.now(IST).isoformat(timespec="seconds")


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def download_pdf(filing):
    url = filing.get("url")
    if not url and filing.get("page_url"):
        url = sources.sebi_pdf_url(filing["page_url"])
        filing["url"] = url
    if not url:
        raise RuntimeError("no document link")
    CACHE.mkdir(exist_ok=True)
    data = sources.http_get(url, referer=filing.get("page_url") or "https://www.nseindia.com/", timeout=300)
    path = CACHE / (filing["key"] + ".pdf")
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        pdfs = sorted((i for i in z.infolist() if i.filename.lower().endswith(".pdf")), key=lambda i: i.file_size, reverse=True)
        if not pdfs:
            raise RuntimeError("zip has no PDF")
        data = z.read(pdfs[0])
    if data[:4] != b"%PDF":
        raise RuntimeError("download is not a PDF")
    path.write_bytes(data)
    return path


def scale_fin(fin):
    """Financials in ₹ crore for the webapp, with statuses and DRHP page references."""
    if not fin.get("ok"):
        return {"ok": False, "reason": fin.get("reason")}
    k = fin.get("to_crore")
    items = {}
    for key, it in fin["items"].items():
        mult = 1 if key.startswith("eps") else k
        items[key] = {"label": it["label"], "drhp_label": it["drhp_label"], "statement": it["statement"], "page": it["page"],
                      "values": [None if v is None or mult is None else round(v * mult, 4) for v in it["values"]],
                      "raw": it["raw"], "status": it["status"], "notes": it["notes"]}
    ratios = {}
    for name, r in fin["ratios"].items():
        mult = k if r["fmt"] == "amount" else 1
        ratios[name] = {**r, "values": [None if v is None or mult is None else round(v * mult, 6) for v in r["values"]]}
    return {"ok": True, "unit_in_drhp": fin["unit"], "source": fin["source"], "periods": fin["periods"], "items": items,
            "ratios": ratios, "checks": fin["checks"], "kpi_stated": fin["kpi_stated"], "kpi_periods": fin.get("kpi_periods"),
            "kpi_page": fin["kpi_page"], "pages": fin["pages"], "core_verified": fin["core_verified"]}


def build_record(filing, rec, fin, sender, suppressed):
    cover = rec["cover"]
    name = filing.get("company") or cover.get("company")
    if name and name.isupper():
        name = " ".join(w if (len(w) <= 3 and w not in ("AND", "OF", "THE")) else w.title() for w in name.split())
    rec["display_name"] = name
    rec["exchange_filed"] = {"NSE Emerge": "NSE (Emerge)", "BSE SME": "BSE (SME)"}.get(filing.get("source"))
    if filing.get("board") == "SME":
        cover["board"] = "SME"
        cover["exchange"] = cover.get("exchange") or ("NSE Emerge" if filing.get("source") == "NSE Emerge" else "BSE SME")
    msgs = mailer.choose_recipients(rec, suppressed)
    emails = [mailer.compose(rec, fin, sender, m) for m in msgs]
    desig = rec.get("designations") or {}
    pemails = rec.get("promoter_emails") or {}
    warnings = []
    if not fin.get("ok"):
        warnings.append(fin.get("reason"))
    elif not fin.get("core_verified"):
        warnings.append("Some core figures could not be cross-checked; only verified figures are used in the email.")
    if not msgs:
        warnings.append("No usable email found for promoters, BRLM or the company.")
    return {
        "key": filing["key"], "company": name, "short": short_name(name), "board": cover.get("board"), "exchange": cover.get("exchange"),
        "source": filing.get("source"), "also_on": filing.get("also_on", []), "filed_on": filing.get("filed_on"),
        "doc_type": filing.get("doc_type"), "document_type": cover.get("document_type"), "document_date": cover.get("document_date"),
        "doc_url": filing.get("url"), "page_url": filing.get("page_url"), "pages": rec.get("pages"),
        "cin": cover.get("cin"), "website": cover.get("website"), "icdr_regulation": cover.get("icdr_regulation"),
        "fresh_issue": cover.get("fresh_issue"), "ofs": cover.get("ofs"),
        "pre_ipo_placement": cover.get("pre_ipo_placement"), "pre_ipo_limit_pct": cover.get("pre_ipo_limit_pct"),
        "promoters": [{"name": p, "designation": desig.get(p), "emails": [e["email"] for e in pemails.get(p, [])]} for p in cover.get("promoters") or []],
        "cs": (rec.get("general") or {}).get("cs"), "brlms": (rec.get("general") or {}).get("brlms") or [],
        "registrar": (rec.get("general") or {}).get("registrar"),
        "business": rec.get("business"), "business_summary": summarise_business((rec.get("business") or {}).get("text"), name),
        "financials": scale_fin(fin), "emails": emails, "warnings": warnings, "processed_at": now(),
    }


def write_index(records):
    idx = []
    for r in records:
        f = r.get("financials") or {}
        latest = {}
        if f.get("ok"):
            j = next((k for k, p in enumerate(f["periods"]) if not p.get("stub")), 0)
            for key in ("revenue", "pat", "total_equity"):
                it = f["items"].get(key)
                if it:
                    latest[key] = {"v": it["values"][j], "s": it["status"][j]}
            for key in ("EBITDA margin", "PAT margin", "RoNW (closing)", "Debt / Equity", "Revenue growth"):
                it = f["ratios"].get(key)
                if it:
                    latest[key] = {"v": it["values"][j], "s": it["status"][j]}
            latest["fy"] = f["periods"][j]["label"]
        idx.append({"key": r["key"], "company": r["company"], "board": r["board"], "exchange": r.get("exchange"), "source": r["source"],
                    "filed_on": r["filed_on"], "doc_type": r["doc_type"], "brlms": [b.get("name") for b in r["brlms"]],
                    "promoters": [p["name"] for p in r["promoters"]], "pre_ipo": r["pre_ipo_placement"], "latest": latest,
                    "verified": (f or {}).get("core_verified"), "warnings": r["warnings"], "processed_at": r["processed_at"]})
    idx.sort(key=lambda x: x.get("filed_on") or "", reverse=True)
    save(SITE_DATA / "index.json", {"updated_at": now(), "companies": idx})


def outreach_entries(record, mail, status, message_id=None, error=None):
    """One row per recipient address: everything needed to follow up later."""
    rows = []
    brlm = next((b for b in record["brlms"] if b.get("name") == mail.get("brlm")), None)
    for addr in mail["to"]:
        if mail["variant"] == "brlm" and brlm:
            role, org, phones = "BRLM contact", brlm.get("name"), brlm.get("phones", [])
        elif mail["variant"] == "company":
            role, org, phones = "Company Secretary / IR", record["company"], (record.get("cs") or {}).get("phones", [])
        else:
            role, org, phones = "Promoter", record["company"], []
        rows.append({
            "id": f"{record['key']}|{addr}", "company_key": record["key"], "company": record["company"], "board": record["board"],
            "filed_on": record["filed_on"], "variant": mail["variant"], "role": role, "organisation": org,
            "names": mail.get("names", []), "email": addr, "phones": phones, "subject": mail["subject"], "status": status,
            "sent_at": now() if status == "sent" else None, "created_at": now(), "message_id": message_id, "error": error,
            "promoters": [p["name"] for p in record["promoters"]],
            "brlm_contacts": [{"firm": b.get("name"), "people": b.get("contact_persons"), "emails": b.get("emails"),
                               "phones": b.get("phones")} for b in record["brlms"]],
            "cs": record.get("cs"), "website": record.get("website"), "doc_url": record.get("doc_url") or record.get("page_url"),
        })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--company")
    ap.add_argument("--board", default="Mainboard")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--max-docs", type=int, default=int(os.environ.get("MAX_DOCS", "12")))
    args = ap.parse_args(argv)

    settings = load(ROOT / "config" / "settings.json", {})
    sender = settings["sender"]
    sending = settings.get("sending", {})
    suppressed = [x.strip().lower() for x in (SUPPRESS.read_text().splitlines() if SUPPRESS.exists() else []) if x.strip() and not x.startswith("#")]
    state = load(STATE, {"processed": {}})
    outreach = load(OUTREACH, {"entries": []})
    user, pw = mailer.credentials()
    can_send = bool(sending.get("approved")) and user and pw and not args.no_send
    print(f"Sending: {'ON' if can_send else 'OFF'} (approved={sending.get('approved')}, credentials={'yes' if user else 'no'})")

    if args.url:
        filings = [{"source": "Manual", "company": args.company or "", "board": args.board, "filed_on": dt.date.today().isoformat(),
                    "doc_type": "DRHP", "url": args.url, "page_url": None, "key": sources.company_key(args.company or args.url)}]
    else:
        filings = sources.all_filings(settings.get("lookback_days", 45))
        print(f"Found {len(filings)} draft filings. Source errors: {sources.ERRORS}")

    COMPANIES.mkdir(parents=True, exist_ok=True)
    done = 0
    sent_today = sum(1 for e in outreach["entries"] if e.get("status") == "sent" and (e.get("sent_at") or "")[:10] == now()[:10])
    already = {(e["company_key"], e["email"]) for e in outreach["entries"] if e.get("status") == "sent"}
    for f in filings:
        prev = state["processed"].get(f["key"])
        if prev and prev.get("ref") == (f.get("url") or f.get("page_url")) and not args.url:
            continue
        if done >= args.max_docs:
            break
        done += 1
        print(f"→ {f['company']} ({f['source']}, {f['filed_on']})")
        try:
            pdf = download_pdf(f)
            rec = extract(pdf)
            fin = build(rec)
            rec.pop("_doc", None)
            record = build_record(f, rec, fin, sender, suppressed)
        except Exception as e:
            traceback.print_exc()
            state["processed"][f["key"]] = {"ref": f.get("url") or f.get("page_url"), "error": str(e)[:300], "at": now(), "company": f["company"]}
            continue
        finally:
            for p in CACHE.glob("*.pdf"):
                p.unlink()
        save(COMPANIES / f"{record['key']}.json", record)
        state["processed"][f["key"]] = {"ref": f.get("url") or f.get("page_url"), "at": now(), "company": record["company"]}

        for mail in record["emails"]:
            todo = [a for a in mail["to"] if (record["key"], a) not in already]
            if not todo:
                continue
            mail = {**mail, "to": todo}
            # replace any earlier draft rows for these addresses
            ids = {f"{record['key']}|{a}" for a in todo}
            outreach["entries"] = [e for e in outreach["entries"] if e["id"] not in ids]
            if can_send and sent_today < sending.get("daily_cap", 40):
                try:
                    mid = mailer.send(mail, sender, user, pw)
                    outreach["entries"] += outreach_entries(record, mail, "sent", message_id=mid)
                    sent_today += 1
                    already |= {(record["key"], a) for a in todo}
                    print(f"   sent to {', '.join(todo)}")
                except Exception as e:
                    outreach["entries"] += outreach_entries(record, mail, "failed", error=str(e)[:300])
                    print(f"   send failed: {e}")
            else:
                outreach["entries"] += outreach_entries(record, mail, "awaiting approval" if not sending.get("approved") else "queued")

    records = [load(p, None) for p in sorted(COMPANIES.glob("*.json"))]
    write_index([r for r in records if r])
    outreach["updated_at"] = now()
    save(OUTREACH, outreach)
    save(STATE, state)
    print(f"Processed {done} document(s).")


if __name__ == "__main__":
    sys.exit(main())
