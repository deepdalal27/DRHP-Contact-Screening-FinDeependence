"""Cross-check every extracted figure and compute ratios.

A figure is marked:
  verified   - it satisfies an accounting identity with other extracted figures
               (e.g. Total assets = Total equity and liabilities, PBT - Tax = PAT), or the same printed
               number appears again elsewhere in the DRHP against the same line item;
  mismatch   - an identity fails (the figure is held back from emails and flagged in the app);
  unverified - read from the table but not independently confirmed.

Ratios are computed only from figures, and inherit the weakest status of their inputs.
"""
import re

from .tables import norm_label

TO_CRORE = {"lakhs": 0.01, "million": 0.1, "crore": 1.0, None: None}


def _tol(*vals):
    return 0.06 + 1e-4 * max(abs(v) for v in vals if v is not None)


def _close(a, b):
    return a is not None and b is not None and abs(a - b) <= _tol(a, b)


def build(extracted):
    fin = extracted["financials"]
    doc = extracted.get("_doc")
    tables, picked = fin["tables"], fin["picked"]
    pl, bs, cf = picked.get("pl", {}), picked.get("bs", {}), picked.get("cf", {})
    base = tables.get("pl") or tables.get("bs")
    if not base:
        return {"ok": False, "reason": "Financial statements not found in the DRHP", "periods": [], "items": {}, "ratios": {}, "checks": []}
    periods = base["periods"]
    n = len(periods)
    unit = base.get("unit") or (tables.get("bs") or {}).get("unit")

    items = {}

    def add(key, row, label, stmt):
        if not row:
            return
        vals = (row["values"] + [None] * n)[:n]
        items[key] = {"label": label, "drhp_label": row["label"], "statement": stmt, "values": vals,
                      "raw": (row["raw"] + [None] * n)[:n], "page": row.get("page"), "line": row.get("line"),
                      "status": ["unverified"] * n, "notes": [[] for _ in range(n)]}

    names = {
        "revenue": "Revenue from operations", "other_income": "Other income", "total_income": "Total income",
        "total_expenses": "Total expenses", "finance_cost": "Finance cost", "depreciation": "Depreciation & amortisation",
        "pbt_before_exceptional": "Profit before exceptional items & tax", "pbt": "Profit before tax", "tax": "Total tax expense",
        "pat": "Profit after tax (PAT)", "eps_basic": "EPS – basic (₹)", "eps_diluted": "EPS – diluted (₹)",
        "total_assets": "Total assets", "share_capital": "Equity share capital", "other_equity": "Other equity",
        "total_equity": "Net worth (total equity)", "total_equity_liabilities": "Total equity & liabilities",
        "inventories": "Inventories", "trade_receivables": "Trade receivables", "cash": "Cash & cash equivalents",
        "current_assets": "Total current assets", "current_liabilities": "Total current liabilities",
        "cfo": "Net cash from operating activities", "cfi": "Net cash from investing activities", "cff": "Net cash from financing activities",
    }
    for stmt, src in (("P&L", pl), ("Balance sheet", bs), ("Cash flow", cf)):
        for key, row in src.items():
            if key in names:
                add(key, row, names[key], stmt)

    # derived inputs
    if "tax" not in items and pl.get("tax_rows"):
        vals = [sum((r["values"][j] or 0) for r in pl["tax_rows"]) if j < n else None for j in range(n)]
        items["tax"] = {"label": "Total tax expense", "drhp_label": " + ".join(r["label"] for r in pl["tax_rows"]), "statement": "P&L",
                        "values": vals, "raw": [None] * n, "page": pl["tax_rows"][0].get("page"), "line": None,
                        "status": ["unverified"] * n, "notes": [["sum of tax lines"] for _ in range(n)]}
    if bs.get("borrowings_rows"):
        rows = bs["borrowings_rows"]
        vals = [sum((r["values"][j] or 0) for r in rows) for j in range(n)]
        items["borrowings"] = {"label": "Total borrowings", "drhp_label": " + ".join(f'{r["label"]} ({r.get("section") or "—"})' for r in rows),
                               "statement": "Balance sheet", "values": vals, "raw": [None] * n, "page": rows[0].get("page"),
                               "line": None, "status": ["unverified"] * n, "notes": [["sum of borrowing lines"] for _ in range(n)]}

    checks = []

    def v(key, j):
        it = items.get(key)
        return it["values"][j] if it and j < len(it["values"]) else None

    def mark(keys, j, ok, note):
        for k in keys:
            if k in items:
                st = items[k]["status"]
                if ok and st[j] != "mismatch":
                    st[j] = "verified"
                elif not ok:
                    st[j] = "mismatch"
                items[k]["notes"][j].append(note)

    for j in range(n):
        p = periods[j]["label"]
        a, b = v("total_assets", j), v("total_equity_liabilities", j)
        if a is not None and b is not None:
            ok = _close(a, b)
            checks.append({"period": p, "check": "Total assets = Total equity & liabilities", "ok": ok, "lhs": a, "rhs": b})
            mark(["total_assets", "total_equity_liabilities"], j, ok, "balance sheet balances" if ok else "balance sheet does not balance")
        r, oi, ti = v("revenue", j), v("other_income", j), v("total_income", j)
        if None not in (r, oi, ti):
            ok = _close(r + oi, ti)
            checks.append({"period": p, "check": "Revenue + Other income = Total income", "ok": ok, "lhs": r + oi, "rhs": ti})
            mark(["revenue", "other_income", "total_income"], j, ok, "adds up to total income" if ok else "does not add up to total income")
        pbt, tax, pat = v("pbt", j), v("tax", j), v("pat", j)
        if None not in (pbt, tax, pat):
            ok = _close(pbt - tax, pat)
            checks.append({"period": p, "check": "Profit before tax − Tax = Profit after tax", "ok": ok, "lhs": pbt - tax, "rhs": pat})
            mark(["pbt", "tax", "pat"], j, ok, "PBT − tax = PAT" if ok else "PBT − tax ≠ PAT")
        te, sc, oe = v("total_equity", j), v("share_capital", j), v("other_equity", j)
        if None not in (te, sc, oe):
            ok = _close(sc + oe, te)
            checks.append({"period": p, "check": "Share capital + Other equity = Net worth", "ok": ok, "lhs": sc + oe, "rhs": te, "soft": True})
            if ok:
                mark(["total_equity", "share_capital", "other_equity"], j, True, "share capital + other equity = net worth")
        ti, tx, pb = v("total_income", j), v("total_expenses", j), v("pbt_before_exceptional", j)
        if None not in (ti, tx, pb) and _close(ti - tx, pb):
            checks.append({"period": p, "check": "Total income − Total expenses = Profit before exceptional items", "ok": True, "lhs": ti - tx, "rhs": pb, "soft": True})
            mark(["total_expenses", "pbt_before_exceptional"], j, True, "income − expenses = profit")

    # the same printed number appears elsewhere in the DRHP (restated statements, KPIs, MD&A) on a matching line
    if doc is not None:
        kw = {"revenue": r"revenue from operations", "pat": r"profit|pat\b", "total_assets": r"total assets",
              "total_equity": r"total equity|net ?worth", "cfo": r"operating activities", "total_income": r"total income",
              "pbt": r"before tax", "eps_basic": r"basic|eps", "finance_cost": r"finance cost", "depreciation": r"depreciation",
              "borrowings": r"borrowings", "trade_receivables": r"trade receivables", "cash": r"cash and cash|cash & cash",
              "inventories": r"inventor"}
        index = {}
        for i, ln in enumerate(doc.lines):
            for tok in re.findall(r"\(?\d[\d,]*\.\d{2}\)?", ln):
                index.setdefault(tok, []).append(i)
        for key, pat in kw.items():
            it = items.get(key)
            if not it:
                continue
            own = it.get("line")
            for j in range(n):
                raw = it["raw"][j] if it["raw"][j] else (_fmt_indian(it["values"][j]) if it["values"][j] is not None else None)
                if not raw or not re.search(r"\.\d{2}", raw) or abs(it["values"][j] or 0) < 1:
                    continue
                hits = []
                for i in index.get(raw, []):
                    if own is not None and abs(i - own) < 3:
                        continue
                    if re.search(pat, doc.lines[i], re.I) or re.search(pat, " ".join(doc.lines[max(0, i - 2):i]), re.I):
                        hits.append(doc.page_of_line(i))
                if hits:
                    pages = sorted(set(hits))[:3]
                    if it["status"][j] != "mismatch":
                        it["status"][j] = "verified"
                    it["notes"][j].append("also printed on page " + ", ".join(map(str, pages)))

    # KPI table cross-check (as stated in "Basis for Offer Price")
    kpi = extracted.get("kpi")
    stated = []
    if kpi:
        for r in kpi["rows"]:
            stated.append({"label": r["label"], "values": r["values"], "raw": r["raw"], "page": r.get("page")})

    ratios = compute_ratios(items, periods)
    if kpi:
        kpi_crosscheck(items, ratios, periods, kpi)
    to_cr = TO_CRORE.get(unit)
    core = ["revenue", "pat", "total_assets", "total_equity"]
    core_ok = all(k in items for k in core) and not any(
        "mismatch" in items[k]["status"] for k in core if k in items)
    return {
        "ok": True, "source": fin.get("source"), "unit": unit, "to_crore": to_cr, "periods": periods,
        "items": items, "ratios": ratios, "checks": checks, "kpi_stated": stated,
        "kpi_page": kpi.get("page") if kpi else None, "kpi_periods": kpi.get("periods") if kpi else None,
        "pages": {k: t.get("page") for k, t in tables.items()},
        "core_verified": core_ok and all(items[k]["status"][_latest_full(periods)] == "verified" for k in core if k in items),
    }


