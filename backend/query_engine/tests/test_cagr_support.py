"""Tests for deterministic CAGR planning, routing, and rendering."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.models.query_planner import CAGRPlan, QueryIntent, QueryRequest
from query_engine.models.response import CAGRResponse, QueryResponseType
from query_engine.services.calculation_service import CalculationService
from query_engine.services.evidence_builder_service import EvidenceBuilderService
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.knowledge_base_builder import KnowledgeBaseBuilder
from query_engine.services.metric_resolution_service import MetricResolutionService
from query_engine.services.query_planner_service import QueryPlannerService
from query_engine.services.response_renderer_service import ResponseRendererService
from shared.models.financial_year_consolidation import FinancialYearConsolidationResult
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
    value: int | float,
    page_number: int,
    table_type: str = "income_statement",
) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=page_number,
        table_type=table_type,
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


def _services() -> tuple[QueryPlannerService, EvidenceBuilderService, ResponseRendererService]:
    workbook_fingerprint = "fp_cagr"
    metric_values = [
        *[
            _metric_value("revenue", year, value, 10)
            for year, value in (
                (2020, 100),
                (2021, 120),
                (2022, 140),
                (2023, 160),
                (2024, 180),
                (2025, 200),
            )
        ],
        *[
            _metric_value("earnings_per_share", year, value, 12)
            for year, value in (
                (2020, 2.0),
                (2021, 2.4),
                (2022, 2.8),
                (2023, 3.2),
                (2024, 3.6),
                (2025, 4.0),
            )
        ],
        *[
            _metric_value("operating_profit", year, value, 14)
            for year, value in (
                (2020, 50),
                (2021, 60),
                (2022, 75),
                (2023, 90),
                (2024, 110),
                (2025, 130),
            )
        ],
        *[
            _metric_value("cash_and_cash_equivalents", year, value, 16, "cash_flow")
            for year, value in (
                (2020, 80),
                (2021, 90),
                (2022, 95),
                (2023, 105),
                (2024, 115),
                (2025, 125),
            )
        ],
        _metric_value("capital_expenditure", 2025, 80, 18, "cash_flow"),
    ]
    bundle = QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_cagr",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=WorkbookResult(
            output_file_path="output/test_query_engine_cagr.xlsx",
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
            groups=[],
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
        report_path=_workspace_tmp("cagr_kb") / "report.json"
    ).build(bundle)
    financial_service = FinancialRetrievalService(knowledge_base)
    resolution_service = MetricResolutionService(
        knowledge_base=knowledge_base,
        financial_retrieval_service=financial_service,
    )
    calculation_service = CalculationService(
        financial_retrieval_service=financial_service,
        metric_resolution_service=resolution_service,
    )
    evidence_builder = EvidenceBuilderService(
        financial_retrieval_service=financial_service,
        metric_resolution_service=resolution_service,
        calculation_service=calculation_service,
    )
    planner = QueryPlannerService(
        metric_resolution_service=resolution_service,
        financial_retrieval_service=financial_service,
        calculation_service=calculation_service,
        evidence_builder_service=evidence_builder,
    )
    return planner, evidence_builder, ResponseRendererService()


def test_revenue_cagr_explicit_range_routes_and_renders() -> None:
    planner, evidence_builder, renderer = _services()

    plan = planner.plan(QueryRequest(raw_query="Revenue CAGR from 2020 to 2025"))
    evidence = evidence_builder.build_cagr_evidence(plan)
    response = renderer.render_cagr(plan, evidence)

    assert isinstance(plan, CAGRPlan)
    assert plan.intent == QueryIntent.CAGR
    assert plan.requested_metric == "revenue"
    assert plan.requested_year is None
    assert plan.start_year == 2020
    assert plan.end_year == 2025
    assert evidence.calculation["calculation_type"] == "cagr"
    assert isinstance(response, CAGRResponse)
    assert response.answer_type == QueryResponseType.CAGR
    assert response.cagr_value == pytest.approx(14.869835, rel=1e-6)
    assert response.start_year == 2020
    assert response.end_year == 2025
    assert response.years == (2020, 2025)
    assert response.citations


def test_eps_cagr_implicit_full_history() -> None:
    planner, evidence_builder, renderer = _services()

    plan = planner.plan(QueryRequest(raw_query="What was EPS CAGR?"))
    response = renderer.render_cagr(plan, evidence_builder.build_cagr_evidence(plan))

    assert isinstance(plan, CAGRPlan)
    assert plan.resolved_metric == "earnings_per_share"
    assert plan.start_year == 2020
    assert plan.end_year == 2025
    assert response.cagr_value == pytest.approx(14.869835, rel=1e-6)


def test_cash_cagr_with_punctuated_normalized_query() -> None:
    planner, evidence_builder, renderer = _services()

    plan = planner.plan(
        QueryRequest(
            raw_query="What was cash CAGR?",
            normalized_query="what was cash cagr?",
        )
    )
    response = renderer.render_cagr(plan, evidence_builder.build_cagr_evidence(plan))

    assert isinstance(plan, CAGRPlan)
    assert plan.resolved_metric == "cash_and_cash_equivalents"
    assert plan.start_year == 2020
    assert plan.end_year == 2025
    assert response.is_answerable is True
    assert response.citations


def test_eps_cagr_with_punctuated_normalized_query() -> None:
    planner, evidence_builder, renderer = _services()

    plan = planner.plan(
        QueryRequest(
            raw_query="What was EPS CAGR?",
            normalized_query="what was eps cagr?",
        )
    )
    response = renderer.render_cagr(plan, evidence_builder.build_cagr_evidence(plan))

    assert isinstance(plan, CAGRPlan)
    assert plan.resolved_metric == "earnings_per_share"
    assert plan.start_year == 2020
    assert plan.end_year == 2025
    assert response.is_answerable is True
    assert response.citations


def test_operating_profit_compound_annual_growth_rate() -> None:
    planner, evidence_builder, renderer = _services()

    plan = planner.plan(
        QueryRequest(raw_query="Operating profit compound annual growth rate")
    )
    response = renderer.render_cagr(plan, evidence_builder.build_cagr_evidence(plan))

    assert isinstance(plan, CAGRPlan)
    assert plan.intent == QueryIntent.COMPOUND_ANNUAL_GROWTH_RATE
    assert plan.resolved_metric == "operating_profit"
    assert response.cagr_value == pytest.approx(21.058328, rel=1e-6)


def test_hyphenated_year_range() -> None:
    planner, _, _ = _services()

    plan = planner.plan(QueryRequest(raw_query="Revenue CAGR 2021-2025"))

    assert isinstance(plan, CAGRPlan)
    assert plan.start_year == 2021
    assert plan.end_year == 2025


def test_last_five_years_range() -> None:
    planner, _, _ = _services()

    plan = planner.plan(QueryRequest(raw_query="Revenue CAGR last 5 years"))

    assert isinstance(plan, CAGRPlan)
    assert plan.start_year == 2021
    assert plan.end_year == 2025


def test_insufficient_history_is_invalid() -> None:
    planner, evidence_builder, renderer = _services()

    plan = planner.plan(QueryRequest(raw_query="Capex CAGR"))
    evidence = evidence_builder.build_cagr_evidence(plan)
    response = renderer.render_cagr(plan, evidence)

    assert isinstance(plan, CAGRPlan)
    assert plan.is_valid is False
    assert "missing start_year or end_year for CAGR query" in plan.errors
    assert evidence.evidence_complete is False
    assert response.is_answerable is False
