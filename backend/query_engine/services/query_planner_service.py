"""Deterministic query planner for the Financial Query Engine."""

from __future__ import annotations

import re

from query_engine.models.metric_resolution import MetricResolutionResult
from query_engine.models.query_planner import (
    CAGRPlan,
    ConflictPlan,
    MetricComparisonPlan,
    MetricGrowthPlan,
    MetricHistoryPlan,
    MetricValuePlan,
    ProvenancePlan,
    QueryIntent,
    QueryPlan,
    QueryRequest,
    UnsupportedPlan,
    normalize_query,
)
from query_engine.services.calculation_service import CalculationService
from query_engine.services.evidence_builder_service import EvidenceBuilderService
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.metric_resolution_service import MetricResolutionService

_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")
_LAST_N_YEARS_PATTERN = re.compile(r"\blast\s+(\d{1,2})\s+years?\b")
_COMPARISON_SPLIT_PATTERN = re.compile(r"\b(?:and|vs|versus|with|to)\b")
_STOPWORD_PATTERN = re.compile(
    r"\b("
    r"what|was|were|is|are|the|a|an|of|for|in|during|as|at|on|by|"
    r"this|that|there|"
    r"to|"
    r"show|me|please|value|values|metric|metrics|financial|financials|"
    r"calculate|cagr|compound|annual|rate|rates|last|years|"
    r"growth|grew|increase|increased|decrease|decreased|decline|declined|"
    r"trend|history|historical|series|over|time|compare|comparison|"
    r"conflict|conflicts|conflicting|competing|candidate|candidates|unresolved|"
    r"why|selected|select|selection|source|provenance|citation|citations|"
    r"where|from|explain|did|does|do|come|came|origin|originate|originated|"
    r"chosen|choose|choosing"
    r")\b"
)


class QueryPlannerService:
    """Create deterministic query plans without executing the final answer flow."""

    def __init__(
        self,
        *,
        metric_resolution_service: MetricResolutionService,
        financial_retrieval_service: FinancialRetrievalService,
        calculation_service: CalculationService,
        evidence_builder_service: EvidenceBuilderService,
    ) -> None:
        """Initialize the planner with deterministic Query Engine services."""

        self._metric_resolution_service = metric_resolution_service
        self._financial_retrieval_service = financial_retrieval_service
        self._calculation_service = calculation_service
        self._evidence_builder_service = evidence_builder_service

    def plan(self, query_request: QueryRequest) -> QueryPlan:
        """Return a deterministic executable plan for a user query request."""

        normalized_query = normalize_query(
            query_request.normalized_query or query_request.raw_query
        )
        intent = query_request.intent or _infer_intent(normalized_query)
        requested_year = query_request.requested_year or _extract_year(normalized_query)
        explicit_start_year, explicit_end_year = _extract_year_range(normalized_query)
        start_year = query_request.start_year or explicit_start_year
        end_year = query_request.end_year or explicit_end_year
        if intent is None:
            return UnsupportedPlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=query_request.requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=query_request.comparison_metric,
                is_valid=False,
                errors=("unsupported query intent",),
            )
        if intent in {QueryIntent.CAGR, QueryIntent.COMPOUND_ANNUAL_GROWTH_RATE}:
            requested_year = None

        requested_metric, comparison_metric = _infer_metrics(
            query_request,
            intent,
            normalized_query,
        )
        metric_resolution = _resolve_metric(
            self._metric_resolution_service,
            requested_metric,
        )
        if intent in {QueryIntent.CAGR, QueryIntent.COMPOUND_ANNUAL_GROWTH_RATE}:
            start_year, end_year = _resolve_cagr_years(
                financial_retrieval_service=self._financial_retrieval_service,
                normalized_query=normalized_query,
                resolved_metric=_resolved_metric(metric_resolution),
                start_year=start_year,
                end_year=end_year,
            )
        comparison_resolution = _resolve_metric(
            self._metric_resolution_service,
            comparison_metric,
        )
        warnings, errors = _validate_common(
            intent=intent,
            requested_metric=requested_metric,
            requested_year=requested_year,
            start_year=start_year,
            end_year=end_year,
            comparison_metric=comparison_metric,
            metric_resolution=metric_resolution,
            comparison_resolution=comparison_resolution,
        )
        is_valid = not errors
        requires_clarification = any(
            resolution.requires_clarification
            for resolution in (metric_resolution, comparison_resolution)
            if resolution is not None
        )

        if intent == QueryIntent.METRIC_VALUE:
            return MetricValuePlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=comparison_metric,
                resolved_metric=_resolved_metric(metric_resolution),
                metric_resolution=metric_resolution,
                is_valid=is_valid,
                requires_clarification=requires_clarification,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )
        if intent == QueryIntent.METRIC_HISTORY:
            return MetricHistoryPlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=comparison_metric,
                resolved_metric=_resolved_metric(metric_resolution),
                metric_resolution=metric_resolution,
                is_valid=is_valid,
                requires_clarification=requires_clarification,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )
        if intent == QueryIntent.METRIC_GROWTH:
            return MetricGrowthPlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=comparison_metric,
                resolved_metric=_resolved_metric(metric_resolution),
                metric_resolution=metric_resolution,
                calculation_type=(
                    "year_over_year_growth"
                    if requested_year is not None
                    else "multi_year_series"
                ),
                is_valid=is_valid,
                requires_clarification=requires_clarification,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )
        if intent in {QueryIntent.CAGR, QueryIntent.COMPOUND_ANNUAL_GROWTH_RATE}:
            return CAGRPlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=comparison_metric,
                resolved_metric=_resolved_metric(metric_resolution),
                metric_resolution=metric_resolution,
                intent=intent,
                is_valid=is_valid,
                requires_clarification=requires_clarification,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )
        if intent == QueryIntent.METRIC_COMPARISON:
            return MetricComparisonPlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=comparison_metric,
                resolved_metric=_resolved_metric(metric_resolution),
                resolved_comparison_metric=_resolved_metric(comparison_resolution),
                metric_resolution=metric_resolution,
                comparison_metric_resolution=comparison_resolution,
                is_valid=is_valid,
                requires_clarification=requires_clarification,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )
        if intent == QueryIntent.CONFLICT_EXPLANATION:
            conflict_count = 0
            if metric_resolution is not None and metric_resolution.resolved_metric:
                conflict_result = self._financial_retrieval_service.retrieve_metric_candidates(
                    metric_resolution.resolved_metric
                )
                conflict_count = len(conflict_result.conflicts)
                warnings.extend(conflict_result.warnings)
                if conflict_count == 0:
                    warnings.append("no conflict groups found for resolved metric")
            return ConflictPlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=comparison_metric,
                resolved_metric=_resolved_metric(metric_resolution),
                metric_resolution=metric_resolution,
                conflict_count=conflict_count,
                is_valid=is_valid,
                requires_clarification=requires_clarification,
                warnings=tuple(_deduplicate(warnings)),
                errors=tuple(errors),
            )
        if intent == QueryIntent.PROVENANCE_LOOKUP:
            return ProvenancePlan(
                raw_query=query_request.raw_query,
                normalized_query=normalized_query,
                requested_metric=requested_metric,
                requested_year=requested_year,
                start_year=start_year,
                end_year=end_year,
                comparison_metric=comparison_metric,
                resolved_metric=_resolved_metric(metric_resolution),
                metric_resolution=metric_resolution,
                is_valid=is_valid,
                requires_clarification=requires_clarification,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )
        return UnsupportedPlan(
            raw_query=query_request.raw_query,
            normalized_query=normalized_query,
            requested_metric=requested_metric,
            requested_year=requested_year,
            start_year=start_year,
            end_year=end_year,
            comparison_metric=comparison_metric,
            is_valid=False,
            errors=("unsupported query intent",),
        )


