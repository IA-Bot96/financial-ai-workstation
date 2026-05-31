"""Pydantic models for OCR engine layers."""

from .financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from .financial_fact_extraction import (
    FinancialFact,
    FinancialFactExtractionResult,
)
from .insights_extraction import Insight, InsightsExtractionResult
from .ocr_processing_result import OCRProcessingResult
from .report import Report
from .source_reference import SourceReference
from .table_extraction import (
    ExtractedTable,
    ExtractionSummary,
    PageExtractionDiagnostic,
    TableExtractionResult,
)
from .table_normalization import MetricMapping, NormalizationResult, NormalizedTable
from .table_detection_result import DetectedPage, FailedPage, TableDetectionResult
from .validation_result import ValidationIssue, ValidationResult, ValidationSeverity

__all__ = [
    "DetectedPage",
    "ExtractedTable",
    "ExtractionSummary",
    "FailedPage",
    "FinancialFact",
    "FinancialFactExtractionResult",
    "FinancialTableClassificationResult",
    "Insight",
    "InsightsExtractionResult",
    "MetricMapping",
    "NormalizationResult",
    "NormalizedTable",
    "OCRProcessingResult",
    "PageTableType",
    "PageExtractionDiagnostic",
    "Report",
    "SourceReference",
    "TableExtractionResult",
    "TableDetectionResult",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
]
