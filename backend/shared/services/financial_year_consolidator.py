"""Consolidate comparative-year metric values across annual reports."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
import logging
import re

from ocr_engine.models.table_normalization import MetricMapping, NormalizationResult
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MetricValueCandidate:
    """Consolidation candidate enriched with normalization provenance."""

    metric_value: MetricValue
    source_confidence: float
    original_metric: str
    requires_review: bool
    input_index: int


@dataclass(frozen=True)
class _ConsolidationGroupDiagnostic:
    """Diagnostic for one duplicate/conflict consolidation group."""

    metric: str
    value_year: int
    candidate_count: int
    selected: dict[str, object]
    removed: list[dict[str, object]]
    is_duplicate_group: bool
    is_conflict_group: bool
    conflict_resolved: bool
    unresolved_conflict: bool
    resolution_reason: str


@dataclass(frozen=True)
class ConsolidationDiagnostics:
    """Summary of duplicate/conflict consolidation decisions."""

    duplicate_groups_resolved: int = 0
    conflict_groups_resolved: int = 0
    unresolved_conflict_groups: int = 0
    quality_overrode_recency: int = 0
    metric_values_removed: int = 0
    review_mappings_reduced: int = 0
    groups: list[_ConsolidationGroupDiagnostic] = field(default_factory=list)

    def model_dump(self) -> dict[str, object]:
        """Return JSON-serializable diagnostics."""

        return asdict(self)


class FinancialYearConsolidator:
    """Select the best available metric value for each metric/value year.

    Annual reports include comparative historical values. For any
    ``(metric, value_year)`` pair, candidate quality is evaluated before
    report recency. Newer reports are preferred only after normalization
    confidence, label quality, source context, and table-source quality tie.
    """

    def __init__(self) -> None:
        """Initialize consolidator state."""

        self.last_diagnostics = ConsolidationDiagnostics()

    def consolidate(self, metric_values: Iterable[MetricValue]) -> list[MetricValue]:
        """Return one source-of-truth value for each metric and value year."""

        candidates = [
            _MetricValueCandidate(
                metric_value=metric_value,
                source_confidence=0.0,
                original_metric=metric_value.metric,
                requires_review=False,
                input_index=input_index,
            )
            for input_index, metric_value in enumerate(metric_values)
        ]
        return self._consolidate_candidates(candidates)

    def consolidate_normalization_result(
        self,
        normalization_result: NormalizationResult,
    ) -> list[MetricValue]:
        """Consolidate one normalization result using mapping confidence metadata."""

        return self._consolidate_candidates(
            _candidates_from_normalization_result(normalization_result)
        )

    def _consolidate_candidates(
        self,
        candidates: Iterable[_MetricValueCandidate],
    ) -> list[MetricValue]:
        """Return consolidated values and store duplicate/conflict diagnostics."""

        selected: dict[tuple[str, int], _MetricValueCandidate] = {}
        grouped: dict[tuple[str, int], list[_MetricValueCandidate]] = {}
        for candidate in candidates:
            metric_value = candidate.metric_value
            self._validate_metric_value(metric_value)
            key = (metric_value.metric, metric_value.value_year)
            grouped.setdefault(key, []).append(candidate)
            existing = selected.get(key)
            if (
                existing is None
                or self._should_replace(existing, candidate)
            ):
                if existing is not None and _values_differ(
                    existing.metric_value,
                    metric_value,
                ):
                    logger.info(
                        "Metric value superseded during financial year consolidation",
                        extra={
                            "metric": metric_value.metric,
                            "value_year": metric_value.value_year,
                            "previous_value": existing.metric_value.value,
                            "selected_value": metric_value.value,
                            "previous_source_report_year": (
                                existing.metric_value.source_report_year
                            ),
                            "selected_source_report_year": (
                                metric_value.source_report_year
                            ),
                            "previous_page_number": existing.metric_value.page_number,
                            "selected_page_number": metric_value.page_number,
                            "previous_table_type": existing.metric_value.table_type,
                            "selected_table_type": metric_value.table_type,
                        },
                    )
                selected[key] = candidate

        self.last_diagnostics = _build_consolidation_diagnostics(
            selected=selected,
            grouped=grouped,
        )

        return sorted(
            (candidate.metric_value for candidate in selected.values()),
            key=lambda metric_value: (
                metric_value.metric,
                metric_value.value_year,
                metric_value.source_report_year,
            ),
        )

    def consolidate_context(self, context: CompanyContext) -> CompanyContext:
        """Consolidate normalized metric values from all report-year buckets."""

        metric_values: list[_MetricValueCandidate] = []
        failures: list[str] = []
        for report in context.reports:
            try:
                normalization_result = context.normalization_results.get(report.year)
                if normalization_result is None:
                    raise ValueError(
                        "Missing normalization result for report year "
                        f"{report.year}."
                )

                for candidate in _candidates_from_normalization_result(
                    normalization_result
                ):
                    metric_value = candidate.metric_value
                    self._validate_bucket_year(report.year, metric_value)
                    self._validate_metric_value(metric_value)
                    metric_values.append(candidate)
            except Exception as exc:
                failures.append(
                    f"Report year {report.year} failed financial year "
                    f"consolidation: {_error_message(exc)}"
                )
                logger.exception(
                    "Financial year consolidation failed for report; continuing",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                    },
                )
                continue

        context.metric_values = self._consolidate_candidates(metric_values)
        if failures:
            raise PipelineLayerPartialFailure(failures, context=context)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run financial year consolidation as a pipeline layer."""

        return self.consolidate_context(context)

    @classmethod
    def _should_replace(
        cls,
        existing: _MetricValueCandidate,
        candidate: _MetricValueCandidate,
    ) -> bool:
        """Return whether candidate should replace the currently selected value."""

        existing_value = existing.metric_value
        candidate_value = candidate.metric_value

        candidate_key = _candidate_quality_key(candidate)
        existing_key = _candidate_quality_key(existing)
        if candidate_key != existing_key:
            return candidate_key > existing_key

        if candidate_value.source_report_year > existing_value.source_report_year:
            return True
        if candidate_value.source_report_year < existing_value.source_report_year:
            return False

        return _tie_break_key(candidate.metric_value) < _tie_break_key(
            existing.metric_value
        )

    @staticmethod
    def _validate_metric_value(metric_value: MetricValue) -> None:
        """Validate comparative-year provenance invariants."""

        if metric_value.value_year > metric_value.source_report_year:
            raise ValueError(
                "metric value_year cannot be greater than source_report_year: "
                f"{metric_value.metric} value_year={metric_value.value_year}, "
                f"source_report_year={metric_value.source_report_year}."
            )

    @staticmethod
    def _validate_bucket_year(bucket_year: int, metric_value: MetricValue) -> None:
        """Ensure context buckets remain isolated by source report year."""

        if bucket_year != metric_value.source_report_year:
            raise ValueError(
                "normalization_results bucket year must match "
                "metric_value.source_report_year: "
                f"bucket_year={bucket_year}, "
                f"source_report_year={metric_value.source_report_year}, "
                f"metric={metric_value.metric}."
            )


