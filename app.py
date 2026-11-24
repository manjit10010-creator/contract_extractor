"""Streamlit interface for the Contract Extractor demo."""

import csv
import io
import tempfile
from pathlib import Path

import streamlit as st

from extractors import GeminiExtractor
from run import process_file
from sinks import COLUMNS, BID_COLUMNS


st.set_page_config(
    page_title="Contract Extractor",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Contract Extractor")
st.caption(
    "AI-assisted extraction and verification for purchase agreements "
    "and subcontractor bid proposals."
)

st.info(
    "Upload a PDF to extract its key information, inspect supporting "
    "evidence, and download a structured CSV result."
)

st.warning(
    "Document text is sent to Google Gemini for processing. "
    "Only upload documents you are authorized to share. "
    "Scanned PDFs without extractable text may not work."
)


def get_gemini_extractor():
    """Create Gemini extractor using Streamlit's secret configuration."""
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        st.error(
            "Gemini API key is not configured. Add GEMINI_API_KEY "
            "to your Streamlit secrets before processing documents."
        )
        st.stop()

    model = st.secrets.get("GEMINI_MODEL")

    return GeminiExtractor(
        api_key=api_key,
        model=model,
    )


def make_csv(row: dict, columns: list[str]) -> bytes:
    """Serialize one result using its existing project CSV schema."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=columns,
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def display_result(result: dict) -> None:
    """Display extraction results and provide the matching CSV."""
    record = result["record"]
    problems = result["problems"]
    row = result["row"]

    is_bid = "project_name" in row

    if is_bid:
        document_type = "Subcontractor bid"
        columns = BID_COLUMNS
        download_name = "subcontractor_bid_results.csv"
    else:
        columns = COLUMNS
        download_name = "purchase_agreement_results.csv"

        if row.get("extractor") == "classifier":
            document_type = "Unrecognized document"
        else:
            document_type = "Purchase agreement"

    st.divider()
    st.subheader("Processing result")

    col1, col2, col3 = st.columns(3)

    col1.metric("Document type", document_type)
    col2.metric("Processing status", row["status"])
    col3.metric("Extractor", row.get("extractor") or "Unknown")

    st.caption(f"File: {result['filename']}")

    if row["status"] == "Auto-filed":
        st.success(
            "All configured validation and evidence checks passed. "
            "The result is marked Auto-filed."
        )
    else:
        st.warning(
            "This document requires human review before its information "
            "should be treated as verified."
        )

    st.subheader("Extracted information")

    extracted_fields = {
        key: value
        for key, value in record.items()
        if key != "evidence"
    }

    st.json(extracted_fields, expanded=True)

    st.subheader("Evidence")

    evidence = row.get("evidence", "")

    if evidence:
        with st.expander("View supporting evidence", expanded=True):
            st.text(evidence)
    else:
        st.caption("No evidence entries were returned.")

    st.subheader("Validation and review")

    if problems:
        for problem in problems:
            st.error(problem)
    else:
        st.success("No validation or evidence problems were reported.")

    with st.expander("Processing metadata"):
        st.write("Extractor:", row.get("extractor"))
        st.write("Model:", row.get("model"))
        st.write("Document:", row.get("file"))

    st.subheader("Download results")

    csv_data = make_csv(row, columns)

    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name=download_name,
        mime="text/csv",
        type="primary",
    )


uploaded_file = st.file_uploader(
    "Choose a PDF document",
    type=["pdf"],
    help="Supported documents: purchase agreements and subcontractor bids.",
)

if uploaded_file is not None:
    st.write(f"Selected file: **{uploaded_file.name}**")
    st.write(f"File size: {uploaded_file.size / 1024:.1f} KB")

    if uploaded_file.size == 0:
        st.error("The uploaded file is empty.")

    elif uploaded_file.size > 20 * 1024 * 1024:
        st.error("The maximum supported upload size is 20 MB.")

    elif st.button("Extract document", type="primary"):
        extractor = get_gemini_extractor()

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".pdf",
                delete=False,
            ) as temp_file:
                temp_file.write(uploaded_file.getvalue())
                temp_path = Path(temp_file.name)

            with st.spinner(
                "Classifying, extracting, and validating your document..."
            ):
                record, problems, row = process_file(
                    temp_path,
                    extractor,
                )
                row["file"] = uploaded_file.name
            st.session_state["extraction_result"] = {
                "record": record,
                "problems": problems,
                "row": row,
                "filename": uploaded_file.name,
            }

        except Exception as error:
            st.error(
                f"Application error: {type(error).__name__}: {error}"
            )

        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

if "extraction_result" in st.session_state:
    display_result(st.session_state["extraction_result"])

st.divider()
st.caption(
    "Contract Extractor | Gemini-powered extraction | "
    "Human review for uncertain or incomplete results"
)
