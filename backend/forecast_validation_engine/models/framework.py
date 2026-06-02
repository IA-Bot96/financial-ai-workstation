"""Framework contracts for Forecast Validation Engine execution."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from forecast_validation_engine.models.forecast_validation import (
    ForecastValidationResult,
    ValidationCategory,
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
)
from forecast_validation_engine.models.forecast_input import ForecastInput
from shared.models.historical_series_integrity import (
    HistoricalSeriesIntegrityGateResult,
    IntegrityStatus as HistoricalBaselineStatus,
)


class ValidationAdmissionStatus(str, Enum):
    """Admission decision for a validation rule."""

    ADMITTED = "ADMITTED"
    ADMITTED_WITH_WARNING = "ADMITTED_WITH_WARNING"
    SKIPPED_BASELINE_NOT_VALIDATABLE = "SKIPPED_BASELINE_NOT_VALIDATABLE"
    SKIPPED_REQUIRED_METRIC_MISSING = "SKIPPED_REQUIRED_METRIC_MISSING"
    SKIPPED_INSUFFICIENT_HISTORY = "SKIPPED_INSUFFICIENT_HISTORY"
    SKIPPED_FORECAST_INPUT_INVALID = "SKIPPED_FORECAST_INPUT_INVALID"


class ValidationContext(BaseModel):
    """Immutable context available to Forecast Validation framework components."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: str = Field(
        ..., min_length=1, description="Stable validation run identifier."
    )
    company_name: str | None = Field(default=None, description="Company name.")
    workbook_id: str | None = Field(default=None, description="Workbook id.")
    workbook_fingerprint: str | None = Field(
        default=None, description="Workbook or bundle fingerprint."
    )
    historical_gate_result: HistoricalSeriesIntegrityGateResult = Field(
        ..., description="Historical baseline integrity gate output."
    )
    forecast_inputs: tuple[ForecastInput, ...] = Field(
        default_factory=tuple,
        description="Forecast input rows supplied for input validation.",
    )
    forecast_input_valid: bool = Field(
        default=True, description="Whether forecast input passed shape validation."
    )
    forecast_input_errors: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Forecast input errors collected before rule admission.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Execution metadata for framework consumers."
    )

    @property
    def baseline_statuses(self) -> dict[str, HistoricalBaselineStatus]:
        """Return baseline status by canonical metric."""

        return {
            result.metric: result.status
            for result in self.historical_gate_result.series_results
        }


class ValidationEngineInput(BaseModel):
    """Input contract for one Forecast Validation framework execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context: ValidationContext = Field(
        ..., description="Validation context for this execution."
    )
    requested_rule_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Optional rule id allow-list. Empty means all registered rules.",
    )


class ValidationAdmissionResult(BaseModel):
    """Admission result that decides whether a rule may execute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(..., min_length=1, description="Validation rule id.")
    category: ValidationCategory = Field(..., description="Rule category.")
    status: ValidationAdmissionStatus = Field(..., description="Admission status.")
    required_metrics: tuple[str, ...] = Field(
        default_factory=tuple, description="Metrics required by the rule."
    )
    gate_statuses: dict[str, HistoricalBaselineStatus] = Field(
        default_factory=dict, description="Gate status by required metric."
    )
    gate_confidence: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description="Minimum gate confidence across required metrics.",
    )
    reasons: tuple[str, ...] = Field(
        default_factory=tuple, description="Deterministic admission reasons."
    )
    evidence: tuple[ValidationEvidence, ...] = Field(
        default_factory=tuple, description="Evidence created during admission."
    )
    confidence: ValidationConfidence = Field(
        default_factory=lambda: ValidationConfidence(score=1.0),
        description="Confidence in the admission decision.",
    )

    @property
    def admitted(self) -> bool:
        """Return whether the rule is allowed to execute."""

        return self.status in {
            ValidationAdmissionStatus.ADMITTED,
            ValidationAdmissionStatus.ADMITTED_WITH_WARNING,
        }


class ValidationRuleResult(BaseModel):
    """Result emitted by an admitted validation rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(..., min_length=1, description="Validation rule id.")
    category: ValidationCategory = Field(..., description="Validation category.")
    outcome: ValidationOutcome = Field(..., description="Rule outcome.")
    confidence: ValidationConfidence = Field(
        ..., description="Final composed validation confidence."
    )
    rule_confidence: float = Field(
        ..., ge=0, le=1, description="Rule-local deterministic confidence."
    )
    gate_confidence: float = Field(
        default=1.0, ge=0, le=1, description="Gate confidence applied."
    )
    evidence_confidence: float = Field(
        default=1.0, ge=0, le=1, description="Evidence completeness confidence."
    )
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple, description="Issues emitted by the rule."
    )
    evidence: tuple[ValidationEvidence, ...] = Field(
        default_factory=tuple, description="Evidence emitted by the rule."
    )
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Rule-level warnings."
    )
    errors: tuple[str, ...] = Field(
        default_factory=tuple, description="Rule-level errors."
    )


class ValidationExecutionResult(BaseModel):
    """Execution result for one registered validation rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(..., min_length=1, description="Validation rule id.")
    category: ValidationCategory = Field(..., description="Validation category.")
    admission: ValidationAdmissionResult = Field(
        ..., description="Admission result for this rule."
    )
    executed: bool = Field(
        ..., description="Whether the rule evaluation method executed."
    )
    result: ValidationRuleResult = Field(
        ..., description="Rule result or framework-generated skipped result."
    )

    @model_validator(mode="after")
    def _validate_admission_enforcement(self) -> "ValidationExecutionResult":
        """Ensure skipped admissions cannot be marked executed."""

        if not self.admission.admitted and self.executed:
            raise ValueError("Rules with skipped admission cannot execute.")
        return self


class ValidationEngineOutput(BaseModel):
    """Output contract for one Forecast Validation framework execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: str = Field(..., min_length=1)
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    execution_results: tuple[ValidationExecutionResult, ...] = Field(
        default_factory=tuple, description="Per-rule execution results."
    )
    result: ForecastValidationResult = Field(
        ..., description="Assembled Forecast Validation result."
    )


__all__ = [
    "ValidationAdmissionResult",
    "ValidationAdmissionStatus",
    "ValidationContext",
    "ValidationEngineInput",
    "ValidationEngineOutput",
    "ValidationExecutionResult",
    "ValidationRuleResult",
]
