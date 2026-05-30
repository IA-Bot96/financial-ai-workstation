"""Workbook population service interface."""

from abc import ABC, abstractmethod

from ocr_engine.models.insights_extraction import Insight
from shared.models.metric_value import MetricValue
from workbook_population.models.workbook_result import WorkbookResult


class IWorkbookPopulationService(ABC):
    """Contract for generating a final Excel workbook from normalized data."""

    @abstractmethod
    def generate_workbook(
        self,
        metric_values: list[MetricValue],
        insights: list[Insight],
        template_path: str | None,
    ) -> WorkbookResult:
        """Generate or populate an .xlsx workbook."""
