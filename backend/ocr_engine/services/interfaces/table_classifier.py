"""Interface for financial table classification services."""

from abc import ABC, abstractmethod

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_detection_result import TableDetectionResult
from shared.models.company_context import CompanyContext


class ITableClassifier(ABC):
    """Contract for services that classify detected financial table pages."""

    @abstractmethod
    def process(self, context: CompanyContext) -> CompanyContext:
        """Classify detected financial tables for every report in a company context."""

    @abstractmethod
    def classify_tables_for_context(self, context: CompanyContext) -> CompanyContext:
        """Classify detected financial tables for every report in a company context."""

    @abstractmethod
    def classify_tables(
        self,
        pdf_path: str,
        table_detection_result: TableDetectionResult,
    ) -> FinancialTableClassificationResult:
        """Classify financial table types present on detected PDF pages."""
