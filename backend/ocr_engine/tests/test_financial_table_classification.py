"""Unit tests for financial table classification models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)


def test_page_table_type_accepts_valid_payload() -> None:
    page_table_type = PageTableType(
        page_number=20,
        table_types=["balance_sheet", "debt_schedule"],
    )

    assert page_table_type.page_number == 20
    assert page_table_type.table_types == ["balance_sheet", "debt_schedule"]


def test_page_table_type_accepts_unknown_table_types() -> None:
    page_table_type = PageTableType(
        page_number=72,
        table_types=["regulatory_capital_adequacy_note"],
    )

    assert page_table_type.table_types == ["regulatory_capital_adequacy_note"]


def test_page_table_type_requires_positive_page_number() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PageTableType(
            page_number=0,
            table_types=["income_statement"],
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


def test_page_table_type_rejects_empty_table_type() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PageTableType(
            page_number=25,
            table_types=[""],
        )

    assert exc_info.value.errors()[0]["type"] == "string_too_short"


def test_page_table_type_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PageTableType(
            page_number=20,
            table_types=["balance_sheet"],
            extraction_status="pending",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_financial_table_classification_result_serializes_expected_output() -> None:
    result = FinancialTableClassificationResult(
        page_table_types=[
            PageTableType(
                page_number=20,
                table_types=["balance_sheet", "debt_schedule"],
            ),
            PageTableType(
                page_number=25,
                table_types=["income_statement"],
            ),
        ]
    )

    assert result.model_dump() == {
        "page_table_types": [
            {
                "page_number": 20,
                "table_types": ["balance_sheet", "debt_schedule"],
            },
            {
                "page_number": 25,
                "table_types": ["income_statement"],
            },
        ]
    }


def test_financial_table_classification_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FinancialTableClassificationResult(
            page_table_types=[],
            model_version="v1",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