def _latest_full(periods):
    for j, p in enumerate(periods):
        if not p.get("stub"):
            return j
    return 0


def _fmt_indian(x):
    neg = x < 0
    x = abs(x)
    s = f"{x:.2f}"
    whole, dec = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        whole = head + "," + tail
    s = whole + "." + dec
    return f"({s})" if neg else s


def _period_days(p, prev_iso=None):
    if not p.get("stub"):
        return 365
    m = int(p["iso"][5:7]) if p.get("iso") else 12
    return {6: 91, 9: 183, 12: 275}.get(m, 365)


def compute_ratios(items, periods):
    n = len(periods)

    def g(key, j):
        it = items.get(key)
        return it["values"][j] if it and it["values"][j] is not None else None

    def st(*keys_j):
        sts = []
        for key, j in keys_j:
            it = items.get(key)
            sts.append(it["status"][j] if it else "missing")
        if "missing" in sts:
            return None
        if "mismatch" in sts:
            return "mismatch"
        return "verified" if all(s == "verified" for s in sts) else "unverified"

    out = {}

    def put(name, j, val, status, fmt, formula):
        if val is None or status is None:
            return
        out.setdefault(name, {"values": [None] * n, "status": [None] * n, "fmt": fmt, "formula": formula})
        out[name]["values"][j] = val
        out[name]["status"][j] = status

    full = [j for j in range(n) if not periods[j].get("stub")]
    for j in range(n):
        rev, pat = g("revenue", j), g("pat", j)
        pbt = g("pbt_before_exceptional", j) if g("pbt_before_exceptional", j) is not None else g("pbt", j)
        pbt_key = "pbt_before_exceptional" if g("pbt_before_exceptional", j) is not None else "pbt"
        fc, dep, oi = g("finance_cost", j), g("depreciation", j), g("other_income", j)
        te, bor = g("total_equity", j), g("borrowings", j)
        if None not in (pbt, fc, dep, oi) and rev:
            e = pbt + fc + dep - oi
            put("EBITDA", j, e, st((pbt_key, j), ("finance_cost", j), ("depreciation", j), ("other_income", j)), "amount",
                "PBT before exceptional items + Finance cost + D&A − Other income")
            put("EBITDA margin", j, e / rev, st((pbt_key, j), ("finance_cost", j), ("depreciation", j), ("other_income", j), ("revenue", j)), "pct", "EBITDA ÷ Revenue from operations")
        if rev and pat is not None:
            put("PAT margin", j, pat / rev, st(("pat", j), ("revenue", j)), "pct", "PAT ÷ Revenue from operations")
        if te and pat is not None:
            put("RoNW (closing)", j, pat / te, st(("pat", j), ("total_equity", j)), "pct",
                "PAT ÷ closing net worth" + (" (not annualised)" if periods[j].get("stub") else ""))
        if te and bor is not None:
            put("Debt / Equity", j, bor / te, st(("borrowings", j), ("total_equity", j)), "x", "Total borrowings ÷ Net worth")
        if te is not None and bor is not None and pbt is not None and fc is not None and (te + bor):
            put("RoCE (closing)", j, (pbt + fc) / (te + bor), st((pbt_key, j), ("finance_cost", j), ("total_equity", j), ("borrowings", j)), "pct",
                "(PBT + Finance cost) ÷ (Net worth + Borrowings)" + (" (not annualised)" if periods[j].get("stub") else ""))
        if fc and pbt is not None:
            put("Interest coverage", j, (pbt + fc) / fc, st((pbt_key, j), ("finance_cost", j)), "x", "(PBT + Finance cost) ÷ Finance cost")
        ca, cl = g("current_assets", j), g("current_liabilities", j)
        if ca is not None and cl:
            put("Current ratio", j, ca / cl, st(("current_assets", j), ("current_liabilities", j)), "x", "Current assets ÷ Current liabilities")
        tr = g("trade_receivables", j)
        if tr is not None and rev:
            put("Receivable days", j, tr / rev * _period_days(periods[j]), st(("trade_receivables", j), ("revenue", j)), "days",
                "Trade receivables ÷ Revenue × days in period")
        ta = g("total_assets", j)
        if ta and rev and not periods[j].get("stub"):
            put("Asset turnover", j, rev / ta, st(("revenue", j), ("total_assets", j)), "x", "Revenue ÷ Total assets")
    # growth between consecutive full years (columns are newest first)
    for a, b in zip(full, full[1:]):
        for key, name in (("revenue", "Revenue growth"), ("pat", "PAT growth")):
            x, y = g(key, a), g(key, b)
            if x is not None and y and y > 0:
                put(name, a, x / y - 1, st((key, a), (key, b)), "pct", f"{periods[a]['label']} vs {periods[b]['label']}")
        if "EBITDA" in out:
            x, y = out["EBITDA"]["values"][a], out["EBITDA"]["values"][b]
            if x is not None and y and y > 0:
                s = "verified" if out["EBITDA"]["status"][a] == out["EBITDA"]["status"][b] == "verified" else "unverified"
                put("EBITDA growth", a, x / y - 1, s, "pct", f"{periods[a]['label']} vs {periods[b]['label']}")
    # CAGR over the full-year span
    if len(full) >= 3:
        a, b = full[0], full[-1]
        x, y = g("revenue", a), g("revenue", b)
        yrs = len(full) - 1
        if x and y and x > 0 and y > 0:
            put(f"Revenue CAGR ({yrs} yr)", a, (x / y) ** (1 / yrs) - 1, st(("revenue", a), ("revenue", b)), "pct",
                f"{periods[b]['label']} → {periods[a]['label']}")
    return out


