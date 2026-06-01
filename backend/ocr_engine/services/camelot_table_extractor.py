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
    ExtractionQualityReport,
    ExtractionSummary,
    FragmentationCleanupDiagnostic,
    HeaderInheritanceDiagnostic,
    LabelDegluingDiagnostic,
    LabelReconstructionDiagnostic,
    MetricValueOccurrence,
    NoteContextInheritanceDiagnostic,
    NoteRowFilteringDiagnostic,
    PageExtractionDiagnostic,
    SuspiciousMetricFinding,
    SuspiciousTableFinding,
    TableExtractionResult,
)
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.interfaces.table_extractor import ITableExtractor
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue

logger = logging.getLogger(__name__)

RawTable = list[list[str]]
UNCLASSIFIED_TABLE_TYPE = "unclassified_table"
EXTRACTION_STRATEGY_CAMELOT = "full_page_camelot"
EXTRACTION_STRATEGY_PDFPLUMBER_DEFAULT = "full_page_pdfplumber_default"
EXTRACTION_STRATEGY_PDFPLUMBER_TEXT = "full_page_pdfplumber_text"
PDFPLUMBER_TEXT_TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
}


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


@dataclass(frozen=True)
class _ExtractionQuality:
    """Quality metrics for raw table extraction before classification mapping."""

    quality_score: float
    year_column_count: int
    metric_label_count: int
    metric_value_count: int
    numeric_only_table_count: int

    @property
    def is_sufficient(self) -> bool:
        """Return whether extraction is usable for MetricValue generation."""

        return (
            self.year_column_count > 0
            and self.metric_label_count > 0
            and self.metric_value_count > 0
        )


@dataclass(frozen=True)
class _RawExtractionResult:
    """Raw extraction rows with selected strategy diagnostics."""

    strategy: str
    raw_tables: list[RawTable]
    quality: _ExtractionQuality


@dataclass(frozen=True)
class _RawTableProvenance:
    """Provenance for a raw table after optional scoped logical splitting."""

    source_table_index: int
    split_table_index: int | None = None
    split_reason: str | None = None
    logical_type_hint: str | None = None


@dataclass(frozen=True)
class _PreparedRawTables:
    """Raw tables prepared for matching, plus split diagnostics."""

    raw_tables: list[RawTable]
    provenance: list[_RawTableProvenance]
    tables_split: int = 0
    split_reason: str | None = None
    logical_types_created: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ReconstructedLabel:
    """Metric label reconstructed from adjacent table cells."""

    original_label: str
    reconstructed_label: str
    confidence: float
    merged_cell_count: int
    stop_reason: str

    @property
    def changed(self) -> bool:
        """Return whether reconstruction changed the extracted label."""

        return self.reconstructed_label != self.original_label


@dataclass(frozen=True)
class _DegluedLabel:
    """Metric label cleaned after reconstruction for OCR spacing artifacts."""

    original_label: str
    deglued_label: str
    confidence: float
    rules_applied: tuple[str, ...]

    @property
    def changed(self) -> bool:
        """Return whether degluing changed the reconstructed label."""

        return self.deglued_label != self.original_label


@dataclass(frozen=True)
class _FragmentationCleanupResult:
    """Metric label completed after reconstruction and degluing."""

    original_label: str
    completed_label: str
    reconstruction_reason: tuple[str, ...]
    source_cells: tuple[str, ...]
    completion_source: tuple[str, ...]

    @property
    def changed(self) -> bool:
        """Return whether cleanup changed the deglued label."""

        return self.completed_label != self.original_label


@dataclass
class _NoteContextStack:
    """Active note-table context while walking extracted rows."""

    active_note_header: str | None = None
    active_section_header: str | None = None
    active_parent_label: str | None = None


@dataclass(frozen=True)
class _ContextInheritedLabel:
    """Metric label after optional note-table context inheritance."""

    original_label: str
    inherited_label: str
    inherited_context: str | None = None
    context_source: str | None = None
    reconstruction_reason: str | None = None

    @property
    def changed(self) -> bool:
        """Return whether context inheritance changed the label."""

        return self.inherited_label != self.original_label


@dataclass
class _HeaderContextStack:
    """Active table/header/unit context while walking extracted rows."""

    active_header: str | None = None
    active_section: str | None = None
    active_unit: str | None = None


