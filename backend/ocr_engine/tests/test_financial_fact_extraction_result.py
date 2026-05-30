"""Unit tests for the financial fact extraction result model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_fact_extraction import (
    FinancialFact,
    FinancialFactExtractionResult,
)


def test_financial_fact_extraction_result_serializes_expected_output() -> None:
    result = FinancialFactExtractionResult(
        facts=[
            FinancialFact(
                name="Revenue",
                value=1200000,
                page=20,
                table_type="income_statement",
            )
        ]
    )

    assert result.model_dump() == {
        "facts": [
            {
                "name": "Revenue",
                "value": 1200000,
                "page": 20,
                "table_type": "income_statement",
            }
        ]
    }


def test_financial_fact_extraction_result_allows_empty_facts() -> None:
    result = FinancialFactExtractionResult(facts=[])

    assert result.facts == []


def test_financial_fact_extraction_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FinancialFactExtractionResult(
            facts=[],
            model_version="v1",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
