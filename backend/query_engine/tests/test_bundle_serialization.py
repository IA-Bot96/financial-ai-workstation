"""Tests for Query Engine bundle fingerprinting and serialization."""

from __future__ import annotations

import sys
from uuid import uuid4
from pathlib import Path

from openpyxl import Workbook

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.services.bundle_serializer import (
    QueryEngineBundleLoader,
    QueryEngineBundleSerializer,
)
from query_engine.services.fingerprint_service import QueryEngineFingerprintService
from shared.models.financial_year_consolidation import (
    FinancialYearConsolidationResult,
)
from shared.models.metric_value import MetricValue
from workbook_population.models.workbook_cell_mapping import WorkbookCellMappingDraft
from workbook_population.models.workbook_result import WorkbookResult


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_workbook(path: Path, value: int = 1000) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Income Statement"
    worksheet.append(["Metric", 2025])
    worksheet.append(["revenue", value])
    workbook.save(path)
    workbook.close()


def _workbook_result(path: Path) -> WorkbookResult:
    return WorkbookResult(
        output_file_path=str(path),
        workbook_mode="dynamic",
        workbook_match_score=0,
        sheets_reused=[],
        sheets_replaced=[],
        sheets_created=["Income Statement"],
        metrics_written=1,
        warnings=[],
    )


def _bundle(path: Path, workbook_fingerprint: str) -> QueryEngineInputBundle:
    metric_value = MetricValue(
        metric="revenue",
        value_year=2025,
        value=1000,
        source_report_year=2025,
        page_number=10,
        table_type="income_statement",
    )
    draft = WorkbookCellMappingDraft(
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
    bundle = QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_test",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=_workbook_result(path),
        financial_year_consolidation_result=FinancialYearConsolidationResult(
            metric_values=[metric_value],
            groups=[],
        ),
        insights_results_by_report_year={2025: InsightsExtractionResult(insights=[])},
        workbook_cell_mappings=[draft.to_record(workbook_fingerprint)],
    )
    expected_fingerprint = QueryEngineFingerprintService().workbook_fingerprint(
        workbook_path=path,
        structured_payload=bundle.stable_payload(),
    )
    return QueryEngineInputBundle(
        **{
            **bundle.model_dump(),
            "workbook_id": f"wb_{expected_fingerprint[:12]}",
            "workbook_fingerprint": expected_fingerprint,
            "workbook_cell_mappings": [draft.to_record(expected_fingerprint)],
        }
    )


def test_fingerprint_is_stable_for_same_workbook_and_payload() -> None:
    tmp_path = _workspace_tmp("fingerprint_stable")
    workbook_path = tmp_path / "model.xlsx"
    _save_workbook(workbook_path)
    payload = {"company": "Lucky", "metrics": [{"metric": "revenue"}]}
    service = QueryEngineFingerprintService()

    first = service.workbook_fingerprint(
        workbook_path=workbook_path,
        structured_payload=payload,
    )
    second = service.workbook_fingerprint(
        workbook_path=workbook_path,
        structured_payload=payload,
    )

    assert first == second


def test_fingerprint_changes_when_structured_payload_changes() -> None:
    tmp_path = _workspace_tmp("fingerprint_payload_change")
    workbook_path = tmp_path / "model.xlsx"
    _save_workbook(workbook_path)
    service = QueryEngineFingerprintService()

    first = service.workbook_fingerprint(
        workbook_path=workbook_path,
        structured_payload={"metric": "revenue"},
    )
    second = service.workbook_fingerprint(
        workbook_path=workbook_path,
        structured_payload={"metric": "gross_profit"},
    )

    assert first != second


def test_query_engine_bundle_serialization_roundtrip() -> None:
    tmp_path = _workspace_tmp("serialization_roundtrip")
    workbook_path = tmp_path / "model.xlsx"
    _save_workbook(workbook_path)
    bundle = _bundle(workbook_path, "fp_roundtrip")
    sidecar_path = tmp_path / "model.kb.json"

    QueryEngineBundleSerializer().serialize(bundle, sidecar_path)
    loaded = QueryEngineBundleLoader().load(sidecar_path)

    assert loaded.model_dump(mode="json") == bundle.model_dump(mode="json")
