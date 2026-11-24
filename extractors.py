"""Two ways to pull key fields out of contract text.

- RuleBasedExtractor: regex only. Fast, free, predictable, but brittle.
- LLMExtractor: calls the Claude Messages API over plain HTTP (needs ANTHROPIC_API_KEY).

Both return the same dict shape so the rest of the pipeline doesn't care which ran.
"""
import json
import os
import re
from datetime import datetime

import requests

FIELDS = [
    "seller", "buyer", "parcel_id", "purchase_price",
    "effective_date", "due_diligence_deadline", "closing_date", "contingencies",
]


def check(resp: requests.Response) -> None:
    """Like raise_for_status, but includes the API's own error message."""
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} from {resp.url.split('?')[0]}:\n{resp.text[:800]}")


def post_with_retry(url: str, retries: int = 3, **kwargs) -> requests.Response:
    """POST with a long timeout; retry on timeouts and on 429/500/503 with a short backoff."""
    import time
    kwargs.setdefault("timeout", 180)
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, **kwargs)
            if resp.status_code not in (429, 500, 503) or attempt == retries:
                return resp
            print(f"  (HTTP {resp.status_code}, retrying {attempt}/{retries - 1}...)")
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt == retries:
                raise
            print(f"  ({type(e).__name__}, retrying {attempt}/{retries - 1}...)")
        time.sleep(5 * attempt)


def empty_result() -> dict:
    return {f: None for f in FIELDS} | {"contingencies": []}


# --------------------------------------------------------------------------- rules
_DATE = r"([A-Z][a-z]+ \d{1,2}, \d{4})"


def _to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


class RuleBasedExtractor:
    """Only understands wording the author thought of in advance."""

    name = "rules"

    def extract(self, text: str) -> dict:
        r = empty_result()
        flat = " ".join(text.split())

        if m := re.search(r"Parcel (?:ID|No\.?) ?:? ?(\d{2}-\d{2}-\d{3}-\d{3})", flat):
            r["parcel_id"] = m.group(1)
        if m := re.search(r"Purchase Price: \$([\d,]+(?:\.\d{2})?)", flat):
            r["purchase_price"] = float(m.group(1).replace(",", ""))
        if m := re.search(rf"made on {_DATE} \(the \"Effective Date\"\)", flat) or \
                re.search(rf"Effective Date: {_DATE}", flat):
            r["effective_date"] = _to_iso(m.group(1))
        if m := re.search(rf"due diligence period ends on {_DATE}", flat, re.I):
            r["due_diligence_deadline"] = _to_iso(m.group(1))
        if m := re.search(rf"Closing Date: {_DATE}", flat):
            r["closing_date"] = _to_iso(m.group(1))
        if m := re.search(r"between ([\w .,]+?) \(\"Seller\"\)", flat):
            r["seller"] = m.group(1).strip()
        return r


# ----------------------------------------------------------------------------- LLM
SYSTEM_PROMPT = """You extract key terms from real-estate purchase agreements.
Return ONLY a JSON object with these keys:
  seller, buyer, parcel_id, purchase_price (number, USD), effective_date,
  due_diligence_deadline, closing_date (all ISO YYYY-MM-DD), contingencies (list of short strings).
Rules:
- If a date is expressed relative to another date ("30 days after the Effective Date"),
  resolve it to an absolute date by doing the arithmetic.
- If a field is not in the document, use null. Never guess or invent a value.
- Add a key "evidence": an object mapping each non-null field to the short exact phrase
  from the document it came from, so a human can verify it."""


class LLMExtractor:
    name = "llm"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
        if not self.api_key:
            raise RuntimeError("Set ANTHROPIC_API_KEY to use the LLM extractor.")

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
                "max_tokens": 1500,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": f"<contract>\n{text}\n</contract>"}],
            },
            timeout=180,
        )
        check(resp)
        raw = "".join(b["text"] for b in resp.json()["content"] if b["type"] == "text")
        return parse_json_reply(raw)


class GeminiExtractor:
    """Same job as LLMExtractor, using Google's Gemini REST API (key from aistudio.google.com)."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        # Model names change over time; override with GEMINI_MODEL if this one is rejected.
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY to use the Gemini extractor.")

    def extract(self, text: str) -> dict:
        resp = post_with_retry(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user",
                              "parts": [{"text": f"<contract>\n{text}\n</contract>"}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
            },
            timeout=180,
        )
        check(resp)
        parts = resp.json()["candidates"][0]["content"]["parts"]
        return parse_json_reply("".join(p.get("text", "") for p in parts))


def parse_json_reply(raw: str) -> dict:
    """Pull the JSON object out of a model reply, tolerating code fences or chatter."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model reply: {raw[:200]!r}")
    data = json.loads(raw[start:end + 1])
    result = empty_result()
    result.update({k: data.get(k) for k in FIELDS})
    result["contingencies"] = result["contingencies"] or []
    result["evidence"] = data.get("evidence") or {}
    return result