@dataclass(frozen=True)
class _HeaderInheritedLabel:
    """Metric label after optional table header inheritance."""

    original_label: str
    inherited_label: str
    inherited_header: str | None = None
    inheritance_source: str | None = None
    reconstruction_reason: str | None = None

    @property
    def changed(self) -> bool:
        """Return whether header inheritance changed the label."""

        return self.inherited_label != self.original_label


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

            raw_extraction = self._extract_page_tables(pdf_path, page_number)
            prepared_tables = self._prepare_raw_tables_for_matching(
                page_table_type=page_table_type,
                raw_tables=raw_extraction.raw_tables,
            )
            extraction_quality = (
                self._evaluate_extraction_quality(prepared_tables.raw_tables)
                if prepared_tables.tables_split
                else raw_extraction.quality
            )
            extraction_strategy = raw_extraction.strategy
            if prepared_tables.tables_split:
                extraction_strategy = f"{extraction_strategy}+analysis_table_split"
            page_tables, page_diagnostic = self._build_extracted_tables(
                page_table_type=page_table_type,
                raw_tables=prepared_tables.raw_tables,
                raw_table_provenance=prepared_tables.provenance,
                detected_table_count=detected_counts_by_page.get(page_number, 0),
                extraction_strategy=extraction_strategy,
                extraction_quality=extraction_quality,
                tables_split=prepared_tables.tables_split,
                split_reason=prepared_tables.split_reason,
                logical_types_created=list(prepared_tables.logical_types_created),
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
        result = self._attach_quality_report(result)
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
        self._logger.info(
            "Extraction quality validation completed",
            extra=result.extraction_summary.quality_report.model_dump(
                exclude={"top_suspicious_tables", "top_suspicious_metrics"}
            ),
        )
        return result

    def _attach_quality_report(
        self,
        result: TableExtractionResult,
    ) -> TableExtractionResult:
        """Attach extraction quality diagnostics without risking data loss."""

        try:
            quality_report = _build_extraction_quality_report(result.tables)
        except Exception:
            self._logger.warning(
                "Extraction quality diagnostics failed; preserving extraction result",
                extra={
                    "tables_extracted": len(result.tables),
                    "metric_values_extracted": len(result.metric_values),
                },
                exc_info=True,
            )
            quality_report = _build_partial_extraction_quality_report(result.tables)

        return result.model_copy(
            update={
                "extraction_summary": result.extraction_summary.model_copy(
                    update={"quality_report": quality_report}
                )
            }
        )

    def _extract_page_tables(
        self,
        pdf_path: str,
        page_number: int,
    ) -> _RawExtractionResult:
        """Extract tables and select the best available raw table strategy."""

        raw_tables = self._extract_with_camelot(pdf_path, page_number)
        camelot_result = self._raw_extraction_result(
            strategy=EXTRACTION_STRATEGY_CAMELOT,
            raw_tables=raw_tables,
        )
        if raw_tables:
            self._logger.info(
                "Camelot succeeded",
                extra={
                    "page": page_number,
                    "tables_extracted": len(raw_tables),
                    **_quality_log_extra(camelot_result.quality),
                },
            )
            if camelot_result.quality.is_sufficient:
                return camelot_result

        self._logger.info(
            "Camelot failed",
            extra={
                "page": page_number,
                "reason": "no_tables_or_poor_quality",
                **_quality_log_extra(camelot_result.quality),
            },
        )
        self._logger.info(
            "Using pdfplumber default fallback",
            extra={"page": page_number},
        )
        pdfplumber_default_result = self._raw_extraction_result(
            strategy=EXTRACTION_STRATEGY_PDFPLUMBER_DEFAULT,
            raw_tables=self._extract_with_pdfplumber(pdf_path, page_number),
        )
        if pdfplumber_default_result.quality.is_sufficient:
            return self._select_best_extraction(
                camelot_result,
                pdfplumber_default_result,
            )

        self._logger.info(
            "Using pdfplumber text fallback",
            extra={
                "page": page_number,
                **_quality_log_extra(pdfplumber_default_result.quality),
            },
        )
        pdfplumber_text_result = self._raw_extraction_result(
            strategy=EXTRACTION_STRATEGY_PDFPLUMBER_TEXT,
            raw_tables=self._extract_with_pdfplumber(
                pdf_path,
                page_number,
                table_settings=PDFPLUMBER_TEXT_TABLE_SETTINGS,
            ),
        )
        return self._select_best_extraction(
            camelot_result,
            pdfplumber_default_result,
            pdfplumber_text_result,
        )

    def _raw_extraction_result(
        self,
        *,
        strategy: str,
        raw_tables: list[RawTable],
    ) -> _RawExtractionResult:
        """Build a raw extraction result with quality metrics."""

        return _RawExtractionResult(
            strategy=strategy,
            raw_tables=raw_tables,
            quality=self._evaluate_extraction_quality(raw_tables),
        )

    def _select_best_extraction(
        self,
        *results: _RawExtractionResult,
    ) -> _RawExtractionResult:
        """Select the highest-quality extraction result deterministically."""

        selected = max(
            results,
            key=lambda result: (
                result.quality.quality_score,
                result.quality.metric_value_count,
                result.quality.year_column_count,
                result.quality.metric_label_count,
                -_strategy_rank(result.strategy),
            ),
        )
        self._logger.info(
            "Extraction strategy selected",
            extra={
                "strategy": selected.strategy,
                "tables_extracted": len(selected.raw_tables),
                **_quality_log_extra(selected.quality),
            },
        )
        return selected

    def _prepare_raw_tables_for_matching(
        self,
        *,
        page_table_type: PageTableType,
        raw_tables: list[RawTable],
    ) -> _PreparedRawTables:
        """Apply narrowly scoped logical splitting before table-type matching."""

        default_provenance = [
            _RawTableProvenance(source_table_index=index)
            for index in range(len(raw_tables))
        ]
        if not raw_tables or not _is_analysis_style_classification(
            page_table_type.table_types
        ):
            return _PreparedRawTables(
                raw_tables=raw_tables,
                provenance=default_provenance,
            )

        if len(raw_tables) >= len(page_table_type.table_types):
            return _PreparedRawTables(
                raw_tables=raw_tables,
                provenance=default_provenance,
            )

        primary_table_type = _primary_analysis_table_type(page_table_type.table_types)
        if primary_table_type is None:
            return _PreparedRawTables(
                raw_tables=raw_tables,
                provenance=default_provenance,
            )

        prepared_tables: list[RawTable] = []
        provenance: list[_RawTableProvenance] = []
        logical_types_created: list[str] = []
        tables_split = 0
        for source_table_index, rows in enumerate(raw_tables):
            split_tables = _split_analysis_style_table(
                rows=rows,
                primary_table_type=primary_table_type,
            )
            if len(split_tables) < 3:
                prepared_tables.append(rows)
                provenance.append(
                    _RawTableProvenance(source_table_index=source_table_index)
                )
                continue

            tables_split += len(split_tables) - 1
            for split_table_index, split_table in enumerate(split_tables):
                prepared_tables.append(split_table.rows)
                logical_types_created.append(split_table.logical_type)
                provenance.append(
                    _RawTableProvenance(
                        source_table_index=source_table_index,
                        split_table_index=split_table_index,
                        split_reason=split_table.split_reason,
                        logical_type_hint=split_table.logical_type,
                    )
                )

        if tables_split == 0:
            return _PreparedRawTables(
                raw_tables=raw_tables,
                provenance=default_provenance,
            )

        self._logger.info(
            "Analysis-style table split into logical subtables",
            extra={
                "page": page_table_type.page_number,
                "tables_split": tables_split,
                "logical_types_created": logical_types_created,
            },
        )
        return _PreparedRawTables(
            raw_tables=prepared_tables,
            provenance=provenance,
            tables_split=tables_split,
            split_reason=_ANALYSIS_SPLIT_REASON,
            logical_types_created=tuple(logical_types_created),
        )

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
        *,
        table_settings: dict[str, str] | None = None,
    ) -> list[RawTable]:
        """Extract tables from a PDF page using pdfplumber."""

        try:
            with self._pdfplumber_open(pdf_path) as pdf:
                page = pdf.pages[page_number - 1]
                if table_settings is None:
                    tables = page.extract_tables() or []
                else:
                    tables = page.extract_tables(table_settings=table_settings) or []
                raw_tables = [self._normalize_rows(table) for table in tables]
                return [table for table in raw_tables if table]
        except Exception:
            self._logger.exception(
                "pdfplumber failed",
                extra={"page": page_number, "table_settings": table_settings},
            )
            return []

    def _build_extracted_tables(
        self,
        *,
        page_table_type: PageTableType,
        raw_tables: list[RawTable],
        detected_table_count: int,
        extraction_strategy: str,
        extraction_quality: _ExtractionQuality,
        raw_table_provenance: Sequence[_RawTableProvenance] | None = None,
        tables_split: int = 0,
        split_reason: str | None = None,
        logical_types_created: list[str] | None = None,
    ) -> tuple[list[ExtractedTable], PageExtractionDiagnostic]:
        """Build output models from raw extracted tables and page classifications."""

        logical_types_created = logical_types_created or []
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
                extraction_strategy=extraction_strategy,
                quality_score=extraction_quality.quality_score,
                year_column_count=extraction_quality.year_column_count,
                metric_label_count=extraction_quality.metric_label_count,
                metric_value_count=extraction_quality.metric_value_count,
                numeric_only_table_count=extraction_quality.numeric_only_table_count,
                unmatched_classifications=page_table_type.table_types,
                unmatched_extractions=[],
                tables_split=tables_split,
                split_reason=split_reason,
                logical_types_created=logical_types_created,
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
            provenance = _raw_table_provenance_for_index(
                raw_table_provenance,
                index,
            )
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
                    source_table_index=provenance.source_table_index,
                    split_table_index=provenance.split_table_index,
                    split_reason=provenance.split_reason,
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
            extraction_strategy=extraction_strategy,
            quality_score=extraction_quality.quality_score,
            year_column_count=extraction_quality.year_column_count,
            metric_label_count=extraction_quality.metric_label_count,
            metric_value_count=sum(
                len(table.metric_values) for table in extracted_tables
            ),
            numeric_only_table_count=extraction_quality.numeric_only_table_count,
            unmatched_classifications=unmatched_classifications,
            unmatched_extractions=unmatched_extractions,
            tables_split=tables_split,
            split_reason=split_reason,
            logical_types_created=logical_types_created,
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
                "extraction_strategy": diagnostic.extraction_strategy,
                "quality_score": diagnostic.quality_score,
                "year_column_count": diagnostic.year_column_count,
                "metric_label_count": diagnostic.metric_label_count,
                "metric_value_count": diagnostic.metric_value_count,
                "numeric_only_table_count": diagnostic.numeric_only_table_count,
                "unmatched_classifications": diagnostic.unmatched_classifications,
                "unmatched_extractions": diagnostic.unmatched_extractions,
                "tables_split": diagnostic.tables_split,
                "split_reason": diagnostic.split_reason,
                "logical_types_created": diagnostic.logical_types_created,
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
        context_stack = _NoteContextStack()
        header_context_stack = _HeaderContextStack()
        use_note_context = _is_note_context_table(table_type, rows)
        for row_index, row in enumerate(rows):
            if row_index == header_row_index:
                _update_header_context_from_row(
                    header_context_stack,
                    label=_row_text(row),
                    row=row,
                    row_index=row_index,
                    header_row_index=header_row_index,
                    metric_value_count=0,
                    table_type=table_type,
                )
                continue

            label_index = self._metric_label_index(row)
            if label_index is None:
                continue

            reconstructed_label = self._reconstruct_metric_label(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            ).reconstructed_label
            deglued_label = _deglue_label_text(reconstructed_label).deglued_label
            metric = _cleanup_fragmented_label(
                deglued_label,
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            ).completed_label
            if _note_row_filtering_reason(metric) is not None:
                continue

            metric_value_count = _metric_value_count_for_row(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
                scale_multiplier=scale_multiplier,
            )
            if metric_value_count == 0:
                _update_header_context_from_row(
                    header_context_stack,
                    label=metric,
                    row=row,
                    row_index=row_index,
                    header_row_index=header_row_index,
                    metric_value_count=metric_value_count,
                    table_type=table_type,
                )
                if not use_note_context:
                    continue
                _update_note_context_from_header_row(
                    context_stack,
                    label=metric,
                    row_index=row_index,
                    header_row_index=header_row_index,
                    table_type=table_type,
                )
                continue

            inherited_label = (
                _inherit_note_context(
                    metric,
                    context_stack,
                    broad_note_context=True,
                )
                if use_note_context
                else _ContextInheritedLabel(
                    original_label=metric,
                    inherited_label=metric,
                )
            )
            header_inherited_label = (
                _inherit_header_context(
                    inherited_label.inherited_label,
                    row=row,
                    label_index=label_index,
                    year_columns=year_columns,
                    context_stack=header_context_stack,
                )
                if not inherited_label.changed
                else _HeaderInheritedLabel(
                    original_label=inherited_label.inherited_label,
                    inherited_label=inherited_label.inherited_label,
                )
            )
            metric = header_inherited_label.inherited_label

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

            if use_note_context and metric_value_count > 0:
                _update_note_context_from_metric_row(
                    context_stack,
                    label=inherited_label.original_label,
                    inherited_label=inherited_label,
                )
            if metric_value_count > 0:
                _update_header_context_from_row(
                    header_context_stack,
                    label=header_inherited_label.original_label,
                    row=row,
                    row_index=row_index,
                    header_row_index=header_row_index,
                    metric_value_count=metric_value_count,
                    table_type=table_type,
                    inherited_label=header_inherited_label,
                )

        return metric_values

    def _evaluate_extraction_quality(
        self,
        raw_tables: list[RawTable],
    ) -> _ExtractionQuality:
        """Evaluate whether raw tables preserve financial table structure."""

        year_column_count = 0
        metric_label_count = 0
        metric_value_count = 0
        numeric_only_table_count = 0

        for rows in raw_tables:
            _, year_columns = self._find_year_columns(rows)
            labels = _metric_labels(rows)
            metric_values = self._extract_metric_values(
                rows=rows,
                source_report_year=9999,
                page_number=1,
                table_type="quality_diagnostic",
            )

            year_column_count += len(year_columns)
            metric_label_count += len(labels)
            metric_value_count += len(metric_values)
            if _is_numeric_only_table(rows):
                numeric_only_table_count += 1

        return _ExtractionQuality(
            quality_score=_quality_score(
                raw_tables=raw_tables,
                year_column_count=year_column_count,
                metric_label_count=metric_label_count,
                metric_value_count=metric_value_count,
                numeric_only_table_count=numeric_only_table_count,
            ),
            year_column_count=year_column_count,
            metric_label_count=metric_label_count,
            metric_value_count=metric_value_count,
            numeric_only_table_count=numeric_only_table_count,
        )

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
    def _reconstruct_metric_label(
        cls,
        *,
        row: Sequence[str],
        label_index: int,
        year_columns: dict[int, int],
    ) -> _ReconstructedLabel:
        """Merge adjacent text cells that belong to one metric label."""

        original_label = str(row[label_index]).strip()
        label_parts: list[str] = []
        stop_reason = "row_end"

        for column_index in range(label_index, len(row)):
            text = str(row[column_index]).strip()
            if column_index != label_index:
                candidate_stop_reason = cls._label_merge_stop_reason(
                    text,
                    column_index=column_index,
                    year_columns=year_columns,
                )
                if candidate_stop_reason is not None:
                    stop_reason = candidate_stop_reason
                    break

            if not text:
                continue

            if re.search(r"[A-Za-z]", text):
                label_parts.append(text)
                continue

            if column_index == label_index:
                stop_reason = "non_text_label"
                break

        reconstructed_label = _normalize_label_text(" ".join(label_parts))
        if not reconstructed_label:
            reconstructed_label = original_label

        merged_cell_count = len(label_parts)
        return _ReconstructedLabel(
            original_label=original_label,
            reconstructed_label=reconstructed_label,
            confidence=cls._label_reconstruction_confidence(
                original_label=original_label,
                reconstructed_label=reconstructed_label,
                merged_cell_count=merged_cell_count,
                stop_reason=stop_reason,
            ),
            merged_cell_count=max(1, merged_cell_count),
            stop_reason=stop_reason,
        )

    @classmethod
    def _label_merge_stop_reason(
        cls,
        text: str,
        *,
        column_index: int,
        year_columns: dict[int, int],
    ) -> str | None:
        """Return the reason a cell should stop label reconstruction."""

        stripped = str(text).strip()
        if column_index in year_columns:
            return "year_column"
        if not stripped:
            return None
        if cls._is_year_cell(stripped):
            return "year_column"
        if cls._is_percentage_cell(stripped):
            return "percentage_column"
        if cls._is_note_number_cell(stripped):
            return "note_number"
        if cls._is_rating_cell(stripped):
            return "rating"
        if cls._parse_metric_value(stripped) is not None:
            return "numeric_value"
        if not re.search(r"[A-Za-z]", stripped):
            return "non_text_cell"
        return None

    @staticmethod
    def _is_year_cell(text: str) -> bool:
        return re.fullmatch(r"(?:19|20)\d{2}", text.strip()) is not None

    @staticmethod
    def _is_note_number_cell(text: str) -> bool:
        stripped = text.strip()
        return (
            re.fullmatch(r"\d+(?:\.\d+)+", stripped) is not None
            or re.fullmatch(
                r"note\s*\d+(?:\.\d+)*",
                stripped,
                re.IGNORECASE,
            )
            is not None
            or stripped.lower() in {"note", "notes"}
        )

    @staticmethod
    def _is_rating_cell(text: str) -> bool:
        stripped = text.strip()
        return (
            re.fullmatch(r"A1\+?|A\+?|AA\+?|AAA|BBB\+?", stripped, re.IGNORECASE)
            is not None
            or stripped.upper() in {"PACRA", "VIS", "JCR", "MOODY", "FITCH"}
        )

    @staticmethod
    def _is_percentage_cell(text: str) -> bool:
        return re.fullmatch(r"[+-]?\d+(?:\.\d+)?%", text.strip()) is not None

    @staticmethod
    def _label_reconstruction_confidence(
        *,
        original_label: str,
        reconstructed_label: str,
        merged_cell_count: int,
        stop_reason: str,
    ) -> float:
        """Score how likely an adjacent-cell label merge is correct."""

        if reconstructed_label == original_label:
            return 1.0

        confidence = 0.72
        if stop_reason in {
            "year_column",
            "numeric_value",
            "note_number",
            "rating",
            "percentage_column",
        }:
            confidence += 0.18
        if 2 <= merged_cell_count <= 5:
            confidence += 0.06
        if merged_cell_count > 7:
            confidence -= 0.12
        if reconstructed_label.lower().startswith(original_label.lower()):
            confidence += 0.03
        return round(max(0.0, min(confidence, 0.99)), 2)

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