def _tie_break_key(metric_value: MetricValue) -> tuple[int, str, str]:
    """Return a stable same-source tie-break key independent of input order."""

    return (
        metric_value.page_number,
        metric_value.table_type.strip().lower(),
        _stable_value_text(metric_value.value),
    )


def _candidates_from_normalization_result(
    normalization_result: NormalizationResult,
) -> list[_MetricValueCandidate]:
    """Return consolidation candidates enriched from parallel mapping metadata."""

    candidates: list[_MetricValueCandidate] = []
    for input_index, metric_value in enumerate(normalization_result.metric_values):
        mapping = (
            normalization_result.mappings[input_index]
            if input_index < len(normalization_result.mappings)
            else None
        )
        candidates.append(
            _MetricValueCandidate(
                metric_value=metric_value,
                source_confidence=_mapping_confidence(mapping),
                original_metric=_mapping_original_metric(mapping, metric_value),
                requires_review=bool(mapping.requires_review) if mapping else False,
                input_index=input_index,
            )
        )
    return candidates


def _mapping_confidence(mapping: MetricMapping | None) -> float:
    """Return mapping confidence, defaulting to zero when unavailable."""

    if mapping is None:
        return 0.0
    return max(0.0, min(1.0, float(mapping.confidence)))


def _mapping_original_metric(
    mapping: MetricMapping | None,
    metric_value: MetricValue,
) -> str:
    """Return raw metric label used for label-quality scoring."""

    if mapping is not None and mapping.original_metric.strip():
        return mapping.original_metric.strip()
    return metric_value.metric.strip()


def _candidate_quality_key(
    candidate: _MetricValueCandidate,
) -> tuple[float, int, int, int]:
    """Return quality rank for same-report duplicate/conflict resolution."""

    metric_value = candidate.metric_value
    return (
        candidate.source_confidence,
        _label_cleanliness_score(candidate.original_metric),
        _source_context_score(candidate),
        _table_type_priority(metric_value.table_type),
    )


