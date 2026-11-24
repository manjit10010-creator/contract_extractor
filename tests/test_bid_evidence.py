
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence import check_bid_evidence, format_evidence


SOURCE = (
    "SUBCONTRACTOR BID PROPOSAL. "
    "Project: Riverside Office Renovation. "
    "Contractor: Northstar Electrical LLC. "
    "Contact: Alex Morgan. "
    "Email: alex@northstar.example. "
    "Trade: Electrical. "
    "Base Bid: $125,000 USD. "
    "Proposed Duration: 45 days. "
    "Quote valid until December 15, 2026. "
    "Alternate 1: Upgrade lighting package, add $8,000. "
    "Allowance: Fixtures, $5,000. "
    "Inclusions: Labor and installation. "
    "Exclusions: Permit fees. "
    "Payment Terms: Net 30."
)


class BidEvidenceTests(unittest.TestCase):

    def make_record(self):
        return {
            "project_name": "Riverside Office Renovation",
            "contractor_name": "Northstar Electrical LLC",
            "contact_name": "Alex Morgan",
            "contact_email": "alex@northstar.example",
            "trade": "Electrical",
            "base_bid_amount": 125000,
            "currency": "USD",
            "proposed_duration_days": 45,
            "quote_valid_until": "2026-12-15",
            "alternates": [
                {
                    "description": "Upgrade lighting package",
                    "amount": 8000,
                }
            ],
            "allowances": [
                {
                    "description": "Fixtures",
                    "amount": 5000,
                }
            ],
            "inclusions": ["Labor and installation"],
            "exclusions": ["Permit fees"],
            "payment_terms": "Net 30",
            "clarifications": [],
            "evidence": {
                "project_name": "Project: Riverside Office Renovation",
                "contractor_name": "Contractor: Northstar Electrical LLC",
                "contact_name": "Contact: Alex Morgan",
                "contact_email": "Email: alex@northstar.example",
                "trade": "Trade: Electrical",
                "base_bid_amount": "Base Bid: $125,000 USD",
                "currency": "Base Bid: $125,000 USD",
                "proposed_duration_days": "Proposed Duration: 45 days",
                "quote_valid_until": "Quote valid until December 15, 2026",
                "alternates": "Alternate 1: Upgrade lighting package, add $8,000",
                "allowances": "Allowance: Fixtures, $5,000",
                "inclusions": "Inclusions: Labor and installation",
                "exclusions": "Exclusions: Permit fees",
                "payment_terms": "Payment Terms: Net 30",
            },
        }

    def test_all_bid_fields_have_verified_evidence(self):
        problems, items = check_bid_evidence(self.make_record(), SOURCE)

        self.assertEqual(problems, [])
        self.assertTrue(items)
        self.assertTrue(all(item["status"] == "verified" for item in items))

    def test_missing_evidence_is_flagged(self):
        rec = self.make_record()
        del rec["evidence"]["contractor_name"]

        problems, items = check_bid_evidence(rec, SOURCE)

        self.assertTrue(any("no evidence given for contractor_name" in p for p in problems))
        contractor = next(i for i in items if i["field"] == "contractor_name")
        self.assertEqual(contractor["status"], "missing")

    def test_invented_quote_is_flagged(self):
        rec = self.make_record()
        rec["evidence"]["contractor_name"] = "Contractor: Fake Company LLC"

        problems, items = check_bid_evidence(rec, SOURCE)

        self.assertTrue(any("not found in source text" in p for p in problems))
        contractor = next(i for i in items if i["field"] == "contractor_name")
        self.assertEqual(contractor["status"], "unsupported")

    def test_wrong_base_bid_amount_is_flagged(self):
        rec = self.make_record()
        rec["base_bid_amount"] = 130000

        problems, _ = check_bid_evidence(rec, SOURCE)

        self.assertTrue(any("does not contain the amount" in p for p in problems))

    def test_wrong_quote_validity_date_is_flagged(self):
        rec = self.make_record()
        rec["quote_valid_until"] = "2026-12-20"

        problems, _ = check_bid_evidence(rec, SOURCE)

        self.assertTrue(any("states 2026-12-15" in p for p in problems))

    def test_wrong_alternate_amount_is_flagged(self):
        rec = self.make_record()
        rec["alternates"][0]["amount"] = 9000

        problems, _ = check_bid_evidence(rec, SOURCE)

        self.assertTrue(any("does not contain amount" in p for p in problems))

    def test_wrong_allowance_description_is_flagged(self):
        rec = self.make_record()
        rec["allowances"][0]["description"] = "Kitchen equipment"

        problems, _ = check_bid_evidence(rec, SOURCE)

        self.assertTrue(any("does not contain description" in p for p in problems))

    def test_evidence_formatting_is_reusable(self):
        _, items = check_bid_evidence(self.make_record(), SOURCE)

        formatted = format_evidence(items)

        self.assertIn("contractor_name [extracted]", formatted)
        self.assertIn("base_bid_amount [extracted]", formatted)


if __name__ == "__main__":
    unittest.main()
