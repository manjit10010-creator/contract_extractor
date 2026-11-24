import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence import check_evidence, format_evidence  # noqa: E402
from extractors import empty_result  # noqa: E402
from run import process_file  # noqa: E402

SAMPLES = Path(__file__).parent.parent / "sample_contracts"

TEXT = (
    'REAL ESTATE PURCHASE AGREEMENT This Agreement is made on January 10, 2027 (the "Effective Date") '
    'between Riverbend Holdings LLC ("Seller") and Anchor Demo Land Group ("Buyer"). '
    "1. Property. Vacant land identified as Parcel ID 12-34-567-890, approx. 14.2 acres. "
    "2. Purchase Price. Purchase Price: $1,250,000.00, payable at Closing. "
    "3. Due Diligence. Buyer's due diligence period ends on February 9, 2027. "
    "4. Closing Date: March 15, 2027. "
    "Effective Date: March 1, 2027. Buyer may terminate within forty-five (45) days after the Effective Date. "
    "Closing shall occur on or before thirty (30) days after the expiration of the Due Diligence Period. "
    "Buyer's obligation to close is subject to obtaining financing and a satisfactory survey. "
    "Dated this 2nd day of April, 2027. Closing on or before the thirtieth day of June, 2027."
)

GOOD_VALUES = {
    "seller": "Riverbend Holdings LLC", "buyer": "Anchor Demo Land Group",
    "parcel_id": "12-34-567-890", "purchase_price": 1_250_000.0,
    "effective_date": "2027-01-10", "due_diligence_deadline": "2027-02-09",
    "closing_date": "2027-03-15",
}
GOOD_QUOTES = {
    "seller": "Riverbend Holdings LLC", "buyer": "Anchor Demo Land Group",
    "parcel_id": "Parcel ID 12-34-567-890", "purchase_price": "Purchase Price: $1,250,000.00",
    "effective_date": 'made on January 10, 2027 (the "Effective Date")',
    "due_diligence_deadline": "due diligence period ends on February 9, 2027",
    "closing_date": "Closing Date: March 15, 2027",
}


def make(values=None, quotes=None, **evidence_overrides):
    """A record shaped like the extractors' output, with evidence."""
    rec = empty_result()
    rec.update(GOOD_VALUES if values is None else values)
    ev = dict(GOOD_QUOTES if quotes is None else quotes)
    ev.update(evidence_overrides)
    rec["evidence"] = ev
    return rec


def statuses(items):
    return {i["field"]: (i["status"], i["basis"]) for i in items}


