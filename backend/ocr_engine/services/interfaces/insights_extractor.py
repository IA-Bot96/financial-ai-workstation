"""Insights extraction service interface."""

from abc import ABC, abstractmethod

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from ocr_engine.models.table_normalization import NormalizationResult
from shared.models.company_context import CompanyContext


class IInsightsExtractor(ABC):
    """Contract for extracting business insights from annual-report narratives."""

    @abstractmethod
    def process(self, context: CompanyContext) -> CompanyContext:
        """Extract insights for every report in a company context."""

    @abstractmethod
    def extract_insights_for_context(self, context: CompanyContext) -> CompanyContext:
        """Extract insights for every report in a company context."""

    @abstractmethod
    def extract_insights(
        self,
        pdf_path: str,
        normalization_result: NormalizationResult,
    ) -> InsightsExtractionResult:
        """Extract structured insights with source traceability."""
