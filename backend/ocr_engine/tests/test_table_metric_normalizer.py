"""Unit tests for the OCR table metric normalization service."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.interfaces.table_metric_normalizer import (
    ITableMetricNormalizer,
)
from ocr_engine.services.table_metric_normalizer import TableMetricNormalizer
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue
from shared.models.report import Report
from shared.normalization.interfaces.metric_normalizer import IMetricNormalizer
from shared.normalization.models.normalized_metric import NormalizedMetric


class FakeMetricNormalizer(IMetricNormalizer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def normalize_metric(self, metric_name: str) -> NormalizedMetric:
        self.calls.append(metric_name)
        lookup = {
            "Net Sales": "revenue",
            "Gross Profit": "gross_profit",
            "Debt": "debt",
        }
        normalized_metric = lookup.get(metric_name)
        return NormalizedMetric(
            original_metric=metric_name,
            normalized_metric=normalized_metric,
            confidence=0.96 if normalized_metric is not None else 0.4,
            requires_review=normalized_metric is None,
        )


def _report(year: int, file_path: str) -> Report:
    return Report(
        id=f"rpt_{year}",
        company_name="Maple Leaf Cement Factory Limited",
        year=year,
        file_name=f"MLCF_{year}_Annual_Report.pdf",
        file_path=file_path,
    )


def _extraction_result(year: int, page_number: int) -> TableExtractionResult:
    return TableExtractionResult(
        tables=[
            ExtractedTable(
                source_report_year=year,
                page_number=page_number,
                table_type="income_statement",
                table_index=0,
                rows=[
                    ["Metric", str(year), str(year - 1)],
                    ["Net Sales", "1200000", "1100000"],
                    ["Gross Profit", "450000", "400000"],
                ],
                metric_values=[
                    MetricValue(
                        metric="Net Sales",
                        value_year=year,
                        value=1200000,
                        source_report_year=year,
                        page_number=page_number,
                        table_type="income_statement",
                    ),
                    MetricValue(
                        metric="Net Sales",
                        value_year=year - 1,
                        value=1100000,
                        source_report_year=year,
                        page_number=page_number,
                        table_type="income_statement",
                    ),
                    MetricValue(
                        metric="Gross Profit",
                        value_year=year,
                        value=450000,
                        source_report_year=year,
                        page_number=page_number,
                        table_type="income_statement",
                    ),
                ],
            )
        ]
    )


def test_table_metric_normalizer_implements_interface() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())

    assert isinstance(service, ITableMetricNormalizer)


def test_normalize_tables_preserves_year_on_tables_and_mappings() -> None:
    metric_normalizer = FakeMetricNormalizer()
    service = TableMetricNormalizer(metric_normalizer=metric_normalizer)

    result = service.normalize_tables(_extraction_result(year=2024, page_number=20))

    assert result.tables[0].source_report_year == 2024
    assert result.tables[0].rows == [
        ["Metric", "2024", "2023"],
        ["revenue", "1200000", "1100000"],
        ["gross_profit", "450000", "400000"],
    ]
    assert [
        (metric_value.metric, metric_value.value_year, metric_value.source_report_year)
        for metric_value in result.metric_values
    ] == [
        ("revenue", 2024, 2024),
        ("revenue", 2023, 2024),
        ("gross_profit", 2024, 2024),
    ]
    assert [
        (mapping.normalized_metric, mapping.value_year, mapping.source_report_year)
        for mapping in result.mappings
    ] == [
        ("revenue", 2024, 2024),
        ("revenue", 2023, 2024),
        ("gross_profit", 2024, 2024),
    ]


def test_normalize_for_context_stores_results_by_report_year() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            _report(2023, "reports/MLCF_2023.pdf"),
            _report(2024, "reports/MLCF_2024.pdf"),
        ],
        extraction_results={
            2023: TableExtractionResult(
                tables=[
                    ExtractedTable(
                        source_report_year=2023,
                        page_number=10,
                        table_type="balance_sheet",
                        table_index=0,
                        rows=[["Debt", "500000"]],
                        metric_values=[
                            MetricValue(
                                metric="Debt",
                                value_year=2023,
                                value=500000,
                                source_report_year=2023,
                                page_number=10,
                                table_type="balance_sheet",
                            )
                        ],
                    )
                ]
            ),
            2024: _extraction_result(year=2024, page_number=20),
        },
    )

    updated_context = service.normalize_for_context(context)

    assert updated_context is context
    assert set(context.normalization_results) == {2023, 2024}
    assert context.normalization_results[2023].metric_values[0].model_dump() == {
        "metric": "debt",
        "value_year": 2023,
        "value": 500000,
        "source_report_year": 2023,
        "page_number": 10,
        "table_type": "balance_sheet",
    }
    assert context.normalization_results[2024].tables[0].year == 2024
    assert {
        mapping.source_report_year
        for mapping in context.normalization_results[2024].mappings
    } == {2024}
    assert (
        context.normalization_results[2023]
        is not context.normalization_results[2024]
    )


def test_normalize_for_context_requires_extraction_result_per_year() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[_report(2024, "reports/MLCF_2024.pdf")],
    )

    with pytest.raises(
        PipelineLayerPartialFailure,
        match="Missing table extraction result",
    ) as exc_info:
        service.normalize_for_context(context)

    assert context.normalization_results[2024].model_dump() == {
        "tables": [],
        "metric_values": [],
        "mappings": [],
    }
    assert context.pipeline_errors == []
    assert "Report year 2024 failed metric normalization" in (
        exc_info.value.error_messages[0]
    )


def test_normalize_for_context_rejects_contaminated_year_bucket() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[_report(2024, "reports/MLCF_2024.pdf")],
        extraction_results={2024: _extraction_result(year=2023, page_number=20)},
    )

    with pytest.raises(
        PipelineLayerPartialFailure,
        match="contains data from other years",
    ) as exc_info:
        service.normalize_for_context(context)

    assert context.normalization_results[2024].tables == []
    assert context.pipeline_errors == []
    assert "Report year 2024 failed metric normalization" in (
        exc_info.value.error_messages[0]
    )


def test_normalize_tables_rejects_merged_multi_year_inputs() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())

    with pytest.raises(ValueError, match="single report year"):
        service.normalize_tables(
            TableExtractionResult(
                tables=[
                    _extraction_result(year=2023, page_number=10).tables[0],
                    _extraction_result(year=2024, page_number=20).tables[0],
                ]
            )
        )
