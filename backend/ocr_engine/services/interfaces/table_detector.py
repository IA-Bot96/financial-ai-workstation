"""Interface for OCR table detection services."""

from abc import ABC, abstractmethod

from ocr_engine.models.table_detection_result import TableDetectionResult


class ITableDetector(ABC):
    """Contract for services that detect PDF pages containing tables."""

    @abstractmethod
    def detect_tables(self, pdf_path: str) -> TableDetectionResult:
        """Detect pages in a PDF that contain at least one table."""
