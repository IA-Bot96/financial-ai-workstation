"""Pydantic models for OCR engine layers."""

from .financial_table_classification import (
    FinancialTableClassification,
    FinancialTableClassificationResult,
)
from .financial_fact_extraction import (
    FinancialFact,
    FinancialFactExtractionResult,
)
from .insights_extraction import Insight, InsightsExtractionResult
from .ocr_processing_result import OCRProcessingResult
from .report import Report
from .source_reference import SourceReference
from .table_extraction import ExtractedTable, TableExtractionResult
from .table_detection_result import DetectedPage, TableDetectionResult

__all__ = [
    "DetectedPage",
    "ExtractedTable",
    "FinancialFact",
    "FinancialFactExtractionResult",
    "FinancialTableClassification",
    "FinancialTableClassificationResult",
    "Insight",
    "InsightsExtractionResult",
    "OCRProcessingResult",
    "Report",
    "SourceReference",
    "TableExtractionResult",
    "TableDetectionResult",
]
