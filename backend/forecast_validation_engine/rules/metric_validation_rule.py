"""Base infrastructure for metric-specific validation rules."""

from __future__ import annotations

from abc import abstractmethod

from forecast_validation_engine.models.framework import (
    ValidationContext,
    ValidationRuleResult,
)
from forecast_validation_engine.models.metric_validation import (
    MetricValidationContext,
    MetricValidationResult,
)
from forecast_validation_engine.services.validation_framework import ValidationRule
from shared.models.historical_series_integrity import HistoricalSeriesIntegrityResult


class BaseMetricValidationRule(ValidationRule):
    """Base class for deterministic single-metric validation rules."""

    metric: str

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        """Build metric context, run rule implementation, and adapt result."""

        gate_result = self._find_gate_result(context)
        metric_context = MetricValidationContext(
            validation_context=context,
            metric=self.metric,
            gate_result=gate_result,
        )
        metric_result = self.evaluate_metric(metric_context)
        return ValidationRuleResult(
            rule_id=self.rule_id,
            category=self.category,
            outcome=metric_result.outcome,
            confidence=metric_result.confidence,
            rule_confidence=metric_result.rule_confidence,
            gate_confidence=gate_result.confidence,
            evidence_confidence=metric_result.evidence_confidence,
            issues=metric_result.issues,
            evidence=metric_result.evidence,
            warnings=metric_result.warnings,
            errors=metric_result.errors,
        )

    @abstractmethod
    def evaluate_metric(
        self,
        context: MetricValidationContext,
    ) -> MetricValidationResult:
        """Evaluate the admitted metric and return a metric result."""

    def _find_gate_result(
        self,
        context: ValidationContext,
    ) -> HistoricalSeriesIntegrityResult:
        """Return the historical gate result for this rule's metric."""

        for result in context.historical_gate_result.series_results:
            if result.metric == self.metric:
                return result
        raise ValueError(
            f"Missing historical gate result for required metric: {self.metric}"
        )


__all__ = ["BaseMetricValidationRule"]
