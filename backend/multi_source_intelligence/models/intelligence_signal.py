"""MSIL Phase 2 IntelligenceSignal envelope models."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    AuthorityClass,
    ClaimType,
    ContentClass,
    EntityScope,
    EventType,
    Horizon,
    ProvenanceType,
    ReviewStatus,
    SourceType,
    TimeBasis,
)
from .entity_resolution import EntityResolutionResult
from .signal_provenance import IntelligenceSignalProvenance
from .snapshots import SnapshotMetadata
from .versioning import MSILVersionPins, default_version_pins


class IntelligenceSignalContent(BaseModel):
    """Class-specific signal content with stable non-text identity hooks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content_class: ContentClass
    identity_key: str | None = Field(
        default=None,
        description="Stable non-text adapter key used for deterministic signal identity.",
    )
    claim_text: str | None = Field(default=None)
    normalized_claim_text: str | None = Field(default=None)
    metric_ref: str | None = Field(default=None)
    value: float | int | str | None = Field(default=None)
    unit: str | None = Field(default=None)
    event_type: EventType | None = Field(default=None)
    market_series_ref: str | None = Field(default=None)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_content_for_class(self) -> "IntelligenceSignalContent":
        """Require the minimum contract fields for each content class."""

        if self.content_class == ContentClass.NUMERIC_CLAIM:
            if not self.metric_ref:
                raise ValueError("numeric_claim content requires metric_ref.")
            if self.value is None:
                raise ValueError("numeric_claim content requires value.")
        elif self.content_class == ContentClass.NARRATIVE_CLAIM:
            if not self.claim_text:
                raise ValueError("narrative_claim content requires claim_text.")
            if not self.identity_key:
                raise ValueError(
                    "narrative_claim content requires text-independent identity_key."
                )
        elif self.content_class == ContentClass.CORPORATE_EVENT:
            if self.event_type is None:
                raise ValueError("corporate_event content requires event_type.")
        elif self.content_class == ContentClass.MARKET_OBSERVATION:
            if not self.market_series_ref:
                raise ValueError("market_observation content requires market_series_ref.")
            if self.value is None:
                raise ValueError("market_observation content requires value.")
        return self

    def identity_component(self) -> dict[str, Any]:
        """Return the text-independent content portion used in signal_id generation."""

        return {
            "content_class": self.content_class.value,
            "identity_key": self.identity_key,
            "metric_ref": self.metric_ref,
            "unit": self.unit,
            "event_type": self.event_type.value if self.event_type else None,
            "market_series_ref": self.market_series_ref,
        }


class IntelligenceSignalClassification(BaseModel):
    """MSIL-owned routing and authority classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content_class: ContentClass
    source_type: SourceType
    claim_type: ClaimType
    authority_class: AuthorityClass
    creation_eligible: bool = Field(
        default=True,
        description="Whether this source/claim may create standalone evidence.",
    )
    mapping_confidence: float = Field(default=1.0, ge=0, le=1)
    authority_confidence: float = Field(default=1.0, ge=0, le=1)
    independence_metadata: dict[str, Any] = Field(default_factory=dict)


class IntelligenceSignalMetadata(BaseModel):
    """Temporal, lineage, and trust metadata for a signal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_time: datetime
    subject_period: str | None = Field(default=None)
    time_basis: TimeBasis
    horizon: Horizon
    source_independent_of_issuer: bool
    verified: bool
    source_lineage: tuple[str, ...] = Field(default_factory=tuple)
    trust_prior: float = Field(default=1.0, ge=0, le=1)
    source_record_id: str | None = Field(
        default=None,
        description="Stable adapter/source record id; never derived from claim text.",
    )
    source_lineage_hooks: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("observation_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        """Observation time must be unambiguous."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation_time must be timezone-aware.")
        return value


