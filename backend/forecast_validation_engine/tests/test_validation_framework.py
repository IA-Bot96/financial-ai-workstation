"""Tests for Forecast Validation Engine Phase 2 framework."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    ValidationAdmissionStatus,
    ValidationCategory,
    ValidationConfidence,
    ValidationContext,
    ValidationEngineInput,
    ValidationEvidence,
    ValidationOutcome,
    ValidationRuleResult,
)
from forecast_validation_engine.services import (  # noqa: E402
    ConfidenceComposer,
    ForecastValidationFramework,
    ValidationAdmissionService,
    ValidationRule,
    ValidationRuleRegistry,
)
from shared.models.historical_series_integrity import (  # noqa: E402
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityResult,
    ScaleConsistencyResult,
)


class _PassingRule(ValidationRule):
    rule_id = "eps_standalone"
    category = ValidationCategory.HISTORICAL_BASELINE
    required_metrics = ("earnings_per_share",)
    minimum_history_years = 2

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        self.calls += 1
        return ValidationRuleResult(
            rule_id=self.rule_id,
            category=self.category,
            outcome=ValidationOutcome.PASS,
            confidence=ValidationConfidence(score=0.95),
            rule_confidence=0.95,
            evidence_confidence=0.7,
            evidence=(
                ValidationEvidence(
                    evidence_id="eps_rule_evidence",
                    category=self.category,
                    summary="EPS standalone baseline admitted.",
                    metrics=("earnings_per_share",),
                    historical_baseline_status="clean_with_warning",
                ),
            ),
        )


class _BlockedRevenueRule(ValidationRule):
    rule_id = "revenue_growth"
    category = ValidationCategory.REVENUE
    required_metrics = ("revenue",)

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        self.calls += 1
        raise AssertionError("Blocked rules must not execute.")


class _MissingDebtRule(ValidationRule):
    rule_id = "debt_check"
    category = ValidationCategory.DEBT
    required_metrics = ("total_debt",)

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        raise AssertionError("Missing metric rules must not execute.")


class _InsufficientHistoryRule(ValidationRule):
    rule_id = "eps_history"
    category = ValidationCategory.HISTORICAL_BASELINE
    required_metrics = ("earnings_per_share",)
    minimum_history_years = 3

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        raise AssertionError("Insufficient history rules must not execute.")


class _ForecastInputRule(ValidationRule):
    rule_id = "forecast_input"
    category = ValidationCategory.FORECAST_PLAUSIBILITY
    required_metrics = ("earnings_per_share",)
    requires_forecast_input = True

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        raise AssertionError("Invalid forecast input rules must not execute.")


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
        selected_series=[],
        blocking_issues=[],
        warning_issues=[],
        candidate_spread_by_year=[],
        yoy_scale_issues=[],
        source_policy_violations=[],
        scale_result=ScaleConsistencyResult(
            status="pass" if status in {"clean", "clean_with_warning"} else "fail",
            max_candidate_spread=None,
            max_yoy_magnitude_ratio=None,
            blocking_reasons=[],
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
            else "clean"
        ),
        status_counts=counts,
        metrics_by_status=metrics_by_status,
        clean_metrics=metrics_by_status["clean"],
        warning_metrics=metrics_by_status["clean_with_warning"],
        blocked_metrics=metrics_by_status["baseline_not_validatable"],
        missing_metrics=metrics_by_status["missing"],
        critical_issue_count=0,
        warning_count=0,
    )


def _context(
    gate_result: HistoricalSeriesIntegrityGateResult,
    *,
    forecast_input_valid: bool = True,
) -> ValidationContext:
    return ValidationContext(
        validation_id="fv_test",
        company_name="Lucky Cement Limited",
        workbook_id="wb_test",
        workbook_fingerprint="fingerprint",
        historical_gate_result=gate_result,
        forecast_input_valid=forecast_input_valid,
        forecast_input_errors=()
        if forecast_input_valid
        else ("Forecast value is missing.",),
    )


def test_clean_with_warning_metric_is_admitted_and_confidence_is_composed() -> None:
    rule = _PassingRule()
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([rule])
    )
    context = _context(
        _gate_result(
            _series_result(
                "earnings_per_share",
                "clean_with_warning",
                confidence=0.8,
            )
        )
    )

    output = framework.execute(ValidationEngineInput(context=context))

    execution = output.execution_results[0]
    assert execution.executed is True
    assert rule.calls == 1
    assert execution.admission.status == ValidationAdmissionStatus.ADMITTED_WITH_WARNING
    assert execution.result.confidence.score == 0.7
    assert output.result.scorecard.category_scores[0].outcome == ValidationOutcome.PASS


def test_baseline_not_validatable_rule_is_skipped_without_execution() -> None:
    rule = _BlockedRevenueRule()
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([rule])
    )
    context = _context(
        _gate_result(_series_result("revenue", "baseline_not_validatable"))
    )

    output = framework.execute(ValidationEngineInput(context=context))

    execution = output.execution_results[0]
    assert execution.executed is False
    assert rule.calls == 0
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_BASELINE_NOT_VALIDATABLE
    )
    assert execution.result.outcome == ValidationOutcome.SKIPPED
    assert output.result.scorecard.overall_outcome == ValidationOutcome.SKIPPED
    assert output.result.evidence[0].historical_baseline_status == (
        "baseline_not_validatable"
    )


def test_missing_required_metric_is_skipped() -> None:
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([_MissingDebtRule()])
    )
    context = _context(_gate_result(_series_result("total_debt", "missing")))

    output = framework.execute(ValidationEngineInput(context=context))

    execution = output.execution_results[0]
    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_REQUIRED_METRIC_MISSING
    )
    assert "Required metric is missing" in execution.result.warnings[0]


def test_insufficient_history_is_skipped() -> None:
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([_InsufficientHistoryRule()])
    )
    context = _context(
        _gate_result(
            _series_result(
                "earnings_per_share",
                "clean",
                years=(2025,),
            )
        )
    )

    output = framework.execute(ValidationEngineInput(context=context))

    execution = output.execution_results[0]
    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_INSUFFICIENT_HISTORY
    )


def test_invalid_forecast_input_is_skipped() -> None:
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([_ForecastInputRule()])
    )
    context = _context(
        _gate_result(_series_result("earnings_per_share", "clean")),
        forecast_input_valid=False,
    )

    output = framework.execute(ValidationEngineInput(context=context))

    execution = output.execution_results[0]
    assert execution.executed is False
    assert execution.admission.status == (
        ValidationAdmissionStatus.SKIPPED_FORECAST_INPUT_INVALID
    )
    assert "Forecast value is missing." in execution.result.warnings


def test_confidence_composer_uses_minimum_confidence() -> None:
    confidence = ConfidenceComposer.compose(
        rule_confidence=0.92,
        gate_confidence=0.81,
        evidence_confidence=0.64,
    )

    assert confidence.score == 0.64
    assert "rule_confidence=0.9200" in confidence.rationale


def test_registry_rejects_duplicate_rule_ids() -> None:
    registry = ValidationRuleRegistry([_PassingRule()])

    with pytest.raises(ValueError, match="Duplicate validation rule id"):
        registry.register(_PassingRule())


def test_requested_rule_subset_executes_only_selected_rules() -> None:
    eps_rule = _PassingRule()
    revenue_rule = _BlockedRevenueRule()
    framework = ForecastValidationFramework(
        registry=ValidationRuleRegistry([revenue_rule, eps_rule])
    )
    context = _context(
        _gate_result(
            _series_result("earnings_per_share", "clean"),
            _series_result("revenue", "baseline_not_validatable"),
        )
    )

    output = framework.execute(
        ValidationEngineInput(
            context=context,
            requested_rule_ids=("eps_standalone",),
        )
    )

    assert len(output.execution_results) == 1
    assert output.execution_results[0].rule_id == "eps_standalone"
    assert eps_rule.calls == 1
    assert revenue_rule.calls == 0
