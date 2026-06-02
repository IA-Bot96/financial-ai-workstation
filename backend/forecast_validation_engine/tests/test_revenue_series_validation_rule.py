"""Tests for revenue historical series readiness validation."""

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
from forecast_validation_engine.rules import RevenueSeriesValidationRule  # noqa: E402
from forecast_validation_engine.services import (  # noqa: E402
    ForecastValidationFramework,
    ValidationRuleRegistry,
)
from shared.models.historical_series_integrity import (  # noqa: E402
    CandidateSpreadEvidence,
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
    ScaleConsistencyResult,
    SeriesValueCandidateEvidence,
)


def _candidate(year: int = 2025) -> SeriesValueCandidateEvidence:
    return SeriesValueCandidateEvidence(
        metric="revenue",
        value_year=year,
        value=25_417_143,
        source_report_year=2025,
        page_number=320,
        table_type="revenue_note",
        source_class="note_disclosure",
        statement_scope="unknown",
        normalization_confidence=1.0,
        source_confidence=1.0,
        original_metric="and liabilities is as follows: - Revenue",
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
        metric="revenue",
        value_years=[2025],
        description=f"Revenue issue: {issue_type}",
        blocking=blocking,
        fixability="review_only",
        evidence_ids=[f"revenue:{issue_type}"],
    )


def _spread() -> CandidateSpreadEvidence:
    return CandidateSpreadEvidence(
        metric="revenue",
        value_year=2025,
        candidate_count=3,
        candidate_spread=66_330_223.08,
        status="block",
        selected_candidate=_candidate(2025),
        sample_competing_candidates=[],
    )


def _revenue_gate_result(
    status: str,
    *,
    confidence: float = 0.95,
    selected_series: bool = True,
) -> HistoricalSeriesIntegrityResult:
    blocking_issues = (
        [
            _issue("candidate_spread_gt_100x", blocking=True),
            _issue("note_selected_over_primary_statement", blocking=True),
            _issue("yoy_scale_issue", blocking=True),
        ]
        if status == "baseline_not_validatable"
        else []
    )
    warning_issues = (
        [_issue("candidate_spread_gt_10x", blocking=False)]
        if status == "clean_with_warning"
        else []
    )
    source_policy_violations = (
        [_issue("note_selected_over_primary_statement", blocking=True)]
        if status == "baseline_not_validatable"
        else []
    )
    return HistoricalSeriesIntegrityResult(
        metric="revenue",
        status=status,  # type: ignore[arg-type]
        value_years=[2024, 2025] if selected_series else [],
        selected_series=[_candidate(2024), _candidate(2025)]
        if selected_series
        else [],
        blocking_issues=blocking_issues,
        warning_issues=warning_issues,
        candidate_spread_by_year=[_spread()]
        if status in {"baseline_not_validatable", "clean_with_warning"}
        else [],
        yoy_scale_issues=[],
        source_policy_violations=source_policy_violations,
        scale_result=ScaleConsistencyResult(
            status="fail"
            if status == "baseline_not_validatable"
            else "warning"
            if status == "clean_with_warning"
            else "pass",
            max_candidate_spread=66_330_223.08
            if status in {"baseline_not_validatable", "clean_with_warning"}
            else None,
            max_yoy_magnitude_ratio=1503207.59
            if status == "baseline_not_validatable"
            else None,
            blocking_reasons=["candidate_spread_gt_100x", "yoy_scale_issue"]
            if status == "baseline_not_validatable"
            else [],
            warning_reasons=["candidate_spread_warning"]
            if status == "clean_with_warning"
            else [],
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
    counts[revenue_result.status] += 1
    metrics_by_status = {
        "clean": [],
        "clean_with_warning": [],
        "baseline_not_validatable": [],
        "missing": [],
    }
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


def _context(revenue_status: str) -> ValidationContext:
    return ValidationContext(
        validation_id=f"fv_revenue_{revenue_status}",
        company_name="Lucky Cement Limited",
        workbook_id="wb_lucky",
        workbook_fingerprint="fingerprint",
        historical_gate_result=_gate_result(
            _revenue_gate_result(
                revenue_status,
                confidence=0.75
                if revenue_status == "clean_with_warning"
                else 0.55
                if revenue_status == "baseline_not_validatable"
                else 0.95,
                selected_series=revenue_status != "missing",
            )
        ),
    )


def _execute(revenue_status: str):
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([RevenueSeriesValidationRule()])
    )
    return framework.execute(ValidationEngineInput(context=_context(revenue_status)))


def test_revenue_clean_executes_and_passes() -> None:
    output = _execute("clean")
    execution = output.execution_results[0]

    assert execution.executed is True
    assert execution.admission.status == ValidationAdmissionStatus.ADMITTED
    assert execution.result.outcome == ValidationOutcome.PASS
    assert execution.result.confidence.score == 0.95
    assert output.result.scorecard.category_scores[0].outcome == ValidationOutcome.PASS
    assert output.result.evidence[0].provenance["gate_metric"] == "revenue"
    assert output.result.evidence[0].citations[0].page_number == 320


def test_revenue_clean_with_warning_executes_and_warns() -> None:
    output = _execute("clean_with_warning")
    execution = output.execution_results[0]

    assert execution.executed is True
    assert execution.admission.status == (
        ValidationAdmissionStatus.ADMITTED_WITH_WARNING
    )
    assert execution.result.outcome == ValidationOutcome.WARNING
    assert execution.result.confidence.score == 0.75
    assert output.result.scorecard.category_scores[0].outcome == (
        ValidationOutcome.WARNING
    )
    assert output.result.scorecard.category_scores[0].score == 70.0
    assert "Revenue issue" in execution.result.warnings[-1]


def test_revenue_baseline_not_validatable_is_skipped_with_gate_evidence() -> None:
    output = _execute("baseline_not_validatable")
    execution = output.execution_results[0]

    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_BASELINE_NOT_VALIDATABLE
    )
    assert execution.result.outcome == ValidationOutcome.SKIPPED
    assert output.result.scorecard.overall_outcome == ValidationOutcome.SKIPPED

    evidence = output.result.evidence[0]
    assert evidence.historical_baseline_status == "baseline_not_validatable"
    assert evidence.calculations["max_candidate_spread"] == 66_330_223.08
    assert evidence.provenance["candidate_spread_issues"][0]["status"] == "block"
    assert evidence.provenance["source_policy_issues"][0]["issue_type"] == (
        "note_selected_over_primary_statement"
    )
    assert evidence.provenance["scale_consistency"]["status"] == "fail"
    assert {
        issue["issue_type"]
        for issue in evidence.provenance["issue_references"]
    } >= {
        "candidate_spread_gt_100x",
        "note_selected_over_primary_statement",
        "yoy_scale_issue",
    }


def test_revenue_missing_is_skipped_with_missing_evidence() -> None:
    output = _execute("missing")
    execution = output.execution_results[0]

    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_REQUIRED_METRIC_MISSING
    )
    assert execution.result.outcome == ValidationOutcome.SKIPPED
    assert "Required metric is missing" in execution.result.warnings[0]

    evidence = output.result.evidence[0]
    assert evidence.historical_baseline_status == "missing"
    assert evidence.provenance["citation_type"] == "NONE"
