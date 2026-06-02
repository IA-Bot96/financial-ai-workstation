"""Deterministic query-planning models for the Financial Query Engine."""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from query_engine.models.metric_resolution import MetricResolutionResult
from shared.models.financial_year_consolidation import StatementScope


class QueryIntent(str, Enum):
    """Supported deterministic query intents."""

    METRIC_VALUE = "METRIC_VALUE"
    METRIC_HISTORY = "METRIC_HISTORY"
    METRIC_GROWTH = "METRIC_GROWTH"
    CAGR = "CAGR"
    COMPOUND_ANNUAL_GROWTH_RATE = "COMPOUND_ANNUAL_GROWTH_RATE"
    METRIC_COMPARISON = "METRIC_COMPARISON"
    CONFLICT_EXPLANATION = "CONFLICT_EXPLANATION"
    PROVENANCE_LOOKUP = "PROVENANCE_LOOKUP"


class QueryRequest(BaseModel):
    """Raw and normalized query fields consumed by the deterministic planner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_query: str = Field(..., min_length=1)
    normalized_query: str | None = Field(default=None)
    requested_metric: str | None = Field(default=None)
    requested_year: int | None = Field(default=None, ge=1900)
    start_year: int | None = Field(default=None, ge=1900)
    end_year: int | None = Field(default=None, ge=1900)
    comparison_metric: str | None = Field(default=None)
    intent: QueryIntent | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _fill_normalized_query(cls, data: object) -> object:
        """Populate normalized_query from raw_query when callers omit it."""

        if not isinstance(data, dict):
            return data
        if data.get("normalized_query"):
            return data
        raw_query = str(data.get("raw_query", ""))
        data = dict(data)
        data["normalized_query"] = normalize_query(raw_query)
        return data


class QueryPlan(BaseModel):
    """Base deterministic query plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_type: str = Field(..., min_length=1)
    intent: QueryIntent | None = Field(default=None)
    raw_query: str = Field(..., min_length=1)
    normalized_query: str = Field(..., min_length=1)
    requested_metric: str | None = Field(default=None)
    requested_year: int | None = Field(default=None, ge=1900)
    start_year: int | None = Field(default=None, ge=1900)
    end_year: int | None = Field(default=None, ge=1900)
    comparison_metric: str | None = Field(default=None)
    resolved_metric: str | None = Field(default=None)
    resolved_comparison_metric: str | None = Field(default=None)
    metric_resolution: MetricResolutionResult | None = Field(default=None)
    comparison_metric_resolution: MetricResolutionResult | None = Field(default=None)
    is_valid: bool = Field(..., description="Whether the plan can be executed.")
    requires_clarification: bool = Field(default=False)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)


class MetricValuePlan(QueryPlan):
    """Plan for retrieving one metric value in a specific year."""

    plan_type: Literal["MetricValuePlan"] = "MetricValuePlan"
    intent: Literal[QueryIntent.METRIC_VALUE] = QueryIntent.METRIC_VALUE
    evidence_method: Literal["build_metric_year_evidence"] = "build_metric_year_evidence"


class MetricHistoryPlan(QueryPlan):
    """Plan for retrieving a metric history series."""

    plan_type: Literal["MetricHistoryPlan"] = "MetricHistoryPlan"
    intent: Literal[QueryIntent.METRIC_HISTORY] = QueryIntent.METRIC_HISTORY
    evidence_method: Literal["build_metric_history_evidence"] = "build_metric_history_evidence"


class MetricGrowthPlan(QueryPlan):
    """Plan for a deterministic metric-growth calculation."""

    plan_type: Literal["MetricGrowthPlan"] = "MetricGrowthPlan"
    intent: Literal[QueryIntent.METRIC_GROWTH] = QueryIntent.METRIC_GROWTH
    calculation_type: Literal["year_over_year_growth", "multi_year_series"] = (
        "multi_year_series"
    )
    evidence_method: Literal["build_calculation_evidence"] = "build_calculation_evidence"


class CAGRPlan(QueryPlan):
    """Plan for deterministic compound annual growth rate calculation."""

    plan_type: Literal["CAGRPlan"] = "CAGRPlan"
    intent: Literal[QueryIntent.CAGR, QueryIntent.COMPOUND_ANNUAL_GROWTH_RATE] = (
        QueryIntent.CAGR
    )
    calculation_type: Literal["cagr"] = "cagr"
    evidence_method: Literal["build_calculation_evidence"] = "build_calculation_evidence"


class MetricComparisonPlan(QueryPlan):
    """Plan for comparing two resolved financial metrics."""

    plan_type: Literal["MetricComparisonPlan"] = "MetricComparisonPlan"
    intent: Literal[QueryIntent.METRIC_COMPARISON] = QueryIntent.METRIC_COMPARISON
    left_evidence_method: Literal["build_metric_evidence"] = "build_metric_evidence"
    right_evidence_method: Literal["build_metric_evidence"] = "build_metric_evidence"


class ConflictPlan(QueryPlan):
    """Plan for exposing conflict candidates for a metric."""

    plan_type: Literal["ConflictPlan"] = "ConflictPlan"
    intent: Literal[QueryIntent.CONFLICT_EXPLANATION] = QueryIntent.CONFLICT_EXPLANATION
    retrieval_method: Literal["retrieve_metric_candidates"] = "retrieve_metric_candidates"
    conflict_count: int = Field(default=0, ge=0)


class ProvenancePlan(QueryPlan):
    """Plan for explaining metric selection and citations."""

    plan_type: Literal["ProvenancePlan"] = "ProvenancePlan"
    intent: Literal[QueryIntent.PROVENANCE_LOOKUP] = QueryIntent.PROVENANCE_LOOKUP
    evidence_method: Literal["build_metric_evidence"] = "build_metric_evidence"


class UnsupportedPlan(QueryPlan):
    """Invalid plan returned when deterministic intent extraction fails."""

    plan_type: Literal["UnsupportedPlan"] = "UnsupportedPlan"


def normalize_query(value: str) -> str:
    """Normalize a raw user query into lowercase token text."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


__all__ = [
    "CAGRPlan",
    "ConflictPlan",
    "MetricComparisonPlan",
    "MetricGrowthPlan",
    "MetricHistoryPlan",
    "MetricValuePlan",
    "ProvenancePlan",
    "QueryIntent",
    "QueryPlan",
    "QueryRequest",
    "UnsupportedPlan",
    "normalize_query",
]
