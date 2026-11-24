"""Pipeline: PDF -> text -> extract -> validate -> CSV (+ optional Airtable).

Examples
  python run.py                        # rule-based baseline on the sample contracts
  python run.py --extractor llm        # Claude does the reading (needs ANTHROPIC_API_KEY)
  python run.py --extractor gemini     # Gemini (needs GEMINI_API_KEY)
  python run.py --extractor llm --airtable
  python run.py --pdf-dir path/to/pdfs
"""
import argparse
import time
from pathlib import Path

from pypdf import PdfReader

from evidence import check_evidence, format_evidence
from extractors import GeminiExtractor, LLMExtractor, RuleBasedExtractor, empty_result
from sinks import push_airtable, to_row, write_csv
from validate import validate

HERE = Path(__file__).parent


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def process_file(pdf: Path, extractor) -> tuple[dict, list[str], dict]:
    """Run one PDF through extract + validate + evidence check. Never raises for a bad file.

    If reading the PDF or calling the extractor fails, the file is marked
    "Needs review" with the original error message, and the batch carries on.
    Evidence that is missing or not found in the PDF text also sends the file to review.
    """
    items: list[dict] = []
    try:
        text = pdf_text(pdf)
        rec = extractor.extract(text)
        problems = validate(rec)
        evidence_problems, items = check_evidence(rec, text)
        problems += evidence_problems
    except Exception as e:  # deliberately broad: one bad file must not stop the batch
        rec = empty_result()
        detail = " ".join(str(e).split())[:300]  # keep the real message, on one line
        problems = [f"processing failed: {type(e).__name__}: {detail}"]
    row = to_row(pdf.name, rec, problems, extractor=extractor.name, model=extractor.model,
                 evidence=format_evidence(items))
    return rec, problems, row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extractor", choices=["rules", "llm", "gemini"], default="rules")
    ap.add_argument("--pdf-dir", type=Path, default=HERE / "sample_contracts")
    ap.add_argument("--out", type=Path, default=HERE / "output" / "results.csv")
    ap.add_argument("--airtable", action="store_true", help="also push rows to Airtable")
    args = ap.parse_args()

    extractor = {"rules": RuleBasedExtractor, "llm": LLMExtractor,
                 "gemini": GeminiExtractor}[args.extractor]()
    pdfs = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs in {args.pdf_dir}. Run make_samples.py first.")

    rows = []
    for pdf in pdfs:
        started = time.perf_counter()
        rec, problems, row = process_file(pdf, extractor)
        seconds = time.perf_counter() - started
        rows.append(row)
        model = f" {extractor.model}" if extractor.model else ""
        print(f"\n{pdf.name}  [{extractor.name}{model}]  -> {row['status']}  ({seconds:.1f}s)")
        for k in ("parcel_id", "purchase_price", "effective_date",
                  "due_diligence_deadline", "closing_date"):
            print(f"  {k:24} {rec.get(k)}")
        for p in problems:
            print(f"  ! {p}")

    write_csv(rows, args.out)
    ok = sum(r["status"] == "Auto-filed" for r in rows)
    print(f"\n{ok}/{len(rows)} auto-filed, {len(rows) - ok} need review. CSV: {args.out}")

    if args.airtable:
        print(f"Pushed {push_airtable(rows)} rows to Airtable.")


if __name__ == "__main__":
    main()
