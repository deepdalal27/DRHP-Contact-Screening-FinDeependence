"""PDF -> text (poppler `pdftotext`) and Indian-format number parsing.

Two text renderings of every DRHP are kept:
  * layout: columns preserved (used for financial tables)
  * raw:    reading order (used for contact blocks such as "Book Running Lead Manager")
Pages are separated by form feeds, so every extracted value can carry its page number.
"""
import re
import subprocess

NUM_RE = re.compile(r"\(?-?\s?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\)?(?!\d)")
DASH_TOKENS = {"-", "–", "—", "nil", "Nil", "NIL"}


def pdf_to_pages(pdf_path, layout=True):
    args = ["pdftotext", "-enc", "UTF-8"]
    if layout:
        args.append("-layout")
    args += [str(pdf_path), "-"]
    out = subprocess.run(args, capture_output=True, check=True, timeout=600).stdout.decode("utf-8", "replace")
    return out.split("\f")


def parse_num(tok):
    """'1,63,275.89' -> 163275.89 ; '(6,853.01)' -> -6853.01 ; '-' -> 0.0 ; otherwise None."""
    if tok is None:
        return None
    t = tok.strip().replace("₹", "").replace(" ", "")
    if t in DASH_TOKENS:
        return 0.0
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if t.startswith("-") and len(t) > 1:
        neg, t = True, t[1:]
    t = t.replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", t):
        return None
    v = float(t)
    return -v if neg else v


# A numeric cell in a layout line: optional parentheses / sign, Indian or western grouping, or a lone dash.
CELL_RE = re.compile(r"(?<![\w.%/])(\(\s?-?[\d,]+(?:\.\d+)?\s?\)|-?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|-?\d+\.\d+|-?\d+|[-–—])(?=\s|$|%)")


def numeric_cells(line):
    """Return [(start_col, end_col, value, raw)] for numeric-looking cells on a layout line."""
    cells = []
    for m in CELL_RE.finditer(line):
        raw = m.group(1)
        v = parse_num(raw)
        if v is None:
            continue
        cells.append((m.start(1), m.end(1), v, raw))
    return cells


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@\s?[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")


def find_emails(s):
    out = []
    for m in EMAIL_RE.finditer(s or ""):
        e = m.group(0).replace(" ", "").strip(".;,").lower()
        if e not in out:
            out.append(e)
    return out


PHONE_RE = re.compile(r"(?:\+\s?91[\s\-]*)?(?:\(?0?\d{2,5}\)?[\s\-]*)?\d[\d\s\-]{6,13}\d")


def find_phones(s):
    out = []
    for m in PHONE_RE.finditer(s or ""):
        p = clean(m.group(0))
        digits = re.sub(r"\D", "", p)
        if 10 <= len(digits) <= 13 and p not in out:
            out.append(p)
    return out
