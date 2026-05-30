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
from ocr_engine.services.camelot_table_extractor import CamelotTableExtractor
from ocr_engine.services.interfaces.table_extractor import ITableExtractor


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

    assert result.model_dump() == {
        "tables": [
            {
                "page_number": 20,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [["Cash", "1000"], ["Inventory", ""]],
            },
            {
                "page_number": 20,
                "table_type": "debt_schedule",
                "table_index": 1,
                "rows": [["Debt", "450"]],
            },
        ]
    }


def test_extract_tables_falls_back_to_pdfplumber_when_camelot_returns_no_tables() -> None:
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
                PageTableType(page_number=1, table_types=["balance_sheet"])
            ]
        ),
    )

    assert result.model_dump() == {
        "tables": [
            {
                "page_number": 1,
                "table_type": "balance_sheet",
                "table_index": 0,
                "rows": [["Cash", "1000"], ["Inventory", ""]],
            }
        ]
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
                PageTableType(page_number=20, table_types=["balance_sheet"]),
                PageTableType(page_number=25, table_types=["income_statement"]),
            ]
        ),
    )

    assert result.model_dump() == {
        "tables": [
            {
                "page_number": 25,
                "table_type": "income_statement",
                "table_index": 0,
                "rows": [["Revenue", "1000"]],
            }
        ]
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
                    PageTableType(page_number=20, table_types=["balance_sheet"])
                ]
            ),
        )

    assert "Processing page 20" in caplog.text
    assert "Camelot succeeded" in caplog.text
    assert "Extraction completed" in caplog.text
