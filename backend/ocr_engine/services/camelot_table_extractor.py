"""Camelot-first table extraction service with pdfplumber fallback."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_detection_result import TableDetectionResult
from ocr_engine.models.table_extraction import (
    ExtractedTable,
    ExtractionSummary,
    PageExtractionDiagnostic,
    TableExtractionResult,
)
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.interfaces.table_extractor import ITableExtractor
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue

logger = logging.getLogger(__name__)

RawTable = list[list[str]]
UNCLASSIFIED_TABLE_TYPE = "unclassified_table"


@dataclass(frozen=True)
class _TableTypeCandidate:
    """A deterministic raw-table to classified-table candidate match."""

    score: int
    raw_table_index: int
    classified_type_index: int


@dataclass(frozen=True)
class _TableMappingResult:
    """Raw table to classified type mapping plus unmatched details."""

    table_type_by_raw_index: dict[int, str]
    assigned_classified_type_indexes: set[int]


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

        failures: list[str] = []
        for report in context.reports:
            try:
                classification_result = context.classification_results.get(report.year)
                if classification_result is None:
                    raise ValueError(
                        "Missing financial table classification result for "
                        f"report year {report.year}."
                    )
                table_detection_result = context.table_detection_results.get(
                    report.year
                )
                if table_detection_result is None:
                    raise ValueError(
                        "Missing table detection result for report year "
                        f"{report.year}."
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
                    table_detection_result=table_detection_result,
                )
                extraction_summary = (
                    context.extraction_results[report.year].extraction_summary
                )
                self._logger.info(
                    "Extraction result stored for downstream layers",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                        "tables": len(context.extraction_results[report.year].tables),
                        "metric_values": len(
                            context.extraction_results[report.year].metric_values
                        ),
                        "total_matched_tables": (
                            extraction_summary.total_matched_tables
                        ),
                    },
                )
                if extraction_summary.total_matched_tables == 0:
                    failures.append(
                        f"Report year {report.year} failed table extraction: "
                        "no matched tables. "
                        f"detected={extraction_summary.total_detected_tables}, "
                        f"classified={extraction_summary.total_classified_tables}, "
                        f"extracted={extraction_summary.total_extracted_tables}."
                    )
                    self._logger.error(
                        "Table extraction produced zero matched tables",
                        extra={
                            "company_name": context.company_name,
                            "year": report.year,
                            "file_path": report.file_path,
                            **extraction_summary.model_dump(
                                exclude={"page_diagnostics"}
                            ),
                        },
                    )
            except Exception as exc:
                failures.append(
                    f"Report year {report.year} failed table extraction: "
                    f"{_error_message(exc)}"
                )
                context.extraction_results[report.year] = TableExtractionResult(
                    tables=[],
                    metric_values=[],
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
        if failures:
            raise PipelineLayerPartialFailure(failures, context=context)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run table extraction as a pipeline layer."""

        return self.extract_tables_for_context(context)

    def extract_tables(
        self,
        pdf_path: str,
        classification_result: FinancialTableClassificationResult,
        table_detection_result: TableDetectionResult | None = None,
    ) -> TableExtractionResult:
        """Extract raw tables for all classified pages."""

        extracted_tables: list[ExtractedTable] = []
        page_diagnostics: list[PageExtractionDiagnostic] = []
        detected_counts_by_page = _detected_counts_by_page(table_detection_result)

        for page_table_type in classification_result.page_table_types:
            page_number = page_table_type.page_number
            self._logger.info(
                "Processing page %s",
                page_number,
                extra={"page": page_number},
            )

            raw_tables = self._extract_page_tables(pdf_path, page_number)
            page_tables, page_diagnostic = self._build_extracted_tables(
                page_table_type=page_table_type,
                raw_tables=raw_tables,
                detected_table_count=detected_counts_by_page.get(page_number, 0),
            )
            extracted_tables.extend(page_tables)
            page_diagnostics.append(page_diagnostic)
            self._log_page_diagnostic(page_diagnostic)

        extraction_summary = _build_extraction_summary(page_diagnostics)
        result = TableExtractionResult(
            tables=extracted_tables,
            metric_values=[
                metric_value
                for table in extracted_tables
                for metric_value in table.metric_values
            ],
            extraction_summary=extraction_summary,
        )
        self._logger.info(
            "Extraction completed",
            extra={
                "tables_extracted": len(result.tables),
                "metric_values_extracted": len(result.metric_values),
                **result.extraction_summary.model_dump(
                    exclude={"page_diagnostics"}
                ),
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
        *,
        page_table_type: PageTableType,
        raw_tables: list[RawTable],
        detected_table_count: int,
    ) -> tuple[list[ExtractedTable], PageExtractionDiagnostic]:
        """Build output models from raw extracted tables and page classifications."""

        if not raw_tables:
            if page_table_type.table_types:
                self._logger.warning(
                    "Classified table types had no extracted tables",
                    extra={
                        "page": page_table_type.page_number,
                        "table_types": page_table_type.table_types,
                    },
                )
            return [], PageExtractionDiagnostic(
                source_report_year=page_table_type.year,
                page_number=page_table_type.page_number,
                detected_table_count=detected_table_count,
                classified_table_count=len(page_table_type.table_types),
                extracted_table_count=0,
                matched_table_count=0,
                unmatched_classifications=page_table_type.table_types,
                unmatched_extractions=[],
            )

        if len(raw_tables) != len(page_table_type.table_types):
            self._logger.warning(
                "Table count and classification type count mismatch",
                extra={
                    "page": page_table_type.page_number,
                    "tables_extracted": len(raw_tables),
                    "table_types": len(page_table_type.table_types),
                },
            )

        table_type_by_raw_index = self._map_table_types_to_raw_tables(
            page_table_type=page_table_type,
            raw_tables=raw_tables,
        )
        unmatched_classifications = [
            table_type
            for index, table_type in enumerate(page_table_type.table_types)
            if index not in table_type_by_raw_index.assigned_classified_type_indexes
        ]
        unmatched_extractions = [
            index
            for index in range(len(raw_tables))
            if index not in table_type_by_raw_index.table_type_by_raw_index
        ]
        extracted_tables: list[ExtractedTable] = []
        for index, rows in enumerate(raw_tables):
            table_type = table_type_by_raw_index.table_type_by_raw_index.get(
                index,
                UNCLASSIFIED_TABLE_TYPE,
            )
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
        return extracted_tables, PageExtractionDiagnostic(
            source_report_year=page_table_type.year,
            page_number=page_table_type.page_number,
            detected_table_count=detected_table_count,
            classified_table_count=len(page_table_type.table_types),
            extracted_table_count=len(raw_tables),
            matched_table_count=len(
                table_type_by_raw_index.table_type_by_raw_index
            ),
            unmatched_classifications=unmatched_classifications,
            unmatched_extractions=unmatched_extractions,
        )

    def _map_table_types_to_raw_tables(
        self,
        *,
        page_table_type: PageTableType,
        raw_tables: list[RawTable],
    ) -> _TableMappingResult:
        """Match classified table types to raw tables without positional guessing."""

        if not page_table_type.table_types:
            for raw_table_index in range(len(raw_tables)):
                self._logger.warning(
                    "Extracted table has no classified table type",
                    extra={
                        "page": page_table_type.page_number,
                        "table_index": raw_table_index,
                    },
                )
            return _TableMappingResult(
                table_type_by_raw_index={},
                assigned_classified_type_indexes=set(),
            )

        if len(raw_tables) == 1 and len(page_table_type.table_types) == 1:
            return _TableMappingResult(
                table_type_by_raw_index={0: page_table_type.table_types[0]},
                assigned_classified_type_indexes={0},
            )

        candidates = self._table_type_candidates(
            raw_tables=raw_tables,
            table_types=page_table_type.table_types,
        )
        assigned_raw_tables: set[int] = set()
        assigned_classified_types: set[int] = set()
        table_type_by_raw_index: dict[int, str] = {}

        for candidate in candidates:
            if candidate.raw_table_index in assigned_raw_tables:
                continue
            if candidate.classified_type_index in assigned_classified_types:
                continue

            assigned_raw_tables.add(candidate.raw_table_index)
            assigned_classified_types.add(candidate.classified_type_index)
            table_type = page_table_type.table_types[candidate.classified_type_index]
            table_type_by_raw_index[candidate.raw_table_index] = table_type
            self._log_order_correction_if_needed(
                page_table_type=page_table_type,
                raw_table_index=candidate.raw_table_index,
                assigned_table_type=table_type,
            )

        self._log_unmatched_tables(
            page_table_type=page_table_type,
            raw_tables=raw_tables,
            table_type_by_raw_index=table_type_by_raw_index,
            assigned_classified_types=assigned_classified_types,
        )
        return _TableMappingResult(
            table_type_by_raw_index=table_type_by_raw_index,
            assigned_classified_type_indexes=assigned_classified_types,
        )

    def _table_type_candidates(
        self,
        *,
        raw_tables: list[RawTable],
        table_types: list[str],
    ) -> list[_TableTypeCandidate]:
        candidates: list[_TableTypeCandidate] = []
        for raw_table_index, rows in enumerate(raw_tables):
            for classified_type_index, table_type in enumerate(table_types):
                score = _table_type_match_score(rows, table_type)
                if score <= 0:
                    continue
                candidates.append(
                    _TableTypeCandidate(
                        score=score,
                        raw_table_index=raw_table_index,
                        classified_type_index=classified_type_index,
                    )
                )

        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.raw_table_index,
                candidate.classified_type_index,
            ),
        )

    def _log_order_correction_if_needed(
        self,
        *,
        page_table_type: PageTableType,
        raw_table_index: int,
        assigned_table_type: str,
    ) -> None:
        if raw_table_index >= len(page_table_type.table_types):
            return

        positional_table_type = page_table_type.table_types[raw_table_index]
        if positional_table_type == assigned_table_type:
            return

        self._logger.warning(
            "Table classification ordering mismatch corrected",
            extra={
                "page": page_table_type.page_number,
                "table_index": raw_table_index,
                "positional_table_type": positional_table_type,
                "assigned_table_type": assigned_table_type,
            },
        )

    def _log_unmatched_tables(
        self,
        *,
        page_table_type: PageTableType,
        raw_tables: list[RawTable],
        table_type_by_raw_index: dict[int, str],
        assigned_classified_types: set[int],
    ) -> None:
        for raw_table_index in range(len(raw_tables)):
            if raw_table_index in table_type_by_raw_index:
                continue
            self._logger.warning(
                "Extracted table could not be matched to a classified table type",
                extra={
                    "page": page_table_type.page_number,
                    "table_index": raw_table_index,
                    "assigned_table_type": UNCLASSIFIED_TABLE_TYPE,
                    "classified_table_types": page_table_type.table_types,
                },
            )

        for classified_type_index, table_type in enumerate(page_table_type.table_types):
            if classified_type_index in assigned_classified_types:
                continue
            self._logger.warning(
                "Classified table type did not match an extracted table",
                extra={
                    "page": page_table_type.page_number,
                    "classified_type_index": classified_type_index,
                    "table_type": table_type,
                },
            )

    def _log_page_diagnostic(
        self,
        diagnostic: PageExtractionDiagnostic,
    ) -> None:
        """Log page-level linkage counts from detection through extraction."""

        self._logger.info(
            "Extraction page diagnostics",
            extra={
                "year": diagnostic.source_report_year,
                "page": diagnostic.page_number,
                "detected_table_count": diagnostic.detected_table_count,
                "classified_table_count": diagnostic.classified_table_count,
                "extracted_table_count": diagnostic.extracted_table_count,
                "matched_table_count": diagnostic.matched_table_count,
                "unmatched_classifications": diagnostic.unmatched_classifications,
                "unmatched_extractions": diagnostic.unmatched_extractions,
            },
        )

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


