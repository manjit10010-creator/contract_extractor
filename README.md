# Contract Extractor (demo)

Reads purchase-agreement PDFs, pulls out the key terms, checks them with plain rules,
and writes a CSV (and optionally Airtable rows). Built to show where an LLM helps and
where ordinary code should stay in charge.

```
PDF -> text (pypdf) -> EXTRACT (rules or Claude) -> VALIDATE (plain rules) -> CSV / Airtable
                                                        |
                                              problems? -> "Needs review"
```

## Run it

```bash
pip install requests pypdf reportlab     # reportlab only for make_samples.py
python make_samples.py                   # makes 3 fake contracts with different wording
python run.py                            # rule-based baseline, no API key needed
export ANTHROPIC_API_KEY=sk-ant-...
python run.py --extractor llm            # Claude reads the contracts
python -m unittest discover -s tests
```

Optional Airtable push: create a table whose fields match the CSV columns, then set
`AIRTABLE_TOKEN`, `AIRTABLE_BASE_ID`, `AIRTABLE_TABLE` and add `--airtable`.

## What to expect

Rule-based baseline on the samples: contract A (explicit dates) is filed; B ("30 days
after the expiration of the Due Diligence Period", price written in words) and C ("the
fifteenth day of May, 2027") fail validation and go to review. The LLM extractor should
resolve them: B closes 2027-05-15 (Mar 1 + 45 days = Apr 15, + 30 days), C closes 2027-06-30.
Check this yourself when you run it; I could not run the LLM mode without an API key.

## Design choices

- The LLM only does the fuzzy reading. Dates, price range, parcel format and date
  ordering are checked by `validate.py`, which is deterministic.
- Anything that fails validation is marked "Needs review" rather than written as fact.
- The LLM is told to return null instead of guessing, and to quote the evidence phrase
  for each field so a human can verify it quickly.

## Next steps

- Scanned PDFs: add OCR (e.g. pytesseract) when `pypdf` returns no text.
- Add a human-approval step before rows reach the real tracker.
- Smartsheet sink (same shape as `push_airtable`).
- Score the LLM against 20+ hand-labelled contracts and track accuracy per field.
