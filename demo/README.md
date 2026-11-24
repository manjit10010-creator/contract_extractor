# Contract Extractor Demo

## Overview

This demonstration showcases a Python-based document extraction workflow for two document types:

1. Real-estate purchase agreements
2. Subcontractor construction bids

The system extracts structured fields from PDF documents, validates the extracted data, checks evidence against the source text, and routes incomplete or ambiguous records for human review.

All documents in this demonstration are fictional.

## Demonstration results

### Purchase agreements

| Document | Result | Explanation |
|---|---|---|
| contract_a_explicit_dates.pdf | Auto-filed | Required information extracted successfully |
| contract_b_relative_dates.pdf | Needs review | Purchase price and closing date are missing |
| contract_c_messy_wording.pdf | Needs review | Parcel ID, purchase price and closing date are missing |

### Subcontractor bids

| Document | Result | Explanation |
|---|---|---|
| bid_a_complete.pdf | Auto-filed | Complete electrical bid with supported values |
| bid_b_alternates.pdf | Auto-filed | Flooring bid with additive and deductive alternates |
| bid_c_missing_fields.pdf | Needs review | Missing contact details, duration and validity date; payment terms unresolved |
| bid_d_ambiguous.pdf | Needs review | Conflicting base bid amounts and unsupported clarification |

## Example extraction

**Riverside Office Renovation**

- Contractor: Northstar Electrical LLC
- Trade: Electrical
- Base bid: USD 125,000
- Alternate: Premium lighting controls, additional USD 4,500
- Allowance: Lighting fixtures, USD 8,000
- Duration: 30 days
- Quote validity: December 15, 2026

## Review behavior

The system does not automatically resolve every uncertainty.

Examples include:

- Missing required fields
- Conflicting amounts
- Unsupported extracted evidence
- Incomplete commercial terms

These records are marked `Needs review` rather than silently accepted.

## Running the demonstration

The curated CSV files in this folder contain results from previous demonstration runs.

To run the purchase-agreement workflow using the rule-based extractor:

```powershell
python run.py --extractor rules --pdf-dir .\sample_contracts --out .\demo\purchase_run.csv
```

For AI-based extraction, configure the appropriate API key and select `llm` or `gemini`.

In rules mode, subcontractor bids are deliberately routed to human review because the bid workflow requires an AI extractor. Running the pipeline again may produce different results from the curated CSV files.
## Files

- `*.pdf`: Fictional source documents
- `purchase_demo_results.csv`: Curated purchase-agreement results
- `bid_demo_results.csv`: Curated subcontractor-bid results
- `README.md`: This demonstration guide

## Limitations

- PDF text extraction only; scanned documents requiring OCR are not supported.
- Classification uses conservative text-pattern matching.
- Evidence checks establish textual support, not guaranteed semantic correctness.
- Auto-filed results still require appropriate operational oversight.
- Human review is necessary for ambiguous or incomplete documents.
- The sample documents are fictional and do not establish legal or commercial suitability.

**Design principle:** AI extracts. Deterministic checks validate. Humans resolve uncertainty.
