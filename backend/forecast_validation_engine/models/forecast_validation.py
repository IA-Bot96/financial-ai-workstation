"""Pydantic contracts for Forecast Validation Engine results."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.models.historical_series_integrity import (
    IntegrityStatus as HistoricalBaselineStatus,
)


class ValidationSeverity(str, Enum):
    """Severity of a validation issue."""

    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class ValidationCategory(str, Enum):
    """High-level validation category."""

    REVENUE = "revenue"
    PROFITABILITY = "profitability"
    CASH_FLOW = "cash_flow"
    DEBT = "debt"
    BALANCE_SHEET = "balance_sheet"
    FORECAST_PLAUSIBILITY = "forecast_plausibility"
    TREND_BREAK = "trend_break"
    HISTORICAL_BASELINE = "historical_baseline"
    DATA_QUALITY = "data_quality"


class ValidationOutcome(str, Enum):
    """Deterministic validation outcome."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    SKIPPED = "skipped"


class ValidationConfidence(BaseModel):
    """Confidence assigned to a validation result or issue."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "score": 0.82,
                    "rationale": [
                        "Historical baseline is clean with warning.",
                        "Workbook citations are available.",
                    ],
                    "limitations": ["Statement scope is unknown."],
                }
            ]
        },
    )

    score: float = Field(
        ..., ge=0, le=1, description="Confidence score from 0 to 1."
    )
    rationale: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Deterministic reasons supporting the confidence score.",
    )
    limitations: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Known limitations that reduce or contextualize confidence.",
    )


class ValidationCitation(BaseModel):
    """Workbook and source citation attached to validation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(
        ..., min_length=1, description="Stable citation identifier."
    )
    workbook_fingerprint: str | None = Field(
        default=None, description="Workbook fingerprint when available."
    )
    sheet_name: str | None = Field(default=None, description="Workbook sheet name.")
    cell_reference: str | None = Field(
        default=None, description="Workbook cell reference such as B12."
    )
    row: int | None = Field(default=None, gt=0, description="One-based row number.")
    column: int | None = Field(
        default=None, gt=0, description="One-based column number."
    )
    page_number: int | None = Field(
        default=None, gt=0, description="One-based PDF source page."
    )
    source_report_year: int | None = Field(
        default=None, ge=1900, description="Annual report year for the source."
    )
    table_type: str | None = Field(default=None, description="Source table type.")


class ValidationEvidence(BaseModel):
    """Evidence record supporting a validation issue or scorecard result."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "evidence_id": "revenue:2025:baseline",
                    "category": "historical_baseline",
                    "summary": "Revenue baseline was blocked by candidate spread.",
                    "metrics": ["revenue"],
                    "value_years": [2025],
                    "historical_baseline_status": "baseline_not_validatable",
                }
            ]
        },
    )

    evidence_id: str = Field(
        ..., min_length=1, description="Stable evidence identifier."
    )
    category: ValidationCategory = Field(..., description="Evidence category.")
    summary: str = Field(
        ..., min_length=1, description="Human-readable evidence summary."
    )
    metrics: tuple[str, ...] = Field(
        default_factory=tuple, description="Canonical metrics referenced."
    )
    value_years: tuple[int, ...] = Field(
        default_factory=tuple, description="Financial years referenced."
    )
    historical_baseline_status: HistoricalBaselineStatus | None = Field(
        default=None,
        description="Historical integrity-gate status for the referenced metric.",
    )
    calculations: dict[str, float | int | str | None] = Field(
        default_factory=dict,
        description="Precomputed deterministic values used as evidence.",
    )
    citations: tuple[ValidationCitation, ...] = Field(
        default_factory=tuple,
        description="Workbook and source citations for the evidence.",
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Structured source provenance."
    )


class ValidationIssue(BaseModel):
    """One deterministic validation issue."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "issue_id": "revenue:baseline_not_validatable",
                    "category": "historical_baseline",
                    "severity": "critical",
                    "outcome": "fail",
                    "title": "Revenue baseline is not validatable",
                    "description": "Revenue has same-year candidate spreads above 100x.",
                    "affected_metrics": ["revenue"],
                    "value_years": [2025],
                    "historical_baseline_status": "baseline_not_validatable",
                    "evidence_ids": ["revenue:2025:baseline"],
                    "is_blocking": True,
                    "confidence": {"score": 0.9},
                }
            ]
        },
    )

    issue_id: str = Field(..., min_length=1, description="Stable issue id.")
    category: ValidationCategory = Field(..., description="Validation category.")
    severity: ValidationSeverity = Field(..., description="Issue severity.")
    outcome: ValidationOutcome = Field(
        ..., description="Validation outcome represented by this issue."
    )
    title: str = Field(..., min_length=1, description="Short issue title.")
    description: str = Field(
        ..., min_length=1, description="Detailed deterministic issue explanation."
    )
    affected_metrics: tuple[str, ...] = Field(
        default_factory=tuple, description="Canonical metrics affected by the issue."
    )
    value_years: tuple[int, ...] = Field(
        default_factory=tuple, description="Financial years affected by the issue."
    )
    historical_baseline_status: HistoricalBaselineStatus | None = Field(
        default=None,
        description="Historical baseline status associated with the issue.",
    )
    evidence_ids: tuple[str, ...] = Field(
        ..., min_length=1, description="Evidence ids supporting this issue."
    )
    is_blocking: bool = Field(
        ..., description="Whether this issue blocks forecast validation."
    )
    confidence: ValidationConfidence = Field(
        ..., description="Confidence in this issue."
    )

    @model_validator(mode="after")
    def _validate_issue_consistency(self) -> "ValidationIssue":
        """Validate structural consistency for issue severity and outcome."""

        if self.severity == ValidationSeverity.CRITICAL and not self.is_blocking:
            raise ValueError("critical validation issues must be blocking.")
        if self.is_blocking and self.outcome == ValidationOutcome.PASS:
            raise ValueError("blocking validation issues cannot have pass outcome.")
        return self