def _infer_intent(normalized_query: str) -> QueryIntent | None:
    if _is_cagr_query(normalized_query):
        if "compound annual growth rate" in normalized_query:
            return QueryIntent.COMPOUND_ANNUAL_GROWTH_RATE
        return QueryIntent.CAGR
    if _contains_any(normalized_query, ("conflict", "conflicts", "conflicting", "competing")):
        return QueryIntent.CONFLICT_EXPLANATION
    if _contains_any(
        normalized_query,
        ("selected", "selection", "source", "provenance", "citation", "citations"),
    ) or normalized_query.startswith("why was ") or _is_source_origin_query(
        normalized_query
    ):
        return QueryIntent.PROVENANCE_LOOKUP
    if _contains_any(normalized_query, ("compare", "comparison", " vs ", " versus ")):
        return QueryIntent.METRIC_COMPARISON
    if _contains_any(
        normalized_query,
        ("growth", "grew", "increase", "increased", "decrease", "decreased", "decline", "declined"),
    ):
        return QueryIntent.METRIC_GROWTH
    if _contains_any(normalized_query, ("trend", "history", "historical", "over time", "series")):
        return QueryIntent.METRIC_HISTORY
    if _extract_year(normalized_query) is not None or _contains_any(
        normalized_query,
        ("what was", "what is", "value"),
    ):
        return QueryIntent.METRIC_VALUE
    return None


def _infer_metrics(
    query_request: QueryRequest,
    intent: QueryIntent,
    normalized_query: str,
) -> tuple[str | None, str | None]:
    if intent == QueryIntent.METRIC_COMPARISON:
        inferred_left, inferred_right = _extract_comparison_metrics(
            normalized_query
        )
        return (
            query_request.requested_metric or inferred_left,
            query_request.comparison_metric or inferred_right,
        )
    return (
        query_request.requested_metric
        or _extract_metric(normalized_query),
        query_request.comparison_metric,
    )


