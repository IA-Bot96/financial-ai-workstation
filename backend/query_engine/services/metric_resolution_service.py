"""Resolve user-facing metric names to FinancialDataset canonical metrics."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping

from query_engine.models.knowledge_base import CompanyKnowledgeBase, normalize_key
from query_engine.models.metric_resolution import (
    MetricMatchType,
    MetricResolutionCandidate,
    MetricResolutionResult,
)
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from shared.normalization.services.metric_registry_loader import (
    CanonicalMetric,
    MetricRegistryLoader,
)

_ALIAS_CONFIDENCE = 0.96
_CANONICAL_CONFIDENCE = 0.98
_EXACT_CONFIDENCE = 1.0
_FUZZY_THRESHOLD = 0.72
_HIGH_CONFIDENCE = 0.90

_MATCH_PRIORITY: dict[MetricMatchType, int] = {
    "exact": 4,
    "alias": 3,
    "canonical": 2,
    "fuzzy": 1,
}

_PREFERRED_CANONICAL_BY_QUERY = {
    # Query Engine policy preference: financial-statement "net income" questions
    # should retrieve the audited PAT line when both concepts exist.
    "net_income": "profit_after_tax",
}

_BROAD_PARENT_PREFERENCES_BY_QUERY = {
    "cash": ("cash_and_cash_equivalents", "cash_and_bank_balances"),
    "debt": ("total_debt",),
    "equity": ("total_equity", "equity"),
    "revenue": ("revenue",),
}


@dataclass(frozen=True)
class _RegistryTerm:
    """One searchable registry term."""

    normalized_term: str
    original_term: str
    canonical_metric: str
    match_type: MetricMatchType


class MetricResolutionService:
    """Resolve user-facing metric names before deterministic financial retrieval."""

    def __init__(
        self,
        *,
        knowledge_base: CompanyKnowledgeBase,
        financial_retrieval_service: FinancialRetrievalService,
        canonical_metric_registry: Mapping[str, Any] | None = None,
        registry_path: str | Path | None = None,
        registry_loader: MetricRegistryLoader | None = None,
    ) -> None:
        """Initialize resolver using the shared OCR canonical registry."""

        self._knowledge_base = knowledge_base
        self._financial_retrieval_service = financial_retrieval_service
        self._registry_loader = registry_loader or MetricRegistryLoader()
        self._metrics = self._load_metrics(canonical_metric_registry, registry_path)
        self._metric_by_key = {metric.key: metric for metric in self._metrics}
        self._terms = self._build_terms(self._metrics)
        self._available_metric_counts = self._build_available_metric_counts()

    def resolve_metric(self, query_metric: str) -> MetricResolutionResult:
        """Resolve a user-facing metric label into canonical candidates."""

        original_query = query_metric.strip()
        if not original_query:
            raise ValueError("query_metric must be a non-empty string.")

        normalized_query = normalize_key(original_query)
        candidates = self._resolve_candidates(original_query, normalized_query)
        best_candidate = self._select_best_candidate(normalized_query, candidates)
        available_high_confidence_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.available_in_dataset
            and candidate.confidence >= _HIGH_CONFIDENCE
        )
        is_ambiguous = len(
            {candidate.canonical_metric for candidate in available_high_confidence_candidates}
        ) > 1
        warnings: list[str] = []
        if not candidates:
            warnings.append(f"unknown metric: {normalized_query}")
        elif best_candidate is None:
            warnings.append(
                "metric resolved only to canonical registry entries that are not "
                "available in the FinancialDataset"
            )
        if is_ambiguous:
            warnings.append(
                "multiple high-confidence metric candidates found; clarification may "
                "be required"
            )

        return MetricResolutionResult(
            query_metric=original_query,
            normalized_query=normalized_query,
            resolved_metric=(
                best_candidate.canonical_metric if best_candidate is not None else None
            ),
            found=bool(candidates),
            is_ambiguous=is_ambiguous,
            requires_clarification=is_ambiguous and best_candidate is None,
            best_candidate=best_candidate,
            candidates=candidates,
            warnings=tuple(_deduplicate(warnings)),
        )

    def resolve_metric_candidates(
        self,
        query_metric: str,
    ) -> tuple[MetricResolutionCandidate, ...]:
        """Return all deterministic canonical candidates for a metric query."""

        return self.resolve_metric(query_metric).candidates

    def resolve_best_metric(
        self,
        query_metric: str,
    ) -> MetricResolutionCandidate | None:
        """Return the best available canonical metric candidate, if any."""

        return self.resolve_metric(query_metric).best_candidate

    def _load_metrics(
        self,
        canonical_metric_registry: Mapping[str, Any] | None,
        registry_path: str | Path | None,
    ) -> tuple[CanonicalMetric, ...]:
        if canonical_metric_registry is not None:
            return self._registry_loader.load_from_dict(canonical_metric_registry)
        if registry_path is not None:
            return self._registry_loader.load_from_file(registry_path)
        return self._registry_loader.load_default()

    def _build_available_metric_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self._knowledge_base.financial_dataset.records:
            counts[record.metric] = counts.get(record.metric, 0) + 1
        return counts

    @staticmethod
    def _build_terms(metrics: tuple[CanonicalMetric, ...]) -> tuple[_RegistryTerm, ...]:
        terms: list[_RegistryTerm] = []
        seen: set[tuple[str, str, str]] = set()
        for metric in metrics:
            for term, match_type in (
                (metric.key, "canonical"),
                (metric.display_name, "canonical"),
                (normalize_key(metric.key), "canonical"),
            ):
                _append_term(
                    terms=terms,
                    seen=seen,
                    term=term,
                    canonical_metric=metric.key,
                    match_type=match_type,
                )
            for alias in metric.aliases:
                _append_term(
                    terms=terms,
                    seen=seen,
                    term=alias,
                    canonical_metric=metric.key,
                    match_type="alias",
                )
        return tuple(terms)

    def _resolve_candidates(
        self,
        original_query: str,
        normalized_query: str,
    ) -> tuple[MetricResolutionCandidate, ...]:
        candidate_by_metric: dict[str, MetricResolutionCandidate] = {}

        if (
            normalized_query in self._available_metric_counts
            and original_query.lower() == normalized_query
        ):
            self._upsert_candidate(
                candidate_by_metric,
                canonical_metric=normalized_query,
                match_type="exact",
                confidence=_EXACT_CONFIDENCE,
                matched_term=original_query,
            )

        for term in self._terms:
            if term.normalized_term != normalized_query:
                continue
            confidence = (
                _ALIAS_CONFIDENCE
                if term.match_type == "alias"
                else _CANONICAL_CONFIDENCE
            )
            self._upsert_candidate(
                candidate_by_metric,
                canonical_metric=term.canonical_metric,
                match_type=term.match_type,
                confidence=confidence,
                matched_term=term.original_term,
            )

        self._add_preferred_candidate(
            candidate_by_metric,
            normalized_query=normalized_query,
            original_query=original_query,
        )

        if not candidate_by_metric:
            self._add_fuzzy_candidates(candidate_by_metric, normalized_query)
        elif not _has_strong_deterministic_match(candidate_by_metric.values()):
            self._add_token_candidates(candidate_by_metric, normalized_query)

        return tuple(
            sorted(
                candidate_by_metric.values(),
                key=lambda candidate: _candidate_sort_key(
                    normalized_query,
                    candidate,
                ),
            )
        )

    def _add_preferred_candidate(
        self,
        candidate_by_metric: dict[str, MetricResolutionCandidate],
        *,
        normalized_query: str,
        original_query: str,
    ) -> None:
        preferred = _PREFERRED_CANONICAL_BY_QUERY.get(normalized_query)
        if preferred is None:
            for broad_parent in _BROAD_PARENT_PREFERENCES_BY_QUERY.get(
                normalized_query,
                (),
            ):
                if broad_parent in self._available_metric_counts:
                    preferred = broad_parent
                    break
        if preferred is None:
            return
        if preferred not in self._available_metric_counts:
            return
        self._upsert_candidate(
            candidate_by_metric,
            canonical_metric=preferred,
            match_type="fuzzy",
            confidence=0.99,
            matched_term=original_query,
        )

    def _add_fuzzy_candidates(
        self,
        candidate_by_metric: dict[str, MetricResolutionCandidate],
        normalized_query: str,
    ) -> None:
        for term in self._terms:
            score = _similarity(normalized_query, term.normalized_term)
            if score >= _FUZZY_THRESHOLD:
                self._upsert_candidate(
                    candidate_by_metric,
                    canonical_metric=term.canonical_metric,
                    match_type="fuzzy",
                    confidence=score,
                    matched_term=term.original_term,
                )
        self._add_token_candidates(candidate_by_metric, normalized_query)

    def _add_token_candidates(
        self,
        candidate_by_metric: dict[str, MetricResolutionCandidate],
        normalized_query: str,
    ) -> None:
        query_tokens = _tokens(normalized_query)
        if not query_tokens:
            return
        for canonical_metric in self._available_metric_counts:
            metric_tokens = _tokens(canonical_metric)
            overlap = query_tokens & metric_tokens
            if not overlap:
                continue
            if query_tokens <= metric_tokens:
                confidence = 0.92 if len(query_tokens) > 1 else 0.91
            else:
                confidence = min(
                    0.88,
                    0.68
                    + (0.1 * len(overlap))
                    + (0.05 * len(overlap) / len(query_tokens)),
                )
            if confidence < _FUZZY_THRESHOLD:
                continue
            self._upsert_candidate(
                candidate_by_metric,
                canonical_metric=canonical_metric,
                match_type="fuzzy",
                confidence=confidence,
                matched_term=canonical_metric,
            )

    def _upsert_candidate(
        self,
        candidate_by_metric: dict[str, MetricResolutionCandidate],
        *,
        canonical_metric: str,
        match_type: MetricMatchType,
        confidence: float,
        matched_term: str,
    ) -> None:
        metric_definition = self._metric_by_key.get(canonical_metric)
        available_count = self._available_metric_counts.get(canonical_metric, 0)
        candidate = MetricResolutionCandidate(
            canonical_metric=canonical_metric,
            display_name=(
                metric_definition.display_name if metric_definition is not None else None
            ),
            category=metric_definition.category if metric_definition is not None else None,
            match_type=match_type,
            confidence=max(0.0, min(1.0, float(confidence))),
            matched_term=matched_term,
            available_in_dataset=available_count > 0,
            financial_record_count=available_count,
        )
        existing = candidate_by_metric.get(canonical_metric)
        if existing is None or _candidate_is_better(candidate, existing):
            candidate_by_metric[canonical_metric] = candidate

    @staticmethod
    def _select_best_candidate(
        normalized_query: str,
        candidates: tuple[MetricResolutionCandidate, ...],
    ) -> MetricResolutionCandidate | None:
        if not candidates:
            return None
        preferred = _PREFERRED_CANONICAL_BY_QUERY.get(normalized_query)
        if preferred is not None:
            for candidate in candidates:
                if candidate.canonical_metric == preferred and candidate.available_in_dataset:
                    return candidate

        available = tuple(candidate for candidate in candidates if candidate.available_in_dataset)
        if available:
            return sorted(
                available,
                key=lambda candidate: _candidate_sort_key(normalized_query, candidate),
            )[0]
        return None


def _append_term(
    *,
    terms: list[_RegistryTerm],
    seen: set[tuple[str, str, str]],
    term: str,
    canonical_metric: str,
    match_type: MetricMatchType,
) -> None:
    normalized_term = normalize_key(term)
    if not normalized_term:
        return
    key = (normalized_term, canonical_metric, match_type)
    if key in seen:
        return
    seen.add(key)
    terms.append(
        _RegistryTerm(
            normalized_term=normalized_term,
            original_term=term,
            canonical_metric=canonical_metric,
            match_type=match_type,
        )
    )


def _candidate_is_better(
    candidate: MetricResolutionCandidate,
    existing: MetricResolutionCandidate,
) -> bool:
    return (
        candidate.available_in_dataset,
        _MATCH_PRIORITY[candidate.match_type],
        candidate.confidence,
        candidate.financial_record_count,
    ) > (
        existing.available_in_dataset,
        _MATCH_PRIORITY[existing.match_type],
        existing.confidence,
        existing.financial_record_count,
    )


def _candidate_sort_key(
    normalized_query: str,
    candidate: MetricResolutionCandidate,
) -> tuple[object, ...]:
    preferred = _PREFERRED_CANONICAL_BY_QUERY.get(normalized_query)
    return (
        0 if candidate.canonical_metric == preferred else 1,
        0 if candidate.available_in_dataset else 1,
        -_MATCH_PRIORITY[candidate.match_type],
        -candidate.confidence,
        -candidate.financial_record_count,
        candidate.canonical_metric,
    )


def _has_strong_deterministic_match(
    candidates: object,
) -> bool:
    for candidate in candidates:
        if not candidate.available_in_dataset:
            continue
        if candidate.match_type in {"exact", "alias"}:
            return True
        if (
            candidate.match_type == "canonical"
            and candidate.confidence >= _ALIAS_CONFIDENCE
        ):
            return True
    return False


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(a=left, b=right).ratio()


def _tokens(value: str) -> set[str]:
    return {token for token in normalize_key(value).split("_") if len(token) >= 3}


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


__all__ = ["MetricResolutionService"]
