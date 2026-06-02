"""Unit tests for Forecast Validation Engine Phase 1 models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    ForecastValidationResult,
    ValidationCategory,
    ValidationCategoryScore,
    ValidationCitation,
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
    ValidationScorecard,
    ValidationSeverity,
)


def _confidence(score: float = 0.9) -> ValidationConfidence:
    return ValidationConfidence(score=score, rationale=("deterministic evidence",))


def _evidence() -> ValidationEvidence:
    return ValidationEvidence(
        evidence_id="revenue:2025:baseline",
        category=ValidationCategory.HISTORICAL_BASELINE,
        summary="Revenue baseline is blocked by candidate spread.",
        metrics=("revenue",),
        value_years=(2025,),
        historical_baseline_status="baseline_not_validatable",
        calculations={"candidate_spread": 125.0},
        citations=(
            ValidationCitation(
                citation_id="rev_2025_cell",
                sheet_name="Income Statement",
                cell_reference="B12",
                row=12,
                column=2,
                page_number=164,
                source_report_year=2025,
                table_type="income_statement",
            ),
        ),
    )


def _issue() -> ValidationIssue:
    return ValidationIssue(
        issue_id="revenue:baseline_not_validatable",
        category=ValidationCategory.HISTORICAL_BASELINE,
        severity=ValidationSeverity.CRITICAL,
        outcome=ValidationOutcome.FAIL,
        title="Revenue baseline is not validatable",
        description="Revenue has candidate spread above the MVP threshold.",
        affected_metrics=("revenue",),
        value_years=(2025,),
        historical_baseline_status="baseline_not_validatable",
        evidence_ids=("revenue:2025:baseline",),
        is_blocking=True,
        confidence=_confidence(),
    )


def _scorecard() -> ValidationScorecard:
    return ValidationScorecard(
        overall_outcome=ValidationOutcome.FAIL,
        overall_score=0,
        category_scores=(
            ValidationCategoryScore(
                category=ValidationCategory.HISTORICAL_BASELINE,
                outcome=ValidationOutcome.FAIL,
                score=0,
                issue_count=1,
                blocking_issue_count=1,
                confidence=_confidence(),
            ),
        ),
        confidence=_confidence(),
        issue_count=1,
        blocking_issue_count=1,
    )


def test_forecast_validation_result_serializes_and_roundtrips() -> None:
    result = ForecastValidationResult(
        validation_id="fv_lucky_2025_001",
        company_name="Lucky Cement Limited",
        workbook_id="wb_lucky",
        workbook_fingerprint="abc123",
        overall_outcome=ValidationOutcome.FAIL,
        historical_baseline_statuses={
            "revenue": "baseline_not_validatable",
            "earnings_per_share": "clean_with_warning",
            "total_debt": "missing",
        },
        issues=(_issue(),),
        evidence=(_evidence(),),
        scorecard=_scorecard(),
        confidence=_confidence(),
    )

    payload = result.model_dump(mode="json")
    roundtrip = ForecastValidationResult.model_validate(payload)

    assert payload["overall_outcome"] == "fail"
    assert payload["historical_baseline_statuses"]["total_debt"] == "missing"
    assert roundtrip.validation_id == result.validation_id
    assert roundtrip.evidence[0].citations[0].cell_reference == "B12"


def test_invalid_historical_baseline_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ValidationEvidence(
            evidence_id="bad_status",
            category=ValidationCategory.DATA_QUALITY,
            summary="Invalid baseline status.",
            historical_baseline_status="requires_review",
        )


def test_result_rejects_missing_evidence_references() -> None:
    with pytest.raises(ValidationError, match="missing evidence ids"):
        ForecastValidationResult(
            validation_id="fv_missing_evidence",
            overall_outcome=ValidationOutcome.FAIL,
            issues=(_issue(),),
            evidence=(),
            scorecard=_scorecard(),
            confidence=_confidence(),
        )


def test_critical_issue_must_be_blocking() -> None:
    with pytest.raises(ValidationError, match="critical validation issues"):
        ValidationIssue(
            issue_id="critical_non_blocking",
            category=ValidationCategory.DATA_QUALITY,
            severity=ValidationSeverity.CRITICAL,
            outcome=ValidationOutcome.WARNING,
            title="Critical but non-blocking",
            description="Invalid structural state.",
            evidence_ids=("e1",),
            is_blocking=False,
            confidence=_confidence(),
        )


def test_blocking_issue_cannot_have_pass_outcome() -> None:
    with pytest.raises(ValidationError, match="blocking validation issues"):
        ValidationIssue(
            issue_id="blocking_pass",
            category=ValidationCategory.DATA_QUALITY,
            severity=ValidationSeverity.HIGH,
            outcome=ValidationOutcome.PASS,
            title="Blocking pass",
            description="Invalid structural state.",
            evidence_ids=("e1",),
            is_blocking=True,
            confidence=_confidence(),
        )


def test_score_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        ValidationConfidence(score=1.1)

    with pytest.raises(ValidationError):
        ValidationCategoryScore(
            category=ValidationCategory.REVENUE,
            outcome=ValidationOutcome.PASS,
            score=101,
            confidence=_confidence(),
        )


def test_scorecard_rejects_inconsistent_issue_counts() -> None:
    with pytest.raises(ValidationError, match="blocking_issue_count"):
        ValidationScorecard(
            overall_outcome=ValidationOutcome.WARNING,
            overall_score=70,
            confidence=_confidence(),
            issue_count=1,
            blocking_issue_count=2,
        )


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        ValidationConfidence(score=0.8, unexpected=True)  # type: ignore[call-arg]
