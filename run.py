
"""Pipeline: PDF -> classify -> extract -> validate -> CSV."""

import argparse
import time
from pathlib import Path
import os
from pypdf import PdfReader

from classification import classify_document
from bid_extractors import ClaudeBidExtractor, GeminiBidExtractor
from bid_schema import (
    empty_bid_result,
    validate_bid,
    check_bid_completeness,
)
from evidence import (
    check_bid_evidence,
    check_evidence,
    format_evidence,
)
from extractors import (
    GeminiExtractor,
    LLMExtractor,
    RuleBasedExtractor,
    empty_result,
)
from sinks import (
    bid_to_row,
    push_airtable,
    to_row,
    write_bid_csv,
    write_csv,
)
from validate import validate

HERE = Path(__file__).parent


def pdf_text(path: Path) -> str:
    return "\n".join(
        page.extract_text() or ""
        for page in PdfReader(path).pages
    )


def process_file(pdf: Path, extractor) -> tuple[dict, list[str], dict]:
    """Classify and process one PDF. Never raises for a bad file."""
    items: list[dict] = []
    extractor_name = extractor.name
    model_name = extractor.model
    document_type = "unknown"

    try:
        text = pdf_text(pdf)
        document_type, reason = classify_document(text)

        if document_type == "unknown":
            rec = empty_result()
            problems = [
                f"document classification requires review: {reason}"
            ]
            extractor_name = "classifier"
            model_name = None

        elif document_type == "subcontractor_bid":
            if extractor.name == "llm":
                bid_extractor = ClaudeBidExtractor(
                    api_key=extractor.api_key,
                    model=extractor.model,
                )
            elif extractor.name == "gemini":
                bid_extractor = GeminiBidExtractor(
                    api_key=extractor.api_key,
                    model=extractor.model,
                )
            else:
                bid_extractor = None

            if bid_extractor is None:
                rec = empty_bid_result()
                problems = [
                    "subcontractor bid requires a Claude or Gemini extractor",
                    reason,
                ]
                extractor_name = "classifier"
                model_name = None
            else:
                rec = bid_extractor.extract(text)
                problems = validate_bid(rec)

                completeness_problems = check_bid_completeness(rec)
                problems += completeness_problems

                evidence_problems, items = check_bid_evidence(rec, text)
                problems += evidence_problems
                extractor_name = bid_extractor.name
                model_name = bid_extractor.model

        else:
            rec = extractor.extract(text)
            problems = validate(rec)
            evidence_problems, items = check_evidence(rec, text)
            problems += evidence_problems

    except Exception as e:
        if document_type == "subcontractor_bid":
            rec = empty_bid_result()
        else:
            rec = empty_result()

        detail = " ".join(str(e).split())[:300]
        problems = [
            f"processing failed: {type(e).__name__}: {detail}"
        ]

    evidence_text = format_evidence(items)

    if document_type == "subcontractor_bid":
        row = bid_to_row(
            pdf.name,
            rec,
            problems,
            extractor=extractor_name,
            model=model_name,
            evidence=evidence_text,
        )
    else:
        row = to_row(
            pdf.name,
            rec,
            problems,
            extractor=extractor_name,
            model=model_name,
            evidence=evidence_text,
        )

    return rec, problems, row


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--extractor",
        choices=["rules", "llm", "gemini"],
        default="rules",
    )
    ap.add_argument(
        "--pdf-dir",
        type=Path,
        default=HERE / "sample_contracts",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=HERE / "output" / "results.csv",
    )
    ap.add_argument(
        "--bid-out",
        type=Path,
        default=HERE / "output" / "bids.csv",
    )
    ap.add_argument(
        "--airtable",
        action="store_true",
        help="also push purchase-agreement rows to Airtable",
    )
    args = ap.parse_args()
    if args.airtable:
        required_vars = (
            "AIRTABLE_TOKEN",
            "AIRTABLE_BASE_ID",
            "AIRTABLE_TABLE",
        )
        missing_vars = [
            name for name in required_vars
            if not os.environ.get(name)
        ]

        if missing_vars:
            raise SystemExit(
                "Airtable configuration is incomplete. "
                "Missing environment variables: "
                + ", ".join(missing_vars)
            )
    extractor = {
        "rules": RuleBasedExtractor,
        "llm": LLMExtractor,
        "gemini": GeminiExtractor,
    }[args.extractor]()

    pdfs = sorted(args.pdf_dir.glob("*.pdf"))

    if not pdfs:
        raise SystemExit(
            f"No PDFs in {args.pdf_dir}. Check the directory."
        )

    purchase_rows = []
    bid_rows = []

    for pdf in pdfs:
        started = time.perf_counter()
        rec, problems, row = process_file(pdf, extractor)
        seconds = time.perf_counter() - started

        is_bid = "project_name" in row

        if is_bid:
            bid_rows.append(row)
        else:
            purchase_rows.append(row)

        model = f" {row['model']}" if row["model"] else ""
        print(
            f"\n{pdf.name} [{row['extractor']}{model}] "
            f"-> {row['status']} ({seconds:.1f}s)"
        )

        fields = (
            (
                "project_name", "contractor_name", "trade",
                "base_bid_amount", "currency",
            )
            if is_bid
            else (
                "parcel_id", "purchase_price", "effective_date",
                "due_diligence_deadline", "closing_date",
            )
        )

        for field in fields:
            print(f"  {field:24} {rec.get(field)}")

        for problem in problems:
            print(f"  ! {problem}")

    if purchase_rows:
        write_csv(purchase_rows, args.out)
        ok = sum(
            row["status"] == "Auto-filed"
            for row in purchase_rows
        )
        print(
            f"\nPurchase agreements: {ok}/{len(purchase_rows)} "
            f"auto-filed. CSV: {args.out}"
        )

    if bid_rows:
        write_bid_csv(bid_rows, args.bid_out)
        ok = sum(
            row["status"] == "Auto-filed"
            for row in bid_rows
        )
        print(
            f"\nSubcontractor bids: {ok}/{len(bid_rows)} "
            f"auto-filed. CSV: {args.bid_out}"
        )

    if args.airtable:
        if purchase_rows:
            print(
                f"Pushed {push_airtable(purchase_rows)} "
                "purchase-agreement rows to Airtable."
            )
        if bid_rows:
            print(
                "Bid rows were not sent to Airtable; "
                "the existing Airtable schema is purchase-specific."
            )


if __name__ == "__main__":
    main()
