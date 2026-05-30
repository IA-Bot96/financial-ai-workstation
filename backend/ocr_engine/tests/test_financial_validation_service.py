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
from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.financial_validation_service import FinancialValidationService
from ocr_engine.validation.validators.base import RuleValidator, ValidationContext
from shared.models.company_context import CompanyContext
from shared.models.report import Report


class FakeValidator(RuleValidator):
    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                year=context.primary_year,
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


class RecordingValidator(RuleValidator):
    def __init__(self) -> None:
        self.seen_contexts: list[tuple[int, set[int], set[int]]] = []

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        classification_years = {
            page_table_type.year
            for page_table_type in context.classification_result.page_table_types
        }
        extraction_years = {
            table.year for table in context.table_extraction_result.tables
        }
        self.seen_contexts.append(
            (context.primary_year, classification_years, extraction_years)
        )
        return [
            ValidationIssue(
                year=context.primary_year,
                rule_name=f"recorded_year_{context.primary_year}",
                expected="single-year context",
                actual="single-year context",
                severity="major",
                message="Year-specific validation executed.",
            )
        ]


def _classification_result() -> FinancialTableClassificationResult:
    return FinancialTableClassificationResult(
        page_table_types=[
            PageTableType(year=2024, page_number=1, table_types=["balance_sheet"])
        ]
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


def test_validate_for_context_stores_results_by_report_year() -> None:
    validator = RecordingValidator()
    service = FinancialValidationService(validators=[validator])
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2023_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2023,
                file_name="MLCF_2023_Annual_Report.pdf",
                file_path="reports/MLCF_2023.pdf",
            ),
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            ),
        ],
        classification_results={
            2023: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2023,
                        page_number=10,
                        table_types=["balance_sheet"],
                    )
                ]
            ),
            2024: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement"],
                    )
                ]
            ),
        },
        extraction_results={
            2023: TableExtractionResult(
                tables=[
                    ExtractedTable(
                        year=2023,
                        page_number=10,
                        table_type="balance_sheet",
                        table_index=0,
                        rows=[["Total assets", "1000"]],
                    )
                ]
            ),
            2024: TableExtractionResult(
                tables=[
                    ExtractedTable(
                        year=2024,
                        page_number=20,
                        table_type="income_statement",
                        table_index=0,
                        rows=[["Revenue", "1200"]],
                    )
                ]
            ),
        },
    )

    updated_context = service.validate_for_context(context)

    assert updated_context is context
    assert set(context.validation_results) == {2023, 2024}
    assert context.validation_results[2023].issues[0].year == 2023
    assert context.validation_results[2024].issues[0].year == 2024
    assert validator.seen_contexts == [
        (2023, {2023}, {2023}),
        (2024, {2024}, {2024}),
    ]
    assert context.validation_results[2023] is not context.validation_results[2024]


def test_validate_for_context_requires_classification_result_per_year() -> None:
    service = FinancialValidationService(validators=[])
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
    )

    with pytest.raises(ValueError, match="Missing financial table classification"):
        service.validate_for_context(context)


def test_validate_for_context_requires_extraction_result_per_year() -> None:
    service = FinancialValidationService(validators=[])
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
        classification_results={2024: _classification_result()},
    )

    with pytest.raises(ValueError, match="Missing table extraction result"):
        service.validate_for_context(context)


def test_validate_for_context_rejects_contaminated_year_bucket() -> None:
    service = FinancialValidationService(validators=[])
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
        classification_results={2024: _classification_result()},
        extraction_results={
            2024: TableExtractionResult(
                tables=[
                    ExtractedTable(
                        year=2023,
                        page_number=20,
                        table_type="balance_sheet",
                        table_index=0,
                        rows=[["Total assets", "1000"]],
                    )
                ]
            )
        },
    )

    with pytest.raises(ValueError, match="contain data from other years"):
        service.validate_for_context(context)


def test_validate_rejects_merged_multi_year_inputs() -> None:
    service = FinancialValidationService(validators=[])

    with pytest.raises(ValueError, match="single report year"):
        service.validate(
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2023,
                        page_number=10,
                        table_types=["balance_sheet"],
                    ),
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement"],
                    ),
                ]
            ),
            table_extraction_result=TableExtractionResult(tables=[]),
        )
