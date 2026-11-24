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


if __name__ == "__main__":
    unittest.main()
