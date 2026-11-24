import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from extractors import GeminiExtractor, RuleBasedExtractor, parse_json_reply  # noqa: E402
from run import process_file  # noqa: E402
from validate import validate  # noqa: E402

SAMPLES = Path(__file__).parent.parent / "sample_contracts"

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


class FakeResponse:
    """Stands in for requests.Response so these tests never touch the network."""

    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.text = text if text is not None else json.dumps(body)
        self.url = "https://example.test/v1beta/models/fake:generateContent"

    def json(self):
        return self._body


def gemini_reply(text: str) -> FakeResponse:
    """Wrap model text in the shape Gemini's API returns it."""
    return FakeResponse(body={"candidates": [{"content": {"parts": [{"text": text}]}}]})


FULL_REPLY = {
    **GOOD, "seller": "Oakmont Family Trust", "buyer": "Anchor Demo Land Group",
    "contingencies": ["satisfactory survey"],
    "evidence": {"closing_date": "Closing Date: March 15, 2027"},
}


class GeminiExtractorTests(unittest.TestCase):
    def setUp(self):
        # Make the tests independent of whatever is set in the real shell.
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("GEMINI_MODEL", None)

    def test_default_model(self):
        self.assertEqual(GeminiExtractor(api_key="test").model, "gemini-3.5-flash")

    def test_good_reply_is_parsed_and_passes_validation(self):
        with mock.patch("extractors.requests.post", return_value=gemini_reply(json.dumps(FULL_REPLY))):
            rec = GeminiExtractor(api_key="test").extract("contract text")
        self.assertEqual(rec["closing_date"], "2027-03-15")
        self.assertEqual(rec["contingencies"], ["satisfactory survey"])
        self.assertEqual(rec["evidence"]["closing_date"], "Closing Date: March 15, 2027")
        self.assertEqual(validate(rec), [])

    def test_absent_field_stays_null_and_is_flagged(self):
        reply = {**FULL_REPLY, "closing_date": None}
        with mock.patch("extractors.requests.post", return_value=gemini_reply(json.dumps(reply))):
            rec = GeminiExtractor(api_key="test").extract("contract text")
        self.assertIsNone(rec["closing_date"])
        self.assertTrue(any("closing_date" in p for p in validate(rec)))

    def test_malformed_reply_fails_safely(self):
        with mock.patch("extractors.requests.post", return_value=gemini_reply("sorry, I can't")):
            with self.assertRaises(ValueError):
                GeminiExtractor(api_key="test").extract("contract text")

    def test_http_error_keeps_the_providers_own_message(self):
        err = FakeResponse(404, text='{"error": {"message": "model is no longer available"}}')
        with mock.patch("extractors.requests.post", return_value=err):
            with self.assertRaises(RuntimeError) as ctx:
                GeminiExtractor(api_key="test").extract("contract text")
        self.assertIn("404", str(ctx.exception))
        self.assertIn("no longer available", str(ctx.exception))

    def test_503_is_retried_then_succeeds(self):
        replies = [FakeResponse(503, text="high demand"), gemini_reply(json.dumps(FULL_REPLY))]
        with mock.patch("extractors.requests.post", side_effect=replies) as post, \
                mock.patch("time.sleep"):  # skip the real backoff wait
            rec = GeminiExtractor(api_key="test").extract("contract text")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(rec["parcel_id"], "12-34-567-890")


class RetryTests(unittest.TestCase):
    def test_persistent_503_is_tried_five_times_with_growing_waits_then_reported(self):
        busy = FakeResponse(503, text='{"error": {"message": "high demand"}}')
        with mock.patch("extractors.requests.post", return_value=busy) as post, \
                mock.patch("time.sleep") as sleep:
            with self.assertRaises(RuntimeError) as ctx:
                GeminiExtractor(api_key="test").extract("contract text")
        self.assertEqual(post.call_count, 5)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 10, 20, 40])
        self.assertIn("high demand", str(ctx.exception))

    def test_a_rejected_key_is_not_retried(self):
        bad = FakeResponse(403, text='{"error": {"message": "API key not valid"}}')
        with mock.patch("extractors.requests.post", return_value=bad) as post:
            with self.assertRaises(RuntimeError):
                GeminiExtractor(api_key="test").extract("contract text")
        self.assertEqual(post.call_count, 1)


