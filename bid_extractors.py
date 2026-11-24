
"""AI extractors for subcontractor bid proposals."""

import json
import os

from bid_schema import empty_bid_result
from extractors import check, post_with_retry


BID_SYSTEM_PROMPT = """
You extract structured information from subcontractor bid proposals.

Return ONLY one valid JSON object with these keys:

project_name
contractor_name
contact_name
contact_email
trade
base_bid_amount
currency
alternates
allowances
inclusions
exclusions
proposed_duration_days
quote_valid_until
payment_terms
clarifications
evidence

Rules:

1. Never invent, assume, or calculate missing information.
2. Use null for missing scalar fields.
3. Use empty lists for missing list fields.
4. base_bid_amount must be a number, not a formatted currency string.
5. currency must be a three-letter uppercase currency code only when
   explicitly identifiable. Otherwise use null.
6. quote_valid_until must use ISO YYYY-MM-DD format when an explicit
   date is available. Otherwise use null.
7. proposed_duration_days must be a positive integer only when the
   document gives a clear duration in days. Do not convert weeks
   into days.
8. alternates must be a list of objects:
   {"description": "short description", "amount": 1000, "direction": "add"}
   direction must be "add" or "deduct" when explicitly stated.
   Use null for an unknown amount or direction.
9. allowances must be a list of objects:
   {"description": "short description", "amount": 1000}
   Use null when the amount is not explicit.
10. inclusions, exclusions, and clarifications must be lists of
    concise strings.
11. Do not resolve conflicting prices. If the document gives conflicting
    base bid amounts, use null for base_bid_amount and explain the
    conflict in clarifications.
12. Do not turn approximate or uncertain values into definite values.
13. Include an "evidence" object. For every non-null extracted field,
    provide a short exact quote copied from the document.
    For list fields, provide quotes that support the extracted items.
14. Evidence quotes must be copied verbatim from the source document.
15. Do not include fields outside the requested JSON structure.
"""


def parse_bid_json_reply(raw: str) -> dict:
    """Parse a model response into the standard bid record."""
    start = raw.find("{")
    end = raw.rfind("}")

    if start == -1 or end == -1:
        raise ValueError(
            f"No JSON object in model reply: {raw[:200]!r}"
        )

    data = json.loads(raw[start:end + 1])

    if not isinstance(data, dict):
        raise ValueError("Model reply must contain a JSON object")

    result = empty_bid_result()

    for field in result:
        if field in data:
            result[field] = data[field]

    if "evidence" not in data:
        result["evidence"] = {}
    else:
        result["evidence"] = data["evidence"]

    if not isinstance(result["evidence"], dict):
        raise ValueError("Bid evidence must be a JSON object")

    return result


class ClaudeBidExtractor:
    """Extract subcontractor bids using the Claude Messages API."""

    name = "claude-bid"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get(
            "CLAUDE_MODEL", "claude-sonnet-5-5"
        )

        if not self.api_key:
            raise RuntimeError(
                "Set ANTHROPIC_API_KEY to use the Claude bid extractor."
            )

    def extract(self, text: str) -> dict:
        resp = post_with_retry(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 2500,
                "system": BID_SYSTEM_PROMPT,
                "messages": [
                    {
                        "role": "user",
                        "content": f"<bid_document>\n{text}\n</bid_document>",
                    }
                ],
            },
            timeout=180,
        )

        check(resp)

        raw = "".join(
            block["text"]
            for block in resp.json()["content"]
            if block["type"] == "text"
        )

        return parse_bid_json_reply(raw)


class GeminiBidExtractor:
    """Extract subcontractor bids using the Gemini REST API."""

    name = "gemini-bid"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get(
            "GEMINI_MODEL", "gemini-3.5-flash"
        )

        if not self.api_key:
            raise RuntimeError(
                "Set GEMINI_API_KEY to use the Gemini bid extractor."
            )

    def extract(self, text: str) -> dict:
        resp = post_with_retry(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent",
            headers={
                "x-goog-api-key": self.api_key,
                "content-type": "application/json",
            },
            json={
                "systemInstruction": {
                    "parts": [{"text": BID_SYSTEM_PROMPT}]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": f"<bid_document>\n{text}\n</bid_document>"}
                        ],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0,
                },
            },
            timeout=180,
        )

        check(resp)

        parts = resp.json()["candidates"][0]["content"]["parts"]
        raw = "".join(part.get("text", "") for part in parts)

        return parse_bid_json_reply(raw)
