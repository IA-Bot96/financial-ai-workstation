"""Unit tests for financial table classification models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassification,
    FinancialTableClassificationResult,
)


def test_financial_table_classification_accepts_valid_payload() -> None:
    classification = FinancialTableClassification(
        page=20,
        table_type="balance_sheet",
        confidence=0.97,
    )

    assert classification.page == 20
    assert classification.table_type == "balance_sheet"
    assert classification.confidence == 0.97


def test_financial_table_classification_accepts_unknown_table_type() -> None:
    classification = FinancialTableClassification(
        page=72,
        table_type="regulatory_capital_adequacy_note",
        confidence=0.89,
    )

    assert classification.table_type == "regulatory_capital_adequacy_note"


def test_financial_table_classification_requires_positive_page() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FinancialTableClassification(
            page=0,
            table_type="income_statement",
            confidence=0.95,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_financial_table_classification_bounds_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        FinancialTableClassification(
            page=25,
            table_type="income_statement",
            confidence=confidence,
        )


def test_financial_table_classification_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FinancialTableClassification(
            page=20,
            table_type="balance_sheet",
            confidence=0.97,
            extraction_status="pending",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_financial_table_classification_result_serializes_expected_output() -> None:
    result = FinancialTableClassificationResult(
        classifications=[
            FinancialTableClassification(
                page=20,
                table_type="balance_sheet",
                confidence=0.97,
            ),
            FinancialTableClassification(
                page=25,
                table_type="income_statement",
                confidence=0.95,
            ),
            FinancialTableClassification(
                page=72,
                table_type="property_plant_equipment_note",
                confidence=0.89,
            ),
        ]
    )

    assert result.model_dump() == {
        "classifications": [
            {
                "page": 20,
                "table_type": "balance_sheet",
                "confidence": 0.97,
            },
            {
                "page": 25,
                "table_type": "income_statement",
                "confidence": 0.95,
            },
            {
                "page": 72,
                "table_type": "property_plant_equipment_note",
                "confidence": 0.89,
            },
        ]
    }


def test_financial_table_classification_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FinancialTableClassificationResult(
            classifications=[],
            model_version="v1",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
