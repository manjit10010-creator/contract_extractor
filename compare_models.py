"""Compare Gemini models on the sample contracts: speed and correctness.

  python compare_models.py gemini-3.5-flash gemini-3.1-flash-lite

Calls the live API (needs GEMINI_API_KEY), so it is not part of the offline tests.
Expected answers are the hand-checked values for the three fictional samples. This is a
smoke comparison on 3 documents, not an accuracy benchmark: do not quote percentages from it.

"Needs review" is not the same as "wrong". A correct but calculated date still goes to review.
"""
import argparse
import time
from pathlib import Path

from extractors import GeminiExtractor
from run import process_file

HERE = Path(__file__).parent

EXPECTED = {
    "contract_a_explicit_dates.pdf": {
        "parcel_id": "12-34-567-890", "purchase_price": 1_250_000,
        "effective_date": "2027-01-10", "due_diligence_deadline": "2027-02-09",
        "closing_date": "2027-03-15"},
    "contract_b_relative_dates.pdf": {
        "parcel_id": "45-67-890-123", "purchase_price": 1_800_000,
        "effective_date": "2027-03-01", "due_diligence_deadline": "2027-04-15",
        "closing_date": "2027-05-15"},
    "contract_c_messy_wording.pdf": {
        "parcel_id": "98-76-543-210", "purchase_price": 2_400_000,
        "effective_date": "2027-04-02", "due_diligence_deadline": "2027-05-15",
        "closing_date": "2027-06-30"},
}


def _same(got, want) -> bool:
    if isinstance(want, (int, float)):
        return isinstance(got, (int, float)) and float(got) == float(want)
    return got == want


def score(rec: dict, expected: dict) -> tuple[int, int]:
    """(fields that match the known answer, fields checked)."""
    return sum(_same(rec.get(f), v) for f, v in expected.items()), len(expected)


def compare(models: list[str], pdf_dir: Path, make_extractor=GeminiExtractor) -> list[dict]:
    results = []
    for model in models:
        extractor = make_extractor(model=model)
        for name, expected in EXPECTED.items():
            started = time.perf_counter()
            rec, problems, row = process_file(pdf_dir / name, extractor)
            seconds = time.perf_counter() - started
            correct, total = score(rec, expected)
            # A file the API failed on (e.g. HTTP 503) says nothing about the model's answers,
            # so it is reported as FAILED and kept out of the correctness numbers.
            failed = any(p.startswith("processing failed") for p in problems)
            results.append({"model": model, "file": name, "seconds": seconds,
                            "status": row["status"], "correct": correct, "total": total,
                            "problems": problems, "failed": failed})
            outcome = (f"FAILED: {problems[0][:70]}" if failed
                       else f"{correct}/{total} correct  {row['status']}")
            print(f"  {model:28} {name:32} {seconds:6.1f}s  {outcome}")
    return results


def summarise(results: list[dict]) -> None:
    print("\nSummary (3 documents each; a smoke test, not a benchmark)")
    for model in dict.fromkeys(r["model"] for r in results):
        mine = [r for r in results if r["model"] == model]
        done = [r for r in mine if not r["failed"]]
        correct, total = sum(r["correct"] for r in done), sum(r["total"] for r in done)
        avg = sum(r["seconds"] for r in done) / len(done) if done else 0.0
        review = sum(r["status"] != "Auto-filed" for r in done)
        print(f"  {model:28} processed {len(done)}/{len(mine)} files, avg {avg:.1f}s each; "
              f"{correct}/{total} fields correct on those; {review} of them need review")
    print("  (failed files are excluded: an API error is not a wrong answer. Re-run to fill the gaps.)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+", help="Gemini model names, e.g. gemini-3.5-flash")
    ap.add_argument("--pdf-dir", type=Path, default=HERE / "sample_contracts")
    args = ap.parse_args()
    summarise(compare(args.models, args.pdf_dir))


if __name__ == "__main__":
    main()