def _detected_counts_by_page(
    table_detection_result: TableDetectionResult | None,
) -> dict[int, int]:
    if table_detection_result is None:
        return {}
    return {
        detected_page.page_number: detected_page.tables_detected
        for detected_page in table_detection_result.detected_pages
    }


def _build_extraction_summary(
    page_diagnostics: list[PageExtractionDiagnostic],
) -> ExtractionSummary:
    """Build report-level diagnostics from page-level extraction diagnostics."""

    unmatched_classifications = [
        f"page={diagnostic.page_number} table_type={table_type}"
        for diagnostic in page_diagnostics
        for table_type in diagnostic.unmatched_classifications
    ]
    unmatched_extractions = [
        f"page={diagnostic.page_number} table_index={table_index}"
        for diagnostic in page_diagnostics
        for table_index in diagnostic.unmatched_extractions
    ]
    return ExtractionSummary(
        total_detected_tables=sum(
            diagnostic.detected_table_count for diagnostic in page_diagnostics
        ),
        total_classified_tables=sum(
            diagnostic.classified_table_count for diagnostic in page_diagnostics
        ),
        total_extracted_tables=sum(
            diagnostic.extracted_table_count for diagnostic in page_diagnostics
        ),
        total_matched_tables=sum(
            diagnostic.matched_table_count for diagnostic in page_diagnostics
        ),
        unmatched_classifications=unmatched_classifications,
        unmatched_extractions=unmatched_extractions,
        page_diagnostics=page_diagnostics,
    )


