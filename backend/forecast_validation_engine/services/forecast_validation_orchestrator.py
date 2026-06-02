"""MVP orchestration spine for Forecast Validation Engine."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from forecast_validation_engine.models.forecast_input import ForecastInput
from forecast_validation_engine.models.forecast_validation import (
    ValidationCategory,
    ValidationCategoryScore,
    ValidationCitation,
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
    ValidationSeverity,
)
from forecast_validation_engine.models.framework import (
    ValidationAdmissionResult,
    ValidationAdmissionStatus,
    ValidationContext,
    ValidationEngineInput,
    ValidationExecutionResult,
    ValidationRuleResult,
)
from forecast_validation_engine.models.orchestration import (
    ForecastValidationRunResult,
    ForecastValidationRunScorecard,
)
from forecast_validation_engine.services.validation_framework import (
    ForecastValidationFramework,
    ValidationRuleRegistry,
)
from shared.models.financial_year_consolidation import FinancialYearConsolidationResult
from shared.models.historical_series_integrity import HistoricalSeriesIntegrityGateResult
from shared.services.historical_series_integrity_gate import HistoricalSeriesIntegrityGate

HISTORICAL_BASELINE_READINESS_CATEGORY: Final[str] = (
    "HistoricalBaselineReadinessCategory"
)
EPS_BASELINE_CATEGORY: Final[str] = "EPSBaselineCategory"
FORECAST_INPUT_CATEGORY: Final[str] = "ForecastInputCategory"
DEFERRED_CATEGORIES: Final[tuple[str, ...]] = (
    "RevenueValidationService",
    "Profitability",
    "Cash Flow",
    "Debt",
    "Balance Sheet",
)


class ForecastValidationOrchestrator:
    """Coordinate MVP gate execution, category admission, and run assembly."""

    def __init__(
        self,
        *,
        integrity_gate: HistoricalSeriesIntegrityGate | None = None,
    ) -> None:
        """Initialize orchestrator with the historical-series integrity gate."""

        self._integrity_gate = integrity_gate or HistoricalSeriesIntegrityGate()

    def run(
        self,
        *,
        consolidation_result: FinancialYearConsolidationResult,
        forecast_inputs: Iterable[ForecastInput] = (),
        validation_id: str = "forecast_validation_run",
        company_name: str | None = None,
        workbook_id: str | None = None,
        workbook_fingerprint: str | None = None,
        bundle_fingerprint: str | None = None,
        metrics: Iterable[str] | None = None,
    ) -> ForecastValidationRunResult:
        """Execute MVP Forecast Validation orchestration."""

        forecast_input_tuple = tuple(forecast_inputs)
        resolved_bundle_fingerprint = bundle_fingerprint or workbook_fingerprint
        gate_version = getattr(self._integrity_gate, "gate_version", "unknown")
        gate_result = self._integrity_gate.evaluate(
            consolidation_result,
            metrics=metrics,
        )
        coverage = _coverage_metrics(gate_result)
        context = ValidationContext(
            validation_id=validation_id,
            company_name=company_name,
            workbook_id=workbook_id,
            workbook_fingerprint=workbook_fingerprint,
            historical_gate_result=gate_result,
            forecast_inputs=forecast_input_tuple,
        )

        category_outcomes: dict[str, ValidationOutcome] = {}
        category_scores_by_name: dict[str, float | None] = {}
        category_confidence_by_name: dict[str, float] = {}
        category_score_rows: list[ValidationCategoryScore] = []
        execution_results: list[ValidationExecutionResult] = []
        evidence: list[ValidationEvidence] = []
        issues: list[ValidationIssue] = []
        warnings: list[str] = []
        executed_categories: list[str] = []
        skipped_categories: list[str] = []

        readiness_result = _historical_readiness_category(gate_result)
        _record_category(
            category_name=HISTORICAL_BASELINE_READINESS_CATEGORY,
            category_result=readiness_result,
            category_outcomes=category_outcomes,
            category_scores_by_name=category_scores_by_name,
            category_confidence_by_name=category_confidence_by_name,
            category_score_rows=category_score_rows,
            evidence=evidence,
            issues=issues,
            warnings=warnings,
            executed_categories=executed_categories,
            skipped_categories=skipped_categories,
        )

        eps_output = _eps_framework().execute(ValidationEngineInput(context=context))
        eps_category = _category_from_execution_results(
            category_name=EPS_BASELINE_CATEGORY,
            category=ValidationCategory.HISTORICAL_BASELINE,
            execution_results=eps_output.execution_results,
        )
        execution_results.extend(eps_output.execution_results)
        _record_category(
            category_name=EPS_BASELINE_CATEGORY,
            category_result=eps_category,
            category_outcomes=category_outcomes,
            category_scores_by_name=category_scores_by_name,
            category_confidence_by_name=category_confidence_by_name,
            category_score_rows=category_score_rows,
            evidence=evidence,
            issues=issues,
            warnings=warnings,
            executed_categories=executed_categories,
            skipped_categories=skipped_categories,
        )

        if forecast_input_tuple:
            forecast_input_output = _forecast_input_framework().execute(
                ValidationEngineInput(context=context)
            )
            forecast_input_category = _category_from_execution_results(
                category_name=FORECAST_INPUT_CATEGORY,
                category=ValidationCategory.DATA_QUALITY,
                execution_results=forecast_input_output.execution_results,
            )
            execution_results.extend(forecast_input_output.execution_results)
        else:
            forecast_input_category = _forecast_input_skipped_category()
        _record_category(
            category_name=FORECAST_INPUT_CATEGORY,
            category_result=forecast_input_category,
            category_outcomes=category_outcomes,
            category_scores_by_name=category_scores_by_name,
            category_confidence_by_name=category_confidence_by_name,
            category_score_rows=category_score_rows,
            evidence=evidence,
            issues=issues,
            warnings=warnings,
            executed_categories=executed_categories,
            skipped_categories=skipped_categories,
        )

        deferred_evidence = _deferred_category_evidence()
        evidence.append(deferred_evidence)
        for category_name in DEFERRED_CATEGORIES:
            category_outcomes[category_name] = ValidationOutcome.SKIPPED
            category_scores_by_name[category_name] = None
            category_confidence_by_name[category_name] = 1.0
            skipped_categories.append(category_name)
            category_score_rows.append(
                ValidationCategoryScore(
                    category=_deferred_validation_category(category_name),
                    outcome=ValidationOutcome.SKIPPED,
                    score=None,
                    issue_count=0,
                    blocking_issue_count=0,
                    confidence=ValidationConfidence(
                        score=1.0,
                        rationale=(
                            "Category is deferred by Forecast Validation MVP scope.",
                        ),
                    ),
                )
            )

        deduped_evidence = _dedupe_evidence(evidence)
        deduped_citations = _dedupe_citations(
            citation
            for evidence_item in deduped_evidence
            for citation in evidence_item.citations
        )
        scorecard = _run_scorecard(
            category_scores=tuple(category_score_rows),
            category_outcomes=category_outcomes,
            category_scores_by_name=category_scores_by_name,
            category_confidence_by_name=category_confidence_by_name,
            executed_categories=tuple(dict.fromkeys(executed_categories)),
            skipped_categories=tuple(dict.fromkeys(skipped_categories)),
            deferred_categories=DEFERRED_CATEGORIES,
            coverage=coverage,
            bundle_fingerprint=resolved_bundle_fingerprint,
            gate_version=gate_version,
            issues=tuple(issues),
            warnings=tuple(warnings),
        )

        return ForecastValidationRunResult(
            validation_id=validation_id,
            company_name=company_name,
            workbook_id=workbook_id,
            workbook_fingerprint=workbook_fingerprint,
            bundle_fingerprint=resolved_bundle_fingerprint,
            gate_version=gate_version,
            historical_gate_result=gate_result,
            scorecard=scorecard,
            execution_results=tuple(execution_results),
            issues=tuple(issues),
            evidence=deduped_evidence,
            citations=deduped_citations,
            provenance={
                "source": "ForecastValidationOrchestrator",
                "gate_executed": True,
                "gate_version": gate_version,
                "bundle_fingerprint": resolved_bundle_fingerprint,
                "coverage": coverage,
                "executable_categories": (
                    HISTORICAL_BASELINE_READINESS_CATEGORY,
                    EPS_BASELINE_CATEGORY,
                    FORECAST_INPUT_CATEGORY,
                ),
                "deferred_categories": DEFERRED_CATEGORIES,
                "deferred_reason": "Deferred by Forecast Validation MVP rescoping.",
                "category_outcomes": {
                    name: outcome.value for name, outcome in category_outcomes.items()
                },
            },
        )


class _CategoryResult:
    """Internal normalized category aggregation result."""

    def __init__(
        self,
        *,
        outcome: ValidationOutcome,
        score: float | None,
        confidence: ValidationConfidence,
        validation_category: ValidationCategory,
        evidence: tuple[ValidationEvidence, ...] = (),
        issues: tuple[ValidationIssue, ...] = (),
        warnings: tuple[str, ...] = (),
        executed: bool,
    ) -> None:
        self.outcome = outcome
        self.score = score
        self.confidence = confidence
        self.validation_category = validation_category
        self.evidence = evidence
        self.issues = issues
        self.warnings = warnings
        self.executed = executed


def _eps_framework() -> ForecastValidationFramework:
    from forecast_validation_engine.rules.eps_baseline_validation_rule import (
        EPSBaselineValidationRule,
    )

    return ForecastValidationFramework(
        registry=ValidationRuleRegistry([EPSBaselineValidationRule()])
    )


def _forecast_input_framework() -> ForecastValidationFramework:
    from forecast_validation_engine.rules.forecast_input_validation_rule import (
        ForecastInputValidationRule,
    )

    return ForecastValidationFramework(
        registry=ValidationRuleRegistry([ForecastInputValidationRule()])
    )


def _historical_readiness_category(
    gate_result: HistoricalSeriesIntegrityGateResult,
) -> _CategoryResult:
    clean_count = gate_result.status_counts.get("clean", 0)
    warning_count = gate_result.status_counts.get("clean_with_warning", 0)
    blocked_count = gate_result.status_counts.get("baseline_not_validatable", 0)
    missing_count = gate_result.status_counts.get("missing", 0)
    ready_count = clean_count + warning_count
    evaluated_count = clean_count + warning_count + blocked_count + missing_count
    coverage_percentage = (
        ready_count / evaluated_count * 100.0 if evaluated_count else 0.0
    )

    if ready_count == 0:
        outcome = ValidationOutcome.SKIPPED
        summary = "No historical baselines are admitted for Forecast Validation."
        score = None
        confidence_score = 1.0
        issue = _category_issue(
            issue_id="historical_baseline_readiness:no_admitted_baselines",
            title="No historical baselines admitted",
            description=summary,
            outcome=ValidationOutcome.SKIPPED,
            severity=ValidationSeverity.HIGH,
            blocking=True,
            evidence_id="historical_baseline_readiness:summary",
        )
        issues = (issue,)
        warnings = (summary,)
        executed = False
    elif blocked_count or missing_count or warning_count:
        outcome = ValidationOutcome.WARNING
        summary = "Historical baseline gate completed with limitations."
        score = 70.0
        confidence_score = min(
            (result.confidence for result in gate_result.series_results),
            default=1.0,
        )
        issues = ()
        warnings = (
            "Some historical baseline metrics are warning, blocked, or missing.",
        )
        executed = True
    else:
        outcome = ValidationOutcome.PASS
        summary = "Historical baseline gate completed with all metrics clean."
        score = 100.0
        confidence_score = min(
            (result.confidence for result in gate_result.series_results),
            default=1.0,
        )
        issues = ()
        warnings = ()
        executed = True

    evidence = ValidationEvidence(
        evidence_id="historical_baseline_readiness:summary",
        category=ValidationCategory.HISTORICAL_BASELINE,
        summary=summary,
        metrics=tuple(gate_result.metrics_evaluated),
        historical_baseline_status=gate_result.overall_status,
        calculations={
            "clean_count": clean_count,
            "clean_with_warning_count": warning_count,
            "blocked_count": blocked_count,
            "missing_count": missing_count,
            "metrics_admitted": ready_count,
            "metrics_evaluated": evaluated_count,
            "coverage_percentage": coverage_percentage,
            "critical_issue_count": gate_result.critical_issue_count,
            "warning_count": gate_result.warning_count,
        },
        provenance={
            "source": "HistoricalSeriesIntegrityGate",
            "category_name": HISTORICAL_BASELINE_READINESS_CATEGORY,
            "metrics_by_status": gate_result.metrics_by_status,
        },
    )
    return _CategoryResult(
        outcome=outcome,
        score=score,
        confidence=ValidationConfidence(
            score=confidence_score,
            rationale=("Historical baseline readiness summarized from gate result.",),
            limitations=warnings,
        ),
        validation_category=ValidationCategory.HISTORICAL_BASELINE,
        evidence=(evidence,),
        issues=issues,
        warnings=warnings,
        executed=executed,
    )


def _forecast_input_skipped_category() -> _CategoryResult:
    evidence = ValidationEvidence(
        evidence_id="forecast_input_category:skipped:no_inputs",
        category=ValidationCategory.DATA_QUALITY,
        summary="Forecast input category skipped because no forecast inputs were supplied.",
        provenance={
            "source": "ForecastValidationOrchestrator",
            "category_name": FORECAST_INPUT_CATEGORY,
            "skip_reason": "no_forecast_inputs_supplied",
        },
    )
    return _CategoryResult(
        outcome=ValidationOutcome.SKIPPED,
        score=None,
        confidence=ValidationConfidence(
            score=1.0,
            rationale=("Forecast input category skipped before rule execution.",),
        ),
        validation_category=ValidationCategory.DATA_QUALITY,
        evidence=(evidence,),
        warnings=("Forecast input category skipped because no inputs were supplied.",),
        executed=False,
    )


def _category_from_execution_results(
    *,
    category_name: str,
    category: ValidationCategory,
    execution_results: tuple[ValidationExecutionResult, ...],
) -> _CategoryResult:
    outcomes = tuple(result.result.outcome for result in execution_results)
    outcome = _aggregate_outcome(outcomes)
    evidence = _dedupe_evidence(
        evidence_item
        for execution_result in execution_results
        for evidence_item in execution_result.result.evidence
    )
    issues = tuple(
        issue
        for execution_result in execution_results
        for issue in execution_result.result.issues
    )
    warnings = tuple(
        warning
        for execution_result in execution_results
        for warning in execution_result.result.warnings
    )
    confidence = ValidationConfidence(
        score=min(
            (result.result.confidence.score for result in execution_results),
            default=1.0,
        ),
        rationale=(
            f"{category_name} confidence is the minimum rule result confidence.",
            *(
                f"{result.rule_id}={result.result.confidence.score:.4f}"
                for result in execution_results
            ),
        ),
        limitations=warnings,
    )
    return _CategoryResult(
        outcome=outcome,
        score=_score_for_outcome(outcome),
        confidence=confidence,
        validation_category=category,
        evidence=evidence,
        issues=issues,
        warnings=warnings,
        executed=any(result.executed for result in execution_results),
    )


def _record_category(
    *,
    category_name: str,
    category_result: _CategoryResult,
    category_outcomes: dict[str, ValidationOutcome],
    category_scores_by_name: dict[str, float | None],
    category_confidence_by_name: dict[str, float],
    category_score_rows: list[ValidationCategoryScore],
    evidence: list[ValidationEvidence],
    issues: list[ValidationIssue],
    warnings: list[str],
    executed_categories: list[str],
    skipped_categories: list[str],
) -> None:
    category_outcomes[category_name] = category_result.outcome
    category_scores_by_name[category_name] = category_result.score
    category_confidence_by_name[category_name] = category_result.confidence.score
    if category_result.executed:
        executed_categories.append(category_name)
    if category_result.outcome == ValidationOutcome.SKIPPED:
        skipped_categories.append(category_name)
    category_score_rows.append(
        ValidationCategoryScore(
            category=category_result.validation_category,
            outcome=category_result.outcome,
            score=category_result.score,
            issue_count=len(category_result.issues),
            blocking_issue_count=sum(
                1 for issue in category_result.issues if issue.is_blocking
            ),
            confidence=category_result.confidence,
        )
    )
    evidence.extend(category_result.evidence)
    issues.extend(category_result.issues)
    warnings.extend(category_result.warnings)


def _run_scorecard(
    *,
    category_scores: tuple[ValidationCategoryScore, ...],
    category_outcomes: dict[str, ValidationOutcome],
    category_scores_by_name: dict[str, float | None],
    category_confidence_by_name: dict[str, float],
    executed_categories: tuple[str, ...],
    skipped_categories: tuple[str, ...],
    deferred_categories: tuple[str, ...],
    coverage: dict[str, float | int],
    bundle_fingerprint: str | None,
    gate_version: str,
    issues: tuple[ValidationIssue, ...],
    warnings: tuple[str, ...],
) -> ForecastValidationRunScorecard:
    active_outcomes = tuple(
        outcome
        for category_name, outcome in category_outcomes.items()
        if category_name not in deferred_categories
    )
    overall_outcome = _aggregate_outcome(active_outcomes)
    numeric_scores = [
        score
        for category_name, score in category_scores_by_name.items()
        if category_name not in deferred_categories and score is not None
    ]
    confidence_scores = [
        confidence
        for category_name, confidence in category_confidence_by_name.items()
        if category_name not in deferred_categories
    ]
    blocking_issue_count = sum(1 for issue in issues if issue.is_blocking)
    coverage_warning = _coverage_warning(coverage)
    scorecard_warnings = (*warnings, coverage_warning) if coverage_warning else warnings
    return ForecastValidationRunScorecard(
        overall_outcome=overall_outcome,
        overall_score=(
            sum(numeric_scores) / len(numeric_scores)
            if numeric_scores
            else None
        ),
        metrics_admitted=int(coverage["metrics_admitted"]),
        metrics_blocked=int(coverage["metrics_blocked"]),
        metrics_missing=int(coverage["metrics_missing"]),
        coverage_percentage=float(coverage["coverage_percentage"]),
        bundle_fingerprint=bundle_fingerprint,
        gate_version=gate_version,
        category_scores=category_scores,
        category_outcomes=category_outcomes,
        category_scores_by_name=category_scores_by_name,
        category_confidence_by_name=category_confidence_by_name,
        executed_categories=executed_categories,
        skipped_categories=skipped_categories,
        deferred_categories=deferred_categories,
        confidence=ValidationConfidence(
            score=min(confidence_scores) if confidence_scores else 1.0,
            rationale=("Run confidence is the minimum active category confidence.",),
            limitations=scorecard_warnings,
        ),
        issue_count=len(issues),
        blocking_issue_count=blocking_issue_count,
        warnings=scorecard_warnings,
    )


def _coverage_metrics(
    gate_result: HistoricalSeriesIntegrityGateResult,
) -> dict[str, float | int]:
    admitted = (
        gate_result.status_counts.get("clean", 0)
        + gate_result.status_counts.get("clean_with_warning", 0)
    )
    blocked = gate_result.status_counts.get("baseline_not_validatable", 0)
    missing = gate_result.status_counts.get("missing", 0)
    evaluated = admitted + blocked + missing
    return {
        "metrics_admitted": admitted,
        "metrics_blocked": blocked,
        "metrics_missing": missing,
        "metrics_evaluated": evaluated,
        "coverage_percentage": (admitted / evaluated * 100.0) if evaluated else 0.0,
    }


def _coverage_warning(coverage: dict[str, float | int]) -> str | None:
    admitted = int(coverage["metrics_admitted"])
    evaluated = int(coverage["metrics_evaluated"])
    if evaluated == 0:
        return "Coverage context: no historical metrics were evaluated."
    if admitted < evaluated:
        return (
            "Coverage context: "
            f"{admitted} of {evaluated} historical metrics are admitted; "
            "scorecard score is not a baseline-health percentage."
        )
    return None


def _aggregate_outcome(outcomes: tuple[ValidationOutcome, ...]) -> ValidationOutcome:
    if not outcomes:
        return ValidationOutcome.SKIPPED
    if ValidationOutcome.FAIL in outcomes:
        return ValidationOutcome.FAIL
    if ValidationOutcome.WARNING in outcomes:
        return ValidationOutcome.WARNING
    if ValidationOutcome.PASS in outcomes:
        return ValidationOutcome.PASS
    return ValidationOutcome.SKIPPED


def _score_for_outcome(outcome: ValidationOutcome) -> float | None:
    if outcome == ValidationOutcome.PASS:
        return 100.0
    if outcome == ValidationOutcome.WARNING:
        return 70.0
    if outcome == ValidationOutcome.FAIL:
        return 0.0
    return None


def _category_issue(
    *,
    issue_id: str,
    title: str,
    description: str,
    outcome: ValidationOutcome,
    severity: ValidationSeverity,
    blocking: bool,
    evidence_id: str,
) -> ValidationIssue:
    return ValidationIssue(
        issue_id=issue_id,
        category=ValidationCategory.HISTORICAL_BASELINE,
        severity=severity,
        outcome=outcome,
        title=title,
        description=description,
        evidence_ids=(evidence_id,),
        is_blocking=blocking,
        confidence=ValidationConfidence(score=1.0),
    )


def _deferred_category_evidence() -> ValidationEvidence:
    return ValidationEvidence(
        evidence_id="forecast_validation_orchestrator:deferred_categories",
        category=ValidationCategory.DATA_QUALITY,
        summary="Deferred Forecast Validation MVP categories were not executed.",
        provenance={
            "source": "ForecastValidationOrchestrator",
            "deferred_categories": DEFERRED_CATEGORIES,
            "reason": "Deferred by Forecast Validation MVP rescoping.",
        },
    )


def _deferred_validation_category(category_name: str) -> ValidationCategory:
    if category_name == "RevenueValidationService":
        return ValidationCategory.REVENUE
    if category_name == "Profitability":
        return ValidationCategory.PROFITABILITY
    if category_name == "Cash Flow":
        return ValidationCategory.CASH_FLOW
    if category_name == "Debt":
        return ValidationCategory.DEBT
    if category_name == "Balance Sheet":
        return ValidationCategory.BALANCE_SHEET
    return ValidationCategory.DATA_QUALITY


def _dedupe_evidence(
    evidence_items: Iterable[ValidationEvidence],
) -> tuple[ValidationEvidence, ...]:
    evidence_by_id: dict[str, ValidationEvidence] = {}
    for evidence_item in evidence_items:
        evidence_by_id.setdefault(evidence_item.evidence_id, evidence_item)
    return tuple(evidence_by_id[evidence_id] for evidence_id in sorted(evidence_by_id))


def _dedupe_citations(
    citations: Iterable[ValidationCitation],
) -> tuple[ValidationCitation, ...]:
    citation_by_id: dict[str, ValidationCitation] = {}
    for citation in citations:
        citation_by_id.setdefault(citation.citation_id, citation)
    return tuple(citation_by_id[citation_id] for citation_id in sorted(citation_by_id))


__all__ = ["ForecastValidationOrchestrator"]
