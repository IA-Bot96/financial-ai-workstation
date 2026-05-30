"""Unit tests for the OCR table metric normalization service."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.services.interfaces.table_metric_normalizer import (
    ITableMetricNormalizer,
)
from ocr_engine.services.table_metric_normalizer import TableMetricNormalizer
from shared.models.company_context import CompanyContext
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
                year=year,
                page_number=page_number,
                table_type="income_statement",
                table_index=0,
                rows=[
                    ["Net Sales", "1200000"],
                    ["Gross Profit", "450000"],
                    ["2024", "2023"],
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

    assert result.model_dump() == {
        "tables": [
            {
                "year": 2024,
                "page_number": 20,
                "table_type": "income_statement",
                "table_index": 0,
                "rows": [
                    ["revenue", "1200000"],
                    ["gross_profit", "450000"],
                    ["2024", "2023"],
                ],
            }
        ],
        "mappings": [
            {
                "year": 2024,
                "original_metric": "Net Sales",
                "normalized_metric": "revenue",
                "confidence": 0.96,
                "requires_review": False,
            },
            {
                "year": 2024,
                "original_metric": "Gross Profit",
                "normalized_metric": "gross_profit",
                "confidence": 0.96,
                "requires_review": False,
            },
        ],
    }
    assert metric_normalizer.calls == ["Net Sales", "Gross Profit"]


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
                        year=2023,
                        page_number=10,
                        table_type="balance_sheet",
                        table_index=0,
                        rows=[["Debt", "500000"]],
                    )
                ]
            ),
            2024: _extraction_result(year=2024, page_number=20),
        },
    )

    updated_context = service.normalize_for_context(context)

    assert updated_context is context
    assert set(context.normalization_results) == {2023, 2024}
    assert context.normalization_results[2023].model_dump() == {
        "tables": [
            {
                "year": 2023,
                "page_number": 10,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [["debt", "500000"]],
            }
        ],
        "mappings": [
            {
                "year": 2023,
                "original_metric": "Debt",
                "normalized_metric": "debt",
                "confidence": 0.96,
                "requires_review": False,
            }
        ],
    }
    assert context.normalization_results[2024].tables[0].year == 2024
    assert {
        mapping.year for mapping in context.normalization_results[2024].mappings
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

    with pytest.raises(ValueError, match="Missing table extraction result"):
        service.normalize_for_context(context)


def test_normalize_for_context_rejects_contaminated_year_bucket() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[_report(2024, "reports/MLCF_2024.pdf")],
        extraction_results={2024: _extraction_result(year=2023, page_number=20)},
    )

    with pytest.raises(ValueError, match="contains data from other years"):
        service.normalize_for_context(context)


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
