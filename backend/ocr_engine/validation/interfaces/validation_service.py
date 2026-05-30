"""Validation service interface for OCR extracted financial tables."""

from abc import ABC, abstractmethod

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.validation_result import ValidationResult


class IValidationService(ABC):
    """Contract for validating extracted financial statement tables."""

    @abstractmethod
    def validate(
        self,
        classification_result: FinancialTableClassificationResult,
        table_extraction_result: TableExtractionResult,
    ) -> ValidationResult:
        """Validate extracted tables and return a scored result."""
