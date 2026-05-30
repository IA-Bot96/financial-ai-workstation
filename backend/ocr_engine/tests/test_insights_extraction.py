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
        area="Debt",
        takeaway="Debt increased due to Southeast Asia expansion financing.",
        source_section="Management Discussion & Analysis",
        page=84,
    )

    assert insight.area == "Debt"
    assert insight.takeaway == "Debt increased due to Southeast Asia expansion financing."
    assert insight.source_section == "Management Discussion & Analysis"
    assert insight.page == 84


def test_insight_accepts_generic_business_area() -> None:
    insight = Insight(
        area="ESG Initiatives",
        takeaway="The company expanded its renewable energy sourcing program.",
        source_section="Sustainability",
        page=118,
    )

    assert insight.area == "ESG Initiatives"


def test_insight_requires_positive_page() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Insight(
            area="Debt",
            takeaway="Debt increased during the reporting period.",
            source_section="Management Discussion & Analysis",
            page=0,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


@pytest.mark.parametrize("field_name", ["area", "takeaway", "source_section"])
def test_insight_requires_non_empty_text_fields(field_name: str) -> None:
    payload = {
        "area": "Debt",
        "takeaway": "Debt increased during the reporting period.",
        "source_section": "Management Discussion & Analysis",
        "page": 84,
    }
    payload[field_name] = ""

    with pytest.raises(ValidationError) as exc_info:
        Insight(**payload)

    assert exc_info.value.errors()[0]["type"] == "string_too_short"


def test_insight_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Insight(
            area="Cost Pressures",
            takeaway="Input costs increased due to higher freight rates.",
            source_section="Operating Review",
            page=64,
            recommendation="Review supplier contracts.",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_insights_extraction_result_serializes_expected_output() -> None:
    result = InsightsExtractionResult(
        insights=[
            Insight(
                area="Debt",
                takeaway="Debt increased due to Southeast Asia expansion financing.",
                source_section="Management Discussion & Analysis",
                page=84,
            ),
            Insight(
                area="Geographic Expansion",
                takeaway="The company plans to expand into Africa and the Middle East.",
                source_section="Risks & Opportunities",
                page=92,
            ),
        ]
    )

    assert result.model_dump() == {
        "insights": [
            {
                "area": "Debt",
                "takeaway": "Debt increased due to Southeast Asia expansion financing.",
                "source_section": "Management Discussion & Analysis",
                "page": 84,
            },
            {
                "area": "Geographic Expansion",
                "takeaway": "The company plans to expand into Africa and the Middle East.",
                "source_section": "Risks & Opportunities",
                "page": 92,
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