def _normalize_label_text(text: str) -> str:
    """Normalize spacing artifacts introduced by split table cells."""

    normalized = re.sub(r"\s+", " ", text).strip()
    fragment_replacements = [
        (r"\bIn\s+vestments\b", "Investments"),
        (r"\bi\s+nvestments\b", "investments"),
        (r"\bHa\s+bib\b", "Habib"),
        (r"\ba\s+ssets\b", "assets"),
        (r"\bshar\s+e\b", "share"),
        (r"\bsubscript\s+ion\b", "subscription"),
        (r"\breserv\s+e\b", "reserve"),
        (r"\breceiva\s+bles\b", "receivables"),
        (r"\btaxatio\s+n\b", "taxation"),
        (r"\bintang\s+ible\b", "intangible"),
        (r"\bpertai\s+ning\b", "pertaining"),
        (r"\bcurren\s+t\b", "current"),
        (r"\bnon[–-]c\s+urrent\b", "non-current"),
        (r"\bgai\s+n\b", "gain"),
        (r"\blo\s+ss\b", "loss"),
        (r"\bobligation\s+s\b", "obligations"),
        (r"\bpers\s+ons\b", "persons"),
        (r"\brem\s+uneration\b", "remuneration"),
        (r"\bexpens\s+es\b", "expenses"),
        (r"\bprepay\s+ments\b", "prepayments"),
    ]
    for pattern, replacement in fragment_replacements:
        normalized = re.sub(pattern, replacement, normalized)
    normalized = re.sub(r"\s+([,;:)])", r"\1", normalized)
    normalized = re.sub(r"([(])\s+", r"\1", normalized)
    return normalized.strip()


_DEGLUE_KNOWN_WORDS = {
    "addition",
    "administrative",
    "advance",
    "advances",
    "amenities",
    "assets",
    "balances",
    "bank",
    "before",
    "billion",
    "capital",
    "cash",
    "charges",
    "company",
    "comprehensive",
    "cost",
    "current",
    "deferred",
    "deposits",
    "distribution",
    "employees",
    "equipment",
    "equity",
    "expenses",
    "finance",
    "financial",
    "gain",
    "habib",
    "income",
    "intangible",
    "investments",
    "liabilities",
    "loans",
    "loss",
    "managerial",
    "noncurrent",
    "note",
    "obligations",
    "of",
    "operating",
    "ordinary",
    "other",
    "payables",
    "persons",
    "prepayments",
    "profit",
    "receivables",
    "remuneration",
    "reserve",
    "reserves",
    "salaries",
    "share",
    "subscription",
    "taxation",
    "term",
    "to",
}
_DEGLUE_TOKEN_PATTERN = re.compile(r"^([^A-Za-z]*)([A-Za-z]+)([^A-Za-z]*)$")
_DEGLUE_RATING_TOKENS = {"A", "AA", "AAA", "A1", "A1+", "PACRA", "VIS", "JCR"}


def _deglue_label_text(text: str) -> _DegluedLabel:
    """Remove intra-word spaces introduced by OCR/pdfplumber label segmentation."""

    original_label = _normalize_label_text(text)
    if not original_label:
        return _DegluedLabel(
            original_label=str(text),
            deglued_label=str(text),
            confidence=1.0,
            rules_applied=(),
        )

    tokens = original_label.split(" ")
    rules_applied: list[str] = []
    for _ in range(4):
        changed = False
        merged_tokens: list[str] = []
        index = 0
        while index < len(tokens):
            if index + 1 < len(tokens):
                merged_token = _try_deglue_token_pair(tokens[index], tokens[index + 1])
                if merged_token is not None:
                    merged_tokens.append(merged_token)
                    rules_applied.append("known_financial_word_join")
                    index += 2
                    changed = True
                    continue

            merged_tokens.append(tokens[index])
            index += 1

        tokens = merged_tokens
        if not changed:
            break

    deglued_label = _normalize_label_text(" ".join(tokens))
    rules = tuple(_dedupe_preserve_order(rules_applied))
    return _DegluedLabel(
        original_label=original_label,
        deglued_label=deglued_label,
        confidence=_label_degluing_confidence(
            original_label=original_label,
            deglued_label=deglued_label,
            rules_applied=rules,
        ),
        rules_applied=rules,
    )


def _try_deglue_token_pair(left: str, right: str) -> str | None:
    """Return a joined token when a token pair is a known split word."""

    left_match = _DEGLUE_TOKEN_PATTERN.fullmatch(left)
    right_match = _DEGLUE_TOKEN_PATTERN.fullmatch(right)
    if left_match is None or right_match is None:
        return None

    left_prefix, left_core, left_suffix = left_match.groups()
    right_prefix, right_core, right_suffix = right_match.groups()
    if left_suffix or right_prefix:
        return None
    if _is_deglue_protected_token(left_core) or _is_deglue_protected_token(right_core):
        return None

    joined_lower = f"{left_core}{right_core}".lower()
    if joined_lower not in _DEGLUE_KNOWN_WORDS:
        return None

    joined = _apply_deglued_case(left_core, right_core, joined_lower)
    return f"{left_prefix}{joined}{right_suffix}"


def _is_deglue_protected_token(token: str) -> bool:
    """Return whether a token should not participate in degluing."""

    upper = token.upper()
    return upper in _DEGLUE_RATING_TOKENS or re.fullmatch(r"(?:19|20)\d{2}", token)


def _apply_deglued_case(left: str, right: str, joined_lower: str) -> str:
    """Return a deglued token with the original label's casing style."""

    if left.isupper() and right.isupper() and len(joined_lower) > 2:
        return joined_lower.upper()
    if left[:1].isupper():
        return joined_lower.capitalize()
    return joined_lower


def _label_degluing_confidence(
    *,
    original_label: str,
    deglued_label: str,
    rules_applied: Sequence[str],
) -> float:
    """Score how likely degluing preserved the intended metric label."""

    if original_label == deglued_label:
        return 1.0
    confidence = 0.91
    if rules_applied:
        confidence += 0.06
    if len(rules_applied) > 4:
        confidence -= 0.06
    return round(max(0.0, min(confidence, 0.99)), 2)


_FRAGMENTATION_CLEANUP_WORDS = tuple(
    sorted(
        _DEGLUE_KNOWN_WORDS
        | {
            "activities",
            "after",
            "analysis",
            "and",
            "average",
            "benefit",
            "coverage",
            "decrease",
            "employed",
            "employee",
            "equivalent",
            "expenditures",
            "flow",
            "increase",
            "investment",
            "june",
            "operation",
            "operations",
            "outflow",
            "particulars",
            "plant",
            "position",
            "property",
            "ratio",
            "ratios",
            "revaluation",
            "sale",
            "sales",
            "times",
            "valuation",
            "value",
            "year",
        },
        key=len,
        reverse=True,
    )
)


def _cleanup_fragmented_label(
    label: str,
    *,
    row: Sequence[str],
    label_index: int,
    year_columns: dict[int, int],
) -> _FragmentationCleanupResult:
    """Complete residual OCR/pdfplumber fragments before MetricValue creation."""

    original_label = _normalize_label_text(label)
    completed_label = original_label
    reasons: list[str] = []
    completion_sources: list[str] = []
    source_cells: list[str] = [
        str(row[label_index]).strip()
    ] if label_index < len(row) and str(row[label_index]).strip() else []

    text_completion = _adjacent_text_completion_fragment(
        row=row,
        label_index=label_index,
        year_columns=year_columns,
        current_label=completed_label,
    )
    if text_completion:
        candidate = _normalize_label_text(
            f"{completed_label} {' '.join(text_completion)}",
        )
        if candidate != completed_label:
            completed_label = candidate
            reasons.append("adjacent_cell_completion")
            completion_sources.append("adjacent_text_cells")
            source_cells.extend(text_completion)

    unit_fragment = _row_unit_context_fragment(
        row=row,
        label_index=label_index,
        year_columns=year_columns,
    )
    if unit_fragment is not None and _should_complete_with_unit_fragment(
        completed_label,
        unit_fragment,
    ):
        candidate = _complete_label_with_unit_fragment(
            completed_label,
            unit_fragment,
        )
        if candidate != completed_label:
            completed_label = candidate
            reasons.append("unit_context_completion")
            completion_sources.append("adjacent_unit_cell")
            source_cells.append(unit_fragment)

    truncated_candidate = _repair_truncated_label(completed_label)
    if truncated_candidate != completed_label:
        completed_label = truncated_candidate
        reasons.append("truncated_label_repair")
        completion_sources.append("heuristic_truncated_label")

    spacing_repaired = _repair_remaining_fragment_spacing(completed_label)
    if spacing_repaired != completed_label:
        completed_label = spacing_repaired
        reasons.append("remaining_spacing_repair")
        completion_sources.append("spacing_repair")

    return _FragmentationCleanupResult(
        original_label=original_label,
        completed_label=completed_label,
        reconstruction_reason=tuple(_dedupe_preserve_order(reasons)),
        source_cells=tuple(
            _dedupe_preserve_order(
                [cell for cell in source_cells if str(cell).strip()],
            )
        ),
        completion_source=tuple(_dedupe_preserve_order(completion_sources)),
    )


def _adjacent_text_completion_fragment(
    *,
    row: Sequence[str],
    label_index: int,
    year_columns: dict[int, int],
    current_label: str,
) -> list[str]:
    """Return adjacent text cells that complete a truncated metric label."""

    fragments: list[str] = []
    for column_index in range(label_index + 1, len(row)):
        text = str(row[column_index]).strip()
        stop_reason = CamelotTableExtractor._label_merge_stop_reason(
            text,
            column_index=column_index,
            year_columns=year_columns,
        )
        if stop_reason is not None:
            break
        if not text:
            continue
        if not re.search(r"[A-Za-z]", text):
            break
        if _is_unit_fragment_cell(text):
            break
        fragments.append(text)

    if not fragments:
        return []
    compact_current = _compact_text(current_label)
    compact_fragments = _compact_text(" ".join(fragments))
    if compact_fragments and compact_fragments in compact_current:
        return []
    candidate = _normalize_label_text(f"{current_label} {' '.join(fragments)}")
    if candidate == current_label:
        return []
    if _should_complete_from_adjacent_text(current_label, fragments):
        return fragments
    return []


def _should_complete_from_adjacent_text(label: str, fragments: Sequence[str]) -> bool:
    """Return whether adjacent text is likely a lost label fragment."""

    if not fragments:
        return False
    joined = _normalize_label_text(" ".join(fragments))
    if not joined:
        return False
    if _HEADER_TRUNCATED_LABEL_PATTERN.search(label):
        return True
    if re.search(r"\b(?:of|and|to|from|for|with|by|in|at)$", _normalize_text(label)):
        return True
    if len(fragments) <= 2 and all(len(fragment.split()) <= 3 for fragment in fragments):
        return True
    return False


def _repair_truncated_label(label: str) -> str:
    """Repair high-confidence truncated label endings seen in annual reports."""

    repaired = _normalize_label_text(label)
    repairs = [
        (r"\bnet assets\s*\(\s*100$", "Net assets (100%)"),
        (r"\bnet assets\s*\(\s*100\s*%$", "Net assets (100%)"),
    ]
    for pattern, replacement in repairs:
        repaired = re.sub(pattern, replacement, repaired, flags=re.IGNORECASE)
    return _normalize_label_text(repaired)


def _should_complete_with_unit_fragment(label: str, unit_fragment: str) -> bool:
    """Return whether an adjacent unit fragment should complete this label."""

    normalized_unit = _normalize_unit_fragment_context(unit_fragment)
    if not normalized_unit:
        return False
    if _unit_context_already_present(label, normalized_unit):
        return False
    return bool(
        label.endswith("(")
        or re.search(r"\(\s*\d+$", label)
        or (
            "(" in label
            and ")" not in label
            and (
                normalized_unit.startswith("%")
                or normalized_unit.startswith(")")
            )
        )
    )


