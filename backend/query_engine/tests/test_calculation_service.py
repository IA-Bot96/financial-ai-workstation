"""Tests for deterministic financial calculation service."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from query_engine.models.calculation import CalculationRequest
from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.services.calculation_service import CalculationService
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.knowledge_base_builder import KnowledgeBaseBuilder
from query_engine.services.metric_resolution_service import MetricResolutionService
from shared.models.financial_year_consolidation import (
    ConsolidationCandidate,
    ConsolidationGroup,
    FinancialYearConsolidationResult,
    StatementScope,
)
from shared.models.metric_value import MetricValue
from workbook_population.models.workbook_cell_mapping import WorkbookCellMappingDraft
from workbook_population.models.workbook_result import WorkbookResult


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _metric_value(
    metric: str,
    year: int,
    value: int,
    page_number: int,
    table_type: str,
) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=page_number,
        table_type=table_type,
    )


def _candidate(
    metric: str,
    year: int,
    value: int,
    page_number: int,
    table_type: str,
    *,
    scope: StatementScope = "consolidated",
    confidence: float = 0.95,
    requires_review: bool = False,
) -> ConsolidationCandidate:
    return ConsolidationCandidate(
        metric=metric,
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=page_number,
        table_type=table_type,
        source_class="primary_statement",
        statement_scope=scope,
        normalization_confidence=confidence,
        source_confidence=confidence,
        original_metric=metric.replace("_", " ").title(),
        requires_review=requires_review,
        label_cleanliness_score=10,
        source_context_score=10,
        table_type_priority=1,
    )


def _group(
    metric: str,
    year: int,
    value: int,
    page_number: int,
    table_type: str,
    *,
    conflict: bool = False,
) -> ConsolidationGroup:
    selected = _candidate(metric, year, value, page_number, table_type)
    competing_value = value - 25 if conflict else value
    competing = _candidate(
        metric,
        year,
        competing_value,
        page_number + 1,
        table_type,
        confidence=0.72 if conflict else 0.9,
        requires_review=conflict,
    )
    return ConsolidationGroup(
        metric=metric,
        value_year=year,
        candidate_count=2,
        selected=selected,
        competing_candidates=[competing],
        is_duplicate_group=True,
        is_conflict_group=conflict,
        conflict_resolved=not conflict,
        unresolved_conflict=conflict,
        conflict_status="unresolved" if conflict else "resolved_duplicate",
        resolution_reason=(
            "requires_analyst_review" if conflict else "higher_confidence"
        ),
    )


def _mapping(
    metric_value: MetricValue,
    row: int,
    workbook_fingerprint: str,
) -> object:
    return WorkbookCellMappingDraft(
        metric=metric_value.metric,
        value_year=metric_value.value_year,
        source_report_year=metric_value.source_report_year,
        table_type=metric_value.table_type,
        sheet_name=metric_value.table_type.replace("_", " ").title(),
        row=row,
        column=2,
        cell_reference=f"B{row}",
        write_status="written",
        written_value=metric_value.value,
    ).to_record(workbook_fingerprint)


def _calculation_service() -> CalculationService:
    workbook_fingerprint = "fp_phase3"
    metric_values = [
        _metric_value("revenue", 2023, 1000, 10, "income_statement"),
        _metric_value("revenue", 2024, 1200, 10, "income_statement"),
        _metric_value("revenue", 2025, 1500, 10, "income_statement"),
        _metric_value("earnings_per_share", 2024, 10, 12, "income_statement"),
        _metric_value("earnings_per_share", 2025, 15, 12, "income_statement"),
        _metric_value("operating_profit", 2023, 100, 14, "income_statement"),
        _metric_value("operating_profit", 2024, 200, 14, "income_statement"),
        _metric_value("operating_profit", 2025, 300, 14, "income_statement"),
        _metric_value("cash_and_cash_equivalents", 2024, 0, 16, "cash_flow"),
        _metric_value("cash_and_cash_equivalents", 2025, 10, 16, "cash_flow"),
        _metric_value("capital_expenditure", 2025, 80, 18, "cash_flow"),
        _metric_value("gross_profit", 2024, 400, 20, "income_statement"),
        _metric_value("gross_profit", 2025, 500, 20, "income_statement"),
    ]
    groups = [
        _group(
            value.metric,
            value.value_year,
            int(value.value),
            value.page_number,
            value.table_type,
            conflict=value.metric == "gross_profit" and value.value_year == 2025,
        )
        for value in metric_values
    ]
    bundle = QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_phase3",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=WorkbookResult(
            output_file_path="output/test_query_engine_phase3.xlsx",
            workbook_mode="dynamic",
            workbook_match_score=0,
            sheets_reused=[],
            sheets_replaced=[],
            sheets_created=["Income Statement", "Cash Flow"],
            metrics_written=len(metric_values),
            warnings=[],
        ),
        financial_year_consolidation_result=FinancialYearConsolidationResult(
            metric_values=metric_values,
            groups=groups,
        ),
        insights_results_by_report_year={
            2025: InsightsExtractionResult(insights=[])
        },
        workbook_cell_mappings=[
            _mapping(metric_value, index, workbook_fingerprint)
            for index, metric_value in enumerate(metric_values, start=2)
        ],
    )
    knowledge_base = KnowledgeBaseBuilder(
        report_path=_workspace_tmp("phase3_kb") / "report.json"
    ).build(bundle)
    financial_service = FinancialRetrievalService(knowledge_base)
    resolution_service = MetricResolutionService(
        knowledge_base=knowledge_base,
        financial_retrieval_service=financial_service,
    )
    return CalculationService(
        financial_retrieval_service=financial_service,
        metric_resolution_service=resolution_service,
    )


def test_revenue_year_over_year_growth() -> None:
    result = _calculation_service().year_over_year_growth("revenue", 2025)

    assert result.success is True
    assert result.value == pytest.approx(25.0)
    assert result.result_unit == "percentage"
    assert [point.value_year for point in result.evidence] == [2024, 2025]


def test_eps_growth_uses_metric_resolution() -> None:
    result = _calculation_service().year_over_year_growth("EPS", 2025)

    assert result.success is True
    assert result.resolved_metric == "earnings_per_share"
    assert result.value == pytest.approx(50.0)


def test_operating_profit_trend_direction() -> None:
    result = _calculation_service().trend_direction("operating profit")

    assert result.success is True
    assert result.value == "increasing"
    assert result.trend_direction == "increasing"


def test_revenue_cagr() -> None:
    result = _calculation_service().cagr("revenue", 2023, 2025)

    assert result.success is True
    assert result.value == pytest.approx(22.474487, rel=1e-6)


def test_missing_history_behavior() -> None:
    result = _calculation_service().cagr("capex", 2023, 2025)

    assert result.success is False
    assert result.value is None
    assert "missing year 2023 for metric" in result.errors


def test_divide_by_zero_behavior() -> None:
    result = _calculation_service().percentage_change("cash", 2024, 2025)

    assert result.success is False
    assert result.value is None
    assert "divide-by-zero: start value is zero" in result.errors


def test_conflict_propagation() -> None:
    result = _calculation_service().percentage_change("gross profit", 2024, 2025)

    assert result.success is True
    assert result.value == pytest.approx(25.0)
    assert result.has_unresolved_conflicts is True
    assert result.conflicts
    assert any("unresolved conflicts" in warning for warning in result.warnings)


def test_provenance_propagation() -> None:
    result = _calculation_service().absolute_change("revenue", 2024, 2025)

    assert result.success is True
    assert result.value == pytest.approx(300.0)
    assert result.confidence > 0
    assert len(result.evidence) == 2
    assert len(result.retrieval_evidence) >= 2
    assert all(point.page_number > 0 for point in result.evidence)
    assert all(point.workbook_citation.citation_status == "cell_mapped" for point in result.evidence)
    assert {point.statement_scope for point in result.evidence} == {"consolidated"}
