"""Service interfaces for OCR engine layers."""

from .table_classifier import ITableClassifier
from .table_detector import ITableDetector
from .table_extractor import ITableExtractor

__all__ = ["ITableClassifier", "ITableDetector", "ITableExtractor"]