def _repair_remaining_fragment_spacing(label: str) -> str:
    """Repair residual intra-word spaces not covered by the degluing pass."""

    repaired = _normalize_label_text(label)
    for word in _FRAGMENTATION_CLEANUP_WORDS:
        for split_index in range(1, len(word)):
            if len(word) <= 3 and word != "and":
                continue
            left = re.escape(word[:split_index])
            right = re.escape(word[split_index:])
            pattern = re.compile(rf"\b{left}\s+{right}\b", re.IGNORECASE)
            repaired = pattern.sub(
                lambda match, canonical=word: _apply_fragment_word_case(
                    canonical,
                    match.group(0),
                ),
                repaired,
            )
    return _normalize_label_text(repaired)


def _apply_fragment_word_case(canonical_word: str, observed_fragment: str) -> str:
    """Return a repaired word using the observed fragment's casing."""

    compacted = re.sub(r"\s+", "", observed_fragment)
    if compacted.isupper() and len(canonical_word) > 2:
        return canonical_word.upper()
    if compacted[:1].isupper():
        return canonical_word.capitalize()
    return canonical_word


_NOTE_UNIT_PATTERN = re.compile(
    r"(?:\bpkr\b|\brs\.?\b|\busd\b|\beur\b|\bgbp\b|\brupees?\b|"
    r"\bruppees\b|\bamounts?\b|"
    r"\bthousand\b|\bthousands\b|\bmillion\b|\bmillions\b|\bmn\b|"
    r"\bbillion\b|\bbillions\b|\bbn\b|(?<!\d)[`'’‘]?0{2,3}s?\b|"
    r"\bin\s+[`'’‘]?0{1,3})",
    re.IGNORECASE,
)
_NOTE_REFERENCE_PATTERN = re.compile(
    r"^(?:note\s*)?\d+(?:\.\d+)*$",
    re.IGNORECASE,
)
_NOTE_HEADER_LABELS = {
    "note",
    "notes",
}
_NOTE_FORMATTING_LABELS = {
    "do",
    "-do-",
    "--do--",
    "---do---",
    "----do----",
}
_NOTE_CONTINUATION_PATTERN = re.compile(
    r"\b(continued|brought forward|carried forward|same as above|"
    r"balance b/f|balance c/f|b/f|c/f)\b",
    re.IGNORECASE,
)
_NOTE_LEGITIMATE_DISCLOSURE_PATTERN = re.compile(
    r"\b(managerial remuneration|number of persons|ordinary shares|"
    r"share counts?|employee counts?|employees?|persons?|shares?)\b",
    re.IGNORECASE,
)
_NOTE_SUBTOTAL_PATTERN = re.compile(
    r"\b(total|subtotal|sub total|net assets|net liabilities|closing balance|"
    r"opening balance|balance as at|balance at|carrying amount|"
    r"written down value)\b",
    re.IGNORECASE,
)


def _note_row_filtering_reason(label: str) -> str | None:
    """Return a reason when a reconstructed/deglued label is note metadata."""

    text = _normalize_label_text(label)
    if not text:
        return "formatting_only_row"

    normalized = _normalize_text(text)
    compacted = normalized.replace(" ", "")
    if normalized in _NOTE_HEADER_LABELS:
        return "note_header"
    if compacted in _NOTE_FORMATTING_LABELS or _is_ditto_marker(text):
        return "continuation_marker"
    if _NOTE_REFERENCE_PATTERN.fullmatch(text.strip()) is not None:
        return "standalone_note_reference"
    if _NOTE_CONTINUATION_PATTERN.search(text):
        return "continuation_marker"
    if _is_formatting_only_label(text):
        return "formatting_only_row"
    if _is_note_unit_row(text):
        return "unit_row"
    return None


def _is_ditto_marker(label: str) -> bool:
    """Return whether a label is only a ditto/continuation marker."""

    compacted = _normalize_text(label).replace(" ", "")
    return "do" in compacted and set(compacted) <= {"d", "o", "-"}


def _is_formatting_only_label(label: str) -> bool:
    """Return whether a label carries no metric text."""

    return re.fullmatch(r"[\W_]+", label.strip()) is not None


def _is_note_unit_row(label: str) -> bool:
    """Return whether a label is a unit/header row rather than a metric."""

    text = _normalize_label_text(label)
    if not _NOTE_UNIT_PATTERN.search(text):
        return False
    if _NOTE_LEGITIMATE_DISCLOSURE_PATTERN.search(text):
        return False
    if _NOTE_SUBTOTAL_PATTERN.search(text):
        return False

    lower_text = text.lower().strip()
    words = re.findall(r"[A-Za-z]+", text)
    normalized_words = {
        word.lower()
        for word in words
        if word.lower() not in {"in", "of", "and", "the", "as", "at"}
    }
    unit_words = {
        "pkr",
        "rs",
        "usd",
        "eur",
        "gbp",
        "rupees",
        "rupee",
        "ruppees",
        "amount",
        "amounts",
        "thousand",
        "thousands",
        "million",
        "millions",
        "mn",
        "billion",
        "billions",
        "bn",
    }
    if (
        text.startswith("(")
        or re.match(r"(?i)^(pkr|rs\.?|rupees?|ruppees|amounts?)\b", lower_text)
    ):
        return True

    return bool(normalized_words) and normalized_words <= unit_words


_NOTE_CONTEXT_TABLE_TYPE_HINTS = {
    "aging",
    "borrowings",
    "capital_work",
    "cash_and_bank",
    "contingent",
    "credit_quality",
    "debt",
    "deferred",
    "deposits",
    "disclosure",
    "expense",
    "expenses",
    "fair_value",
    "financial_assets",
    "financial_instruments",
    "fixed_assets",
    "intangible",
    "inventory",
    "lease",
    "liabilities",
    "loan",
    "movement",
    "mutual_fund",
    "note",
    "notes",
    "payables",
    "prepayments",
    "provision",
    "receivables",
    "related_party",
    "remuneration",
    "schedule",
    "short_term",
    "stock",
    "tax",
    "taxation",
}
_NOTE_CONTEXT_HEADER_PATTERN = re.compile(
    r"\b(breakup|claims?|classification|comprise|comprises|details?|"
    r"during the year|following|in respect of|movement|schedule|set out)\b",
    re.IGNORECASE,
)
_NOTE_CONTEXT_DEPENDENT_PATTERNS = (
    (
        "total_label",
        re.compile(r"^(?:total|subtotal|sub total)$", re.IGNORECASE),
    ),
    (
        "generic_note_label",
        re.compile(
            r"^(?:others?|other|current|non[- ]?current|less than .+|"
            r"more than .+|neither past due nor impaired)$",
            re.IGNORECASE,
        ),
    ),
    (
        "movement_label",
        re.compile(
            r"^(?:opening balance|closing balance|additions?|disposals?|"
            r"transfers?|adjustments?|charge for the year|for the year|"
            r"written off|balance at .+|balance as at .+|balance b/f|"
            r"balance c/f|b/f|c/f)$",
            re.IGNORECASE,
        ),
    ),
    (
        "short_disclosure_label",
        re.compile(
            r"^(?:number of persons|number of employees|number of shares|"
            r"less than pkr .+ each|less than rs .+ each)$",
            re.IGNORECASE,
        ),
    ),
)
_NOTE_CONTEXT_STANDALONE_LABELS = {
    "bank balances",
    "cash and bank balances",
    "cash and cash equivalents",
    "property plant and equipment",
}


def _is_note_context_table(table_type: str, rows: RawTable) -> bool:
    """Return whether note context inheritance should be considered."""

    normalized_type = _normalize_key(table_type)
    primary_statement_types = {
        "balance_sheet",
        "cash_flow_statement",
        "comprehensive_income_statement",
        "income_statement",
        "profit_and_loss",
        "statement_of_cash_flows",
        "statement_of_changes_in_equity",
        "statement_of_comprehensive_income",
        "statement_of_financial_position",
        "statement_of_profit_or_loss",
    }
    if normalized_type in primary_statement_types:
        return False
    if any(hint in normalized_type for hint in _NOTE_CONTEXT_TABLE_TYPE_HINTS):
        return True

    table_text = _normalized_table_text(rows)
    return bool(
        _NOTE_CONTEXT_HEADER_PATTERN.search(table_text)
        or _contains_phrase(table_text, "note")
        or _contains_phrase(table_text, "notes")
    )


def _update_note_context_from_header_row(
    context_stack: _NoteContextStack,
    *,
    label: str,
    row_index: int,
    header_row_index: int | None,
    table_type: str,
) -> None:
    """Update active note context from a non-value row."""

    context_label = _normalize_label_text(label)
    if not _is_usable_context_label(context_label):
        return
    if _context_inheritance_reason(context_label) is not None:
        return

    if _is_note_header_context_label(
        context_label,
        row_index=row_index,
        header_row_index=header_row_index,
        table_type=table_type,
    ):
        context_stack.active_note_header = context_label
        context_stack.active_section_header = None
        context_stack.active_parent_label = None
        return

    context_stack.active_section_header = context_label
    context_stack.active_parent_label = None


def _update_note_context_from_metric_row(
    context_stack: _NoteContextStack,
    *,
    label: str,
    inherited_label: _ContextInheritedLabel,
) -> None:
    """Track the latest complete metric row as parent context."""

    if inherited_label.changed:
        return
    if not _is_usable_context_label(label):
        return
    if _context_inheritance_reason(label) is not None:
        return
    context_stack.active_parent_label = _normalize_label_text(label)


def _inherit_note_context(
    label: str,
    context_stack: _NoteContextStack,
    *,
    broad_note_context: bool = False,
) -> _ContextInheritedLabel:
    """Return a label enriched with active note context when appropriate."""

    normalized_label = _normalize_label_text(label)
    reason = _context_inheritance_reason(normalized_label)
    if (
        reason is None
        and broad_note_context
        and _has_inheritance_context(context_stack)
        and _is_context_sensitive_note_metric(normalized_label)
    ):
        reason = "note_context_label"
    if reason is None:
        return _ContextInheritedLabel(
            original_label=normalized_label,
            inherited_label=normalized_label,
        )

    context_source, inherited_context = _select_inherited_context(
        reason,
        context_stack,
    )
    if inherited_context is None or context_source is None:
        return _ContextInheritedLabel(
            original_label=normalized_label,
            inherited_label=normalized_label,
        )
    if _context_already_present(
        label=normalized_label,
        inherited_context=inherited_context,
    ):
        return _ContextInheritedLabel(
            original_label=normalized_label,
            inherited_label=normalized_label,
        )

    return _ContextInheritedLabel(
        original_label=normalized_label,
        inherited_label=_normalize_label_text(
            f"{inherited_context} - {normalized_label}",
        ),
        inherited_context=inherited_context,
        context_source=context_source,
        reconstruction_reason=reason,
    )


def _context_inheritance_reason(label: str) -> str | None:
    """Return why a label should inherit context, if applicable."""

    normalized = _normalize_text(label)
    if not normalized:
        return None
    for reason, pattern in _NOTE_CONTEXT_DEPENDENT_PATTERNS:
        if pattern.fullmatch(normalized):
            return reason
    return None


def _select_inherited_context(
    reason: str,
    context_stack: _NoteContextStack,
) -> tuple[str | None, str | None]:
    """Return the best available context source for a dependent note label."""

    if reason == "generic_note_label":
        candidates = (
            ("parent_row", context_stack.active_parent_label),
            ("section_header", context_stack.active_section_header),
            ("note_header", context_stack.active_note_header),
        )
    elif reason == "note_context_label":
        candidates = (
            ("section_header", context_stack.active_section_header),
            ("note_header", context_stack.active_note_header),
        )
    elif reason == "total_label":
        candidates = (
            ("section_header", context_stack.active_section_header),
            ("note_header", context_stack.active_note_header),
        )
    else:
        candidates = (
            ("section_header", context_stack.active_section_header),
            ("parent_row", context_stack.active_parent_label),
            ("note_header", context_stack.active_note_header),
        )

    for source, candidate in candidates:
        if _is_usable_context_label(candidate or ""):
            return source, candidate
    return None, None


