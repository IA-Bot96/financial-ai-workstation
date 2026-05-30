"""Helpers for validation layer unit tests."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.validation.validators.base import ValidationContext, build_validation_context


def extracted_table(
    rows: list[list[str]],
    table_type: str,
    page_number: int = 1,
    table_index: int = 0,
) -> ExtractedTable:
    return ExtractedTable(
        page_number=page_number,
        table_type=table_type,
        table_index=table_index,
        rows=rows,
    )


def classification_result(
    page_number: int = 1,
    table_types: list[str] | None = None,
) -> FinancialTableClassificationResult:
    return FinancialTableClassificationResult(
        page_table_types=[
            PageTableType(
                page_number=page_number,
                table_types=table_types or ["balance_sheet"],
            )
        ]
    )


def context_for(tables: list[ExtractedTable]) -> ValidationContext:
    return build_validation_context(
        classification_result=classification_result(
            table_types=list({table.table_type for table in tables})
        ),
        table_extraction_result=TableExtractionResult(tables=tables),
    )


def rule_names(issues: list[object]) -> set[str]:
    return {issue.rule_name for issue in issues}