class EvidenceTests(unittest.TestCase):
    def test_all_fields_verified(self):
        problems, items = check_evidence(make(), TEXT)
        self.assertEqual(problems, [])
        self.assertEqual(len(items), 7)
        self.assertTrue(all(s == ("verified", "extracted") for s in statuses(items).values()))

    def test_records_without_an_evidence_key_are_not_checked(self):
        rec = empty_result() | GOOD_VALUES  # what the rule-based extractor returns
        self.assertEqual(check_evidence(rec, TEXT), ([], []))

    def test_null_fields_need_no_evidence(self):
        rec = make(values={"parcel_id": "12-34-567-890"}, quotes={"parcel_id": "Parcel ID 12-34-567-890"})
        problems, items = check_evidence(rec, TEXT)
        self.assertEqual(problems, [])
        self.assertEqual([i["field"] for i in items], ["parcel_id"])

    def test_missing_quote_is_flagged(self):
        quotes = {k: v for k, v in GOOD_QUOTES.items() if k != "closing_date"}
        problems, items = check_evidence(make(quotes=quotes), TEXT)
        self.assertEqual(problems, ["no evidence given for closing_date"])
        self.assertEqual(statuses(items)["closing_date"][0], "missing")

    def test_invented_quote_is_flagged(self):
        problems, items = check_evidence(make(closing_date="Closing Date: April 1, 2027"), TEXT)
        self.assertEqual(len(problems), 1)
        self.assertIn("not found in source text", problems[0])
        self.assertEqual(statuses(items)["closing_date"][0], "unsupported")

    def test_very_short_quote_is_not_accepted(self):
        problems, _ = check_evidence(make(parcel_id="a"), TEXT)
        self.assertTrue(any("parcel_id" in p and "not found" in p for p in problems))

    def test_real_quote_that_does_not_contain_the_value_is_flagged(self):
        rec = make(values={**GOOD_VALUES, "parcel_id": "99-99-999-999"})
        problems, _ = check_evidence(rec, TEXT)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not contain the value", problems[0])

    def test_price_must_appear_in_the_quote(self):
        rec = make(values={**GOOD_VALUES, "purchase_price": 1_300_000.0})
        problems, _ = check_evidence(rec, TEXT)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not contain the amount", problems[0])

    def test_date_that_contradicts_its_quote_is_flagged(self):
        rec = make(values={**GOOD_VALUES, "closing_date": "2027-03-16"})
        problems, _ = check_evidence(rec, TEXT)
        self.assertEqual(len(problems), 1)
        self.assertIn("states 2027-03-15 but the value is 2027-03-16", problems[0])

    def test_calculated_date_is_labelled_and_sent_to_review(self):
        rec = make(values={**GOOD_VALUES, "closing_date": "2027-05-15"},
                   closing_date="thirty (30) days after the expiration of the Due Diligence Period")
        problems, items = check_evidence(rec, TEXT)
        self.assertEqual(len(problems), 1)
        self.assertIn("closing_date was calculated", problems[0])
        self.assertEqual(statuses(items)["closing_date"], ("verified", "calculated"))
        self.assertEqual(statuses(items)["effective_date"], ("verified", "extracted"))

    def test_relative_quote_that_also_names_a_date_is_still_calculated(self):
        quote = "Effective Date: March 1, 2027. Buyer may terminate within forty-five (45) days after the Effective Date"
        rec = make(values={**GOOD_VALUES, "due_diligence_deadline": "2027-04-15"},
                   due_diligence_deadline=quote)
        self.assertEqual(statuses(check_evidence(rec, TEXT)[1])["due_diligence_deadline"],
                         ("verified", "calculated"))

    def test_day_of_month_wordings_count_as_stated_dates(self):
        rec = make(values={**GOOD_VALUES, "effective_date": "2027-04-02", "closing_date": "2027-06-30"},
                   effective_date="Dated this 2nd day of April, 2027",
                   closing_date="the thirtieth day of June, 2027")
        problems, items = check_evidence(rec, TEXT)
        self.assertEqual(problems, [])
        self.assertEqual(statuses(items)["effective_date"], ("verified", "extracted"))
        self.assertEqual(statuses(items)["closing_date"], ("verified", "extracted"))

    def test_formatting_differences_in_the_source_are_tolerated(self):
        text = "between Hartwell Properties, Inc.\n  as “seller” and Anchor"
        rec = make(values={"seller": "Hartwell Properties, Inc."},
                   quotes={"seller": "Hartwell Properties Inc. as \"seller\""})
        self.assertEqual(check_evidence(rec, text)[0], [])

    def test_evidence_that_is_not_a_dict_counts_as_missing(self):
        rec = make()
        rec["evidence"] = ["Closing Date: March 15, 2027"]
        problems, _ = check_evidence(rec, TEXT)
        self.assertEqual(len(problems), 7)
        self.assertTrue(all(p.startswith("no evidence given") for p in problems))

    def test_list_evidence_for_contingencies(self):
        rec = make(values={"contingencies": ["financing", "survey"]},
                   quotes={"contingencies": ["obtaining financing", "a satisfactory survey"]})
        problems, items = check_evidence(rec, TEXT)
        self.assertEqual(problems, [])
        self.assertEqual(statuses(items)["contingencies"], ("verified", "extracted"))

    def test_one_fake_quote_in_a_list_is_enough_to_flag(self):
        rec = make(values={"contingencies": ["financing", "zoning"]},
                   quotes={"contingencies": ["obtaining financing", "rezoning approval"]})
        problems, _ = check_evidence(rec, TEXT)
        self.assertEqual(len(problems), 1)
        self.assertIn("rezoning approval", problems[0])

    def test_format_evidence_labels_each_status(self):
        rec = make(values={**GOOD_VALUES, "closing_date": "2027-05-15", "parcel_id": "99-99-999-999"},
                   closing_date="thirty (30) days after the expiration of the Due Diligence Period")
        rec["evidence"].pop("seller")
        line = format_evidence(check_evidence(rec, TEXT)[1])
        self.assertIn("seller [NO EVIDENCE]", line)
        self.assertIn("parcel_id [UNSUPPORTED]", line)
        self.assertIn('closing_date [calculated]: "thirty (30) days', line)
        self.assertIn('purchase_price [extracted]: "Purchase Price: $1,250,000.00"', line)


