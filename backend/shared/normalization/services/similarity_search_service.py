"""Cosine similarity search for shared metric normalization."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SimilarityMatch:
    """Best cosine-similarity match for one query vector."""

    index: int
    score: float


class SimilaritySearchService:
    """Find nearest canonical metric terms using cosine similarity."""

    def search_best(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
    ) -> SimilarityMatch | None:
        """Return the best candidate match for one query embedding."""

        if query_embedding.size == 0 or candidate_embeddings.size == 0:
            return None

        query_matrix = np.asarray(query_embedding, dtype=float).reshape(1, -1)
        candidate_matrix = np.asarray(candidate_embeddings, dtype=float)
        similarities = self._cosine_similarity(query_matrix, candidate_matrix)
        best_index = int(np.argmax(similarities[0]))
        return SimilarityMatch(index=best_index, score=float(similarities[0, best_index]))

    def _cosine_similarity(
        self,
        query_embeddings: np.ndarray,
        candidate_embeddings: np.ndarray,
    ) -> np.ndarray:
        """Calculate cosine similarity, falling back to numpy without sklearn."""

        try:
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            return self._numpy_cosine_similarity(query_embeddings, candidate_embeddings)

        return cosine_similarity(query_embeddings, candidate_embeddings)

    def _numpy_cosine_similarity(
        self,
        query_embeddings: np.ndarray,
        candidate_embeddings: np.ndarray,
    ) -> np.ndarray:
        """Calculate cosine similarity with numpy only."""

        query_norms = np.linalg.norm(query_embeddings, axis=1, keepdims=True)
        candidate_norms = np.linalg.norm(candidate_embeddings, axis=1, keepdims=True)
        query_norms[query_norms == 0] = 1
        candidate_norms[candidate_norms == 0] = 1
        normalized_queries = query_embeddings / query_norms
        normalized_candidates = candidate_embeddings / candidate_norms
        return normalized_queries @ normalized_candidates.T
