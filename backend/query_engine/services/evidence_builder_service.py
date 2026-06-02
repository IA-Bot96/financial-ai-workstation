"""Deterministic evidence bundle construction for the Financial Query Engine."""

from __future__ import annotations

import math
import re
from typing import Any

from query_engine.models.calculation import CalculationEvidence, CalculationResult
from query_engine.models.evidence import (
    EvidenceBundle,
    EvidenceCitation,
    EvidenceConflict,
    EvidenceMetric,
    EvidenceSeries,
)
from query_engine.models.knowledge_base import (
    ConflictRecord,
    FinancialRecord,
    WorkbookCellCitation,
)
from query_engine.models.metric_resolution import MetricResolutionResult
from query_engine.models.query_planner import CAGRPlan
from query_engine.models.retrieval import FinancialRetrievalResult
from query_engine.services.calculation_service import CalculationService
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.metric_resolution_service import MetricResolutionService


class EvidenceBuilderService:
    """Build deterministic evidence bundles from retrieval and calculation results."""

    def __init__(
        self,
        *,
        financial_retrieval_service: FinancialRetrievalService,
        metric_resolution_service: MetricResolutionService,
        calculation_service: CalculationService,
    ) -> None:
        """Initialize evidence construction with deterministic dependencies."""

        self._financial_retrieval_service = financial_retrieval_service
        self._metric_resolution_service = metric_resolution_service
        self._calculation_service = calculation_service

    def build_metric_evidence(self, metric: str) -> EvidenceBundle:
        """Build evidence for all available values for a user-facing metric."""

        resolution = self._metric_resolution_service.resolve_metric(metric)
        retrieval_result = self._retrieve_if_resolved(resolution, mode="metric")
        metrics = (
            tuple(_metric_from_financial_record(record) for record in retrieval_result.financial_records)
            if retrieval_result is not None
            else ()
        )
        return self._bundle(
            bundle_type="metric",
            query_metric=metric,
            resolution=resolution,
            metrics=metrics,
            retrieval_result=retrieval_result,
        )

    def build_metric_year_evidence(self, metric: str, year: int) -> EvidenceBundle:
        """Build evidence for a user-facing metric in one analytical year."""

        resolution = self._metric_resolution_service.resolve_metric(metric)
        retrieval_result: FinancialRetrievalResult | None = None
        if resolution.resolved_metric is not None:
            retrieval_result = self._financial_retrieval_service.retrieve_by_metric_and_year(
                resolution.resolved_metric,
                year,
            )
        metrics = (
            tuple(_metric_from_financial_record(record) for record in retrieval_result.financial_records)
            if retrieval_result is not None
            else ()
        )
        return self._bundle(
            bundle_type="metric_year",
            query_metric=metric,
            resolution=resolution,
            metrics=metrics,
            retrieval_result=retrieval_result,
        )

    def build_metric_history_evidence(self, metric: str) -> EvidenceBundle:
        """Build ordered historical evidence for a user-facing metric."""

        resolution = self._metric_resolution_service.resolve_metric(metric)
        retrieval_result = self._retrieve_if_resolved(resolution, mode="history")
        metrics = (
            tuple(_metric_from_financial_record(record) for record in retrieval_result.financial_records)
            if retrieval_result is not None
            else ()
        )
        series = EvidenceSeries(
            requested_metric=metric,
            resolved_metric=resolution.resolved_metric,
            points=metrics,
        )
        return self._bundle(
            bundle_type="metric_history",
            query_metric=metric,
            resolution=resolution,
            metrics=metrics,
            series=series,
            retrieval_result=retrieval_result,
        )

    def build_calculation_evidence(
        self,
        calculation_result: CalculationResult,
    ) -> EvidenceBundle:
        """Build evidence from an already executed deterministic calculation."""

        metrics = tuple(
            _metric_from_calculation_evidence(point)
            for point in calculation_result.evidence
        )
        series = EvidenceSeries(
            requested_metric=calculation_result.requested_metric,
            resolved_metric=calculation_result.resolved_metric,
            points=metrics,
        )
        calculation = {
            "calculation_type": calculation_result.calculation_type,
            "success": calculation_result.success,
            "value": calculation_result.value,
            "result_unit": calculation_result.result_unit,
            "trend_direction": calculation_result.trend_direction,
            "source_years": tuple(point.value_year for point in metrics),
            "supporting_value_count": len(metrics),
        }
        return self._bundle(
            bundle_type="calculation",
            query_metric=calculation_result.requested_metric,
            resolution=calculation_result.metric_resolution,
            metrics=metrics,
            series=series,
            calculation=calculation,
            conflicts=tuple(
                _conflict_from_record(conflict)
                for conflict in calculation_result.conflicts
            ),
            has_unresolved_conflicts=calculation_result.has_unresolved_conflicts,
            is_ambiguous=calculation_result.is_ambiguous,
            confidence=calculation_result.confidence,
            warnings=calculation_result.warnings,
            errors=calculation_result.errors,
        )

    def build_cagr_evidence(self, plan: CAGRPlan) -> EvidenceBundle:
        """Execute a CAGR plan and build deterministic calculation evidence."""

        if plan.requested_metric is None:
            return EvidenceBundle(
                bundle_type="calculation",
                query_metric=plan.raw_query,
                resolved_metric=plan.resolved_metric,
                validation_errors=("missing metric for CAGR calculation",),
            )
        if plan.start_year is None or plan.end_year is None:
            return EvidenceBundle(
                bundle_type="calculation",
                query_metric=plan.requested_metric,
                resolved_metric=plan.resolved_metric,
                metric_resolution=plan.metric_resolution,
                validation_errors=("missing start_year or end_year for CAGR calculation",),
            )
        calculation_result = self._calculation_service.cagr(
            plan.requested_metric,
            plan.start_year,
            plan.end_year,
        )
        return self.build_calculation_evidence(calculation_result)

    def _retrieve_if_resolved(
        self,
        resolution: MetricResolutionResult,
        *,
        mode: str,
    ) -> FinancialRetrievalResult | None:
        if resolution.resolved_metric is None:
            return None
        if mode == "history":
            return self._financial_retrieval_service.retrieve_metric_history(
                resolution.resolved_metric
            )
        return self._financial_retrieval_service.retrieve_by_metric(
            resolution.resolved_metric
        )

    def _bundle(
        self,
        *,
        bundle_type: str,
        query_metric: str,
        resolution: MetricResolutionResult | None,
        metrics: tuple[EvidenceMetric, ...],
        series: EvidenceSeries | None = None,
        retrieval_result: FinancialRetrievalResult | None = None,
        calculation: dict[str, Any] | None = None,
        conflicts: tuple[EvidenceConflict, ...] | None = None,
        has_unresolved_conflicts: bool | None = None,
        is_ambiguous: bool | None = None,
        confidence: float | None = None,
        warnings: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
    ) -> EvidenceBundle:
        retrieval_conflicts = (
            tuple(_conflict_from_record(conflict) for conflict in retrieval_result.conflicts)
            if retrieval_result is not None
            else ()
        )
        all_conflicts = conflicts if conflicts is not None else retrieval_conflicts
        all_warnings = _deduplicate(
            [
                *(resolution.warnings if resolution is not None else ()),
                *(retrieval_result.warnings if retrieval_result is not None else ()),
                *warnings,
            ]
        )
        validation_errors = _validation_errors(
            resolution=resolution,
            metrics=metrics,
            errors=errors,
        )
        citations = tuple(metric.citation for metric in metrics)
        citation_complete = bool(citations) and all(
            citation.citation_status == "cell_mapped"
            and bool(citation.sheet_name)
            and bool(citation.cell_reference)
            for citation in citations
        )
        provenance_consistent = bool(metrics) and all(
            metric.value_year <= metric.source_report_year
            and metric.page_number > 0
            and bool(metric.table_type)
            for metric in metrics
        )
        evidence_complete = bool(metrics) and not validation_errors
        resolved_metric = resolution.resolved_metric if resolution is not None else None
        resolution_confidence = _resolution_confidence(resolution)
        bundle_confidence = (
            confidence
            if confidence is not None
            else _bundle_confidence(resolution_confidence, metrics)
        )
        return EvidenceBundle(
            bundle_type=bundle_type,
            query_metric=query_metric,
            resolved_metric=resolved_metric,
            resolution_confidence=resolution_confidence,
            metric_resolution=resolution,
            metrics=metrics,
            series=series,
            calculation=calculation or {},
            conflicts=all_conflicts,
            citations=citations,
            has_unresolved_conflicts=(
                has_unresolved_conflicts
                if has_unresolved_conflicts is not None
                else any(conflict.unresolved_conflict for conflict in all_conflicts)
            ),
            is_ambiguous=(
                is_ambiguous
                if is_ambiguous is not None
                else bool(
                    (resolution and resolution.is_ambiguous)
                    or (retrieval_result and retrieval_result.is_ambiguous)
                )
            ),
            confidence=bundle_confidence,
            evidence_complete=evidence_complete,
            citation_complete=citation_complete,
            provenance_consistent=provenance_consistent,
            validation_errors=validation_errors,
            warnings=tuple(all_warnings),
        )


