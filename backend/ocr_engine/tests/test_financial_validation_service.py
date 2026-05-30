"""Unit tests for the financial validation service."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.financial_validation_service import FinancialValidationService
from ocr_engine.validation.validators.base import RuleValidator, ValidationContext


class FakeValidator(RuleValidator):
    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                rule_name="fake_major_rule",
                expected="ok",
                actual="bad",
                severity="major",
                message="Fake validator issue.",
            )
        ]


class FailingValidator(RuleValidator):
    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        raise RuntimeError("boom")


def _classification_result() -> FinancialTableClassificationResult:
    return FinancialTableClassificationResult(
        page_table_types=[PageTableType(page_number=1, table_types=["balance_sheet"])]
    )


def test_financial_validation_service_aggregates_issues_and_score() -> None:
    service = FinancialValidationService(
        validators=[FakeValidator(), FailingValidator()]
    )

    result = service.validate(
        classification_result=_classification_result(),
        table_extraction_result=TableExtractionResult(tables=[]),
    )

    assert result.validation_score == 80.0
    assert result.is_valid is True
    assert [issue.rule_name for issue in result.issues] == [
        "fake_major_rule",
        "FailingValidator",
    ]


def test_financial_validation_service_logs_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = FinancialValidationService(validators=[FakeValidator()])

    with caplog.at_level(logging.INFO):
        service.validate(
            classification_result=_classification_result(),
            table_extraction_result=TableExtractionResult(tables=[]),
        )

    assert "Starting financial validation" in caplog.text
    assert "Financial validation completed" in caplog.text
