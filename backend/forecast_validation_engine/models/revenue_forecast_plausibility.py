"""Revenue forecast plausibility validation supporting models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from forecast_validation_engine.models.forecast_input import ForecastInput
from forecast_validation_engine.models.forecast_validation import (
    HistoricalBaselineStatus,
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
)


class RevenueForecastPlausibilityResult(BaseModel):
    """Typed result for deterministic revenue forecast plausibility validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    forecast_input: ForecastInput = Field(
        ..., description="Revenue forecast input evaluated by the rule."
    )
    baseline_status: HistoricalBaselineStatus = Field(
        ..., description="Revenue historical baseline status from the integrity gate."
    )
    historical_minimum: float | None = Field(
        default=None, description="Minimum admitted historical revenue."
    )
    historical_maximum: float | None = Field(
        default=None, description="Maximum admitted historical revenue."
    )
    historical_average: float | None = Field(
        default=None, description="Average admitted historical revenue."
    )
    latest_revenue: float | None = Field(
        default=None, description="Latest admitted historical revenue."
    )
    forecast_revenue: float | None = Field(
        default=None, description="Forecast revenue value."
    )
    forecast_multiple: float | None = Field(
        default=None,
        description="Forecast revenue divided by historical maximum revenue.",
    )
    distance_from_latest: float | None = Field(
        default=None,
        description="Absolute relative distance from latest historical revenue.",
    )
    distance_from_average: float | None = Field(
        default=None,
        description="Absolute relative distance from average historical revenue.",
    )
    outcome: ValidationOutcome = Field(..., description="Rule outcome.")
    confidence: ValidationConfidence = Field(
        ..., description="Composed deterministic confidence for the result."
    )
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple, description="Issues emitted by the rule."
    )
    evidence: tuple[ValidationEvidence, ...] = Field(
        default_factory=tuple, description="Evidence emitted by the rule."
    )
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Rule warnings."
    )
    errors: tuple[str, ...] = Field(default_factory=tuple, description="Rule errors.")


__all__ = ["RevenueForecastPlausibilityResult"]
