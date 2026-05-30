"""Template workbook population service."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ocr_engine.models.insights_extraction import Insight
from shared.models.metric_value import MetricValue
from workbook_population.constants.workbook_constants import (
    HIGH_TEMPLATE_MATCH_THRESHOLD,
    INSIGHTS_SHEET_NAME,
    LOW_TEMPLATE_MATCH_THRESHOLD,
)
from workbook_population.models.sheet_validation_result import SheetValidationResult
from workbook_population.services.workbook_mapper import WorkbookMapper, _normalize_key

logger = logging.getLogger(__name__)


class TemplatePopulationService:
    """Populate Excel templates using independent sheet-level decisions."""

    def __init__(
        self,
        *,
        mapper: WorkbookMapper | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the service with an injectable workbook mapper."""

        self._mapper = mapper or WorkbookMapper()
        self._logger = log or logger

    def populate(
        self,
        *,
        template_path: str,
        output_file_path: str,
        metric_values: list[MetricValue],
        insights: list[Insight],
        sheet_results: list[SheetValidationResult],
    ) -> tuple[list[str], list[str], list[str], int, list[str]]:
        """Populate, replace, or create sheets based on sheet-level compatibility."""

        workbook = load_workbook(template_path, data_only=False)
        metrics_written = 0
        warnings: list[str] = []
        sheets_reused: list[str] = []
        sheets_replaced: list[str] = []
        sheets_created: list[str] = []

        grouped_values = self._group_values_by_sheet(metric_values)
        sheet_result_by_name = {
            _normalize_key(sheet_result.sheet_name): sheet_result
            for sheet_result in sheet_results
        }

        try:
            for sheet_name, values in grouped_values.items():
                sheet_result = sheet_result_by_name.get(_normalize_key(sheet_name))
                existing_sheet_name = self._find_existing_sheet_name(
                    workbook,
                    sheet_name,
                )

                if existing_sheet_name is None:
                    worksheet = workbook.create_sheet(sheet_name)
                    metrics_written += self._write_generated_metric_sheet(
                        worksheet,
                        values,
                    )
                    sheets_created.append(sheet_name)
                    continue

                if sheet_result is None:
                    warnings.append(
                        f"{sheet_name} has no validation result; sheet left unchanged."
                    )
                    continue

                if sheet_result.match_score >= HIGH_TEMPLATE_MATCH_THRESHOLD:
                    written, sheet_warnings = self._populate_compatible_sheet(
                        workbook=workbook,
                        sheet_name=sheet_name,
                        metric_values=values,
                    )
                    metrics_written += written
                    warnings.extend(sheet_warnings)
                    sheets_reused.append(existing_sheet_name)
                    continue

                if sheet_result.match_score >= LOW_TEMPLATE_MATCH_THRESHOLD:
                    warnings.append(
                        f"{sheet_name} template is {sheet_result.match_score}% "
                        "compatible and requires user decision."
                    )
                    continue

                replacement_index = workbook.sheetnames.index(existing_sheet_name)
                workbook.remove(workbook[existing_sheet_name])
                worksheet = workbook.create_sheet(sheet_name, replacement_index)
                metrics_written += self._write_generated_metric_sheet(worksheet, values)
                sheets_replaced.append(sheet_name)

            if self._populate_insights(workbook, insights):
                sheets_created.append(INSIGHTS_SHEET_NAME)

            output_path = Path(output_file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            workbook.save(output_path)
            return (
                sheets_reused,
                sheets_replaced,
                sheets_created,
                metrics_written,
                warnings,
            )
        finally:
            workbook.close()

    def _populate_compatible_sheet(
        self,
        *,
        workbook: object,
        sheet_name: str,
        metric_values: list[MetricValue],
    ) -> tuple[int, list[str]]:
        metrics_written = 0
        warnings: list[str] = []

        for metric_value in metric_values:
            mapping = self._mapper.resolve_template_mapping(workbook, metric_value)
            if mapping is None:
                warnings.append(
                    "No template cell mapping found for "
                    f"{metric_value.metric} {metric_value.value_year}."
                )
                continue

            if _normalize_key(mapping.sheet_name) != _normalize_key(sheet_name):
                warnings.append(
                    "Skipped cross-sheet mapping for "
                    f"{metric_value.metric} {metric_value.value_year}."
                )
                continue

            worksheet = workbook[mapping.sheet_name]
            cell = worksheet.cell(row=mapping.row, column=mapping.column)
            if self._is_formula_cell(cell.value):
                warnings.append(
                    "Skipped formula cell " f"{mapping.sheet_name}!{cell.coordinate}."
                )
                continue

            cell.value = metric_value.value
            metrics_written += 1

        return metrics_written, warnings

    def _group_values_by_sheet(
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
    def _find_existing_sheet_name(workbook: object, sheet_name: str) -> str | None:
        if sheet_name in workbook.sheetnames:
            return sheet_name

        normalized_target = _normalize_key(sheet_name)
        for existing_sheet_name in workbook.sheetnames:
            if _normalize_key(existing_sheet_name) == normalized_target:
                return existing_sheet_name
        return None

    @staticmethod
    def _write_generated_metric_sheet(
        worksheet: Worksheet,
        metric_values: list[MetricValue],
    ) -> int:
        years = sorted({metric_value.value_year for metric_value in metric_values})
        metrics = _ordered_unique(metric_value.metric for metric_value in metric_values)
        values_by_metric_year = {
            (metric_value.metric, metric_value.value_year): metric_value.value
            for metric_value in metric_values
        }

        worksheet.append(["Metric", *years])
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
    def _populate_insights(workbook: object, insights: list[Insight]) -> bool:
        """Write insights to a dedicated sheet without touching formulas elsewhere."""

        sheet_created = INSIGHTS_SHEET_NAME not in workbook.sheetnames
        if sheet_created:
            worksheet = workbook.create_sheet(INSIGHTS_SHEET_NAME)
        else:
            worksheet = workbook[INSIGHTS_SHEET_NAME]
            worksheet.delete_rows(1, worksheet.max_row)

        headers = [
            "Year",
            "Source Report Year",
            "Area",
            "Takeaway",
            "Source Section",
            "Page",
            "Confidence",
        ]
        worksheet.append(headers)
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
        return sheet_created

    @staticmethod
    def _is_formula_cell(value: object) -> bool:
        return isinstance(value, str) and value.startswith("=")


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        ordered.append(value)
        seen.add(value)
    return ordered


def _autosize_columns(worksheet: Worksheet) -> None:
    for column_cells in worksheet.columns:
        max_length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in column_cells
        )
        worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = (
            min(max_length + 2, 60)
        )


__all__ = ["TemplatePopulationService"]
