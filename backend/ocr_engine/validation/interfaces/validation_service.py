"""Validation service interface for OCR extracted financial tables."""

from abc import ABC, abstractmethod

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.validation_result import ValidationResult
from shared.models.company_context import CompanyContext


class IValidationService(ABC):
    """Contract for validating extracted financial statement tables."""

    @abstractmethod
    def process(self, context: CompanyContext) -> CompanyContext:
        """Validate extracted tables for every report in a company context."""

    @abstractmethod
    def validate_for_context(self, context: CompanyContext) -> CompanyContext:
        """Validate extracted tables for every report in a company context."""

    @abstractmethod
    def validate(
        self,
        classification_result: FinancialTableClassificationResult,
        table_extraction_result: TableExtractionResult,
    ) -> ValidationResult:
        """Validate extracted tables and return a scored result."""
