import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extractors import RuleBasedExtractor, parse_json_reply  # noqa: E402
from validate import validate  # noqa: E402

GOOD = {
    "parcel_id": "12-34-567-890", "purchase_price": 1_250_000.0,
    "effective_date": "2027-01-10", "due_diligence_deadline": "2027-02-09",
    "closing_date": "2027-03-15",
}


class ValidateTests(unittest.TestCase):
    def test_clean_record_passes(self):
        self.assertEqual(validate(GOOD), [])

    def test_missing_required(self):
        self.assertTrue(any("closing_date" in p for p in validate({**GOOD, "closing_date": None})))

    def test_bad_parcel_format(self):
        self.assertTrue(any("parcel_id" in p for p in validate({**GOOD, "parcel_id": "ABC"})))

    def test_closing_before_effective(self):
        self.assertTrue(any("not after" in p for p in validate({**GOOD, "closing_date": "2026-12-01"})))

    def test_implausible_price(self):
        self.assertTrue(any("plausible" in p for p in validate({**GOOD, "purchase_price": 12.0})))

    def test_diligence_after_closing(self):
        self.assertTrue(any("after closing" in p for p in
                            validate({**GOOD, "due_diligence_deadline": "2027-04-01"})))


class ExtractorTests(unittest.TestCase):
    def test_rules_handle_the_wording_they_were_written_for(self):
        text = ('made on January 10, 2027 (the "Effective Date") Parcel ID 12-34-567-890 '
                "Purchase Price: $1,250,000.00 Closing Date: March 15, 2027.")
        r = RuleBasedExtractor().extract(text)
        self.assertEqual(r["closing_date"], "2027-03-15")
        self.assertEqual(r["purchase_price"], 1_250_000.0)

    def test_rules_miss_relative_dates(self):
        text = "Closing shall occur 30 days after the Effective Date."
        self.assertIsNone(RuleBasedExtractor().extract(text)["closing_date"])

    def test_parse_json_reply_tolerates_code_fences(self):
        reply = 'Here you go:\n```json\n{"parcel_id": "12-34-567-890", "contingencies": null}\n```'
        r = parse_json_reply(reply)
        self.assertEqual(r["parcel_id"], "12-34-567-890")
        self.assertEqual(r["contingencies"], [])

    def test_parse_json_reply_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_json_reply("sorry, I can't")


if __name__ == "__main__":
    unittest.main()
