"""Checks that what the model says it found is really in the document.

No AI here, on purpose. The model returns a short quote ("evidence") for each value it
extracts. This module uses plain string rules to check that:

  1. every non-empty field has a quote,
  2. the quote really appears in the source text,
  3. the quote actually contains the value, so a real-but-unrelated quote cannot vouch
     for an invented value,
  4. for dates: whether the date is written in the quote ("extracted") or was worked out
     from relative wording such as "30 days after ..." ("calculated").

What this does NOT do: it does not check that a calculated date's arithmetic is right.
Instead, every calculated date is sent to a person for review, with a reason saying so.

The rule-based extractor produces no quotes (its regexes read values straight from the
text), so a record with no "evidence" key at all is not checked here.
"""
import re
from datetime import date

from extractors import FIELDS

TEXT_FIELDS = ("seller", "buyer", "parcel_id")
DATE_FIELDS = ("effective_date", "due_diligence_deadline", "closing_date")
MIN_QUOTE_LEN = 4  # characters, after loosening; stops a quote like "a" matching anything

_MONTHS = {name: i for i, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_MONTH_RE = "|".join(_MONTHS)

_ONES = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"]
_TEENS = ["tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
          "sixteenth", "seventeenth", "eighteenth", "nineteenth"]
_DAY_WORDS = {w: i + 1 for i, w in enumerate(_ONES)}
_DAY_WORDS.update({w: 10 + i for i, w in enumerate(_TEENS)})
_DAY_WORDS["twentieth"] = 20
_DAY_WORDS.update({f"twenty-{w}": 21 + i for i, w in enumerate(_ONES)})
_DAY_WORDS["thirtieth"] = 30
_DAY_WORDS["thirty-first"] = 31
_DAY_WORD_RE = "|".join(sorted(map(re.escape, _DAY_WORDS), key=len, reverse=True))

# Wording that means "a date worked out from another date", e.g. "30 days after the ..."
_RELATIVE = re.compile(
    r"\bdays?\b[^.]{0,60}\b(?:after|before|following|prior|from)\b"
    r"|\b(?:after|following|from)\s+the\s+(?:effective date|expiration|execution|end of|date of)\b")

_PUNCT_FIX = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", " ": " "})


def _clean(s: str) -> str:
    """Lower-case, straighten curly quotes and dashes, collapse all whitespace."""
    return " ".join(s.translate(_PUNCT_FIX).lower().split())


def _loose(s: str) -> str:
    """_clean, and also ignore punctuation, so 'Inc.' and 'Inc' compare equal."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _clean(s)).split())


def _short(s: str, n: int = 80) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 3] + "..."


def _stated_dates(quote: str) -> set[date]:
    """Every explicit calendar date written in the quote, in the wordings we expect."""
    q = _clean(quote)
    found: set[date] = set()

    def add(y: int, m: int, d: int) -> None:
        try:
            found.add(date(y, m, d))
        except ValueError:
            pass

    for y, m, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", q):
        add(int(y), int(m), int(d))
    for m, d, y in re.findall(rf"\b({_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", q):
        add(int(y), _MONTHS[m], int(d))
    for d, m, y in re.findall(
            rf"\b(\d{{1,2}}(?:st|nd|rd|th)?|{_DAY_WORD_RE})\s+day\s+of\s+({_MONTH_RE}),?\s+(\d{{4}})\b", q):
        day = _DAY_WORDS[d] if d in _DAY_WORDS else int(re.sub(r"\D", "", d))
        add(int(y), _MONTHS[m], day)
    return found


def _numbers(quote: str) -> list[float]:
    out = []
    for tok in re.findall(r"\d[\d,]*(?:\.\d+)?", quote):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            pass
    return out


def _quotes(raw) -> list[str]:
    """The model may give one quote or a list. Anything else counts as no quote."""
    items = raw if isinstance(raw, list) else [raw]
    return [q for q in items if isinstance(q, str) and q.strip()]


def _judge(field: str, value, quotes: list[str], source: str) -> tuple[str, str | None, str]:
    """Return (status, problem message or None, basis). Status: verified/unsupported/missing."""
    if not quotes:
        return "missing", f"no evidence given for {field}", "extracted"

    for q in quotes:
        loose = _loose(q)
        if len(loose) < MIN_QUOTE_LEN or loose not in source:
            return ("unsupported",
                    f"evidence for {field} not found in source text: {_short(q)!r}", "extracted")

    joined = " ".join(quotes)

    if field in TEXT_FIELDS:
        if _loose(str(value)) not in _loose(joined):
            return "unsupported", f"evidence for {field} does not contain the value {value!r}", "extracted"

    elif field == "purchase_price":
        try:
            number = float(str(value).replace(",", ""))
        except ValueError:
            return "unsupported", f"purchase_price is not a number, cannot check evidence: {value!r}", "extracted"
        if number not in _numbers(joined):
            return "unsupported", f"evidence for purchase_price does not contain the amount {value!r}", "extracted"

    elif field in DATE_FIELDS:
        try:
            target = date.fromisoformat(value)
        except (TypeError, ValueError):
            # validate.py already reports an invalid date, so don't repeat it here.
            return "verified", None, "extracted"
        stated = set().union(*(_stated_dates(q) for q in quotes))
        if target in stated:
            return "verified", None, "extracted"
        if not stated or _RELATIVE.search(_clean(joined)):
            return "verified", None, "calculated"  # worked out from relative wording
        shown = ", ".join(sorted(d.isoformat() for d in stated))
        return "unsupported", f"evidence for {field} states {shown} but the value is {value}", "extracted"

    # contingencies: the model summarises them, so we only require that its quotes are real.
    return "verified", None, "extracted"


def check_evidence(rec: dict, text: str) -> tuple[list[str], list[dict]]:
    """Return (problems, items). Problems are review reasons; items describe each field's evidence."""
    if "evidence" not in rec:
        return [], []
    evidence = rec["evidence"] if isinstance(rec["evidence"], dict) else {}
    source = _loose(text)

    problems, items = [], []
    for field in FIELDS:
        value = rec.get(field)
        if value in (None, "", []):
            continue  # nothing was extracted, so nothing needs evidence
        quotes = _quotes(evidence.get(field))
        status, problem, basis = _judge(field, value, quotes, source)
        items.append({"field": field, "value": value, "quotes": quotes,
                      "status": status, "basis": basis})
        if problem:
            problems.append(problem)
        elif basis == "calculated":
            # The quote is real, but the date itself was worked out by the model and
            # nothing here re-does the arithmetic, so a person must confirm it.
            problems.append(f"{field} was calculated from relative wording, not stated in the "
                            f"document; confirm the date")
    return problems, items


def format_evidence(items: list[dict]) -> str:
    """One readable line for the CSV, so a reviewer sees what each value rests on."""
    parts = []
    for it in items:
        quote = _short(" / ".join(it["quotes"]), 120)
        if it["status"] == "missing":
            parts.append(f'{it["field"]} [NO EVIDENCE]')
        elif it["status"] == "unsupported":
            parts.append(f'{it["field"]} [UNSUPPORTED]: "{quote}"')
        else:
            parts.append(f'{it["field"]} [{it["basis"]}]: "{quote}"')
    return " | ".join(parts)


BID_TEXT_FIELDS = (
    "project_name",
    "contractor_name",
    "contact_name",
    "contact_email",
    "trade",
    "currency",
    "payment_terms",
)

BID_NUMBER_FIELDS = (
    "base_bid_amount",
    "proposed_duration_days",
)

BID_DATE_FIELDS = ("quote_valid_until",)

BID_LIST_TEXT_FIELDS = (
    "inclusions",
    "exclusions",
    "clarifications",
)


def _bid_number_supported(value, quotes: str) -> bool:
    """Check whether a numeric value appears in the supporting quotes."""
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return False

    return number in _numbers(quotes)


def _judge_bid(field: str, value, quotes: list[str],
               source: str) -> tuple[str, str | None, str]:
    """Verify bid evidence without applying purchase-agreement date rules."""
    if not quotes:
        return "missing", f"no evidence given for {field}", "extracted"

    for quote in quotes:
        loose = _loose(quote)
        if len(loose) < MIN_QUOTE_LEN or loose not in source:
            return (
                "unsupported",
                f"evidence for {field} not found in source text: {_short(quote)!r}",
                "extracted",
            )

    joined = " ".join(quotes)

    if field in BID_TEXT_FIELDS:
        if _loose(str(value)) not in _loose(joined):
            return (
                "unsupported",
                f"evidence for {field} does not contain the value {value!r}",
                "extracted",
            )

    elif field in BID_NUMBER_FIELDS:
        if not _bid_number_supported(value, joined):
            return (
                "unsupported",
                f"evidence for {field} does not contain the amount {value!r}",
                "extracted",
            )

    elif field in BID_DATE_FIELDS:
        try:
            target = date.fromisoformat(value)
        except (TypeError, ValueError):
            return (
                "unsupported",
                f"{field} is not a valid ISO date: {value!r}",
                "extracted",
            )

        stated = set().union(*(_stated_dates(q) for q in quotes))
        if target not in stated:
            shown = ", ".join(sorted(d.isoformat() for d in stated)) or "no explicit date"
            return (
                "unsupported",
                f"evidence for {field} states {shown} but the value is {value}",
                "extracted",
            )

    elif field in BID_LIST_TEXT_FIELDS:
        if not isinstance(value, list):
            return (
                "unsupported",
                f"{field} must be a list",
                "extracted",
            )

        for item in value:
            if not isinstance(item, str) or _loose(item) not in _loose(joined):
                return (
                    "unsupported",
                    f"evidence for {field} does not contain item {item!r}",
                    "extracted",
                )

    elif field in ("alternates", "allowances"):
        if not isinstance(value, list):
            return (
                "unsupported",
                f"{field} must be a list",
                "extracted",
            )

        for item in value:
            if not isinstance(item, dict):
                return (
                    "unsupported",
                    f"{field} contains an item that is not an object",
                    "extracted",
                )

            description = item.get("description")
            amount = item.get("amount")

            if not isinstance(description, str) or _loose(description) not in _loose(joined):
                return (
                    "unsupported",
                    f"evidence for {field} does not contain description {description!r}",
                    "extracted",
                )

            if amount is not None and not _bid_number_supported(amount, joined):
                return (
                    "unsupported",
                    f"evidence for {field} does not contain amount {amount!r}",
                    "extracted",
                )

    return "verified", None, "extracted"


def check_bid_evidence(rec: dict, text: str) -> tuple[list[str], list[dict]]:
    """Check evidence for subcontractor bid fields."""
    if "evidence" not in rec:
        return [], []

    evidence = rec["evidence"] if isinstance(rec["evidence"], dict) else {}
    source = _loose(text)

    fields = (
        *BID_TEXT_FIELDS,
        *BID_NUMBER_FIELDS,
        *BID_DATE_FIELDS,
        *BID_LIST_TEXT_FIELDS,
        "alternates",
        "allowances",
    )

    problems = []
    items = []

    for field in fields:
        value = rec.get(field)

        if value in (None, "", []):
            continue

        quotes = _quotes(evidence.get(field))
        status, problem, basis = _judge_bid(field, value, quotes, source)

        items.append({
            "field": field,
            "value": value,
            "quotes": quotes,
            "status": status,
            "basis": basis,
        })

        if problem:
            problems.append(problem)

    return problems, items