class ValidationCategoryScore(BaseModel):
    """Scorecard row for one validation category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ValidationCategory = Field(..., description="Validation category.")
    outcome: ValidationOutcome = Field(..., description="Category outcome.")
    score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Category score from 0 to 100 when scored.",
    )
    issue_count: int = Field(
        default=0, ge=0, description="Issues emitted for this category."
    )
    blocking_issue_count: int = Field(
        default=0, ge=0, description="Blocking issues in this category."
    )
    confidence: ValidationConfidence = Field(
        default_factory=lambda: ValidationConfidence(score=0.0),
        description="Confidence for the category outcome.",
    )

    @model_validator(mode="after")
    def _validate_category_score_counts(self) -> "ValidationCategoryScore":
        """Ensure blocking counts cannot exceed total issue counts."""

        if self.blocking_issue_count > self.issue_count:
            raise ValueError("blocking_issue_count cannot exceed issue_count.")
        return self


class ValidationScorecard(BaseModel):
    """Overall and category-level validation scorecard."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "overall_outcome": "skipped",
                    "overall_score": None,
                    "category_scores": [
                        {
                            "category": "historical_baseline",
                            "outcome": "fail",
                            "score": 0,
                            "issue_count": 1,
                            "blocking_issue_count": 1,
                            "confidence": {"score": 0.9},
                        }
                    ],
                    "confidence": {"score": 0.9},
                }
            ]
        },
    )

    overall_outcome: ValidationOutcome = Field(
        ..., description="Overall validation outcome."
    )
    overall_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Overall score from 0 to 100 when scoring is applicable.",
    )
    category_scores: tuple[ValidationCategoryScore, ...] = Field(
        default_factory=tuple, description="Per-category scorecard rows."
    )
    confidence: ValidationConfidence = Field(
        ..., description="Confidence in the scorecard."
    )
    issue_count: int = Field(default=0, ge=0, description="Total issue count.")
    blocking_issue_count: int = Field(
        default=0, ge=0, description="Total blocking issue count."
    )
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Scorecard-level warnings."
    )

    @model_validator(mode="after")
    def _validate_scorecard_counts(self) -> "ValidationScorecard":
        """Ensure scorecard counts are internally consistent."""

        if self.blocking_issue_count > self.issue_count:
            raise ValueError("blocking_issue_count cannot exceed issue_count.")
        return self


class ForecastValidationResult(BaseModel):
    """Root result produced by the Forecast Validation Engine."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "validation_id": "fv_lucky_2025_001",
                    "schema_version": "1.0.0",
                    "company_name": "Lucky Cement Limited",
                    "workbook_id": "wb_001",
                    "overall_outcome": "skipped",
                    "historical_baseline_statuses": {
                        "revenue": "baseline_not_validatable",
                        "earnings_per_share": "clean_with_warning",
                    },
                    "scorecard": {
                        "overall_outcome": "skipped",
                        "overall_score": None,
                        "confidence": {"score": 0.8},
                    },
                }
            ]
        },
    )

    validation_id: str = Field(
        ..., min_length=1, description="Stable validation run id."
    )
    schema_version: str = Field(
        default="1.0.0", description="Forecast Validation result schema version."
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the result was generated.",
    )
    company_name: str | None = Field(default=None, description="Company name.")
    workbook_id: str | None = Field(default=None, description="Workbook id.")
    workbook_fingerprint: str | None = Field(
        default=None, description="Workbook or bundle fingerprint."
    )
    overall_outcome: ValidationOutcome = Field(
        ..., description="Overall validation outcome."
    )
    historical_baseline_statuses: dict[str, HistoricalBaselineStatus] = Field(
        default_factory=dict,
        description="Historical integrity-gate status by canonical metric.",
    )
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple, description="Validation issues emitted."
    )
    evidence: tuple[ValidationEvidence, ...] = Field(
        default_factory=tuple, description="Evidence records supporting issues."
    )
    scorecard: ValidationScorecard = Field(
        ..., description="Overall and category validation scorecard."
    )
    confidence: ValidationConfidence = Field(
        default_factory=lambda: ValidationConfidence(score=0.0),
        description="Confidence in the overall result.",
    )
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Result-level warnings."
    )
    errors: tuple[str, ...] = Field(
        default_factory=tuple, description="Result-level errors."
    )

    @model_validator(mode="after")
    def _validate_result_consistency(self) -> "ForecastValidationResult":
        """Validate references and scorecard consistency."""

        if self.scorecard.overall_outcome != self.overall_outcome:
            raise ValueError("scorecard overall_outcome must match result outcome.")

        evidence_ids = {item.evidence_id for item in self.evidence}
        missing_evidence_ids = sorted(
            {
                evidence_id
                for issue in self.issues
                for evidence_id in issue.evidence_ids
                if evidence_id not in evidence_ids
            }
        )
        if missing_evidence_ids:
            raise ValueError(
                "Validation issues reference missing evidence ids: "
                + ", ".join(missing_evidence_ids)
            )
        return self


__all__ = [
    "ForecastValidationResult",
    "HistoricalBaselineStatus",
    "ValidationCategory",
    "ValidationCategoryScore",
    "ValidationCitation",
    "ValidationConfidence",
    "ValidationEvidence",
    "ValidationIssue",
    "ValidationOutcome",
    "ValidationScorecard",
    "ValidationSeverity",
]