def _table_type_match_score(rows: RawTable, table_type: str) -> int:
    """Score how strongly raw table text supports a classified table type."""

    table_text = _normalized_table_text(rows)
    if not table_text:
        return 0

    score = 0
    keywords = _keywords_for_table_type(table_type)
    for keyword in keywords:
        if _contains_phrase(table_text, keyword):
            score += max(1, len(keyword.split()))

    if not keywords:
        for token in _table_type_tokens(table_type):
            if _contains_phrase(table_text, token):
                score += 1

    return score


def _normalized_table_text(rows: RawTable) -> str:
    values = [
        str(cell)
        for row in rows
        for cell in row
        if str(cell).strip()
    ]
    return _normalize_text(" ".join(values))


def _normalize_text(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"\b{re.escape(normalized_phrase)}\b", text) is not None


def _keywords_for_table_type(table_type: str) -> tuple[str, ...]:
    normalized_table_type = _normalize_key(table_type)
    return _TABLE_TYPE_KEYWORDS.get(normalized_table_type, ())


def _table_type_tokens(table_type: str) -> tuple[str, ...]:
    ignored_tokens = {
        "and",
        "financial",
        "note",
        "notes",
        "of",
        "schedule",
        "statement",
        "table",
    }
    tokens = tuple(
        token
        for token in _normalize_key(table_type).split("_")
        if len(token) > 2 and token not in ignored_tokens
    )
    return tokens


