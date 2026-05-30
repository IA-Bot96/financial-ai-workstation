"""Unit tests for the financial fact model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_fact_extraction import FinancialFact


def test_financial_fact_accepts_numeric_value() -> None:
    fact = FinancialFact(
        year=2024,
        metric="revenue",
        value=1200000,
        page_number=20,
        table_type="income_statement",
    )

    assert fact.model_dump() == {
        "year": 2024,
        "metric": "revenue",
        "value": 1200000,
        "page_number": 20,
        "table_type": "income_statement",
    }


def test_financial_fact_accepts_text_value() -> None:
    fact = FinancialFact(
        year=2024,
        metric="net_profit_margin",
        value="12.5%",
        page_number=21,
        table_type="income_statement",
    )

    assert fact.value == "12.5%"


@pytest.mark.parametrize("field_name", ["metric", "table_type"])
def test_financial_fact_requires_non_empty_text_fields(field_name: str) -> None:
    payload = {
        "year": 2024,
        "metric": "revenue",
        "value": 1200000,
        "page_number": 20,
        "table_type": "income_statement",
    }
    payload[field_name] = ""

    with pytest.raises(ValidationError) as exc_info:
        FinancialFact(**payload)

    assert exc_info.value.errors()[0]["type"] == "string_too_short"


def test_financial_fact_requires_positive_page() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FinancialFact(
            year=2024,
            metric="revenue",
            value=1200000,
            page_number=0,
            table_type="income_statement",
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


def test_financial_fact_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FinancialFact(
            year=2024,
            metric="revenue",
            value=1200000,
            page_number=20,
            table_type="income_statement",
            normalized_name="revenue",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
