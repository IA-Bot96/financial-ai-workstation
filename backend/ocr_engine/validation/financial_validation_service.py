"""Financial validation service that aggregates rule-based validators."""

from __future__ import annotations

import logging
from typing import Sequence

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.validation_result import ValidationIssue, ValidationResult
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.validation.interfaces.validation_service import IValidationService
from ocr_engine.validation.scoring.validation_score_calculator import (
    ValidationScoreCalculator,
)
from ocr_engine.validation.validators import (
    BalanceSheetValidator,
    CashFlowValidator,
    CompletenessValidator,
    CrossStatementValidator,
    IncomeStatementValidator,
    OCRValidator,
    RatioValidator,
)
from ocr_engine.validation.validators.base import (
    RuleValidator,
    ValidationContext,
    build_validation_context,
    make_issue,
)
from shared.models.company_context import CompanyContext

logger = logging.getLogger(__name__)


class FinancialValidationService(IValidationService):
    """Validate extracted OCR financial tables using accounting rules."""

    def __init__(
        self,
        validators: Sequence[RuleValidator] | None = None,
        score_calculator: ValidationScoreCalculator | None = None,
    ) -> None:
        """Initialize the service with injectable validators and scoring."""

        self._validators = tuple(validators) if validators is not None else (
            BalanceSheetValidator(),
            IncomeStatementValidator(),
            CashFlowValidator(),
            CrossStatementValidator(),
            RatioValidator(),
            OCRValidator(),
            CompletenessValidator(),
        )
        self._score_calculator = score_calculator or ValidationScoreCalculator()

    def validate_for_context(self, context: CompanyContext) -> CompanyContext:
        """Validate each report year independently and store results by year.

        This method reads classification and extraction results from the same
        year bucket, runs validators only on that year's data, and writes to
        ``context.validation_results[report.year]``.
        """

        logger.info(
            "Starting financial validation for company context",
            extra={
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )

        failures: list[str] = []
        for report in context.reports:
            try:
                classification_result = context.classification_results.get(
                    report.year
                )
                if classification_result is None:
                    raise ValueError(
                        "Missing financial table classification result for "
                        f"report year {report.year}."
                    )

                extraction_result = context.extraction_results.get(report.year)
                if extraction_result is None:
                    raise ValueError(
                        "Missing table extraction result for report year "
                        f"{report.year}."
                    )

                self._ensure_results_match_year(
                    report.year,
                    classification_result,
                    extraction_result,
                )
                logger.info(
                    "Validating extracted tables for report year %s",
                    report.year,
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                    },
                )
                context.validation_results[report.year] = self.validate(
                    classification_result=classification_result,
                    table_extraction_result=extraction_result,
                )
            except Exception as exc:
                failures.append(
                    f"Report year {report.year} failed financial validation: "
                    f"{_error_message(exc)}"
                )
                context.validation_results[report.year] = ValidationResult(
                    is_valid=False,
                    validation_score=0,
                    issues=[],
                )
                logger.exception(
                    "Financial validation failed for report; continuing",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                    },
                )
                continue

        logger.info(
            "Company context financial validation complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.validation_results),
            },
        )
        if failures:
            raise PipelineLayerPartialFailure(failures, context=context)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run financial validation as a pipeline layer."""

        return self.validate_for_context(context)

    def validate(
        self,
        classification_result: FinancialTableClassificationResult,
        table_extraction_result: TableExtractionResult,
    ) -> ValidationResult:
        """Validate extracted tables and return aggregated issues plus score."""

        self._ensure_single_result_year(
            classification_result,
            table_extraction_result,
        )

        logger.info(
            "Starting financial validation",
            extra={
                "classified_pages": len(classification_result.page_table_types),
                "extracted_tables": len(table_extraction_result.tables),
            },
        )

        issues: list[ValidationIssue] = []

        value_years = sorted(
            {
                metric_value.value_year
                for metric_value in table_extraction_result.metric_values
            }
        )
        if value_years:
            for value_year in value_years:
                context = build_validation_context(
                    classification_result=classification_result,
                    table_extraction_result=table_extraction_result,
                    value_year=value_year,
                )
                issues.extend(self._run_validators(context))
        else:
            context = build_validation_context(
                classification_result=classification_result,
                table_extraction_result=table_extraction_result,
            )
            issues.extend(self._run_validators(context))

        score = self._score_calculator.calculate_score(issues)
        result = ValidationResult(
            is_valid=self._score_calculator.is_valid(score, issues),
            validation_score=score,
            issues=issues,
        )

        logger.info(
            "Financial validation completed",
            extra={
                "validation_score": result.validation_score,
                "is_valid": result.is_valid,
                "issue_count": len(result.issues),
            },
        )
        return result

    def _run_validators(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run all validators for one value-year validation context."""

        issues: list[ValidationIssue] = []
        for validator in self._validators:
            try:
                validator_issues = validator.validate(context)
            except Exception as exc:  # pragma: no cover - defensive service guard
                logger.exception(
                    "Validation rule group failed",
                    extra={"validator": validator.__class__.__name__},
                )
                issues.append(
                    make_issue(
                        year=context.primary_year,
                        rule_name=validator.__class__.__name__,
                        expected="validator completes",
                        actual=str(exc),
                        severity="major",
                        message=(
                            f"{validator.__class__.__name__} failed during "
                            "validation and was skipped."
                        ),
                    )
                )
                continue

            issues.extend(validator_issues)

        return issues

    @classmethod
    def _ensure_results_match_year(
        cls,
        year: int,
        classification_result: FinancialTableClassificationResult,
        table_extraction_result: TableExtractionResult,
    ) -> None:
        """Ensure a context year bucket contains only data from that year."""

        result_years = cls._result_years(classification_result, table_extraction_result)
        mismatched_years = result_years - {year}
        if mismatched_years:
            raise ValueError(
                "Validation inputs for report year "
                f"{year} contain data from other years: "
                f"{sorted(mismatched_years)}."
            )

    @classmethod
    def _ensure_single_result_year(
        cls,
        classification_result: FinancialTableClassificationResult,
        table_extraction_result: TableExtractionResult,
    ) -> None:
        """Prevent direct validation of merged multi-year data."""

        result_years = cls._result_years(classification_result, table_extraction_result)
        if len(result_years) > 1:
            raise ValueError(
                "Validation inputs must contain a single report year. "
                f"Received years: {sorted(result_years)}."
            )

    @staticmethod
    def _result_years(
        classification_result: FinancialTableClassificationResult,
        table_extraction_result: TableExtractionResult,
    ) -> set[int]:
        """Return all years represented by classification and extraction results."""

        return {
            page_table_type.year
            for page_table_type in classification_result.page_table_types
        } | {
            table.source_report_year for table in table_extraction_result.tables
        } | {
            metric_value.source_report_year
            for metric_value in table_extraction_result.metric_values
        }


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for result metadata."""

    return str(exc) or exc.__class__.__name__
