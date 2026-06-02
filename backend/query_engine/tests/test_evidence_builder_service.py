"""Tests for deterministic evidence bundle construction."""

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
from query_engine.services.calculation_service import CalculationService
from query_engine.services.evidence_builder_service import EvidenceBuilderService
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


def _services() -> tuple[EvidenceBuilderService, CalculationService]:
    workbook_fingerprint = "fp_phase4"
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
        workbook_id="wb_phase4",
        workbook_fingerprint=workbook_fingerprint,
        company_name="Lucky Cement Limited",
        report_years=[2025],
        workbook_result=WorkbookResult(
            output_file_path="output/test_query_engine_phase4.xlsx",
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
        report_path=_workspace_tmp("phase4_kb") / "report.json"
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
    return evidence_builder, calculation_service


def test_single_metric_evidence() -> None:
    evidence_builder, _ = _services()

    bundle = evidence_builder.build_metric_evidence("revenue")

    assert bundle.bundle_type == "metric"
    assert bundle.resolved_metric == "revenue"
    assert bundle.evidence_complete is True
    assert len(bundle.metrics) == 3
    assert bundle.confidence > 0


def test_year_evidence() -> None:
    evidence_builder, _ = _services()

    bundle = evidence_builder.build_metric_year_evidence("revenue", 2025)

    assert bundle.bundle_type == "metric_year"
    assert bundle.evidence_complete is True
    assert [metric.value_year for metric in bundle.metrics] == [2025]
    assert bundle.metrics[0].value == 1500


def test_history_evidence() -> None:
    evidence_builder, _ = _services()

    bundle = evidence_builder.build_metric_history_evidence("revenue")

    assert bundle.bundle_type == "metric_history"
    assert bundle.series is not None
    assert [point.value_year for point in bundle.series.points] == [2023, 2024, 2025]
    assert bundle.provenance_consistent is True


def test_growth_evidence() -> None:
    evidence_builder, calculation_service = _services()
    calculation = calculation_service.year_over_year_growth("revenue", 2025)

    bundle = evidence_builder.build_calculation_evidence(calculation)

    assert bundle.bundle_type == "calculation"
    assert bundle.calculation["calculation_type"] == "year_over_year_growth"
    assert bundle.calculation["value"] == pytest.approx(25.0)
    assert bundle.series is not None
    assert [point.value_year for point in bundle.series.points] == [2024, 2025]
    assert bundle.evidence_complete is True


def test_conflict_propagation() -> None:
    evidence_builder, _ = _services()

    bundle = evidence_builder.build_metric_year_evidence("gross profit", 2025)

    assert bundle.has_unresolved_conflicts is True
    assert bundle.conflicts
    assert bundle.conflicts[0].conflict_status == "unresolved"
    assert bundle.metrics[0].unresolved_conflict is True


def test_citation_propagation() -> None:
    evidence_builder, calculation_service = _services()
    calculation = calculation_service.absolute_change("revenue", 2024, 2025)

    bundle = evidence_builder.build_calculation_evidence(calculation)

    assert bundle.citation_complete is True
    assert len(bundle.citations) == 2
    assert {citation.cell_reference for citation in bundle.citations} == {"B3", "B4"}
    assert all(metric.citation.sheet_name == "Income Statement" for metric in bundle.metrics)
