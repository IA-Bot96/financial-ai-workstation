"""Tests for deterministic Query Engine retrieval services."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult
from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.services.financial_retrieval_service import FinancialRetrievalService
from query_engine.services.insight_retrieval_service import InsightRetrievalService
from query_engine.services.knowledge_base_builder import KnowledgeBaseBuilder
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
    value_year: int,
    value: int,
    table_type: str,
    page_number: int,
) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=value_year,
        value=value,
        source_report_year=2025,
        page_number=page_number,
        table_type=table_type,
    )


def _candidate(
    metric: str,
    value_year: int,
    value: int,
    table_type: str,
    page_number: int,
    *,
    confidence: float = 0.95,
    scope: StatementScope = "consolidated",
    requires_review: bool = False,
) -> ConsolidationCandidate:
    return ConsolidationCandidate(
        metric=metric,
        value_year=value_year,
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


def _mapping(
    metric: str,
    value_year: int,
    table_type: str,
    row: int,
    workbook_fingerprint: str,
) -> object:
    return WorkbookCellMappingDraft(
        metric=metric,
        value_year=value_year,
        source_report_year=2025,
        table_type=table_type,
        sheet_name=table_type.replace("_", " ").title(),
        row=row,
        column=2,
        cell_reference=f"B{row}",
        write_status="written",
        written_value=1000,
    ).to_record(workbook_fingerprint)


def _knowledge_base():
    workbook_fingerprint = "fp_phase2"
    revenue_2025 = _metric_value("revenue", 2025, 1200, "income_statement", 10)
    revenue_2024 = _metric_value("revenue", 2024, 1000, "income_statement", 10)
    debt_2025 = _metric_value("debt", 2025, 500, "balance_sheet", 11)
    cash_2025 = _metric_value("cash_and_cash_equivalents", 2025, 300, "cash_flow", 12)
    debt_group = ConsolidationGroup(
        metric="debt",
        value_year=2025,
        candidate_count=2,
        selected=_candidate("debt", 2025, 500, "balance_sheet", 11),
        competing_candidates=[
            _candidate(
                "debt",
                2025,
                650,
                "debt_note",
                45,
                confidence=0.72,
                requires_review=True,
            )
        ],
        is_duplicate_group=True,
        is_conflict_group=True,
        conflict_resolved=False,
        unresolved_conflict=True,
        conflict_status="unresolved",
        resolution_reason="requires_analyst_review",
    )
    bundle = QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_phase2",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=WorkbookResult(
            output_file_path="output/test_query_engine_phase2.xlsx",
            workbook_mode="dynamic",
            workbook_match_score=0,
            sheets_reused=[],
            sheets_replaced=[],
            sheets_created=["Income Statement", "Balance Sheet", "Cash Flow"],
            metrics_written=4,
            warnings=[],
        ),
        financial_year_consolidation_result=FinancialYearConsolidationResult(
            metric_values=[revenue_2025, revenue_2024, debt_2025, cash_2025],
            groups=[debt_group],
        ),
        insights_results_by_report_year={
            2025: InsightsExtractionResult(
                insights=[
                    Insight(
                        value_year=2025,
                        source_report_year=2025,
                        area="Debt",
                        takeaway="Borrowings increased for expansion.",
                        source_section="Business Review",
                        page_number=25,
                        confidence=0.91,
                    ),
                    Insight(
                        value_year=2025,
                        source_report_year=2025,
                        area="Revenue Growth",
                        takeaway="Revenue increased due to higher dispatches.",
                        source_section="Management Discussion",
                        page_number=31,
                        confidence=0.88,
                    ),
                ]
            )
        },
        workbook_cell_mappings=[
            _mapping("revenue", 2025, "income_statement", 2, workbook_fingerprint),
            _mapping("revenue", 2024, "income_statement", 3, workbook_fingerprint),
            _mapping("debt", 2025, "balance_sheet", 4, workbook_fingerprint),
            _mapping(
                "cash_and_cash_equivalents",
                2025,
                "cash_flow",
                5,
                workbook_fingerprint,
            ),
        ],
    )
    return KnowledgeBaseBuilder(
        report_path=_workspace_tmp("phase2_kb") / "report.json"
    ).build(bundle)


def test_financial_retrieval_exact_metric() -> None:
    service = FinancialRetrievalService(_knowledge_base())

    result = service.retrieve_by_metric("Revenue")

    assert result.found is True
    assert result.normalized_metric == "revenue"
    assert len(result.financial_records) == 2
    assert result.candidates[0].workbook_citation is not None
    assert result.evidence[0].metric == "revenue"


def test_financial_retrieval_metric_and_year() -> None:
    service = FinancialRetrievalService(_knowledge_base())

    result = service.retrieve_by_metric_and_year("revenue", 2025)

    assert result.found is True
    assert result.query_year == 2025
    assert len(result.financial_records) == 1
    assert result.financial_records[0].value == 1200
    assert result.financial_records[0].workbook_citation.cell_reference == "B2"


def test_financial_retrieval_metric_history() -> None:
    service = FinancialRetrievalService(_knowledge_base())

    result = service.retrieve_metric_history("revenue")

    assert [record.value_year for record in result.financial_records] == [2024, 2025]


def test_financial_retrieval_by_statement_scope() -> None:
    service = FinancialRetrievalService(_knowledge_base())

    result = service.retrieve_by_statement_scope("debt", "consolidated")

    assert result.found is True
    assert len(result.financial_records) == 1
    assert result.financial_records[0].statement_scope == "consolidated"


def test_financial_retrieval_surfaces_unresolved_conflicts() -> None:
    service = FinancialRetrievalService(_knowledge_base())

    result = service.retrieve_metric_candidates("debt")

    assert result.has_unresolved_conflicts is True
    assert result.is_ambiguous is True
    assert len(result.conflicts) == 1
    assert len(result.candidates) == 2
    assert {candidate.candidate_type for candidate in result.candidates} == {
        "selected_financial_record",
        "competing_conflict_candidate",
    }


def test_financial_retrieval_missing_metric_behavior() -> None:
    service = FinancialRetrievalService(_knowledge_base())

    result = service.retrieve_by_metric("ebitda")

    assert result.found is False
    assert result.financial_records == ()
    assert "missing metric: ebitda" in result.warnings


def test_insight_retrieval_by_report_year_and_category() -> None:
    service = InsightRetrievalService(_knowledge_base())

    year_result = service.retrieve_by_report_year(2025)
    category_result = service.retrieve_by_category("Debt")

    assert year_result.found is True
    assert len(year_result.insights) == 2
    assert category_result.found is True
    assert len(category_result.insights) == 1
    assert category_result.insights[0].area == "Debt"


def test_insight_retrieval_by_topic() -> None:
    service = InsightRetrievalService(_knowledge_base())

    result = service.retrieve_by_topic("revenue growth")

    assert result.found is True
    assert len(result.insights) == 1
    assert result.insights[0].topic == "revenue_growth"


def test_insight_retrieval_related_to_metric() -> None:
    service = InsightRetrievalService(_knowledge_base())

    result = service.retrieve_related_to_metric("revenue")

    assert result.found is True
    assert len(result.insights) == 1
    assert "Revenue" in result.insights[0].area


def test_insight_retrieval_missing_category_behavior() -> None:
    service = InsightRetrievalService(_knowledge_base())

    result = service.retrieve_by_category("Exports")

    assert result.found is False
    assert result.insights == ()
    assert "missing insight category: exports" in result.warnings
