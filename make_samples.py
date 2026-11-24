"""Generate three fake purchase agreements (PDF) that word the same facts differently.

All names, parcels and amounts are invented.
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).parent / "sample_contracts"

CONTRACTS = {
    "contract_a_explicit_dates.pdf": [
        "REAL ESTATE PURCHASE AGREEMENT",
        "This Agreement is made on January 10, 2027 (the \"Effective Date\") between "
        "Riverbend Holdings LLC (\"Seller\") and Anchor Demo Land Group (\"Buyer\").",
        "1. Property. Vacant land identified as Parcel ID 12-34-567-890, approx. 14.2 acres.",
        "2. Purchase Price. Purchase Price: $1,250,000.00, payable at Closing.",
        "3. Due Diligence. Buyer's due diligence period ends on February 9, 2027.",
        "4. Closing Date: March 15, 2027.",
        "5. Contingencies. This Agreement is contingent upon (a) satisfactory Phase I "
        "environmental report, (b) rezoning approval, and (c) clear title commitment.",
    ],
    "contract_b_relative_dates.pdf": [
        "PURCHASE AND SALE AGREEMENT",
        "Effective Date: March 1, 2027. Seller: Oakmont Family Trust. "
        "Buyer: Anchor Demo Land Group.",
        "Section 1. The land is located at Lot 7, Cedar Ridge, Parcel No. 45-67-890-123.",
        "Section 2. The purchase price shall be One Million Eight Hundred Thousand "
        "Dollars ($1,800,000.00).",
        "Section 3. Buyer may terminate for any reason within forty-five (45) days "
        "after the Effective Date (the \"Due Diligence Period\").",
        "Section 4. Closing shall occur on or before thirty (30) days after the "
        "expiration of the Due Diligence Period.",
        "Section 5. Buyer's obligation to close is subject to obtaining financing "
        "and a satisfactory survey.",
    ],
    "contract_c_messy_wording.pdf": [
        "LAND SALE CONTRACT",
        "Dated this 2nd day of April, 2027, by and between Hartwell Properties, Inc. "
        "as seller and Anchor Demo Land Group as purchaser.",
        "The premises (tax parcel 98-76-543-210) are sold for the sum of "
        "$2,400,000, of which $50,000 is earnest money.",
        "Purchaser shall complete its inspections no later than the fifteenth day of "
        "May, 2027. Title shall pass at a closing to be held on or before the "
        "thirtieth day of June, 2027.",
        "This sale is conditioned on utility availability confirmation and "
        "approval of the preliminary site plan by the county.",
    ],
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    styles = getSampleStyleSheet()
    for name, paragraphs in CONTRACTS.items():
        doc = SimpleDocTemplate(str(OUT / name), pagesize=letter)
        story = []
        for i, text in enumerate(paragraphs):
            story.append(Paragraph(text, styles["Title" if i == 0 else "BodyText"]))
            story.append(Spacer(1, 10))
        doc.build(story)
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
