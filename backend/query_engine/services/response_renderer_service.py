"""Deterministic response rendering for the Financial Query Engine."""

from __future__ import annotations

from typing import Any

from query_engine.models.evidence import EvidenceBundle, EvidenceMetric
from query_engine.models.query_planner import (
    CAGRPlan,
    ConflictPlan,
    MetricComparisonPlan,
    MetricGrowthPlan,
    MetricHistoryPlan,
    MetricValuePlan,
    ProvenancePlan,
    QueryPlan,
)
from query_engine.models.response import (
    CAGRResponse,
    ConflictResponse,
    MetricComparisonResponse,
    MetricGrowthResponse,
    MetricHistoryResponse,
    MetricValueResponse,
    ProvenanceResponse,
    QueryResponse,
)


class ResponseRendererService:
    """Render deterministic Query Engine responses from plans and evidence."""

    def render(
        self,
        plan: QueryPlan,
        evidence_bundle: EvidenceBundle,
        comparison_evidence_bundle: EvidenceBundle | None = None,
    ) -> QueryResponse:
        """Render a response by dispatching on the concrete query plan type."""

        if isinstance(plan, MetricValuePlan):
            return self.render_metric_value(plan, evidence_bundle)
        if isinstance(plan, MetricHistoryPlan):
            return self.render_metric_history(plan, evidence_bundle)
        if isinstance(plan, MetricGrowthPlan):
            return self.render_metric_growth(plan, evidence_bundle)
        if isinstance(plan, CAGRPlan):
            return self.render_cagr(plan, evidence_bundle)
        if isinstance(plan, MetricComparisonPlan):
            return self.render_metric_comparison(
                plan,
                evidence_bundle,
                comparison_evidence_bundle,
            )
        if isinstance(plan, ConflictPlan):
            return self.render_conflict(plan, evidence_bundle)
        if isinstance(plan, ProvenancePlan):
            return self.render_provenance(plan, evidence_bundle)
        return QueryResponse(
            answer_type="metric_value",
            raw_query=plan.raw_query,
            intent=plan.intent,
            confidence=0.0,
            is_ambiguous=plan.requires_clarification,
            has_conflicts=False,
            is_answerable=False,
            warnings=plan.warnings,
            errors=(*plan.errors, "unsupported plan type for response rendering"),
        )

    def render_metric_value(
        self,
        plan: MetricValuePlan,
        evidence_bundle: EvidenceBundle,
    ) -> MetricValueResponse:
        """Render a single metric-year value response."""

        metric = _select_metric(evidence_bundle.metrics, year=plan.requested_year)
        return MetricValueResponse(
            **_base_fields(plan, evidence_bundle),
            metrics=_metric_names(evidence_bundle.metrics, fallback=plan.resolved_metric),
            values=(() if metric is None else (metric.value,)),
            years=(() if metric is None else (metric.value_year,)),
            metric=plan.resolved_metric,
            year=plan.requested_year,
            value=metric.value if metric is not None else None,
            is_answerable=metric is not None and evidence_bundle.evidence_complete,
        )

    def render_metric_history(
        self,
        plan: MetricHistoryPlan,
        evidence_bundle: EvidenceBundle,
    ) -> MetricHistoryResponse:
        """Render a historical metric series response."""

        points = tuple(
            _metric_point(metric)
            for metric in sorted(evidence_bundle.metrics, key=lambda item: item.value_year)
        )
        return MetricHistoryResponse(
            **_base_fields(plan, evidence_bundle),
            metrics=_metric_names(evidence_bundle.metrics, fallback=plan.resolved_metric),
            values=tuple(point["value"] for point in points),
            years=tuple(point["value_year"] for point in points),
            metric=plan.resolved_metric,
            series=points,
            is_answerable=bool(points) and evidence_bundle.evidence_complete,
        )

    def render_metric_growth(
        self,
        plan: MetricGrowthPlan,
        evidence_bundle: EvidenceBundle,
    ) -> MetricGrowthResponse:
        """Render a deterministic growth or trend calculation response."""

        supporting_values = tuple(
            _metric_point(metric)
            for metric in sorted(evidence_bundle.metrics, key=lambda item: item.value_year)
        )
        result_value = evidence_bundle.calculation.get("value")
        return MetricGrowthResponse(
            **_base_fields(plan, evidence_bundle),
            metrics=_metric_names(evidence_bundle.metrics, fallback=plan.resolved_metric),
            values=tuple(
                value for value in (result_value,) if value is not None
            ),
            years=tuple(point["value_year"] for point in supporting_values),
            metric=plan.resolved_metric,
            calculation_type=_optional_str(
                evidence_bundle.calculation.get("calculation_type")
            ),
            result_value=result_value,
            result_unit=_optional_str(evidence_bundle.calculation.get("result_unit")),
            supporting_values=supporting_values,
            is_answerable=bool(supporting_values) and not evidence_bundle.validation_errors,
        )

    def render_cagr(
        self,
        plan: CAGRPlan,
        evidence_bundle: EvidenceBundle,
    ) -> CAGRResponse:
        """Render a deterministic CAGR calculation response."""

        source_values = tuple(
            _metric_point(metric)
            for metric in sorted(evidence_bundle.metrics, key=lambda item: item.value_year)
            if metric.value_year in {plan.start_year, plan.end_year}
        )
        if not source_values:
            source_values = tuple(
                _metric_point(metric)
                for metric in sorted(evidence_bundle.metrics, key=lambda item: item.value_year)
            )
        result_value = evidence_bundle.calculation.get("value")
        return CAGRResponse(
            **_base_fields(plan, evidence_bundle),
            metrics=_metric_names(evidence_bundle.metrics, fallback=plan.resolved_metric),
            values=tuple(
                value for value in (result_value,) if value is not None
            ),
            years=tuple(point["value_year"] for point in source_values),
            metric=plan.resolved_metric,
            cagr_value=result_value,
            result_unit=_optional_str(evidence_bundle.calculation.get("result_unit")),
            start_year=plan.start_year,
            end_year=plan.end_year,
            source_values=source_values,
            is_answerable=(
                result_value is not None
                and bool(source_values)
                and not evidence_bundle.validation_errors
            ),
        )

    def render_metric_comparison(
        self,
        plan: MetricComparisonPlan,
        left_evidence_bundle: EvidenceBundle,
        right_evidence_bundle: EvidenceBundle | None = None,
    ) -> MetricComparisonResponse:
        """Render a comparison between two metric evidence bundles."""

        right_bundle = right_evidence_bundle or _empty_bundle_for_comparison(plan)
        left_values = tuple(_metric_point(metric) for metric in left_evidence_bundle.metrics)
        right_values = tuple(_metric_point(metric) for metric in right_bundle.metrics)
        citations = (*left_evidence_bundle.citations, *right_bundle.citations)
        conflicts = (*left_evidence_bundle.conflicts, *right_bundle.conflicts)
        warnings = _deduplicate(
            [*left_evidence_bundle.warnings, *right_bundle.warnings, *plan.warnings]
        )
        errors = _deduplicate(
            [
                *left_evidence_bundle.validation_errors,
                *right_bundle.validation_errors,
                *plan.errors,
            ]
        )
        return MetricComparisonResponse(
            answer_type="metric_comparison",
            raw_query=plan.raw_query,
            intent=plan.intent,
            metrics=tuple(
                value
                for value in (plan.resolved_metric, plan.resolved_comparison_metric)
                if value is not None
            ),
            values=tuple(
                point["value"] for point in (*left_values, *right_values)
            ),
            years=tuple(
                sorted({point["value_year"] for point in (*left_values, *right_values)})
            ),
            confidence=_average_confidence(
                left_evidence_bundle.confidence,
                right_bundle.confidence,
            ),
            is_ambiguous=(
                plan.requires_clarification
                or left_evidence_bundle.is_ambiguous
                or right_bundle.is_ambiguous
            ),
            has_conflicts=bool(conflicts)
            or left_evidence_bundle.has_unresolved_conflicts
            or right_bundle.has_unresolved_conflicts,
            citations=citations,
            provenance_references=(
                *_provenance_references(left_evidence_bundle.metrics),
                *_provenance_references(right_bundle.metrics),
            ),
            conflicts=conflicts,
            warnings=tuple(warnings),
            errors=tuple(errors),
            is_answerable=bool(left_values and right_values) and not errors,
            left_metric=plan.resolved_metric,
            right_metric=plan.resolved_comparison_metric,
            left_values=left_values,
            right_values=right_values,
        )

    def render_conflict(
        self,
        plan: ConflictPlan,
        evidence_bundle: EvidenceBundle,
    ) -> ConflictResponse:
        """Render conflict groups without suppressing competing values."""

        candidate_values = tuple(
            value
            for conflict in evidence_bundle.conflicts
            for value in conflict.candidate_values
        )
        return ConflictResponse(
            **_base_fields(plan, evidence_bundle),
            metrics=_metric_names(evidence_bundle.metrics, fallback=plan.resolved_metric),
            values=candidate_values,
            years=tuple(conflict.value_year for conflict in evidence_bundle.conflicts),
            metric=plan.resolved_metric,
            conflict_count=len(evidence_bundle.conflicts),
            conflict_details=evidence_bundle.conflicts,
            is_answerable=bool(evidence_bundle.conflicts),
        )

    def render_provenance(
        self,
        plan: ProvenancePlan,
        evidence_bundle: EvidenceBundle,
    ) -> ProvenanceResponse:
        """Render selected value provenance and competing candidates."""

        selected_metric = _select_metric(evidence_bundle.metrics, year=plan.requested_year)
        competing_values = tuple(
            value
            for conflict in evidence_bundle.conflicts
            for value in conflict.candidate_values
            if selected_metric is None or value != selected_metric.value
        )
        resolution_reason = None
        if selected_metric is not None:
            resolution_reason = _optional_str(
                selected_metric.provenance.get("resolution_reason")
            )
        if resolution_reason is None and evidence_bundle.conflicts:
            resolution_reason = evidence_bundle.conflicts[0].resolution_reason
        return ProvenanceResponse(
            **_base_fields(plan, evidence_bundle),
            metrics=_metric_names(evidence_bundle.metrics, fallback=plan.resolved_metric),
            values=(() if selected_metric is None else (selected_metric.value,)),
            years=(() if selected_metric is None else (selected_metric.value_year,)),
            metric=plan.resolved_metric,
            selected_value=selected_metric.value if selected_metric is not None else None,
            selected_year=(
                selected_metric.value_year if selected_metric is not None else None
            ),
            competing_values=competing_values,
            resolution_reason=resolution_reason,
            source_page=selected_metric.page_number if selected_metric is not None else None,
            source_type=(
                _optional_str(selected_metric.provenance.get("source_class"))
                if selected_metric is not None
                else None
            ),
            is_answerable=selected_metric is not None and not evidence_bundle.validation_errors,
        )


