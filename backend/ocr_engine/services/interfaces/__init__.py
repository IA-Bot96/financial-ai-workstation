"""Service interfaces for OCR engine layers."""

from .table_classifier import ITableClassifier
from .table_detector import ITableDetector
from .table_extractor import ITableExtractor
from .insights_extractor import IInsightsExtractor

__all__ = [
    "IInsightsExtractor",
    "ITableClassifier",
    "ITableDetector",
    "ITableExtractor",
]
