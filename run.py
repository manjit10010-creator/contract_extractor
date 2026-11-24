"""Pipeline: PDF -> text -> extract -> validate -> CSV (+ optional Airtable).

Examples
  python run.py                        # rule-based baseline on the sample contracts
  python run.py --extractor llm        # Claude does the reading (needs ANTHROPIC_API_KEY)
  python run.py --extractor gemini     # Gemini (needs GEMINI_API_KEY)
  python run.py --extractor llm --airtable
  python run.py --pdf-dir path/to/pdfs
"""
import argparse
from pathlib import Path

from pypdf import PdfReader

from extractors import GeminiExtractor, LLMExtractor, RuleBasedExtractor
from sinks import push_airtable, to_row, write_csv
from validate import validate

HERE = Path(__file__).parent


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


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
        rec = extractor.extract(pdf_text(pdf))
        problems = validate(rec)
        row = to_row(pdf.name, rec, problems)
        rows.append(row)
        print(f"\n{pdf.name}  [{extractor.name}]  -> {row['status']}")
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
