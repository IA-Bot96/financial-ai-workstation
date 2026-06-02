"""Metric validation contracts for Forecast Validation rules."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from forecast_validation_engine.models.forecast_validation import (
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
)
from forecast_validation_engine.models.framework import ValidationContext
from shared.models.historical_series_integrity import (
    HistoricalSeriesIntegrityResult,
    IntegrityStatus as HistoricalBaselineStatus,
)


class MetricValidationContext(BaseModel):
    """Context passed to a single-metric validation rule implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_context: ValidationContext = Field(
        ..., description="Forecast Validation execution context."
    )
    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    gate_result: HistoricalSeriesIntegrityResult = Field(
        ..., description="Historical integrity result for the metric."
    )


class MetricValidationResult(BaseModel):
    """Intermediate result returned by metric validation rule implementations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    baseline_status: HistoricalBaselineStatus = Field(
        ..., description="Historical baseline status used by the rule."
    )
    outcome: ValidationOutcome = Field(..., description="Rule outcome.")
    confidence: ValidationConfidence = Field(
        ..., description="Rule-local confidence before framework composition."
    )
    rule_confidence: float = Field(
        ..., ge=0, le=1, description="Rule-local confidence score."
    )
    evidence_confidence: float = Field(
        default=1.0, ge=0, le=1, description="Evidence completeness confidence."
    )
    value_years: tuple[int, ...] = Field(
        default_factory=tuple, description="Historical years covered by the metric."
    )
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple, description="Validation issues produced by the rule."
    )
    evidence: tuple[ValidationEvidence, ...] = Field(
        default_factory=tuple, description="Evidence produced by the rule."
    )
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Rule-level warnings."
    )
    errors: tuple[str, ...] = Field(
        default_factory=tuple, description="Rule-level errors."
    )


__all__ = ["MetricValidationContext", "MetricValidationResult"]
