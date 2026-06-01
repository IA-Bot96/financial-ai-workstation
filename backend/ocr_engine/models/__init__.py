"""Pydantic models for OCR engine layers."""

from .financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from .financial_fact_extraction import (
    FinancialFact,
    FinancialFactExtractionResult,
)
from .insights_extraction import (
    Insight,
    InsightsExtractionDiagnostics,
    InsightsExtractionResult,
    SectionIdentificationPageDiagnostic,
    SectionIdentificationReport,
)
from .ocr_processing_result import OCRProcessingResult
from .report import Report
from .source_reference import SourceReference
from .table_extraction import (
    ExtractedTable,
    ExtractionQualityReport,
    ExtractionSummary,
    LabelDegluingDiagnostic,
    LabelReconstructionDiagnostic,
    MetricValueOccurrence,
    NoteContextInheritanceDiagnostic,
    NoteRowFilteringDiagnostic,
    PageExtractionDiagnostic,
    SuspiciousMetricFinding,
    SuspiciousTableFinding,
    TableExtractionResult,
)
from .table_normalization import MetricMapping, NormalizationResult, NormalizedTable
from .table_detection_result import DetectedPage, FailedPage, TableDetectionResult
from .validation_result import ValidationIssue, ValidationResult, ValidationSeverity

__all__ = [
    "DetectedPage",
    "ExtractedTable",
    "ExtractionQualityReport",
    "ExtractionSummary",
    "FailedPage",
    "FinancialFact",
    "FinancialFactExtractionResult",
    "FinancialTableClassificationResult",
    "Insight",
    "InsightsExtractionDiagnostics",
    "InsightsExtractionResult",
    "LabelDegluingDiagnostic",
    "LabelReconstructionDiagnostic",
    "MetricMapping",
    "MetricValueOccurrence",
    "NoteContextInheritanceDiagnostic",
    "NoteRowFilteringDiagnostic",
    "NormalizationResult",
    "NormalizedTable",
    "OCRProcessingResult",
    "PageTableType",
    "PageExtractionDiagnostic",
    "Report",
    "SourceReference",
    "SectionIdentificationPageDiagnostic",
    "SectionIdentificationReport",
    "SuspiciousMetricFinding",
    "SuspiciousTableFinding",
    "TableExtractionResult",
    "TableDetectionResult",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
]
