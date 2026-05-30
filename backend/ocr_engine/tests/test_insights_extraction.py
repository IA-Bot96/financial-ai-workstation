"""Unit tests for insights extraction models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult


def test_insight_accepts_valid_payload() -> None:
    insight = Insight(
        year=2024,
        area="Debt",
        takeaway="Debt increased due to Southeast Asia expansion financing.",
        source_section="Management Discussion & Analysis",
        page_number=84,
        confidence=0.91,
    )

    assert insight.area == "Debt"
    assert insight.year == 2024
    assert insight.takeaway == "Debt increased due to Southeast Asia expansion financing."
    assert insight.source_section == "Management Discussion & Analysis"
    assert insight.page_number == 84
    assert insight.confidence == 0.91


def test_insight_accepts_generic_business_area() -> None:
    insight = Insight(
        year=2024,
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
            year=2024,
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
            year=2024,
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
        "year": 2024,
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
            year=2024,
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
                year=2024,
                area="Debt",
                takeaway="Debt increased due to Southeast Asia expansion financing.",
                source_section="Management Discussion & Analysis",
                page_number=84,
                confidence=0.91,
            ),
            Insight(
                year=2024,
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
                "year": 2024,
                "area": "Debt",
                "takeaway": "Debt increased due to Southeast Asia expansion financing.",
                "source_section": "Management Discussion & Analysis",
                "page_number": 84,
                "confidence": 0.91,
            },
            {
                "year": 2024,
                "area": "Geographic Expansion",
                "takeaway": "The company plans to expand into Africa and the Middle East.",
                "source_section": "Risks & Opportunities",
                "page_number": 92,
                "confidence": 0.88,
            },
        ]
    }


def test_insights_extraction_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        InsightsExtractionResult(
            insights=[],
            model_version="v1",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
