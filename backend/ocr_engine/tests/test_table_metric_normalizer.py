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
            "Depreciation": "depreciation_expense",
            "Insurance": "insurance_expense",
            "Goodwill": "goodwill",
            "Accrued liabilities": "accrued_liabilities",
            "Interest cost": "defined_benefit_interest_cost",
            "Benefit obligation": "defined_benefit_obligation",
            "Balance as at July 1": "opening_balance",
            "REMUNERATION OF CHIEF EXECUTIVE - Managerial remuneration": (
                "chief_executive_remuneration"
            ),
            "Managerial remuneration": "managerial_remuneration",
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
                source_table_index=2,
                split_table_index=1,
                split_reason=(
                    "analysis_section_markers_with_repeated_year_headers_and_"
                    "subtotal_rows"
                ),
                detected_table_id=f"{year}:{page_number}:0",
                page_table_index=0,
                bbox=[72.0, 144.0, 540.0, 320.0],
                detection_confidence=0.97,
                match_method="detected_table_id",
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
    assert result.tables[0].source_table_index == 2
    assert result.tables[0].split_table_index == 1
    assert result.tables[0].split_reason == (
        "analysis_section_markers_with_repeated_year_headers_and_subtotal_rows"
    )
    assert result.tables[0].detected_table_id == "2024:20:0"
    assert result.tables[0].page_table_index == 0
    assert result.tables[0].bbox == [72.0, 144.0, 540.0, 320.0]
    assert result.tables[0].detection_confidence == 0.97
    assert result.tables[0].match_method == "detected_table_id"
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
    assert {
        (
            mapping.original_metric,
            mapping.page_number,
            mapping.table_type,
            mapping.table_index,
            mapping.detected_table_id,
            mapping.match_method,
        )
        for mapping in result.mappings
    } == {
        ("Net Sales", 20, "income_statement", 0, "2024:20:0", "detected_table_id"),
        ("Gross Profit", 20, "income_statement", 0, "2024:20:0", "detected_table_id"),
    }
    assert [
        (mapping.normalized_metric, mapping.value_year, mapping.source_report_year)
        for mapping in result.mappings
    ] == [
        ("revenue", 2024, 2024),
        ("revenue", 2023, 2024),
        ("gross_profit", 2024, 2024),
    ]


def test_normalize_tables_strips_preserved_parent_prefix_for_strong_child_match(
) -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    extraction_result = TableExtractionResult(
        tables=[
            ExtractedTable(
                source_report_year=2025,
                page_number=222,
                table_type="cost_of_sales_note",
                table_index=0,
                rows=[],
                metric_values=[
                    MetricValue(
                        metric="COST OF SALES - Depreciation",
                        value_year=2025,
                        value=125,
                        source_report_year=2025,
                        page_number=222,
                        table_type="cost_of_sales_note",
                    )
                ],
            )
        ]
    )

    result = service.normalize_tables(extraction_result)

    assert result.metric_values[0].metric == "depreciation_expense"
    assert result.mappings[0].original_metric == "COST OF SALES - Depreciation"
    assert result.mappings[0].normalized_metric == "depreciation_expense"
    assert result.mappings[0].normalization_input_metric == "Depreciation"
    assert result.mappings[0].parent_metric_context == "COST OF SALES"
    assert result.mappings[0].child_metric == "Depreciation"
    assert result.mappings[0].parent_prefix_stripped is True
    assert result.mappings[0].normalization_rule == "parent_prefix_stripping"


