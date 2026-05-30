"""Service interfaces for OCR engine layers."""

from .table_classifier import ITableClassifier
from .table_detector import ITableDetector

__all__ = ["ITableClassifier", "ITableDetector"]
