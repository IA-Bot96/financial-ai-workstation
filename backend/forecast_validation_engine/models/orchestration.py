"""Forecast Validation Engine run-level orchestration models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from forecast_validation_engine.models.forecast_validation import (
    ValidationCategoryScore,
    ValidationCitation,
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
)
from forecast_validation_engine.models.framework import ValidationExecutionResult
from shared.models.historical_series_integrity import HistoricalSeriesIntegrityGateResult


class ForecastValidationRunScorecard(BaseModel):
    """Run-level scorecard assembled by the Forecast Validation orchestrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_outcome: ValidationOutcome = Field(
        ..., description="Run-level validation outcome."
    )
    overall_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Run-level score when scored categories are available.",
    )
    metrics_admitted: int = Field(
        default=0,
        ge=0,
        description="Historical metrics admitted by the integrity gate.",
    )
    metrics_blocked: int = Field(
        default=0,
        ge=0,
        description="Historical metrics blocked by the integrity gate.",
    )
    metrics_missing: int = Field(
        default=0,
        ge=0,
        description="Historical metrics missing from the integrity gate input.",
    )
    coverage_percentage: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Admitted metric count divided by evaluated metric count.",
    )
    bundle_fingerprint: str | None = Field(
        default=None,
        description="Production bundle fingerprint pinned to this scorecard.",
    )
    gate_version: str = Field(
        default="unknown",
        min_length=1,
        description="HistoricalSeriesIntegrityGate logic version.",
    )
    category_scores: tuple[ValidationCategoryScore, ...] = Field(
        default_factory=tuple,
        description="Scorecard rows for executable and deferred categories.",
    )
    category_outcomes: dict[str, ValidationOutcome] = Field(
        default_factory=dict,
        description="Outcome by orchestration category name.",
    )
    category_scores_by_name: dict[str, float | None] = Field(
        default_factory=dict,
        description="Score by orchestration category name.",
    )
    category_confidence_by_name: dict[str, float] = Field(
        default_factory=dict,
        description="Confidence by orchestration category name.",
    )
    executed_categories: tuple[str, ...] = Field(
        default_factory=tuple, description="Categories that executed."
    )
    skipped_categories: tuple[str, ...] = Field(
        default_factory=tuple, description="Categories skipped by admission or scope."
    )
    deferred_categories: tuple[str, ...] = Field(
        default_factory=tuple, description="MVP-deferred categories not executed."
    )
    confidence: ValidationConfidence = Field(
        ..., description="Run-level aggregate confidence."
    )
    issue_count: int = Field(default=0, ge=0, description="Total issue count.")
    blocking_issue_count: int = Field(
        default=0, ge=0, description="Total blocking issue count."
    )
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Run-level warnings."
    )


class ForecastValidationRunResult(BaseModel):
    """Complete result produced by the Forecast Validation orchestrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: str = Field(
        ..., min_length=1, description="Stable validation run identifier."
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when orchestration completed.",
    )
    company_name: str | None = Field(default=None, description="Company name.")
    workbook_id: str | None = Field(default=None, description="Workbook id.")
    workbook_fingerprint: str | None = Field(
        default=None, description="Workbook or bundle fingerprint."
    )
    bundle_fingerprint: str | None = Field(
        default=None, description="Production bundle fingerprint used for this run."
    )
    gate_version: str = Field(
        default="unknown", min_length=1, description="Historical gate logic version."
    )
    historical_gate_result: HistoricalSeriesIntegrityGateResult = Field(
        ..., description="Historical-series integrity gate output."
    )
    scorecard: ForecastValidationRunScorecard = Field(
        ..., description="Run-level scorecard."
    )
    execution_results: tuple[ValidationExecutionResult, ...] = Field(
        default_factory=tuple,
        description="Rule execution results for categories that reached the framework.",
    )
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple, description="Run-level issues."
    )
    evidence: tuple[ValidationEvidence, ...] = Field(
        default_factory=tuple, description="Run-level evidence."
    )
    citations: tuple[ValidationCitation, ...] = Field(
        default_factory=tuple, description="Run-level deduplicated citations."
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Run-level orchestration provenance."
    )


__all__ = [
    "ForecastValidationRunResult",
    "ForecastValidationRunScorecard",
]
