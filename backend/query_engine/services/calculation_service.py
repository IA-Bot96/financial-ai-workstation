"""Deterministic financial calculation service."""

from __future__ import annotations

import math
import re

from query_engine.models.calculation import (
    CalculationEvidence,
    CalculationRequest,
    CalculationResult,
    CalculationSeries,
    CalculationType,
    TrendDirection,
)
from query_engine.models.knowledge_base import ConflictRecord, FinancialRecord
from query_engine.models.metric_resolution import MetricResolutionResult
from query_engine.models.retrieval import FinancialRetrievalResult, RetrievalEvidence
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.metric_resolution_service import MetricResolutionService
from shared.models.financial_year_consolidation import StatementScope

_SOURCE_CLASS_PRIORITY = {
    "primary_statement": 5,
    "supporting_schedule": 4,
    "note_disclosure": 3,
    "analysis_or_ratio": 2,
    "unclassified": 1,
}


class CalculationService:
    """Run deterministic calculations over resolved financial metric series."""

    def __init__(
        self,
        *,
        financial_retrieval_service: FinancialRetrievalService,
        metric_resolution_service: MetricResolutionService,
    ) -> None:
        """Initialize the calculation service with deterministic dependencies."""

        self._financial_retrieval_service = financial_retrieval_service
        self._metric_resolution_service = metric_resolution_service

    def calculate(self, request: CalculationRequest) -> CalculationResult:
        """Dispatch a calculation request to the deterministic implementation."""

        if request.calculation_type == "year_over_year_growth":
            year = request.year if request.year is not None else request.end_year
            if year is None:
                return self._failure(
                    request,
                    errors=("year_over_year_growth requires year or end_year.",),
                )
            return self.year_over_year_growth(
                request.metric,
                year,
                statement_scope=request.statement_scope,
                request=request,
            )
        if request.calculation_type == "cagr":
            return self.cagr(
                request.metric,
                request.start_year,
                request.end_year,
                statement_scope=request.statement_scope,
                request=request,
            )
        if request.calculation_type == "percentage_change":
            return self.percentage_change(
                request.metric,
                request.start_year,
                request.end_year,
                statement_scope=request.statement_scope,
                request=request,
            )
        if request.calculation_type == "absolute_change":
            return self.absolute_change(
                request.metric,
                request.start_year,
                request.end_year,
                statement_scope=request.statement_scope,
                request=request,
            )
        if request.calculation_type == "trend_direction":
            return self.trend_direction(
                request.metric,
                start_year=request.start_year,
                end_year=request.end_year,
                statement_scope=request.statement_scope,
                request=request,
            )
        if request.calculation_type == "multi_year_series":
            return self.multi_year_series(
                request.metric,
                start_year=request.start_year,
                end_year=request.end_year,
                statement_scope=request.statement_scope,
                request=request,
            )
        return self._failure(
            request,
            errors=(f"unsupported calculation_type: {request.calculation_type}",),
        )

    def year_over_year_growth(
        self,
        metric: str,
        year: int,
        *,
        statement_scope: StatementScope | None = None,
        request: CalculationRequest | None = None,
    ) -> CalculationResult:
        """Calculate year-over-year growth percentage for a metric."""

        request = request or CalculationRequest(
            calculation_type="year_over_year_growth",
            metric=metric,
            year=year,
            statement_scope=statement_scope,
        )
        series_context = self._series_context(metric, statement_scope)
        return self._change_result(
            request=request,
            series_context=series_context,
            start_year=year - 1,
            end_year=year,
            calculation_type="year_over_year_growth",
            result_unit="percentage",
            mode="percentage",
        )

    def cagr(
        self,
        metric: str,
        start_year: int | None,
        end_year: int | None,
        *,
        statement_scope: StatementScope | None = None,
        request: CalculationRequest | None = None,
    ) -> CalculationResult:
        """Calculate compound annual growth rate for a metric."""

        request = request or CalculationRequest(
            calculation_type="cagr",
            metric=metric,
            start_year=start_year,
            end_year=end_year,
            statement_scope=statement_scope,
        )
        if start_year is None or end_year is None:
            return self._failure(request, errors=("cagr requires start_year and end_year.",))
        series_context = self._series_context(metric, statement_scope)
        base = series_context.point_by_year.get(start_year)
        end = series_context.point_by_year.get(end_year)
        errors = list(series_context.errors)
        if base is None:
            errors.append(f"missing year {start_year} for metric")
        if end is None:
            errors.append(f"missing year {end_year} for metric")
        if errors:
            return self._result(
                request=request,
                series_context=series_context,
                success=False,
                errors=tuple(errors),
            )
        if base.numeric_value is None or end.numeric_value is None:
            return self._result(
                request=request,
                series_context=series_context,
                success=False,
                errors=("non-numeric value prevents CAGR calculation",),
            )
        if base.numeric_value <= 0 or end.numeric_value < 0:
            return self._result(
                request=request,
                series_context=series_context,
                success=False,
                errors=("CAGR requires positive start value and non-negative end value",),
            )
        periods = end_year - start_year
        value = ((end.numeric_value / base.numeric_value) ** (1 / periods) - 1) * 100
        return self._result(
            request=request,
            series_context=series_context,
            success=True,
            value=value,
            result_unit="percentage",
        )

    def percentage_change(
        self,
        metric: str,
        start_year: int | None,
        end_year: int | None,
        *,
        statement_scope: StatementScope | None = None,
        request: CalculationRequest | None = None,
    ) -> CalculationResult:
        """Calculate percentage change between two years."""

        request = request or CalculationRequest(
            calculation_type="percentage_change",
            metric=metric,
            start_year=start_year,
            end_year=end_year,
            statement_scope=statement_scope,
        )
        if start_year is None or end_year is None:
            return self._failure(
                request,
                errors=("percentage_change requires start_year and end_year.",),
            )
        return self._change_result(
            request=request,
            series_context=self._series_context(metric, statement_scope),
            start_year=start_year,
            end_year=end_year,
            calculation_type="percentage_change",
            result_unit="percentage",
            mode="percentage",
        )

    def absolute_change(
        self,
        metric: str,
        start_year: int | None,
        end_year: int | None,
        *,
        statement_scope: StatementScope | None = None,
        request: CalculationRequest | None = None,
    ) -> CalculationResult:
        """Calculate absolute value change between two years."""

        request = request or CalculationRequest(
            calculation_type="absolute_change",
            metric=metric,
            start_year=start_year,
            end_year=end_year,
            statement_scope=statement_scope,
        )
        if start_year is None or end_year is None:
            return self._failure(
                request,
                errors=("absolute_change requires start_year and end_year.",),
            )
        return self._change_result(
            request=request,
            series_context=self._series_context(metric, statement_scope),
            start_year=start_year,
            end_year=end_year,
            calculation_type="absolute_change",
            result_unit="value",
            mode="absolute",
        )

    def trend_direction(
        self,
        metric: str,
        *,
        start_year: int | None = None,
        end_year: int | None = None,
        statement_scope: StatementScope | None = None,
        request: CalculationRequest | None = None,
    ) -> CalculationResult:
        """Classify deterministic trend direction over available history."""

        request = request or CalculationRequest(
            calculation_type="trend_direction",
            metric=metric,
            start_year=start_year,
            end_year=end_year,
            statement_scope=statement_scope,
        )
        series_context = self._series_context(metric, statement_scope)
        points = _filter_points(series_context.points, start_year, end_year)
        if len(points) < 2:
            return self._result(
                request=request,
                series_context=series_context.with_points(points),
                success=False,
                trend_direction="insufficient_data",
                errors=("insufficient history for trend_direction",),
            )
        numeric_points = [point for point in points if point.numeric_value is not None]
        if len(numeric_points) < 2:
            return self._result(
                request=request,
                series_context=series_context.with_points(points),
                success=False,
                trend_direction="insufficient_data",
                errors=("non-numeric values prevent trend_direction",),
            )
        direction = _trend_direction([point.numeric_value for point in numeric_points])
        return self._result(
            request=request,
            series_context=series_context.with_points(points),
            success=True,
            value=direction,
            result_unit="direction",
            trend_direction=direction,
        )

    def multi_year_series(
        self,
        metric: str,
        *,
        start_year: int | None = None,
        end_year: int | None = None,
        statement_scope: StatementScope | None = None,
        request: CalculationRequest | None = None,
    ) -> CalculationResult:
        """Return a deterministic multi-year metric series."""

        request = request or CalculationRequest(
            calculation_type="multi_year_series",
            metric=metric,
            start_year=start_year,
            end_year=end_year,
            statement_scope=statement_scope,
        )
        series_context = self._series_context(metric, statement_scope)
        points = _filter_points(series_context.points, start_year, end_year)
        if not points:
            return self._result(
                request=request,
                series_context=series_context.with_points(points),
                success=False,
                errors=("no series points available",),
            )
        return self._result(
            request=request,
            series_context=series_context.with_points(points),
            success=True,
            result_unit="series",
        )

    def _change_result(
        self,
        *,
        request: CalculationRequest,
        series_context: "_SeriesContext",
        start_year: int,
        end_year: int,
        calculation_type: CalculationType,
        result_unit: str,
        mode: str,
    ) -> CalculationResult:
        start = series_context.point_by_year.get(start_year)
        end = series_context.point_by_year.get(end_year)
        errors = list(series_context.errors)
        if start is None:
            errors.append(f"missing year {start_year} for metric")
        if end is None:
            errors.append(f"missing year {end_year} for metric")
        scoped_context = series_context.with_points(
            tuple(point for point in (start, end) if point is not None)
        )
        if errors:
            return self._result(
                request=request,
                series_context=scoped_context,
                success=False,
                errors=tuple(errors),
            )
        if start is None or end is None:
            return self._result(
                request=request,
                series_context=scoped_context,
                success=False,
                errors=("missing source values",),
            )
        if start.numeric_value is None or end.numeric_value is None:
            return self._result(
                request=request,
                series_context=scoped_context,
                success=False,
                errors=(f"non-numeric value prevents {calculation_type}",),
            )
        if mode == "percentage":
            if start.numeric_value == 0:
                return self._result(
                    request=request,
                    series_context=scoped_context,
                    success=False,
                    errors=("divide-by-zero: start value is zero",),
                )
            value = ((end.numeric_value - start.numeric_value) / start.numeric_value) * 100
        else:
            value = end.numeric_value - start.numeric_value
        return self._result(
            request=request,
            series_context=scoped_context,
            success=True,
            value=value,
            result_unit=result_unit,
        )

    def _series_context(
        self,
        metric: str,
        statement_scope: StatementScope | None,
    ) -> "_SeriesContext":
        resolution = self._metric_resolution_service.resolve_metric(metric)
        warnings = list(resolution.warnings)
        errors: list[str] = []
        if resolution.is_ambiguous:
            warnings.append("ambiguous metric resolution propagated to calculation")
        if resolution.resolved_metric is None:
            errors.append("metric could not be resolved")
            return _SeriesContext(
                requested_metric=metric,
                resolved_metric=None,
                resolution=resolution,
                retrieval_result=None,
                points=(),
                conflicts=(),
                retrieval_evidence=(),
                warnings=tuple(_deduplicate(warnings)),
                errors=tuple(_deduplicate(errors)),
            )

        if statement_scope is not None:
            retrieval_result = self._financial_retrieval_service.retrieve_by_statement_scope(
                resolution.resolved_metric,
                statement_scope,
            )
        else:
            retrieval_result = self._financial_retrieval_service.retrieve_metric_history(
                resolution.resolved_metric
            )
        warnings.extend(retrieval_result.warnings)
        if retrieval_result.has_unresolved_conflicts:
            warnings.append("unresolved conflicts propagated to calculation")
        if retrieval_result.is_ambiguous:
            warnings.append("ambiguous financial retrieval propagated to calculation")

        selected_records = _select_records_by_year(retrieval_result.financial_records)
        points = tuple(
            _calculation_evidence(record, retrieval_result.evidence)
            for record in selected_records
        )
        return _SeriesContext(
            requested_metric=metric,
            resolved_metric=resolution.resolved_metric,
            resolution=resolution,
            retrieval_result=retrieval_result,
            points=points,
            conflicts=retrieval_result.conflicts,
            retrieval_evidence=retrieval_result.evidence,
            warnings=tuple(_deduplicate(warnings)),
            errors=tuple(_deduplicate(errors)),
        )

    def _result(
        self,
        *,
        request: CalculationRequest,
        series_context: "_SeriesContext",
        success: bool,
        value: float | str | None = None,
        result_unit: str | None = None,
        trend_direction: TrendDirection | None = None,
        warnings: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
    ) -> CalculationResult:
        all_warnings = tuple(_deduplicate([*series_context.warnings, *warnings]))
        all_errors = tuple(_deduplicate([*series_context.errors, *errors]))
        evidence = series_context.points
        scopes = tuple(
            sorted(
                {point.statement_scope for point in evidence}
            )
        )
        has_unresolved_conflicts = any(
            conflict.unresolved_conflict for conflict in series_context.conflicts
        ) or any(point.unresolved_conflict for point in evidence)
        return CalculationResult(
            request=request,
            calculation_type=request.calculation_type,
            requested_metric=series_context.requested_metric,
            resolved_metric=series_context.resolved_metric,
            success=success and not all_errors,
            value=value if success and not all_errors else None,
            result_unit=result_unit,
            trend_direction=trend_direction,
            series=CalculationSeries(
                requested_metric=series_context.requested_metric,
                resolved_metric=series_context.resolved_metric,
                points=evidence,
            ),
            evidence=evidence,
            retrieval_evidence=series_context.retrieval_evidence,
            conflicts=series_context.conflicts,
            has_unresolved_conflicts=has_unresolved_conflicts,
            is_ambiguous=(
                series_context.resolution.is_ambiguous
                or bool(
                    series_context.retrieval_result
                    and series_context.retrieval_result.is_ambiguous
                )
            ),
            statement_scope_differences=scopes if len(scopes) > 1 else (),
            confidence=_confidence(series_context.resolution, evidence),
            metric_resolution=series_context.resolution,
            warnings=all_warnings,
            errors=all_errors,
        )

    @staticmethod
    def _failure(
        request: CalculationRequest,
        *,
        errors: tuple[str, ...],
    ) -> CalculationResult:
        return CalculationResult(
            request=request,
            calculation_type=request.calculation_type,
            requested_metric=request.metric,
            success=False,
            series=CalculationSeries(requested_metric=request.metric),
            errors=errors,
        )


