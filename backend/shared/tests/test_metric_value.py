"""Unit tests for the shared MetricValue model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.models.metric_value import MetricValue


def test_metric_value_accepts_valid_payload() -> None:
    metric_value = MetricValue(
        metric="revenue",
        year=2024,
        value=1500000.0,
    )

    assert metric_value.model_dump() == {
        "metric": "revenue",
        "year": 2024,
        "value": 1500000.0,
    }


def test_metric_value_requires_non_empty_metric() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MetricValue(metric="", year=2024, value=1500000.0)

    assert exc_info.value.errors()[0]["type"] == "string_too_short"


def test_metric_value_requires_year_at_or_after_1900() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MetricValue(metric="revenue", year=1899, value=1500000.0)

    assert exc_info.value.errors()[0]["type"] == "greater_than_equal"


def test_metric_value_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MetricValue(
            metric="revenue",
            year=2024,
            value=1500000.0,
            company_name="Maple Leaf Cement Factory Limited",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
