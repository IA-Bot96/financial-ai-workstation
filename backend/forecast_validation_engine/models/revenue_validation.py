"""Revenue category validation aggregate models."""

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


class RevenueValidationSummary(BaseModel):
    """Deterministic summary for the complete revenue validation category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: ValidationOutcome = Field(
        ..., description="Aggregated revenue category outcome."
    )
    score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Revenue category score when applicable.",
    )
    confidence: ValidationConfidence = Field(
        ..., description="Aggregated revenue category confidence."
    )
    rule_count: int = Field(..., ge=0, description="Revenue rules evaluated.")
    executed_rule_count: int = Field(
        ..., ge=0, description="Revenue rules that executed after admission."
    )
    skipped_rule_count: int = Field(
        ..., ge=0, description="Revenue rules skipped by admission."
    )
    issue_count: int = Field(..., ge=0, description="Revenue issues emitted.")
    blocking_issue_count: int = Field(
        ..., ge=0, description="Blocking revenue issues emitted."
    )
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Revenue category warnings."
    )


class RevenueValidationResult(BaseModel):
    """Complete deterministic result for revenue category validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: str = Field(
        ..., min_length=1, description="Validation run identifier."
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when revenue validation completed.",
    )
    summary: RevenueValidationSummary = Field(
        ..., description="Aggregated revenue category summary."
    )
    category_score: ValidationCategoryScore = Field(
        ..., description="Revenue category scorecard row."
    )
    execution_results: tuple[ValidationExecutionResult, ...] = Field(
        default_factory=tuple,
        description="Execution results for the revenue validation rules.",
    )
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple, description="Aggregated revenue issues."
    )
    evidence: tuple[ValidationEvidence, ...] = Field(
        default_factory=tuple, description="Aggregated revenue evidence."
    )
    citations: tuple[ValidationCitation, ...] = Field(
        default_factory=tuple, description="Deduplicated revenue citations."
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured provenance for revenue category aggregation.",
    )


__all__ = [
    "RevenueValidationResult",
    "RevenueValidationSummary",
]
