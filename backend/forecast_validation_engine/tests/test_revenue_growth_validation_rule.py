"""Tests for revenue forecast growth validation."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    ForecastInput,
    ValidationAdmissionStatus,
    ValidationContext,
    ValidationEngineInput,
    ValidationOutcome,
)
from forecast_validation_engine.rules import RevenueGrowthValidationRule  # noqa: E402
from forecast_validation_engine.services import (  # noqa: E402
    ForecastValidationFramework,
    ValidationRuleRegistry,
)
from shared.models.historical_series_integrity import (  # noqa: E402
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
    ScaleConsistencyResult,
    SeriesValueCandidateEvidence,
)


def _candidate(year: int, value: float) -> SeriesValueCandidateEvidence:
    return SeriesValueCandidateEvidence(
        metric="revenue",
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=292,
        table_type="income_statement",
        source_class="primary_statement",
        statement_scope="consolidated",
        normalization_confidence=0.98,
        source_confidence=0.97,
        original_metric="Revenue",
        requires_review=False,
        is_currently_selected=True,
    )


def _issue(issue_type: str) -> HistoricalSeriesIntegrityIssue:
    return HistoricalSeriesIntegrityIssue(
        issue_type=issue_type,
        severity="critical",
        metric="revenue",
        value_years=[2025],
        description=f"Revenue issue: {issue_type}",
        blocking=True,
        fixability="review_only",
        evidence_ids=[f"revenue:{issue_type}"],
    )


def _series_result(
    status: str,
    *,
    values: tuple[tuple[int, float], ...] = ((2023, 100.0), (2024, 110.0), (2025, 121.0)),
    confidence: float = 0.94,
) -> HistoricalSeriesIntegrityResult:
    selected_series = [_candidate(year, value) for year, value in values]
    return HistoricalSeriesIntegrityResult(
        metric="revenue",
        status=status,  # type: ignore[arg-type]
        value_years=[year for year, _ in values],
        selected_series=selected_series if status != "missing" else [],
        blocking_issues=(
            [_issue("candidate_spread_gt_100x")]
            if status == "baseline_not_validatable"
            else []
        ),
        warning_issues=[],
        candidate_spread_by_year=[],
        yoy_scale_issues=[],
        source_policy_violations=[],
        scale_result=ScaleConsistencyResult(
            status="fail" if status == "baseline_not_validatable" else "pass",
            max_candidate_spread=150.0
            if status == "baseline_not_validatable"
            else None,
            max_yoy_magnitude_ratio=None,
            blocking_reasons=["candidate_spread_gt_100x"]
            if status == "baseline_not_validatable"
            else [],
            warning_reasons=[],
        ),
        evidence=[],
        confidence=confidence,
        validation_readiness=status in {"clean", "clean_with_warning"},
    )


def _gate_result(
    revenue_result: HistoricalSeriesIntegrityResult,
) -> HistoricalSeriesIntegrityGateResult:
    counts = {
        "clean": 0,
        "clean_with_warning": 0,
        "baseline_not_validatable": 0,
        "missing": 0,
    }
    metrics_by_status = {
        "clean": [],
        "clean_with_warning": [],
        "baseline_not_validatable": [],
        "missing": [],
    }
    counts[revenue_result.status] += 1
    metrics_by_status[revenue_result.status].append("revenue")
    return HistoricalSeriesIntegrityGateResult(
        metrics_evaluated=["revenue"],
        series_results=[revenue_result],
        overall_status=revenue_result.status,
        status_counts=counts,
        metrics_by_status=metrics_by_status,
        clean_metrics=metrics_by_status["clean"],
        warning_metrics=metrics_by_status["clean_with_warning"],
        blocked_metrics=metrics_by_status["baseline_not_validatable"],
        missing_metrics=metrics_by_status["missing"],
        critical_issue_count=len(revenue_result.blocking_issues),
        warning_count=len(revenue_result.warning_issues),
    )


def _execute(
    *,
    revenue_result: HistoricalSeriesIntegrityResult,
    forecast_value: float = 133.1,
    forecast_year: int = 2026,
):
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([RevenueGrowthValidationRule()])
    )
    context = ValidationContext(
        validation_id="fv_revenue_growth",
        company_name="Lucky Cement Limited",
        workbook_id="wb_lucky",
        workbook_fingerprint="fingerprint",
        historical_gate_result=_gate_result(revenue_result),
        forecast_inputs=(
            ForecastInput(
                metric="revenue",
                forecast_year=forecast_year,
                value=forecast_value,
                unit="PKR",
                source="Analyst forecast",
            ),
        ),
    )
    return framework.execute(ValidationEngineInput(context=context))


def _growth_evidence(output):
    return next(
        evidence
        for evidence in output.result.evidence
        if evidence.evidence_id == "revenue_growth_validation:revenue_growth"
    )


def test_revenue_growth_within_historical_range_passes() -> None:
    output = _execute(revenue_result=_series_result("clean"), forecast_value=133.1)
    execution = output.execution_results[0]

    assert execution.executed is True
    assert execution.admission.status == ValidationAdmissionStatus.ADMITTED
    assert execution.result.outcome == ValidationOutcome.PASS
    assert output.result.scorecard.overall_outcome == ValidationOutcome.PASS

    evidence = _growth_evidence(output)
    assert evidence.calculations["forecast_growth_rate"] == pytest.approx(0.1)
    assert evidence.calculations["average_growth_rate"] == pytest.approx(0.1)
    assert evidence.provenance["historical_growth_rates"][0]["from_year"] == 2023
    assert evidence.citations[0].page_number == 292


def test_revenue_growth_moderately_outside_range_warns() -> None:
    output = _execute(revenue_result=_series_result("clean"), forecast_value=144.0)
    execution = output.execution_results[0]

    assert execution.executed is True
    assert execution.result.outcome == ValidationOutcome.WARNING
    assert output.result.scorecard.overall_outcome == ValidationOutcome.WARNING
    assert output.result.scorecard.category_scores[0].score == 70.0
    assert execution.result.issues[0].is_blocking is False
    assert "moderately outside historical range" in execution.result.issues[0].title


def test_revenue_growth_materially_outside_range_fails() -> None:
    output = _execute(revenue_result=_series_result("clean"), forecast_value=181.5)
    execution = output.execution_results[0]

    assert execution.executed is True
    assert execution.result.outcome == ValidationOutcome.FAIL
    assert output.result.scorecard.overall_outcome == ValidationOutcome.FAIL
    assert execution.result.issues[0].is_blocking is True
    assert "materially outside historical range" in execution.result.issues[0].title


def test_revenue_growth_baseline_not_validatable_is_skipped() -> None:
    output = _execute(
        revenue_result=_series_result(
            "baseline_not_validatable",
            confidence=0.52,
        )
    )
    execution = output.execution_results[0]

    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_BASELINE_NOT_VALIDATABLE
    )
    assert execution.result.outcome == ValidationOutcome.SKIPPED
    assert output.result.scorecard.overall_outcome == ValidationOutcome.SKIPPED
    assert output.result.evidence[0].historical_baseline_status == (
        "baseline_not_validatable"
    )


def test_revenue_growth_insufficient_history_is_skipped() -> None:
    output = _execute(
        revenue_result=_series_result(
            "clean",
            values=((2025, 121.0),),
        )
    )
    execution = output.execution_results[0]

    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_INSUFFICIENT_HISTORY
    )
    assert execution.result.outcome == ValidationOutcome.SKIPPED
    assert output.result.scorecard.overall_outcome == ValidationOutcome.SKIPPED
    assert "Insufficient admitted history" in execution.result.warnings[0]
