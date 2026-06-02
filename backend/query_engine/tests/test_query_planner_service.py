"""Tests for deterministic Query Planner service."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.models.query_planner import (
    ConflictPlan,
    MetricComparisonPlan,
    MetricGrowthPlan,
    MetricHistoryPlan,
    MetricValuePlan,
    ProvenancePlan,
    QueryIntent,
    QueryRequest,
)
from query_engine.services.calculation_service import CalculationService
from query_engine.services.evidence_builder_service import EvidenceBuilderService
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.knowledge_base_builder import KnowledgeBaseBuilder
from query_engine.services.metric_resolution_service import MetricResolutionService
from query_engine.services.query_planner_service import QueryPlannerService
from shared.models.financial_year_consolidation import (
    ConsolidationCandidate,
    ConsolidationGroup,
    FinancialYearConsolidationResult,
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
        statement_scope="consolidated",
        normalization_confidence=confidence,
        source_confidence=confidence,
        original_metric=metric.replace("_", " ").title(),
        requires_review=requires_review,
        label_cleanliness_score=10,
        source_context_score=10,
        table_type_priority=1,
    )


def _cash_conflict_group() -> ConsolidationGroup:
    selected = _candidate(
        "cash_and_cash_equivalents",
        2025,
        500,
        20,
        "cash_flow",
    )
    competing = _candidate(
        "cash_and_cash_equivalents",
        2025,
        475,
        21,
        "balance_sheet",
        confidence=0.8,
        requires_review=True,
    )
    return ConsolidationGroup(
        metric="cash_and_cash_equivalents",
        value_year=2025,
        candidate_count=2,
        selected=selected,
        competing_candidates=[competing],
        is_duplicate_group=True,
        is_conflict_group=True,
        conflict_resolved=False,
        unresolved_conflict=True,
        conflict_status="unresolved",
        resolution_reason="requires_analyst_review",
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


def _planner_service() -> QueryPlannerService:
    workbook_fingerprint = "fp_phase5"
    metric_values = [
        _metric_value("revenue", 2023, 1000, 10, "income_statement"),
        _metric_value("revenue", 2024, 1200, 10, "income_statement"),
        _metric_value("revenue", 2025, 1500, 10, "income_statement"),
        _metric_value("earnings_per_share", 2025, 15, 12, "income_statement"),
        _metric_value("total_debt", 2025, 700, 16, "balance_sheet"),
        _metric_value("cash_and_cash_equivalents", 2025, 500, 20, "cash_flow"),
    ]
    bundle = QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_phase5",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=WorkbookResult(
            output_file_path="output/test_query_engine_phase5.xlsx",
            workbook_mode="dynamic",
            workbook_match_score=0,
            sheets_reused=[],
            sheets_replaced=[],
            sheets_created=["Income Statement", "Balance Sheet", "Cash Flow"],
            metrics_written=len(metric_values),
            warnings=[],
        ),
        financial_year_consolidation_result=FinancialYearConsolidationResult(
            metric_values=metric_values,
            groups=[_cash_conflict_group()],
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
        report_path=_workspace_tmp("phase5_kb") / "report.json"
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
    return QueryPlannerService(
        metric_resolution_service=resolution_service,
        financial_retrieval_service=financial_service,
        calculation_service=calculation_service,
        evidence_builder_service=evidence_builder,
    )


def test_value_query_plan() -> None:
    plan = _planner_service().plan(
        QueryRequest(raw_query="What was revenue in 2025?")
    )

    assert isinstance(plan, MetricValuePlan)
    assert plan.intent == QueryIntent.METRIC_VALUE
    assert plan.requested_metric == "revenue"
    assert plan.requested_year == 2025
    assert plan.resolved_metric == "revenue"
    assert plan.is_valid is True


def test_history_query_plan() -> None:
    plan = _planner_service().plan(QueryRequest(raw_query="Show revenue trend."))

    assert isinstance(plan, MetricHistoryPlan)
    assert plan.intent == QueryIntent.METRIC_HISTORY
    assert plan.resolved_metric == "revenue"
    assert plan.evidence_method == "build_metric_history_evidence"
    assert plan.is_valid is True


def test_growth_query_plan() -> None:
    plan = _planner_service().plan(QueryRequest(raw_query="Show revenue growth."))

    assert isinstance(plan, MetricGrowthPlan)
    assert plan.intent == QueryIntent.METRIC_GROWTH
    assert plan.resolved_metric == "revenue"
    assert plan.calculation_type == "multi_year_series"
    assert plan.is_valid is True


def test_comparison_query_plan() -> None:
    plan = _planner_service().plan(QueryRequest(raw_query="Compare debt and cash."))

    assert isinstance(plan, MetricComparisonPlan)
    assert plan.intent == QueryIntent.METRIC_COMPARISON
    assert plan.requested_metric == "debt"
    assert plan.comparison_metric == "cash"
    assert plan.resolved_metric == "total_debt"
    assert plan.resolved_comparison_metric == "cash_and_cash_equivalents"
    assert plan.is_valid is True


def test_conflict_query_plan() -> None:
    plan = _planner_service().plan(
        QueryRequest(raw_query="Show conflicting values for cash.")
    )

    assert isinstance(plan, ConflictPlan)
    assert plan.intent == QueryIntent.CONFLICT_EXPLANATION
    assert plan.resolved_metric == "cash_and_cash_equivalents"
    assert plan.conflict_count == 1
    assert plan.is_valid is True


def test_provenance_query_plan() -> None:
    plan = _planner_service().plan(QueryRequest(raw_query="Why was EPS selected?"))

    assert isinstance(plan, ProvenancePlan)
    assert plan.intent == QueryIntent.PROVENANCE_LOOKUP
    assert plan.requested_metric == "eps"
    assert plan.resolved_metric == "earnings_per_share"
    assert plan.is_valid is True


def test_missing_year_for_value_query_is_invalid() -> None:
    plan = _planner_service().plan(
        QueryRequest(raw_query="What was revenue?", intent=QueryIntent.METRIC_VALUE)
    )

    assert isinstance(plan, MetricValuePlan)
    assert plan.is_valid is False
    assert "missing year for metric value query" in plan.errors


def test_unknown_metric_is_invalid() -> None:
    plan = _planner_service().plan(
        QueryRequest(raw_query="What was imaginary metric in 2025?")
    )

    assert isinstance(plan, MetricValuePlan)
    assert plan.is_valid is False
    assert "metric could not be resolved" in plan.errors
