"""Parse column tables (restated financial statements, KPI tables) from `pdftotext -layout` text.

A data row is a line whose right-hand side is a run of numeric cells, each separated from the
previous token by at least two spaces. Column positions come from the rows themselves, and header
text above the first row is assigned to the nearest column so that wrapped headers such as
"As on March / 31, 2026" still resolve to one period per column.
"""
import re
from collections import Counter

from .textutil import numeric_cells, clean

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MON_ABBR = {k[:3]: v for k, v in MONTHS.items()}


_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_UNIT_RE = re.compile(
    r"(?i)" + _MON + r"\.?\s*\d{1,2}(?:st|nd|rd|th)?\s*,?\s*(?:\d{4})?"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+" + _MON + r",?\s*(?:\d{4})?"
    r"|\b\d{1,2}[./-]\d{2}[./-]\d{4}\b"
    r"|(?:fiscal|fy)\s*'?\d{2,4}(?:\s*[-–]\s*\d{2,4})?"
    r"|\b\d{1,2},\s*\d{4}\b|\b(?:19|20)\d{2}\b")


def trailing_cells(line):
    """Numeric cells at the end of the line, each preceded by >= 2 spaces (or a tab-like gap)."""
    cells = numeric_cells(line)
    run = []
    pos = len(line.rstrip())
    for c in reversed(cells):
        start, end, v, raw = c
        between = line[end:pos]
        if between.strip() not in ("", "%"):
            break
        before = line[:start]
        gap = len(before) - len(before.rstrip())
        lead = before.rstrip()
        if lead and gap < 2:
            # a single space separates this "number" from text: it is part of the label (e.g. "Note 5", "(1)")
            break
        run.append(c)
        pos = start
    run.reverse()
    return run


