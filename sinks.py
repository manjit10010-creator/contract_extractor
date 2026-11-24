"""Where results go: always a CSV, optionally an Airtable base."""
import csv
import os
from pathlib import Path

import requests

COLUMNS = [
    "file", "status", "seller", "buyer", "parcel_id", "purchase_price",
    "effective_date", "due_diligence_deadline", "closing_date",
    "contingencies", "problems", "extractor", "model",
]


def to_row(filename: str, rec: dict, problems: list[str],
           extractor: str | None = None, model: str | None = None) -> dict:
    row = {c: rec.get(c) for c in COLUMNS if c in rec}
    row["file"] = filename
    row["extractor"] = extractor  # which extractor produced this row (rules / llm / gemini)
    row["model"] = model          # model identifier, or None for the rule-based extractor
    row["status"] = "Needs review" if problems else "Auto-filed"
    row["contingencies"] = "; ".join(rec.get("contingencies") or [])
    row["problems"] = "; ".join(problems)
    return row


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def push_airtable(rows: list[dict]) -> int:
    """Create one record per row. Needs AIRTABLE_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_TABLE.

    The table's field names must match COLUMNS. Airtable accepts 10 records per request.
    """
    token = os.environ["AIRTABLE_TOKEN"]
    base, table = os.environ["AIRTABLE_BASE_ID"], os.environ["AIRTABLE_TABLE"]
    url = f"https://api.airtable.com/v0/{base}/{requests.utils.quote(table)}"
    sent = 0
    for i in range(0, len(rows), 10):
        batch = [{"fields": {k: v for k, v in r.items() if v not in (None, "")}}
                 for r in rows[i:i + 10]]
        resp = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                             json={"records": batch}, timeout=30)
        resp.raise_for_status()
        sent += len(batch)
    return sent