class _SeriesContext:
    def __init__(
        self,
        *,
        requested_metric: str,
        resolved_metric: str | None,
        resolution,
        retrieval_result: FinancialRetrievalResult | None,
        points: tuple[CalculationEvidence, ...],
        conflicts: tuple[ConflictRecord, ...],
        retrieval_evidence: tuple[RetrievalEvidence, ...],
        warnings: tuple[str, ...],
        errors: tuple[str, ...],
    ) -> None:
        self.requested_metric = requested_metric
        self.resolved_metric = resolved_metric
        self.resolution = resolution
        self.retrieval_result = retrieval_result
        self.points = points
        self.conflicts = conflicts
        self.retrieval_evidence = retrieval_evidence
        self.warnings = warnings
        self.errors = errors
        self.point_by_year = {point.value_year: point for point in points}

    def with_points(
        self,
        points: tuple[CalculationEvidence, ...],
    ) -> "_SeriesContext":
        return _SeriesContext(
            requested_metric=self.requested_metric,
            resolved_metric=self.resolved_metric,
            resolution=self.resolution,
            retrieval_result=self.retrieval_result,
            points=points,
            conflicts=self.conflicts,
            retrieval_evidence=self.retrieval_evidence,
            warnings=self.warnings,
            errors=self.errors,
        )


