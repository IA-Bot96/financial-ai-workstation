"""Unit tests for workbook population Pydantic models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from workbook_population.models.template_validation_result import (
    TemplateValidationResult,
)
from workbook_population.models.sheet_validation_result import SheetValidationResult
from workbook_population.models.workbook_result import WorkbookResult


def test_workbook_result_accepts_valid_payload() -> None:
    result = WorkbookResult(
        output_file_path="output/company_model.xlsx",
        workbook_mode="template",
        workbook_match_score=97.5,
        sheets_reused=["Income Statement"],
        sheets_replaced=[],
        sheets_created=["Insights"],
        metrics_written=432,
        warnings=[],
    )

    assert result.model_dump()["workbook_mode"] == "template"


def test_workbook_result_bounds_workbook_match_score() -> None:
    with pytest.raises(ValidationError) as exc_info:
        WorkbookResult(
            output_file_path="output/company_model.xlsx",
            workbook_mode="template",
            workbook_match_score=101,
            sheets_reused=[],
            sheets_replaced=[],
            sheets_created=[],
            metrics_written=0,
            warnings=[],
        )

    assert exc_info.value.errors()[0]["type"] == "less_than_equal"


def test_sheet_validation_result_bounds_match_score() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SheetValidationResult(
            sheet_name="Income Statement",
            match_score=-1,
            is_compatible=False,
            missing_metrics=[],
            extra_metrics=[],
            warnings=[],
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than_equal"


def test_template_validation_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TemplateValidationResult(
            is_match=True,
            match_score=95,
            sheet_results=[],
            missing_metrics=[],
            extra_metrics=[],
            warnings=[],
            mode="template",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
