"""Embedding generation for shared metric normalization."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np

from shared.normalization.constants.normalization_constants import (
    DEFAULT_EMBEDDING_MODEL_NAME,
)


class SupportsEncode(Protocol):
    """Protocol for sentence-transformer-compatible embedding models."""

    def encode(
        self,
        sentences: Sequence[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        """Generate embeddings for a batch of sentences."""


class EmbeddingGenerator:
    """Generate sentence-transformer embeddings with lazy model loading."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
        model: SupportsEncode | None = None,
    ) -> None:
        """Initialize the generator with an optional injected model."""

        self._model_name = model_name
        self._model = model

    def generate(self, texts: Sequence[str]) -> np.ndarray:
        """Return normalized embeddings for a batch of metric names."""

        if not texts:
            return np.empty((0, 0), dtype=float)

        model = self._get_model()
        embeddings = model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=float)

    def _get_model(self) -> SupportsEncode:
        """Load sentence-transformers only when embedding search is used."""

        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError(
                "sentence-transformers is required for embedding metric "
                "normalization. Install sentence-transformers or inject a "
                "compatible embedding model."
            ) from exc

        self._model = SentenceTransformer(self._model_name)
        return self._model