def _label_cleanliness_score(label: str) -> int:
    """Score whether a candidate label appears reconstructed and complete."""

    text = label.strip()
    if not text:
        return 0

    score = 100
    if _has_fragmentation_signal(text):
        score -= 35
    if _has_truncation_signal(text):
        score -= 25
    if len(re.findall(r"[A-Za-z]", text)) < 4:
        score -= 15
    words = re.findall(r"[A-Za-z]+", text)
    score += min(len(words), 10)
    return max(0, score)


def _has_fragmentation_signal(label: str) -> bool:
    """Return whether a label still contains OCR/pdfplumber split-word artifacts."""

    normalized = label.lower()
    return bool(
        re.search(
            r"\b(?:a nd|ra tio|rat ios|operati ons|ex penditures|"
            r"activit(?:y|ies)|valu e|re valuation|inv ested|"
            r"particu lars|j u?ne|employ ee|pro fit|charg es|sale s)\b",
            normalized,
        )
    )


def _has_truncation_signal(label: str) -> bool:
    """Return whether a label appears cut off before its full context."""

    stripped = label.strip()
    return bool(
        re.search(r"\([^)]*$", stripped)
        or re.search(
            r"\b(?:of|and|to|from|for|with|by|in|at|the)$",
            stripped,
            re.IGNORECASE,
        )
    )


def _source_context_score(candidate: _MetricValueCandidate) -> int:
    """Score whether a candidate carries enough provenance/context to trust."""

    score = 0
    if not candidate.requires_review:
        score += 30
    if candidate.original_metric.strip() != candidate.metric_value.metric.strip():
        score += 10
    if len(candidate.original_metric.split()) >= 2:
        score += 10
    if candidate.metric_value.page_number > 0:
        score += 5
    return score


def _table_type_priority(table_type: str) -> int:
    """Return preference for primary financial statements over note disclosures."""

    normalized = table_type.strip().lower()
    primary_statement_priorities = {
        "income_statement": 100,
        "statement_of_profit_or_loss": 100,
        "balance_sheet": 100,
        "statement_of_financial_position": 100,
        "cash_flow_statement": 100,
        "statement_of_cash_flows": 100,
        "statement_of_changes_in_equity": 95,
    }
    if normalized in primary_statement_priorities:
        return primary_statement_priorities[normalized]
    if "analysis" in normalized or "ratio" in normalized:
        return 75
    if "schedule" in normalized:
        return 65
    if "note" in normalized or "disclosure" in normalized:
        return 35
    if normalized == "unclassified_table":
        return 0
    return 50


def _build_consolidation_diagnostics(
    *,
    selected: dict[tuple[str, int], _MetricValueCandidate],
    grouped: dict[tuple[str, int], list[_MetricValueCandidate]],
) -> ConsolidationDiagnostics:
    """Build duplicate/conflict diagnostics from selected and grouped candidates."""

    group_diagnostics: list[_ConsolidationGroupDiagnostic] = []
    for key, candidates in grouped.items():
        if len(candidates) <= 1:
            continue
        selected_candidate = selected[key]
        distinct_values = {
            _stable_value_text(candidate.metric_value.value) for candidate in candidates
        }
        is_conflict_group = len(distinct_values) > 1
        is_duplicate_group = len(candidates) > 1
        removed = [
            candidate for candidate in candidates if candidate is not selected_candidate
        ]
        unresolved_conflict = (
            is_conflict_group
            and _has_unresolved_top_tie(candidates, selected_candidate)
        )
        group_diagnostics.append(
            _ConsolidationGroupDiagnostic(
                metric=key[0],
                value_year=key[1],
                candidate_count=len(candidates),
                selected=_candidate_payload(selected_candidate),
                removed=[_candidate_payload(candidate) for candidate in removed],
                is_duplicate_group=is_duplicate_group,
                is_conflict_group=is_conflict_group,
                conflict_resolved=is_conflict_group and not unresolved_conflict,
                unresolved_conflict=unresolved_conflict,
                resolution_reason=_resolution_reason(
                    selected_candidate=selected_candidate,
                    candidates=candidates,
                    unresolved_conflict=unresolved_conflict,
                ),
            )
        )

    metric_values_removed = sum(
        diagnostic.candidate_count - 1 for diagnostic in group_diagnostics
    )
    review_mappings_reduced = sum(
        1
        for diagnostic in group_diagnostics
        if not diagnostic.unresolved_conflict
        for removed_candidate in diagnostic.removed
        if bool(removed_candidate.get("requires_review"))
    )
    return ConsolidationDiagnostics(
        duplicate_groups_resolved=sum(
            1 for diagnostic in group_diagnostics if diagnostic.is_duplicate_group
        ),
        conflict_groups_resolved=sum(
            1 for diagnostic in group_diagnostics if diagnostic.conflict_resolved
        ),
        unresolved_conflict_groups=sum(
            1 for diagnostic in group_diagnostics if diagnostic.unresolved_conflict
        ),
        quality_overrode_recency=sum(
            1
            for diagnostic in group_diagnostics
            if diagnostic.resolution_reason
            in {
                "higher_normalization_confidence",
                "cleaner_reconstructed_label",
                "more_complete_source_context",
                "preferred_financial_statement_source",
            }
            and any(
                removed_candidate.get("source_report_year", 0)
                > diagnostic.selected.get("source_report_year", 0)
                for removed_candidate in diagnostic.removed
            )
        ),
        metric_values_removed=metric_values_removed,
        review_mappings_reduced=review_mappings_reduced,
        groups=sorted(
            group_diagnostics,
            key=lambda diagnostic: (
                diagnostic.metric,
                diagnostic.value_year,
                -diagnostic.candidate_count,
            ),
        ),
    )


