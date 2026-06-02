"""Tests for forecast input validation rule."""

import sys
from pathlib import Path

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
from forecast_validation_engine.rules import ForecastInputValidationRule  # noqa: E402
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


def _candidate(metric: str, year: int = 2025) -> SeriesValueCandidateEvidence:
    return SeriesValueCandidateEvidence(
        metric=metric,
        value_year=year,
        value=52.53 if metric == "earnings_per_share" else 25_417_143,
        source_report_year=2025,
        page_number=292 if metric == "earnings_per_share" else 320,
        table_type="income_statement" if metric == "earnings_per_share" else "revenue_note",
        source_class="primary_statement"
        if metric == "earnings_per_share"
        else "note_disclosure",
        statement_scope="unknown",
        normalization_confidence=0.96,
        source_confidence=0.96,
        original_metric=metric.replace("_", " ").title(),
        requires_review=False,
        is_currently_selected=True,
    )


def _issue(metric: str, issue_type: str) -> HistoricalSeriesIntegrityIssue:
    return HistoricalSeriesIntegrityIssue(
        issue_type=issue_type,
        severity="critical",
        metric=metric,
        value_years=[2025],
        description=f"{metric} issue: {issue_type}",
        blocking=True,
        fixability="review_only",
        evidence_ids=[f"{metric}:{issue_type}"],
    )


def _series_result(
    metric: str,
    status: str,
    *,
    years: tuple[int, ...] = (2024, 2025),
    confidence: float = 0.95,
) -> HistoricalSeriesIntegrityResult:
    return HistoricalSeriesIntegrityResult(
        metric=metric,
        status=status,  # type: ignore[arg-type]
        value_years=list(years),
        selected_series=[_candidate(metric, year) for year in years]
        if status != "missing"
        else [],
        blocking_issues=(
            [_issue(metric, "candidate_spread_gt_100x")]
            if status == "baseline_not_validatable"
            else []
        ),
        warning_issues=[],
        candidate_spread_by_year=[],
        yoy_scale_issues=[],
        source_policy_violations=[],
        scale_result=ScaleConsistencyResult(
            status="fail" if status == "baseline_not_validatable" else "pass",
            max_candidate_spread=66_330_223.08
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
    *series_results: HistoricalSeriesIntegrityResult,
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
    for result in series_results:
        counts[result.status] += 1
        metrics_by_status[result.status].append(result.metric)
    return HistoricalSeriesIntegrityGateResult(
        metrics_evaluated=[result.metric for result in series_results],
        series_results=list(series_results),
        overall_status=(
            "baseline_not_validatable"
            if counts["baseline_not_validatable"]
            else "clean_with_warning"
            if counts["clean_with_warning"]
            else "missing"
            if counts["missing"]
            else "clean"
        ),
        status_counts=counts,
        metrics_by_status=metrics_by_status,
        clean_metrics=metrics_by_status["clean"],
        warning_metrics=metrics_by_status["clean_with_warning"],
        blocked_metrics=metrics_by_status["baseline_not_validatable"],
        missing_metrics=metrics_by_status["missing"],
        critical_issue_count=sum(len(result.blocking_issues) for result in series_results),
        warning_count=sum(len(result.warning_issues) for result in series_results),
    )


def _execute(
    forecast_inputs: tuple[ForecastInput, ...],
    *series_results: HistoricalSeriesIntegrityResult,
):
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([ForecastInputValidationRule()])
    )
    context = ValidationContext(
        validation_id="fv_forecast_input",
        company_name="Lucky Cement Limited",
        workbook_id="wb_lucky",
        workbook_fingerprint="fingerprint",
        historical_gate_result=_gate_result(*series_results),
        forecast_inputs=forecast_inputs,
    )
    return framework.execute(ValidationEngineInput(context=context))


def test_valid_forecast_input_passes() -> None:
    output = _execute(
        (
            ForecastInput(
                metric="earnings_per_share",
                forecast_year=2026,
                value=60.5,
                unit="PKR/share",
                source="Analyst forecast",
            ),
        ),
        _series_result("earnings_per_share", "clean", confidence=0.92),
    )

    execution = output.execution_results[0]
    assert execution.executed is True
    assert execution.admission.status == ValidationAdmissionStatus.ADMITTED
    assert execution.result.outcome == ValidationOutcome.PASS
    assert execution.result.confidence.score == 0.92
    assert output.result.scorecard.overall_outcome == ValidationOutcome.PASS
    assert output.result.evidence[0].provenance["forecast_year"] == 2026
    assert output.result.evidence[0].citations[0].page_number == 292


def test_missing_forecast_year_fails_structural_validation() -> None:
    output = _execute(
        (
            ForecastInput(
                metric="earnings_per_share",
                forecast_year=None,
                value=60.5,
            ),
        ),
        _series_result("earnings_per_share", "clean"),
    )

    execution = output.execution_results[0]
    assert execution.executed is True
    assert execution.result.outcome == ValidationOutcome.FAIL
    assert output.result.scorecard.overall_outcome == ValidationOutcome.FAIL
    assert "Forecast year is missing." in execution.result.errors


def test_missing_forecast_metric_fails_structural_validation() -> None:
    output = _execute(
        (
            ForecastInput(
                metric=None,
                forecast_year=2026,
                value=60.5,
            ),
        ),
        _series_result("earnings_per_share", "clean"),
    )

    execution = output.execution_results[0]
    assert execution.executed is True
    assert execution.result.outcome == ValidationOutcome.FAIL
    assert "Forecast metric is missing." in execution.result.errors


def test_baseline_not_validatable_is_skipped_by_admission() -> None:
    output = _execute(
        (
            ForecastInput(
                metric="revenue",
                forecast_year=2026,
                value=100_000,
            ),
        ),
        _series_result("revenue", "baseline_not_validatable", confidence=0.55),
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


def test_insufficient_history_warns_with_limitations() -> None:
    output = _execute(
        (
            ForecastInput(
                metric="earnings_per_share",
                forecast_year=2026,
                value=60.5,
            ),
        ),
        _series_result(
            "earnings_per_share",
            "clean",
            years=(2025,),
            confidence=0.95,
        ),
    )

    execution = output.execution_results[0]
    assert execution.executed is True
    assert execution.result.outcome == ValidationOutcome.WARNING
    assert execution.result.confidence.score == 0.8
    assert output.result.scorecard.overall_outcome == ValidationOutcome.WARNING
    assert "insufficient years" in execution.result.warnings[0]