class FakeLLM:
    """An extractor that returns a fixed record, as if a model had produced it."""
    name, model = "gemini", "fake-model"

    def __init__(self, rec):
        self.rec = rec

    def extract(self, text):
        return self.rec


class EvidenceInPipelineTests(unittest.TestCase):
    PDF = SAMPLES / "contract_a_explicit_dates.pdf"

    def test_good_evidence_lets_the_record_through_and_is_saved(self):
        _, problems, row = process_file(self.PDF, FakeLLM(make()))
        self.assertEqual(problems, [])
        self.assertEqual(row["status"], "Auto-filed")
        self.assertIn('closing_date [extracted]: "Closing Date: March 15, 2027"', row["evidence"])

    def test_unsupported_evidence_sends_the_record_to_review(self):
        rec = make(parcel_id="Parcel ID 00-00-000-000")
        _, problems, row = process_file(self.PDF, FakeLLM(rec))
        self.assertEqual(row["status"], "Needs review")
        self.assertTrue(any("parcel_id" in p and "not found" in p for p in problems))
        self.assertIn("parcel_id [UNSUPPORTED]", row["evidence"])

    def test_calculated_dates_in_a_real_pdf_go_to_review(self):
        pdf = SAMPLES / "contract_b_relative_dates.pdf"
        rec = empty_result() | {
            "seller": "Oakmont Family Trust", "buyer": "Anchor Demo Land Group",
            "parcel_id": "45-67-890-123", "purchase_price": 1_800_000,
            "effective_date": "2027-03-01", "due_diligence_deadline": "2027-04-15",
            "closing_date": "2027-05-15",
            "evidence": {
                "seller": "Seller: Oakmont Family Trust", "buyer": "Buyer: Anchor Demo Land Group",
                "parcel_id": "Parcel No. 45-67-890-123",
                "purchase_price": "One Million Eight Hundred Thousand Dollars ($1,800,000.00)",
                "effective_date": "Effective Date: March 1, 2027",
                "due_diligence_deadline": "forty-five (45) days after the Effective Date",
                "closing_date": "thirty (30) days after the expiration of the Due Diligence Period"}}
        _, problems, row = process_file(pdf, FakeLLM(rec))
        self.assertEqual(row["status"], "Needs review")
        self.assertEqual(len(problems), 2)  # the two calculated dates, nothing else
        self.assertTrue(all("was calculated" in p for p in problems))
        self.assertIn("closing_date [calculated]", row["evidence"])

    def test_missing_evidence_sends_the_record_to_review(self):
        rec = make()
        rec["evidence"] = {}
        _, _, row = process_file(self.PDF, FakeLLM(rec))
        self.assertEqual(row["status"], "Needs review")
        self.assertIn("no evidence given for closing_date", row["problems"])

    def test_rule_based_extractor_is_unaffected(self):
        from extractors import RuleBasedExtractor
        _, problems, row = process_file(self.PDF, RuleBasedExtractor())
        self.assertEqual(problems, [])
        self.assertEqual(row["status"], "Auto-filed")
        self.assertEqual(row["evidence"], "")


if __name__ == "__main__":
    unittest.main()
