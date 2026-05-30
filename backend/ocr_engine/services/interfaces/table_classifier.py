"""Interface for financial table classification services."""

from abc import ABC, abstractmethod

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_detection_result import TableDetectionResult


class ITableClassifier(ABC):
    """Contract for services that classify detected financial table pages."""

    @abstractmethod
    def classify_tables(
        self,
        pdf_path: str,
        table_detection_result: TableDetectionResult,
    ) -> FinancialTableClassificationResult:
        """Classify financial table types present on detected PDF pages."""
