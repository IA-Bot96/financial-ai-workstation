"""Metric-resolution models for Query Engine canonical metric lookup."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MetricMatchType = Literal["exact", "alias", "canonical", "fuzzy"]


class MetricResolutionCandidate(BaseModel):
    """One canonical metric candidate for a user-facing metric query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_metric: str = Field(..., min_length=1)
    display_name: str | None = Field(default=None)
    category: str | None = Field(default=None)
    match_type: MetricMatchType = Field(..., description="How the candidate matched.")
    confidence: float = Field(..., ge=0, le=1)
    matched_term: str = Field(..., min_length=1)
    available_in_dataset: bool = Field(
        ..., description="Whether the knowledge base has financial records for it."
    )
    financial_record_count: int = Field(..., ge=0)


class MetricResolutionResult(BaseModel):
    """Resolution result for one user-facing metric query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_metric: str = Field(..., min_length=1)
    normalized_query: str = Field(..., min_length=1)
    resolved_metric: str | None = Field(
        default=None, description="Best canonical metric selected for retrieval."
    )
    found: bool = Field(..., description="Whether any candidate was found.")
    is_ambiguous: bool = Field(
        ..., description="Whether multiple high-confidence candidates remain."
    )
    requires_clarification: bool = Field(
        ..., description="Whether the query should ask the user to clarify."
    )
    best_candidate: MetricResolutionCandidate | None = Field(default=None)
    candidates: tuple[MetricResolutionCandidate, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)


__all__ = [
    "MetricMatchType",
    "MetricResolutionCandidate",
    "MetricResolutionResult",
]
