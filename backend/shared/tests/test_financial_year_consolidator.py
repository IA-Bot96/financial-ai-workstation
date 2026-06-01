"""Unit tests for comparative-year metric value consolidation."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_normalization import MetricMapping, NormalizationResult
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue
from shared.models.report import Report
from shared.services.financial_year_consolidator import FinancialYearConsolidator


def _metric_value(
    metric: str,
    value_year: int,
    value: int | str,
    source_report_year: int,
    page_number: int = 120,
    table_type: str = "income_statement",
) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=value_year,
        value=value,
        source_report_year=source_report_year,
        page_number=page_number,
        table_type=table_type,
    )


def _report(year: int) -> Report:
    return Report(
        id=f"rpt_{year}",
        company_name="Maple Leaf Cement Factory Limited",
        year=year,
        file_name=f"MLCF_{year}_Annual_Report.pdf",
        file_path=f"reports/MLCF_{year}.pdf",
    )


def _mapping(
    original_metric: str,
    normalized_metric: str,
    value_year: int,
    source_report_year: int,
    confidence: float,
    requires_review: bool = False,
) -> MetricMapping:
    return MetricMapping(
        value_year=value_year,
        source_report_year=source_report_year,
        original_metric=original_metric,
        normalized_metric=normalized_metric,
        confidence=confidence,
        requires_review=requires_review,
    )


def test_consolidator_prefers_latest_source_report_for_value_year(
    caplog: pytest.LogCaptureFixture,
) -> None:
    values = [
        _metric_value("revenue", 2024, 1400, 2024),
        _metric_value("revenue", 2024, 1500, 2025),
        _metric_value("revenue", 2023, 1200, 2024),
        _metric_value("ebitda", 2024, 320, 2025),
    ]

    with caplog.at_level(logging.INFO):
        result = FinancialYearConsolidator().consolidate(values)

    assert [metric_value.model_dump() for metric_value in result] == [
        {
            "metric": "ebitda",
            "value_year": 2024,
            "value": 320,
            "source_report_year": 2025,
            "page_number": 120,
            "table_type": "income_statement",
        },
        {
            "metric": "revenue",
            "value_year": 2023,
            "value": 1200,
            "source_report_year": 2024,
            "page_number": 120,
            "table_type": "income_statement",
        },
        {
            "metric": "revenue",
            "value_year": 2024,
            "value": 1500,
            "source_report_year": 2025,
            "page_number": 120,
            "table_type": "income_statement",
        },
    ]
    assert "Metric value superseded" in caplog.text


def test_consolidator_tie_breaks_duplicate_metrics_in_same_report() -> None:
    values = [
        _metric_value("revenue", 2024, 1500, 2025, page_number=120),
        _metric_value("revenue", 2024, 1400, 2025, page_number=20),
    ]

    result = FinancialYearConsolidator().consolidate(values)

    assert len(result) == 1
    assert result[0].value == 1400
    assert result[0].page_number == 20


def test_consolidator_tie_breaks_equal_source_report_year_conflicts() -> None:
    values = [
        _metric_value("revenue", 2024, 1500, 2025, page_number=20),
        _metric_value("revenue", 2024, 1400, 2025, page_number=20),
    ]

    result = FinancialYearConsolidator().consolidate(values)

    assert len(result) == 1
    assert result[0].value == 1400


def test_consolidator_prefers_higher_normalization_confidence_for_lucky_duplicate(
) -> None:
    result = NormalizationResult(
        tables=[],
        metric_values=[
            _metric_value(
                "other_income",
                2025,
                100,
                2025,
                page_number=164,
                table_type="income_statement",
            ),
            _metric_value(
                "other_income",
                2025,
                110,
                2025,
                page_number=164,
                table_type="income_statement",
            ),
        ],
        mappings=[
            _mapping(
                "(Other Income)/Charges",
                "other_income",
                2025,
                2025,
                0.91,
            ),
            _mapping(
                "(Other Income)/Charg es",
                "other_income",
                2025,
                2025,
                0.72,
            ),
        ],
    )
    consolidator = FinancialYearConsolidator()

    consolidated = consolidator.consolidate_normalization_result(result)

    assert len(consolidated) == 1
    assert consolidated[0].value == 100
    diagnostics = consolidator.last_diagnostics
    assert diagnostics.duplicate_groups_resolved == 1
    assert diagnostics.conflict_groups_resolved == 1
    assert diagnostics.metric_values_removed == 1
    assert diagnostics.groups[0].resolution_reason == (
        "higher_normalization_confidence"
    )


def test_consolidator_prefers_cleaner_reconstructed_label_for_lucky_conflict(
) -> None:
    result = NormalizationResult(
        tables=[],
        metric_values=[
            _metric_value("cash_flow_coverage_ratio", 2025, 2.5, 2025),
            _metric_value("cash_flow_coverage_ratio", 2025, 2.7, 2025),
        ],
        mappings=[
            _mapping(
                "Cash flow Coverage ratio times",
                "cash_flow_coverage_ratio",
                2025,
                2025,
                0.91,
            ),
            _mapping(
                "Cash flow Coverage ra tio times",
                "cash_flow_coverage_ratio",
                2025,
                2025,
                0.91,
            ),
        ],
    )
    consolidator = FinancialYearConsolidator()

    consolidated = consolidator.consolidate_normalization_result(result)

    assert len(consolidated) == 1
    assert consolidated[0].value == 2.5
    assert consolidator.last_diagnostics.groups[0].resolution_reason == (
        "cleaner_reconstructed_label"
    )


def test_consolidator_prefers_statement_source_over_note_for_millat_metric(
) -> None:
    result = NormalizationResult(
        tables=[],
        metric_values=[
            _metric_value(
                "revenue",
                2024,
                1500,
                2025,
                page_number=20,
                table_type="income_statement",
            ),
            _metric_value(
                "revenue",
                2024,
                1490,
                2025,
                page_number=210,
                table_type="revenue_note",
            ),
        ],
        mappings=[
            _mapping("Revenue", "revenue", 2024, 2025, 0.96),
            _mapping("Revenue", "revenue", 2024, 2025, 0.96),
        ],
    )
    consolidator = FinancialYearConsolidator()

    consolidated = consolidator.consolidate_normalization_result(result)

    assert len(consolidated) == 1
    assert consolidated[0].value == 1500
    assert consolidated[0].table_type == "income_statement"
    assert consolidator.last_diagnostics.groups[0].resolution_reason == (
        "preferred_financial_statement_source"
    )


def test_consolidator_marks_unresolved_equal_precedence_conflicts() -> None:
    result = NormalizationResult(
        tables=[],
        metric_values=[
            _metric_value("revenue", 2024, 1500, 2025, page_number=20),
            _metric_value("revenue", 2024, 1400, 2025, page_number=20),
        ],
        mappings=[
            _mapping("Revenue", "revenue", 2024, 2025, 0.96),
            _mapping("Revenue", "revenue", 2024, 2025, 0.96),
        ],
    )
    consolidator = FinancialYearConsolidator()

    consolidated = consolidator.consolidate_normalization_result(result)

    assert consolidated[0].value == 1400
    assert consolidator.last_diagnostics.conflict_groups_resolved == 0
    assert consolidator.last_diagnostics.unresolved_conflict_groups == 1
    assert consolidator.last_diagnostics.groups[0].resolution_reason == (
        "unresolved_equal_precedence_conflict"
    )


def test_consolidator_populates_company_context_metric_values() -> None:
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[_report(2024), _report(2025)],
        normalization_results={
            2024: NormalizationResult(
                tables=[],
                metric_values=[_metric_value("revenue", 2024, 1400, 2024)],
            ),
            2025: NormalizationResult(
                tables=[],
                metric_values=[
                    _metric_value("revenue", 2025, 1800, 2025),
                    _metric_value("revenue", 2024, 1500, 2025),
                ],
            ),
        },
    )

    updated_context = FinancialYearConsolidator().consolidate_context(context)

    assert updated_context is context
    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in context.metric_values
    ] == [
        ("revenue", 2024, 1500),
        ("revenue", 2025, 1800),
    ]


def test_consolidator_rejects_bucket_year_mismatch() -> None:
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[_report(2024), _report(2025)],
        normalization_results={
            2024: NormalizationResult(
                tables=[],
                metric_values=[_metric_value("revenue", 2024, 1500, 2025)],
            )
        },
    )

    with pytest.raises(
        PipelineLayerPartialFailure,
        match="bucket year must match",
    ) as exc_info:
        FinancialYearConsolidator().consolidate_context(context)

    assert context.metric_values == []
    assert "Report year 2024 failed financial year consolidation" in (
        exc_info.value.error_messages[0]
    )


def test_consolidator_rejects_future_year_values() -> None:
    values = [_metric_value("revenue", 2026, 1500, 2025)]

    with pytest.raises(ValueError, match="value_year cannot be greater"):
        FinancialYearConsolidator().consolidate(values)