def _has_inheritance_context(context_stack: _NoteContextStack) -> bool:
    """Return whether the stack has any context available for inheritance."""

    return any(
        _is_usable_context_label(candidate or "")
        for candidate in (
            context_stack.active_parent_label,
            context_stack.active_section_header,
            context_stack.active_note_header,
        )
    )


def _is_context_sensitive_note_metric(label: str) -> bool:
    """Return whether a note metric needs context to stay interpretable."""

    normalized = _normalize_text(label)
    words = normalized.split()
    if not words:
        return False
    if normalized in _NOTE_CONTEXT_STANDALONE_LABELS:
        return False
    if len(words) <= 4:
        return True
    return bool(
        re.search(
            r"\b(accrued|deposits?|gain|levy|loss|other|prepayments?|"
            r"receivables?|tax|taxation)\b",
            normalized,
        )
        and len(words) <= 7
    )


def _is_note_header_context_label(
    label: str,
    *,
    row_index: int,
    header_row_index: int | None,
    table_type: str,
) -> bool:
    """Return whether a non-value row should be treated as the note header."""

    if header_row_index is not None and row_index < header_row_index:
        return True
    normalized_label = _normalize_text(label)
    if _NOTE_CONTEXT_HEADER_PATTERN.search(normalized_label):
        return True
    if "note" in _normalize_key(table_type) and len(normalized_label.split()) >= 7:
        return True
    return False


def _is_usable_context_label(label: str) -> bool:
    """Return whether a label is safe to use as inherited context."""

    text = _normalize_label_text(label)
    if not text or _note_row_filtering_reason(text) is not None:
        return False
    normalized = _normalize_text(text)
    words = normalized.split()
    if normalized.startswith("for the year ended"):
        return False
    if normalized.startswith("particulars "):
        return False
    if normalized.startswith("represent ") or " has been" in normalized:
        return False
    if "if any" in normalized:
        return False
    if words:
        short_word_count = sum(1 for word in words if len(word) <= 2)
        if short_word_count / len(words) > 0.4:
            return False
    if len(words) > 8 and _NOTE_CONTEXT_HEADER_PATTERN.search(normalized) is None:
        return False
    if len(words) > 14:
        return False
    if len(words) == 1 and normalized not in {"taxation", "borrowings"}:
        return False
    return True


def _context_already_present(*, label: str, inherited_context: str) -> bool:
    """Return whether applying the context would only repeat the label."""

    normalized_label = _normalize_text(label)
    normalized_context = _normalize_text(inherited_context)
    if not normalized_label or not normalized_context:
        return True
    return (
        normalized_label == normalized_context
        or _contains_phrase(normalized_context, normalized_label)
        or _contains_phrase(normalized_label, normalized_context)
    )


_HEADER_INHERITANCE_UNIT_PATTERN = re.compile(
    r"\b(pkr|rs\.?|usd|rupees?|mn|million|times|percent|mt|each)\b|%",
    re.IGNORECASE,
)
_HEADER_SECTION_PATTERN = re.compile(
    r"\b(assets?|capital|cash flows?|current liabilities|financial ratios|"
    r"key ratios|liabilities|non[- ]?financial ratios|ratio|share capital|"
    r"turnover)\b",
    re.IGNORECASE,
)
_HEADER_CONTEXT_LABEL_PATTERN = re.compile(
    r"\b(company|corporation|holdings?|industries|limited|ltd|power|"
    r"resources|associates?|subsidiar(?:y|ies)|quoted|unquoted)\b",
    re.IGNORECASE,
)
_HEADER_CONTEXT_DEPENDENT_PATTERN = re.compile(
    r"^(?:current portion\b.*|investment at cost$|ordinary shares?.*each$|"
    r".*\btimes$|.*\bpercent$|.*%.*|.*\brupees?$|.*\bmn$|.*\bmt$)",
    re.IGNORECASE,
)
_HEADER_TRUNCATED_LABEL_PATTERN = re.compile(
    r"(?:\([^)]*$|\b(?:i\s+nc|th\s+e|bas|provi|accumula|unalloca|rema)$|\d+\s*$)",
    re.IGNORECASE,
)


def _update_header_context_from_row(
    context_stack: _HeaderContextStack,
    *,
    label: str,
    row: Sequence[str],
    row_index: int,
    header_row_index: int | None,
    metric_value_count: int,
    table_type: str,
    inherited_label: _HeaderInheritedLabel | None = None,
) -> None:
    """Update active table/header/unit context from an extracted row."""

    if inherited_label is not None and inherited_label.changed:
        return

    row_context = _normalize_label_text(label)
    if not _is_usable_header_context(row_context):
        return

    if metric_value_count > 0:
        return

    unit_context = _unit_context_from_label(row_context)
    if unit_context is not None:
        context_stack.active_unit = unit_context

    if _is_table_section_context(row_context, table_type=table_type):
        context_stack.active_section = row_context
        context_stack.active_header = row_context
        return

    if _is_table_header_context(
        row_context,
        row=row,
        row_index=row_index,
        header_row_index=header_row_index,
        table_type=table_type,
    ):
        context_stack.active_header = row_context


def _inherit_header_context(
    label: str,
    *,
    row: Sequence[str],
    label_index: int,
    year_columns: dict[int, int],
    context_stack: _HeaderContextStack,
) -> _HeaderInheritedLabel:
    """Return a fragmented label enriched with active header/unit context."""

    normalized_label = _normalize_label_text(label)
    row_unit_context = _row_unit_context_fragment(
        row=row,
        label_index=label_index,
        year_columns=year_columns,
    )
    if row_unit_context is not None:
        completed = _complete_label_with_unit_fragment(
            normalized_label,
            row_unit_context,
        )
        if completed != normalized_label:
            return _HeaderInheritedLabel(
                original_label=normalized_label,
                inherited_label=completed,
                inherited_header=row_unit_context,
                inheritance_source="unit_context",
                reconstruction_reason="unit_fragment_completion",
            )

    reason = _header_inheritance_reason(normalized_label)
    if reason is None:
        return _HeaderInheritedLabel(
            original_label=normalized_label,
            inherited_label=normalized_label,
        )

    inheritance_source, inherited_header = _select_header_context(
        reason,
        context_stack,
    )
    if inheritance_source is None or inherited_header is None:
        return _HeaderInheritedLabel(
            original_label=normalized_label,
            inherited_label=normalized_label,
        )
    if _context_already_present(
        label=normalized_label,
        inherited_context=inherited_header,
    ):
        return _HeaderInheritedLabel(
            original_label=normalized_label,
            inherited_label=normalized_label,
        )

    return _HeaderInheritedLabel(
        original_label=normalized_label,
        inherited_label=_normalize_label_text(
            f"{inherited_header} - {normalized_label}",
        ),
        inherited_header=inherited_header,
        inheritance_source=inheritance_source,
        reconstruction_reason=reason,
    )


def _header_inheritance_reason(label: str) -> str | None:
    """Return why a fragmented label should inherit header context."""

    normalized = _normalize_text(label)
    if not normalized:
        return None
    if re.search(r"\(\s*\d+\s*%\)", label):
        return None
    if _HEADER_TRUNCATED_LABEL_PATTERN.search(label):
        return "truncated_label_completion"
    if normalized.startswith("current portion"):
        return "section_context_inheritance"
    if "ordinary shares" in normalized and "each" in normalized:
        return "security_header_inheritance"
    if normalized == "investment at cost":
        return "table_header_inheritance"
    if _HEADER_CONTEXT_DEPENDENT_PATTERN.match(label):
        return "unit_context_inheritance"
    return None


def _select_header_context(
    reason: str,
    context_stack: _HeaderContextStack,
) -> tuple[str | None, str | None]:
    """Return the best available header context for a fragmented label."""

    if reason == "unit_context_inheritance":
        candidates = (
            ("table_section_context", context_stack.active_section),
            ("table_header_context", context_stack.active_header),
            ("unit_context", context_stack.active_unit),
        )
    elif reason == "security_header_inheritance":
        candidates = (
            ("table_header_context", context_stack.active_header),
            ("table_section_context", context_stack.active_section),
            ("unit_context", context_stack.active_unit),
        )
    else:
        candidates = (
            ("table_section_context", context_stack.active_section),
            ("table_header_context", context_stack.active_header),
            ("unit_context", context_stack.active_unit),
        )

    for source, candidate in candidates:
        if _is_usable_header_context(candidate or ""):
            return source, candidate
    return None, None


def _row_unit_context_fragment(
    *,
    row: Sequence[str],
    label_index: int,
    year_columns: dict[int, int],
) -> str | None:
    """Return an adjacent unit fragment excluded from label reconstruction."""

    fragments: list[str] = []
    for column_index in range(label_index + 1, len(row)):
        if column_index in year_columns:
            break
        text = str(row[column_index]).strip()
        if not text:
            continue
        if CamelotTableExtractor._is_note_number_cell(text):
            break
        if CamelotTableExtractor._parse_metric_value(text) is not None:
            break
        if _is_unit_fragment_cell(text):
            fragments.append(text)
            continue
        if fragments:
            break
        if re.search(r"[A-Za-z]", text):
            continue
        break

    if not fragments:
        return None
    return _normalize_label_text("".join(fragments))


def _is_unit_fragment_cell(text: str) -> bool:
    """Return whether a cell is a unit fragment for an adjacent label."""

    stripped = str(text).strip()
    if not stripped:
        return False
    return (
        stripped in {"%)", "%", "(%)"}
        or bool(_HEADER_INHERITANCE_UNIT_PATTERN.search(stripped))
        and CamelotTableExtractor._parse_metric_value(stripped) is None
    )


def _complete_label_with_unit_fragment(label: str, unit_fragment: str) -> str:
    """Complete a label using an adjacent unit fragment."""

    normalized_unit = _normalize_unit_fragment_context(unit_fragment)
    if not normalized_unit:
        return label
    if _unit_context_already_present(label, normalized_unit):
        return label
    if "%" in normalized_unit and "%" in label:
        return label
    if normalized_unit in {"%)", "%", "(%)"} and re.search(r"\(\s*\d+\s*%\)", label):
        return label
    if label.endswith("(") or re.search(r"\(\s*\d+$", label):
        return _normalize_label_text(f"{label}{normalized_unit}")
    if normalized_unit.startswith(")") or normalized_unit.startswith("%"):
        return _normalize_label_text(f"{label}{normalized_unit}")
    if _contains_phrase(_normalize_text(label), normalized_unit):
        return label
    return _normalize_label_text(f"{label} {normalized_unit}")


def _unit_context_already_present(label: str, normalized_unit: str) -> bool:
    """Return whether a unit fragment is already represented in the label."""

    label_text = _normalize_text(label)
    unit_text = _normalize_text(normalized_unit)
    if not unit_text:
        return False
    unit_groups = (
        {"percent", "%"},
        {"rupees", "rupee", "pkr", "rs"},
        {"times"},
        {"million", "mn"},
        {"thousand", "000"},
        {"each"},
        {"mt"},
    )
    for group in unit_groups:
        unit_has_group = any(token in unit_text for token in group)
        label_has_group = any(token in label_text for token in group)
        if unit_has_group and label_has_group:
            return True
    return False


def _normalize_unit_fragment_context(unit_fragment: str) -> str:
    """Normalize adjacent unit fragments before completion checks."""

    normalized_unit = _normalize_label_text(unit_fragment)
    normalized_unit = re.sub(
        r"^(?:f|o\s*f)\s+(?=pkr|rs\.?|usd|rupees?)",
        "of ",
        normalized_unit,
        flags=re.IGNORECASE,
    )
    return normalized_unit


