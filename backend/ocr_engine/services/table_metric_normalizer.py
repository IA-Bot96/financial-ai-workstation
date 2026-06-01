"""OCR table metric normalization service."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Sequence

from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.table_normalization import (
    MetricMapping,
    NormalizationResult,
    NormalizedTable,
)
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.interfaces.table_metric_normalizer import (
    ITableMetricNormalizer,
)
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue
from shared.normalization.constants.normalization_constants import (
    HIGH_CONFIDENCE_THRESHOLD,
)
from shared.normalization.interfaces.metric_normalizer import IMetricNormalizer
from shared.normalization.models.normalized_metric import NormalizedMetric

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MetricNormalizationDecision:
    """Normalization result plus preprocessing provenance."""

    result: NormalizedMetric
    normalization_input_metric: str
    parent_metric_context: str | None = None
    child_metric: str | None = None
    parent_prefix_stripped: bool = False
    normalization_rule: str | None = None


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

        failures: list[str] = []
        for report in context.reports:
            try:
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
            except Exception as exc:
                failures.append(
                    f"Report year {report.year} failed metric normalization: "
                    f"{_error_message(exc)}"
                )
                context.normalization_results[report.year] = NormalizationResult(
                    tables=[],
                    metric_values=[],
                    mappings=[],
                )
                self._logger.exception(
                    "Metric normalization failed for report; continuing",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                    },
                )
                continue

        self._logger.info(
            "Company context metric normalization complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.normalization_results),
            },
        )
        if failures:
            raise PipelineLayerPartialFailure(failures, context=context)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run metric normalization as a pipeline layer."""

        return self.normalize_for_context(context)

    def normalize_tables(
        self,
        table_extraction_result: TableExtractionResult,
    ) -> NormalizationResult:
        """Normalize metric labels in a single report's extracted tables."""

        self._ensure_single_result_year(table_extraction_result)
        normalized_tables: list[NormalizedTable] = []
        mappings: list[MetricMapping] = []
        all_metric_values: list[MetricValue] = []

        for table in table_extraction_result.tables:
            normalized_rows: list[list[str]] = []
            for row in table.rows:
                normalized_row = self._normalize_row(row)
                normalized_rows.append(normalized_row)

            table_metric_values: list[MetricValue] = []
            for metric_value in table.metric_values:
                normalized_metric_value, mapping = self._normalize_metric_value(
                    metric_value,
                    table=table,
                )
                table_metric_values.append(normalized_metric_value)
                all_metric_values.append(normalized_metric_value)
                mappings.append(mapping)

            normalized_tables.append(
                NormalizedTable(
                    source_report_year=table.source_report_year,
                    page_number=table.page_number,
                    table_type=table.table_type,
                    table_index=table.table_index,
                    source_table_index=table.source_table_index,
                    split_table_index=table.split_table_index,
                    split_reason=table.split_reason,
                    detected_table_id=table.detected_table_id,
                    page_table_index=table.page_table_index,
                    bbox=table.bbox,
                    detection_confidence=table.detection_confidence,
                    match_method=table.match_method,
                    rows=normalized_rows,
                    metric_values=table_metric_values,
                )
            )

        result = NormalizationResult(
            tables=normalized_tables,
            metric_values=all_metric_values,
            mappings=mappings,
        )
        self._logger.info(
            "Metric normalization completed",
            extra={
                "tables_normalized": len(result.tables),
                "mappings_generated": len(result.mappings),
            },
        )
        return result

    def _normalize_row(self, row: Sequence[str]) -> list[str]:
        """Normalize the first text label in a table row, preserving raw cells."""

        normalized_row = [str(cell).strip() for cell in row]
        label_index = self._metric_label_index(normalized_row)
        if label_index is None:
            return normalized_row

        original_metric = normalized_row[label_index]
        normalized_metric = self._metric_normalizer.normalize_metric(original_metric)
        if normalized_metric.normalized_metric is not None:
            normalized_row[label_index] = normalized_metric.normalized_metric

        return normalized_row

    def _normalize_metric_value(
        self,
        metric_value: MetricValue,
        *,
        table: object | None = None,
    ) -> tuple[MetricValue, MetricMapping]:
        """Normalize one extracted metric value while preserving year provenance."""

        decision = self._normalize_metric_with_parent_prefix(
            metric_value.metric
        )
        normalized_metric = decision.result
        normalized_metric_name = normalized_metric.normalized_metric or metric_value.metric
        normalized_metric_value = metric_value.model_copy(
            update={"metric": normalized_metric_name}
        )
        mapping = MetricMapping(
            value_year=metric_value.value_year,
            source_report_year=metric_value.source_report_year,
            original_metric=normalized_metric.original_metric,
            normalized_metric=normalized_metric.normalized_metric,
            confidence=normalized_metric.confidence,
            requires_review=normalized_metric.requires_review,
            page_number=metric_value.page_number,
            table_type=metric_value.table_type,
            table_index=getattr(table, "table_index", None),
            detected_table_id=getattr(table, "detected_table_id", None),
            match_method=getattr(table, "match_method", None),
            normalization_input_metric=decision.normalization_input_metric,
            parent_metric_context=decision.parent_metric_context,
            child_metric=decision.child_metric,
            parent_prefix_stripped=decision.parent_prefix_stripped,
            normalization_rule=decision.normalization_rule,
        )
        return normalized_metric_value, mapping

    def _normalize_metric_with_parent_prefix(
        self,
        metric_name: str,
    ) -> _MetricNormalizationDecision:
        """Normalize a metric, stripping preserved parent context when safe."""

        original_result = self._metric_normalizer.normalize_metric(metric_name)
        split_metric = _split_parent_prefixed_metric(metric_name)
        if split_metric is None:
            return _MetricNormalizationDecision(
                result=original_result,
                normalization_input_metric=metric_name,
            )

        parent_context, child_metric = split_metric
        child_result = self._metric_normalizer.normalize_metric(child_metric)
        if not _is_strong_child_match(child_result):
            return _MetricNormalizationDecision(
                result=original_result,
                normalization_input_metric=metric_name,
            )

        original_is_strong_specific_match = (
            original_result.normalized_metric is not None
            and original_result.confidence >= HIGH_CONFIDENCE_THRESHOLD
            and original_result.normalized_metric != child_result.normalized_metric
        )
        if original_is_strong_specific_match:
            return _MetricNormalizationDecision(
                result=original_result,
                normalization_input_metric=metric_name,
            )

        self._logger.debug(
            "Parent prefix stripped before metric normalization",
            extra={
                "original_metric": metric_name,
                "parent_metric_context": parent_context,
                "child_metric": child_metric,
                "normalized_metric": child_result.normalized_metric,
                "confidence": child_result.confidence,
            },
        )
        return _MetricNormalizationDecision(
            result=NormalizedMetric(
                original_metric=metric_name,
                normalized_metric=child_result.normalized_metric,
                confidence=child_result.confidence,
                requires_review=child_result.requires_review,
            ),
            normalization_input_metric=child_metric,
            parent_metric_context=parent_context,
            child_metric=child_metric,
            parent_prefix_stripped=True,
            normalization_rule="parent_prefix_stripping",
        )

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

        return {
            table.source_report_year for table in table_extraction_result.tables
        } | {
            metric_value.source_report_year
            for metric_value in table_extraction_result.metric_values
        }

    @staticmethod
    def _load_default_normalizer() -> IMetricNormalizer:
        """Load the shared embedding normalizer only when needed."""

        from shared.normalization.services.metric_normalizer import (
            EmbeddingMetricNormalizer,
        )

        return EmbeddingMetricNormalizer()


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for result metadata."""

    return str(exc) or exc.__class__.__name__


def _split_parent_prefixed_metric(metric_name: str) -> tuple[str, str] | None:
    """Return parent context and child metric for a preserved context label."""

    parts = [
        part.strip()
        for part in re.split(r"\s+(?:-|\u2013|\u2014)\s+", metric_name)
        if part.strip()
    ]
    if len(parts) < 2:
        return None

    parent_context = " - ".join(parts[:-1]).strip()
    child_metric = parts[-1].strip()
    if not parent_context or not child_metric:
        return None
    if not re.search(r"[A-Za-z]", parent_context):
        return None
    if not re.search(r"[A-Za-z]", child_metric):
        return None
    return parent_context, child_metric


def _is_strong_child_match(normalized_metric: NormalizedMetric) -> bool:
    """Return whether a stripped child metric maps strongly on its own."""

    return (
        normalized_metric.normalized_metric is not None
        and not normalized_metric.requires_review
        and normalized_metric.confidence >= HIGH_CONFIDENCE_THRESHOLD
    )
