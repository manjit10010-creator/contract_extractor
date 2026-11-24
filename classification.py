
"""Conservative document classification for the extraction pipeline."""

import re


PURCHASE_PATTERNS = [
    r"\breal estate purchase agreement\b",
    r"\bpurchase and sale agreement\b",
    r"\bvacant land purchase agreement\b",
    r"\bseller\b.{0,100}\bbuyer\b",
    r"\bland sale contract\b",
    r"\bseller\b.{0,150}\b(?:buyer|purchaser)\b",
]

BID_PATTERNS = [
    r"\bsubcontractor (?:bid|proposal|quotation)\b",
    r"\b(?:construction )?bid proposal\b",
    r"\bquote submitted to\b",
    r"\bproposal for construction\b",
    r"\bbase bid\b",
    r"\bscope of work\b",
]


def classify_document(text: str) -> tuple[str, str]:
    """Return (document_type, reason).

    Ambiguous or weak matches are deliberately classified as unknown.
    """
    normalized = " ".join(text.lower().split())

    if not normalized.strip():
        return "unknown", "document contains no readable text"

    purchase_hits = sum(
        bool(re.search(pattern, normalized, re.I))
        for pattern in PURCHASE_PATTERNS
    )
    bid_hits = sum(
        bool(re.search(pattern, normalized, re.I))
        for pattern in BID_PATTERNS
    )

    if purchase_hits >= 2 and bid_hits == 0:
        return "purchase_agreement", "purchase-agreement indicators found"

    if bid_hits >= 2 and purchase_hits == 0:
        return "subcontractor_bid", "subcontractor-bid indicators found"

    if purchase_hits and bid_hits:
        return "unknown", "conflicting document-type indicators"

    return "unknown", "insufficient document-type indicators"
