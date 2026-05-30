"""Interface for OCR table detection services."""

from abc import ABC, abstractmethod

from ocr_engine.models.table_detection_result import TableDetectionResult
from shared.models.company_context import CompanyContext


class ITableDetector(ABC):
    """Contract for services that detect PDF pages containing tables."""

    @abstractmethod
    def process(self, context: CompanyContext) -> CompanyContext:
        """Detect tables for every report in a company context."""

    @abstractmethod
    def detect_tables_for_context(self, context: CompanyContext) -> CompanyContext:
        """Detect tables for every report in a company context."""

    @abstractmethod
    def detect_tables(self, pdf_path: str, year: int) -> TableDetectionResult:
        """Detect pages in a PDF that contain at least one table."""
