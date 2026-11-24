
"""Generate fictional subcontractor bid PDFs for testing."""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)
from reportlab.lib.units import inch


OUTPUT_DIR = Path(__file__).parent / "sample_bids"


SAMPLES = {
    "bid_a_complete.pdf": {
        "title": "SUBCONTRACTOR BID PROPOSAL",
        "body": [
            ("Project", "Riverside Office Renovation"),
            ("Submitted to", "Westbridge General Contractors"),
            ("Subcontractor", "Northstar Electrical LLC"),
            ("Contact", "Daniel Morgan"),
            ("Email", "daniel@northstarelectrical.example"),
            ("Trade", "Electrical"),
            ("Base bid", "$125,000.00 USD"),
            ("Scope of work", "Provide electrical labor, wiring, outlets, lighting installation, and panel upgrades."),
            ("Inclusions", "All electrical labor, standard wiring, installation materials, and testing."),
            ("Exclusions", "Permit fees, concealed hazardous materials, and work outside the electrical scope."),
            ("Allowance", "Lighting fixture allowance: $8,000.00."),
            ("Alternate", "Upgrade to premium lighting controls: Add $4,500.00."),
            ("Proposed duration", "Work will require 30 calendar days after site access."),
            ("Quote validity", "This bid remains valid until December 15, 2026."),
            ("Payment terms", "Payment is due within 30 days of approved invoices."),
            ("Clarifications", "Pricing assumes normal working hours and uninterrupted site access."),
        ],
    },

    "bid_b_alternates.pdf": {
        "title": "SUBCONTRACTOR BID PROPOSAL",
        "body": [
            ("Project", "Oakwood Retail Fit-Out"),
            ("Submitted to", "Summit Construction Group"),
            ("Subcontractor", "Precision Flooring Services"),
            ("Contact", "Maria Chen"),
            ("Email", "maria@precisionflooring.example"),
            ("Trade", "Flooring"),
            ("Base bid", "$86,500.00 USD"),
            ("Scope of work", "Supply and install flooring throughout the retail premises."),
            ("Inclusions", "Floor preparation, standard installation labor, and adhesive."),
            ("Exclusions", "Structural repairs and removal of hazardous materials."),
            ("Allowance", "Subfloor repair allowance: $6,000.00."),
            ("Alternate 1", "Upgrade to premium porcelain tile: Add $12,500.00."),
            ("Alternate 2", "Use standard vinyl flooring instead: Deduct $9,000.00."),
            ("Proposed duration", "Estimated completion time is 24 calendar days."),
            ("Quote validity", "This quotation expires on January 10, 2027."),
            ("Payment terms", "Progress payments are due within 15 days of invoice approval."),
            ("Clarifications", "Final quantities are subject to field measurement."),
        ],
    },

    "bid_c_missing_fields.pdf": {
        "title": "CONSTRUCTION BID PROPOSAL",
        "body": [
            ("Project", "Greenfield Warehouse Expansion"),
            ("Submitted to", "Atlas Building Contractors"),
            ("Subcontractor", "Clearline Plumbing"),
            ("Trade", "Plumbing"),
            ("Base bid", "$54,200.00 USD"),
            ("Scope of work", "Install domestic water supply and drainage systems."),
            ("Inclusions", "Standard plumbing labor, pipes, fittings, and installation."),
            ("Exclusions", "Excavation and external utility connection charges."),
            ("Payment terms", "Payment terms to be agreed before contract execution."),
        ],
    },

    "bid_d_ambiguous.pdf": {
        "title": "SUBCONTRACTOR QUOTATION",
        "body": [
            ("Project", "Central Avenue Commercial Renovation"),
            ("Submitted to", "Meridian Project Management"),
            ("Subcontractor", "Apex Mechanical Contractors"),
            ("Trade", "HVAC"),
            ("Base bid", "$72,000.00 USD"),
            ("Pricing note", "The total may be $72,000 or $79,000 depending on final equipment selection."),
            ("Scope of work", "Provide HVAC equipment, ductwork, and installation."),
            ("Inclusions", "Equipment and installation labor, subject to final selection."),
            ("Exclusions", "Electrical connections and structural modifications."),
            ("Allowance", "Equipment allowance is approximately $10,000, subject to confirmation."),
            ("Alternate", "High-efficiency equipment option: price to be confirmed."),
            ("Duration", "Completion expected in approximately four to six weeks."),
            ("Validity", "Quote validity will be confirmed after final site inspection."),
            ("Payment terms", "Payment schedule subject to negotiation."),
            ("Clarification", "Final scope and pricing require written confirmation from both parties."),
        ],
    },
}


def create_pdf(filename: str, sample: dict) -> None:
    """Create one readable PDF document."""
    path = OUTPUT_DIR / filename

    document = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph(sample["title"], styles["Title"]),
        Spacer(1, 18),
    ]

    for heading, value in sample["body"]:
        story.append(
            Paragraph(f"<b>{heading}:</b> {value}", styles["BodyText"])
        )
        story.append(Spacer(1, 9))

    story.append(Spacer(1, 15))
    story.append(
        Paragraph(
            "Fictional document generated for software testing. "
            "Not a real offer or contractual commitment.",
            styles["Italic"],
        )
    )

    document.build(story)
    print(f"Created: {path}")


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for filename, sample in SAMPLES.items():
        create_pdf(filename, sample)

    print(f"\nGenerated {len(SAMPLES)} sample bids in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
