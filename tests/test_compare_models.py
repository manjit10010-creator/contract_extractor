import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from compare_models import EXPECTED, compare, score  # noqa: E402
from extractors import empty_result  # noqa: E402

SAMPLES = Path(__file__).parent.parent / "sample_contracts"
A = EXPECTED["contract_a_explicit_dates.pdf"]


class ScoreTests(unittest.TestCase):
    def test_all_correct(self):
        self.assertEqual(score(empty_result() | A, A), (5, 5))

    def test_price_compares_as_a_number(self):
        self.assertEqual(score(empty_result() | {**A, "purchase_price": 1250000.0}, A), (5, 5))

    def test_wrong_and_missing_fields_do_not_count(self):
        rec = empty_result() | {**A, "closing_date": "2027-03-16", "parcel_id": None}
        self.assertEqual(score(rec, A), (3, 5))

    def test_a_string_price_is_not_a_match(self):
        self.assertEqual(score(empty_result() | {**A, "purchase_price": "1,250,000"}, A), (4, 5))


class FakeModel:
    """Always answers with contract A's values, whatever it is shown."""
    name = "gemini"

    def __init__(self, model):
        self.model = model

    def extract(self, text):
        return empty_result() | A


class CompareTests(unittest.TestCase):
    def test_compare_scores_every_model_on_every_file(self):
        results = compare(["model-x", "model-y"], SAMPLES, make_extractor=lambda model: FakeModel(model))
        self.assertEqual(len(results), 6)
        self.assertEqual({r["model"] for r in results}, {"model-x", "model-y"})
        by_file = {r["file"]: r for r in results if r["model"] == "model-x"}
        self.assertEqual(by_file["contract_a_explicit_dates.pdf"]["correct"], 5)
        self.assertLess(by_file["contract_b_relative_dates.pdf"]["correct"], 5)
        self.assertTrue(all(r["seconds"] >= 0 for r in results))


class FlakyModel:
    """Fails like an overloaded API on one contract, answers contract A's values otherwise."""
    name = "gemini"

    def __init__(self, model):
        self.model = model

    def extract(self, text):
        if "PURCHASE AND SALE AGREEMENT" in text:  # contract B's title
            raise RuntimeError("HTTP 503: high demand")
        return empty_result() | A


class FailureHandlingTests(unittest.TestCase):
    def test_api_failures_are_marked_failed_and_kept_out_of_the_score(self):
        results = compare(["m"], SAMPLES, make_extractor=lambda model: FlakyModel(model))
        failed = {r["file"]: r["failed"] for r in results}
        self.assertEqual(failed, {"contract_a_explicit_dates.pdf": False,
                                  "contract_b_relative_dates.pdf": True,
                                  "contract_c_messy_wording.pdf": False})

    def test_summary_counts_only_processed_files(self):
        import contextlib
        import io
        results = compare(["m"], SAMPLES, make_extractor=lambda model: FlakyModel(model))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            from compare_models import summarise
            summarise(results)
        self.assertIn("processed 2/3 files", buf.getvalue())
        self.assertIn("5/10 fields correct", buf.getvalue())  # A right (5), C wrong (0), B excluded


if __name__ == "__main__":
    unittest.main()
