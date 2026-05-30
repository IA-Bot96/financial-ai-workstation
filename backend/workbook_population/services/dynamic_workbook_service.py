"""Dynamic Excel workbook generation service."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from ocr_engine.models.insights_extraction import Insight
from shared.models.metric_value import MetricValue
from workbook_population.constants.workbook_constants import (
    INSIGHTS_SHEET_NAME,
)
from workbook_population.services.workbook_mapper import WorkbookMapper


class DynamicWorkbookService:
    """Generate editable financial model workbooks from MetricValue records."""

    def __init__(self, *, mapper: WorkbookMapper | None = None) -> None:
        """Initialize dynamic workbook generation dependencies."""

        self._mapper = mapper or WorkbookMapper()

    def generate(
        self,
        *,
        output_file_path: str,
        metric_values: list[MetricValue],
        insights: list[Insight],
    ) -> tuple[list[str], int, list[str]]:
        """Generate a workbook from scratch and save it to output_file_path."""

        workbook = Workbook()
        default_sheet = workbook.active
        workbook.remove(default_sheet)

        sheet_metrics = self._group_metrics_by_sheet(metric_values)
        created_sheets: list[str] = []
        metrics_written = 0

        for sheet_name, values in sheet_metrics.items():
            worksheet = workbook.create_sheet(sheet_name)
            created_sheets.append(sheet_name)
            metrics_written += self._write_metric_sheet(worksheet, values)

        if not sheet_metrics and not insights:
            worksheet = workbook.create_sheet("Financial Data")
            worksheet.append(["Metric"])
            _style_header(worksheet[1])
            created_sheets.append("Financial Data")

        if insights:
            self._write_insights_sheet(workbook, insights)
            created_sheets.append(INSIGHTS_SHEET_NAME)

        output_path = Path(output_file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(output_path)
        workbook.close()

        warnings: list[str] = []
        if not metric_values:
            warnings.append("No metric values were provided; generated an empty model.")

        return created_sheets, metrics_written, warnings

    def _group_metrics_by_sheet(
        self,
        metric_values: Iterable[MetricValue],
    ) -> dict[str, list[MetricValue]]:
        grouped: dict[str, list[MetricValue]] = defaultdict(list)
        for metric_value in metric_values:
            grouped[self._mapper.sheet_name_for_metric_value(metric_value)].append(
                metric_value
            )
        return dict(grouped)

    @staticmethod
    def _write_metric_sheet(worksheet: object, metric_values: list[MetricValue]) -> int:
        years = sorted({metric_value.value_year for metric_value in metric_values})
        metrics = _ordered_unique(metric_value.metric for metric_value in metric_values)
        values_by_metric_year = {
            (metric_value.metric, metric_value.value_year): metric_value.value
            for metric_value in metric_values
        }

        worksheet.append(["Metric", *years])
        _style_header(worksheet[1])

        written = 0
        for metric in metrics:
            row = [metric]
            for year in years:
                value = values_by_metric_year.get((metric, year))
                row.append(value)
                if value is not None:
                    written += 1
            worksheet.append(row)

        _autosize_columns(worksheet)
        return written

    @staticmethod
    def _write_insights_sheet(workbook: Workbook, insights: list[Insight]) -> None:
        worksheet = workbook.create_sheet(INSIGHTS_SHEET_NAME)
        worksheet.append(
            [
                "Year",
                "Source Report Year",
                "Area",
                "Takeaway",
                "Source Section",
                "Page",
                "Confidence",
            ]
        )
        _style_header(worksheet[1])

        for insight in insights:
            worksheet.append(
                [
                    insight.value_year,
                    insight.source_report_year,
                    insight.area,
                    insight.takeaway,
                    insight.source_section,
                    insight.page_number,
                    insight.confidence,
                ]
            )

        _autosize_columns(worksheet)


def _style_header(cells: object) -> None:
    fill = PatternFill("solid", fgColor="1F4E78")
    font = Font(color="FFFFFF", bold=True)
    for cell in cells:
        cell.fill = fill
        cell.font = font


def _autosize_columns(worksheet: object) -> None:
    for column_cells in worksheet.columns:
        max_length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in column_cells
        )
        worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = (
            min(max_length + 2, 60)
        )


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        ordered.append(value)
        seen.add(value)
    return ordered


__all__ = ["DynamicWorkbookService"]
