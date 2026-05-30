"""OpenPyXL workbook population orchestration service."""

from __future__ import annotations

import logging
from pathlib import Path

from ocr_engine.models.insights_extraction import Insight
from shared.models.metric_value import MetricValue
from workbook_population.constants.workbook_constants import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_FILE_NAME,
    DYNAMIC_WORKBOOK_MODE,
    HIGH_TEMPLATE_MATCH_THRESHOLD,
    LOW_TEMPLATE_MATCH_THRESHOLD,
    TEMPLATE_WORKBOOK_MODE,
    USER_DECISION_WORKBOOK_MODE,
)
from workbook_population.interfaces.workbook_population_service import (
    IWorkbookPopulationService,
)
from workbook_population.models.sheet_validation_result import SheetValidationResult
from workbook_population.models.workbook_result import WorkbookResult
from workbook_population.services.dynamic_workbook_service import DynamicWorkbookService
from workbook_population.services.template_population_service import (
    TemplatePopulationService,
)
from workbook_population.services.template_structure_validator import (
    TemplateStructureValidator,
)

logger = logging.getLogger(__name__)


class OpenPyXLWorkbookPopulationService(IWorkbookPopulationService):
    """Generate the final Excel workbook using template or dynamic mode."""

    def __init__(
        self,
        *,
        output_dir: str | Path = DEFAULT_OUTPUT_DIR,
        output_file_name: str = DEFAULT_OUTPUT_FILE_NAME,
        template_validator: TemplateStructureValidator | None = None,
        template_population_service: TemplatePopulationService | None = None,
        dynamic_workbook_service: DynamicWorkbookService | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize workbook population with injectable collaborators."""

        self._output_dir = Path(output_dir)
        self._output_file_name = output_file_name
        self._template_validator = template_validator or TemplateStructureValidator()
        self._template_population_service = (
            template_population_service or TemplatePopulationService()
        )
        self._dynamic_workbook_service = (
            dynamic_workbook_service or DynamicWorkbookService()
        )
        self._logger = log or logger

    def generate_workbook(
        self,
        metric_values: list[MetricValue],
        insights: list[Insight],
        template_path: str | None,
    ) -> WorkbookResult:
        """Generate or populate an Excel workbook from normalized financial data."""

        self._validate_inputs(metric_values)
        output_file_path = str(self._output_dir / self._output_file_name)
        warnings: list[str] = []
        workbook_match_score: float | None = None

        self._logger.info(
            "Starting workbook population",
            extra={
                "metric_values": len(metric_values),
                "insights": len(insights),
                "template_path": template_path,
            },
        )

        if template_path is not None:
            validation_result = self._template_validator.validate(
                template_path,
                metric_values,
            )
            workbook_match_score = validation_result.match_score
            warnings.extend(validation_result.warnings)

            if validation_result.sheet_results:
                (
                    sheets_reused,
                    sheets_replaced,
                    sheets_created,
                    metrics_written,
                    populate_warnings,
                ) = (
                    self._template_population_service.populate(
                        template_path=template_path,
                        output_file_path=output_file_path,
                        metric_values=metric_values,
                        insights=insights,
                        sheet_results=validation_result.sheet_results,
                    )
                )
                warnings.extend(populate_warnings)
                return self._result(
                    output_file_path=output_file_path,
                    workbook_mode=self._workbook_mode_for_validation(
                        validation_result.sheet_results
                    ),
                    workbook_match_score=workbook_match_score,
                    sheets_reused=sheets_reused,
                    sheets_replaced=sheets_replaced,
                    sheets_created=sheets_created,
                    metrics_written=metrics_written,
                    warnings=warnings,
                )

        sheets_created, metrics_written, dynamic_warnings = (
            self._dynamic_workbook_service.generate(
                output_file_path=output_file_path,
                metric_values=metric_values,
                insights=insights,
            )
        )
        warnings.extend(dynamic_warnings)
        return self._result(
            output_file_path=output_file_path,
            workbook_mode=DYNAMIC_WORKBOOK_MODE,
            workbook_match_score=workbook_match_score,
            sheets_reused=[],
            sheets_replaced=[],
            sheets_created=sheets_created,
            metrics_written=metrics_written,
            warnings=warnings,
        )

    @staticmethod
    def _validate_inputs(metric_values: list[MetricValue]) -> None:
        seen: set[tuple[str, int]] = set()
        duplicates: set[tuple[str, int]] = set()
        for metric_value in metric_values:
            key = (metric_value.metric, metric_value.value_year)
            if key in seen:
                duplicates.add(key)
            seen.add(key)

        if duplicates:
            formatted = ", ".join(
                f"{metric}/{year}" for metric, year in sorted(duplicates)
            )
            raise ValueError(
                "Duplicate consolidated metric/value_year combinations: "
                f"{formatted}."
            )

    def _result(
        self,
        *,
        output_file_path: str,
        workbook_mode: str,
        workbook_match_score: float | None,
        sheets_reused: list[str],
        sheets_replaced: list[str],
        sheets_created: list[str],
        metrics_written: int,
        warnings: list[str],
    ) -> WorkbookResult:
        result = WorkbookResult(
            output_file_path=output_file_path,
            workbook_mode=workbook_mode,
            workbook_match_score=workbook_match_score,
            sheets_reused=sheets_reused,
            sheets_replaced=sheets_replaced,
            sheets_created=sheets_created,
            metrics_written=metrics_written,
            warnings=_deduplicate(warnings),
        )
        self._logger.info(
            "Workbook population completed",
            extra=result.model_dump(),
        )
        return result

    @staticmethod
    def _workbook_mode_for_validation(
        sheet_results: list[SheetValidationResult],
    ) -> str:
        for sheet_result in sheet_results:
            if (
                LOW_TEMPLATE_MATCH_THRESHOLD
                <= sheet_result.match_score
                < HIGH_TEMPLATE_MATCH_THRESHOLD
            ):
                return USER_DECISION_WORKBOOK_MODE
        return TEMPLATE_WORKBOOK_MODE


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        deduplicated.append(value)
        seen.add(value)
    return deduplicated


__all__ = ["OpenPyXLWorkbookPopulationService"]
