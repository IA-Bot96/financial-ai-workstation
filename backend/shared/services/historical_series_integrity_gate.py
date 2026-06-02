"""Deterministic historical-series integrity gate for Forecast Validation."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Final

from shared.models.financial_year_consolidation import (
    ConsolidationCandidate,
    ConsolidationGroup,
    FinancialYearConsolidationResult,
    SourceClass,
    StatementScope,
)
from shared.models.historical_series_integrity import (
    CandidateSpreadEvidence,
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
    IntegrityEvidence,
    IntegrityStatus,
    ScaleCheckStatus,
    ScaleConsistencyResult,
    SeriesValueCandidateEvidence,
    YoYScaleEvidence,
)
from shared.models.metric_value import MetricValue

logger = logging.getLogger(__name__)

MVP_HISTORICAL_SERIES_METRICS: Final[tuple[str, ...]] = (
    "revenue",
    "profit_after_tax",
    "operating_profit",
    "total_assets",
    "cash_and_cash_equivalents",
    "operating_cash_flow",
    "gross_profit",
    "earnings_per_share",
    "total_debt",
    "long_term_debt",
    "total_equity",
)

_EPS_METRICS: Final[set[str]] = {"earnings_per_share"}

_METRIC_ALLOWED_HEADLINE_TABLES: Final[dict[str, tuple[str, ...]]] = {
    "revenue": ("income_statement", "statement_of_profit_or_loss"),
    "profit_after_tax": ("income_statement", "statement_of_profit_or_loss"),
    "operating_profit": ("income_statement", "statement_of_profit_or_loss"),
    "gross_profit": ("income_statement", "statement_of_profit_or_loss"),
    "earnings_per_share": (
        "income_statement",
        "statement_of_profit_or_loss",
        "financial_ratios",
    ),
    "total_assets": ("balance_sheet", "statement_of_financial_position"),
    "total_equity": ("balance_sheet", "statement_of_financial_position"),
    "cash_and_cash_equivalents": (
        "balance_sheet",
        "statement_of_financial_position",
        "cash_flow_statement",
        "statement_of_cash_flows",
    ),
    "operating_cash_flow": ("cash_flow_statement", "statement_of_cash_flows"),
    "total_debt": ("balance_sheet", "statement_of_financial_position"),
    "long_term_debt": ("balance_sheet", "statement_of_financial_position"),
}

_SOURCE_CLASS_PRIMARY_TABLES: Final[set[str]] = {
    "income_statement",
    "statement_of_profit_or_loss",
    "balance_sheet",
    "statement_of_financial_position",
    "cash_flow_statement",
    "statement_of_cash_flows",
    "statement_of_changes_in_equity",
}


class HistoricalSeriesIntegrityGate:
    """Classify historical financial series before Forecast Validation runs.

    The gate consumes the existing financial-year consolidation output and
    returns conservative readiness statuses. It does not forecast, calculate
    growth, calculate CAGR, or repair OCR output.
    """

    default_metrics: tuple[str, ...] = MVP_HISTORICAL_SERIES_METRICS

    def evaluate(
        self,
        consolidation_result: FinancialYearConsolidationResult,
        metrics: Iterable[str] | None = None,
    ) -> HistoricalSeriesIntegrityGateResult:
        """Evaluate integrity for the requested canonical metrics."""

        requested_metrics = list(dict.fromkeys(metrics or self.default_metrics))
        metric_values_by_metric = _group_selected_metric_values(
            consolidation_result.metric_values
        )
        groups_by_key = {
            (group.metric, group.value_year): group
            for group in consolidation_result.groups
        }

        series_results = [
            self._evaluate_metric(
                metric=metric,
                selected_values=metric_values_by_metric.get(metric, []),
                groups_by_key=groups_by_key,
            )
            for metric in requested_metrics
        ]
        status_counts = _status_counts(series_results)
        metrics_by_status = _metrics_by_status(series_results)
        overall_status = _overall_status(status_counts)

        return HistoricalSeriesIntegrityGateResult(
            metrics_evaluated=requested_metrics,
            series_results=series_results,
            overall_status=overall_status,
            status_counts=status_counts,
            metrics_by_status=metrics_by_status,
            clean_metrics=metrics_by_status["clean"],
            warning_metrics=metrics_by_status["clean_with_warning"],
            blocked_metrics=metrics_by_status["baseline_not_validatable"],
            missing_metrics=metrics_by_status["missing"],
            critical_issue_count=sum(
                len(result.blocking_issues) for result in series_results
            ),
            warning_count=sum(
                len(result.warning_issues) for result in series_results
            ),
        )

    def _evaluate_metric(
        self,
        *,
        metric: str,
        selected_values: list[MetricValue],
        groups_by_key: dict[tuple[str, int], ConsolidationGroup],
    ) -> HistoricalSeriesIntegrityResult:
        """Evaluate one metric series."""

        if not selected_values:
            return self._missing_result(metric)

        selected_values = sorted(selected_values, key=lambda value: value.value_year)
        selected_series: list[SeriesValueCandidateEvidence] = []
        blocking_issues: list[HistoricalSeriesIntegrityIssue] = []
        warning_issues: list[HistoricalSeriesIntegrityIssue] = []
        candidate_spreads: list[CandidateSpreadEvidence] = []
        yoy_checks: list[YoYScaleEvidence] = []
        source_policy_violations: list[HistoricalSeriesIntegrityIssue] = []
        evidence_records: list[IntegrityEvidence] = []

        for selected_value in selected_values:
            key = (metric, selected_value.value_year)
            group = groups_by_key.get(key)
            selected_candidate = _selected_candidate_evidence(selected_value, group)
            selected_series.append(selected_candidate)
            candidates = _candidate_evidence_for_year(selected_value, group)

            spread_evidence = _candidate_spread_evidence(
                metric=metric,
                value_year=selected_value.value_year,
                candidates=candidates,
                selected_candidate=selected_candidate,
            )
            candidate_spreads.append(spread_evidence)
            evidence_records.append(
                _integrity_evidence(
                    evidence_id=_evidence_id(
                        metric,
                        selected_value.value_year,
                        "candidate_spread",
                    ),
                    metric=metric,
                    value_year=selected_value.value_year,
                    evidence_type="candidate_spread",
                    candidates=candidates,
                    calculations={
                        "candidate_count": spread_evidence.candidate_count,
                        "candidate_spread": spread_evidence.candidate_spread,
                    },
                    policy_applied="ScaleConsistencyContract",
                )
            )
            spread_issue = _issue_for_spread(spread_evidence)
            if spread_issue is not None:
                if spread_issue.blocking:
                    blocking_issues.append(spread_issue)
                else:
                    warning_issues.append(spread_issue)

            if group is not None and group.unresolved_conflict:
                issue = _issue(
                    issue_type="unresolved_conflict",
                    severity="critical",
                    metric=metric,
                    value_years=[selected_value.value_year],
                    description=(
                        f"{metric} has an unresolved consolidation conflict for "
                        f"{selected_value.value_year}."
                    ),
                    blocking=True,
                    fixability="review_only",
                    evidence_ids=[
                        _evidence_id(metric, selected_value.value_year, "candidate_spread")
                    ],
                )
                blocking_issues.append(issue)

            if selected_candidate.requires_review:
                issue = _issue(
                    issue_type="review_gated_value",
                    severity="critical",
                    metric=metric,
                    value_years=[selected_value.value_year],
                    description=(
                        f"{metric} selected value for {selected_value.value_year} "
                        "still requires normalization review."
                    ),
                    blocking=True,
                    fixability="review_only",
                    evidence_ids=[
                        _evidence_id(metric, selected_value.value_year, "candidate_spread")
                    ],
                )
                blocking_issues.append(issue)

            source_issues = _source_policy_issues(
                metric=metric,
                selected_candidate=selected_candidate,
                candidates=candidates,
            )
            source_policy_violations.extend(source_issues)
            blocking_issues.extend(issue for issue in source_issues if issue.blocking)
            warning_issues.extend(issue for issue in source_issues if not issue.blocking)

        yoy_checks.extend(_yoy_scale_checks(metric, selected_series))
        for yoy_check in yoy_checks:
            evidence_records.append(
                _integrity_evidence(
                    evidence_id=_evidence_id(
                        metric,
                        yoy_check.to_year,
                        "yoy_scale",
                    ),
                    metric=metric,
                    value_year=yoy_check.to_year,
                    evidence_type="yoy_scale",
                    candidates=[
                        candidate
                        for candidate in selected_series
                        if candidate.value_year in {yoy_check.from_year, yoy_check.to_year}
                    ],
                    calculations={
                        "from_year": yoy_check.from_year,
                        "to_year": yoy_check.to_year,
                        "previous_value": yoy_check.previous_value,
                        "current_value": yoy_check.current_value,
                        "ratio": yoy_check.ratio,
                    },
                    policy_applied="ScaleConsistencyContract",
                )
            )
            issue = _issue_for_yoy(yoy_check)
            if issue is not None:
                if issue.blocking:
                    blocking_issues.append(issue)
                else:
                    warning_issues.append(issue)

        scale_result = _scale_result(candidate_spreads, yoy_checks)
        status = _series_status(blocking_issues, warning_issues)
        logger.debug(
            "Historical series integrity evaluated",
            extra={
                "metric": metric,
                "status": status,
                "blocking_issues": len(blocking_issues),
                "warnings": len(warning_issues),
            },
        )

        return HistoricalSeriesIntegrityResult(
            metric=metric,
            status=status,
            value_years=[value.value_year for value in selected_values],
            selected_series=selected_series,
            blocking_issues=blocking_issues,
            warning_issues=warning_issues,
            candidate_spread_by_year=candidate_spreads,
            yoy_scale_issues=yoy_checks,
            source_policy_violations=source_policy_violations,
            scale_result=scale_result,
            evidence=evidence_records,
            confidence=_status_confidence(status, blocking_issues, warning_issues),
            validation_readiness=status in {"clean", "clean_with_warning"},
        )

    @staticmethod
    def _missing_result(metric: str) -> HistoricalSeriesIntegrityResult:
        """Return a missing exact canonical metric result."""

        evidence_id = _evidence_id(metric, None, "missing_metric")
        issue = _issue(
            issue_type="missing_exact_canonical_metric",
            severity="critical",
            metric=metric,
            value_years=[],
            description=(
                f"Exact canonical metric {metric!r} is absent; no substitute "
                "was used for Forecast Validation."
            ),
            blocking=True,
            fixability="not_applicable",
            evidence_ids=[evidence_id],
        )
        return HistoricalSeriesIntegrityResult(
            metric=metric,
            status="missing",
            value_years=[],
            selected_series=[],
            blocking_issues=[issue],
            warning_issues=[],
            candidate_spread_by_year=[],
            yoy_scale_issues=[],
            source_policy_violations=[],
            scale_result=ScaleConsistencyResult(
                status="not_applicable",
                max_candidate_spread=None,
                max_yoy_magnitude_ratio=None,
                blocking_reasons=["missing_exact_canonical_metric"],
                warning_reasons=[],
            ),
            evidence=[
                _integrity_evidence(
                    evidence_id=evidence_id,
                    metric=metric,
                    value_year=None,
                    evidence_type="missing_metric",
                    candidates=[],
                    calculations={},
                    policy_applied="MissingMetricPolicy",
                )
            ],
            confidence=1.0,
            validation_readiness=False,
        )


def _group_selected_metric_values(
    metric_values: Iterable[MetricValue],
) -> dict[str, list[MetricValue]]:
    grouped: dict[str, list[MetricValue]] = {}
    for metric_value in metric_values:
        grouped.setdefault(metric_value.metric, []).append(metric_value)
    return grouped


def _candidate_evidence_for_year(
    selected_value: MetricValue,
    group: ConsolidationGroup | None,
) -> list[SeriesValueCandidateEvidence]:
    if group is None:
        return [_candidate_from_metric_value(selected_value, is_selected=True)]
    return [
        _candidate_from_consolidation_candidate(group.selected, is_selected=True),
        *[
            _candidate_from_consolidation_candidate(
                candidate,
                is_selected=False,
            )
            for candidate in group.competing_candidates
        ],
    ]


def _selected_candidate_evidence(
    selected_value: MetricValue,
    group: ConsolidationGroup | None,
) -> SeriesValueCandidateEvidence:
    if group is None:
        return _candidate_from_metric_value(selected_value, is_selected=True)
    return _candidate_from_consolidation_candidate(group.selected, is_selected=True)


def _candidate_from_metric_value(
    metric_value: MetricValue,
    *,
    is_selected: bool,
) -> SeriesValueCandidateEvidence:
    return SeriesValueCandidateEvidence(
        metric=metric_value.metric,
        value_year=metric_value.value_year,
        value=metric_value.value,
        source_report_year=metric_value.source_report_year,
        page_number=metric_value.page_number,
        table_type=metric_value.table_type,
        source_class=_source_class(metric_value.table_type),
        statement_scope="unknown",
        normalization_confidence=0.0,
        source_confidence=0.0,
        original_metric=metric_value.metric,
        requires_review=False,
        is_currently_selected=is_selected,
    )


def _candidate_from_consolidation_candidate(
    candidate: ConsolidationCandidate,
    *,
    is_selected: bool,
) -> SeriesValueCandidateEvidence:
    return SeriesValueCandidateEvidence(
        metric=candidate.metric,
        value_year=candidate.value_year,
        value=candidate.value,
        source_report_year=candidate.source_report_year,
        page_number=candidate.page_number,
        table_type=candidate.table_type,
        source_class=candidate.source_class,
        statement_scope=candidate.statement_scope,
        normalization_confidence=candidate.normalization_confidence,
        source_confidence=candidate.source_confidence,
        original_metric=candidate.original_metric,
        requires_review=candidate.requires_review,
        is_currently_selected=is_selected,
    )


def _candidate_spread_evidence(
    *,
    metric: str,
    value_year: int,
    candidates: list[SeriesValueCandidateEvidence],
    selected_candidate: SeriesValueCandidateEvidence,
) -> CandidateSpreadEvidence:
    numeric_values = [
        abs(value)
        for candidate in candidates
        if (value := _numeric_value(candidate.value)) is not None and value != 0
    ]
    spread = _magnitude_spread(numeric_values)
    status = _scale_status(spread)
    return CandidateSpreadEvidence(
        metric=metric,
        value_year=value_year,
        candidate_count=len(numeric_values),
        candidate_spread=spread,
        status=status,
        selected_candidate=selected_candidate,
        sample_competing_candidates=[
            candidate for candidate in candidates if not candidate.is_currently_selected
        ][:10],
    )


def _issue_for_spread(
    spread: CandidateSpreadEvidence,
) -> HistoricalSeriesIntegrityIssue | None:
    if spread.status == "block" and spread.metric in _EPS_METRICS:
        return _issue(
            issue_type="candidate_spread_gt_100x_rejected_eps_candidates",
            severity="warning",
            metric=spread.metric,
            value_years=[spread.value_year],
            description=(
                f"{spread.metric} has rejected same-year candidates spread above "
                "100x, but EPS selected values remain usable with review warning."
            ),
            blocking=False,
            fixability="review_only",
            evidence_ids=[_evidence_id(spread.metric, spread.value_year, "candidate_spread")],
        )
    if spread.status == "block":
        return _issue(
            issue_type="candidate_spread_gt_100x",
            severity="critical",
            metric=spread.metric,
            value_years=[spread.value_year],
            description=(
                f"{spread.metric} candidate spread exceeds 100x for "
                f"{spread.value_year}; selected value cannot be trusted."
            ),
            blocking=True,
            fixability="review_only",
            evidence_ids=[_evidence_id(spread.metric, spread.value_year, "candidate_spread")],
        )
    if spread.status == "warning_or_block":
        return _issue(
            issue_type="candidate_spread_gt_10x",
            severity="warning",
            metric=spread.metric,
            value_years=[spread.value_year],
            description=(
                f"{spread.metric} candidate spread exceeds 10x for "
                f"{spread.value_year}."
            ),
            blocking=False,
            fixability="policy",
            evidence_ids=[_evidence_id(spread.metric, spread.value_year, "candidate_spread")],
        )
    if spread.status == "warning":
        return _issue(
            issue_type="candidate_spread_gt_5x",
            severity="warning",
            metric=spread.metric,
            value_years=[spread.value_year],
            description=(
                f"{spread.metric} candidate spread exceeds 5x for "
                f"{spread.value_year}."
            ),
            blocking=False,
            fixability="policy",
            evidence_ids=[_evidence_id(spread.metric, spread.value_year, "candidate_spread")],
        )
    return None


def _source_policy_issues(
    *,
    metric: str,
    selected_candidate: SeriesValueCandidateEvidence,
    candidates: list[SeriesValueCandidateEvidence],
) -> list[HistoricalSeriesIntegrityIssue]:
    allowed_tables = _METRIC_ALLOWED_HEADLINE_TABLES.get(metric)
    if allowed_tables is None:
        return []

    issues: list[HistoricalSeriesIntegrityIssue] = []
    selected_table = _normalize_table_type(selected_candidate.table_type)
    evidence_id = _evidence_id(metric, selected_candidate.value_year, "candidate_spread")

    if selected_table not in allowed_tables:
        issue_type = "disallowed_source_table"
        if metric == "cash_and_cash_equivalents" and selected_table in {
            "income_statement",
            "statement_of_profit_or_loss",
        }:
            issue_type = "cash_selected_from_income_statement"
        elif metric == "operating_cash_flow" and selected_table in {
            "balance_sheet",
            "statement_of_financial_position",
        }:
            issue_type = "operating_cash_flow_selected_from_balance_sheet"

        issues.append(
            _issue(
                issue_type=issue_type,
                severity="critical",
                metric=metric,
                value_years=[selected_candidate.value_year],
                description=(
                    f"{metric} selected from {selected_candidate.table_type}; "
                    f"expected one of {list(allowed_tables)}."
                ),
                blocking=True,
                fixability="policy",
                evidence_ids=[evidence_id],
            )
        )

    valid_primary_candidates = [
        candidate
        for candidate in candidates
        if _normalize_table_type(candidate.table_type) in allowed_tables
        and candidate.source_class == "primary_statement"
    ]
    if (
        selected_candidate.source_class == "note_disclosure"
        and valid_primary_candidates
    ):
        issues.append(
            _issue(
                issue_type="note_selected_over_primary_statement",
                severity="critical",
                metric=metric,
                value_years=[selected_candidate.value_year],
                description=(
                    f"{metric} selected from note disclosure while a valid "
                    "primary-statement candidate exists."
                ),
                blocking=True,
                fixability="policy",
                evidence_ids=[evidence_id],
            )
        )
    return issues


def _yoy_scale_checks(
    metric: str,
    selected_series: list[SeriesValueCandidateEvidence],
) -> list[YoYScaleEvidence]:
    checks: list[YoYScaleEvidence] = []
    numeric_series = [
        (candidate.value_year, numeric_value)
        for candidate in sorted(selected_series, key=lambda item: item.value_year)
        if (numeric_value := _numeric_value(candidate.value)) is not None
    ]
    for (from_year, previous_value), (to_year, current_value) in zip(
        numeric_series,
        numeric_series[1:],
    ):
        ratio = _magnitude_spread([abs(previous_value), abs(current_value)])
        checks.append(
            YoYScaleEvidence(
                metric=metric,
                from_year=from_year,
                to_year=to_year,
                previous_value=previous_value,
                current_value=current_value,
                ratio=ratio,
                status=_scale_status(ratio, block_threshold=10.0),
            )
        )
    return checks


def _issue_for_yoy(
    yoy_check: YoYScaleEvidence,
) -> HistoricalSeriesIntegrityIssue | None:
    if yoy_check.status == "block":
        return _issue(
            issue_type="yoy_scale_issue",
            severity="critical",
            metric=yoy_check.metric,
            value_years=[yoy_check.from_year, yoy_check.to_year],
            description=(
                f"{yoy_check.metric} YoY magnitude ratio exceeds 10x between "
                f"{yoy_check.from_year} and {yoy_check.to_year}."
            ),
            blocking=True,
            fixability="review_only",
            evidence_ids=[_evidence_id(yoy_check.metric, yoy_check.to_year, "yoy_scale")],
        )
    if yoy_check.status in {"warning", "warning_or_block"}:
        return _issue(
            issue_type="yoy_scale_warning",
            severity="warning",
            metric=yoy_check.metric,
            value_years=[yoy_check.from_year, yoy_check.to_year],
            description=(
                f"{yoy_check.metric} YoY magnitude ratio exceeds 5x between "
                f"{yoy_check.from_year} and {yoy_check.to_year}."
            ),
            blocking=False,
            fixability="review_only",
            evidence_ids=[_evidence_id(yoy_check.metric, yoy_check.to_year, "yoy_scale")],
        )
    return None


def _scale_result(
    candidate_spreads: list[CandidateSpreadEvidence],
    yoy_checks: list[YoYScaleEvidence],
) -> ScaleConsistencyResult:
    max_spread = max(
        (
            spread.candidate_spread
            for spread in candidate_spreads
            if spread.candidate_spread is not None
        ),
        default=None,
    )
    max_yoy = max(
        (check.ratio for check in yoy_checks if check.ratio is not None),
        default=None,
    )
    blocking_reasons: list[str] = []
    warning_reasons: list[str] = []
    if any(spread.status == "block" for spread in candidate_spreads):
        blocking_reasons.append("candidate_spread_gt_100x")
    if any(check.status == "block" for check in yoy_checks):
        blocking_reasons.append("yoy_scale_issue")
    if any(spread.status in {"warning", "warning_or_block"} for spread in candidate_spreads):
        warning_reasons.append("candidate_spread_warning")
    if any(check.status in {"warning", "warning_or_block"} for check in yoy_checks):
        warning_reasons.append("yoy_scale_warning")
    if blocking_reasons:
        status = "fail"
    elif warning_reasons:
        status = "warning"
    else:
        status = "pass"
    return ScaleConsistencyResult(
        status=status,
        max_candidate_spread=max_spread,
        max_yoy_magnitude_ratio=max_yoy,
        blocking_reasons=blocking_reasons,
        warning_reasons=warning_reasons,
    )


def _series_status(
    blocking_issues: list[HistoricalSeriesIntegrityIssue],
    warning_issues: list[HistoricalSeriesIntegrityIssue],
) -> IntegrityStatus:
    if blocking_issues:
        return "baseline_not_validatable"
    if warning_issues:
        return "clean_with_warning"
    return "clean"


def _status_confidence(
    status: IntegrityStatus,
    blocking_issues: list[HistoricalSeriesIntegrityIssue],
    warning_issues: list[HistoricalSeriesIntegrityIssue],
) -> float:
    if status == "clean":
        return 0.95
    if status == "clean_with_warning":
        return 0.8
    if status == "missing":
        return 1.0
    if blocking_issues:
        return max(0.55, 0.9 - (len(blocking_issues) * 0.03))
    return max(0.6, 0.8 - (len(warning_issues) * 0.02))


def _status_counts(
    results: list[HistoricalSeriesIntegrityResult],
) -> dict[str, int]:
    counts = {
        "clean": 0,
        "clean_with_warning": 0,
        "baseline_not_validatable": 0,
        "missing": 0,
    }
    for result in results:
        counts[result.status] += 1
    return counts


def _metrics_by_status(
    results: list[HistoricalSeriesIntegrityResult],
) -> dict[str, list[str]]:
    grouped = {
        "clean": [],
        "clean_with_warning": [],
        "baseline_not_validatable": [],
        "missing": [],
    }
    for result in results:
        grouped[result.status].append(result.metric)
    return grouped


def _overall_status(status_counts: dict[str, int]) -> IntegrityStatus:
    if status_counts["baseline_not_validatable"]:
        return "baseline_not_validatable"
    if status_counts["missing"]:
        return "missing"
    if status_counts["clean_with_warning"]:
        return "clean_with_warning"
    return "clean"


def _integrity_evidence(
    *,
    evidence_id: str,
    metric: str,
    value_year: int | None,
    evidence_type: str,
    candidates: list[SeriesValueCandidateEvidence],
    calculations: dict[str, float | int | str | None],
    policy_applied: str,
) -> IntegrityEvidence:
    return IntegrityEvidence(
        evidence_id=evidence_id,
        metric=metric,
        value_year=value_year,
        evidence_type=evidence_type,
        candidate_values=candidates,
        calculations=calculations,
        policy_applied=policy_applied,
    )


def _issue(
    *,
    issue_type: str,
    severity: str,
    metric: str,
    value_years: list[int],
    description: str,
    blocking: bool,
    fixability: str,
    evidence_ids: list[str],
) -> HistoricalSeriesIntegrityIssue:
    return HistoricalSeriesIntegrityIssue(
        issue_type=issue_type,
        severity=severity,  # type: ignore[arg-type]
        metric=metric,
        value_years=value_years,
        description=description,
        blocking=blocking,
        fixability=fixability,  # type: ignore[arg-type]
        evidence_ids=evidence_ids,
    )


def _evidence_id(metric: str, value_year: int | None, evidence_type: str) -> str:
    year = "series" if value_year is None else str(value_year)
    return f"{metric}:{year}:{evidence_type}"


def _scale_status(
    spread: float | None,
    *,
    block_threshold: float = 100.0,
) -> ScaleCheckStatus:
    if spread is None:
        return "not_applicable"
    if spread <= 5:
        return "pass"
    if spread <= 10:
        return "warning"
    if spread <= block_threshold:
        return "warning_or_block"
    return "block"


def _magnitude_spread(values: list[float]) -> float | None:
    non_zero_values = [abs(value) for value in values if value != 0]
    if len(non_zero_values) < 2:
        return None
    return max(non_zero_values) / min(non_zero_values)


def _numeric_value(value: float | int | str) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _normalize_table_type(table_type: str) -> str:
    return table_type.strip().lower()


def _source_class(table_type: str) -> SourceClass:
    normalized = _normalize_table_type(table_type)
    if normalized in _SOURCE_CLASS_PRIMARY_TABLES:
        return "primary_statement"
    if "note" in normalized or "disclosure" in normalized:
        return "note_disclosure"
    if "analysis" in normalized or "ratio" in normalized:
        return "analysis_or_ratio"
    if normalized == "unclassified_table":
        return "unclassified"
    return "supporting_schedule"


def _statement_scope() -> StatementScope:
    return "unknown"
