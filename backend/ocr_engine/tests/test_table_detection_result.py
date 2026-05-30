"""Unit tests for the table detection result model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_detection_result import DetectedPage, TableDetectionResult


def test_detected_page_accepts_valid_payload() -> None:
    detected_page = DetectedPage(
        page_number=20,
        tables_detected=3,
    )

    assert detected_page.page_number == 20
    assert detected_page.tables_detected == 3


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("page_number", 0, "greater_than"),
        ("tables_detected", 0, "greater_than"),
    ],
)
def test_detected_page_requires_positive_values(
    field_name: str,
    value: int,
    error_type: str,
) -> None:
    payload = {
        "page_number": 20,
        "tables_detected": 3,
    }
    payload[field_name] = value

    with pytest.raises(ValidationError) as exc_info:
        DetectedPage(**payload)

    assert exc_info.value.errors()[0]["type"] == error_type


def test_detected_page_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DetectedPage(
            page_number=20,
            tables_detected=3,
            confidence=0.97,
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_table_detection_result_accepts_valid_payload() -> None:
    result = TableDetectionResult(
        detected_pages=[
            DetectedPage(page_number=20, tables_detected=3),
            DetectedPage(page_number=25, tables_detected=1),
            DetectedPage(page_number=42, tables_detected=2),
        ],
        total_pages_processed=132,
    )

    assert [page.page_number for page in result.detected_pages] == [20, 25, 42]
    assert [page.tables_detected for page in result.detected_pages] == [3, 1, 2]
    assert result.total_pages_processed == 132


def test_table_detection_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TableDetectionResult(
            detected_pages=[
                DetectedPage(page_number=20, tables_detected=3),
            ],
            total_pages_processed=132,
            extraction_status="pending",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_table_detection_result_requires_non_negative_pages_processed() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TableDetectionResult(
            detected_pages=[
                DetectedPage(page_number=20, tables_detected=3),
            ],
            total_pages_processed=-1,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than_equal"


def test_table_detection_result_serializes_to_expected_output() -> None:
    result = TableDetectionResult(
        detected_pages=[
            DetectedPage(page_number=20, tables_detected=3),
            DetectedPage(page_number=25, tables_detected=1),
            DetectedPage(page_number=42, tables_detected=2),
        ],
        total_pages_processed=132,
    )

    assert result.model_dump() == {
        "detected_pages": [
            {
                "page_number": 20,
                "tables_detected": 3,
            },
            {
                "page_number": 25,
                "tables_detected": 1,
            },
            {
                "page_number": 42,
                "tables_detected": 2,
            },
        ],
        "total_pages_processed": 132,
    }
