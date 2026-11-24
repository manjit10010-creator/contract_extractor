
"""Schema and deterministic validation for subcontractor bids."""

import math
import re
from datetime import date


BID_FIELDS = [
    "project_name",
    "contractor_name",
    "contact_name",
    "contact_email",
    "trade",
    "base_bid_amount",
    "currency",
    "alternates",
    "allowances",
    "inclusions",
    "exclusions",
    "proposed_duration_days",
    "quote_valid_until",
    "payment_terms",
    "clarifications",
]

REQUIRED_BID_FIELDS = [
    "project_name",
    "contractor_name",
    "trade",
    "base_bid_amount",
    "currency",
]


def empty_bid_result() -> dict:
    """Return an empty bid record with predictable field types."""
    return {
        "project_name": None,
        "contractor_name": None,
        "contact_name": None,
        "contact_email": None,
        "trade": None,
        "base_bid_amount": None,
        "currency": None,
        "alternates": [],
        "allowances": [],
        "inclusions": [],
        "exclusions": [],
        "proposed_duration_days": None,
        "quote_valid_until": None,
        "payment_terms": None,
        "clarifications": [],
    }


def _valid_positive_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _validate_bid_items(field: str, items: object) -> list[str]:
    problems = []

    if not isinstance(items, list):
        return [f"{field} must be a list"]

    for index, item in enumerate(items):
        prefix = f"{field}[{index}]"

        if not isinstance(item, dict):
            problems.append(f"{prefix} must be an object")
            continue

        description = item.get("description")
        amount = item.get("amount")

        if not isinstance(description, str) or not description.strip():
            problems.append(f"{prefix} is missing a description")

        if amount is not None and not _valid_positive_number(amount):
            problems.append(f"{prefix} has an invalid amount: {amount!r}")

        direction = item.get("direction")
        if direction is not None and direction not in ("add", "deduct"):
            problems.append(
                f"{prefix} has an invalid direction: {direction!r}"
            )

    return problems


def validate_bid(rec: dict) -> list[str]:
    """Return validation problems. An empty list means structurally valid."""
    problems = []

    if not isinstance(rec, dict):
        return ["bid record must be an object"]

    for field in REQUIRED_BID_FIELDS:
        if rec.get(field) in (None, ""):
            problems.append(f"missing required field: {field}")

    for field in ("project_name", "contractor_name", "trade"):
        value = rec.get(field)
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            problems.append(f"{field} must be a non-empty string")

    amount = rec.get("base_bid_amount")
    if amount is not None and not _valid_positive_number(amount):
        problems.append(
            f"base_bid_amount must be a positive finite number: {amount!r}"
        )

    currency = rec.get("currency")
    if currency is not None and (
        not isinstance(currency, str)
        or not re.fullmatch(r"[A-Z]{3}", currency)
    ):
        problems.append(
            f"currency must be a three-letter uppercase code: {currency!r}"
        )

    email = rec.get("contact_email")
    if email is not None and (
        not isinstance(email, str)
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        problems.append(f"contact_email has an invalid format: {email!r}")

    duration = rec.get("proposed_duration_days")
    if duration is not None and (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration <= 0
    ):
        problems.append(
            f"proposed_duration_days must be a positive integer: {duration!r}"
        )

    valid_until = rec.get("quote_valid_until")
    if valid_until is not None:
        try:
            date.fromisoformat(valid_until)
        except (TypeError, ValueError):
            problems.append(
                f"quote_valid_until must be a valid ISO date: {valid_until!r}"
            )

    for field in ("alternates", "allowances"):
        problems.extend(_validate_bid_items(field, rec.get(field, [])))

    for field in ("inclusions", "exclusions", "clarifications"):
        value = rec.get(field, [])
        if not isinstance(value, list):
            problems.append(f"{field} must be a list")
        elif any(not isinstance(item, str) or not item.strip() for item in value):
            problems.append(f"{field} must contain non-empty strings")

    return problems

def check_bid_completeness(record: dict) -> list[str]:
    """Identify missing information that prevents automatic bid filing."""

    review_fields = {
        "contact_name": "contact name is missing",
        "contact_email": "contact email is missing",
        "proposed_duration_days": "proposed duration is missing",
        "quote_valid_until": "quote validity date is missing",
        "payment_terms": "payment terms are missing",
    }

    problems = []

    for field, message in review_fields.items():
        value = record.get(field)

        if value is None or (
            isinstance(value, str) and not value.strip()
        ):
            problems.append(message)

    if isinstance(record.get("payment_terms"), str):
        payment_terms = record["payment_terms"].lower()

        if "to be agreed" in payment_terms or "subject to negotiation" in payment_terms:
            problems.append(
                "payment terms require agreement or negotiation"
            )

    return problems