KPI_MAP = [
    ("item", "revenue", r"^revenue from operations"),
    ("item", "pat", r"^(?:restated )?(?:profit after tax|pat\b|net profit|profit for the (?:year|period))"),
    ("item", "total_equity", r"^net ?worth|^total equity"),
    ("item", "borrowings", r"^total borrowings|^borrowings"),
    ("ratio", "EBITDA", r"^(?:operating )?ebitda(?! margin)"),
    ("ratio", "EBITDA margin", r"^(?:operating )?ebitda margin"),
    ("ratio", "PAT margin", r"^(?:pat|net profit|profit after tax) margin"),
    ("ratio", "Debt / Equity", r"^(?:net )?debt[- ]?(?:to[- ])?equity"),
    ("ratio", "Revenue growth", r"^(?:growth in revenue|revenue growth)"),
]


def kpi_crosscheck(items, ratios, periods, kpi):
    """Match each KPI row in 'Basis for Offer Price' to our own figure for the same period."""
    kp = kpi.get("periods") or []
    col = {}
    for j, p in enumerate(periods):
        for k, q in enumerate(kp):
            if p.get("iso") and p.get("iso") == q.get("iso"):
                col[j] = k
    for kind, key, pat in KPI_MAP:
        tgt = (items if kind == "item" else ratios).get(key)
        if not tgt:
            continue
        for r in kpi["rows"]:
            lab = norm_label(r["label"])
            if not re.search(pat, lab) or (key == "Debt / Equity" and lab.startswith("net")):
                continue
            pct = "%" in " ".join(x or "" for x in r.get("raw", [])) or "margin" in lab or "growth" in lab or "(%)" in r["label"]
            for j, k in col.items():
                ours = tgt["values"][j]
                theirs = r["values"][k] if k < len(r["values"]) else None
                if ours is None or theirs is None:
                    continue
                if kind == "ratio" and tgt.get("fmt") == "pct":
                    ok = abs(ours * 100 - theirs) <= 0.06 if pct or abs(theirs) > 1.5 else abs(ours - theirs) <= 0.0006
                elif kind == "ratio" and tgt.get("fmt") == "x":
                    ok = abs(ours - theirs) <= 0.006
                else:
                    ok = abs(ours - theirs) <= _tol(ours, theirs)
                notes = tgt["notes"][j] if "notes" in tgt else tgt.setdefault("notes", [[] for _ in periods])[j]
                if ok:
                    if tgt["status"][j] != "mismatch":
                        tgt["status"][j] = "verified"
                    notes.append(f"matches DRHP KPI table (page {r.get('page')})")
                else:
                    notes.append(f"DRHP KPI table shows {r['raw'][k]} (page {r.get('page')}) – definition may differ")
            break
