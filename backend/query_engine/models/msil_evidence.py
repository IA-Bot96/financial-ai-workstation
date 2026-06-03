"""Query-facing views over MSIL evidence.

These models intentionally mirror only consumable MSIL facts. Query Engine may
display and cite MSIL evidence, but it does not own entity resolution,
authority assignment, timeline assembly, corroboration, or divergence.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueryMSILCitation(BaseModel):
    """Citation derived directly from MSIL provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    citation_status: Literal["provenance_attached"] = "provenance_attached"
    verified: bool = True
    workbook_fingerprint: str | None = Field(default=None)
    page_number: int | None = Field(default=None, ge=1)
    report_reference: str | None = Field(default=None)
    source_report_year: int | None = Field(default=None, ge=1900)
    source_section: str | None = Field(default=None)
    cell_reference: str | None = Field(default=None)
    snapshot_id: str | None = Field(default=None)
    url: str | None = Field(default=None)
    retrieved_at: str | None = Field(default=None)
    source_lineage: tuple[str, ...] = Field(default_factory=tuple)
    locator: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_real_provenance(self) -> "QueryMSILCitation":
        if self.provenance_type == "NONE":
            raise ValueError("QueryMSILCitation cannot be built from NONE provenance.")
        if not self.locator:
            raise ValueError("QueryMSILCitation requires a provenance locator.")
        return self


class QueryMSILAuthority(BaseModel):
    """MSIL authority metadata exposed to Query as display-only data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: str = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    claim_type: str = Field(..., min_length=1)
    creation_eligible: bool
    mapping_confidence: float = Field(..., ge=0, le=1)
    authority_confidence: float = Field(..., ge=0, le=1)
    independence_metadata: dict[str, Any] = Field(default_factory=dict)


class QueryMSILTimelineReference(BaseModel):
    """Timeline/event reference assembled by MSIL and surfaced by Query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(..., min_length=1)
    entry_id: str | None = Field(default=None)
    entity_ref: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    event_time: str = Field(..., min_length=1)
    time_basis: str = Field(..., min_length=1)
    source_signal_refs: tuple[str, ...] = Field(default_factory=tuple)
    authority_class: str = Field(..., min_length=1)
    claim_type: str = Field(..., min_length=1)
    current_flag: bool | None = Field(default=None)
    superseded_by: str | None = Field(default=None)
    supersedes: tuple[str, ...] = Field(default_factory=tuple)


class QueryMSILDivergenceReference(BaseModel):
    """Divergence surfaced by MSIL. Query never resolves it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    divergence_id: str = Field(..., min_length=1)
    divergence_type: str | None = Field(default=None)
    status: str = Field(default="surfaced", min_length=1)
    entity_ref: str | None = Field(default=None)
    subject: str | None = Field(default=None)
    signal_refs: tuple[str, ...] = Field(default_factory=tuple)
    authority_classes: tuple[str, ...] = Field(default_factory=tuple)
    source_types: tuple[str, ...] = Field(default_factory=tuple)
    chronology_comparison: str | None = Field(default=None)
    authority_weighting: dict[str, Any] = Field(default_factory=dict)
    query_resolution_policy: Literal["surface_only"] = "surface_only"


class QueryMSILEvidence(BaseModel):
    """One IntelligenceSignal converted into a Query-consumable evidence record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(..., min_length=1)
    signal_ref: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    entity_scope: str = Field(..., min_length=1)
    content_class: str = Field(..., min_length=1)
    claim_text: str | None = Field(default=None)
    normalized_claim_text: str | None = Field(default=None)
    metric_ref: str | None = Field(default=None)
    value: float | int | str | None = Field(default=None)
    unit: str | None = Field(default=None)
    event_type: str | None = Field(default=None)
    source_report_year: int | None = Field(default=None, ge=1900)
    value_year: int | None = Field(default=None, ge=1900)
    source_section: str | None = Field(default=None)
    review_status: str | None = Field(default=None)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    observation_time: str = Field(..., min_length=1)
    subject_period: str | None = Field(default=None)
    time_basis: str = Field(..., min_length=1)
    horizon: str = Field(..., min_length=1)
    source_record_id: str | None = Field(default=None)
    authority: QueryMSILAuthority
    citations: tuple[QueryMSILCitation, ...] = Field(..., min_length=1)
    timeline_refs: tuple[QueryMSILTimelineReference, ...] = Field(default_factory=tuple)
    divergence_refs: tuple[QueryMSILDivergenceReference, ...] = Field(
        default_factory=tuple
    )
    provenance_payload: dict[str, Any] = Field(default_factory=dict)
    source_payload: dict[str, Any] = Field(default_factory=dict)
    version_pins: dict[str, Any] = Field(default_factory=dict)


class QueryMSILEvidenceCollection(BaseModel):
    """Immutable collection returned by the Query MSIL evidence adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: tuple[QueryMSILEvidence, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    ownership_boundaries: dict[str, bool] = Field(default_factory=dict)

    @property
    def by_signal_ref(self) -> dict[str, QueryMSILEvidence]:
        """Return evidence keyed by signal id."""

        return {item.signal_ref: item for item in self.evidence}


class QueryMSILEvidenceRetrievalResult(BaseModel):
    """Result for Query-facing MSIL evidence retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    found: bool
    evidence: tuple[QueryMSILEvidence, ...] = Field(default_factory=tuple)
    citations: tuple[QueryMSILCitation, ...] = Field(default_factory=tuple)
    authorities: tuple[QueryMSILAuthority, ...] = Field(default_factory=tuple)
    divergence_refs: tuple[QueryMSILDivergenceReference, ...] = Field(
        default_factory=tuple
    )
    warnings: tuple[str, ...] = Field(default_factory=tuple)


__all__ = [
    "QueryMSILAuthority",
    "QueryMSILCitation",
    "QueryMSILDivergenceReference",
    "QueryMSILEvidence",
    "QueryMSILEvidenceCollection",
    "QueryMSILEvidenceRetrievalResult",
    "QueryMSILTimelineReference",
]
