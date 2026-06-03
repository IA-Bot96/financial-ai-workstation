"""Corroboration and divergence models for MSIL Phase 7."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    AuthorityClass,
    ClaimType,
    ContentClass,
    DivergenceStatus,
    DivergenceType,
    EventType,
    SourceType,
    TimeBasis,
)
from .versioning import MSILVersionPins, default_version_pins


class EvidenceComparisonReason(str, Enum):
    """Deterministic reason for accepted/rejected evidence comparison."""

    INDEPENDENT_ORIGIN = "independent_origin"
    DUPLICATE_SIGNAL = "duplicate_signal"
    SAME_SOURCE_REPLAY = "same_source_replay"
    SAME_AUTHORITY_CLASS = "same_authority_class"
    LINEAGE_LINKED = "lineage_linked"
    INCOMPATIBLE_ENTITY = "incompatible_entity"
    INCOMPATIBLE_SUBJECT = "incompatible_subject"
    INCOMPATIBLE_CLAIM_OR_EVENT_TYPE = "incompatible_claim_or_event_type"
    INCOMPATIBLE_TIMELINE_CONTEXT = "incompatible_timeline_context"
    NO_MATERIAL_CONFLICT = "no_material_conflict"
    MISSING_ASSERTION_VALUE = "missing_assertion_value"


class CorroborationReference(BaseModel):
    """One source member considered for corroboration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_ref: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    content_class: ContentClass
    source_type: SourceType
    authority_class: AuthorityClass
    claim_type: ClaimType
    event_type: EventType | None = Field(default=None)
    observation_time: datetime
    subject_period: str | None = Field(default=None)
    time_basis: TimeBasis
    provenance_ref: str = Field(..., min_length=1)
    source_lineage: tuple[str, ...] = Field(default_factory=tuple)
    derived_from: tuple[str, ...] = Field(default_factory=tuple)
    re_reported_from: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("observation_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation_time must be timezone-aware.")
        return value


class CorroborationGroup(BaseModel):
    """Independent-origin agreement group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    corroboration_group_id: str | None = Field(default=None)
    entity_ref: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    claim_type: ClaimType
    event_type: EventType | None = Field(default=None)
    member_signal_refs: tuple[str, ...] = Field(..., min_length=2)
    member_references: tuple[CorroborationReference, ...] = Field(..., min_length=2)
    independent_origin_count: int = Field(..., ge=2)
    authority_classes_present: tuple[AuthorityClass, ...] = Field(..., min_length=2)
    lineage_checked: bool = Field(default=True)
    is_circular: bool = Field(default=False)
    strength: float = Field(..., ge=0, le=1)
    version_pins: MSILVersionPins = Field(default_factory=default_version_pins)

    @model_validator(mode="after")
    def _validate_group(self) -> "CorroborationGroup":
        if not self.lineage_checked:
            raise ValueError("CorroborationGroup requires lineage_checked=True.")
        if self.is_circular:
            raise ValueError("Circular evidence cannot become a CorroborationGroup.")
        if len(set(self.member_signal_refs)) != len(self.member_signal_refs):
            raise ValueError("member_signal_refs cannot contain duplicates.")
        if len(self.member_references) != len(self.member_signal_refs):
            raise ValueError("member_references must align to member_signal_refs.")
        if any(ref.entity_ref != self.entity_ref for ref in self.member_references):
            raise ValueError("All corroboration members must match entity_ref.")
        if any(ref.subject != self.subject for ref in self.member_references):
            raise ValueError("All corroboration members must match subject.")
        if any(ref.claim_type != self.claim_type for ref in self.member_references):
            raise ValueError("All corroboration members must match claim_type.")
        if len(set(self.authority_classes_present)) != len(
            self.authority_classes_present
        ):
            raise ValueError("authority_classes_present must be unique.")
        if self.independent_origin_count != len(self.authority_classes_present):
            raise ValueError("independent_origin_count must equal authority classes.")

        expected_id = generate_corroboration_group_id(self)
        if self.corroboration_group_id is not None and self.corroboration_group_id != expected_id:
            raise ValueError(
                "corroboration_group_id does not match deterministic derivation."
            )
        object.__setattr__(self, "corroboration_group_id", expected_id)
        return self


class CorroborationCandidateDiagnostic(BaseModel):
    """Rejected or unresolved corroboration candidate pair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_ref_a: str = Field(..., min_length=1)
    signal_ref_b: str = Field(..., min_length=1)
    reason: EvidenceComparisonReason
    details: str = Field(..., min_length=1)
    circular: bool = Field(default=False)


