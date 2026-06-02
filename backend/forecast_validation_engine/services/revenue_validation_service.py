"""Revenue category validation service."""

from __future__ import annotations

from collections.abc import Iterable

from forecast_validation_engine.models.forecast_validation import (
    ValidationCategory,
    ValidationCategoryScore,
    ValidationCitation,
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
)
from forecast_validation_engine.models.framework import (
    ValidationContext,
    ValidationEngineInput,
    ValidationExecutionResult,
)
from forecast_validation_engine.models.revenue_validation import (
    RevenueValidationResult,
    RevenueValidationSummary,
)
from forecast_validation_engine.rules.revenue_forecast_plausibility_validation_rule import (
    RevenueForecastPlausibilityValidationRule,
)
from forecast_validation_engine.rules.revenue_growth_validation_rule import (
    RevenueGrowthValidationRule,
)
from forecast_validation_engine.rules.revenue_trend_break_validation_rule import (
    RevenueTrendBreakValidationRule,
)
from forecast_validation_engine.services.validation_framework import (
    ForecastValidationFramework,
    ValidationRuleRegistry,
)


class RevenueValidationService:
    """Execute and aggregate the complete deterministic revenue validation category."""

    def __init__(self, framework: ForecastValidationFramework | None = None) -> None:
        """Initialize service with the default revenue rule set."""

        self._framework = framework or ForecastValidationFramework(
            registry=ValidationRuleRegistry(
                [
                    RevenueGrowthValidationRule(),
                    RevenueTrendBreakValidationRule(),
                    RevenueForecastPlausibilityValidationRule(),
                ]
            )
        )

    def validate(self, context: ValidationContext) -> RevenueValidationResult:
        """Run all revenue rules and return a category-level aggregate."""

        output = self._framework.execute(ValidationEngineInput(context=context))
        execution_results = output.execution_results
        issues = tuple(
            issue
            for execution_result in execution_results
            for issue in execution_result.result.issues
        )
        evidence = _dedupe_evidence(
            evidence_item
            for execution_result in execution_results
            for evidence_item in execution_result.result.evidence
        )
        citations = _dedupe_citations(
            citation
            for evidence_item in evidence
            for citation in evidence_item.citations
        )
        outcome = _aggregate_outcome(
            tuple(execution_result.result.outcome for execution_result in execution_results)
        )
        confidence = _aggregate_confidence(execution_results)
        score = _score_for_outcome(outcome)
        warnings = tuple(
            warning
            for execution_result in execution_results
            for warning in execution_result.result.warnings
        )
        blocking_issue_count = sum(1 for issue in issues if issue.is_blocking)
        category_score = ValidationCategoryScore(
            category=ValidationCategory.REVENUE,
            outcome=outcome,
            score=score,
            issue_count=len(issues),
            blocking_issue_count=blocking_issue_count,
            confidence=confidence,
        )
        summary = RevenueValidationSummary(
            outcome=outcome,
            score=score,
            confidence=confidence,
            rule_count=len(execution_results),
            executed_rule_count=sum(1 for result in execution_results if result.executed),
            skipped_rule_count=sum(
                1 for result in execution_results if not result.executed
            ),
            issue_count=len(issues),
            blocking_issue_count=blocking_issue_count,
            warnings=warnings,
        )
        return RevenueValidationResult(
            validation_id=context.validation_id,
            summary=summary,
            category_score=category_score,
            execution_results=execution_results,
            issues=issues,
            evidence=evidence,
            citations=citations,
            provenance={
                "source": "RevenueValidationService",
                "rule_ids": [result.rule_id for result in execution_results],
                "rule_outcomes": {
                    result.rule_id: result.result.outcome.value
                    for result in execution_results
                },
                "admission_statuses": {
                    result.rule_id: result.admission.status.value
                    for result in execution_results
                },
                "executed_rules": [
                    result.rule_id for result in execution_results if result.executed
                ],
                "skipped_rules": [
                    result.rule_id for result in execution_results if not result.executed
                ],
            },
        )


def _aggregate_outcome(outcomes: tuple[ValidationOutcome, ...]) -> ValidationOutcome:
    if not outcomes:
        return ValidationOutcome.SKIPPED
    if ValidationOutcome.FAIL in outcomes:
        return ValidationOutcome.FAIL
    if ValidationOutcome.WARNING in outcomes:
        return ValidationOutcome.WARNING
    if all(outcome == ValidationOutcome.SKIPPED for outcome in outcomes):
        return ValidationOutcome.SKIPPED
    if ValidationOutcome.PASS in outcomes:
        return ValidationOutcome.PASS
    return ValidationOutcome.SKIPPED


def _aggregate_confidence(
    execution_results: tuple[ValidationExecutionResult, ...],
) -> ValidationConfidence:
    scores = [result.result.confidence.score for result in execution_results]
    score = min(scores) if scores else 1.0
    return ValidationConfidence(
        score=score,
        rationale=(
            "Revenue category confidence is the minimum confidence across revenue rules.",
            *(f"{result.rule_id}={result.result.confidence.score:.4f}" for result in execution_results),
        ),
    )


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


__all__ = ["RevenueValidationService"]
