"""Camelot-first table extraction service with pdfplumber fallback."""

from __future__ import annotations

import logging
from typing import Any, Callable

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.services.interfaces.table_extractor import ITableExtractor

logger = logging.getLogger(__name__)

RawTable = list[list[str]]


class CamelotTableExtractor(ITableExtractor):
    """Extract raw table rows from classified PDF pages.

    Camelot is attempted first for each page. If it fails or returns no tables,
    pdfplumber is used as a fallback. The service preserves table rows and cells
    as strings and performs no financial normalization or downstream mapping.
    """

    def __init__(
        self,
        *,
        camelot_reader: Callable[..., Any] | None = None,
        pdfplumber_open: Callable[[str], Any] | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the extractor with optional injected dependencies."""

        self._camelot_reader = camelot_reader or self._load_camelot_reader()
        self._pdfplumber_open = pdfplumber_open or self._load_pdfplumber_open()
        self._logger = log or logger

    def extract_tables(
        self,
        pdf_path: str,
        classification_result: FinancialTableClassificationResult,
    ) -> TableExtractionResult:
        """Extract raw tables for all classified pages."""

        extracted_tables: list[ExtractedTable] = []

        for page_table_type in classification_result.page_table_types:
            page_number = page_table_type.page_number
            self._logger.info(
                "Processing page %s",
                page_number,
                extra={"page": page_number},
            )

            raw_tables = self._extract_page_tables(pdf_path, page_number)
            extracted_tables.extend(
                self._build_extracted_tables(page_table_type, raw_tables)
            )

        result = TableExtractionResult(tables=extracted_tables)
        self._logger.info(
            "Extraction completed",
            extra={"tables_extracted": len(result.tables)},
        )
        return result

    def _extract_page_tables(self, pdf_path: str, page_number: int) -> list[RawTable]:
        """Extract tables from a page using Camelot with pdfplumber fallback."""

        raw_tables = self._extract_with_camelot(pdf_path, page_number)
        if raw_tables:
            self._logger.info(
                "Camelot succeeded",
                extra={"page": page_number, "tables_extracted": len(raw_tables)},
            )
            return raw_tables

        self._logger.info(
            "Camelot failed",
            extra={"page": page_number, "reason": "no_tables"},
        )
        self._logger.info(
            "Using pdfplumber fallback",
            extra={"page": page_number},
        )
        return self._extract_with_pdfplumber(pdf_path, page_number)

    def _extract_with_camelot(self, pdf_path: str, page_number: int) -> list[RawTable]:
        """Extract tables from a PDF page using Camelot."""

        try:
            tables = self._camelot_reader(pdf_path, pages=str(page_number))
            raw_tables = [
                self._normalize_rows(table.df.values.tolist())
                for table in tables
                if hasattr(table, "df")
            ]
            return [table for table in raw_tables if table]
        except Exception:
            self._logger.exception(
                "Camelot failed",
                extra={"page": page_number},
            )
            return []

    def _extract_with_pdfplumber(
        self,
        pdf_path: str,
        page_number: int,
    ) -> list[RawTable]:
        """Extract tables from a PDF page using pdfplumber."""

        try:
            with self._pdfplumber_open(pdf_path) as pdf:
                page = pdf.pages[page_number - 1]
                tables = page.extract_tables() or []
                raw_tables = [self._normalize_rows(table) for table in tables]
                return [table for table in raw_tables if table]
        except Exception:
            self._logger.exception(
                "pdfplumber failed",
                extra={"page": page_number},
            )
            return []

    def _build_extracted_tables(
        self,
        page_table_type: PageTableType,
        raw_tables: list[RawTable],
    ) -> list[ExtractedTable]:
        """Build output models from raw extracted tables and page classifications."""

        if not raw_tables or not page_table_type.table_types:
            return []

        extracted_tables: list[ExtractedTable] = []
        for index, rows in enumerate(raw_tables):
            table_type_index = min(index, len(page_table_type.table_types) - 1)
            extracted_tables.append(
                ExtractedTable(
                    page_number=page_table_type.page_number,
                    table_type=page_table_type.table_types[table_type_index],
                    rows=rows,
                )
            )
        return extracted_tables

    @classmethod
    def _normalize_rows(cls, rows: Any) -> RawTable:
        """Convert table cells to trimmed strings while preserving row structure."""

        normalized_rows: RawTable = []
        for row in rows or []:
            normalized_rows.append([cls._normalize_cell(cell) for cell in row])
        return normalized_rows

    @staticmethod
    def _normalize_cell(value: Any) -> str:
        """Normalize a single extracted table cell to a string."""

        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _load_camelot_reader() -> Callable[..., Any]:
        """Load Camelot's table reader lazily."""

        try:
            import camelot
        except ImportError as exc:
            raise RuntimeError("Camelot is required for table extraction.") from exc

        return camelot.read_pdf

    @staticmethod
    def _load_pdfplumber_open() -> Callable[[str], Any]:
        """Load pdfplumber lazily."""

        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("pdfplumber is required for table extraction.") from exc

        return pdfplumber.open