def parse_period(text):
    """Return (iso_date, label, is_stub) from a header cell, or None.

    Header cells are often wrapped ("As at / March 31, / 2026"), so the month, day and year are
    found independently inside the cell text."""
    t = clean(text).lower()
    mm = re.search(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b", t)
    ym = re.search(r"\b((?:19|20)\d{2})\b", t)
    if mm and ym:
        mon = MON_ABBR[mm.group(1)[:3]]
        rest = t[:ym.start()] + " " + t[ym.end():]
        dm = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", rest)
        day = int(dm.group(1)) if dm and int(dm.group(1)) <= 31 else None
        yr = int(ym.group(1))
        if day is None:
            day = {2: 28, 4: 30, 6: 30, 9: 30, 11: 30}.get(mon, 31)
        iso = f"{yr:04d}-{mon:02d}-{day:02d}"
        if mon == 3:
            return (iso, f"FY{str(yr)[2:]}", False)
        abbr = [k for k, v in MON_ABBR.items() if v == mon][0].title()
        return (iso, f"{abbr}-{str(yr)[2:]}", True)
    m3 = re.search(r"(\d{2})[./-](\d{2})[./-](\d{4})", t)
    if m3:
        day, mon, yr = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
        if mon == 3:
            return (f"{yr}-03-{day:02d}", f"FY{str(yr)[2:]}", False)
        abbr = [k for k, v in MON_ABBR.items() if v == mon][0].title()
        return (f"{yr}-{mon:02d}-{day:02d}", f"{abbr}-{str(yr)[2:]}", True)
    m4 = re.search(r"(?:fiscal|fy|financial year)\s*'?(\d{4})(?:\s*[-–]\s*(\d{2,4}))?", t)
    if m4:
        yr = int(m4.group(1))
        if m4.group(2):
            y2 = m4.group(2)
            yr = int(y2) if len(y2) == 4 else int(str(yr)[:2] + y2)
        return (f"{yr}-03-31", f"FY{str(yr)[2:]}", False)
    m5 = re.search(r"\bfy\s*'?(\d{2})\b", t)
    if m5:
        return (f"20{m5.group(1)}-03-31", f"FY{m5.group(1)}", False)
    if ym:  # a bare year under "Fiscal" / "year ended" headings: Indian fiscal years end on March 31
        yr = int(ym.group(1))
        return (f"{yr}-03-31", f"FY{str(yr)[2:]}", False)
    return None


def parse_table(lines, first_line_no=0, page_of=None, max_header_lines=14):
    """lines: list[str] layout text. Returns dict(periods, rows, ncols)."""
    parsed = []
    for i, ln in enumerate(lines):
        cells = trailing_cells(ln)
        if cells and all(re.fullmatch(r"(?:19|20)\d{2}", c[3]) for c in cells):
            cells = []  # a line of years is a header, not data
        parsed.append(cells)
    counts = Counter(len(c) for c in parsed if len(c) >= 2)
    if not counts:
        return {"periods": [], "rows": [], "ncols": 0}
    ncols = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    ends = [[] for _ in range(ncols)]
    for c in parsed:
        if len(c) == ncols:
            for j, cell in enumerate(c):
                ends[j].append(cell[1])
    col_end = [sorted(e)[len(e) // 2] for e in ends]
    starts = [[] for _ in range(ncols)]
    for c in parsed:
        if len(c) == ncols:
            for j, cell in enumerate(c):
                starts[j].append(cell[0])
    col_start = [sorted(x)[len(x) // 2] for x in starts]

    def col_of(end):
        return min(range(ncols), key=lambda j: abs(col_end[j] - end))

    first_row = next((i for i, c in enumerate(parsed) if len(c) >= max(2, ncols - 1)), None)
    # header text -> columns: each phrase (split on 2+ spaces) goes to the column whose span centre is nearest
    header_cols = [""] * ncols
    h0 = max(0, (first_row or 0) - max_header_lines)
    label_edge = min(min(x) for x in starts) - 6  # header text can sit a little left of the numbers
    centres = [(col_start[j] + col_end[j]) / 2 for j in range(ncols)]
    spacing = min([centres[k + 1] - centres[k] for k in range(ncols - 1)] or [40])
    section = ""
    for ln in lines[h0:first_row or 0]:
        if re.search(r"\b(non[- ]?current|current)\s+(assets|liabilities)\b", ln, re.I) and len(clean(ln)) < 60:
            section = clean(ln)
        units = []
        taken = [False] * len(ln)
        for m in DATE_UNIT_RE.finditer(ln):
            units.append((m.start(), m.end(), m.group(0)))
            for k in range(m.start(), m.end()):
                taken[k] = True
        rest = "".join(" " if taken[k] else ch for k, ch in enumerate(ln))
        for m in re.finditer(r"\S+(?: \S+)*", rest):
            if m.end() - m.start() <= spacing * 0.9:
                units.append((m.start(), m.end(), m.group(0)))
        prev_date_col = -1
        for a, b, txt in sorted(units):
            if b < label_edge:
                continue
            mid = (a + b) / 2
            j = min(range(ncols), key=lambda k: abs(centres[k] - mid))
            if DATE_UNIT_RE.fullmatch(txt):
                # dates on one line read left to right, one per column
                if j <= prev_date_col and prev_date_col + 1 < ncols:
                    j = prev_date_col + 1
                prev_date_col = j
            header_cols[j] += " " + txt
    periods = []
    for j in range(ncols):
        p = parse_period(header_cols[j])
        periods.append({"iso": p[0], "label": p[1], "stub": p[2]} if p else {"iso": None, "label": clean(header_cols[j])[-20:] or f"Col{j + 1}", "stub": False})

    drop = [j for j in range(ncols) if re.search(r"\bnotes?\b", header_cols[j], re.I)
            and all((c[2] == int(c[2]) and abs(c[2]) < 100) for c in [x for row in parsed for x in row if len(row) == ncols and col_of(x[1]) == j])]

    rows = []
    pending = []
    for i, ln in enumerate(lines):
        cells = parsed[i]
        if i < (first_row or 0):
            continue
        if len(cells) == 0:
            txt = clean(ln)
            if txt:
                pending.append(txt)
                if re.search(r"\b(non[- ]?current|current)\s+(assets|liabilities)\b", txt, re.I) and len(txt) < 60:
                    section = txt
            continue
        if re.fullmatch(r"\s*\d{1,4}\s*", ln):  # page number
            continue
        label = clean(ln[:cells[0][0]])
        if not label:
            label = " ".join(pending[-2:]) if pending else f"Subtotal: {section}"
        values = [None] * ncols
        raws = [None] * ncols
        if len(cells) == ncols:
            for j, cell in enumerate(cells):
                values[j], raws[j] = cell[2], cell[3]
        else:
            for cell in cells:
                j = col_of(cell[1])
                values[j], raws[j] = cell[2], cell[3]
        if drop:
            values = [v for j, v in enumerate(values) if j not in drop]
            raws = [v for j, v in enumerate(raws) if j not in drop]
        ln_no = first_line_no + i
        rows.append({
            "label": label, "context": " | ".join(pending[-2:]), "section": section,
            "values": values, "raw": raws, "line": ln_no, "page": page_of(ln_no) if page_of else None,
        })
        pending = []
    if drop:
        periods = [p for j, p in enumerate(periods) if j not in drop]
        header_cols = [h for j, h in enumerate(header_cols) if j not in drop]
    return {"periods": periods, "rows": rows, "ncols": len(periods), "header_text": [clean(h) for h in header_cols]}


def norm_label(label):
    t = label.lower()
    t = re.sub(r"^\s*(?:[ivxlc]+\.?\s+|\(?[a-z]\)\s*|\(?[ivx]+\)\s*|\d+\.\s+|[-•]\s*)+", "", t)
    t = re.sub(r"\((?:[a-z]{1,3}|[ivx]+)\s*[-+=/]\s*[^)]*\)", "", t)  # (III-IV), (A+B)
    t = re.sub(r"\(\d\)", "", t)
    t = re.sub(r"^[a-h][.)]?\s+(?=[a-z])", "", t)                 # "A. Revenue", "a Revenue"
    t = re.sub(r"\s*[-–]\s*[a-z]$", "", t.strip())                  # "Total equity - D"
    t = re.sub(r"\s*\((?:[a-z]|[ivx]+|[a-z]\s*[-+=]\s*[a-z+\- ]+)\)$", "", t.strip())  # "(A)", "(ii)", "(C=A+B)"
    t = t.replace("&", "and")
    return clean(t)
