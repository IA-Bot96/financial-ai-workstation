"""Tests for immutable Query Engine knowledge-base construction."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult
from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.services.knowledge_base_builder import KnowledgeBaseBuilder
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


def _workbook_result() -> WorkbookResult:
    return WorkbookResult(
        output_file_path="output/test_query_engine_phase1.xlsx",
        workbook_mode="dynamic",
        workbook_match_score=0,
        sheets_reused=[],
        sheets_replaced=[],
        sheets_created=["Income Statement", "Balance Sheet"],
        metrics_written=2,
        warnings=[],
    )


def _metric_value(
    metric: str,
    value_year: int,
    value: int,
    table_type: str,
    page_number: int,
    source_report_year: int = 2025,
) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=value_year,
        value=value,
        source_report_year=source_report_year,
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
    confidence: float = 0.96,
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
        statement_scope="consolidated",
        normalization_confidence=confidence,
        source_confidence=confidence,
        original_metric=metric.replace("_", " ").title(),
        requires_review=requires_review,
        label_cleanliness_score=10,
        source_context_score=10,
        table_type_priority=1,
    )


def _bundle(
    *,
    include_revenue_mapping: bool = True,
    bad_source_year: bool = False,
) -> QueryEngineInputBundle:
    workbook_fingerprint = "fp_phase1"
    cash_year = 2024 if bad_source_year else 2025
    revenue = _metric_value(
        "revenue",
        2025,
        1000,
        "income_statement",
        10,
    )
    cash = _metric_value("cash", cash_year, 250, "balance_sheet", 11, cash_year)
    selected = _candidate("revenue", 2025, 1000, "income_statement", 10)
    competing = _candidate(
        "revenue",
        2025,
        900,
        "income_statement",
        12,
        confidence=0.8,
        requires_review=True,
    )
    group = ConsolidationGroup(
        metric="revenue",
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
    mappings = []
    if include_revenue_mapping:
        mappings.append(
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
            ).to_record(workbook_fingerprint)
        )
    mappings.append(
        WorkbookCellMappingDraft(
            metric="cash",
            value_year=cash_year,
            source_report_year=cash_year,
            table_type="balance_sheet",
            sheet_name="Balance Sheet",
            row=2,
            column=2,
            cell_reference="B2",
            write_status="written",
            written_value=250,
        ).to_record(workbook_fingerprint)
    )
    return QueryEngineInputBundle(
        schema_version="1.0.0",
        workbook_id="wb_phase1",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=_workbook_result(),
        financial_year_consolidation_result=FinancialYearConsolidationResult(
            metric_values=[revenue, cash],
            groups=[group],
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
                        confidence=0.9,
                    )
                ]
            )
        },
        workbook_cell_mappings=mappings,
    )


def test_knowledge_base_builder_loads_datasets_and_report() -> None:
    report_path = _workspace_tmp("phase1_report") / "query_engine_phase1_report.json"
    builder = KnowledgeBaseBuilder(report_path=report_path)

    knowledge_base = builder.build(_bundle())

    assert knowledge_base.metadata.company_name == "Lucky Cement Limited"
    assert len(knowledge_base.financial_dataset.records) == 2
    assert len(knowledge_base.insight_dataset.records) == 1
    assert len(knowledge_base.conflict_dataset.records) == 1
    assert len(knowledge_base.conflict_dataset.unresolved_conflicts) == 1
    assert knowledge_base.validation_result.is_valid is True
    assert report_path.exists()
    assert builder.last_report is not None
    assert builder.last_report.financial_records_loaded == 2


def test_knowledge_base_indexes_financial_and_insight_records() -> None:
    knowledge_base = KnowledgeBaseBuilder(
        report_path=_workspace_tmp("phase1_index") / "report.json"
    ).build(_bundle())

    revenue_records = knowledge_base.financial_dataset.records_for_metric("revenue")
    year_records = knowledge_base.financial_dataset.records_for_value_year(2025)
    insight_records = knowledge_base.insight_dataset.records_for_report_year(2025)

    assert len(revenue_records) == 1
    assert revenue_records[0].workbook_citation.cell_reference == "B2"
    assert len(year_records) == 2
    assert len(insight_records) == 1
    assert (
        knowledge_base.financial_dataset.indexes.count_summary()["by_statement_scope"]
        == 2
    )
    assert knowledge_base.insight_dataset.indexes.count_summary()["by_category"] == 1


def test_knowledge_base_validation_warns_when_mapping_missing() -> None:
    knowledge_base = KnowledgeBaseBuilder(
        report_path=_workspace_tmp("phase1_missing_mapping") / "report.json"
    ).build(_bundle(include_revenue_mapping=False))

    assert knowledge_base.validation_result.is_valid is True
    assert any(
        "no workbook cell mapping" in warning
        for warning in knowledge_base.validation_result.warnings
    )
    revenue = knowledge_base.financial_dataset.records_for_metric("revenue")[0]
    assert revenue.workbook_citation.citation_status == "missing"


def test_knowledge_base_validation_flags_source_year_outside_report_years() -> None:
    knowledge_base = KnowledgeBaseBuilder(
        report_path=_workspace_tmp("phase1_bad_year") / "report.json"
    ).build(_bundle(bad_source_year=True))

    assert knowledge_base.validation_result.is_valid is False
    assert any(
        "outside report_years" in error
        for error in knowledge_base.validation_result.errors
    )


def test_knowledge_base_is_immutable() -> None:
    knowledge_base = KnowledgeBaseBuilder(
        report_path=_workspace_tmp("phase1_immutable") / "report.json"
    ).build(_bundle())

    with pytest.raises(ValidationError):
        knowledge_base.metadata.company_name = "Other"

    with pytest.raises(AttributeError):
        knowledge_base.financial_dataset.records.append(  # type: ignore[attr-defined]
            knowledge_base.financial_dataset.records[0]
        )
