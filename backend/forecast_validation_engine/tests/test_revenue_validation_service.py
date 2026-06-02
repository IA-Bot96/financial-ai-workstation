"""Tests for complete revenue category validation service."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    ForecastInput,
    ValidationContext,
    ValidationOutcome,
)
from forecast_validation_engine.services import RevenueValidationService  # noqa: E402
from shared.models.historical_series_integrity import (  # noqa: E402
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
    ScaleConsistencyResult,
    SeriesValueCandidateEvidence,
)

_BASELINE_VALUES = (
    (2021, 100.0),
    (2022, 108.0),
    (2023, 118.8),
    (2024, 131.868),
    (2025, 143.73612),
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
    values: tuple[tuple[int, float], ...] = _BASELINE_VALUES,
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


def _latest_value() -> float:
    return _BASELINE_VALUES[-1][1]


def _forecast_value(growth_rate: float) -> float:
    return _latest_value() * (1 + growth_rate)


def _context(
    *,
    revenue_result: HistoricalSeriesIntegrityResult,
    forecast_value: float,
) -> ValidationContext:
    return ValidationContext(
        validation_id="fv_revenue_category",
        company_name="Lucky Cement Limited",
        workbook_id="wb_lucky",
        workbook_fingerprint="fingerprint",
        historical_gate_result=_gate_result(revenue_result),
        forecast_inputs=(
            ForecastInput(
                metric="revenue",
                forecast_year=2026,
                value=forecast_value,
                unit="PKR",
                source="Analyst forecast",
            ),
        ),
    )


def _validate(
    *,
    forecast_value: float,
    revenue_result: HistoricalSeriesIntegrityResult | None = None,
):
    service = RevenueValidationService()
    return service.validate(
        _context(
            revenue_result=revenue_result or _series_result("clean"),
            forecast_value=forecast_value,
        )
    )


def test_revenue_validation_all_pass() -> None:
    result = _validate(forecast_value=_forecast_value(0.10))

    assert result.summary.outcome == ValidationOutcome.PASS
    assert result.summary.score == 100.0
    assert result.category_score.outcome == ValidationOutcome.PASS
    assert result.summary.rule_count == 3
    assert result.summary.executed_rule_count == 3
    assert result.summary.skipped_rule_count == 0
    assert {item.result.outcome for item in result.execution_results} == {
        ValidationOutcome.PASS
    }


def test_revenue_validation_warning_mix() -> None:
    result = _validate(forecast_value=_forecast_value(0.20))

    assert result.summary.outcome == ValidationOutcome.WARNING
    assert result.summary.score == 70.0
    assert result.category_score.outcome == ValidationOutcome.WARNING
    assert result.summary.issue_count >= 1
    assert result.summary.blocking_issue_count == 0
    assert ValidationOutcome.WARNING in {
        item.result.outcome for item in result.execution_results
    }


def test_revenue_validation_failure_mix() -> None:
    result = _validate(forecast_value=_forecast_value(0.50))

    assert result.summary.outcome == ValidationOutcome.FAIL
    assert result.summary.score == 0.0
    assert result.category_score.outcome == ValidationOutcome.FAIL
    assert result.summary.blocking_issue_count >= 1
    assert ValidationOutcome.FAIL in {
        item.result.outcome for item in result.execution_results
    }


def test_revenue_validation_skipped_baseline() -> None:
    result = _validate(
        revenue_result=_series_result(
            "baseline_not_validatable",
            confidence=0.52,
        ),
        forecast_value=_forecast_value(0.10),
    )

    assert result.summary.outcome == ValidationOutcome.SKIPPED
    assert result.summary.score is None
    assert result.category_score.outcome == ValidationOutcome.SKIPPED
    assert result.summary.executed_rule_count == 0
    assert result.summary.skipped_rule_count == 3
    assert all(not item.executed for item in result.execution_results)


def test_revenue_validation_aggregates_evidence_citations_and_provenance() -> None:
    result = _validate(forecast_value=_forecast_value(0.20))

    assert len(result.evidence) >= 3
    assert len(result.citations) >= 5
    assert "revenue_growth_validation" in result.provenance["rule_ids"]
    assert "revenue_trend_break_validation" in result.provenance["rule_ids"]
    assert "revenue_forecast_plausibility_validation" in (
        result.provenance["rule_ids"]
    )
    assert result.provenance["rule_outcomes"]["revenue_growth_validation"] in {
        "pass",
        "warning",
        "fail",
    }


def test_revenue_validation_confidence_uses_lowest_rule_confidence() -> None:
    result = _validate(
        revenue_result=_series_result("clean", confidence=0.81),
        forecast_value=_forecast_value(0.10),
    )

    assert result.summary.confidence.score == 0.81
    assert result.category_score.confidence.score == 0.81
    assert "revenue_growth_validation=0.8100" in result.summary.confidence.rationale
