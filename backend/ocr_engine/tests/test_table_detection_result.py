"""Unit tests for the table detection result model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_detection_result import TableDetectionResult


def test_table_detection_result_accepts_valid_payload() -> None:
    result = TableDetectionResult(
        table_pages=[24, 25, 42],
        total_detected_tables=7,
    )

    assert result.table_pages == [24, 25, 42]
    assert result.total_detected_tables == 7


def test_table_detection_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TableDetectionResult(
            table_pages=[24, 25, 42],
            total_detected_tables=7,
            extraction_status="pending",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_table_detection_result_requires_non_negative_table_count() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TableDetectionResult(
            table_pages=[24],
            total_detected_tables=-1,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than_equal"


def test_table_detection_result_serializes_to_expected_output() -> None:
    result = TableDetectionResult(
        table_pages=[24, 25, 42],
        total_detected_tables=7,
    )

    assert result.model_dump() == {
        "table_pages": [24, 25, 42],
        "total_detected_tables": 7,
    }
