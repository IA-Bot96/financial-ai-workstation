"""Tests for Query Engine input bundle contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult
from query_engine.models.input_bundle import (
    BundleVersionInfo,
    QueryEngineInputBundle,
)
from shared.models.financial_year_consolidation import (
    FinancialYearConsolidationResult,
)
from shared.models.metric_value import MetricValue
from workbook_population.models.workbook_cell_mapping import (
    WorkbookCellMappingDraft,
)
from workbook_population.models.workbook_result import WorkbookResult


def _workbook_result() -> WorkbookResult:
    return WorkbookResult(
        output_file_path="output/test.xlsx",
        workbook_mode="dynamic",
        workbook_match_score=0,
        sheets_reused=[],
        sheets_replaced=[],
        sheets_created=["Income Statement"],
        metrics_written=1,
        warnings=[],
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


def _insights_result() -> InsightsExtractionResult:
    return InsightsExtractionResult(
        insights=[
            Insight(
                value_year=2025,
                source_report_year=2025,
                area="Revenue",
                takeaway="Revenue increased due to higher dispatches.",
                source_section="Business Review",
                page_number=22,
                confidence=0.9,
            )
        ]
    )


def _mapping(workbook_fingerprint: str = "fp_123") -> WorkbookCellMappingDraft:
    return WorkbookCellMappingDraft(
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


def _bundle() -> QueryEngineInputBundle:
    workbook_fingerprint = "fp_123"
    return QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_123",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=_workbook_result(),
        financial_year_consolidation_result=FinancialYearConsolidationResult(
            metric_values=[_metric_value()],
            groups=[],
        ),
        insights_results_by_report_year={2025: _insights_result()},
        workbook_cell_mappings=[
            _mapping(workbook_fingerprint).to_record(workbook_fingerprint)
        ],
    )


def test_query_engine_input_bundle_validates_required_contract() -> None:
    bundle = _bundle()

    validation = bundle.validate_contract()

    assert validation.is_valid is True
    assert validation.errors == []
    assert validation.version_info.schema_version == "1.0.0"


def test_query_engine_input_bundle_rejects_duplicate_report_years() -> None:
    with pytest.raises(ValidationError, match="report_years contains duplicates"):
        QueryEngineInputBundle(
            **{
                **_bundle().model_dump(),
                "report_years": [2025, 2025],
            }
        )


def test_query_engine_input_bundle_rejects_unknown_insight_year() -> None:
    payload = _bundle().model_dump()
    payload["insights_results_by_report_year"] = {2024: _insights_result()}

    with pytest.raises(
        ValidationError,
        match="insights_results_by_report_year contains years",
    ):
        QueryEngineInputBundle(**payload)


def test_query_engine_input_bundle_rejects_mapping_fingerprint_mismatch() -> None:
    payload = _bundle().model_dump()
    payload["workbook_cell_mappings"] = [_mapping("other").to_record("other")]

    with pytest.raises(
        ValidationError,
        match="fingerprint that does not match workbook_fingerprint",
    ):
        QueryEngineInputBundle(**payload)


def test_version_info_accepts_same_major_and_warns_on_newer_minor() -> None:
    version_info = BundleVersionInfo.parse("1.1.0")

    assert version_info.is_compatible is True
    assert version_info.warning is not None


def test_query_engine_input_bundle_rejects_unsupported_major_version() -> None:
    payload = _bundle().model_dump()
    payload["schema_version"] = "2.0.0"

    with pytest.raises(ValidationError, match="unsupported Query Engine"):
        QueryEngineInputBundle(**payload)
