"""Tests for Query Engine metric resolution against the canonical registry."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.knowledge_base_builder import KnowledgeBaseBuilder
from query_engine.services.metric_resolution_service import MetricResolutionService
from shared.models.financial_year_consolidation import FinancialYearConsolidationResult
from shared.models.metric_value import MetricValue
from workbook_population.models.workbook_cell_mapping import WorkbookCellMappingDraft
from workbook_population.models.workbook_result import WorkbookResult


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _metric_value(metric: str, value: int, page_number: int) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=2025,
        value=value,
        source_report_year=2025,
        page_number=page_number,
        table_type="income_statement",
    )


def _mapping(
    metric: str,
    row: int,
    workbook_fingerprint: str,
) -> object:
    return WorkbookCellMappingDraft(
        metric=metric,
        value_year=2025,
        source_report_year=2025,
        table_type="income_statement",
        sheet_name="Income Statement",
        row=row,
        column=2,
        cell_reference=f"B{row}",
        write_status="written",
        written_value=100,
    ).to_record(workbook_fingerprint)


def _resolution_service() -> MetricResolutionService:
    workbook_fingerprint = "fp_phase2_5"
    metrics = [
        "revenue",
        "revenue_per_employee",
        "earnings_per_share",
        "total_debt",
        "current_portion_long_term_debt",
        "debt_to_equity",
        "capital_expenditure",
        "operating_profit",
        "profit_after_tax",
        "equity",
        "return_on_equity",
        "cash_and_cash_equivalents",
        "cash_at_beginning_of_period",
        "operating_cash_flow",
        "free_cash_flow",
    ]
    metric_values = [
        _metric_value(metric, index * 100, index)
        for index, metric in enumerate(metrics, start=1)
    ]
    bundle = QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_phase2_5",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=WorkbookResult(
            output_file_path="output/test_query_engine_phase2_5.xlsx",
            workbook_mode="dynamic",
            workbook_match_score=0,
            sheets_reused=[],
            sheets_replaced=[],
            sheets_created=["Income Statement"],
            metrics_written=len(metrics),
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
            _mapping(metric, index, workbook_fingerprint)
            for index, metric in enumerate(metrics, start=1)
        ],
    )
    knowledge_base = KnowledgeBaseBuilder(
        report_path=_workspace_tmp("phase2_5_kb") / "report.json"
    ).build(bundle)
    financial_service = FinancialRetrievalService(knowledge_base)
    return MetricResolutionService(
        knowledge_base=knowledge_base,
        financial_retrieval_service=financial_service,
    )


def test_metric_resolution_eps_alias() -> None:
    result = _resolution_service().resolve_metric("EPS")

    assert result.resolved_metric == "earnings_per_share"
    assert result.best_candidate is not None
    assert result.best_candidate.match_type == "alias"
    assert result.best_candidate.available_in_dataset is True


def test_metric_resolution_debt_returns_candidates() -> None:
    result = _resolution_service().resolve_metric("Debt")

    candidate_metrics = {candidate.canonical_metric for candidate in result.candidates}

    assert result.found is True
    assert result.is_ambiguous is True
    assert result.resolved_metric == "total_debt"
    assert "total_debt" in candidate_metrics
    assert "current_portion_long_term_debt" in candidate_metrics
    assert "debt_to_equity" in candidate_metrics


def test_metric_resolution_total_debt_with_punctuation() -> None:
    result = _resolution_service().resolve_metric("total debt ?")

    assert result.resolved_metric == "total_debt"
    assert result.best_candidate is not None
    assert result.best_candidate.match_type == "alias"
    assert result.best_candidate.available_in_dataset is True


def test_metric_resolution_capex_alias() -> None:
    result = _resolution_service().resolve_best_metric("Capex")

    assert result is not None
    assert result.canonical_metric == "capital_expenditure"
    assert result.match_type == "alias"


def test_metric_resolution_revenue_exact() -> None:
    result = _resolution_service().resolve_metric("revenue")

    assert result.resolved_metric == "revenue"
    assert result.is_ambiguous is False
    assert result.best_candidate is not None
    assert result.best_candidate.match_type == "exact"
    assert [candidate.canonical_metric for candidate in result.candidates] == [
        "revenue"
    ]


def test_metric_resolution_operating_profit_prefers_alias_over_canonical() -> None:
    result = _resolution_service().resolve_metric("Operating Profit")

    assert result.resolved_metric == "operating_profit"
    assert result.is_ambiguous is False
    assert result.best_candidate is not None
    assert result.best_candidate.match_type == "alias"


def test_metric_resolution_net_income_prefers_profit_after_tax() -> None:
    result = _resolution_service().resolve_metric("Net Income")

    assert result.resolved_metric == "profit_after_tax"
    assert result.best_candidate is not None
    assert result.best_candidate.canonical_metric == "profit_after_tax"


def test_metric_resolution_cash_flow_is_ambiguous_candidate_family() -> None:
    result = _resolution_service().resolve_metric("Cash Flow")
    candidate_metrics = {candidate.canonical_metric for candidate in result.candidates}

    assert result.found is True
    assert result.is_ambiguous is True
    assert "operating_cash_flow" in candidate_metrics
    assert "free_cash_flow" in candidate_metrics


def test_metric_resolution_cash_prefers_cash_and_cash_equivalents() -> None:
    result = _resolution_service().resolve_metric("cash")
    candidate_metrics = {candidate.canonical_metric for candidate in result.candidates}

    assert result.resolved_metric == "cash_and_cash_equivalents"
    assert result.is_ambiguous is True
    assert "cash_and_cash_equivalents" in candidate_metrics
    assert "cash_at_beginning_of_period" in candidate_metrics


def test_metric_resolution_equity_suppresses_related_fuzzy_candidates() -> None:
    result = _resolution_service().resolve_metric("equity")

    assert result.resolved_metric == "equity"
    assert result.is_ambiguous is False
    assert [candidate.canonical_metric for candidate in result.candidates] == [
        "equity"
    ]


def test_metric_resolution_unknown_metric() -> None:
    result = _resolution_service().resolve_metric("nonexistent management metric")

    assert result.found is False
    assert result.resolved_metric is None
    assert result.candidates == ()
    assert result.warnings == ("unknown metric: nonexistent_management_metric",)
