"""Unit tests for shared cosine similarity search."""

import sys
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.normalization.services.similarity_search_service import (
    SimilaritySearchService,
)


def test_similarity_search_returns_best_candidate() -> None:
    service = SimilaritySearchService()

    match = service.search_best(
        query_embedding=np.array([0.0, 1.0]),
        candidate_embeddings=np.array([[1.0, 0.0], [0.0, 1.0]]),
    )

    assert match is not None
    assert match.index == 1
    assert match.score == 1.0


def test_similarity_search_returns_none_for_empty_candidates() -> None:
    service = SimilaritySearchService()

    match = service.search_best(
        query_embedding=np.array([0.0, 1.0]),
        candidate_embeddings=np.empty((0, 2)),
    )

    assert match is None
