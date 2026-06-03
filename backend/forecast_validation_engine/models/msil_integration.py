"""MSIL evidence consumption contracts for Forecast Validation reporting."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from forecast_validation_engine.models.forecast_validation import ValidationEvidence


class MSILNumericInfluence(str, Enum):
    """How non-baseline MSIL evidence may influence FVE reporting."""

    INCREASE_CONFIDENCE = "increase_confidence"
    DECREASE_CONFIDENCE = "decrease_confidence"
    REPORTING_CONTEXT_ONLY = "reporting_context_only"


class ForecastContextPlausibilityStatus(str, Enum):
    """Forward-looking plausibility status, distinct from validation pass/fail."""

    PLAUSIBLE = "plausible"
    PLAUSIBLE_WITH_WARNINGS = "plausible_with_warnings"
    IMPLAUSIBLE_REQUIRES_REVIEW = "implausible_requires_review"


class ForecastContextBenchmark(BaseModel):
    """One MSIL forecast-context benchmark retained for plausibility reporting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(..., min_length=1)
    signal_ref: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    forecast_year: int | None = Field(default=None, ge=1900)
    benchmark_value: float | int | str
    authority_label: str = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    uncertainty_indicator: str = Field(..., min_length=1)
    divergence_refs: tuple[str, ...] = Field(default_factory=tuple)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ForecastContextPlausibilityAssessment(BaseModel):
    """Governance-only assessment of submitted forecast against MSIL benchmarks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment_id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    forecast_year: int | None = Field(default=None, ge=1900)
    status: ForecastContextPlausibilityStatus
    plausibility_confidence: float = Field(..., ge=0, le=1)
    authority_ceiling: float = Field(..., ge=0, le=1)
    benchmark_values: tuple[ForecastContextBenchmark, ...] = Field(
        default_factory=tuple
    )
    submitted_forecast_value: float | int | str | None = Field(default=None)
    deviation_ratio: float | None = Field(default=None)
    uncertainty_indicator: str = Field(..., min_length=1)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    divergence_refs: tuple[str, ...] = Field(default_factory=tuple)
    governance_boundary: str = Field(
        default="plausibility_only",
        description="Forecast context never affects HSIG, baseline, or validation truth.",
    )


class MSILNumericConfidenceAdjustment(BaseModel):
    """Report-only confidence influence derived from MSIL-owned evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(..., min_length=1)
    signal_ref: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    influence: MSILNumericInfluence
    adjustment: float = Field(
        ...,
        ge=-1,
        le=1,
        description="Signed confidence influence. This is never a calculation input.",
    )
    reason: str = Field(..., min_length=1)
    divergence_refs: tuple[str, ...] = Field(default_factory=tuple)
    corroboration_refs: tuple[str, ...] = Field(default_factory=tuple)
    authority_ceiling: float | None = Field(default=None, ge=0, le=1)
    applies_to: str = Field(
        default="reporting_confidence_only",
        min_length=1,
        description="Never applies to baseline or historical validation confidence.",
    )


class MSILNumericEvidenceConsumptionResult(BaseModel):
    """FVE consumption result for MSIL NumericEvidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_processed: int = Field(..., ge=0)
    supporting_evidence_consumed: int = Field(..., ge=0)
    event_facts_consumed: int = Field(..., ge=0)
    forecast_context_consumed: int = Field(default=0, ge=0)
    forecast_context_ignored: int = Field(..., ge=0)
    baseline_evidence_ignored: int = Field(..., ge=0)
    non_authoritative_ignored: int = Field(..., ge=0)
    divergences_surfaced: int = Field(..., ge=0)
    confidence_adjustments: tuple[MSILNumericConfidenceAdjustment, ...] = Field(
        default_factory=tuple
    )
    plausibility_assessments: tuple[ForecastContextPlausibilityAssessment, ...] = Field(
        default_factory=tuple
    )
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    validation_evidence: tuple[ValidationEvidence, ...] = Field(default_factory=tuple)
    hsig_bypass_attempts: int = Field(default=0, ge=0)
    baseline_modifications: int = Field(default=0, ge=0)
    calculations_modified: int = Field(default=0, ge=0)
    ownership_boundaries: dict[str, bool] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ForecastContextBenchmark",
    "ForecastContextPlausibilityAssessment",
    "ForecastContextPlausibilityStatus",
    "MSILNumericConfidenceAdjustment",
    "MSILNumericEvidenceConsumptionResult",
    "MSILNumericInfluence",
]
