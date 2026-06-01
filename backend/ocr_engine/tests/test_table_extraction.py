"""Unit tests for table extraction models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_extraction import (
    ExtractedTable,
    ExtractionSummary,
    PageExtractionDiagnostic,
    TableExtractionResult,
)


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
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "balance_sheet",
                "table_index": 0,
                "source_table_index": 0,
                "split_table_index": None,
                "split_reason": None,
                "rows": [
                    ["Cash", "1000"],
                    ["Inventory", "500"],
                ],
                "metric_values": [],
            }
        ],
        "metric_values": [],
        "extraction_summary": {
            "total_detected_tables": 0,
            "total_classified_tables": 0,
            "total_extracted_tables": 0,
            "total_matched_tables": 0,
            "unmatched_classifications": [],
            "unmatched_extractions": [],
            "page_diagnostics": [],
            "tables_split": 0,
            "split_reasons": [],
            "logical_types_created": [],
            "quality_report": {
                "tables_extracted": 0,
                "tables_rejected": 0,
                "metric_values_generated": 0,
                "duplicate_metric_group_count": 0,
                "duplicate_metric_value_count": 0,
                "conflicting_metric_group_count": 0,
                "missing_year_table_count": 0,
                "missing_label_table_count": 0,
                "numeric_only_table_count": 0,
                "unclassified_table_count": 0,
                "labels_reconstructed": 0,
                "metric_values_improved_by_label_reconstruction": 0,
                "confidence_distribution": {},
                "top_suspicious_tables": [],
                "top_suspicious_metrics": [],
                "label_reconstruction_diagnostics": [],
            },
        },
    }


def test_extraction_summary_serializes_page_diagnostics() -> None:
    summary = ExtractionSummary(
        total_detected_tables=2,
        total_classified_tables=2,
        total_extracted_tables=1,
        total_matched_tables=1,
        unmatched_classifications=["page=20 table_type=balance_sheet"],
        unmatched_extractions=[],
        page_diagnostics=[
            PageExtractionDiagnostic(
                source_report_year=2024,
                page_number=20,
                detected_table_count=2,
                classified_table_count=2,
                extracted_table_count=1,
                matched_table_count=1,
                unmatched_classifications=["balance_sheet"],
                unmatched_extractions=[],
            )
        ],
    )

    assert summary.model_dump()["page_diagnostics"][0] == {
        "source_report_year": 2024,
        "page_number": 20,
        "detected_table_count": 2,
        "classified_table_count": 2,
        "extracted_table_count": 1,
        "matched_table_count": 1,
        "extraction_strategy": "unknown",
        "quality_score": 0.0,
        "year_column_count": 0,
        "metric_label_count": 0,
        "metric_value_count": 0,
        "numeric_only_table_count": 0,
        "unmatched_classifications": ["balance_sheet"],
        "unmatched_extractions": [],
        "tables_split": 0,
        "split_reason": None,
        "logical_types_created": [],
    }


def test_table_extraction_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TableExtractionResult(
            tables=[],
            extraction_version="v1",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
