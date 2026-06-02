"""Tests for deterministic response rendering."""

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
from query_engine.models.query_planner import (
    ConflictPlan,
    MetricComparisonPlan,
    MetricGrowthPlan,
    MetricHistoryPlan,
    MetricValuePlan,
    ProvenancePlan,
)
from query_engine.models.response import (
    ConflictResponse,
    MetricComparisonResponse,
    MetricGrowthResponse,
    MetricHistoryResponse,
    MetricValueResponse,
    ProvenanceResponse,
    QueryResponseType,
)
from query_engine.services.calculation_service import CalculationService
from query_engine.services.evidence_builder_service import EvidenceBuilderService
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.knowledge_base_builder import KnowledgeBaseBuilder
from query_engine.services.metric_resolution_service import MetricResolutionService
from query_engine.services.response_renderer_service import ResponseRendererService
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
    competing = _candidate(
        metric,
        year,
        value - 25 if conflict else value,
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


def _services() -> tuple[EvidenceBuilderService, CalculationService, ResponseRendererService]:
    workbook_fingerprint = "fp_phase6"
    metric_values = [
        _metric_value("revenue", 2023, 1000, 10, "income_statement"),
        _metric_value("revenue", 2024, 1200, 10, "income_statement"),
        _metric_value("revenue", 2025, 1500, 10, "income_statement"),
        _metric_value("gross_profit", 2024, 400, 12, "income_statement"),
        _metric_value("gross_profit", 2025, 500, 12, "income_statement"),
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
        workbook_id="wb_phase6",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=WorkbookResult(
            output_file_path="output/test_query_engine_phase6.xlsx",
            workbook_mode="dynamic",
            workbook_match_score=0,
            sheets_reused=[],
            sheets_replaced=[],
            sheets_created=["Income Statement"],
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
        report_path=_workspace_tmp("phase6_kb") / "report.json"
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
    return evidence_builder, calculation_service, ResponseRendererService()


def test_metric_value_response() -> None:
    evidence_builder, _, renderer = _services()
    plan = MetricValuePlan(
        raw_query="What was revenue in 2025?",
        normalized_query="what was revenue in 2025",
        requested_metric="revenue",
        requested_year=2025,
        resolved_metric="revenue",
        is_valid=True,
    )
    evidence = evidence_builder.build_metric_year_evidence("revenue", 2025)

    response = renderer.render_metric_value(plan, evidence)

    assert isinstance(response, MetricValueResponse)
    assert response.answer_type == QueryResponseType.METRIC_VALUE
    assert response.metric == "revenue"
    assert response.year == 2025
    assert response.value == 1500
    assert response.citations[0].cell_reference == "B4"
    assert response.is_answerable is True


def test_history_response() -> None:
    evidence_builder, _, renderer = _services()
    plan = MetricHistoryPlan(
        raw_query="Show revenue trend.",
        normalized_query="show revenue trend",
        requested_metric="revenue",
        resolved_metric="revenue",
        is_valid=True,
    )
    evidence = evidence_builder.build_metric_history_evidence("revenue")

    response = renderer.render_metric_history(plan, evidence)

    assert isinstance(response, MetricHistoryResponse)
    assert response.answer_type == QueryResponseType.METRIC_HISTORY
    assert response.years == (2023, 2024, 2025)
    assert response.values == (1000, 1200, 1500)
    assert len(response.series) == 3


def test_growth_response() -> None:
    evidence_builder, calculation_service, renderer = _services()
    plan = MetricGrowthPlan(
        raw_query="Show revenue growth in 2025.",
        normalized_query="show revenue growth in 2025",
        requested_metric="revenue",
        requested_year=2025,
        resolved_metric="revenue",
        calculation_type="year_over_year_growth",
        is_valid=True,
    )
    calculation = calculation_service.year_over_year_growth("revenue", 2025)
    evidence = evidence_builder.build_calculation_evidence(calculation)

    response = renderer.render_metric_growth(plan, evidence)

    assert isinstance(response, MetricGrowthResponse)
    assert response.answer_type == QueryResponseType.METRIC_GROWTH
    assert response.result_value == pytest.approx(25.0)
    assert response.result_unit == "percentage"
    assert response.years == (2024, 2025)
    assert len(response.supporting_values) == 2


def test_comparison_response() -> None:
    evidence_builder, _, renderer = _services()
    plan = MetricComparisonPlan(
        raw_query="Compare revenue and gross profit.",
        normalized_query="compare revenue and gross profit",
        requested_metric="revenue",
        comparison_metric="gross profit",
        resolved_metric="revenue",
        resolved_comparison_metric="gross_profit",
        is_valid=True,
    )
    revenue_evidence = evidence_builder.build_metric_evidence("revenue")
    gross_profit_evidence = evidence_builder.build_metric_evidence("gross profit")

    response = renderer.render_metric_comparison(
        plan,
        revenue_evidence,
        gross_profit_evidence,
    )

    assert isinstance(response, MetricComparisonResponse)
    assert response.answer_type == QueryResponseType.METRIC_COMPARISON
    assert response.left_metric == "revenue"
    assert response.right_metric == "gross_profit"
    assert response.has_conflicts is True
    assert response.left_values
    assert response.right_values


def test_conflict_response_surfaces_conflicts() -> None:
    evidence_builder, _, renderer = _services()
    plan = ConflictPlan(
        raw_query="Show conflicting values for gross profit.",
        normalized_query="show conflicting values for gross profit",
        requested_metric="gross profit",
        resolved_metric="gross_profit",
        conflict_count=1,
        is_valid=True,
    )
    evidence = evidence_builder.build_metric_year_evidence("gross profit", 2025)

    response = renderer.render_conflict(plan, evidence)

    assert isinstance(response, ConflictResponse)
    assert response.answer_type == QueryResponseType.CONFLICT
    assert response.has_conflicts is True
    assert response.conflict_count == 1
    assert response.values == (500, 475)
    assert response.conflict_details[0].conflict_status == "unresolved"


def test_provenance_response() -> None:
    evidence_builder, _, renderer = _services()
    plan = ProvenancePlan(
        raw_query="Why was gross profit selected?",
        normalized_query="why was gross profit selected",
        requested_metric="gross profit",
        resolved_metric="gross_profit",
        is_valid=True,
    )
    evidence = evidence_builder.build_metric_year_evidence("gross profit", 2025)

    response = renderer.render_provenance(plan, evidence)

    assert isinstance(response, ProvenanceResponse)
    assert response.answer_type == QueryResponseType.PROVENANCE
    assert response.selected_value == 500
    assert response.competing_values == (475,)
    assert response.resolution_reason == "requires_analyst_review"
    assert response.source_page == 12
    assert response.source_type == "primary_statement"
