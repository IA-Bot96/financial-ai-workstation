"""Interface for OCR table metric normalization services."""

from abc import ABC, abstractmethod

from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.table_normalization import NormalizationResult
from shared.models.company_context import CompanyContext


class ITableMetricNormalizer(ABC):
    """Contract for normalizing metric labels inside extracted OCR tables."""

    @abstractmethod
    def normalize_for_context(self, context: CompanyContext) -> CompanyContext:
        """Normalize extracted tables for every report in a company context."""

    @abstractmethod
    def normalize_tables(
        self,
        table_extraction_result: TableExtractionResult,
    ) -> NormalizationResult:
        """Normalize metric labels in one report's extracted tables."""