@pytest.mark.parametrize(
    ("raw_metric", "expected_metric", "expected_parent", "expected_child"),
    [
        (
            "TRADE AND OTHER PAYABLES - Accrued liabilities",
            "accrued_liabilities",
            "TRADE AND OTHER PAYABLES",
            "Accrued liabilities",
        ),
        (
            "INTANGIBLE ASSETS - Goodwill",
            "goodwill",
            "INTANGIBLE ASSETS",
            "Goodwill",
        ),
        (
            "COST OF SALES–Depreciation",
            "depreciation_expense",
            "COST OF SALES",
            "Depreciation",
        ),
        (
            "COST OF SALES - Insurance",
            "insurance_expense",
            "COST OF SALES",
            "Insurance",
        ),
        (
            "DEFINED BENEFIT OBLIGATION: - - Interest cost",
            "defined_benefit_interest_cost",
            "DEFINED BENEFIT OBLIGATION",
            "Interest cost",
        ),
        (
            "EXECUTIVES GRATUITY FUND - Benefit obligation",
            "defined_benefit_obligation",
            "EXECUTIVES GRATUITY FUND",
            "Benefit obligation",
        ),
    ],
)
def test_normalize_tables_generalizes_hyphenated_parent_child_labels(
    raw_metric: str,
    expected_metric: str,
    expected_parent: str,
    expected_child: str,
) -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    extraction_result = TableExtractionResult(
        tables=[
            ExtractedTable(
                source_report_year=2025,
                page_number=240,
                table_type="notes",
                table_index=0,
                rows=[],
                metric_values=[
                    MetricValue(
                        metric=raw_metric,
                        value_year=2025,
                        value=100,
                        source_report_year=2025,
                        page_number=240,
                        table_type="notes",
                    )
                ],
            )
        ]
    )

    result = service.normalize_tables(extraction_result)

    assert result.metric_values[0].metric == expected_metric
    assert result.mappings[0].original_metric == raw_metric
    assert result.mappings[0].normalized_metric == expected_metric
    assert result.mappings[0].normalization_input_metric == expected_child
    assert result.mappings[0].parent_metric_context == expected_parent
    assert result.mappings[0].child_metric == expected_child
    assert result.mappings[0].parent_prefix_stripped is True
    assert result.mappings[0].normalization_rule == "parent_prefix_stripping"


def test_normalize_tables_does_not_strip_generic_note_child_labels() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    extraction_result = TableExtractionResult(
        tables=[
            ExtractedTable(
                source_report_year=2025,
                page_number=241,
                table_type="notes",
                table_index=0,
                rows=[],
                metric_values=[
                    MetricValue(
                        metric="INTANGIBLE ASSETS - Balance as at July 1",
                        value_year=2025,
                        value=100,
                        source_report_year=2025,
                        page_number=241,
                        table_type="notes",
                    )
                ],
            )
        ]
    )

    result = service.normalize_tables(extraction_result)

    assert result.metric_values[0].metric == (
        "INTANGIBLE ASSETS - Balance as at July 1"
    )
    assert result.mappings[0].normalized_metric is None
    assert result.mappings[0].requires_review is True
    assert result.mappings[0].parent_prefix_stripped is False
    assert result.mappings[0].parent_metric_context is None
    assert result.mappings[0].child_metric is None


def test_normalize_tables_keeps_parent_prefix_when_child_is_not_strong() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    extraction_result = TableExtractionResult(
        tables=[
            ExtractedTable(
                source_report_year=2025,
                page_number=222,
                table_type="cost_of_sales_note",
                table_index=0,
                rows=[],
                metric_values=[
                    MetricValue(
                        metric="COST OF SALES - Unclear disclosure",
                        value_year=2025,
                        value=125,
                        source_report_year=2025,
                        page_number=222,
                        table_type="cost_of_sales_note",
                    )
                ],
            )
        ]
    )

    result = service.normalize_tables(extraction_result)

    assert result.metric_values[0].metric == "COST OF SALES - Unclear disclosure"
    assert result.mappings[0].normalized_metric is None
    assert result.mappings[0].requires_review is True
    assert result.mappings[0].normalization_input_metric == (
        "COST OF SALES - Unclear disclosure"
    )
    assert result.mappings[0].parent_prefix_stripped is False


def test_normalize_tables_keeps_stronger_specific_parent_context_mapping() -> None:
    service = TableMetricNormalizer(metric_normalizer=FakeMetricNormalizer())
    extraction_result = TableExtractionResult(
        tables=[
            ExtractedTable(
                source_report_year=2025,
                page_number=300,
                table_type="remuneration_note",
                table_index=0,
                rows=[],
                metric_values=[
                    MetricValue(
                        metric=(
                            "REMUNERATION OF CHIEF EXECUTIVE - "
                            "Managerial remuneration"
                        ),
                        value_year=2025,
                        value=10,
                        source_report_year=2025,
                        page_number=300,
                        table_type="remuneration_note",
                    )
                ],
            )
        ]
    )

    result = service.normalize_tables(extraction_result)

    assert result.metric_values[0].metric == "chief_executive_remuneration"
    assert result.mappings[0].normalized_metric == "chief_executive_remuneration"
    assert result.mappings[0].normalization_input_metric == (
        "REMUNERATION OF CHIEF EXECUTIVE - Managerial remuneration"
    )
    assert result.mappings[0].parent_prefix_stripped is False


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
