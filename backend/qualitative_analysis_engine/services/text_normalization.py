"""Text normalization helpers for deterministic taxonomy matching."""

from __future__ import annotations

import re


def normalize_text(value: str) -> str:
    """Normalize source text for taxonomy matching."""

    normalized = value.lower().replace("&", " and ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


__all__ = ["normalize_text"]

