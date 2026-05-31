"""Consolidate comparative-year metric values across annual reports."""

from __future__ import annotations

from collections.abc import Iterable
import logging

from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue

logger = logging.getLogger(__name__)


class FinancialYearConsolidator:
    """Select the best available metric value for each metric/value year.

    Annual reports include comparative historical values. For any
    ``(metric, value_year)`` pair, the latest available ``source_report_year``
    is treated as the source of truth because it may contain restatements,
    corrections, reclassifications, or audited comparative values.
    """

    def consolidate(self, metric_values: Iterable[MetricValue]) -> list[MetricValue]:
        """Return one source-of-truth value for each metric and value year."""

        selected: dict[tuple[str, int], MetricValue] = {}
        for metric_value in metric_values:
            self._validate_metric_value(metric_value)
            key = (metric_value.metric, metric_value.value_year)
            existing = selected.get(key)
            if (
                existing is None
                or self._should_replace(existing, metric_value)
            ):
                if existing is not None and _values_differ(existing, metric_value):
                    logger.info(
                        "Metric value superseded during financial year consolidation",
                        extra={
                            "metric": metric_value.metric,
                            "value_year": metric_value.value_year,
                            "previous_value": existing.value,
                            "selected_value": metric_value.value,
                            "previous_source_report_year": (
                                existing.source_report_year
                            ),
                            "selected_source_report_year": (
                                metric_value.source_report_year
                            ),
                            "previous_page_number": existing.page_number,
                            "selected_page_number": metric_value.page_number,
                            "previous_table_type": existing.table_type,
                            "selected_table_type": metric_value.table_type,
                        },
                    )
                selected[key] = metric_value

        return sorted(
            selected.values(),
            key=lambda metric_value: (
                metric_value.metric,
                metric_value.value_year,
                metric_value.source_report_year,
            ),
        )

    def consolidate_context(self, context: CompanyContext) -> CompanyContext:
        """Consolidate normalized metric values from all report-year buckets."""

        metric_values: list[MetricValue] = []
        failures: list[str] = []
        for report in context.reports:
            try:
                normalization_result = context.normalization_results.get(report.year)
                if normalization_result is None:
                    raise ValueError(
                        "Missing normalization result for report year "
                        f"{report.year}."
                    )

                for metric_value in normalization_result.metric_values:
                    self._validate_bucket_year(report.year, metric_value)
                    self._validate_metric_value(metric_value)
                    metric_values.append(metric_value)
            except Exception as exc:
                failures.append(
                    f"Report year {report.year} failed financial year "
                    f"consolidation: {_error_message(exc)}"
                )
                logger.exception(
                    "Financial year consolidation failed for report; continuing",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                    },
                )
                continue

        context.metric_values = self.consolidate(metric_values)
        if failures:
            raise PipelineLayerPartialFailure(failures, context=context)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run financial year consolidation as a pipeline layer."""

        return self.consolidate_context(context)

    @classmethod
    def _should_replace(
        cls,
        existing: MetricValue,
        candidate: MetricValue,
    ) -> bool:
        """Return whether candidate should replace the currently selected value."""

        if candidate.source_report_year > existing.source_report_year:
            return True
        if candidate.source_report_year < existing.source_report_year:
            return False

        return _tie_break_key(candidate) < _tie_break_key(existing)

    @staticmethod
    def _validate_metric_value(metric_value: MetricValue) -> None:
        """Validate comparative-year provenance invariants."""

        if metric_value.value_year > metric_value.source_report_year:
            raise ValueError(
                "metric value_year cannot be greater than source_report_year: "
                f"{metric_value.metric} value_year={metric_value.value_year}, "
                f"source_report_year={metric_value.source_report_year}."
            )

    @staticmethod
    def _validate_bucket_year(bucket_year: int, metric_value: MetricValue) -> None:
        """Ensure context buckets remain isolated by source report year."""

        if bucket_year != metric_value.source_report_year:
            raise ValueError(
                "normalization_results bucket year must match "
                "metric_value.source_report_year: "
                f"bucket_year={bucket_year}, "
                f"source_report_year={metric_value.source_report_year}, "
                f"metric={metric_value.metric}."
            )


def _tie_break_key(metric_value: MetricValue) -> tuple[int, str, str]:
    """Return a stable same-source tie-break key independent of input order."""

    return (
        metric_value.page_number,
        metric_value.table_type.strip().lower(),
        _stable_value_text(metric_value.value),
    )


def _stable_value_text(value: float | int | str) -> str:
    """Return a stable comparable representation for a metric value."""

    return f"{type(value).__name__}:{value}"


def _values_differ(left: MetricValue, right: MetricValue) -> bool:
    """Return whether two metric values carry different extracted values."""

    return _stable_value_text(left.value) != _stable_value_text(right.value)


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for result metadata."""

    return str(exc) or exc.__class__.__name__
