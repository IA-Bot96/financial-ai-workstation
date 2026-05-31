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
from ocr_engine.validation.financial_validation_service import (
    FinancialValidationService,
)
from ocr_engine.validation.validators.balance_sheet_validator import (
    BalanceSheetValidator,
)
from ocr_engine.validation.validators.base import (
    RuleValidator,
    ValidationContext,
    build_validation_context,
    parse_number,
)
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue
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


class CriticalValidator(RuleValidator):
    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                year=context.primary_year,
                rule_name="critical_rule",
                expected="balanced",
                actual="unbalanced",
                severity="critical",
                message="Critical validation issue.",
            )
        ]


class DuplicateIssueValidator(RuleValidator):
    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                year=context.primary_year,
                rule_name="same_structural_issue",
                expected="present",
                actual="missing",
                severity="major",
                message="Same issue repeated for each value year.",
            )
        ]


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


def test_financial_validation_service_critical_issue_fails_regardless_of_score(
) -> None:
    service = FinancialValidationService(validators=[CriticalValidator()])

    result = service.validate(
        classification_result=_classification_result(),
        table_extraction_result=TableExtractionResult(tables=[]),
    )

    assert result.validation_score == 80.0
    assert result.is_valid is False


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


def test_validate_executes_rules_independently_by_value_year() -> None:
    validator = RecordingValidator()
    service = FinancialValidationService(validators=[validator])

    result = service.validate(
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=120,
                    table_types=["balance_sheet"],
                )
            ]
        ),
        table_extraction_result=TableExtractionResult(
            tables=[
                ExtractedTable(
                    source_report_year=2025,
                    page_number=120,
                    table_type="balance_sheet",
                    table_index=0,
                    rows=[],
                )
            ],
            metric_values=[
                MetricValue(
                    metric="total_assets",
                    value_year=2025,
                    value=100,
                    source_report_year=2025,
                    page_number=120,
                    table_type="balance_sheet",
                ),
                MetricValue(
                    metric="total_assets",
                    value_year=2024,
                    value=80,
                    source_report_year=2025,
                    page_number=120,
                    table_type="balance_sheet",
                ),
            ],
        ),
    )

    assert [context[0] for context in validator.seen_contexts] == [2024, 2025]
    assert [issue.year for issue in result.issues] == [2024, 2025]


def test_validate_scores_repeated_multi_year_issues_once() -> None:
    service = FinancialValidationService(validators=[DuplicateIssueValidator()])

    result = service.validate(
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=120,
                    table_types=["balance_sheet"],
                )
            ]
        ),
        table_extraction_result=TableExtractionResult(
            tables=[
                ExtractedTable(
                    source_report_year=2025,
                    page_number=120,
                    table_type="balance_sheet",
                    table_index=0,
                    rows=[],
                )
            ],
            metric_values=[
                MetricValue(
                    metric="total_assets",
                    value_year=2025,
                    value=100,
                    source_report_year=2025,
                    page_number=120,
                    table_type="balance_sheet",
                ),
                MetricValue(
                    metric="total_assets",
                    value_year=2024,
                    value=80,
                    source_report_year=2025,
                    page_number=120,
                    table_type="balance_sheet",
                ),
            ],
        ),
    )

    assert [issue.year for issue in result.issues] == [2024, 2025]
    assert result.validation_score == 90.0


def test_validation_parses_common_financial_scales() -> None:
    assert parse_number("Rs 2 thousand") == 2_000
    assert parse_number("Rs 2 million") == 2_000_000
    assert parse_number("Rs 2 billion") == 2_000_000_000


def test_validation_context_applies_table_scale_to_raw_values() -> None:
    context = build_validation_context(
        classification_result=_classification_result(),
        table_extraction_result=TableExtractionResult(
            tables=[
                ExtractedTable(
                    source_report_year=2024,
                    page_number=1,
                    table_type="balance_sheet",
                    table_index=0,
                    rows=[
                        ["Amounts in million"],
                        ["Particulars", "2024"],
                        ["Total assets", "2"],
                        ["Total liabilities", "1.2"],
                        ["Total equity", "0.8"],
                    ],
                )
            ]
        ),
    )

    assert context.value_for("total_assets") == 2_000_000
    assert BalanceSheetValidator().validate(context) == []


def test_validation_ignores_note_reference_columns() -> None:
    context = build_validation_context(
        classification_result=_classification_result(),
        table_extraction_result=TableExtractionResult(
            tables=[
                ExtractedTable(
                    source_report_year=2024,
                    page_number=1,
                    table_type="balance_sheet",
                    table_index=0,
                    rows=[
                        ["Particulars", "Note", "2024"],
                        ["Total assets", "4", "2500"],
                        ["Total liabilities", "5", "1500"],
                        ["Total equity", "6", "1000"],
                    ],
                )
            ]
        ),
    )

    assert context.value_for("total_assets") == 2500
    assert BalanceSheetValidator().validate(context) == []


def test_accounting_equation_uses_tight_tolerance() -> None:
    context = build_validation_context(
        classification_result=_classification_result(),
        table_extraction_result=TableExtractionResult(
            tables=[
                ExtractedTable(
                    source_report_year=2024,
                    page_number=1,
                    table_type="balance_sheet",
                    table_index=0,
                    rows=[
                        ["Particulars", "2024"],
                        ["Total assets", "1000.75"],
                        ["Total liabilities", "500"],
                        ["Total equity", "500"],
                    ],
                )
            ]
        ),
    )

    issues = BalanceSheetValidator().validate(context)

    assert "accounting_equation" in {issue.rule_name for issue in issues}