def _has_unresolved_top_tie(
    candidates: list[_MetricValueCandidate],
    selected_candidate: _MetricValueCandidate,
) -> bool:
    """Return whether a conflict required final stable tie-break selection."""

    selected_quality_key = _candidate_quality_key(selected_candidate)
    tied_top_candidates = [
        candidate
        for candidate in candidates
        if candidate.metric_value.source_report_year
        == selected_candidate.metric_value.source_report_year
        and _candidate_quality_key(candidate) == selected_quality_key
    ]
    tied_values = {
        _stable_value_text(candidate.metric_value.value)
        for candidate in tied_top_candidates
    }
    return len(tied_values) > 1


def _resolution_reason(
    *,
    selected_candidate: _MetricValueCandidate,
    candidates: list[_MetricValueCandidate],
    unresolved_conflict: bool,
) -> str:
    """Return the first precedence rule that separated the selected candidate."""

    if unresolved_conflict:
        return "unresolved_equal_precedence_conflict"

    selected_value = selected_candidate.metric_value
    if any(
        candidate.source_confidence < selected_candidate.source_confidence
        for candidate in candidates
    ):
        return "higher_normalization_confidence"
    selected_cleanliness = _label_cleanliness_score(selected_candidate.original_metric)
    if any(
        _label_cleanliness_score(candidate.original_metric) < selected_cleanliness
        for candidate in candidates
    ):
        return "cleaner_reconstructed_label"
    selected_context_score = _source_context_score(selected_candidate)
    if any(
        _source_context_score(candidate) < selected_context_score
        for candidate in candidates
    ):
        return "more_complete_source_context"
    selected_table_priority = _table_type_priority(selected_value.table_type)
    if any(
        _table_type_priority(candidate.metric_value.table_type)
        < selected_table_priority
        for candidate in candidates
    ):
        return "preferred_financial_statement_source"
    if any(
        candidate.metric_value.source_report_year < selected_value.source_report_year
        for candidate in candidates
    ):
        return "latest_source_report_year"
    return "stable_tie_break"


def _candidate_payload(candidate: _MetricValueCandidate) -> dict[str, object]:
    """Return JSON-serializable candidate provenance."""

    metric_value = candidate.metric_value
    return {
        "metric": metric_value.metric,
        "value_year": metric_value.value_year,
        "value": metric_value.value,
        "source_report_year": metric_value.source_report_year,
        "page_number": metric_value.page_number,
        "table_type": metric_value.table_type,
        "source_confidence": candidate.source_confidence,
        "original_metric": candidate.original_metric,
        "requires_review": candidate.requires_review,
        "label_cleanliness_score": _label_cleanliness_score(candidate.original_metric),
        "source_context_score": _source_context_score(candidate),
        "table_type_priority": _table_type_priority(metric_value.table_type),
    }


def _stable_value_text(value: float | int | str) -> str:
    """Return a stable comparable representation for a metric value."""

    return f"{type(value).__name__}:{value}"


def _values_differ(left: MetricValue, right: MetricValue) -> bool:
    """Return whether two metric values carry different extracted values."""

    return _stable_value_text(left.value) != _stable_value_text(right.value)


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for result metadata."""

    return str(exc) or exc.__class__.__name__
