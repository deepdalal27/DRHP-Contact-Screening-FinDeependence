import unittest

from pipeline.textutil import parse_num, find_emails
from pipeline.tables import parse_period, parse_table, trailing_cells, norm_label
from pipeline.compose import summarise_business, short_name, compose
from pipeline.mailer import choose_recipients


class Numbers(unittest.TestCase):
    def test_indian_format(self):
        self.assertEqual(parse_num("1,63,275.89"), 163275.89)
        self.assertEqual(parse_num("(6,853.01)"), -6853.01)
        self.assertEqual(parse_num("-"), 0.0)
        self.assertIsNone(parse_num("abc"))

    def test_emails(self):
        self.assertEqual(find_emails("Email: mb@ beelinemb.com; ig@beelinemb.com"), ["mb@beelinemb.com", "ig@beelinemb.com"])

    def test_label_numbers_are_not_values(self):
        cells = trailing_cells("EBITDA Margin (8) (%)                    10.65      14.85      9.10")
        self.assertEqual([c[2] for c in cells], [10.65, 14.85, 9.10])


class Periods(unittest.TestCase):
    def test_periods(self):
        self.assertEqual(parse_period("As at March 31, 2026")[1], "FY26")
        self.assertEqual(parse_period("March 31, As at 2025")[1], "FY25")
        self.assertEqual(parse_period("For the period ended June 30, 2026")[1:], ("Jun-26", True))
        self.assertEqual(parse_period("Fiscal 2024")[1], "FY24")


TABLE = """                    RESTATED STATEMENT OF PROFIT AND LOSS
                                                         (All amounts are in ₹ million)
                                                   For the      For the year       For the year
                     Particulars                period ended       ended              ended
                                                June 30, 2026 March 31, 2026 March 31, 2025
   (a) Revenue from Operations                         537.26         1,554.97          1,060.99
   (b) Other Income                                      6.20            14.64              4.65
Total Income                                           543.46         1,569.61          1,065.64
III Profit/(Loss) before exceptional items and tax
                                                        (8.90)        (188.84)           (21.33)
(I-II)
""".split("\n")


class Tables(unittest.TestCase):
    def test_table(self):
        t = parse_table(TABLE)
        self.assertEqual([p["label"] for p in t["periods"]], ["Jun-26", "FY26", "FY25"])
        rows = {norm_label(r["label"]): r["values"] for r in t["rows"]}
        self.assertEqual(rows["revenue from operations"], [537.26, 1554.97, 1060.99])
        self.assertEqual(rows["profit/(loss) before exceptional items and tax"], [-8.9, -188.84, -21.33])


class Email(unittest.TestCase):
    def test_summary(self):
        s = summarise_business("We are a compliance and validation company providing validation, qualification and instrumentation "
                               "solutions to customers operating primarily in regulated industries. Our services support customers.",
                               "GAMP Services Limited")
        self.assertTrue(s.startswith("GAMP Services is a compliance"))
        self.assertNotIn("We ", s)
        self.assertEqual(short_name("Hunger Pangs Limited"), "Hunger Pangs")

    def test_recipient_order(self):
        rec = {"promoter_emails": {}, "general": {"brlms": [{"name": "A Capital", "emails": ["deal@a.com"], "contact_persons": ["X"]},
                                                            {"name": "B Capital", "emails": ["deal@b.com"], "contact_persons": []}],
                                                  "cs": {"name": "CS", "emails": ["cs@co.com"]}}}
        msgs = choose_recipients(rec)
        self.assertEqual([m["variant"] for m in msgs], ["brlm", "brlm"])  # one personalised mail per BRLM
        rec["promoter_emails"] = {"P One": [{"email": "pone@co.com", "page": 3}]}
        self.assertEqual(choose_recipients(rec)[0]["variant"], "promoter")
        rec["promoter_emails"], rec["general"]["brlms"] = {}, []
        self.assertEqual(choose_recipients(rec)[0]["to"], ["cs@co.com"])
        self.assertEqual(choose_recipients(rec, suppressed=["cs@co.com"]), [])

    def test_compose_has_contacts_and_no_unverified_numbers(self):
        rec = {"cover": {"company": "Test Co Limited", "promoters": ["A B"], "board": "Mainboard", "document_date": "Oct 1, 2026"},
               "business": None, "display_name": "Test Co Limited"}
        sender = {"name": "CA Deep Dalal", "designation": "Fund Manager", "fund": "Parshwanath Capital Ventures Fund",
                  "fund_type_short": "SEBI-registered Category III AIF", "intro": "Intro.", "email": "fundmanager@parshwanath.in",
                  "whatsapp": "+91 83200 52970", "phone": "+91 70690 06298"}
        fin = {"ok": True, "to_crore": 0.01, "periods": [{"label": "FY26", "stub": False}, {"label": "FY25", "stub": False}],
               "items": {"revenue": {"values": [1000.0, 800.0], "status": ["verified", "unverified"]},
                         "pat": {"values": [100.0, 50.0], "status": ["unverified", "unverified"]}},
               "ratios": {"Revenue growth": {"values": [0.25, None], "status": ["unverified", None], "fmt": "pct"}}}
        m = compose(rec, fin, sender, {"variant": "brlm", "to": ["x@y.com"], "names": ["X"], "brlm": "Y"})
        for s in ("fundmanager@parshwanath.in", "83200 52970", "70690 06298", "Pre-IPO", "QIP"):
            self.assertIn(s, m["html"])
        self.assertNotIn("1.00", m["text"])  # unverified PAT (₹1.00 cr) must not appear


if __name__ == "__main__":
    unittest.main()


class PromoterEmails(unittest.TestCase):
    def test_only_own_or_personal_domains(self):
        from pipeline.extract import Doc, promoter_contacts
        doc = Doc(["x"], ["harsh.bhatt2@yesbank.in glocarlsbergindia@nortonrosefulbright.com manish@gracerenew.com "
                          "harshbagadia@gmail.com harsh@gmail.com"])
        got = promoter_contacts(doc, ["Manish Bagadia", "Harsh Bagadia", "Carlsberg A/s"], {"gracerenew.com"})
        self.assertEqual([e["email"] for e in got["Manish Bagadia"]], ["manish@gracerenew.com"])
        self.assertEqual([e["email"] for e in got["Harsh Bagadia"]], ["harshbagadia@gmail.com"])
        self.assertNotIn("Carlsberg A/s", got)
