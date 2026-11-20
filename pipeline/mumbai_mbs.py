"""Merchant bankers (BRLMs) recorded from DRHPs that have a Mumbai office.

A firm is identified by its email domain (the DRHP sometimes prints two bankers side by side, so names
and mailboxes can be mixed up; the domain is not). Mumbai = a 022 number for that firm in a DRHP, or a
Mumbai address. Output: JSON list of firms with their mailboxes, phones and the IPOs they handle.
"""
import json, glob, re, sys
from collections import Counter, OrderedDict

NOT_DEAL = re.compile(r"complain|grievance|griev|redress|investor|^ig\b|^igrc|helpdesk|support|query|customer|care", re.I)
NOT_MB_DOMAINS = ("shirvaralaw.com",)
SAME_FIRM = {"marwadichandaranagroup.com": "marwadichandarana.com"}
NAMES = {"jmfl.com": "JM Financial Limited", "360.one": "360 ONE WAM Limited", "morganstanley.com": "Morgan Stanley India Company Private Limited",
         "serencapital.in": "Seren Capital Private Limited", "iiflcap.com": "IIFL Capital Services Limited",
         "icicisecurities.com": "ICICI Securities Limited", "equirus.com": "Equirus Capital Limited",
         "pantomathgroup.com": "Pantomath Capital Advisors Private Limited", "hemsecurities.com": "Hem Securities Limited"}
MUMBAI_ADDRESS = {"pantomathgroup.com": "Pantomath Nucleus House, Saki Vihar Road, Andheri (East), Mumbai 400 072",
                  "360.one": "360 ONE Centre, Kamala City, Lower Parel, Mumbai (head office)"}


def mumbai_phone(p):
    d = re.sub(r"\D", "", p)
    if len(d) > 10 and d.startswith("91"):
        d = d[2:]
    d = d.lstrip("0")
    return d.startswith("22") and len(d) == 10


def clean_name(n):
    n = re.sub(r"\s*\((?:formerly|earlier)[^)]*\)?.*$", "", n or "", flags=re.I)
    return re.sub(r"[*^]+$", "", n).strip()


def firms():
    firms = OrderedDict()
    root = __import__("pathlib").Path(__file__).resolve().parent.parent
    for f in sorted(glob.glob(str(root / "site/data/companies/*.json"))):
        c = json.load(open(f))
        for b in c.get("brlms") or []:
            ems = [e.lower() for e in (b.get("emails") or []) if not NOT_DEAL.search(e.split("@")[0]) and not e.endswith(NOT_MB_DOMAINS)]
            doms = OrderedDict()
            for e in ems:
                d = e.split("@")[1]
                doms.setdefault(SAME_FIRM.get(d, d), []).append(e)
            single = len(doms) == 1
            for d, mails in doms.items():
                r = firms.setdefault(d, {"domain": d, "names": Counter(), "phones": [], "emails": [], "deals": [], "address": MUMBAI_ADDRESS.get(d)})
                if single and b.get("name") and not b["name"].lower().startswith("legal"):
                    r["names"][clean_name(b["name"])] += 1
                    for p in b.get("phones") or []:  # phones only when the block is unambiguous
                        if p not in r["phones"]:
                            r["phones"].append(p)
                for e in mails:
                    if e not in r["emails"]:
                        r["emails"].append(e)
                if c["company"] not in r["deals"]:
                    r["deals"].append(c["company"])
    out = []
    for d, r in firms.items():
        name = NAMES.get(d) or (r["names"].most_common(1)[0][0] if r["names"] else d)
        generic = [e for e in r["emails"] if re.match(r"^(mb|ib|mbd|mbk|ipo|info|ecm|merchant)", e.split("@")[0])]
        out.append({"firm": name, "domain": d, "phones": r["phones"], "emails": r["emails"], "deals": r["deals"],
                    "to": (generic or r["emails"][-1:])[:1],
                    "mumbai": any(mumbai_phone(p) for p in r["phones"]) or bool(r["address"]), "address": r["address"]})
    return out


if __name__ == "__main__":
    json.dump(firms(), sys.stdout, indent=1, ensure_ascii=False)
