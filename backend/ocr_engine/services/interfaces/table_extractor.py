"""Interface for OCR table extraction services."""

from abc import ABC, abstractmethod

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_extraction import TableExtractionResult


class ITableExtractor(ABC):
    """Contract for services that extract raw table rows from classified pages."""

    @abstractmethod
    def extract_tables(
        self,
        pdf_path: str,
        classification_result: FinancialTableClassificationResult,
    ) -> TableExtractionResult:
        """Extract structured rows from classified financial table pages."""