def _base_fields(
    plan: QueryPlan,
    evidence_bundle: EvidenceBundle,
) -> dict[str, object]:
    return {
        "raw_query": plan.raw_query,
        "intent": plan.intent,
        "confidence": evidence_bundle.confidence,
        "is_ambiguous": plan.requires_clarification or evidence_bundle.is_ambiguous,
        "has_conflicts": bool(evidence_bundle.conflicts)
        or evidence_bundle.has_unresolved_conflicts,
        "citations": evidence_bundle.citations,
        "provenance_references": _provenance_references(evidence_bundle.metrics),
        "conflicts": evidence_bundle.conflicts,
        "warnings": tuple(
            _deduplicate([*plan.warnings, *evidence_bundle.warnings])
        ),
        "errors": tuple(
            _deduplicate([*plan.errors, *evidence_bundle.validation_errors])
        ),
    }


def _select_metric(
    metrics: tuple[EvidenceMetric, ...],
    *,
    year: int | None,
) -> EvidenceMetric | None:
    if year is not None:
        for metric in metrics:
            if metric.value_year == year:
                return metric
    return metrics[0] if metrics else None


def _metric_point(metric: EvidenceMetric) -> dict[str, Any]:
    return {
        "metric": metric.metric,
        "value_year": metric.value_year,
        "value": metric.value,
        "numeric_value": metric.numeric_value,
        "source_report_year": metric.source_report_year,
        "page_number": metric.page_number,
        "table_type": metric.table_type,
        "statement_scope": metric.statement_scope,
        "confidence": metric.confidence,
        "conflict_status": metric.conflict_status,
    }