def _extract_comparison_metrics(normalized_query: str) -> tuple[str | None, str | None]:
    query_without_years = _YEAR_PATTERN.sub(" ", normalized_query)
    query_without_lead = re.sub(r"^\s*(compare|comparison of)\s+", "", query_without_years)
    parts = [
        _clean_metric_text(part)
        for part in _COMPARISON_SPLIT_PATTERN.split(query_without_lead)
    ]
    metrics = [part for part in parts if part]
    if len(metrics) >= 2:
        return metrics[0], metrics[1]
    return (metrics[0], None) if metrics else (None, None)


def _extract_metric(normalized_query: str) -> str | None:
    metric = _clean_metric_text(_YEAR_PATTERN.sub(" ", normalized_query))
    return metric or None


def _clean_metric_text(value: str) -> str:
    cleaned = _STOPWORD_PATTERN.sub(" ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or ""


def _is_cagr_query(normalized_query: str) -> bool:
    return (
        " cagr " in f" {normalized_query} "
        or "compound annual growth rate" in normalized_query
    )


def _is_source_origin_query(normalized_query: str) -> bool:
    return (
        normalized_query.startswith(("where did ", "where does ", "where do "))
        and " come from" in f" {normalized_query} "
    )


def _extract_year_range(normalized_query: str) -> tuple[int | None, int | None]:
    years = [int(match.group(0)) for match in _YEAR_PATTERN.finditer(normalized_query)]
    if len(years) >= 2:
        return years[0], years[-1]
    return None, None


def _resolve_cagr_years(
    *,
    financial_retrieval_service: FinancialRetrievalService,
    normalized_query: str,
    resolved_metric: str | None,
    start_year: int | None,
    end_year: int | None,
) -> tuple[int | None, int | None]:
    if resolved_metric is None:
        return start_year, end_year
    years = sorted(
        {
            record.value_year
            for record in financial_retrieval_service.retrieve_metric_history(
                resolved_metric
            ).financial_records
        }
    )
    if len(years) < 2:
        return start_year, end_year
    if start_year is not None and end_year is not None:
        return start_year, end_year
    match = _LAST_N_YEARS_PATTERN.search(normalized_query)
    if match is not None:
        period_count = max(2, int(match.group(1)))
        selected = years[-period_count:]
        return selected[0], selected[-1]
    return years[0], years[-1]


def _extract_year(normalized_query: str) -> int | None:
    match = _YEAR_PATTERN.search(normalized_query)
    return int(match.group(0)) if match else None


def _resolve_metric(
    metric_resolution_service: MetricResolutionService,
    metric: str | None,
) -> MetricResolutionResult | None:
    if metric is None:
        return None
    try:
        return metric_resolution_service.resolve_metric(metric)
    except ValueError:
        return None


def _validate_common(
    *,
    intent: QueryIntent,
    requested_metric: str | None,
    requested_year: int | None,
    start_year: int | None,
    end_year: int | None,
    comparison_metric: str | None,
    metric_resolution: MetricResolutionResult | None,
    comparison_resolution: MetricResolutionResult | None,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if requested_metric is None:
        errors.append("missing metric")
    if intent == QueryIntent.METRIC_VALUE and requested_year is None:
        errors.append("missing year for metric value query")
    if intent in {QueryIntent.CAGR, QueryIntent.COMPOUND_ANNUAL_GROWTH_RATE}:
        if start_year is None or end_year is None:
            errors.append("missing start_year or end_year for CAGR query")
        elif start_year >= end_year:
            errors.append("start_year must be before end_year for CAGR query")
    if intent == QueryIntent.METRIC_COMPARISON and comparison_metric is None:
        errors.append("missing comparison metric")

    warnings.extend(_resolution_warnings(metric_resolution))
    warnings.extend(_resolution_warnings(comparison_resolution))
    if requested_metric is not None and _resolved_metric(metric_resolution) is None:
        errors.append("metric could not be resolved")
    if (
        intent == QueryIntent.METRIC_COMPARISON
        and comparison_metric is not None
        and _resolved_metric(comparison_resolution) is None
    ):
        errors.append("comparison metric could not be resolved")
    if metric_resolution is not None and metric_resolution.requires_clarification:
        errors.append("metric resolution requires clarification")
    if (
        comparison_resolution is not None
        and comparison_resolution.requires_clarification
    ):
        errors.append("comparison metric resolution requires clarification")
    return _deduplicate(warnings), _deduplicate(errors)


def _resolution_warnings(
    resolution: MetricResolutionResult | None,
) -> list[str]:
    if resolution is None:
        return []
    return list(resolution.warnings)


def _resolved_metric(
    resolution: MetricResolutionResult | None,
) -> str | None:
    return resolution.resolved_metric if resolution is not None else None


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    padded = f" {value} "
    return any(needle in padded for needle in needles)


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


__all__ = ["QueryPlannerService"]
