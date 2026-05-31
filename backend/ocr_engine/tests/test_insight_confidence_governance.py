"""Tests for insight confidence governance."""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import Insight
from ocr_engine.governance.insight_confidence_governance import (
    INSIGHT_ROUTE_EXPORT,
    INSIGHT_ROUTE_REJECT,
    INSIGHT_ROUTE_REVIEW,
    InsightConfidenceGovernance,
)


def _insight(
    *,
    confidence: float,
    area: str = "Risks",
    takeaway: str = "Demand changed during the year.",
) -> Insight:
    return Insight(
        value_year=2025,
        source_report_year=2025,
        area=area,
        takeaway=takeaway,
        source_section="Risks",
        page_number=63,
        confidence=confidence,
    )


def test_confidence_governance_rejects_low_confidence_non_quantified_insight() -> None:
    result = InsightConfidenceGovernance().apply(
        [_insight(confidence=0.2, takeaway="Market outlook remains uncertain.")]
    )

    assert result.exported_insights == []
    assert result.review_insights == []
    assert result.rejected_low_confidence_count == 1
    assert result.decisions[0].route == INSIGHT_ROUTE_REJECT
    assert result.decisions[0].reason == "confidence_below_reject_threshold"


def test_confidence_governance_routes_review_bucket() -> None:
    insight = _insight(
        confidence=0.6,
        takeaway="Tractor export earnings are tracked as a growth lever.",
    )

    result = InsightConfidenceGovernance().apply([insight])

    assert result.review_insights == [insight]
    assert result.exported_insights == []
    assert result.rejected_insights == []
    assert result.decisions[0].route == INSIGHT_ROUTE_REVIEW


def test_confidence_governance_filters_generic_governance_boilerplate() -> None:
    result = InsightConfidenceGovernance().apply(
        [
            _insight(
                confidence=0.6,
                area="Internal controls",
                takeaway=(
                    "Adequate internal financial controls are in place and "
                    "are being observed."
                ),
            )
        ]
    )

    assert result.review_insights == []
    assert result.rejected_low_confidence_count == 1
    assert result.generic_filtered_count == 1
    assert result.decisions[0].reason == (
        "generic_low_confidence_without_quantitative_evidence"
    )


def test_confidence_governance_retains_quantified_low_confidence_for_review() -> None:
    insight = _insight(
        confidence=0.0,
        area="Sustainability / energy efficiency",
        takeaway=(
            "Generated 799,551 kWh renewable electricity and avoided "
            "679.62 tons of CO2 emissions."
        ),
    )

    result = InsightConfidenceGovernance().apply([insight])

    assert result.review_insights == [insight]
    assert result.rejected_insights == []
    assert result.decisions[0].route == INSIGHT_ROUTE_REVIEW
    assert result.decisions[0].reason == "low_confidence_quantified_safety_review"


def test_confidence_governance_exports_high_confidence_insight() -> None:
    insight = _insight(confidence=0.9)

    result = InsightConfidenceGovernance().apply([insight])

    assert result.exported_insights == [insight]
    assert result.decisions[0].route == INSIGHT_ROUTE_EXPORT
    assert result.confidence_distribution == {
        "0.0": 0,
        "0.1-0.5": 0,
        "0.5-0.7": 0,
        "0.7-0.9": 0,
        "0.9+": 1,
    }


def test_confidence_governance_writes_filtering_audit() -> None:
    output_path = Path("output/test_insight_filtering_audit.json")
    governance = InsightConfidenceGovernance()
    result = governance.apply(
        [
            _insight(confidence=0.9),
            _insight(confidence=0.6),
            _insight(confidence=0.1),
        ]
    )

    governance.write_audit(result, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["final_exported_insight_count"] == 1
    assert payload["review_bucket_count"] == 1
    assert payload["rejected_low_confidence_count"] == 1
