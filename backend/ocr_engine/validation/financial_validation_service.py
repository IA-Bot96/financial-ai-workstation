"""Financial validation service that aggregates rule-based validators."""

from __future__ import annotations

import logging
from typing import Sequence

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.validation_result import ValidationIssue, ValidationResult
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
    build_validation_context,
    make_issue,
)

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

    def validate(
        self,
        classification_result: FinancialTableClassificationResult,
        table_extraction_result: TableExtractionResult,
    ) -> ValidationResult:
        """Validate extracted tables and return aggregated issues plus score."""

        logger.info(
            "Starting financial validation",
            extra={
                "classified_pages": len(classification_result.page_table_types),
                "extracted_tables": len(table_extraction_result.tables),
            },
        )

        context = build_validation_context(
            classification_result=classification_result,
            table_extraction_result=table_extraction_result,
        )
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

        score = self._score_calculator.calculate_score(issues)
        result = ValidationResult(
            is_valid=self._score_calculator.is_valid(score),
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
