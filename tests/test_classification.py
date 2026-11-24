
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from classification import classify_document


class ClassificationTests(unittest.TestCase):

    def test_identifies_purchase_agreement(self):
        text = """
        REAL ESTATE PURCHASE AGREEMENT
        Agreement between Riverbend Holdings LLC (Seller)
        and Anchor Demo Land Group (Buyer).
        """
        result, _ = classify_document(text)
        self.assertEqual(result, "purchase_agreement")

    def test_identifies_subcontractor_bid(self):
        text = """
        SUBCONTRACTOR BID PROPOSAL
        Project: Office Renovation
        Scope of Work: Electrical installation
        Base Bid: $45,000
        """
        result, _ = classify_document(text)
        self.assertEqual(result, "subcontractor_bid")

    def test_unknown_document_is_not_guessed(self):
        text = "A document containing general business correspondence."
        result, _ = classify_document(text)
        self.assertEqual(result, "unknown")

    def test_empty_document_is_unknown(self):
        result, _ = classify_document("")
        self.assertEqual(result, "unknown")

    def test_conflicting_indicators_go_to_review(self):
        text = """
        REAL ESTATE PURCHASE AGREEMENT
        Seller and Buyer agree to the terms.
        SUBCONTRACTOR BID PROPOSAL
        Scope of Work and Base Bid.
        """
        result, reason = classify_document(text)
        self.assertEqual(result, "unknown")
        self.assertIn("conflicting", reason)

    def test_identifies_land_sale_contract(self):
        text = """
        LAND SALE CONTRACT
        Dated April 2, 2027, by and between Hartwell Properties, Inc.
        as seller and Anchor Demo Land Group as purchaser.
        """
        result, _ = classify_document(text)
        self.assertEqual(result, "purchase_agreement")

if __name__ == "__main__":
    unittest.main()