def _unit_context_from_label(label: str) -> str | None:
    """Return unit context embedded in a header or metric label."""

    text = _normalize_label_text(label)
    match = _HEADER_INHERITANCE_UNIT_PATTERN.search(text)
    if match is None:
        return None
    if len(_normalize_text(text).split()) <= 6:
        return text
    return match.group(0)


def _is_table_section_context(label: str, *, table_type: str) -> bool:
    """Return whether a non-value row can act as table section context."""

    normalized = _normalize_text(label)
    if not normalized:
        return False
    if _HEADER_SECTION_PATTERN.search(normalized):
        return True
    normalized_type = _normalize_key(table_type)
    if "ratio" in normalized_type and "ratio" in normalized:
        return True
    return False


def _is_table_header_context(
    label: str,
    *,
    row: Sequence[str],
    row_index: int,
    header_row_index: int | None,
    table_type: str,
) -> bool:
    """Return whether a non-value row can act as header context."""

    normalized = _normalize_text(label)
    if not normalized:
        return False
    if header_row_index is not None and row_index < header_row_index:
        return True
    if _HEADER_CONTEXT_LABEL_PATTERN.search(normalized):
        return True
    if _is_table_section_context(label, table_type=table_type):
        return True
    non_empty_cells = [str(cell).strip() for cell in row if str(cell).strip()]
    return len(non_empty_cells) <= 3 and 1 < len(normalized.split()) <= 8


def _is_usable_header_context(label: str) -> bool:
    """Return whether a label is safe to use as header inheritance context."""

    text = _normalize_label_text(label)
    if not text or _note_row_filtering_reason(text) is not None:
        return False
    normalized = _normalize_text(text)
    words = normalized.split()
    if not words:
        return False
    if normalized.startswith("metric "):
        return False
    if normalized.startswith(("except ", "excluding ")):
        return False
    if re.fullmatch(r"(?:19|20)\d{2}(?:\s+(?:19|20)\d{2})*", normalized):
        return False
    if normalized.startswith("for the year ended"):
        return False
    if len(words) > 12:
        return False
    short_word_count = sum(1 for word in words if len(word) <= 2)
    if len(words) > 2 and short_word_count / len(words) > 0.5:
        return False
    return True


def _detected_counts_by_page(
    table_detection_result: TableDetectionResult | None,
) -> dict[int, int]:
    if table_detection_result is None:
        return {}
    return {
        detected_page.page_number: detected_page.tables_detected
        for detected_page in table_detection_result.detected_pages
    }


def _metric_labels(rows: RawTable) -> list[str]:
    """Return detected metric label cells from raw rows."""

    labels: list[str] = []
    for row in rows:
        label_index = CamelotTableExtractor._metric_label_index(row)
        if label_index is not None:
            labels.append(row[label_index].strip())
    return labels


def _is_numeric_only_table(rows: RawTable) -> bool:
    """Return whether a table has numbers but no text metric labels."""

    if _metric_labels(rows):
        return False
    return any(
        CamelotTableExtractor._parse_metric_value(str(cell)) is not None
        for row in rows
        for cell in row
    )


def _quality_score(
    *,
    raw_tables: list[RawTable],
    year_column_count: int,
    metric_label_count: int,
    metric_value_count: int,
    numeric_only_table_count: int,
) -> float:
    """Score raw extraction usefulness for financial MetricValue generation."""

    if not raw_tables:
        return 0.0

    score = 10.0
    if numeric_only_table_count < len(raw_tables):
        score += 10.0
    if year_column_count:
        score += min(25.0, 12.5 * year_column_count)
    if metric_label_count:
        score += min(25.0, 2.0 * metric_label_count)
    if metric_value_count:
        score += min(30.0, 2.0 * metric_value_count)
    score -= min(20.0, 10.0 * numeric_only_table_count)
    return round(max(0.0, min(score, 100.0)), 2)


def _quality_log_extra(quality: _ExtractionQuality) -> dict[str, int | float]:
    """Return structured logging fields for extraction quality."""

    return {
        "quality_score": quality.quality_score,
        "year_column_count": quality.year_column_count,
        "metric_label_count": quality.metric_label_count,
        "metric_value_count": quality.metric_value_count,
        "numeric_only_table_count": quality.numeric_only_table_count,
    }


def _strategy_rank(strategy: str) -> int:
    """Return a stable preference rank used only when quality ties."""

    ranks = {
        EXTRACTION_STRATEGY_PDFPLUMBER_TEXT: 0,
        EXTRACTION_STRATEGY_PDFPLUMBER_DEFAULT: 1,
        EXTRACTION_STRATEGY_CAMELOT: 2,
    }
    return ranks.get(strategy, 99)


@dataclass(frozen=True)
class _AnalysisStyleSplit:
    """Logical table split identified inside an analysis-style physical table."""

    rows: RawTable
    logical_type: str
    split_reason: str


_ANALYSIS_SPLIT_REASON = (
    "analysis_section_markers_with_repeated_year_headers_and_subtotal_rows"
)
_ANALYSIS_PRIMARY_TABLE_TYPES = {
    "balance_sheet",
    "statement_of_financial_position",
    "income_statement",
    "profit_and_loss",
    "statement_of_profit_or_loss",
}


def _is_analysis_style_classification(table_types: Sequence[str]) -> bool:
    """Return whether a page classification matches the proven split pattern."""

    normalized_types = {_normalize_key(table_type) for table_type in table_types}
    return (
        bool(normalized_types & _ANALYSIS_PRIMARY_TABLE_TYPES)
        and "vertical_analysis" in normalized_types
        and "horizontal_analysis" in normalized_types
    )


def _primary_analysis_table_type(table_types: Sequence[str]) -> str | None:
    """Return the primary statement type in an analysis-style classification."""

    for table_type in table_types:
        if _normalize_key(table_type) in _ANALYSIS_PRIMARY_TABLE_TYPES:
            return table_type
    return None


def _split_analysis_style_table(
    *,
    rows: RawTable,
    primary_table_type: str,
) -> list[_AnalysisStyleSplit]:
    """Split only proven primary + vertical/horizontal analysis tables."""

    if not rows or not _analysis_subtotal_row_indexes(rows):
        return []

    markers: list[tuple[int, str]] = [(0, primary_table_type)]
    vertical_seen = False
    horizontal_seen = False
    for row_index, row in enumerate(rows):
        compact_text = _compact_text(_row_text(row))
        if len(_years_in_row(row)) < 2:
            continue

        if "verticalanalysis" in compact_text and not vertical_seen:
            markers.append((row_index, "vertical_analysis"))
            vertical_seen = True
        if "horizontalanalysis" in compact_text and not horizontal_seen:
            markers.append((row_index, "horizontal_analysis"))
            horizontal_seen = True

    if not vertical_seen or not horizontal_seen:
        return []

    markers = _dedupe_markers(markers)
    splits: list[_AnalysisStyleSplit] = []
    for marker_index, (start_row, logical_type) in enumerate(markers):
        end_row = (
            markers[marker_index + 1][0] - 1
            if marker_index + 1 < len(markers)
            else len(rows) - 1
        )
        split_rows = rows[start_row : end_row + 1]
        if not any(_row_text(row) for row in split_rows):
            continue
        splits.append(
            _AnalysisStyleSplit(
                rows=split_rows,
                logical_type=logical_type,
                split_reason=_ANALYSIS_SPLIT_REASON,
            )
        )
    return splits if len(splits) >= 3 else []


def _analysis_subtotal_row_indexes(rows: RawTable) -> list[int]:
    """Return subtotal rows used as a confidence signal for analysis splitting."""

    subtotal_phrases = (
        "total assets",
        "total equity",
        "total equity and liabilities",
        "total funds invested",
        "gross profit",
        "operating profit",
        "profit before taxation",
        "profit after taxation",
        "total comprehensive income",
    )
    indexes: list[int] = []
    for row_index, row in enumerate(rows):
        normalized = _normalize_text(_row_text(row))
        if any(_contains_phrase(normalized, phrase) for phrase in subtotal_phrases):
            indexes.append(row_index)
    return indexes


def _years_in_row(row: Sequence[str]) -> list[int]:
    """Return value years found in a row."""

    years: list[int] = []
    for cell in row:
        for match in re.findall(r"\b(?:19|20)\d{2}\b", str(cell)):
            years.append(int(match))
    return years