class ProcessFileTests(unittest.TestCase):
    def test_extractor_failure_goes_to_review_with_original_message(self):
        class Boom:
            name, model = "gemini", "fake-model"

            def extract(self, text):
                raise RuntimeError("HTTP 404: model is no longer available")

        _, problems, row = process_file(SAMPLES / "contract_a_explicit_dates.pdf", Boom())
        self.assertEqual(row["status"], "Needs review")
        self.assertIn("no longer available", row["problems"])
        self.assertTrue(problems[0].startswith("processing failed"))
        self.assertEqual((row["extractor"], row["model"]), ("gemini", "fake-model"))

    def test_unreadable_pdf_goes_to_review_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "broken.pdf"
            bad.write_bytes(b"this is not a pdf")
            _, _, row = process_file(bad, RuleBasedExtractor())
        self.assertEqual(row["status"], "Needs review")
        self.assertIn("processing failed", row["problems"])

    def test_successful_file_records_extractor_and_model(self):
        _, problems, row = process_file(SAMPLES / "contract_a_explicit_dates.pdf", RuleBasedExtractor())
        self.assertEqual(problems, [])
        self.assertEqual(row["status"], "Auto-filed")
        self.assertEqual(row["extractor"], "rules")
        self.assertIsNone(row["model"])

    def test_unknown_document_goes_to_review_without_extraction(self):
        class MustNotRun:
            name, model = "rules", None

            def extract(self, text):
                raise AssertionError("Extractor must not run")

        with mock.patch(
            "run.pdf_text",
            return_value="General business correspondence with no clear document type."
        ):
            _, problems, row = process_file(Path("unknown.pdf"), MustNotRun())

        self.assertEqual(row["status"], "Needs review")
        self.assertEqual(row["extractor"], "classifier")
        self.assertIsNone(row["model"])
        self.assertTrue(any("classification requires review" in p for p in problems))

    def test_subcontractor_bid_goes_to_review_without_extraction(self):
        class MustNotRun:
            name, model = "rules", None

            def extract(self, text):
                raise AssertionError("Purchase extractor must not run on a bid")

        bid_text = """
        SUBCONTRACTOR BID PROPOSAL
        Project: Office Renovation
        Scope of Work: Electrical installation
        Base Bid: $45,000
        """

        with mock.patch("run.pdf_text", return_value=bid_text):
            _, problems, row = process_file(Path("sample_bid.pdf"), MustNotRun())

        self.assertEqual(row["status"], "Needs review")
        self.assertEqual(row["extractor"], "classifier")
        self.assertTrue(any("requires a Claude or Gemini extractor" in p for p in problems))

    def _run_mocked_bid(self, record, source):
        """Run the real bid pipeline with a mocked Claude response."""

        class InputExtractor:
            name = "llm"
            model = "fake-model"
            api_key = "test-key"

        class FakeBidExtractor:
            name = "claude-bid"
            model = "fake-bid-model"

            def extract(self, text):
                return record

        with mock.patch("run.pdf_text", return_value=source), \
                mock.patch(
                    "run.ClaudeBidExtractor",
                    return_value=FakeBidExtractor(),
                ):
            return process_file(Path("test_bid.pdf"), InputExtractor())

    def _complete_bid(self):
        """A fictional bid whose extracted values have source evidence."""
        source = """
        SUBCONTRACTOR BID PROPOSAL
        Project Name: Riverside Office Renovation
        Contractor Name: Bright Electrical LLC
        Contact Name: Alex Morgan
        Contact Email: alex@example.com
        Trade: Electrical
        Base Bid: $125,000.00 USD
        Currency: USD
        Alternate: Upgrade to premium fixtures for $4,500.
        Allowance: Lighting allowance of $8,000.
        Inclusion: Installation of electrical panels.
        Exclusion: Decorative light fixtures.
        Proposed Duration: 30 days.
        Quote Valid Until: December 15, 2026.
        Payment Terms: Net 30.
        Scope of Work: Electrical installation and testing.
        """

        record = {
            "project_name": "Riverside Office Renovation",
            "contractor_name": "Bright Electrical LLC",
            "contact_name": "Alex Morgan",
            "contact_email": "alex@example.com",
            "trade": "Electrical",
            "base_bid_amount": 125000.0,
            "currency": "USD",
            "alternates": [
                {
                    "description": "Upgrade to premium fixtures",
                    "amount": 4500.0,
                    "direction": "add",
                }
            ],
            "allowances": [
                {
                    "description": "Lighting allowance",
                    "amount": 8000.0,
                }
            ],
            "inclusions": ["Installation of electrical panels"],
            "exclusions": ["Decorative light fixtures"],
            "proposed_duration_days": 30,
            "quote_valid_until": "2026-12-15",
            "payment_terms": "Net 30",
            "clarifications": [],
            "evidence": {
                "project_name": "Project Name: Riverside Office Renovation",
                "contractor_name": "Contractor Name: Bright Electrical LLC",
                "contact_name": "Contact Name: Alex Morgan",
                "contact_email": "Contact Email: alex@example.com",
                "trade": "Trade: Electrical",
                "base_bid_amount": "Base Bid: $125,000.00 USD",
                "currency": "Currency: USD",
                "alternates": "Alternate: Upgrade to premium fixtures for $4,500.",
                "allowances": "Allowance: Lighting allowance of $8,000.",
                "inclusions": "Inclusion: Installation of electrical panels.",
                "exclusions": "Exclusion: Decorative light fixtures.",
                "proposed_duration_days": "Proposed Duration: 30 days.",
                "quote_valid_until": "Quote Valid Until: December 15, 2026.",
                "payment_terms": "Payment Terms: Net 30.",
            },
        }

        return source, record

    def test_complete_bid_passes_end_to_end(self):
        source, record = self._complete_bid()

        rec, problems, row = self._run_mocked_bid(record, source)

        self.assertEqual(problems, [])
        self.assertEqual(row["status"], "Auto-filed")
        self.assertEqual(row["extractor"], "claude-bid")
        self.assertEqual(rec["base_bid_amount"], 125000.0)
        self.assertIn("Upgrade to premium fixtures", row["alternates"])
        self.assertIn("base_bid_amount [extracted]", row["evidence"])

        def test_incomplete_bid_goes_to_review(self):
            source, record = self._complete_bid()

            # Simulate a bid with missing business-critical details.
            record["contact_name"] = None
            record["contact_email"] = None
            record["proposed_duration_days"] = None
            record["quote_valid_until"] = None
            record["payment_terms"] = (
            "Payment terms to be agreed before contract execution."
            )

            # Remove evidence for fields that are now missing.
            for field in (
                "contact_name",
                "contact_email",
                "proposed_duration_days",
                "quote_valid_until",
            ):
                record["evidence"].pop(field)

            record["evidence"]["payment_terms"] = (
            "Payment Terms: Net 30."
            )

            rec, problems, row = self._run_mocked_bid(record, source)

            self.assertEqual(row["status"], "Needs review")

            self.assertTrue(
                any("contact name" in p for p in problems)
            )
            self.assertTrue(
                any("contact email" in p for p in problems)
            )
            self.assertTrue(
                any("duration" in p for p in problems)
            )
            self.assertTrue(
                any("quote validity" in p for p in problems)
            )
            self.assertTrue(
                any("require agreement" in p for p in problems)
            )

    def test_missing_required_bid_field_goes_to_review(self):
        source, record = self._complete_bid()

        record["base_bid_amount"] = None
        record["evidence"].pop("base_bid_amount")

        rec, problems, row = self._run_mocked_bid(record, source)

        self.assertIsNone(rec["base_bid_amount"])
        self.assertEqual(row["status"], "Needs review")
        self.assertTrue(
            any("base_bid_amount" in problem for problem in problems)
        )

    def test_ambiguous_bid_total_goes_to_review(self):
        source, record = self._complete_bid()

        source += """
        IMPORTANT: Revised total is $79,000.
        Earlier proposal total was $72,000.
        The contractor must clarify which total is correct.
        """

        record["base_bid_amount"] = None
        record["clarifications"] = [
            "Conflicting totals of $72,000 and $79,000"
        ]
        record["evidence"].pop("base_bid_amount")
        record["evidence"]["clarifications"] = (
            "Earlier proposal total was $72,000. "
            "Revised total is $79,000."
        )

        rec, problems, row = self._run_mocked_bid(record, source)

        self.assertIsNone(rec["base_bid_amount"])
        self.assertEqual(row["status"], "Needs review")
        self.assertTrue(
            any("base_bid_amount" in problem for problem in problems)
        )

if __name__ == "__main__":
    unittest.main()
