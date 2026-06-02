"""Tests for EPS baseline validation rule."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    ValidationAdmissionStatus,
    ValidationContext,
    ValidationEngineInput,
    ValidationOutcome,
)
from forecast_validation_engine.rules import EPSBaselineValidationRule  # noqa: E402
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


def _candidate(year: int = 2025) -> SeriesValueCandidateEvidence:
    return SeriesValueCandidateEvidence(
        metric="earnings_per_share",
        value_year=year,
        value=52.53,
        source_report_year=2025,
        page_number=292,
        table_type="income_statement",
        source_class="primary_statement",
        statement_scope="unknown",
        normalization_confidence=0.96,
        source_confidence=0.96,
        original_metric="Earnings per share - basic and diluted",
        requires_review=False,
        is_currently_selected=True,
    )


def _issue(
    issue_type: str,
    *,
    blocking: bool,
) -> HistoricalSeriesIntegrityIssue:
    return HistoricalSeriesIntegrityIssue(
        issue_type=issue_type,
        severity="critical" if blocking else "warning",
        metric="earnings_per_share",
        value_years=[2025],
        description=f"EPS issue: {issue_type}",
        blocking=blocking,
        fixability="review_only",
        evidence_ids=[f"eps:{issue_type}"],
    )


def _eps_gate_result(
    status: str,
    *,
    confidence: float = 0.95,
    selected_series: bool = True,
) -> HistoricalSeriesIntegrityResult:
    return HistoricalSeriesIntegrityResult(
        metric="earnings_per_share",
        status=status,  # type: ignore[arg-type]
        value_years=[2024, 2025] if selected_series else [],
        selected_series=[_candidate(2024), _candidate(2025)]
        if selected_series
        else [],
        blocking_issues=(
            [_issue("candidate_spread_gt_100x", blocking=True)]
            if status == "baseline_not_validatable"
            else []
        ),
        warning_issues=(
            [
                _issue(
                    "candidate_spread_gt_100x_rejected_eps_candidates",
                    blocking=False,
                )
            ]
            if status == "clean_with_warning"
            else []
        ),
        candidate_spread_by_year=[],
        yoy_scale_issues=[],
        source_policy_violations=[],
        scale_result=ScaleConsistencyResult(
            status="warning" if status == "clean_with_warning" else "pass",
            max_candidate_spread=5057471.26
            if status == "clean_with_warning"
            else None,
            max_yoy_magnitude_ratio=5.19
            if status == "clean_with_warning"
            else None,
            blocking_reasons=[],
            warning_reasons=["candidate_spread_warning"]
            if status == "clean_with_warning"
            else [],
        ),
        evidence=[],
        confidence=confidence,
        validation_readiness=status in {"clean", "clean_with_warning"},
    )


def _gate_result(
    eps_result: HistoricalSeriesIntegrityResult,
) -> HistoricalSeriesIntegrityGateResult:
    counts = {
        "clean": 0,
        "clean_with_warning": 0,
        "baseline_not_validatable": 0,
        "missing": 0,
    }
    counts[eps_result.status] += 1
    metrics_by_status = {
        "clean": [],
        "clean_with_warning": [],
        "baseline_not_validatable": [],
        "missing": [],
    }
    metrics_by_status[eps_result.status].append("earnings_per_share")
    return HistoricalSeriesIntegrityGateResult(
        metrics_evaluated=["earnings_per_share"],
        series_results=[eps_result],
        overall_status=eps_result.status,
        status_counts=counts,
        metrics_by_status=metrics_by_status,
        clean_metrics=metrics_by_status["clean"],
        warning_metrics=metrics_by_status["clean_with_warning"],
        blocked_metrics=metrics_by_status["baseline_not_validatable"],
        missing_metrics=metrics_by_status["missing"],
        critical_issue_count=len(eps_result.blocking_issues),
        warning_count=len(eps_result.warning_issues),
    )


def _context(eps_status: str) -> ValidationContext:
    return ValidationContext(
        validation_id=f"fv_eps_{eps_status}",
        company_name="Lucky Cement Limited",
        workbook_id="wb_lucky",
        workbook_fingerprint="fingerprint",
        historical_gate_result=_gate_result(
            _eps_gate_result(
                eps_status,
                confidence=0.8 if eps_status == "clean_with_warning" else 0.95,
                selected_series=eps_status != "missing",
            )
        ),
    )


def _execute(eps_status: str):
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([EPSBaselineValidationRule()])
    )
    return framework.execute(ValidationEngineInput(context=_context(eps_status)))


def test_eps_clean_executes_and_passes() -> None:
    output = _execute("clean")
    execution = output.execution_results[0]

    assert execution.executed is True
    assert execution.admission.status == ValidationAdmissionStatus.ADMITTED
    assert execution.result.outcome == ValidationOutcome.PASS
    assert execution.result.confidence.score == 0.95
    assert output.result.scorecard.category_scores[0].outcome == ValidationOutcome.PASS
    assert output.result.evidence[0].provenance["citation_type"] == "PDF_PROVENANCE"
    assert output.result.evidence[0].citations[0].page_number == 292


def test_eps_clean_with_warning_executes_and_warns() -> None:
    output = _execute("clean_with_warning")
    execution = output.execution_results[0]

    assert execution.executed is True
    assert execution.admission.status == (
        ValidationAdmissionStatus.ADMITTED_WITH_WARNING
    )
    assert execution.result.outcome == ValidationOutcome.WARNING
    assert execution.result.confidence.score == 0.8
    assert output.result.scorecard.category_scores[0].outcome == (
        ValidationOutcome.WARNING
    )
    assert output.result.scorecard.category_scores[0].score == 70.0
    assert "EPS issue" in execution.result.warnings[-1]


def test_eps_baseline_not_validatable_is_skipped_by_admission() -> None:
    output = _execute("baseline_not_validatable")
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


def test_eps_missing_is_skipped_by_admission() -> None:
    output = _execute("missing")
    execution = output.execution_results[0]

    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_REQUIRED_METRIC_MISSING
    )
    assert execution.result.outcome == ValidationOutcome.SKIPPED
    assert "Required metric is missing" in execution.result.warnings[0]
