"""Unit tests for table extraction models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult


def test_extracted_table_accepts_valid_payload() -> None:
    table = ExtractedTable(
        year=2024,
        page_number=20,
        table_type="balance_sheet",
        table_index=0,
        rows=[
            ["Cash", "1000"],
            ["Inventory", "500"],
        ],
    )

    assert table.page_number == 20
    assert table.table_type == "balance_sheet"
    assert table.table_index == 0
    assert table.rows[0] == ["Cash", "1000"]


def test_extracted_table_allows_empty_rows() -> None:
    table = ExtractedTable(
        year=2024,
        page_number=72,
        table_type="property_plant_equipment_note",
        table_index=0,
        rows=[],
    )

    assert table.rows == []


def test_extracted_table_requires_positive_page() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExtractedTable(
            year=2024,
            page_number=0,
            table_type="income_statement",
            table_index=0,
            rows=[],
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


def test_extracted_table_requires_non_negative_table_index() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExtractedTable(
            year=2024,
            page_number=20,
            table_type="balance_sheet",
            table_index=-1,
            rows=[],
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than_equal"


def test_extracted_table_requires_rows_as_lists_of_strings() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExtractedTable(
            year=2024,
            page_number=20,
            table_type="balance_sheet",
            table_index=0,
            rows=[["Revenue", 1200000]],
        )

    assert exc_info.value.errors()[0]["type"] == "string_type"


def test_extracted_table_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExtractedTable(
            year=2024,
            page_number=20,
            table_type="balance_sheet",
            table_index=0,
            rows=[],
            headers=["year", "revenue", "debt"],
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_table_extraction_result_serializes_expected_output() -> None:
    result = TableExtractionResult(
        tables=[
            ExtractedTable(
                year=2024,
                page_number=20,
                table_type="balance_sheet",
                table_index=0,
                rows=[
                    ["Cash", "1000"],
                    ["Inventory", "500"],
                ],
            )
        ]
    )

    assert result.model_dump() == {
        "tables": [
            {
                "year": 2024,
                "page_number": 20,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [
                    ["Cash", "1000"],
                    ["Inventory", "500"],
                ],
            }
        ]
    }


def test_table_extraction_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TableExtractionResult(
            tables=[],
            extraction_version="v1",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
