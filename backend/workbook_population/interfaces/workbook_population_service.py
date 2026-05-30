"""Workbook population service interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ocr_engine.models.insights_extraction import Insight
from shared.models.metric_value import MetricValue
from workbook_population.models.workbook_result import WorkbookResult

if TYPE_CHECKING:
    from shared.models.company_context import CompanyContext


class IWorkbookPopulationService(ABC):
    """Contract for generating a final Excel workbook from normalized data."""

    @abstractmethod
    def process(self, context: CompanyContext) -> CompanyContext:
        """Generate or populate the workbook and store the result in context."""

    @abstractmethod
    def generate_workbook(
        self,
        metric_values: list[MetricValue],
        insights: list[Insight],
        template_path: str | None,
    ) -> WorkbookResult:
        """Generate or populate an .xlsx workbook."""
