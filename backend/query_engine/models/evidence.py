"""Evidence bundle models for deterministic Query Engine answer support."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.metric_resolution import MetricResolutionResult
from shared.models.financial_year_consolidation import StatementScope

EvidenceBundleType = Literal["metric", "metric_year", "metric_history", "calculation"]


class EvidenceCitation(BaseModel):
    """Workbook and source citation attached to an evidence item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_status: str = Field(..., min_length=1)
    sheet_name: str | None = Field(default=None)
    row: int | None = Field(default=None, gt=0)
    column: int | None = Field(default=None, gt=0)
    cell_reference: str | None = Field(default=None)
    source_report_year: int | None = Field(default=None, ge=1900)
    page_number: int | None = Field(default=None, gt=0)
    table_type: str | None = Field(default=None)


class EvidenceMetric(BaseModel):
    """One selected financial metric value with retrieval provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    canonical_metric: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    value: float | int | str
    numeric_value: float | None = Field(default=None)
    source_report_year: int = Field(..., ge=1900)
    page_number: int = Field(..., gt=0)
    table_type: str = Field(..., min_length=1)
    statement_scope: StatementScope
    confidence: float = Field(..., ge=0, le=1)
    source_metric: str | None = Field(default=None)
    conflict_status: str = Field(..., min_length=1)
    unresolved_conflict: bool = Field(default=False)
    requires_review: bool = Field(default=False)
    citation: EvidenceCitation
    provenance: dict[str, Any] = Field(default_factory=dict)


class EvidenceSeries(BaseModel):
    """Ordered metric evidence series for history and calculations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_metric: str = Field(..., min_length=1)
    resolved_metric: str | None = Field(default=None)
    points: tuple[EvidenceMetric, ...] = Field(default_factory=tuple)


class EvidenceConflict(BaseModel):
    """Conflict metadata propagated into evidence bundles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conflict_group_id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    conflict_status: str = Field(..., min_length=1)
    unresolved_conflict: bool
    candidate_count: int = Field(..., gt=1)
    selected_candidate_id: str = Field(..., min_length=1)
    resolution_reason: str = Field(..., min_length=1)
    candidate_values: tuple[float | int | str, ...] = Field(default_factory=tuple)


class EvidenceInsightReference(BaseModel):
    """Insight reference available to future mixed financial/narrative answers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    insight_id: str = Field(..., min_length=1)
    area: str = Field(..., min_length=1)
    takeaway: str = Field(..., min_length=1)
    source_section: str = Field(..., min_length=1)
    page_number: int = Field(..., gt=0)
    confidence: float = Field(..., ge=0, le=1)


class EvidenceBundle(BaseModel):
    """Complete deterministic evidence package for one query-engine operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_type: EvidenceBundleType
    query_metric: str = Field(..., min_length=1)
    resolved_metric: str | None = Field(default=None)
    resolution_confidence: float = Field(default=0.0, ge=0, le=1)
    metric_resolution: MetricResolutionResult | None = Field(default=None)
    metrics: tuple[EvidenceMetric, ...] = Field(default_factory=tuple)
    series: EvidenceSeries | None = Field(default=None)
    calculation: dict[str, Any] = Field(default_factory=dict)
    conflicts: tuple[EvidenceConflict, ...] = Field(default_factory=tuple)
    citations: tuple[EvidenceCitation, ...] = Field(default_factory=tuple)
    insight_references: tuple[EvidenceInsightReference, ...] = Field(default_factory=tuple)
    has_unresolved_conflicts: bool = Field(default=False)
    is_ambiguous: bool = Field(default=False)
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence_complete: bool = Field(default=False)
    citation_complete: bool = Field(default=False)
    provenance_consistent: bool = Field(default=False)
    validation_errors: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)


__all__ = [
    "EvidenceBundle",
    "EvidenceBundleType",
    "EvidenceCitation",
    "EvidenceConflict",
    "EvidenceInsightReference",
    "EvidenceMetric",
    "EvidenceSeries",
]