class CorroborationResult(BaseModel):
    """Corroboration groups plus rejected candidate diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    groups: tuple[CorroborationGroup, ...] = Field(default_factory=tuple)
    rejected_candidates: tuple[CorroborationCandidateDiagnostic, ...] = Field(
        default_factory=tuple
    )
    candidates_evaluated: int = Field(..., ge=0)
    lineage_checks_performed: int = Field(..., ge=0)
    circularity_rejections: int = Field(..., ge=0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class DivergenceReference(BaseModel):
    """One side of a surfaced divergence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_ref: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    claim_summary: str = Field(..., min_length=1)
    assertion_value: str = Field(..., min_length=1)
    content_class: ContentClass
    source_type: SourceType
    authority_class: AuthorityClass
    claim_type: ClaimType
    event_type: EventType | None = Field(default=None)
    observation_time: datetime
    subject_period: str | None = Field(default=None)
    time_basis: TimeBasis
    provenance_ref: str = Field(..., min_length=1)

    @field_validator("observation_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation_time must be timezone-aware.")
        return value


class Divergence(BaseModel):
    """Cross-source disagreement surfaced by MSIL, never resolved by MSIL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    divergence_id: str | None = Field(default=None)
    entity_ref: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    divergence_type: DivergenceType
    side_a: DivergenceReference
    side_b: DivergenceReference
    authority_weighting: dict[str, Any] = Field(..., min_length=1)
    chronology_comparison: str = Field(..., min_length=1)
    status: Literal[DivergenceStatus.SURFACED] = DivergenceStatus.SURFACED
    detected_by: Literal["msil"] = "msil"
    pending_corroboration: bool = Field(default=False)
    version_pins: MSILVersionPins = Field(default_factory=default_version_pins)

    @model_validator(mode="after")
    def _validate_divergence(self) -> "Divergence":
        if self.side_a.entity_ref != self.entity_ref or self.side_b.entity_ref != self.entity_ref:
            raise ValueError("Divergence sides must match entity_ref.")
        if self.side_a.subject != self.subject or self.side_b.subject != self.subject:
            raise ValueError("Divergence sides must match subject.")
        if self.side_a.signal_ref == self.side_b.signal_ref:
            raise ValueError("Divergence cannot compare the same signal twice.")

        expected_id = generate_divergence_id(self)
        if self.divergence_id is not None and self.divergence_id != expected_id:
            raise ValueError("divergence_id does not match deterministic derivation.")
        object.__setattr__(self, "divergence_id", expected_id)
        return self


class DivergenceCandidateDiagnostic(BaseModel):
    """Rejected or unresolved divergence candidate pair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_ref_a: str = Field(..., min_length=1)
    signal_ref_b: str = Field(..., min_length=1)
    reason: EvidenceComparisonReason
    details: str = Field(..., min_length=1)


class DivergenceResult(BaseModel):
    """Divergences plus unresolved candidate diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    divergences: tuple[Divergence, ...] = Field(default_factory=tuple)
    unresolved_candidates: tuple[DivergenceCandidateDiagnostic, ...] = Field(
        default_factory=tuple
    )
    candidates_evaluated: int = Field(..., ge=0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


def generate_corroboration_group_id(group: CorroborationGroup) -> str:
    """Generate deterministic corroboration group id."""

    payload = {
        "entity_ref": group.entity_ref,
        "subject": group.subject,
        "claim_type": group.claim_type.value,
        "event_type": group.event_type.value if group.event_type else None,
        "member_signal_refs": sorted(group.member_signal_refs),
        "authority_classes_present": sorted(
            item.value for item in group.authority_classes_present
        ),
        "msil_schema_version": group.version_pins.msil_schema_version,
    }
    return "cor_" + _digest(payload)


def generate_divergence_id(divergence: Divergence) -> str:
    """Generate deterministic divergence id."""

    payload = {
        "entity_ref": divergence.entity_ref,
        "subject": divergence.subject,
        "divergence_type": divergence.divergence_type.value,
        "side_signal_refs": sorted(
            (divergence.side_a.signal_ref, divergence.side_b.signal_ref)
        ),
        "side_assertions": sorted(
            (divergence.side_a.assertion_value, divergence.side_b.assertion_value)
        ),
        "msil_schema_version": divergence.version_pins.msil_schema_version,
    }
    return "div_" + _digest(payload)


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "CorroborationCandidateDiagnostic",
    "CorroborationGroup",
    "CorroborationReference",
    "CorroborationResult",
    "Divergence",
    "DivergenceCandidateDiagnostic",
    "DivergenceReference",
    "DivergenceResult",
    "EvidenceComparisonReason",
    "generate_corroboration_group_id",
    "generate_divergence_id",
]
