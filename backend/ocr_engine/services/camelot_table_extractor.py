"""Camelot-first table extraction service with pdfplumber fallback."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Sequence

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.pipeline.models.pipeline_error import PipelineError
from ocr_engine.services.interfaces.table_extractor import ITableExtractor
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue

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

    def extract_tables_for_context(self, context: CompanyContext) -> CompanyContext:
        """Extract tables for each report and store results by report year.

        The method reads ``context.classification_results[report.year]`` and
        writes extracted tables to ``context.extraction_results[report.year]``.
        Each annual report is processed independently.
        """

        self._logger.info(
            "Starting table extraction for company context",
            extra={
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )

        for report in context.reports:
            try:
                classification_result = context.classification_results.get(report.year)
                if classification_result is None:
                    raise ValueError(
                        "Missing financial table classification result for "
                        f"report year {report.year}."
                    )

                self._logger.info(
                    "Extracting tables for report year %s",
                    report.year,
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                        "file_path": report.file_path,
                    },
                )
                context.extraction_results[report.year] = self.extract_tables(
                    pdf_path=report.file_path,
                    classification_result=classification_result,
                )
            except Exception as exc:
                context.extraction_results[report.year] = TableExtractionResult(
                    tables=[],
                    metric_values=[],
                )
                context.pipeline_errors.append(
                    PipelineError(
                        layer_name="Table Extraction",
                        error_message=(
                            f"Report year {report.year} failed table extraction: "
                            f"{_error_message(exc)}"
                        ),
                    )
                )
                self._logger.exception(
                    "Table extraction failed for report; continuing",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                        "file_path": report.file_path,
                    },
                )
                continue

        self._logger.info(
            "Company context table extraction complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.extraction_results),
            },
        )
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run table extraction as a pipeline layer."""

        return self.extract_tables_for_context(context)

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

        result = TableExtractionResult(
            tables=extracted_tables,
            metric_values=[
                metric_value
                for table in extracted_tables
                for metric_value in table.metric_values
            ],
        )
        self._logger.info(
            "Extraction completed",
            extra={
                "tables_extracted": len(result.tables),
                "metric_values_extracted": len(result.metric_values),
            },
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

        if len(raw_tables) != len(page_table_type.table_types):
            self._logger.warning(
                "Table count and classification type count mismatch",
                extra={
                    "page": page_table_type.page_number,
                    "tables_extracted": len(raw_tables),
                    "table_types": len(page_table_type.table_types),
                },
            )

        extracted_tables: list[ExtractedTable] = []
        for index, rows in enumerate(raw_tables[: len(page_table_type.table_types)]):
            table_type = page_table_type.table_types[index]
            extracted_tables.append(
                ExtractedTable(
                    source_report_year=page_table_type.year,
                    page_number=page_table_type.page_number,
                    table_type=table_type,
                    table_index=index,
                    rows=rows,
                    metric_values=self._extract_metric_values(
                        rows=rows,
                        source_report_year=page_table_type.year,
                        page_number=page_table_type.page_number,
                        table_type=table_type,
                    ),
                )
            )
        return extracted_tables

    def _extract_metric_values(
        self,
        *,
        rows: RawTable,
        source_report_year: int,
        page_number: int,
        table_type: str,
    ) -> list[MetricValue]:
        """Extract metric/value-year pairs from normalized raw table rows."""

        header_row_index, year_columns = self._find_year_columns(rows)
        if not year_columns:
            return []

        scale_multiplier = self._scale_multiplier(rows)
        metric_values: list[MetricValue] = []
        for row_index, row in enumerate(rows):
            if row_index == header_row_index:
                continue

            label_index = self._metric_label_index(row)
            if label_index is None:
                continue

            metric = row[label_index].strip()
            for column_index, value_year in year_columns.items():
                if column_index >= len(row) or column_index == label_index:
                    continue

                value = self._parse_metric_value(
                    row[column_index],
                    default_scale_multiplier=scale_multiplier,
                )
                if value is None:
                    continue

                metric_values.append(
                    MetricValue(
                        metric=metric,
                        value_year=value_year,
                        value=value,
                        source_report_year=source_report_year,
                        page_number=page_number,
                        table_type=table_type,
                    )
                )

        return metric_values

    @staticmethod
    def _find_year_columns(rows: RawTable) -> tuple[int | None, dict[int, int]]:
        """Return the header row index and columns that contain value years."""

        best_row_index: int | None = None
        best_match: dict[int, int] = {}
        for row_index, row in enumerate(rows):
            year_columns: dict[int, int] = {}
            for column_index, cell in enumerate(row):
                match = re.fullmatch(r"(?:19|20)\d{2}", str(cell).strip())
                if match is not None:
                    year_columns[column_index] = int(match.group(0))

            if len(year_columns) > len(best_match):
                best_row_index = row_index
                best_match = year_columns

        return best_row_index, best_match

    @staticmethod
    def _metric_label_index(row: Sequence[str]) -> int | None:
        """Return the first cell that looks like a metric label."""

        for index, cell in enumerate(row):
            text = str(cell).strip()
            if text and not re.fullmatch(r"(?:19|20)\d{2}", text) and re.search(
                r"[A-Za-z]",
                text,
            ):
                return index
        return None

    @classmethod
    def _parse_metric_value(
        cls,
        value: str,
        *,
        default_scale_multiplier: int = 1,
    ) -> float | int | None:
        """Parse a table cell into a typed financial value when possible."""

        text = str(value).strip()
        if not text or text.lower() in {"-", "na", "n/a", "nil", "none"}:
            return None

        cell_scale_multiplier = cls._cell_scale_multiplier(text)
        multiplier = cell_scale_multiplier or default_scale_multiplier
        cleaned = text.replace("\u2212", "-").replace(",", "")
        cleaned = cls._remove_allowed_financial_tokens(cleaned)
        if re.search(r"[A-Za-z]", cleaned):
            return None

        match = re.search(
            r"(?P<accounting>\(\s*[+-]?\d+(?:\.\d+)?\s*\))|"
            r"(?P<signed>[-+]?\d+(?:\.\d+)?)",
            cleaned,
        )
        if match is None:
            return None

        token = match.group(0)
        negative = bool(match.group("accounting")) or token.strip().startswith("-")
        parsed = float(token.replace("(", "").replace(")", ""))
        parsed = abs(parsed) * multiplier
        if negative:
            parsed = -abs(parsed)
        if parsed.is_integer():
            return int(parsed)
        return parsed

    @classmethod
    def _scale_multiplier(cls, rows: RawTable) -> int:
        """Detect a financial scale multiplier from table-level text."""

        for row in rows:
            for cell in row:
                multiplier = cls._table_scale_multiplier(str(cell))
                if multiplier is not None:
                    return multiplier
        return 1

    @staticmethod
    def _table_scale_multiplier(text: str) -> int | None:
        normalized = text.lower().replace(",", "")
        if not re.search(r"\b(in|amounts?|rs|pkr|usd|rupees?)\b", normalized):
            return None
        return _scale_multiplier_from_text(normalized)

    @staticmethod
    def _cell_scale_multiplier(text: str) -> int | None:
        return _scale_multiplier_from_text(text.lower().replace(",", ""))

    @staticmethod
    def _remove_allowed_financial_tokens(text: str) -> str:
        cleaned = re.sub(
            r"(?i)\b(rs|pkr|usd|eur|gbp|rupees|rupee|amounts?|in)\b\.?",
            " ",
            text,
        )
        cleaned = re.sub(
            r"(?i)\b(thousands?|million|millions|mn|billion|billions|bn)\b\.?",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"(?i)(?<!\d)'000s?\b|(?<!\d)\b000s?\b", " ", cleaned)
        cleaned = cleaned.replace("%", " ")
        return cleaned

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


def _scale_multiplier_from_text(text: str) -> int | None:
    """Return a financial scale multiplier mentioned in text."""

    if re.search(r"\b(billion|billions|bn)\b", text):
        return 1_000_000_000
    if re.search(r"\b(million|millions|mn)\b", text):
        return 1_000_000
    if re.search(
        r"\b(thousand|thousands)\b|(?<!\d)'000s?\b|(?<!\d)\b000s?\b",
        text,
    ):
        return 1_000
    return None


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for result metadata."""

    return str(exc) or exc.__class__.__name__
