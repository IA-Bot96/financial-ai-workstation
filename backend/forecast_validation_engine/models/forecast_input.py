"""Forecast input models for Forecast Validation Engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from forecast_validation_engine.models.forecast_validation import (
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
)
from shared.models.historical_series_integrity import (
    IntegrityStatus as HistoricalBaselineStatus,
)


class ForecastInput(BaseModel):
    """One forecast value submitted for validation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "metric": "earnings_per_share",
                    "forecast_year": 2026,
                    "value": 60.5,
                    "unit": "PKR/share",
                    "source": "Analyst forecast",
                }
            ]
        },
    )

    metric: str | None = Field(
        default=None,
        description="Canonical metric key for the forecast value.",
    )
    forecast_year: int | None = Field(
        default=None,
        ge=1900,
        description="Forecast year represented by the value.",
    )
    value: float | int | str | None = Field(
        default=None, description="Forecast value supplied by the user or model."
    )
    unit: str | None = Field(default=None, description="Forecast unit when known.")
    scale: str | None = Field(default=None, description="Forecast scale when known.")
    source: str | None = Field(
        default=None, description="Forecast source such as analyst, model, or user."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional source metadata."
    )


class ForecastInputValidationResult(BaseModel):
    """Validation result for one forecast input row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    forecast_input: ForecastInput = Field(..., description="Forecast input row.")
    metric: str | None = Field(default=None, description="Resolved forecast metric.")
    forecast_year: int | None = Field(default=None, ge=1900)
    baseline_status: HistoricalBaselineStatus | None = Field(
        default=None, description="Historical baseline status for the metric."
    )
    gate_confidence: float | None = Field(
        default=None, ge=0, le=1, description="Historical gate confidence."
    )
    outcome: ValidationOutcome = Field(..., description="Input validation outcome.")
    can_proceed: bool = Field(
        ..., description="Whether downstream forecast validation may proceed."
    )
    confidence: ValidationConfidence = Field(
        ..., description="Confidence in this input validation result."
    )
    issues: tuple[ValidationIssue, ...] = Field(default_factory=tuple)
    evidence: tuple[ValidationEvidence, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)


__all__ = ["ForecastInput", "ForecastInputValidationResult"]
