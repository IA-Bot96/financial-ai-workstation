"""Tests for Phase 0 bundle generation service."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from query_engine.services.bundle_generation_service import (
    QueryEngineBundleGenerationService,
)
from query_engine.services.bundle_serializer import QueryEngineBundleLoader
from shared.models.company_context import CompanyContext
from shared.models.financial_year_consolidation import (
    FinancialYearConsolidationResult,
)
from shared.models.metric_value import MetricValue
from shared.models.report import Report
from workbook_population.services.workbook_population_service import (
    OpenPyXLWorkbookPopulationService,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _report() -> Report:
    return Report(
        id="rpt_2025",
        company_name="Lucky Cement Limited",
        year=2025,
        file_name="Lucky_2025_Annual_Report.pdf",
        file_path="/reports/Lucky_2025_Annual_Report.pdf",
    )


def _metric_value() -> MetricValue:
    return MetricValue(
        metric="revenue",
        value_year=2025,
        value=1000,
        source_report_year=2025,
        page_number=10,
        table_type="income_statement",
    )


def test_bundle_generation_service_persists_sidecar_after_workbook_population(
) -> None:
    tmp_path = _workspace_tmp("bundle_generation")
    metric_value = _metric_value()
    workbook_service = OpenPyXLWorkbookPopulationService(
        output_dir=tmp_path,
        output_file_name="phase0.xlsx",
    )
    context = CompanyContext(
        company_name="Lucky Cement Limited",
        reports=[_report()],
        metric_values=[metric_value],
        financial_year_consolidation_result=FinancialYearConsolidationResult(
            metric_values=[metric_value],
            groups=[],
        ),
        insights_results={2025: InsightsExtractionResult(insights=[])},
    )
    workbook_service.process(context)

    bundle_service = QueryEngineBundleGenerationService(
        cell_mapping_provider=workbook_service,
        report_path=tmp_path / "query_engine_phase0_report.json",
    )
    result = bundle_service.process(context)

    assert result is context
    assert context.query_engine_bundle_path is not None
    sidecar_path = Path(context.query_engine_bundle_path)
    assert sidecar_path.exists()
    loaded = QueryEngineBundleLoader().load(sidecar_path)
    assert loaded.company_name == "Lucky Cement Limited"
    assert len(loaded.workbook_cell_mappings) == 1
    assert loaded.workbook_cell_mappings[0].cell_reference == "B2"
    assert bundle_service.last_report is not None
    assert bundle_service.last_report.mappings_persisted == 1
    assert (tmp_path / "query_engine_phase0_report.json").exists()
