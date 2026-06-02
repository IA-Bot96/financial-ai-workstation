"""Deterministic response models for the Financial Query Engine."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.evidence import EvidenceCitation, EvidenceConflict
from query_engine.models.query_planner import QueryIntent


class QueryResponseType(str, Enum):
    """Supported deterministic response types."""

    METRIC_VALUE = "metric_value"
    METRIC_HISTORY = "metric_history"
    METRIC_GROWTH = "metric_growth"
    CAGR = "cagr"
    METRIC_COMPARISON = "metric_comparison"
    CONFLICT = "conflict"
    PROVENANCE = "provenance"


class QueryResponse(BaseModel):
    """Base response returned by deterministic response rendering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_type: QueryResponseType
    raw_query: str = Field(..., min_length=1)
    intent: QueryIntent | None = Field(default=None)
    metrics: tuple[str, ...] = Field(default_factory=tuple)
    values: tuple[float | int | str, ...] = Field(default_factory=tuple)
    years: tuple[int, ...] = Field(default_factory=tuple)
    confidence: float = Field(..., ge=0, le=1)
    is_ambiguous: bool
    has_conflicts: bool
    citations: tuple[EvidenceCitation, ...] = Field(default_factory=tuple)
    provenance_references: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    conflicts: tuple[EvidenceConflict, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)
    is_answerable: bool = Field(..., description="Whether response contains usable data.")


class MetricValueResponse(QueryResponse):
    """Response for one metric value in one year."""

    answer_type: Literal[QueryResponseType.METRIC_VALUE] = QueryResponseType.METRIC_VALUE
    metric: str | None = Field(default=None)
    year: int | None = Field(default=None, ge=1900)
    value: float | int | str | None = Field(default=None)


class MetricHistoryResponse(QueryResponse):
    """Response for a metric's historical value series."""

    answer_type: Literal[QueryResponseType.METRIC_HISTORY] = QueryResponseType.METRIC_HISTORY
    metric: str | None = Field(default=None)
    series: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class MetricGrowthResponse(QueryResponse):
    """Response for deterministic growth or trend calculations."""

    answer_type: Literal[QueryResponseType.METRIC_GROWTH] = QueryResponseType.METRIC_GROWTH
    metric: str | None = Field(default=None)
    calculation_type: str | None = Field(default=None)
    result_value: float | int | str | None = Field(default=None)
    result_unit: str | None = Field(default=None)
    supporting_values: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class CAGRResponse(QueryResponse):
    """Response for deterministic compound annual growth rate calculations."""

    answer_type: Literal[QueryResponseType.CAGR] = QueryResponseType.CAGR
    metric: str | None = Field(default=None)
    cagr_value: float | int | str | None = Field(default=None)
    result_unit: str | None = Field(default=None)
    start_year: int | None = Field(default=None, ge=1900)
    end_year: int | None = Field(default=None, ge=1900)
    source_values: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class MetricComparisonResponse(QueryResponse):
    """Response for comparing two financial metrics."""

    answer_type: Literal[QueryResponseType.METRIC_COMPARISON] = (
        QueryResponseType.METRIC_COMPARISON
    )
    left_metric: str | None = Field(default=None)
    right_metric: str | None = Field(default=None)
    left_values: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    right_values: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class ConflictResponse(QueryResponse):
    """Response exposing unresolved or resolved conflict groups."""

    answer_type: Literal[QueryResponseType.CONFLICT] = QueryResponseType.CONFLICT
    metric: str | None = Field(default=None)
    conflict_count: int = Field(default=0, ge=0)
    conflict_details: tuple[EvidenceConflict, ...] = Field(default_factory=tuple)


class ProvenanceResponse(QueryResponse):
    """Response explaining selected values, competing values, and sources."""

    answer_type: Literal[QueryResponseType.PROVENANCE] = QueryResponseType.PROVENANCE
    metric: str | None = Field(default=None)
    selected_value: float | int | str | None = Field(default=None)
    selected_year: int | None = Field(default=None, ge=1900)
    competing_values: tuple[float | int | str, ...] = Field(default_factory=tuple)
    resolution_reason: str | None = Field(default=None)
    source_page: int | None = Field(default=None, gt=0)
    source_type: str | None = Field(default=None)


__all__ = [
    "CAGRResponse",
    "ConflictResponse",
    "MetricComparisonResponse",
    "MetricGrowthResponse",
    "MetricHistoryResponse",
    "MetricValueResponse",
    "ProvenanceResponse",
    "QueryResponse",
    "QueryResponseType",
]
