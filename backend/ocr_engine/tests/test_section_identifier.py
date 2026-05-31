"""Unit tests for narrative section identification."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.narrative_text_extractor import NarrativePage
from ocr_engine.services.section_identifier import SectionIdentifier


def test_section_identifier_keeps_relevant_sections_and_ignores_boilerplate() -> None:
    pages = [
        NarrativePage(1, "Business Review\nExports increased in the Middle East."),
        NarrativePage(2, "Capacity expansion continued during the year."),
        NarrativePage(3, "Independent Auditor's Report\nOpinion on statements."),
    ]

    section_pages = SectionIdentifier().identify_sections(pages)

    assert [(page.page_number, page.section) for page in section_pages] == [
        (1, "Business Review"),
        (2, "Business Review"),
    ]


def test_section_identifier_reports_page_type_confidence_and_rejections() -> None:
    pages = [
        NarrativePage(
            1,
            (
                "Directors Report\n"
                "The Directors are pleased to present their report together "
                "with the audited financial statements."
            ),
        ),
        NarrativePage(
            2,
            "Notes to the Financial Statements\n2025 2024\nRevenue 100 90",
        ),
        NarrativePage(3, "2025\n2024\n100\n200"),
        NarrativePage(4, "", text_source="none", pymupdf=False, ocr=False),
    ]

    identifier = SectionIdentifier()
    section_pages = identifier.identify_sections(pages)
    report = identifier.last_report

    assert [(page.page_number, page.section) for page in section_pages] == [
        (1, "Directors Report")
    ]
    assert report.total_pages == 4
    assert report.accepted_pages == 1
    assert report.rejected_pages == 3
    assert report.page_diagnostics[0].detected_section == "Directors Report"
    assert report.page_diagnostics[0].confidence_score >= 0.55
    assert report.page_diagnostics[1].page_type == "notes"
    assert report.page_diagnostics[1].rejection_reason == "page_type_notes"
    assert report.page_diagnostics[2].rejection_reason in {
        "no_section_candidate",
        "page_type_table_heavy",
    }
    assert report.page_diagnostics[3].rejection_reason == "no_text"