def _metric_from_financial_record(record: FinancialRecord) -> EvidenceMetric:
    return EvidenceMetric(
        record_id=record.record_id,
        metric=record.metric,
        canonical_metric=record.canonical_metric,
        value_year=record.value_year,
        value=record.value,
        numeric_value=_to_float(record.value),
        source_report_year=record.source_report_year,
        page_number=record.page_number,
        table_type=record.table_type,
        statement_scope=record.statement_scope,
        confidence=record.normalization_confidence,
        source_metric=record.original_metric,
        conflict_status=record.conflict_status,
        unresolved_conflict=record.unresolved_conflict,
        requires_review=record.requires_review,
        citation=_citation_from_workbook_citation(
            record.workbook_citation,
            source_report_year=record.source_report_year,
            page_number=record.page_number,
            table_type=record.table_type,
        ),
        provenance={
            "record_id": record.record_id,
            "source_class": record.source_class,
            "source_confidence": record.source_confidence,
            "candidate_count": record.candidate_count,
            "resolution_reason": record.resolution_reason,
            "conflict_group_id": record.conflict_group_id,
        },
    )


def _metric_from_calculation_evidence(point: CalculationEvidence) -> EvidenceMetric:
    source_metric = None
    requires_review = False
    source_class = None
    source_confidence = None
    if point.retrieval_evidence:
        provenance = point.retrieval_evidence[0].provenance
        source_metric = _optional_str(provenance.get("original_metric"))
        requires_review = bool(provenance.get("requires_review", False))
        source_class = provenance.get("source_class")
        source_confidence = provenance.get("source_confidence")
    return EvidenceMetric(
        record_id=point.record_id,
        metric=point.metric,
        canonical_metric=point.metric,
        value_year=point.value_year,
        value=point.value,
        numeric_value=point.numeric_value,
        source_report_year=point.source_report_year,
        page_number=point.page_number,
        table_type=point.table_type,
        statement_scope=point.statement_scope,
        confidence=point.confidence,
        source_metric=source_metric,
        conflict_status=point.conflict_status,
        unresolved_conflict=point.unresolved_conflict,
        requires_review=requires_review,
        citation=_citation_from_workbook_citation(
            point.workbook_citation,
            source_report_year=point.source_report_year,
            page_number=point.page_number,
            table_type=point.table_type,
        ),
        provenance={
            "record_id": point.record_id,
            "source_class": source_class,
            "source_confidence": source_confidence,
            "retrieval_evidence_ids": tuple(
                evidence.evidence_id for evidence in point.retrieval_evidence
            ),
        },
    )


