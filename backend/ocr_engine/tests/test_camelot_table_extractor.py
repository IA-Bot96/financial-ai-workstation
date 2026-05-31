"""Unit tests for the Camelot table extractor service."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_detection_result import (
    DetectedPage,
    TableDetectionResult,
)
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.camelot_table_extractor import CamelotTableExtractor
from ocr_engine.services.interfaces.table_extractor import ITableExtractor
from shared.models.company_context import CompanyContext
from shared.models.report import Report


class FakeValues:
    def __init__(self, rows: list[list[object]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[object]]:
        return self._rows


class FakeDataFrame:
    def __init__(self, rows: list[list[object]]) -> None:
        self.values = FakeValues(rows)


class FakeCamelotTable:
    def __init__(self, rows: list[list[object]]) -> None:
        self.df = FakeDataFrame(rows)


class FakePdfplumberPage:
    def __init__(self, tables: list[list[list[object]]]) -> None:
        self._tables = tables

    def extract_tables(self) -> list[list[list[object]]]:
        return self._tables


class FakePdfplumberDocument:
    def __init__(self, pages: list[FakePdfplumberPage]) -> None:
        self.pages = pages

    def __enter__(self) -> "FakePdfplumberDocument":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def _classification_result() -> FinancialTableClassificationResult:
    return FinancialTableClassificationResult(
        page_table_types=[
            PageTableType(
                year=2024,
                page_number=20,
                table_types=["balance_sheet", "debt_schedule"],
            )
        ]
    )


def test_camelot_table_extractor_implements_interface() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    assert isinstance(extractor, ITableExtractor)


def test_extract_tables_uses_camelot_first() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([[" Cash ", 1000], ["Inventory", None]]),
            FakeCamelotTable([["Debt", " 450 "]]),
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=_classification_result(),
    )

    assert result.model_dump(exclude={"extraction_summary"}) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [["Cash", "1000"], ["Inventory", ""]],
                "metric_values": [],
            },
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "debt_schedule",
                "table_index": 1,
                "rows": [["Debt", "450"]],
                "metric_values": [],
            },
        ],
        "metric_values": [],
    }


def test_extract_tables_identifies_metric_value_years() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025", "2024"],
                    ["Revenue", "100", "80"],
                    ["Debt", "45", "50"],
                ]
            )
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=120,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    assert [
        (
            metric_value.metric,
            metric_value.value_year,
            metric_value.value,
            metric_value.source_report_year,
        )
        for metric_value in result.metric_values
    ] == [
        ("Revenue", 2025, 100, 2025),
        ("Revenue", 2024, 80, 2025),
        ("Debt", 2025, 45, 2025),
        ("Debt", 2024, 50, 2025),
    ]


def test_extract_tables_applies_financial_scale_conversion() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Rupees in thousand"],
                    ["Metric", "2025"],
                    ["Revenue", "1.5"],
                ]
            ),
            FakeCamelotTable(
                [
                    ["Amounts in million"],
                    ["Metric", "2025"],
                    ["EBITDA", "2"],
                ]
            ),
            FakeCamelotTable(
                [
                    ["USD in billion"],
                    ["Metric", "2025"],
                    ["Debt", "3"],
                ]
            ),
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=120,
                    table_types=[
                        "income_statement",
                        "income_statement",
                        "debt_schedule",
                    ],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Revenue", 1500),
        ("EBITDA", 2_000_000),
        ("Debt", 3_000_000_000),
    ]


def test_extract_tables_parses_accounting_negatives_only_when_numeric() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2024"],
                    ["Profit", "(1,250)"],
                    ["Expense", "-25"],
                    ["Restated value", "(Restated) 100"],
                    ["Disclosure", "Note 12"],
                ]
            )
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2024,
                    page_number=20,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Profit", -1250),
        ("Expense", -25),
    ]


def test_extract_tables_logs_type_count_mismatch_and_preserves_extra_tables(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Cash", "1000"]]),
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "500"]]),
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet"],
                    )
                ]
            ),
        )

    assert len(result.tables) == 2
    assert result.tables[0].table_type == "balance_sheet"
    assert result.tables[0].rows == [["Metric", "2024"], ["Cash", "1000"]]
    assert result.tables[1].table_type == "unclassified_table"
    assert result.tables[1].rows == [["Metric", "2024"], ["Revenue", "500"]]
    assert result.metric_values[0].metric == "Cash"
    assert result.metric_values[1].metric == "Revenue"
    assert "Table count and classification type count mismatch" in caplog.text
    assert "could not be matched to a classified table type" in caplog.text


def test_extract_tables_corrects_classification_ordering_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "1000"]]),
            FakeCamelotTable([["Metric", "2024"], ["Cash", "600"]]),
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet", "income_statement"],
                    )
                ]
            ),
        )

    assert [
        (table.table_index, table.table_type, table.rows[1][0])
        for table in result.tables
    ] == [
        (0, "income_statement", "Revenue"),
        (1, "balance_sheet", "Cash"),
    ]
    assert "Table classification ordering mismatch corrected" in caplog.text


def test_extract_tables_logs_extra_classified_tables(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Cash", "1000"]]),
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet", "income_statement"],
                    )
                ]
            ),
        )

    assert len(result.tables) == 1
    assert result.tables[0].table_type == "balance_sheet"
    assert "Table count and classification type count mismatch" in caplog.text
    assert "Classified table type did not match an extracted table" in caplog.text


def test_extract_tables_reports_page_diagnostics_from_detection_to_extraction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "1000"]]),
            FakeCamelotTable([["Metric", "2024"], ["Unmapped Disclosure", "9"]]),
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )

    with caplog.at_level(logging.INFO):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement"],
                    )
                ]
            ),
            table_detection_result=TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=2),
                ],
                total_pages_processed=100,
            ),
        )

    summary = result.extraction_summary
    assert summary.total_detected_tables == 2
    assert summary.total_classified_tables == 1
    assert summary.total_extracted_tables == 2
    assert summary.total_matched_tables == 1
    assert summary.unmatched_extractions == ["page=20 table_index=1"]
    assert summary.unmatched_classifications == []
    assert summary.page_diagnostics[0].model_dump() == {
        "source_report_year": 2024,
        "page_number": 20,
        "detected_table_count": 2,
        "classified_table_count": 1,
        "extracted_table_count": 2,
        "matched_table_count": 1,
        "unmatched_classifications": [],
        "unmatched_extractions": [1],
    }
    assert "Extraction page diagnostics" in caplog.text


def test_extract_tables_for_context_fails_when_no_tables_match() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Unmapped Disclosure", "9"]]),
        ],
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
        classification_results={
            2024: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement", "balance_sheet"],
                    )
                ]
            )
        },
        table_detection_results={
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=2),
                ],
                total_pages_processed=100,
            )
        },
    )

    with pytest.raises(PipelineLayerPartialFailure, match="no matched tables"):
        extractor.extract_tables_for_context(context)

    summary = context.extraction_results[2024].extraction_summary
    assert summary.total_detected_tables == 2
    assert summary.total_classified_tables == 2
    assert summary.total_extracted_tables == 1
    assert summary.total_matched_tables == 0


def test_extract_tables_for_context_stores_results_by_report_year() -> None:
    def camelot_reader(pdf_path: str, pages: str) -> list[FakeCamelotTable]:
        raw_tables_by_page = {
            ("reports/MLCF_2023.pdf", "10"): [
                FakeCamelotTable([["Cash", "800"]]),
            ],
            ("reports/MLCF_2024.pdf", "20"): [
                FakeCamelotTable([["Cash", "1000"]]),
                FakeCamelotTable([["Debt", "450"]]),
            ],
        }
        return raw_tables_by_page[(pdf_path, pages)]

    extractor = CamelotTableExtractor(
        camelot_reader=camelot_reader,
        pdfplumber_open=lambda _: pytest.fail("pdfplumber should not be used"),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2023_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2023,
                file_name="MLCF_2023_Annual_Report.pdf",
                file_path="reports/MLCF_2023.pdf",
            ),
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            ),
        ],
        classification_results={
            2023: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2023,
                        page_number=10,
                        table_types=["balance_sheet"],
                    ),
                ]
            ),
            2024: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet", "debt_schedule"],
                    ),
                ]
            ),
        },
        table_detection_results={
            2023: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2023, page_number=10, tables_detected=1),
                ],
                total_pages_processed=100,
            ),
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=2),
                ],
                total_pages_processed=132,
            ),
        },
    )

    updated_context = extractor.extract_tables_for_context(context)

    assert updated_context is context
    assert set(context.extraction_results) == {2023, 2024}
    assert context.extraction_results[2023].model_dump(
        exclude={"extraction_summary"}
    ) == {
        "tables": [
            {
                "source_report_year": 2023,
                "page_number": 10,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [["Cash", "800"]],
                "metric_values": [],
            }
        ],
        "metric_values": [],
    }
    assert context.extraction_results[2024].model_dump(
        exclude={"extraction_summary"}
    ) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [["Cash", "1000"]],
                "metric_values": [],
            },
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "debt_schedule",
                "table_index": 1,
                "rows": [["Debt", "450"]],
                "metric_values": [],
            },
        ],
        "metric_values": [],
    }
    assert context.extraction_results[2023] is not context.extraction_results[2024]


def test_extract_tables_for_context_isolates_year_failures() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "1000"]])
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2023_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2023,
                file_name="MLCF_2023_Annual_Report.pdf",
                file_path="reports/MLCF_2023.pdf",
            ),
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
        classification_results={
            2024: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement"],
                    )
                ]
            )
        },
        table_detection_results={
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=1),
                ],
                total_pages_processed=132,
            )
        },
    )

    with pytest.raises(PipelineLayerPartialFailure) as exc_info:
        extractor.extract_tables_for_context(context)

    assert exc_info.value.context is context
    assert set(context.extraction_results) == {2023, 2024}
    assert context.extraction_results[2023].model_dump(
        exclude={"extraction_summary"}
    ) == {
        "tables": [],
        "metric_values": [],
    }
    assert context.extraction_results[2024].metric_values[0].metric == "Revenue"
    assert "Report year 2023 failed table extraction" in (
        exc_info.value.error_messages[0]
    )
    assert context.pipeline_errors == []


def test_extract_tables_falls_back_to_pdfplumber_when_camelot_returns_no_tables(
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [],
        pdfplumber_open=lambda _: FakePdfplumberDocument(
            [
                FakePdfplumberPage(
                    [
                        [[" Cash ", "1000"], ["Inventory", None]],
                    ]
                )
            ]
        ),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2024,
                    page_number=1,
                    table_types=["balance_sheet"],
                )
            ]
        ),
    )

    assert result.model_dump(exclude={"extraction_summary"}) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 1,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [["Cash", "1000"], ["Inventory", ""]],
                "metric_values": [],
            }
        ],
        "metric_values": [],
    }


def test_extract_tables_returns_empty_when_both_extractors_fail() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("camelot failure")
        ),
        pdfplumber_open=lambda _: (_ for _ in ()).throw(
            RuntimeError("pdfplumber failure")
        ),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=_classification_result(),
    )

    assert result.tables == []


def test_extract_tables_continues_processing_remaining_pages() -> None:
    def camelot_reader(pdf_path: str, pages: str) -> list[FakeCamelotTable]:
        if pages == "20":
            raise RuntimeError("page failed")
        return [FakeCamelotTable([["Revenue", "1000"]])]

    extractor = CamelotTableExtractor(
        camelot_reader=camelot_reader,
        pdfplumber_open=lambda _: FakePdfplumberDocument(
            [FakePdfplumberPage([]) for _ in range(30)]
        ),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2024,
                    page_number=20,
                    table_types=["balance_sheet"],
                ),
                PageTableType(
                    year=2024,
                    page_number=25,
                    table_types=["income_statement"],
                ),
            ]
        ),
    )

    assert result.model_dump(exclude={"extraction_summary"}) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 25,
                "table_type": "income_statement",
                "table_index": 0,
                "rows": [["Revenue", "1000"]],
                "metric_values": [],
            }
        ],
        "metric_values": [],
    }


def test_extract_tables_logs_processing_and_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Cash", "1000"]])
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    with caplog.at_level(logging.INFO):
        extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet"],
                    )
                ]
            ),
        )

    assert "Processing page 20" in caplog.text
    assert "Camelot succeeded" in caplog.text
    assert "Extraction completed" in caplog.text
