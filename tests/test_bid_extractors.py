
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from bid_extractors import (
    ClaudeBidExtractor,
    GeminiBidExtractor,
    parse_bid_json_reply,
)


class BidParserTests(unittest.TestCase):

    def test_parses_valid_bid(self):
        raw = """
        {
            "project_name": "Riverside Office Renovation",
            "contractor_name": "Northstar Electrical LLC",
            "trade": "Electrical",
            "base_bid_amount": 125000,
            "currency": "USD",
            "alternates": [],
            "allowances": [],
            "inclusions": [],
            "exclusions": [],
            "clarifications": [],
            "evidence": {
                "base_bid_amount": "$125,000.00 USD"
            }
        }
        """

        result = parse_bid_json_reply(raw)

        self.assertEqual(result["base_bid_amount"], 125000)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["project_name"], "Riverside Office Renovation")
        self.assertIn("evidence", result)

    def test_missing_fields_keep_empty_defaults(self):
        result = parse_bid_json_reply('{"project_name": "Test Project"}')

        self.assertEqual(result["project_name"], "Test Project")
        self.assertIsNone(result["base_bid_amount"])
        self.assertEqual(result["alternates"], [])
        self.assertEqual(result["evidence"], {})

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_bid_json_reply("This is not JSON")

    def test_rejects_non_object_json(self):
        with self.assertRaises(ValueError):
            parse_bid_json_reply('["not", "an", "object"]')

    def test_rejects_non_object_evidence(self):
        with self.assertRaises(ValueError):
            parse_bid_json_reply('{"evidence": []}')


class BidExtractorTests(unittest.TestCase):

    def test_claude_uses_bid_prompt_and_parses_response(self):
        extractor = ClaudeBidExtractor(api_key="test-key")

        response = Mock()
        response.ok = True
        response.json.return_value = {
            "content": [
                {
                    "type": "text",
                    "text": '{"project_name": "Test Project"}',
                }
            ]
        }

        with patch("bid_extractors.post_with_retry", return_value=response) as post:
            result = extractor.extract("SUBCONTRACTOR BID PROPOSAL")

        self.assertEqual(result["project_name"], "Test Project")
        self.assertIn("subcontractor bid proposals", post.call_args.kwargs["json"]["system"].lower())

    def test_gemini_uses_bid_prompt_and_parses_response(self):
        extractor = GeminiBidExtractor(api_key="test-key")

        response = Mock()
        response.ok = True
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": '{"project_name": "Test Project"}'}
                        ]
                    }
                }
            ]
        }

        with patch("bid_extractors.post_with_retry", return_value=response) as post:
            result = extractor.extract("SUBCONTRACTOR BID PROPOSAL")

        self.assertEqual(result["project_name"], "Test Project")
        self.assertIn(
            "subcontractor bid proposals",
            post.call_args.kwargs["json"]["systemInstruction"]["parts"][0]["text"].lower(),
        )

    def test_missing_api_key_is_rejected(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                ClaudeBidExtractor()

            with self.assertRaises(RuntimeError):
                GeminiBidExtractor()


if __name__ == "__main__":
    unittest.main()
