"""Shared deterministic single-metric normalizer."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from shared.normalization.constants.normalization_constants import (
    ALIAS_MATCH_CONFIDENCE,
    EXACT_MATCH_CONFIDENCE,
    HIGH_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
)
from shared.normalization.interfaces.metric_normalizer import IMetricNormalizer
from shared.normalization.models.normalized_metric import NormalizedMetric
from shared.normalization.services.embedding_generator import EmbeddingGenerator
from shared.normalization.services.metric_registry_loader import (
    CanonicalMetric,
    MetricRegistryLoader,
)
from shared.normalization.services.similarity_search_service import (
    SimilaritySearchService,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistryCandidate:
    """Searchable canonical registry term."""

    text: str
    normalized_text: str
    canonical_key: str
    source: str


@dataclass(frozen=True)
class RegistryLookup:
    """Deterministic lookup maps and embedding candidates."""

    exact_lookup: Mapping[str, str]
    alias_lookup: Mapping[str, str]
    candidates: tuple[RegistryCandidate, ...]


class EmbeddingMetricNormalizer(IMetricNormalizer):
    """Normalize one financial metric name using exact, alias, then embedding search."""

    def __init__(
        self,
        canonical_metric_registry: Mapping[str, Any] | None = None,
        registry_path: str | Path | None = None,
        registry_loader: MetricRegistryLoader | None = None,
        embedding_generator: EmbeddingGenerator | None = None,
        similarity_search_service: SimilaritySearchService | None = None,
    ) -> None:
        """Initialize the normalizer and build registry lookups."""

        self._registry_loader = registry_loader or MetricRegistryLoader()
        self._embedding_generator = embedding_generator or EmbeddingGenerator()
        self._similarity_search_service = (
            similarity_search_service or SimilaritySearchService()
        )
        self._metrics = self._load_metrics(canonical_metric_registry, registry_path)
        self._lookup = self._build_lookup(self._metrics)
        self._candidate_embeddings: np.ndarray | None = None

    def normalize_metric(self, metric_name: str) -> NormalizedMetric:
        """Normalize a single metric name to a canonical metric key."""

        original_metric = metric_name.strip()
        if not original_metric:
            raise ValueError("metric_name must be a non-empty string.")

        normalized_input = _normalize_text(original_metric)

        exact_match = self._lookup.exact_lookup.get(normalized_input)
        if exact_match is not None:
            logger.info(
                "Metric Found Via Exact Match",
                extra={
                    "original_metric": original_metric,
                    "normalized_metric": exact_match,
                },
            )
            return self._build_result(
                original_metric=original_metric,
                normalized_metric=exact_match,
                confidence=EXACT_MATCH_CONFIDENCE,
            )

        alias_match = self._lookup.alias_lookup.get(normalized_input)
        if alias_match is not None:
            logger.info(
                "Metric Found Via Alias Match",
                extra={
                    "original_metric": original_metric,
                    "normalized_metric": alias_match,
                },
            )
            return self._build_result(
                original_metric=original_metric,
                normalized_metric=alias_match,
                confidence=ALIAS_MATCH_CONFIDENCE,
            )

        return self._normalize_with_embeddings(original_metric)

    def _load_metrics(
        self,
        canonical_metric_registry: Mapping[str, Any] | None,
        registry_path: str | Path | None,
    ) -> tuple[CanonicalMetric, ...]:
        """Load registry metrics from an injected dict, path, or bundled JSON."""

        if canonical_metric_registry is not None:
            return self._registry_loader.load_from_dict(canonical_metric_registry)
        if registry_path is not None:
            return self._registry_loader.load_from_file(registry_path)
        return self._registry_loader.load_default()

    def _build_lookup(
        self,
        metrics: tuple[CanonicalMetric, ...],
    ) -> RegistryLookup:
        """Build exact and alias lookup maps plus embedding candidates."""

        exact_lookup: dict[str, str] = {}
        alias_lookup: dict[str, str] = {}
        candidates: list[RegistryCandidate] = []
        seen_candidates: set[tuple[str, str]] = set()

        for metric in metrics:
            exact_terms = tuple(
                dict.fromkeys((metric.key, metric.display_name, _normalize_key(metric.key)))
            )
            for term in exact_terms:
                normalized = _normalize_text(term)
                if not normalized:
                    continue
                exact_lookup.setdefault(normalized, metric.key)
                candidate = (normalized, metric.key)
                if candidate not in seen_candidates:
                    candidates.append(
                        RegistryCandidate(
                            text=term,
                            normalized_text=normalized,
                            canonical_key=metric.key,
                            source="canonical",
                        )
                    )
                    seen_candidates.add(candidate)

            for alias in metric.aliases:
                normalized_alias = _normalize_text(alias)
                if not normalized_alias:
                    continue
                alias_lookup.setdefault(normalized_alias, metric.key)
                candidate = (normalized_alias, metric.key)
                if candidate not in seen_candidates:
                    candidates.append(
                        RegistryCandidate(
                            text=alias,
                            normalized_text=normalized_alias,
                            canonical_key=metric.key,
                            source="alias",
                        )
                    )
                    seen_candidates.add(candidate)

        return RegistryLookup(
            exact_lookup=exact_lookup,
            alias_lookup=alias_lookup,
            candidates=tuple(candidates),
        )

    def _normalize_with_embeddings(self, original_metric: str) -> NormalizedMetric:
        """Normalize a metric name with embedding similarity search."""

        candidate_embeddings = self._get_candidate_embeddings()
        query_embedding = self._embedding_generator.generate([original_metric])[0]
        match = self._similarity_search_service.search_best(
            query_embedding=query_embedding,
            candidate_embeddings=candidate_embeddings,
        )

        if match is None:
            return self._build_result(
                original_metric=original_metric,
                normalized_metric=None,
                confidence=0.0,
            )

        candidate = self._lookup.candidates[match.index]
        result = self._build_result(
            original_metric=original_metric,
            normalized_metric=candidate.canonical_key,
            confidence=match.score,
        )

        if result.requires_review:
            logger.info(
                "Metric Requires Review",
                extra={
                    "original_metric": original_metric,
                    "best_match": candidate.canonical_key,
                    "confidence": result.confidence,
                },
            )
        elif result.confidence < HIGH_CONFIDENCE_THRESHOLD:
            logger.warning(
                "Metric Found Via Embedding Search",
                extra={
                    "original_metric": original_metric,
                    "normalized_metric": result.normalized_metric,
                    "confidence": result.confidence,
                },
            )
        else:
            logger.info(
                "Metric Found Via Embedding Search",
                extra={
                    "original_metric": original_metric,
                    "normalized_metric": result.normalized_metric,
                    "confidence": result.confidence,
                },
            )

        return result

    def _get_candidate_embeddings(self) -> np.ndarray:
        """Return cached registry candidate embeddings."""

        if self._candidate_embeddings is None:
            self._candidate_embeddings = self._embedding_generator.generate(
                [candidate.text for candidate in self._lookup.candidates]
            )
        return self._candidate_embeddings

    def _build_result(
        self,
        original_metric: str,
        normalized_metric: str | None,
        confidence: float,
    ) -> NormalizedMetric:
        """Build a normalized metric result using threshold rules."""

        clamped_confidence = max(0.0, min(1.0, float(confidence)))
        requires_review = clamped_confidence < MEDIUM_CONFIDENCE_THRESHOLD
        return NormalizedMetric(
            original_metric=original_metric,
            normalized_metric=None if requires_review else normalized_metric,
            confidence=clamped_confidence,
            requires_review=requires_review,
        )


def _normalize_key(value: str) -> str:
    """Normalize text into canonical key style."""

    return _normalize_text(value).replace(" ", "_")


def _normalize_text(value: str) -> str:
    """Normalize metric text for deterministic exact and alias matching."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
