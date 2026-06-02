"""Revenue trend-break validation supporting models."""

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
from forecast_validation_engine.models.revenue_growth import GrowthEvidence


class RevenueTrendBreakResult(BaseModel):
    """Typed result for deterministic revenue trend-break validation."""

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
        default=None, description="Average historical revenue growth rate."
    )
    median_growth_rate: float | None = Field(
        default=None, description="Median historical revenue growth rate."
    )
    standard_deviation: float | None = Field(
        default=None, description="Sample standard deviation of historical growth rates."
    )
    growth_volatility: float | None = Field(
        default=None, description="Volatility metric used for trend-break assessment."
    )
    forecast_growth_rate: float | None = Field(
        default=None, description="Forecast growth rate from latest historical year."
    )
    trend_break_type: str | None = Field(
        default=None,
        description="Detected trend-break type, if any.",
        examples=["positive_trend_break"],
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


__all__ = ["RevenueTrendBreakResult"]
