"""Plain rules that check whatever the extractor produced. No AI here on purpose:
this layer must be predictable and auditable."""
import re
from datetime import date

PARCEL_RE = re.compile(r"^\d{2}-\d{2}-\d{3}-\d{3}$")
REQUIRED = ["parcel_id", "purchase_price", "closing_date"]


def _d(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def validate(rec: dict) -> list[str]:
    """Return a list of problems. Empty list = safe to auto-file."""
    problems = []

    for f in REQUIRED:
        if rec.get(f) in (None, ""):
            problems.append(f"missing required field: {f}")

    if rec.get("parcel_id") and not PARCEL_RE.match(rec["parcel_id"]):
        problems.append(f"parcel_id has unexpected format: {rec['parcel_id']}")

    price = rec.get("purchase_price")
    if price is not None:
        if not isinstance(price, (int, float)) or price <= 0:
            problems.append(f"purchase_price is not a positive number: {price}")
        elif not (10_000 <= price <= 500_000_000):
            problems.append(f"purchase_price outside plausible range: {price}")

    for f in ("effective_date", "due_diligence_deadline", "closing_date"):
        if rec.get(f) and _d(rec[f]) is None:
            problems.append(f"{f} is not a valid ISO date: {rec[f]}")

    eff, dd, close = (_d(rec.get(k)) for k in
                      ("effective_date", "due_diligence_deadline", "closing_date"))
    if eff and close and close <= eff:
        problems.append("closing_date is not after effective_date")
    if dd and close and dd > close:
        problems.append("due_diligence_deadline is after closing_date")
    if eff and dd and dd < eff:
        problems.append("due_diligence_deadline is before effective_date")

    return problems