def _metric_names(
    metrics: tuple[EvidenceMetric, ...],
    *,
    fallback: str | None,
) -> tuple[str, ...]:
    names = [metric.metric for metric in metrics]
    if not names and fallback is not None:
        names.append(fallback)
    return tuple(_deduplicate(names))


def _provenance_references(
    metrics: tuple[EvidenceMetric, ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "record_id": metric.record_id,
            "metric": metric.metric,
            "value_year": metric.value_year,
            "source_report_year": metric.source_report_year,
            "page_number": metric.page_number,
            "table_type": metric.table_type,
            "statement_scope": metric.statement_scope,
            "source_metric": metric.source_metric,
            "source_class": metric.provenance.get("source_class"),
            "resolution_reason": metric.provenance.get("resolution_reason"),
            "citation_status": metric.citation.citation_status,
        }
        for metric in metrics
    )


def _average_confidence(*values: float) -> float:
    valid = [value for value in values if value > 0]
    if not valid:
        return 0.0
    return max(0.0, min(1.0, sum(valid) / len(valid)))


def _empty_bundle_for_comparison(plan: MetricComparisonPlan) -> EvidenceBundle:
    return EvidenceBundle(
        bundle_type="metric",
        query_metric=plan.comparison_metric or "unknown",
        resolved_metric=plan.resolved_comparison_metric,
        validation_errors=("comparison evidence bundle missing",),
    )


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


__all__ = ["ResponseRendererService"]
