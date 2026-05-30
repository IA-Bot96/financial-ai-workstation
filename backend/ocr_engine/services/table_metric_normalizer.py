"""OCR table metric normalization service."""

from __future__ import annotations

import logging
import re
from typing import Sequence

from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.models.table_normalization import (
    MetricMapping,
    NormalizationResult,
    NormalizedTable,
)
from ocr_engine.services.interfaces.table_metric_normalizer import (
    ITableMetricNormalizer,
)
from shared.models.company_context import CompanyContext
from shared.normalization.interfaces.metric_normalizer import IMetricNormalizer

logger = logging.getLogger(__name__)


class TableMetricNormalizer(ITableMetricNormalizer):
    """Normalize raw OCR table row labels to canonical metric names.

    This OCR layer works on extracted table rows. The injected shared normalizer
    remains responsible only for converting one metric name into a canonical key.
    """

    def __init__(
        self,
        *,
        metric_normalizer: IMetricNormalizer | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the service with an injectable single-metric normalizer."""

        self._metric_normalizer = metric_normalizer or self._load_default_normalizer()
        self._logger = log or logger

    def normalize_for_context(self, context: CompanyContext) -> CompanyContext:
        """Normalize each report year independently and store results by year.

        The method reads ``context.extraction_results[report.year]`` and writes
        the normalized output to ``context.normalization_results[report.year]``.
        Results from different years are never merged.
        """

        self._logger.info(
            "Starting metric normalization for company context",
            extra={
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )

        for report in context.reports:
            extraction_result = context.extraction_results.get(report.year)
            if extraction_result is None:
                raise ValueError(
                    "Missing table extraction result for report year "
                    f"{report.year}."
                )

            self._ensure_result_matches_year(report.year, extraction_result)
            self._logger.info(
                "Normalizing metrics for report year %s",
                report.year,
                extra={
                    "company_name": context.company_name,
                    "year": report.year,
                },
            )
            context.normalization_results[report.year] = self.normalize_tables(
                extraction_result
            )

        self._logger.info(
            "Company context metric normalization complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.normalization_results),
            },
        )
        return context

    def normalize_tables(
        self,
        table_extraction_result: TableExtractionResult,
    ) -> NormalizationResult:
        """Normalize metric labels in a single report's extracted tables."""

        self._ensure_single_result_year(table_extraction_result)
        normalized_tables: list[NormalizedTable] = []
        mappings: list[MetricMapping] = []

        for table in table_extraction_result.tables:
            normalized_rows: list[list[str]] = []
            for row in table.rows:
                normalized_row, mapping = self._normalize_row(table, row)
                normalized_rows.append(normalized_row)
                if mapping is not None:
                    mappings.append(mapping)

            normalized_tables.append(
                NormalizedTable(
                    year=table.year,
                    page_number=table.page_number,
                    table_type=table.table_type,
                    table_index=table.table_index,
                    rows=normalized_rows,
                )
            )

        result = NormalizationResult(tables=normalized_tables, mappings=mappings)
        self._logger.info(
            "Metric normalization completed",
            extra={
                "tables_normalized": len(result.tables),
                "mappings_generated": len(result.mappings),
            },
        )
        return result

    def _normalize_row(
        self,
        table: ExtractedTable,
        row: Sequence[str],
    ) -> tuple[list[str], MetricMapping | None]:
        """Normalize the first text label in a table row, preserving raw cells."""

        normalized_row = [str(cell).strip() for cell in row]
        label_index = self._metric_label_index(normalized_row)
        if label_index is None:
            return normalized_row, None

        original_metric = normalized_row[label_index]
        normalized_metric = self._metric_normalizer.normalize_metric(original_metric)
        if normalized_metric.normalized_metric is not None:
            normalized_row[label_index] = normalized_metric.normalized_metric

        mapping = MetricMapping(
            year=table.year,
            original_metric=normalized_metric.original_metric,
            normalized_metric=normalized_metric.normalized_metric,
            confidence=normalized_metric.confidence,
            requires_review=normalized_metric.requires_review,
        )
        return normalized_row, mapping

    @staticmethod
    def _metric_label_index(row: Sequence[str]) -> int | None:
        """Return the first non-empty cell that looks like a metric label."""

        for index, cell in enumerate(row):
            text = str(cell).strip()
            if text and re.search(r"[A-Za-z]", text):
                return index
        return None

    @classmethod
    def _ensure_result_matches_year(
        cls,
        year: int,
        table_extraction_result: TableExtractionResult,
    ) -> None:
        """Ensure a context year bucket contains only tables from that year."""

        result_years = cls._result_years(table_extraction_result)
        mismatched_years = result_years - {year}
        if mismatched_years:
            raise ValueError(
                "Normalization input for report year "
                f"{year} contains data from other years: "
                f"{sorted(mismatched_years)}."
            )

    @classmethod
    def _ensure_single_result_year(
        cls,
        table_extraction_result: TableExtractionResult,
    ) -> None:
        """Prevent direct normalization of merged multi-year table results."""

        result_years = cls._result_years(table_extraction_result)
        if len(result_years) > 1:
            raise ValueError(
                "Normalization input must contain a single report year. "
                f"Received years: {sorted(result_years)}."
            )

    @staticmethod
    def _result_years(table_extraction_result: TableExtractionResult) -> set[int]:
        """Return all years represented by extracted tables."""

        return {table.year for table in table_extraction_result.tables}

    @staticmethod
    def _load_default_normalizer() -> IMetricNormalizer:
        """Load the shared embedding normalizer only when needed."""

        from shared.normalization.services.metric_normalizer import (
            EmbeddingMetricNormalizer,
        )

        return EmbeddingMetricNormalizer()
