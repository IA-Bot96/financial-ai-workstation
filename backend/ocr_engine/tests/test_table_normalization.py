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
        rows=[["revenue", "1200000"]],
    )

    assert table.page_number == 20
    assert table.rows == [["revenue", "1200000"]]


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
                "year": 2024,
                "page_number": 20,
                "table_type": "income_statement",
                "table_index": 0,
                "rows": [["revenue", "1200000"]],
            }
        ],
        "mappings": [],
    }


def test_metric_mapping_preserves_year_and_review_state() -> None:
    mapping = MetricMapping(
        year=2024,
        original_metric="Net Sales",
        normalized_metric="revenue",
        confidence=0.96,
        requires_review=False,
    )

    assert mapping.model_dump() == {
        "year": 2024,
        "original_metric": "Net Sales",
        "normalized_metric": "revenue",
        "confidence": 0.96,
        "requires_review": False,
    }


def test_normalization_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        NormalizationResult(tables=[], mappings=[], extra_field=True)

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
