"""Unit tests for OCR table normalization models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_normalization import (
    MetricMapping,
    NormalizationResult,
    NormalizedTable,
)


def test_normalized_table_accepts_valid_payload() -> None:
    table = NormalizedTable(
        year=2024,
        page_number=20,
        table_type="income_statement",
        table_index=0,
        detected_table_id="2024:20:0",
        page_table_index=0,
        bbox=[72.0, 144.0, 540.0, 320.0],
        detection_confidence=0.97,
        match_method="detected_table_id",
        rows=[["revenue", "1200000"]],
    )

    assert table.page_number == 20
    assert table.rows == [["revenue", "1200000"]]
    assert table.detected_table_id == "2024:20:0"
    assert table.match_method == "detected_table_id"


def test_normalized_table_requires_positive_page_number() -> None:
    with pytest.raises(ValidationError) as exc_info:
        NormalizedTable(
            year=2024,
            page_number=0,
            table_type="income_statement",
            table_index=0,
            rows=[],
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


def test_normalization_result_serializes_expected_output() -> None:
    result = NormalizationResult(
        tables=[
            NormalizedTable(
                year=2024,
                page_number=20,
                table_type="income_statement",
                table_index=0,
                rows=[["revenue", "1200000"]],
            )
        ]
    )

    assert result.model_dump() == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "income_statement",
                "table_index": 0,
                "source_table_index": 0,
                "split_table_index": None,
                "split_reason": None,
                "detected_table_id": None,
                "page_table_index": None,
                "bbox": None,
                "detection_confidence": None,
                "match_method": None,
                "rows": [["revenue", "1200000"]],
                "metric_values": [],
            }
        ],
        "metric_values": [],
        "mappings": [],
    }


def test_metric_mapping_preserves_year_and_review_state() -> None:
    mapping = MetricMapping(
        value_year=2024,
        source_report_year=2025,
        original_metric="Net Sales",
        normalized_metric="revenue",
        confidence=0.96,
        requires_review=False,
    )

    assert mapping.model_dump() == {
        "value_year": 2024,
        "source_report_year": 2025,
        "original_metric": "Net Sales",
        "normalized_metric": "revenue",
        "confidence": 0.96,
        "requires_review": False,
        "page_number": None,
        "table_type": None,
        "table_index": None,
        "detected_table_id": None,
        "match_method": None,
        "normalization_input_metric": None,
        "parent_metric_context": None,
        "child_metric": None,
        "parent_prefix_stripped": False,
        "normalization_rule": None,
    }


def test_normalization_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        NormalizationResult(tables=[], mappings=[], extra_field=True)

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
