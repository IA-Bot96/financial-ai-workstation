"""Revenue growth validation supporting models."""

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


class GrowthEvidence(BaseModel):
    """One deterministic growth calculation between two adjacent years."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(
        ..., min_length=1, description="Canonical metric being compared."
    )
    from_year: int = Field(
        ..., ge=1900, description="Prior financial year in the growth calculation."
    )
    to_year: int = Field(
        ..., ge=1900, description="Current financial year in the growth calculation."
    )
    from_value: float = Field(..., description="Prior-year numeric value.")
    to_value: float = Field(..., description="Current-year numeric value.")
    growth_rate: float = Field(
        ..., description="Growth rate as a decimal. Example: 0.1 means 10%."
    )


class RevenueGrowthValidationResult(BaseModel):
    """Typed result for the revenue forecast growth validation rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    forecast_input: ForecastInput = Field(
        ..., description="Revenue forecast input evaluated by the rule."
    )
    baseline_status: HistoricalBaselineStatus = Field(
        ..., description="Revenue historical baseline status from the integrity gate."
    )
    historical_growth_rates: tuple[GrowthEvidence, ...] = Field(
        default_factory=tuple,
        description="Adjacent-year historical revenue growth calculations.",
    )
    average_growth_rate: float | None = Field(
        default=None, description="Average historical growth rate."
    )
    min_growth_rate: float | None = Field(
        default=None, description="Minimum historical growth rate."
    )
    max_growth_rate: float | None = Field(
        default=None, description="Maximum historical growth rate."
    )
    forecast_growth_rate: float | None = Field(
        default=None, description="Forecast growth rate from latest historical year."
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


__all__ = [
    "GrowthEvidence",
    "RevenueGrowthValidationResult",
]