def _dedupe_markers(markers: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Deduplicate split markers by row while preserving first type."""

    result: list[tuple[int, str]] = []
    seen_rows: set[int] = set()
    for row_index, logical_type in sorted(markers, key=lambda marker: marker[0]):
        if row_index in seen_rows:
            continue
        seen_rows.add(row_index)
        result.append((row_index, logical_type))
    return result


def _raw_table_provenance_for_index(
    provenance: Sequence[_RawTableProvenance] | None,
    index: int,
) -> _RawTableProvenance:
    """Return provenance for a prepared raw table index."""

    if provenance is not None and index < len(provenance):
        return provenance[index]
    return _RawTableProvenance(source_table_index=index)


def _row_text(row: Sequence[str]) -> str:
    """Return non-empty row cells joined for boundary detection."""

    return " ".join(str(cell).strip() for cell in row if str(cell).strip())


def _compact_text(value: str) -> str:
    """Return compact lower-case alphanumeric text for fragmented headings."""

    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    """Return unique strings while preserving first occurrence order."""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _build_extraction_quality_report(
    tables: list[ExtractedTable],
) -> ExtractionQualityReport:
    """Build table and metric quality validation findings."""

    table_findings: list[SuspiciousTableFinding] = []
    confidence_distribution = {
        "0-20": 0,
        "20-40": 0,
        "40-60": 0,
        "60-80": 0,
        "80-100": 0,
    }

    missing_year_table_count = 0
    missing_label_table_count = 0
    numeric_only_table_count = 0
    unclassified_table_count = 0

    for table in tables:
        finding = _table_quality_finding(table)
        _increment_quality_bucket(confidence_distribution, finding.quality_score)
        if finding.year_column_count == 0:
            missing_year_table_count += 1
        if finding.metric_label_count == 0:
            missing_label_table_count += 1
        if finding.numeric_only:
            numeric_only_table_count += 1
        if _normalize_key(table.table_type) == UNCLASSIFIED_TABLE_TYPE:
            unclassified_table_count += 1
        if finding.reasons:
            table_findings.append(finding)

    metric_findings = _metric_quality_findings(tables)
    label_reconstruction_diagnostics = _label_reconstruction_diagnostics(tables)
    label_degluing_diagnostics = _label_degluing_diagnostics(tables)
    fragmentation_cleanup_diagnostics = _fragmentation_cleanup_diagnostics(tables)
    note_row_filtering_diagnostics = _note_row_filtering_diagnostics(tables)
    note_context_inheritance_diagnostics = _note_context_inheritance_diagnostics(
        tables,
    )
    header_inheritance_diagnostics = _header_inheritance_diagnostics(tables)
    top_suspicious_tables = sorted(
        table_findings,
        key=lambda finding: (
            -finding.suspicion_score,
            finding.page_number,
            finding.table_index,
        ),
    )[:20]
    top_suspicious_metrics = sorted(
        metric_findings,
        key=lambda finding: (
            -finding.suspicion_score,
            finding.metric,
            finding.value_year,
            finding.table_type,
        ),
    )[:20]
    duplicate_group_count = sum(
        1 for finding in metric_findings if "duplicate_metric_values" in finding.reasons
    )
    conflicting_group_count = sum(
        1 for finding in metric_findings if "conflicting_values" in finding.reasons
    )
    duplicate_value_count = sum(
        finding.occurrence_count - 1
        for finding in metric_findings
        if "duplicate_metric_values" in finding.reasons
    )

    return ExtractionQualityReport(
        tables_extracted=len(tables),
        tables_rejected=len(table_findings),
        metric_values_generated=sum(len(table.metric_values) for table in tables),
        duplicate_metric_group_count=duplicate_group_count,
        duplicate_metric_value_count=duplicate_value_count,
        conflicting_metric_group_count=conflicting_group_count,
        missing_year_table_count=missing_year_table_count,
        missing_label_table_count=missing_label_table_count,
        numeric_only_table_count=numeric_only_table_count,
        unclassified_table_count=unclassified_table_count,
        labels_reconstructed=len(label_reconstruction_diagnostics),
        metric_values_improved_by_label_reconstruction=sum(
            diagnostic.metric_values_affected
            for diagnostic in label_reconstruction_diagnostics
        ),
        labels_deglued=len(label_degluing_diagnostics),
        metric_values_improved_by_label_degluing=sum(
            diagnostic.metric_values_affected
            for diagnostic in label_degluing_diagnostics
        ),
        labels_completed=len(fragmentation_cleanup_diagnostics),
        metric_values_improved_by_fragmentation_cleanup=sum(
            diagnostic.metric_values_affected
            for diagnostic in fragmentation_cleanup_diagnostics
        ),
        note_rows_filtered=len(note_row_filtering_diagnostics),
        metric_values_removed_by_note_row_filtering=sum(
            diagnostic.metric_values_removed
            for diagnostic in note_row_filtering_diagnostics
        ),
        context_inheritances_applied=len(note_context_inheritance_diagnostics),
        metric_values_improved_by_context_inheritance=sum(
            diagnostic.metric_values_affected
            for diagnostic in note_context_inheritance_diagnostics
        ),
        header_inheritances_applied=len(header_inheritance_diagnostics),
        metric_values_improved_by_header_inheritance=sum(
            diagnostic.metric_values_affected
            for diagnostic in header_inheritance_diagnostics
        ),
        confidence_distribution=confidence_distribution,
        top_suspicious_tables=top_suspicious_tables,
        top_suspicious_metrics=top_suspicious_metrics,
        label_reconstruction_diagnostics=label_reconstruction_diagnostics,
        label_degluing_diagnostics=label_degluing_diagnostics,
        fragmentation_cleanup_diagnostics=fragmentation_cleanup_diagnostics,
        note_row_filtering_diagnostics=note_row_filtering_diagnostics,
        note_context_inheritance_diagnostics=note_context_inheritance_diagnostics,
        header_inheritance_diagnostics=header_inheritance_diagnostics,
    )


def _build_partial_extraction_quality_report(
    tables: list[ExtractedTable],
) -> ExtractionQualityReport:
    """Build minimal non-failing quality metadata after diagnostics failure."""

    return ExtractionQualityReport(
        tables_extracted=len(tables),
        metric_values_generated=sum(len(table.metric_values) for table in tables),
        unclassified_table_count=sum(
            1
            for table in tables
            if _normalize_key(table.table_type) == UNCLASSIFIED_TABLE_TYPE
        ),
        confidence_distribution={},
        top_suspicious_tables=[],
        top_suspicious_metrics=[],
        label_reconstruction_diagnostics=[],
        label_degluing_diagnostics=[],
        fragmentation_cleanup_diagnostics=[],
        note_row_filtering_diagnostics=[],
        note_context_inheritance_diagnostics=[],
        header_inheritance_diagnostics=[],
    )


def _table_quality_finding(table: ExtractedTable) -> SuspiciousTableFinding:
    """Build a quality finding for a table, with empty reasons when clean."""

    _, year_columns = CamelotTableExtractor._find_year_columns(table.rows)
    labels = _metric_labels(table.rows)
    numeric_only = _is_numeric_only_table(table.rows)
    metric_value_count = len(table.metric_values)
    quality_score = _quality_score(
        raw_tables=[table.rows],
        year_column_count=len(year_columns),
        metric_label_count=len(labels),
        metric_value_count=metric_value_count,
        numeric_only_table_count=1 if numeric_only else 0,
    )
    reasons: list[str] = []
    if not year_columns:
        reasons.append("missing_years")
    if not labels:
        reasons.append("missing_labels")
    if numeric_only:
        reasons.append("numeric_only_table")
    if _normalize_key(table.table_type) == UNCLASSIFIED_TABLE_TYPE:
        reasons.append("unclassified_table")
    if metric_value_count == 0:
        reasons.append("no_metric_values")

    suspicion_score = _table_suspicion_score(
        quality_score=quality_score,
        reasons=reasons,
    )
    return SuspiciousTableFinding(
        source_report_year=table.source_report_year,
        page_number=table.page_number,
        table_index=table.table_index,
        table_type=table.table_type,
        row_count=len(table.rows),
        column_count=max((len(row) for row in table.rows), default=0),
        quality_score=quality_score,
        suspicion_score=suspicion_score,
        year_column_count=len(year_columns),
        metric_label_count=len(labels),
        metric_value_count=metric_value_count,
        numeric_only=numeric_only,
        reasons=reasons,
    )


def _table_suspicion_score(*, quality_score: float, reasons: list[str]) -> float:
    """Return a bounded review priority score for a table."""

    score = 100 - quality_score
    reason_weights = {
        "missing_years": 20,
        "missing_labels": 20,
        "numeric_only_table": 25,
        "unclassified_table": 10,
        "no_metric_values": 15,
    }
    score += sum(reason_weights.get(reason, 0) for reason in reasons)
    return round(max(0.0, min(score, 100.0)), 2)


def _label_reconstruction_diagnostics(
    tables: list[ExtractedTable],
) -> list[LabelReconstructionDiagnostic]:
    """Return row-level diagnostics for reconstructed metric labels."""

    diagnostics: list[LabelReconstructionDiagnostic] = []
    for table in tables:
        _, year_columns = CamelotTableExtractor._find_year_columns(table.rows)
        if not year_columns:
            continue

        for row_index, row in enumerate(table.rows):
            label_index = CamelotTableExtractor._metric_label_index(row)
            if label_index is None:
                continue

            reconstructed = CamelotTableExtractor._reconstruct_metric_label(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            deglued = _deglue_label_text(reconstructed.reconstructed_label)
            completed = _cleanup_fragmented_label(
                deglued.deglued_label,
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            if (
                _note_row_filtering_reason(
                    completed.completed_label
                )
                is not None
            ):
                continue
            if not reconstructed.changed:
                continue

            metric_values_affected = _metric_value_count_for_row(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
                scale_multiplier=CamelotTableExtractor._scale_multiplier(
                    table.rows,
                ),
            )
            if metric_values_affected == 0:
                continue

            diagnostics.append(
                LabelReconstructionDiagnostic(
                    source_report_year=table.source_report_year,
                    page_number=table.page_number,
                    table_index=table.table_index,
                    table_type=table.table_type,
                    row_index=row_index,
                    original_label=reconstructed.original_label,
                    reconstructed_label=reconstructed.reconstructed_label,
                    reconstruction_confidence=reconstructed.confidence,
                    merged_cell_count=reconstructed.merged_cell_count,
                    metric_values_affected=metric_values_affected,
                    stop_reason=reconstructed.stop_reason,
                )
            )

    return diagnostics


def _label_degluing_diagnostics(
    tables: list[ExtractedTable],
) -> list[LabelDegluingDiagnostic]:
    """Return row-level diagnostics for labels cleaned by degluing."""

    diagnostics: list[LabelDegluingDiagnostic] = []
    for table in tables:
        _, year_columns = CamelotTableExtractor._find_year_columns(table.rows)
        if not year_columns:
            continue

        scale_multiplier = CamelotTableExtractor._scale_multiplier(table.rows)
        for row_index, row in enumerate(table.rows):
            label_index = CamelotTableExtractor._metric_label_index(row)
            if label_index is None:
                continue

            reconstructed = CamelotTableExtractor._reconstruct_metric_label(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            deglued = _deglue_label_text(reconstructed.reconstructed_label)
            completed = _cleanup_fragmented_label(
                deglued.deglued_label,
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            if _note_row_filtering_reason(completed.completed_label) is not None:
                continue
            if not deglued.changed:
                continue

            metric_values_affected = _metric_value_count_for_row(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
                scale_multiplier=scale_multiplier,
            )
            if metric_values_affected == 0:
                continue

            diagnostics.append(
                LabelDegluingDiagnostic(
                    source_report_year=table.source_report_year,
                    page_number=table.page_number,
                    table_index=table.table_index,
                    table_type=table.table_type,
                    row_index=row_index,
                    original_label=deglued.original_label,
                    deglued_label=deglued.deglued_label,
                    degluing_confidence=deglued.confidence,
                    rules_applied=list(deglued.rules_applied),
                    metric_values_affected=metric_values_affected,
                )
            )

    return diagnostics


def _fragmentation_cleanup_diagnostics(
    tables: list[ExtractedTable],
) -> list[FragmentationCleanupDiagnostic]:
    """Return diagnostics for labels completed by final fragmentation cleanup."""

    diagnostics: list[FragmentationCleanupDiagnostic] = []
    for table in tables:
        _, year_columns = CamelotTableExtractor._find_year_columns(table.rows)
        if not year_columns:
            continue

        scale_multiplier = CamelotTableExtractor._scale_multiplier(table.rows)
        for row_index, row in enumerate(table.rows):
            label_index = CamelotTableExtractor._metric_label_index(row)
            if label_index is None:
                continue

            reconstructed = CamelotTableExtractor._reconstruct_metric_label(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            deglued = _deglue_label_text(reconstructed.reconstructed_label)
            completed = _cleanup_fragmented_label(
                deglued.deglued_label,
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            if _note_row_filtering_reason(completed.completed_label) is not None:
                continue
            if not completed.changed:
                continue

            metric_values_affected = _metric_value_count_for_row(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
                scale_multiplier=scale_multiplier,
            )
            if metric_values_affected == 0:
                continue

            diagnostics.append(
                FragmentationCleanupDiagnostic(
                    source_report_year=table.source_report_year,
                    page_number=table.page_number,
                    table_index=table.table_index,
                    table_type=table.table_type,
                    row_index=row_index,
                    original_label=completed.original_label,
                    completed_label=completed.completed_label,
                    reconstruction_reason=", ".join(
                        completed.reconstruction_reason,
                    )
                    or "fragmentation_cleanup",
                    source_cells=list(completed.source_cells),
                    completion_source=", ".join(completed.completion_source)
                    or "fragmentation_cleanup",
                    metric_values_affected=metric_values_affected,
                )
            )

    return diagnostics


def _note_row_filtering_diagnostics(
    tables: list[ExtractedTable],
) -> list[NoteRowFilteringDiagnostic]:
    """Return row-level diagnostics for note rows filtered as non-metrics."""

    diagnostics: list[NoteRowFilteringDiagnostic] = []
    for table in tables:
        _, year_columns = CamelotTableExtractor._find_year_columns(table.rows)
        if not year_columns:
            continue

        scale_multiplier = CamelotTableExtractor._scale_multiplier(table.rows)
        for row_index, row in enumerate(table.rows):
            label_index = CamelotTableExtractor._metric_label_index(row)
            if label_index is None:
                continue

            reconstructed = CamelotTableExtractor._reconstruct_metric_label(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            deglued = _deglue_label_text(reconstructed.reconstructed_label)
            completed = _cleanup_fragmented_label(
                deglued.deglued_label,
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            filtering_reason = _note_row_filtering_reason(completed.completed_label)
            if filtering_reason is None:
                continue

            metric_values_removed = _metric_value_count_for_row(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
                scale_multiplier=scale_multiplier,
            )
            if metric_values_removed == 0:
                continue

            diagnostics.append(
                NoteRowFilteringDiagnostic(
                    source_report_year=table.source_report_year,
                    page_number=table.page_number,
                    table_index=table.table_index,
                    table_type=table.table_type,
                    row_index=row_index,
                    label=completed.completed_label,
                    filtering_reason=filtering_reason,
                    metric_values_removed=metric_values_removed,
                )
            )

    return diagnostics


def _note_context_inheritance_diagnostics(
    tables: list[ExtractedTable],
) -> list[NoteContextInheritanceDiagnostic]:
    """Return diagnostics for note labels enriched from context stack."""

    diagnostics: list[NoteContextInheritanceDiagnostic] = []
    for table in tables:
        header_row_index, year_columns = CamelotTableExtractor._find_year_columns(
            table.rows,
        )
        if not year_columns or not _is_note_context_table(table.table_type, table.rows):
            continue

        scale_multiplier = CamelotTableExtractor._scale_multiplier(table.rows)
        context_stack = _NoteContextStack()
        for row_index, row in enumerate(table.rows):
            if row_index == header_row_index:
                continue

            label_index = CamelotTableExtractor._metric_label_index(row)
            if label_index is None:
                continue

            reconstructed = CamelotTableExtractor._reconstruct_metric_label(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            deglued = _deglue_label_text(reconstructed.reconstructed_label)
            label = _cleanup_fragmented_label(
                deglued.deglued_label,
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            ).completed_label
            if _note_row_filtering_reason(label) is not None:
                continue

            metric_values_affected = _metric_value_count_for_row(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
                scale_multiplier=scale_multiplier,
            )
            if metric_values_affected == 0:
                _update_note_context_from_header_row(
                    context_stack,
                    label=label,
                    row_index=row_index,
                    header_row_index=header_row_index,
                    table_type=table.table_type,
                )
                continue

            inherited_label = _inherit_note_context(
                label,
                context_stack,
                broad_note_context=True,
            )
            if inherited_label.changed:
                diagnostics.append(
                    NoteContextInheritanceDiagnostic(
                        source_report_year=table.source_report_year,
                        page_number=table.page_number,
                        table_index=table.table_index,
                        table_type=table.table_type,
                        row_index=row_index,
                        original_label=inherited_label.original_label,
                        inherited_label=inherited_label.inherited_label,
                        inherited_context=inherited_label.inherited_context or "",
                        context_source=inherited_label.context_source or "",
                        reconstruction_reason=(
                            inherited_label.reconstruction_reason or ""
                        ),
                        metric_values_affected=metric_values_affected,
                    )
                )

            _update_note_context_from_metric_row(
                context_stack,
                label=inherited_label.original_label,
                inherited_label=inherited_label,
            )

    return diagnostics


def _header_inheritance_diagnostics(
    tables: list[ExtractedTable],
) -> list[HeaderInheritanceDiagnostic]:
    """Return diagnostics for labels enriched from table/header context."""

    diagnostics: list[HeaderInheritanceDiagnostic] = []
    for table in tables:
        header_row_index, year_columns = CamelotTableExtractor._find_year_columns(
            table.rows,
        )
        if not year_columns:
            continue

        scale_multiplier = CamelotTableExtractor._scale_multiplier(table.rows)
        note_context_stack = _NoteContextStack()
        header_context_stack = _HeaderContextStack()
        use_note_context = _is_note_context_table(table.table_type, table.rows)
        for row_index, row in enumerate(table.rows):
            if row_index == header_row_index:
                _update_header_context_from_row(
                    header_context_stack,
                    label=_row_text(row),
                    row=row,
                    row_index=row_index,
                    header_row_index=header_row_index,
                    metric_value_count=0,
                    table_type=table.table_type,
                )
                continue

            label_index = CamelotTableExtractor._metric_label_index(row)
            if label_index is None:
                continue

            reconstructed = CamelotTableExtractor._reconstruct_metric_label(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            )
            deglued = _deglue_label_text(reconstructed.reconstructed_label)
            label = _cleanup_fragmented_label(
                deglued.deglued_label,
                row=row,
                label_index=label_index,
                year_columns=year_columns,
            ).completed_label
            if _note_row_filtering_reason(label) is not None:
                continue

            metric_values_affected = _metric_value_count_for_row(
                row=row,
                label_index=label_index,
                year_columns=year_columns,
                scale_multiplier=scale_multiplier,
            )
            if metric_values_affected == 0:
                _update_header_context_from_row(
                    header_context_stack,
                    label=label,
                    row=row,
                    row_index=row_index,
                    header_row_index=header_row_index,
                    metric_value_count=metric_values_affected,
                    table_type=table.table_type,
                )
                if use_note_context:
                    _update_note_context_from_header_row(
                        note_context_stack,
                        label=label,
                        row_index=row_index,
                        header_row_index=header_row_index,
                        table_type=table.table_type,
                    )
                continue

            note_inherited = (
                _inherit_note_context(
                    label,
                    note_context_stack,
                    broad_note_context=True,
                )
                if use_note_context
                else _ContextInheritedLabel(
                    original_label=label,
                    inherited_label=label,
                )
            )
            header_inherited = (
                _inherit_header_context(
                    note_inherited.inherited_label,
                    row=row,
                    label_index=label_index,
                    year_columns=year_columns,
                    context_stack=header_context_stack,
                )
                if not note_inherited.changed
                else _HeaderInheritedLabel(
                    original_label=note_inherited.inherited_label,
                    inherited_label=note_inherited.inherited_label,
                )
            )
            if header_inherited.changed:
                diagnostics.append(
                    HeaderInheritanceDiagnostic(
                        source_report_year=table.source_report_year,
                        page_number=table.page_number,
                        table_index=table.table_index,
                        table_type=table.table_type,
                        row_index=row_index,
                        original_label=header_inherited.original_label,
                        inherited_label=header_inherited.inherited_label,
                        inherited_header=header_inherited.inherited_header or "",
                        inheritance_source=header_inherited.inheritance_source or "",
                        reconstruction_reason=(
                            header_inherited.reconstruction_reason or ""
                        ),
                        metric_values_affected=metric_values_affected,
                    )
                )

            if use_note_context and metric_values_affected > 0:
                _update_note_context_from_metric_row(
                    note_context_stack,
                    label=note_inherited.original_label,
                    inherited_label=note_inherited,
                )
            _update_header_context_from_row(
                header_context_stack,
                label=header_inherited.original_label,
                row=row,
                row_index=row_index,
                header_row_index=header_row_index,
                metric_value_count=metric_values_affected,
                table_type=table.table_type,
                inherited_label=header_inherited,
            )

    return diagnostics


def _metric_value_count_for_row(
    *,
    row: Sequence[str],
    label_index: int,
    year_columns: dict[int, int],
    scale_multiplier: int,
) -> int:
    """Return how many MetricValues a row can emit."""

    count = 0
    for column_index in year_columns:
        if column_index >= len(row) or column_index == label_index:
            continue
        if (
            CamelotTableExtractor._parse_metric_value(
                row[column_index],
                default_scale_multiplier=scale_multiplier,
            )
            is not None
        ):
            count += 1
    return count


def _metric_quality_findings(
    tables: list[ExtractedTable],
) -> list[SuspiciousMetricFinding]:
    """Return duplicate/conflicting/unclassified metric findings."""

    grouped: dict[
        tuple[str, int, int, str],
        list[tuple[MetricValueOccurrence, float | int | str]],
    ] = {}
    for table in tables:
        for metric_value in table.metric_values:
            key = (
                metric_value.metric,
                metric_value.value_year,
                metric_value.source_report_year,
                metric_value.table_type,
            )
            occurrence = MetricValueOccurrence(
                page_number=metric_value.page_number,
                table_index=table.table_index,
                table_type=metric_value.table_type,
                value=metric_value.value,
            )
            grouped.setdefault(key, []).append((occurrence, metric_value.value))

    findings: list[SuspiciousMetricFinding] = []
    for (
        metric,
        value_year,
        source_report_year,
        table_type,
    ), occurrences_and_values in grouped.items():
        occurrences = [
            occurrence for occurrence, _ in occurrences_and_values
        ]
        values = [value for _, value in occurrences_and_values]
        distinct_values = _distinct_values(values)
        reasons: list[str] = []
        if len(occurrences) > 1:
            reasons.append("duplicate_metric_values")
        if len(distinct_values) > 1:
            reasons.append("conflicting_values")
        if _normalize_key(table_type) == UNCLASSIFIED_TABLE_TYPE:
            reasons.append("unclassified_table_metric")
        if not reasons:
            continue

        findings.append(
            SuspiciousMetricFinding(
                metric=metric,
                value_year=value_year,
                source_report_year=source_report_year,
                table_type=table_type,
                occurrence_count=len(occurrences),
                distinct_values=distinct_values,
                suspicion_score=_metric_suspicion_score(
                    reasons=reasons,
                    occurrence_count=len(occurrences),
                    distinct_value_count=len(distinct_values),
                ),
                reasons=reasons,
                occurrences=occurrences[:10],
            )
        )

    return findings


def _metric_suspicion_score(
    *,
    reasons: list[str],
    occurrence_count: int,
    distinct_value_count: int,
) -> float:
    """Return a bounded review priority score for a metric finding."""

    score = 0.0
    if "conflicting_values" in reasons:
        score += 65
    if "duplicate_metric_values" in reasons:
        score += min(25, 5 * (occurrence_count - 1))
    if "unclassified_table_metric" in reasons:
        score += 20
    if distinct_value_count > 2:
        score += min(10, 2 * distinct_value_count)
    return round(max(0.0, min(score, 100.0)), 2)


def _distinct_values(values: list[float | int | str]) -> list[float | int | str]:
    """Return distinct values while preserving first-seen order."""

    distinct: list[float | int | str] = []
    seen: set[str] = set()
    for value in values:
        stable = _stable_value_text(value)
        if stable in seen:
            continue
        seen.add(stable)
        distinct.append(value)
    return distinct


def _stable_value_text(value: float | int | str) -> str:
    """Return a stable comparable representation for a metric value."""

    return f"{type(value).__name__}:{value}"


def _increment_quality_bucket(
    distribution: dict[str, int],
    quality_score: float,
) -> None:
    """Increment the quality-score bucket for one table."""

    if quality_score < 20:
        distribution["0-20"] += 1
    elif quality_score < 40:
        distribution["20-40"] += 1
    elif quality_score < 60:
        distribution["40-60"] += 1
    elif quality_score < 80:
        distribution["60-80"] += 1
    else:
        distribution["80-100"] += 1


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
        tables_split=sum(diagnostic.tables_split for diagnostic in page_diagnostics),
        split_reasons=_dedupe_preserve_order(
            [
                diagnostic.split_reason
                for diagnostic in page_diagnostics
                if diagnostic.split_reason
            ]
        ),
        logical_types_created=_dedupe_preserve_order(
            [
                table_type
                for diagnostic in page_diagnostics
                for table_type in diagnostic.logical_types_created
            ]
        ),
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
        "comprehensive income",
        "statement of comprehensive income",
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
        "profit before taxation",
        "profit after tax",
        "profit after taxation",
        "earnings per share",
        "other comprehensive income",
        "other comprehensive loss",
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
        "cash generated f rom operations",
        "profit before working capital changes",
        "decrease increase in current assets",
        "increase in current liabilities",
        "net cash",
        "et cash",
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
        "long term financin g",
        "long term lo ans",
        "short term borrowings",
        "short term bo rrowings",
        "loans and borrowings",
        "lease liabilities",
        "markup accrued",
        "debt",
    ),
    "notes": (
        "notes to the financial statements",
        "notes to financial statements",
        "notes to the consolidated financial statements",
        "notes to consolidated financial statements",
        "no tes t o the c onso l idat ed fin anci al state men t s",
        "note 2025 2024",
        "pkr in",
        "for the year ended",
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
        "taxable temporary differences",
        "taxable temp orary differ ences",
        "deductible temporary differences",
        "deductible te mporary di fferences",
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
        "operating fix ed assets",
        "additions",
        "depreciation",
        "written down value",
        "capital work in progress",
        "capital work in p rogress",
        "capital spare",
    ),
}