def _normalize_key(value: str) -> str:
    normalized = str(value).lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for result metadata."""

    return str(exc) or exc.__class__.__name__


_TABLE_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "balance_sheet": (
        "statement of financial position",
        "total assets",
        "non current assets",
        "current assets",
        "total liabilities",
        "share capital",
        "reserves",
        "equity",
        "inventory",
        "inventories",
        "trade receivables",
        "trade payables",
        "cash and bank",
        "cash",
        "bank balances",
        "property plant and equipment",
    ),
    "statement_of_financial_position": (
        "statement of financial position",
        "total assets",
        "total liabilities",
        "equity",
        "current assets",
        "current liabilities",
    ),
    "income_statement": (
        "statement of profit or loss",
        "profit and loss",
        "revenue",
        "sales",
        "turnover",
        "cost of sales",
        "gross profit",
        "ebitda",
        "operating profit",
        "finance cost",
        "profit before tax",
        "profit after tax",
        "earnings per share",
    ),
    "profit_and_loss": (
        "profit and loss",
        "revenue",
        "sales",
        "cost of sales",
        "gross profit",
        "profit before tax",
        "profit after tax",
    ),
    "statement_of_profit_or_loss": (
        "statement of profit or loss",
        "revenue",
        "cost of sales",
        "gross profit",
        "profit after tax",
        "earnings per share",
    ),
    "cash_flow_statement": (
        "statement of cash flows",
        "cash flows",
        "operating activities",
        "investing activities",
        "financing activities",
        "cash generated from operations",
        "net cash",
        "cash and cash equivalents",
    ),
    "cash_flow": (
        "cash flows",
        "operating activities",
        "investing activities",
        "financing activities",
        "net cash",
    ),
    "statement_of_cash_flows": (
        "statement of cash flows",
        "operating activities",
        "investing activities",
        "financing activities",
        "cash and cash equivalents",
    ),
    "statement_of_changes_in_equity": (
        "statement of changes in equity",
        "share capital",
        "reserves",
        "unappropriated profit",
        "total comprehensive income",
        "dividend",
    ),
    "debt_schedule": (
        "debt schedule",
        "borrowings",
        "long term debt",
        "short term debt",
        "long term financing",
        "short term borrowings",
        "loans and borrowings",
        "lease liabilities",
        "markup accrued",
        "debt",
    ),
    "borrowings_note": (
        "borrowings",
        "long term financing",
        "short term borrowings",
        "loans and borrowings",
        "lease liabilities",
    ),
    "loans_and_borrowings": (
        "loans and borrowings",
        "borrowings",
        "long term financing",
        "short term borrowings",
        "lease liabilities",
    ),
    "segment_information": (
        "segment information",
        "reportable segment",
        "segment revenue",
        "segment assets",
        "segment liabilities",
        "geographical segment",
    ),
    "taxation_note": (
        "taxation",
        "tax expense",
        "current tax",
        "deferred tax",
        "income tax",
        "tax charge",
    ),
    "inventory_note": (
        "inventories",
        "inventory",
        "raw materials",
        "work in process",
        "finished goods",
        "stores spares",
        "stock in trade",
    ),
    "property_plant_equipment_note": (
        "property plant and equipment",
        "operating fixed assets",
        "additions",
        "depreciation",
        "written down value",
        "capital work in progress",
    ),
}
