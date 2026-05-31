"""Unit tests for insights extraction models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import (
    Insight,
    InsightsExtractionDiagnostics,
    InsightsExtractionResult,
)


def test_insight_accepts_valid_payload() -> None:
    insight = Insight(
        value_year=2024,
        source_report_year=2025,
        area="Debt",
        takeaway="Debt increased due to Southeast Asia expansion financing.",
        source_section="Management Discussion & Analysis",
        page_number=84,
        confidence=0.91,
    )

    assert insight.area == "Debt"
    assert insight.value_year == 2024
    assert insight.source_report_year == 2025
    assert insight.takeaway == "Debt increased due to Southeast Asia expansion financing."
    assert insight.source_section == "Management Discussion & Analysis"
    assert insight.page_number == 84
    assert insight.confidence == 0.91


def test_insight_accepts_generic_business_area() -> None:
    insight = Insight(
        value_year=2024,
        source_report_year=2025,
        area="ESG Initiatives",
        takeaway="The company expanded its renewable energy sourcing program.",
        source_section="Sustainability",
        page_number=118,
        confidence=0.87,
    )

    assert insight.area == "ESG Initiatives"


def test_insight_requires_positive_page() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Insight(
            value_year=2024,
            source_report_year=2025,
            area="Debt",
            takeaway="Debt increased during the reporting period.",
            source_section="Management Discussion & Analysis",
            page_number=0,
            confidence=0.9,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


def test_insight_requires_confidence_between_zero_and_one() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Insight(
            value_year=2024,
            source_report_year=2025,
            area="Debt",
            takeaway="Debt increased during the reporting period.",
            source_section="Management Discussion & Analysis",
            page_number=84,
            confidence=1.2,
        )

    assert exc_info.value.errors()[0]["type"] == "less_than_equal"


@pytest.mark.parametrize("field_name", ["area", "takeaway", "source_section"])
def test_insight_requires_non_empty_text_fields(field_name: str) -> None:
    payload = {
        "area": "Debt",
        "value_year": 2024,
        "source_report_year": 2025,
        "takeaway": "Debt increased during the reporting period.",
        "source_section": "Management Discussion & Analysis",
        "page_number": 84,
        "confidence": 0.9,
    }
    payload[field_name] = ""

    with pytest.raises(ValidationError) as exc_info:
        Insight(**payload)

    assert exc_info.value.errors()[0]["type"] == "string_too_short"


def test_insight_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Insight(
            value_year=2024,
            source_report_year=2025,
            area="Cost Pressures",
            takeaway="Input costs increased due to higher freight rates.",
            source_section="Operating Review",
            page_number=64,
            confidence=0.85,
            recommendation="Review supplier contracts.",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_insights_extraction_result_serializes_expected_output() -> None:
    result = InsightsExtractionResult(
        insights=[
            Insight(
                value_year=2024,
                source_report_year=2025,
                area="Debt",
                takeaway="Debt increased due to Southeast Asia expansion financing.",
                source_section="Management Discussion & Analysis",
                page_number=84,
                confidence=0.91,
            ),
            Insight(
                value_year=2024,
                source_report_year=2025,
                area="Geographic Expansion",
                takeaway="The company plans to expand into Africa and the Middle East.",
                source_section="Risks & Opportunities",
                page_number=92,
                confidence=0.88,
            ),
        ]
    )

    assert result.model_dump() == {
        "insights": [
            {
                "value_year": 2024,
                "source_report_year": 2025,
                "area": "Debt",
                "takeaway": "Debt increased due to Southeast Asia expansion financing.",
                "source_section": "Management Discussion & Analysis",
                "page_number": 84,
                "confidence": 0.91,
            },
            {
                "value_year": 2024,
                "source_report_year": 2025,
                "area": "Geographic Expansion",
                "takeaway": "The company plans to expand into Africa and the Middle East.",
                "source_section": "Risks & Opportunities",
                "page_number": 92,
                "confidence": 0.88,
            },
        ],
        "diagnostics": {
            "total_pages_processed": 0,
            "pages_with_text": 0,
            "total_text_characters": 0,
            "section_pages": 0,
            "total_chunks_created": 0,
            "chunk_size": 0,
            "chunk_overlap": 0,
            "retrieval_strategy": "section_balanced_score_all_relevant_chunks",
            "top_k": None,
            "chunks_sent_to_llm": 0,
            "llm_call_count": 0,
            "generated_insights": 0,
            "section_page_count_by_section": {},
            "chunk_count_by_section": {},
            "ranked_chunk_count_by_section": {},
            "insight_count_by_section": {},
        },
    }


def test_insights_diagnostics_serializes_section_counts() -> None:
    diagnostics = InsightsExtractionDiagnostics(
        total_pages_processed=400,
        pages_with_text=312,
        total_text_characters=745000,
        section_pages=84,
        total_chunks_created=126,
        chunk_size=2800,
        chunk_overlap=250,
        top_k=None,
        chunks_sent_to_llm=96,
        llm_call_count=12,
        generated_insights=54,
        insight_count_by_section={"Business Review": 29, "Risks": 8},
    )

    assert diagnostics.model_dump()["insight_count_by_section"] == {
        "Business Review": 29,
        "Risks": 8,
    }


def test_insights_extraction_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        InsightsExtractionResult(
            insights=[],
            model_version="v1",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
