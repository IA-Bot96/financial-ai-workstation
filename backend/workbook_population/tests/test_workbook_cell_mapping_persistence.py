"""Tests for workbook cell mapping capture during workbook population."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.models.metric_value import MetricValue
from workbook_population.models.sheet_validation_result import SheetValidationResult
from workbook_population.models.workbook_cell_mapping import WorkbookCellMappingDraft
from workbook_population.services.dynamic_workbook_service import DynamicWorkbookService
from workbook_population.services.template_population_service import (
    TemplatePopulationService,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _metric_value(metric: str = "revenue") -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=2025,
        value=1000,
        source_report_year=2025,
        page_number=10,
        table_type="income_statement",
    )


def test_dynamic_workbook_service_captures_written_cell_mappings(
) -> None:
    tmp_path = _workspace_tmp("dynamic_mapping")
    service = DynamicWorkbookService()

    service.generate(
        output_file_path=str(tmp_path / "dynamic.xlsx"),
        metric_values=[_metric_value()],
        insights=[],
    )

    assert service.last_cell_mapping_drafts == [
        WorkbookCellMappingDraft(
            metric="revenue",
            value_year=2025,
            source_report_year=2025,
            table_type="income_statement",
            sheet_name="Income Statement",
            row=2,
            column=2,
            cell_reference="B2",
            write_status="written",
            written_value=1000,
        )
    ]


def test_template_population_service_captures_formula_skipped_mapping(
) -> None:
    tmp_path = _workspace_tmp("template_mapping")
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "output.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Income Statement"
    worksheet.append(["Metric", 2025])
    worksheet.append(["revenue", "=1+1"])
    workbook.save(template_path)
    workbook.close()

    service = TemplatePopulationService()
    service.populate(
        template_path=str(template_path),
        output_file_path=str(output_path),
        metric_values=[_metric_value()],
        insights=[],
        sheet_results=[
            SheetValidationResult(
                sheet_name="Income Statement",
                match_score=100,
                is_compatible=True,
                missing_metrics=[],
                extra_metrics=[],
                warnings=[],
            )
        ],
    )

    assert service.last_cell_mapping_drafts == [
        WorkbookCellMappingDraft(
            metric="revenue",
            value_year=2025,
            source_report_year=2025,
            table_type="income_statement",
            sheet_name="Income Statement",
            row=2,
            column=2,
            cell_reference="B2",
            write_status="skipped_formula",
            written_value=1000,
        )
    ]
