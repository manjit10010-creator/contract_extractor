
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bid_schema import (
    empty_bid_result,
    validate_bid,
    check_bid_completeness,
)


class BidSchemaTests(unittest.TestCase):

    def valid_record(self):
        rec = empty_bid_result()
        rec.update({
            "project_name": "Riverside Office Renovation",
            "contractor_name": "Northstar Electrical LLC",
            "trade": "Electrical",
            "base_bid_amount": 125000.0,
            "currency": "USD",
        })
        return rec

    def test_empty_result_has_all_fields(self):
        rec = empty_bid_result()

        self.assertEqual(
            set(rec),
            {
                "project_name", "contractor_name", "contact_name",
                "contact_email", "trade", "base_bid_amount", "currency",
                "alternates", "allowances", "inclusions", "exclusions",
                "proposed_duration_days", "quote_valid_until",
                "payment_terms", "clarifications",
            },
        )

    def test_clean_bid_passes(self):
        self.assertEqual(validate_bid(self.valid_record()), [])

    def test_missing_required_fields_are_flagged(self):
        problems = validate_bid(empty_bid_result())

        self.assertEqual(len(problems), 5)
        self.assertTrue(any("missing required field: base_bid_amount" in p
                            for p in problems))

    def test_invalid_base_bid_amount_is_flagged(self):
        rec = self.valid_record()
        rec["base_bid_amount"] = -100

        self.assertTrue(any("base_bid_amount" in p
                            for p in validate_bid(rec)))

    def test_boolean_is_not_accepted_as_an_amount(self):
        rec = self.valid_record()
        rec["base_bid_amount"] = True

        self.assertTrue(any("base_bid_amount" in p
                            for p in validate_bid(rec)))

    def test_invalid_currency_is_flagged(self):
        rec = self.valid_record()
        rec["currency"] = "dollars"

        self.assertTrue(any("currency" in p for p in validate_bid(rec)))

    def test_invalid_email_is_flagged(self):
        rec = self.valid_record()
        rec["contact_email"] = "not-an-email"

        self.assertTrue(any("contact_email" in p
                            for p in validate_bid(rec)))

    def test_invalid_duration_is_flagged(self):
        rec = self.valid_record()
        rec["proposed_duration_days"] = -5

        self.assertTrue(any("proposed_duration_days" in p
                            for p in validate_bid(rec)))

    def test_invalid_quote_date_is_flagged(self):
        rec = self.valid_record()
        rec["quote_valid_until"] = "15/12/2026"

        self.assertTrue(any("quote_valid_until" in p
                            for p in validate_bid(rec)))

    def test_invalid_alternate_is_flagged(self):
        rec = self.valid_record()
        rec["alternates"] = [{"description": "", "amount": -500}]

        problems = validate_bid(rec)

        self.assertTrue(any("description" in p for p in problems))
        self.assertTrue(any("amount" in p for p in problems))

    def test_invalid_alternate_direction_is_flagged(self):
        rec = self.valid_record()
        rec["alternates"] = [{
            "description": "Lighting upgrade",
            "amount": 8000,
            "direction": "maybe",
        }]

        self.assertTrue(any("direction" in p for p in validate_bid(rec)))

    def test_list_fields_must_be_lists(self):
        rec = self.valid_record()
        rec["inclusions"] = "Labor"

        self.assertTrue(any("inclusions must be a list" in p
                            for p in validate_bid(rec)))

class BidCompletenessTests(unittest.TestCase):

    def complete_record(self):
        rec = empty_bid_result()
        rec.update({
            "project_name": "Riverside Office Renovation",
            "contractor_name": "Northstar Electrical LLC",
            "contact_name": "Daniel Morgan",
            "contact_email": "daniel@example.com",
            "trade": "Electrical",
            "base_bid_amount": 125000.0,
            "currency": "USD",
            "proposed_duration_days": 30,
            "quote_valid_until": "2026-12-15",
            "payment_terms": "Net 30",
        })
        return rec

    def test_complete_bid_passes_completeness_check(self):
        self.assertEqual(
            check_bid_completeness(self.complete_record()),
            [],
        )

    def test_missing_contact_details_trigger_review(self):
        rec = self.complete_record()
        rec["contact_name"] = None
        rec["contact_email"] = None

        problems = check_bid_completeness(rec)

        self.assertTrue(any("contact name" in p for p in problems))
        self.assertTrue(any("contact email" in p for p in problems))

    def test_missing_duration_and_quote_validity_trigger_review(self):
        rec = self.complete_record()
        rec["proposed_duration_days"] = None
        rec["quote_valid_until"] = None

        problems = check_bid_completeness(rec)

        self.assertTrue(any("duration" in p for p in problems))
        self.assertTrue(any("quote validity" in p for p in problems))

    def test_payment_terms_requiring_agreement_trigger_review(self):
        rec = self.complete_record()
        rec["payment_terms"] = (
            "Payment terms to be agreed before contract execution."
        )

        problems = check_bid_completeness(rec)

        self.assertTrue(any("require agreement" in p for p in problems))

    def test_empty_alternates_and_allowances_are_acceptable(self):
        rec = self.complete_record()
        rec["alternates"] = []
        rec["allowances"] = []

        self.assertEqual(check_bid_completeness(rec), [])

if __name__ == "__main__":
    unittest.main()