class IntelligenceSignal(BaseModel):
    """Common evidence envelope for all future MSIL adapters."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "signal_id": "sig_...",
                    "entity_ref": "lucky_cement",
                    "entity_scope": "company",
                    "content": {"content_class": "narrative_claim"},
                    "classification": {
                        "content_class": "narrative_claim",
                        "source_type": "annual_report",
                        "claim_type": "descriptive",
                        "authority_class": "audited_issuer",
                    },
                    "provenance": {"provenance_type": "PDF_PAGE"},
                }
            ]
        },
    )

    signal_id: str | None = Field(
        default=None,
        description="Derived deterministic id. Supplied ids must match derivation.",
    )
    entity_ref: str = Field(..., min_length=1)
    entity_scope: EntityScope
    entity_resolution: EntityResolutionResult
    content: IntelligenceSignalContent
    classification: IntelligenceSignalClassification
    metadata: IntelligenceSignalMetadata
    provenance: IntelligenceSignalProvenance
    snapshot_metadata: SnapshotMetadata | None = Field(default=None)
    supersedes: str | None = Field(default=None)
    superseded_by: str | None = Field(default=None)
    corroboration_group: str | None = Field(default=None)
    divergence_refs: tuple[str, ...] = Field(default_factory=tuple)
    version_pins: MSILVersionPins = Field(default_factory=default_version_pins)

    @model_validator(mode="after")
    def _validate_signal(self) -> "IntelligenceSignal":
        """Enforce Phase 2 envelope invariants."""

        if self.provenance.provenance_type == ProvenanceType.NONE:
            raise ValueError("NONE provenance is forbidden for IntelligenceSignal.")
        if self.entity_resolution.review_status != ReviewStatus.RESOLVED:
            raise ValueError("IntelligenceSignal requires resolved entity_resolution.")
        if self.entity_resolution.resolved_entity_ref != self.entity_ref:
            raise ValueError("entity_ref must match entity_resolution.resolved_entity_ref.")
        if self.content.content_class != self.classification.content_class:
            raise ValueError("content.content_class must match classification.content_class.")
        if self.provenance.source_type != self.classification.source_type:
            raise ValueError("provenance source_type must match classification.source_type.")
        self._validate_snapshot_consistency()

        expected_signal_id = generate_signal_id(self)
        if self.signal_id is not None and self.signal_id != expected_signal_id:
            raise ValueError("signal_id does not match deterministic derivation.")
        object.__setattr__(self, "signal_id", expected_signal_id)
        return self

    def _validate_snapshot_consistency(self) -> None:
        snapshot_ref = getattr(self.provenance, "snapshot_ref", None)
        if snapshot_ref is None:
            return
        if snapshot_ref.source_type != self.provenance.source_type:
            raise ValueError("snapshot_ref.source_type must match provenance.source_type.")
        if self.snapshot_metadata is not None:
            metadata_ref = self.snapshot_metadata.snapshot_ref
            if metadata_ref.snapshot_id != snapshot_ref.snapshot_id:
                raise ValueError("snapshot_metadata must describe provenance.snapshot_ref.")


def generate_signal_id(signal: IntelligenceSignal) -> str:
    """Generate a deterministic text-independent signal identifier."""

    provenance_payload = signal.provenance.model_dump(
        mode="json",
        exclude={"retrieved_at", "verified", "source_lineage"},
    )
    identity_payload = {
        "entity_ref": signal.entity_ref,
        "entity_scope": signal.entity_scope.value,
        "entity_resolution_method": signal.entity_resolution.method.value,
        "resolved_security_ref": signal.entity_resolution.resolved_security_ref,
        "content": signal.content.identity_component(),
        "classification": {
            "source_type": signal.classification.source_type.value,
            "claim_type": signal.classification.claim_type.value,
            "authority_class": signal.classification.authority_class.value,
            "content_class": signal.classification.content_class.value,
        },
        "time": {
            "observation_time": signal.metadata.observation_time.isoformat(),
            "subject_period": signal.metadata.subject_period,
            "time_basis": signal.metadata.time_basis.value,
            "horizon": signal.metadata.horizon.value,
        },
        "source_record_id": signal.metadata.source_record_id,
        "provenance": provenance_payload,
        "version_pins": {
            "msil_schema_version": signal.version_pins.msil_schema_version,
            "authority_matrix_version": signal.version_pins.authority_matrix_version,
            "entity_registry_version": signal.version_pins.entity_registry_version,
            "provenance_schema_version": signal.version_pins.provenance_schema_version,
        },
    }
    encoded = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
    return f"sig_{digest}"


__all__ = [
    "IntelligenceSignal",
    "IntelligenceSignalClassification",
    "IntelligenceSignalContent",
    "IntelligenceSignalMetadata",
    "generate_signal_id",
]
