"""Execution framework for Forecast Validation Engine rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterable
from typing import Final

from forecast_validation_engine.models.forecast_validation import (
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
from forecast_validation_engine.models.framework import (
    ValidationAdmissionResult,
    ValidationAdmissionStatus,
    ValidationContext,
    ValidationEngineInput,
    ValidationEngineOutput,
    ValidationExecutionResult,
    ValidationRuleResult,
)
from shared.models.historical_series_integrity import HistoricalSeriesIntegrityResult

_ADMITTED_STATUSES: Final[set[ValidationAdmissionStatus]] = {
    ValidationAdmissionStatus.ADMITTED,
    ValidationAdmissionStatus.ADMITTED_WITH_WARNING,
}


class ValidationRule(ABC):
    """Base contract for deterministic Forecast Validation rules."""

    rule_id: str
    category: ValidationCategory
    required_metrics: tuple[str, ...] = ()
    minimum_history_years: int = 0
    requires_forecast_input: bool = False

    @abstractmethod
    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        """Evaluate the rule after admission succeeds."""

    def required_metrics_for_context(
        self,
        context: ValidationContext,
    ) -> tuple[str, ...]:
        """Return required metrics for this rule in the current context."""

        return self.required_metrics


class ValidationRuleRegistry:
    """Registry of validation rules available to the framework."""

    def __init__(self, rules: Iterable[ValidationRule] | None = None) -> None:
        """Initialize registry with optional rules."""

        self._rules: dict[str, ValidationRule] = {}
        for rule in rules or ():
            self.register(rule)

    def register(self, rule: ValidationRule) -> None:
        """Register one validation rule."""

        if not rule.rule_id:
            raise ValueError("Validation rule id cannot be empty.")
        if rule.rule_id in self._rules:
            raise ValueError(f"Duplicate validation rule id: {rule.rule_id}")
        self._rules[rule.rule_id] = rule

    def get(self, rule_id: str) -> ValidationRule:
        """Return a registered validation rule."""

        try:
            return self._rules[rule_id]
        except KeyError as exc:
            raise KeyError(f"Validation rule is not registered: {rule_id}") from exc

    def list_rules(self) -> tuple[ValidationRule, ...]:
        """Return registered rules in deterministic order."""

        return tuple(self._rules[rule_id] for rule_id in sorted(self._rules))

    def select_rules(self, requested_rule_ids: tuple[str, ...]) -> tuple[ValidationRule, ...]:
        """Return all rules or a deterministic requested subset."""

        if not requested_rule_ids:
            return self.list_rules()
        return tuple(self.get(rule_id) for rule_id in requested_rule_ids)


class ConfidenceComposer:
    """Compose gate, rule, and evidence confidence deterministically."""

    @staticmethod
    def compose(
        *,
        rule_confidence: float,
        gate_confidence: float,
        evidence_confidence: float,
        rationale: Iterable[str] = (),
        limitations: Iterable[str] = (),
    ) -> ValidationConfidence:
        """Return min(rule_confidence, gate_confidence, evidence_confidence)."""

        score = min(rule_confidence, gate_confidence, evidence_confidence)
        return ValidationConfidence(
            score=score,
            rationale=tuple(
                [
                    f"rule_confidence={rule_confidence:.4f}",
                    f"gate_confidence={gate_confidence:.4f}",
                    f"evidence_confidence={evidence_confidence:.4f}",
                    *rationale,
                ]
            ),
            limitations=tuple(limitations),
        )


class ValidationAdmissionService:
    """Apply gate-first admission rules before any validation rule executes."""

    def admit(
        self,
        *,
        rule: ValidationRule,
        context: ValidationContext,
    ) -> ValidationAdmissionResult:
        """Return whether the rule can execute for the current context."""

        required_metrics = rule.required_metrics_for_context(context)
        gate_results = {
            result.metric: result
            for result in context.historical_gate_result.series_results
        }
        gate_statuses = {
            metric: gate_results[metric].status
            for metric in required_metrics
            if metric in gate_results
        }
        gate_confidence = min(
            (
                gate_results[metric].confidence
                for metric in required_metrics
                if metric in gate_results
            ),
            default=1.0,
        )

        if rule.requires_forecast_input and not context.forecast_input_valid:
            return self._skipped(
                rule=rule,
                status=ValidationAdmissionStatus.SKIPPED_FORECAST_INPUT_INVALID,
                gate_statuses=gate_statuses,
                gate_confidence=gate_confidence,
                reasons=context.forecast_input_errors
                or ("Forecast input failed validation.",),
                evidence=(
                    _admission_evidence(
                        rule=rule,
                        status=ValidationAdmissionStatus.SKIPPED_FORECAST_INPUT_INVALID,
                        summary="Forecast input failed validation.",
                        metrics=required_metrics,
                    ),
                ),
                required_metrics=required_metrics,
            )

        missing_metrics = [
            metric
            for metric in required_metrics
            if metric not in gate_results or gate_results[metric].status == "missing"
        ]
        if missing_metrics:
            return self._skipped(
                rule=rule,
                status=ValidationAdmissionStatus.SKIPPED_REQUIRED_METRIC_MISSING,
                gate_statuses=gate_statuses,
                gate_confidence=gate_confidence,
                reasons=tuple(
                    f"Required metric is missing: {metric}"
                    for metric in missing_metrics
                ),
                evidence=tuple(
                    _admission_evidence(
                        rule=rule,
                        status=ValidationAdmissionStatus.SKIPPED_REQUIRED_METRIC_MISSING,
                        summary=f"Required metric is missing: {metric}",
                        metrics=(metric,),
                        gate_result=gate_results.get(metric),
                    )
                    for metric in missing_metrics
                ),
                required_metrics=required_metrics,
            )

        blocked_metrics = [
            metric
            for metric in required_metrics
            if gate_results[metric].status == "baseline_not_validatable"
        ]
        if blocked_metrics:
            return self._skipped(
                rule=rule,
                status=ValidationAdmissionStatus.SKIPPED_BASELINE_NOT_VALIDATABLE,
                gate_statuses=gate_statuses,
                gate_confidence=gate_confidence,
                reasons=tuple(
                    f"Historical baseline is not validatable: {metric}"
                    for metric in blocked_metrics
                ),
                evidence=tuple(
                    _admission_evidence(
                        rule=rule,
                        status=ValidationAdmissionStatus.SKIPPED_BASELINE_NOT_VALIDATABLE,
                        summary=f"Historical baseline is not validatable: {metric}",
                        metrics=(metric,),
                        gate_result=gate_results[metric],
                    )
                    for metric in blocked_metrics
                ),
                required_metrics=required_metrics,
            )

        insufficient_metrics = [
            metric
            for metric in required_metrics
            if len(gate_results[metric].value_years) < rule.minimum_history_years
        ]
        if insufficient_metrics:
            return self._skipped(
                rule=rule,
                status=ValidationAdmissionStatus.SKIPPED_INSUFFICIENT_HISTORY,
                gate_statuses=gate_statuses,
                gate_confidence=gate_confidence,
                reasons=tuple(
                    "Insufficient admitted history for "
                    f"{metric}: required {rule.minimum_history_years} years."
                    for metric in insufficient_metrics
                ),
                evidence=tuple(
                    _admission_evidence(
                        rule=rule,
                        status=ValidationAdmissionStatus.SKIPPED_INSUFFICIENT_HISTORY,
                        summary=(
                            "Insufficient admitted history for "
                            f"{metric}: required {rule.minimum_history_years} years."
                        ),
                        metrics=(metric,),
                        gate_result=gate_results[metric],
                    )
                    for metric in insufficient_metrics
                ),
                required_metrics=required_metrics,
            )

        if any(
            gate_results[metric].status == "clean_with_warning"
            for metric in required_metrics
        ):
            return ValidationAdmissionResult(
                rule_id=rule.rule_id,
                category=rule.category,
                status=ValidationAdmissionStatus.ADMITTED_WITH_WARNING,
                required_metrics=required_metrics,
                gate_statuses=gate_statuses,
                gate_confidence=gate_confidence,
                reasons=("At least one required metric is clean_with_warning.",),
                evidence=tuple(
                    _admission_evidence(
                        rule=rule,
                        status=ValidationAdmissionStatus.ADMITTED_WITH_WARNING,
                        summary=(
                            "Required metric is admitted with warning: "
                            f"{metric}"
                        ),
                        metrics=(metric,),
                        gate_result=gate_results[metric],
                    )
                    for metric in required_metrics
                    if gate_results[metric].status == "clean_with_warning"
                ),
                confidence=ValidationConfidence(
                    score=gate_confidence,
                    rationale=("Admission allowed with historical baseline warning.",),
                ),
            )

        return ValidationAdmissionResult(
            rule_id=rule.rule_id,
            category=rule.category,
            status=ValidationAdmissionStatus.ADMITTED,
            required_metrics=required_metrics,
            gate_statuses=gate_statuses,
            gate_confidence=gate_confidence,
            reasons=("All required metrics admitted by historical gate.",),
            confidence=ValidationConfidence(
                score=gate_confidence,
                rationale=("Admission allowed by historical gate.",),
            ),
        )

    @staticmethod
    def _skipped(
        *,
        rule: ValidationRule,
        status: ValidationAdmissionStatus,
        gate_statuses: dict[str, str],
        gate_confidence: float,
        reasons: tuple[str, ...],
        evidence: tuple[ValidationEvidence, ...],
        required_metrics: tuple[str, ...],
    ) -> ValidationAdmissionResult:
        return ValidationAdmissionResult(
            rule_id=rule.rule_id,
            category=rule.category,
            status=status,
            required_metrics=required_metrics,
            gate_statuses=gate_statuses,  # type: ignore[arg-type]
            gate_confidence=gate_confidence,
            reasons=reasons,
            evidence=evidence,
            confidence=ValidationConfidence(
                score=gate_confidence,
                rationale=("Rule skipped by admission contract.", *reasons),
            ),
        )


class ValidationScorecardAssembler:
    """Build Forecast Validation scorecards from rule execution results."""

    def assemble(
        self,
        execution_results: Iterable[ValidationExecutionResult],
    ) -> ValidationScorecard:
        """Return overall and per-category scorecard."""

        results = tuple(execution_results)
        grouped: dict[ValidationCategory, list[ValidationExecutionResult]] = defaultdict(list)
        for result in results:
            grouped[result.category].append(result)

        category_scores = tuple(
            self._category_score(category, category_results)
            for category, category_results in sorted(
                grouped.items(),
                key=lambda item: item[0].value,
            )
        )
        issues = [
            issue
            for execution_result in results
            for issue in execution_result.result.issues
        ]
        blocking_issue_count = sum(1 for issue in issues if issue.is_blocking)
        overall_outcome = _aggregate_outcome(
            tuple(score.outcome for score in category_scores)
        )
        numeric_scores = [
            score.score for score in category_scores if score.score is not None
        ]
        confidence_scores = [score.confidence.score for score in category_scores]

        return ValidationScorecard(
            overall_outcome=overall_outcome,
            overall_score=(
                sum(numeric_scores) / len(numeric_scores)
                if numeric_scores
                else None
            ),
            category_scores=category_scores,
            confidence=ValidationConfidence(
                score=min(confidence_scores) if confidence_scores else 1.0,
                rationale=("Scorecard assembled from execution results.",),
            ),
            issue_count=len(issues),
            blocking_issue_count=blocking_issue_count,
        )

    @staticmethod
    def _category_score(
        category: ValidationCategory,
        execution_results: list[ValidationExecutionResult],
    ) -> ValidationCategoryScore:
        outcomes = tuple(result.result.outcome for result in execution_results)
        outcome = _aggregate_outcome(outcomes)
        issues = [
            issue
            for execution_result in execution_results
            for issue in execution_result.result.issues
        ]
        blocking_issue_count = sum(1 for issue in issues if issue.is_blocking)
        confidence_scores = [
            execution_result.result.confidence.score
            for execution_result in execution_results
        ]
        return ValidationCategoryScore(
            category=category,
            outcome=outcome,
            score=_score_for_outcome(outcome),
            issue_count=len(issues),
            blocking_issue_count=blocking_issue_count,
            confidence=ValidationConfidence(
                score=min(confidence_scores) if confidence_scores else 1.0,
                rationale=(f"Category {category.value} score assembled.",),
            ),
        )


class ForecastValidationFramework:
    """Run registered validation rules through gate-first admission."""

    def __init__(
        self,
        *,
        registry: ValidationRuleRegistry,
        admission_service: ValidationAdmissionService | None = None,
        scorecard_assembler: ValidationScorecardAssembler | None = None,
    ) -> None:
        """Initialize the framework executor."""

        self._registry = registry
        self._admission_service = admission_service or ValidationAdmissionService()
        self._scorecard_assembler = scorecard_assembler or ValidationScorecardAssembler()

    def execute(self, engine_input: ValidationEngineInput) -> ValidationEngineOutput:
        """Execute admitted rules and assemble a ForecastValidationResult."""

        execution_results: list[ValidationExecutionResult] = []
        for rule in self._registry.select_rules(engine_input.requested_rule_ids):
            admission = self._admission_service.admit(
                rule=rule,
                context=engine_input.context,
            )
            if admission.status not in _ADMITTED_STATUSES:
                rule_result = _skipped_rule_result(admission)
                execution_results.append(
                    ValidationExecutionResult(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        admission=admission,
                        executed=False,
                        result=rule_result,
                    )
                )
                continue

            raw_result = rule.evaluate(engine_input.context)
            composed_confidence = ConfidenceComposer.compose(
                rule_confidence=raw_result.rule_confidence,
                gate_confidence=admission.gate_confidence,
                evidence_confidence=raw_result.evidence_confidence,
                rationale=raw_result.confidence.rationale,
                limitations=raw_result.confidence.limitations,
            )
            rule_result = raw_result.model_copy(
                update={
                    "gate_confidence": admission.gate_confidence,
                    "confidence": composed_confidence,
                    "evidence": (*admission.evidence, *raw_result.evidence),
                    "warnings": (*admission.reasons, *raw_result.warnings)
                    if admission.status == ValidationAdmissionStatus.ADMITTED_WITH_WARNING
                    else raw_result.warnings,
                }
            )
            execution_results.append(
                ValidationExecutionResult(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    admission=admission,
                    executed=True,
                    result=rule_result,
                )
            )

        execution_tuple = tuple(execution_results)
        scorecard = self._scorecard_assembler.assemble(execution_tuple)
        evidence = _dedupe_evidence(
            evidence
            for execution_result in execution_tuple
            for evidence in execution_result.result.evidence
        )
        issues = tuple(
            issue
            for execution_result in execution_tuple
            for issue in execution_result.result.issues
        )
        result = ForecastValidationResult(
            validation_id=engine_input.context.validation_id,
            company_name=engine_input.context.company_name,
            workbook_id=engine_input.context.workbook_id,
            workbook_fingerprint=engine_input.context.workbook_fingerprint,
            overall_outcome=scorecard.overall_outcome,
            historical_baseline_statuses=engine_input.context.baseline_statuses,
            issues=issues,
            evidence=evidence,
            scorecard=scorecard,
            confidence=scorecard.confidence,
        )
        return ValidationEngineOutput(
            validation_id=engine_input.context.validation_id,
            execution_results=execution_tuple,
            result=result,
        )


def _skipped_rule_result(admission: ValidationAdmissionResult) -> ValidationRuleResult:
    evidence = admission.evidence or (
        _admission_evidence(
            rule_id=admission.rule_id,
            category=admission.category,
            required_metrics=admission.required_metrics,
            status=admission.status,
            summary="Rule skipped by admission contract.",
        ),
    )
    issue = ValidationIssue(
        issue_id=f"{admission.rule_id}:{admission.status.value.lower()}",
        category=admission.category,
        severity=_severity_for_admission(admission.status),
        outcome=ValidationOutcome.SKIPPED,
        title=f"Validation rule skipped: {admission.rule_id}",
        description=" ".join(admission.reasons) or admission.status.value,
        affected_metrics=admission.required_metrics,
        value_years=(),
        evidence_ids=tuple(item.evidence_id for item in evidence),
        is_blocking=True,
        confidence=admission.confidence,
    )
    return ValidationRuleResult(
        rule_id=admission.rule_id,
        category=admission.category,
        outcome=ValidationOutcome.SKIPPED,
        confidence=admission.confidence,
        rule_confidence=admission.confidence.score,
        gate_confidence=admission.gate_confidence,
        evidence_confidence=1.0,
        issues=(issue,),
        evidence=evidence,
        warnings=admission.reasons,
    )


def _admission_evidence(
    *,
    status: ValidationAdmissionStatus,
    summary: str,
    metrics: tuple[str, ...] = (),
    gate_result: HistoricalSeriesIntegrityResult | None = None,
    rule: ValidationRule | None = None,
    rule_id: str | None = None,
    category: ValidationCategory | None = None,
    required_metrics: tuple[str, ...] = (),
) -> ValidationEvidence:
    resolved_rule_id = rule.rule_id if rule is not None else rule_id
    resolved_category = rule.category if rule is not None else category
    resolved_metrics = metrics or (
        rule.required_metrics if rule is not None else required_metrics
    )
    if resolved_rule_id is None or resolved_category is None:
        raise ValueError("Admission evidence requires rule or rule_id/category.")

    metric_suffix = "_".join(resolved_metrics) if resolved_metrics else "no_metric"
    evidence_id = f"{resolved_rule_id}:{status.value.lower()}:{metric_suffix}"
    return ValidationEvidence(
        evidence_id=evidence_id,
        category=resolved_category,
        summary=summary,
        metrics=resolved_metrics,
        value_years=tuple(gate_result.value_years) if gate_result is not None else (),
        historical_baseline_status=gate_result.status if gate_result is not None else None,
        calculations={
            "gate_confidence": gate_result.confidence
            if gate_result is not None
            else None,
            "max_candidate_spread": (
                gate_result.scale_result.max_candidate_spread
                if gate_result is not None
                else None
            ),
            "max_yoy_magnitude_ratio": (
                gate_result.scale_result.max_yoy_magnitude_ratio
                if gate_result is not None
                else None
            ),
            "blocking_issue_count": len(gate_result.blocking_issues)
            if gate_result is not None
            else None,
            "warning_issue_count": len(gate_result.warning_issues)
            if gate_result is not None
            else None,
        },
        citations=_gate_pdf_citations(gate_result),
        provenance={
            "admission_status": status.value,
            "citation_type": "PDF_PROVENANCE"
            if gate_result is not None and gate_result.selected_series
            else "NONE",
            "source": "HistoricalSeriesIntegrityGate",
            "issue_references": _gate_issue_references(gate_result),
            "candidate_spread_issues": _candidate_spread_references(gate_result),
            "source_policy_issues": _source_policy_references(gate_result),
            "scale_consistency": _scale_consistency_reference(gate_result),
            "selected_series": _selected_series_reference(gate_result),
        },
    )


def _gate_pdf_citations(
    gate_result: HistoricalSeriesIntegrityResult | None,
) -> tuple[ValidationCitation, ...]:
    if gate_result is None:
        return ()
    return tuple(
        ValidationCitation(
            citation_id=(
                f"{gate_result.metric}_pdf_"
                f"{candidate.value_year}_{candidate.page_number}"
            ),
            page_number=candidate.page_number,
            source_report_year=candidate.source_report_year,
            table_type=candidate.table_type,
        )
        for candidate in gate_result.selected_series
    )


def _gate_issue_references(
    gate_result: HistoricalSeriesIntegrityResult | None,
) -> list[dict[str, object]]:
    if gate_result is None:
        return []
    return [
        {
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "value_years": issue.value_years,
            "blocking": issue.blocking,
            "evidence_ids": issue.evidence_ids,
        }
        for issue in (*gate_result.blocking_issues, *gate_result.warning_issues)
    ]


def _candidate_spread_references(
    gate_result: HistoricalSeriesIntegrityResult | None,
) -> list[dict[str, object]]:
    if gate_result is None:
        return []
    return [
        {
            "value_year": spread.value_year,
            "candidate_count": spread.candidate_count,
            "candidate_spread": spread.candidate_spread,
            "status": spread.status,
        }
        for spread in gate_result.candidate_spread_by_year
    ]


def _source_policy_references(
    gate_result: HistoricalSeriesIntegrityResult | None,
) -> list[dict[str, object]]:
    if gate_result is None:
        return []
    return [
        {
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "value_years": issue.value_years,
            "blocking": issue.blocking,
            "evidence_ids": issue.evidence_ids,
        }
        for issue in gate_result.source_policy_violations
    ]


def _scale_consistency_reference(
    gate_result: HistoricalSeriesIntegrityResult | None,
) -> dict[str, object]:
    if gate_result is None:
        return {}
    return {
        "status": gate_result.scale_result.status,
        "max_candidate_spread": gate_result.scale_result.max_candidate_spread,
        "max_yoy_magnitude_ratio": gate_result.scale_result.max_yoy_magnitude_ratio,
        "blocking_reasons": gate_result.scale_result.blocking_reasons,
        "warning_reasons": gate_result.scale_result.warning_reasons,
    }


def _selected_series_reference(
    gate_result: HistoricalSeriesIntegrityResult | None,
) -> list[dict[str, object]]:
    if gate_result is None:
        return []
    return [
        {
            "value_year": candidate.value_year,
            "value": candidate.value,
            "source_report_year": candidate.source_report_year,
            "page_number": candidate.page_number,
            "table_type": candidate.table_type,
            "source_class": candidate.source_class,
            "statement_scope": candidate.statement_scope,
            "original_metric": candidate.original_metric,
            "requires_review": candidate.requires_review,
        }
        for candidate in gate_result.selected_series
    ]


def _severity_for_admission(
    status: ValidationAdmissionStatus,
) -> ValidationSeverity:
    if status in {
        ValidationAdmissionStatus.SKIPPED_BASELINE_NOT_VALIDATABLE,
        ValidationAdmissionStatus.SKIPPED_REQUIRED_METRIC_MISSING,
        ValidationAdmissionStatus.SKIPPED_FORECAST_INPUT_INVALID,
    }:
        return ValidationSeverity.HIGH
    if status == ValidationAdmissionStatus.SKIPPED_INSUFFICIENT_HISTORY:
        return ValidationSeverity.WARNING
    return ValidationSeverity.INFO


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


def _dedupe_evidence(
    evidence_items: Iterable[ValidationEvidence],
) -> tuple[ValidationEvidence, ...]:
    evidence_by_id: dict[str, ValidationEvidence] = {}
    for evidence in evidence_items:
        evidence_by_id.setdefault(evidence.evidence_id, evidence)
    return tuple(evidence_by_id[evidence_id] for evidence_id in sorted(evidence_by_id))


__all__ = [
    "ConfidenceComposer",
    "ForecastValidationFramework",
    "ValidationAdmissionService",
    "ValidationRule",
    "ValidationRuleRegistry",
    "ValidationScorecardAssembler",
]