def _citation_from_workbook_citation(
    citation: WorkbookCellCitation,
    *,
    source_report_year: int | None,
    page_number: int | None,
    table_type: str | None,
) -> EvidenceCitation:
    return EvidenceCitation(
        citation_status=citation.citation_status,
        sheet_name=citation.sheet_name,
        row=citation.row,
        column=citation.column,
        cell_reference=citation.cell_reference,
        source_report_year=source_report_year,
        page_number=page_number,
        table_type=table_type,
    )


def _conflict_from_record(conflict: ConflictRecord) -> EvidenceConflict:
    return EvidenceConflict(
        conflict_group_id=conflict.conflict_group_id,
        metric=conflict.metric,
        value_year=conflict.value_year,
        conflict_status=conflict.conflict_status,
        unresolved_conflict=conflict.unresolved_conflict,
        candidate_count=conflict.candidate_count,
        selected_candidate_id=conflict.selected_candidate_id,
        resolution_reason=conflict.resolution_reason,
        candidate_values=tuple(candidate.value for candidate in conflict.candidates),
    )


def _validation_errors(
    *,
    resolution: MetricResolutionResult | None,
    metrics: tuple[EvidenceMetric, ...],
    errors: tuple[str, ...],
) -> tuple[str, ...]:
    validation_errors = list(errors)
    if resolution is None:
        validation_errors.append("metric resolution unavailable")
    elif resolution.resolved_metric is None:
        validation_errors.append("metric could not be resolved")
    if not metrics:
        validation_errors.append("no evidence metrics found")
    if metrics and not all(metric.citation.citation_status == "cell_mapped" for metric in metrics):
        validation_errors.append("missing workbook citation for one or more evidence metrics")
    if metrics and not all(metric.value_year <= metric.source_report_year for metric in metrics):
        validation_errors.append("inconsistent provenance: value_year exceeds source_report_year")
    return tuple(_deduplicate(validation_errors))


def _resolution_confidence(resolution: MetricResolutionResult | None) -> float:
    if resolution is None or resolution.best_candidate is None:
        return 0.0
    return resolution.best_candidate.confidence


def _bundle_confidence(
    resolution_confidence: float,
    metrics: tuple[EvidenceMetric, ...],
) -> float:
    values = [resolution_confidence] if resolution_confidence > 0 else []
    values.extend(metric.confidence for metric in metrics)
    if not values:
        return 0.0
    return max(0.0, min(1.0, sum(values) / len(values)))


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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _deduplicate(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


__all__ = ["EvidenceBuilderService"]