def _select_records_by_year(
    records: tuple[FinancialRecord, ...],
) -> tuple[FinancialRecord, ...]:
    grouped: dict[int, list[FinancialRecord]] = {}
    for record in records:
        grouped.setdefault(record.value_year, []).append(record)
    selected: list[FinancialRecord] = []
    for _, year_records in sorted(grouped.items()):
        selected.append(sorted(year_records, key=_record_sort_key)[0])
    return tuple(selected)


def _record_sort_key(record: FinancialRecord) -> tuple[object, ...]:
    return (
        record.unresolved_conflict,
        -record.normalization_confidence,
        -record.source_confidence,
        -_SOURCE_CLASS_PRIORITY.get(record.source_class, 0),
        -record.source_report_year,
        record.record_id,
    )


def _calculation_evidence(
    record: FinancialRecord,
    retrieval_evidence: tuple[RetrievalEvidence, ...],
) -> CalculationEvidence:
    return CalculationEvidence(
        record_id=record.record_id,
        metric=record.metric,
        value_year=record.value_year,
        value=record.value,
        numeric_value=_to_float(record.value),
        source_report_year=record.source_report_year,
        page_number=record.page_number,
        table_type=record.table_type,
        statement_scope=record.statement_scope,
        confidence=record.normalization_confidence,
        conflict_status=record.conflict_status,
        unresolved_conflict=record.unresolved_conflict,
        workbook_citation=record.workbook_citation,
        retrieval_evidence=tuple(
            evidence
            for evidence in retrieval_evidence
            if evidence.evidence_id == record.record_id
        ),
    )


def _to_float(value: float | int | str) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace(",", "").replace(" ", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", "-", ".", "-."}:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return -abs(parsed) if negative else parsed


def _filter_points(
    points: tuple[CalculationEvidence, ...],
    start_year: int | None,
    end_year: int | None,
) -> tuple[CalculationEvidence, ...]:
    return tuple(
        point
        for point in points
        if (start_year is None or point.value_year >= start_year)
        and (end_year is None or point.value_year <= end_year)
    )


def _trend_direction(values: list[float]) -> TrendDirection:
    diffs = [right - left for left, right in zip(values, values[1:])]
    if all(diff > 0 for diff in diffs):
        return "increasing"
    if all(diff < 0 for diff in diffs):
        return "decreasing"
    if all(diff == 0 for diff in diffs):
        return "flat"
    return "mixed"


def _confidence(
    resolution: MetricResolutionResult,
    evidence: tuple[CalculationEvidence, ...],
) -> float:
    values: list[float] = []
    if resolution.best_candidate is not None:
        values.append(resolution.best_candidate.confidence)
    values.extend(point.confidence for point in evidence)
    if not values:
        return 0.0
    return max(0.0, min(1.0, sum(values) / len(values)))


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


__all__ = ["CalculationService"]
