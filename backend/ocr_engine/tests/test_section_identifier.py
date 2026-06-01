"""Unit tests for narrative section identification."""

import sys
from pathlib import Path

import pytest

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


def test_section_identifier_accepts_strategy_aliases_from_ocr_headings() -> None:
    pages = [
        NarrativePage(
            20,
            (
                "PESTLE\n"
                "Analysis\n"
                "Political and economical factors affected market demand, "
                "inflation, exports, and regulatory risk during the year."
            ),
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
        NarrativePage(
            25,
            (
                "Strategyand\n"
                "Resource\n"
                "Allocatior\n"
                "Long term priorities include market leadership, working capital "
                "discipline, and export growth."
            ),
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
    ]

    section_pages = SectionIdentifier().identify_sections(pages)

    assert [(page.page_number, page.section) for page in section_pages] == [
        (20, "Strategy"),
        (25, "Strategy"),
    ]


def test_section_identifier_merges_adjacent_short_ocr_heading_lines() -> None:
    pages = [
        NarrativePage(
            52,
            (
                "Chairman's\n"
                "Review\n"
                "I am pleased to present the Chairman's review on overall "
                "performance of the board and the business."
            ),
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
        NarrativePage(
            72,
            (
                "Corporate Social\n"
                "Responsibility\n"
                "The company continued community, safety, employee, and "
                "environment initiatives during the year."
            ),
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
    ]

    identifier = SectionIdentifier()
    section_pages = identifier.identify_sections(pages)

    assert [(page.page_number, page.section) for page in section_pages] == [
        (52, "Chairman Review"),
        (72, "Sustainability"),
    ]
    assert all(
        diagnostic.heading_match
        for diagnostic in identifier.last_report.page_diagnostics
    )


def test_section_identifier_accepts_financial_and_business_review_aliases() -> None:
    pages = [
        NarrativePage(
            12,
            "Financial\nHighlights\nRevenue, profit, and margins improved.",
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
        NarrativePage(
            28,
            "Key Performance\nIndicators\nSales volume and exports improved.",
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
        NarrativePage(
            95,
            (
                "Segmental Review of Business\n"
                "Performance\n"
                "Tractor sales, revenue, and profit are reviewed by segment."
            ),
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
        NarrativePage(
            96,
            "DUPONT\nAnalysis\nNet profit margin and return metrics changed.",
            text_source="ocr",
            pymupdf=False,
            ocr=True,
        ),
    ]

    section_pages = SectionIdentifier().identify_sections(pages)

    assert [(page.page_number, page.section) for page in section_pages] == [
        (12, "Financial Review"),
        (28, "Business Review"),
        (95, "Business Review"),
        (96, "Financial Review"),
    ]


def test_section_identifier_keeps_terminal_exclusions_after_recall_improvements() -> None:
    pages = [
        NarrativePage(
            101,
            (
                "Notes to the Financial Statements\n"
                "Financial Highlights\n"
                "2025 2024\n"
                "Revenue 100 90"
            ),
        ),
        NarrativePage(
            292,
            (
                "Proxy Form\n"
                "Strategy and Resource Allocation\n"
                "Member voting instructions."
            ),
        ),
    ]

    identifier = SectionIdentifier()
    section_pages = identifier.identify_sections(pages)

    assert section_pages == []
    assert identifier.last_report.page_diagnostics[0].rejection_reason == (
        "page_type_notes"
    )
    assert identifier.last_report.page_diagnostics[1].rejection_reason == (
        "page_type_proxy"
    )


def test_section_identifier_resets_low_confidence_continuation_after_budget() -> None:
    """Low-confidence inherited sections should not bleed indefinitely."""

    continuation_text = "\n".join(
        [
            "Market demand remained steady despite inflation pressure.",
            "Update",
            "Costs",
            "Exports",
            "Margins",
        ]
    )
    pages = [
        NarrativePage(1, "Business Review\nExports increased in key markets."),
        NarrativePage(2, continuation_text),
        NarrativePage(3, continuation_text),
        NarrativePage(4, continuation_text),
        NarrativePage(5, continuation_text),
        NarrativePage(6, continuation_text),
        NarrativePage(
            7,
            "Financial Review\nRevenue and profitability improved during the year.",
        ),
        NarrativePage(8, continuation_text),
    ]

    identifier = SectionIdentifier(continuation_page_limit=3)
    section_pages = identifier.identify_sections(pages)
    report = identifier.last_report

    assert [(page.page_number, page.section) for page in section_pages] == [
        (1, "Business Review"),
        (2, "Business Review"),
        (3, "Business Review"),
        (4, "Business Review"),
        (7, "Financial Review"),
        (8, "Financial Review"),
    ]
    page_5 = report.page_diagnostics[4]
    assert page_5.is_continuation is True
    assert page_5.continuation_index == 4
    assert page_5.continuation_budget_exceeded is True
    assert page_5.rejection_reason == "continuation_budget_exceeded"
    assert report.page_diagnostics[5].detected_section is None
    assert report.page_diagnostics[7].is_continuation is True
    assert report.page_diagnostics[7].continuation_index == 1
    assert report.continuation_resets == 1
    assert report.continuation_budget_exceeded == 1


def test_section_identifier_preserves_high_confidence_continuation_over_budget() -> None:
    """Strong narrative continuation should survive the conservative budget."""

    low_confidence_text = "\n".join(
        [
            "Demand remained steady despite inflation pressure.",
            "Update",
            "Costs",
            "Exports",
            "Margins",
        ]
    )
    high_confidence_text = "\n".join(
        [
            "The company delivered strong operational performance in exports.",
            "Management invested in efficiency, safety, and employee welfare.",
            "Demand remained resilient and margins improved during the year.",
            "The business maintained disciplined working capital and liquidity.",
        ]
    )
    pages = [
        NarrativePage(1, "Business Review\nExports increased in key markets."),
        NarrativePage(2, low_confidence_text),
        NarrativePage(3, low_confidence_text),
        NarrativePage(4, low_confidence_text),
        NarrativePage(5, high_confidence_text),
    ]

    identifier = SectionIdentifier(
        continuation_page_limit=3,
        continuation_high_confidence_threshold=0.85,
    )
    section_pages = identifier.identify_sections(pages)
    report = identifier.last_report

    assert [(page.page_number, page.section) for page in section_pages] == [
        (1, "Business Review"),
        (2, "Business Review"),
        (3, "Business Review"),
        (4, "Business Review"),
        (5, "Business Review"),
    ]
    page_5 = report.page_diagnostics[4]
    assert page_5.continuation_index == 4
    assert page_5.continuation_budget_exceeded is True
    assert page_5.confidence_score >= 0.85
    assert page_5.rejection_reason is None
    assert report.continuation_resets == 0
    assert report.continuation_budget_exceeded == 1


def test_section_identifier_rejects_invalid_continuation_configuration() -> None:
    with pytest.raises(ValueError, match="continuation_page_limit"):
        SectionIdentifier(continuation_page_limit=-1)

    with pytest.raises(ValueError, match="continuation_high_confidence_threshold"):
        SectionIdentifier(continuation_high_confidence_threshold=1.1)
