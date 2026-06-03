"""Numeric admission contracts for FVE multi-source governance."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from multi_source_intelligence.models import (
    AuthorityClass,
    ClaimType,
    IntelligenceSignalProvenance,
    SourceType,
)
from shared.models.historical_series_integrity import (
    IntegrityStatus as HistoricalBaselineStatus,
)


NUMERIC_ADMISSION_POLICY_VERSION = "1.0.0"


class NumericRole(str, Enum):
    """FVE role assigned to an incoming MSIL numeric claim."""

    BASELINE = "baseline"
    SUPPORTING = "supporting"
    EVENT_FACT = "event_fact"
    FORECAST_CONTEXT = "forecast_context"
    NON_AUTHORITATIVE = "non_authoritative"


class NumericEvidenceStatus(str, Enum):
    """Admission status for one numeric evidence record."""

    ADMITTED = "admitted"
    ADMITTED_WITH_WARNING = "admitted_with_warning"
    SKIPPED_BASELINE_NOT_VALIDATABLE = "skipped_baseline_not_validatable"
    SKIPPED_REQUIRED_METRIC_MISSING = "skipped_required_metric_missing"
    EXCLUDED_NON_AUTHORITATIVE = "excluded_non_authoritative"
    REVALIDATION_TRIGGER = "revalidation_trigger"


class NumericAdmissionDecision(BaseModel):
    """Policy decision for one MSIL numeric claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_ref: str = Field(..., min_length=1)
    source_type: SourceType
    authority_class: AuthorityClass
    claim_type: ClaimType
    role: NumericRole
    status: NumericEvidenceStatus
    admitted: bool
    can_be_baseline: bool = Field(
        ..., description="Whether the value may enter historical baseline math."
    )
    hsig_delegated: bool = Field(
        default=False, description="Whether the unchanged HSIG decided admission."
    )
    hsig_status: HistoricalBaselineStatus | None = Field(default=None)
    integrity_verdict: str = Field(..., min_length=1)
    reasons: tuple[str, ...] = Field(default_factory=tuple)
    policy_version: str = Field(default=NUMERIC_ADMISSION_POLICY_VERSION)

    @model_validator(mode="after")
    def _validate_decision(self) -> "NumericAdmissionDecision":
        if self.can_be_baseline:
            if self.role != NumericRole.BASELINE:
                raise ValueError("Only baseline role can be baseline-admissible.")
            if not self.hsig_delegated:
                raise ValueError("Baseline-admissible values must delegate to HSIG.")
            if self.status not in {
                NumericEvidenceStatus.ADMITTED,
                NumericEvidenceStatus.ADMITTED_WITH_WARNING,
            }:
                raise ValueError("Baseline-admissible values must be admitted.")
        if self.role == NumericRole.NON_AUTHORITATIVE and self.admitted:
            raise ValueError("Non-authoritative numeric evidence cannot be admitted.")
        return self


class NumericEvidence(BaseModel):
    """FVE-owned numeric envelope admitted or excluded by the NAG."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str | None = Field(default=None)
    signal_ref: str = Field(..., min_length=1)
    value: float | int | str = Field(..., description="Numeric value as supplied.")
    metric: str = Field(..., min_length=1)
    period: str = Field(..., min_length=1)
    value_year: int | None = Field(default=None, ge=1900)
    source_report_year: int | None = Field(default=None, ge=1900)
    authority: AuthorityClass
    source_type: SourceType
    claim_type: ClaimType
    provenance: IntelligenceSignalProvenance
    role: NumericRole
    status: NumericEvidenceStatus
    admitted: bool
    can_be_baseline: bool
    integrity_verdict: str = Field(..., min_length=1)
    hsig_status: HistoricalBaselineStatus | None = Field(default=None)
    divergence_refs: tuple[str, ...] = Field(default_factory=tuple)
    supersession_refs: tuple[str, ...] = Field(default_factory=tuple)
    admission_decision: NumericAdmissionDecision
    metadata: dict[str, Any] = Field(default_factory=dict)
    policy_version: str = Field(default=NUMERIC_ADMISSION_POLICY_VERSION)

    @model_validator(mode="after")
    def _validate_evidence(self) -> "NumericEvidence":
        if self.admission_decision.signal_ref != self.signal_ref:
            raise ValueError("admission_decision.signal_ref must match signal_ref.")
        if self.admission_decision.role != self.role:
            raise ValueError("admission_decision.role must match role.")
        if self.admission_decision.status != self.status:
            raise ValueError("admission_decision.status must match status.")
        if self.admission_decision.can_be_baseline != self.can_be_baseline:
            raise ValueError("admission_decision.can_be_baseline must match.")

        expected_id = generate_numeric_evidence_id(self)
        if self.evidence_id is not None and self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match deterministic derivation.")
        object.__setattr__(self, "evidence_id", expected_id)
        return self


class NumericAdmissionGateResult(BaseModel):
    """Numeric Admission Gate output for one batch of MSIL numeric claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = Field(default=NUMERIC_ADMISSION_POLICY_VERSION)
    numeric_claims_processed: int = Field(..., ge=0)
    decisions: tuple[NumericAdmissionDecision, ...] = Field(default_factory=tuple)
    evidence: tuple[NumericEvidence, ...] = Field(default_factory=tuple)
    ignored_non_numeric_signals: int = Field(default=0, ge=0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_counts(self) -> "NumericAdmissionGateResult":
        if self.numeric_claims_processed != len(self.decisions):
            raise ValueError("numeric_claims_processed must equal decisions count.")
        if len(self.evidence) != len(self.decisions):
            raise ValueError("one NumericEvidence record is required per decision.")
        return self


def generate_numeric_evidence_id(evidence: NumericEvidence) -> str:
    """Generate deterministic numeric evidence id."""

    payload = {
        "signal_ref": evidence.signal_ref,
        "metric": evidence.metric,
        "period": evidence.period,
        "role": evidence.role.value,
        "status": evidence.status.value,
        "policy_version": evidence.policy_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "ne_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "NUMERIC_ADMISSION_POLICY_VERSION",
    "NumericAdmissionDecision",
    "NumericAdmissionGateResult",
    "NumericEvidence",
    "NumericEvidenceStatus",
    "NumericRole",
    "generate_numeric_evidence_id",
]
