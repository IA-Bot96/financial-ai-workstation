"""Consolidate comparative-year metric values across annual reports."""

from __future__ import annotations

from collections.abc import Iterable

from shared.models.company_context import CompanyContext
from shared.models.metric_value import MetricValue


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
            key = (metric_value.metric, metric_value.value_year)
            existing = selected.get(key)
            if (
                existing is None
                or metric_value.source_report_year > existing.source_report_year
            ):
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

        metric_values = [
            metric_value
            for normalization_result in context.normalization_results.values()
            for metric_value in normalization_result.metric_values
        ]
        context.metric_values = self.consolidate(metric_values)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run financial year consolidation as a pipeline layer."""

        return self.consolidate_context(context)
