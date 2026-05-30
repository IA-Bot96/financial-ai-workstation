"""Unit tests for the shared normalized metric model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.normalization.models.normalized_metric import NormalizedMetric


def test_normalized_metric_accepts_valid_payload() -> None:
    metric = NormalizedMetric(
        original_metric="Net Sales",
        normalized_metric="revenue",
        confidence=0.96,
        requires_review=False,
    )

    assert metric.model_dump() == {
        "original_metric": "Net Sales",
        "normalized_metric": "revenue",
        "confidence": 0.96,
        "requires_review": False,
    }


def test_normalized_metric_allows_review_without_normalized_metric() -> None:
    metric = NormalizedMetric(
        original_metric="Unclear OCR Label",
        normalized_metric=None,
        confidence=0.42,
        requires_review=True,
    )

    assert metric.normalized_metric is None
    assert metric.requires_review is True


def test_normalized_metric_bounds_confidence() -> None:
    with pytest.raises(ValidationError) as exc_info:
        NormalizedMetric(
            original_metric="Net Sales",
            normalized_metric="revenue",
            confidence=1.2,
            requires_review=False,
        )

    assert exc_info.value.errors()[0]["type"] == "less_than_equal"


def test_normalized_metric_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        NormalizedMetric(
            original_metric="Net Sales",
            normalized_metric="revenue",
            confidence=0.96,
            requires_review=False,
            source="alias",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
