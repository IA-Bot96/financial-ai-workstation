"""Revenue forecast trend-break validation rule."""

from __future__ import annotations

from statistics import mean, median, stdev
from typing import Final

from forecast_validation_engine.models.forecast_input import ForecastInput
from forecast_validation_engine.models.forecast_validation import (
    ValidationCategory,
    ValidationCitation,
    ValidationConfidence,
    ValidationEvidence,
    ValidationIssue,
    ValidationOutcome,
    ValidationSeverity,
)
from forecast_validation_engine.models.framework import (
    ValidationContext,
    ValidationRuleResult,
)
from forecast_validation_engine.models.revenue_growth import GrowthEvidence
from forecast_validation_engine.services.validation_framework import ValidationRule
from shared.models.historical_series_integrity import (
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
    SeriesValueCandidateEvidence,
)

_REVENUE_METRIC: Final[str] = "revenue"
_MINIMUM_HISTORY_YEARS: Final[int] = 3
_CONSISTENT_DEVIATION_FLOOR: Final[float] = 0.05
_WARNING_DEVIATION_FLOOR: Final[float] = 0.10
_FAIL_DEVIATION_FLOOR: Final[float] = 0.20
_STRONG_DIRECTION_REVERSAL_THRESHOLD: Final[float] = 0.10


class RevenueTrendBreakValidationRule(ValidationRule):
    """Detect material revenue forecast breaks from historical growth patterns."""

    rule_id = "revenue_trend_break_validation"
    category = ValidationCategory.REVENUE
    required_metrics = (_REVENUE_METRIC,)
    minimum_history_years = _MINIMUM_HISTORY_YEARS
    requires_forecast_input = True

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        """Evaluate revenue trend-break risk after framework admission succeeds."""

        gate_result = _gate_result_for_metric(context, _REVENUE_METRIC)
        forecast_input = _revenue_forecast_input(context)
        if gate_result is None:
            return _invalid_result(
                forecast_input=forecast_input or ForecastInput(metric=_REVENUE_METRIC),
                issue_id="revenue_trend_break_validation:missing_gate_result",
                title="Revenue gate result is missing",
                description="Revenue trend-break validation requires an admitted revenue baseline.",
                errors=("Revenue gate result is missing.",),
            )
        if forecast_input is None:
            return _invalid_result(
                forecast_input=ForecastInput(metric=_REVENUE_METRIC),
                gate_result=gate_result,
                issue_id="revenue_trend_break_validation:missing_forecast_input",
                title="Revenue forecast input is missing",
                description="Revenue trend-break validation requires a revenue forecast input.",
                errors=("Revenue forecast input is missing.",),
            )

        forecast_year = forecast_input.forecast_year
        forecast_value = _numeric_value(forecast_input.value)
        if forecast_year is None or forecast_value is None:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_trend_break_validation:invalid_forecast_input",
                title="Revenue forecast input is invalid",
                description="Revenue forecast year and numeric value are required.",
                errors=("Revenue forecast year and numeric value are required.",),
            )

        selected_series = _numeric_selected_series(gate_result)
        if len(selected_series) < self.minimum_history_years:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_trend_break_validation:insufficient_numeric_history",
                title="Revenue numeric history is insufficient",
                description=(
                    "At least three numeric revenue history years are required "
                    "for trend-break validation."
                ),
                errors=("At least three numeric revenue history years are required.",),
            )

        historical_growth_rates = _historical_growth_rates(selected_series)
        if len(historical_growth_rates) < 2:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_trend_break_validation:insufficient_growth_rates",
                title="Revenue growth pattern is insufficient",
                description=(
                    "At least two historical growth observations are required "
                    "for trend-break validation."
                ),
                errors=("At least two historical growth observations are required.",),
            )

        latest_candidate, latest_value = selected_series[-1]
        forecast_growth_rate = _growth_rate(latest_value, forecast_value)
        if forecast_growth_rate is None:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_trend_break_validation:invalid_forecast_growth",
                title="Forecast revenue growth cannot be calculated",
                description=(
                    "Forecast revenue growth cannot be calculated from a zero "
                    "latest historical value."
                ),
                errors=("Forecast revenue growth cannot be calculated.",),
            )

        growth_values = tuple(item.growth_rate for item in historical_growth_rates)
        average_growth_rate = mean(growth_values)
        median_growth_rate = median(growth_values)
        standard_deviation = stdev(growth_values) if len(growth_values) > 1 else None
        growth_volatility = standard_deviation or 0.0
        assessment = _assess_trend_break(
            historical_growth_rates=growth_values,
            forecast_growth_rate=forecast_growth_rate,
            median_growth_rate=median_growth_rate,
            growth_volatility=growth_volatility,
        )
        evidence = _trend_break_evidence(
            forecast_input=forecast_input,
            gate_result=gate_result,
            historical_growth_rates=historical_growth_rates,
            average_growth_rate=average_growth_rate,
            median_growth_rate=median_growth_rate,
            standard_deviation=standard_deviation,
            growth_volatility=growth_volatility,
            forecast_growth_rate=forecast_growth_rate,
            latest_candidate=latest_candidate,
            latest_value=latest_value,
            assessment=assessment,
        )
        issues = _trend_break_issues(
            assessment=assessment,
            evidence_id=evidence.evidence_id,
            forecast_year=forecast_year,
            forecast_growth_rate=forecast_growth_rate,
            median_growth_rate=median_growth_rate,
        )
        warnings = tuple(issue.description for issue in issues if not issue.is_blocking)
        rule_confidence = _rule_confidence(assessment.outcome)
        evidence_confidence = _evidence_confidence(gate_result)
        confidence = ValidationConfidence(
            score=min(rule_confidence, gate_result.confidence, evidence_confidence),
            rationale=(
                f"rule_confidence={rule_confidence:.4f}",
                f"gate_confidence={gate_result.confidence:.4f}",
                f"evidence_confidence={evidence_confidence:.4f}",
                "Revenue forecast growth compared against historical growth pattern and volatility.",
            ),
            limitations=warnings,
        )

        return ValidationRuleResult(
            rule_id=self.rule_id,
            category=self.category,
            outcome=assessment.outcome,
            confidence=confidence,
            rule_confidence=rule_confidence,
            gate_confidence=gate_result.confidence,
            evidence_confidence=evidence_confidence,
            issues=issues,
            evidence=(evidence,),
            warnings=warnings,
        )


class _TrendBreakAssessment:
    """Internal deterministic trend-break decision."""

    def __init__(
        self,
        *,
        outcome: ValidationOutcome,
        trend_break_type: str | None,
        deviation_from_median: float,
        warning_threshold: float,
        fail_threshold: float,
        direction_reversal: bool,
    ) -> None:
        self.outcome = outcome
        self.trend_break_type = trend_break_type
        self.deviation_from_median = deviation_from_median
        self.warning_threshold = warning_threshold
        self.fail_threshold = fail_threshold
        self.direction_reversal = direction_reversal


def _assess_trend_break(
    *,
    historical_growth_rates: tuple[float, ...],
    forecast_growth_rate: float,
    median_growth_rate: float,
    growth_volatility: float,
) -> _TrendBreakAssessment:
    deviation = abs(forecast_growth_rate - median_growth_rate)
    consistent_threshold = max(_CONSISTENT_DEVIATION_FLOOR, growth_volatility)
    warning_threshold = max(_WARNING_DEVIATION_FLOOR, growth_volatility * 2)
    fail_threshold = max(_FAIL_DEVIATION_FLOOR, growth_volatility * 4)
    all_positive = all(value > 0 for value in historical_growth_rates)
    all_negative = all(value < 0 for value in historical_growth_rates)
    direction_reversal = (
        (all_positive and forecast_growth_rate < 0)
        or (all_negative and forecast_growth_rate > 0)
    )
    strong_direction_reversal = (
        (all_positive and forecast_growth_rate <= -_STRONG_DIRECTION_REVERSAL_THRESHOLD)
        or (all_negative and forecast_growth_rate >= _STRONG_DIRECTION_REVERSAL_THRESHOLD)
    )

    if strong_direction_reversal or deviation > fail_threshold:
        outcome = ValidationOutcome.FAIL
    elif direction_reversal or deviation > warning_threshold:
        outcome = ValidationOutcome.WARNING
    elif deviation <= consistent_threshold:
        outcome = ValidationOutcome.PASS
    else:
        outcome = ValidationOutcome.PASS

    return _TrendBreakAssessment(
        outcome=outcome,
        trend_break_type=_trend_break_type(
            outcome=outcome,
            forecast_growth_rate=forecast_growth_rate,
            median_growth_rate=median_growth_rate,
            direction_reversal=direction_reversal,
        ),
        deviation_from_median=deviation,
        warning_threshold=warning_threshold,
        fail_threshold=fail_threshold,
        direction_reversal=direction_reversal,
    )


def _trend_break_type(
    *,
    outcome: ValidationOutcome,
    forecast_growth_rate: float,
    median_growth_rate: float,
    direction_reversal: bool,
) -> str | None:
    if outcome == ValidationOutcome.PASS:
        return None
    if direction_reversal and forecast_growth_rate < 0:
        return "negative_direction_reversal"
    if direction_reversal and forecast_growth_rate > 0:
        return "positive_direction_reversal"
    if forecast_growth_rate > median_growth_rate:
        return "positive_trend_break"
    return "negative_trend_break"


def _gate_result_for_metric(
    context: ValidationContext,
    metric: str,
) -> HistoricalSeriesIntegrityResult | None:
    for result in context.historical_gate_result.series_results:
        if result.metric == metric:
            return result
    return None


def _revenue_forecast_input(context: ValidationContext) -> ForecastInput | None:
    for forecast_input in context.forecast_inputs:
        if _clean_metric(forecast_input.metric) == _REVENUE_METRIC:
            return forecast_input
    return None


def _clean_metric(metric: str | None) -> str | None:
    if metric is None:
        return None
    normalized = metric.strip().lower()
    return normalized or None


def _numeric_selected_series(
    gate_result: HistoricalSeriesIntegrityResult,
) -> list[tuple[SeriesValueCandidateEvidence, float]]:
    selected: list[tuple[SeriesValueCandidateEvidence, float]] = []
    for candidate in sorted(gate_result.selected_series, key=lambda item: item.value_year):
        value = _numeric_value(candidate.value)
        if value is not None:
            selected.append((candidate, value))
    return selected


def _numeric_value(value: float | int | str | None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    cleaned = value.strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _historical_growth_rates(
    selected_series: list[tuple[SeriesValueCandidateEvidence, float]],
) -> tuple[GrowthEvidence, ...]:
    rates: list[GrowthEvidence] = []
    for (previous_candidate, previous_value), (current_candidate, current_value) in zip(
        selected_series,
        selected_series[1:],
        strict=False,
    ):
        growth_rate = _growth_rate(previous_value, current_value)
        if growth_rate is None:
            continue
        rates.append(
            GrowthEvidence(
                metric=_REVENUE_METRIC,
                from_year=previous_candidate.value_year,
                to_year=current_candidate.value_year,
                from_value=previous_value,
                to_value=current_value,
                growth_rate=growth_rate,
            )
        )
    return tuple(rates)


def _growth_rate(previous_value: float, current_value: float) -> float | None:
    if previous_value == 0:
        return None
    return (current_value - previous_value) / abs(previous_value)


def _trend_break_evidence(
    *,
    forecast_input: ForecastInput,
    gate_result: HistoricalSeriesIntegrityResult,
    historical_growth_rates: tuple[GrowthEvidence, ...],
    average_growth_rate: float,
    median_growth_rate: float,
    standard_deviation: float | None,
    growth_volatility: float,
    forecast_growth_rate: float,
    latest_candidate: SeriesValueCandidateEvidence,
    latest_value: float,
    assessment: _TrendBreakAssessment,
) -> ValidationEvidence:
    forecast_year = forecast_input.forecast_year
    forecast_value = _numeric_value(forecast_input.value)
    value_years = list(gate_result.value_years)
    if forecast_year is not None:
        value_years.append(forecast_year)
    return ValidationEvidence(
        evidence_id="revenue_trend_break_validation:revenue_trend_break",
        category=ValidationCategory.REVENUE,
        summary=_evidence_summary(assessment.outcome),
        metrics=(_REVENUE_METRIC,),
        value_years=tuple(dict.fromkeys(value_years)),
        historical_baseline_status=gate_result.status,
        calculations={
            "average_growth_rate": average_growth_rate,
            "median_growth_rate": median_growth_rate,
            "standard_deviation": standard_deviation,
            "growth_volatility": growth_volatility,
            "forecast_growth_rate": forecast_growth_rate,
            "deviation_from_median": assessment.deviation_from_median,
            "warning_threshold": assessment.warning_threshold,
            "fail_threshold": assessment.fail_threshold,
            "latest_historical_year": latest_candidate.value_year,
            "latest_historical_value": latest_value,
            "forecast_year": forecast_year,
            "forecast_value": forecast_value,
            "historical_growth_count": len(historical_growth_rates),
        },
        citations=tuple(
            ValidationCitation(
                citation_id=(
                    f"revenue_trend_break_pdf_{candidate.value_year}_"
                    f"{candidate.page_number}"
                ),
                page_number=candidate.page_number,
                source_report_year=candidate.source_report_year,
                table_type=candidate.table_type,
            )
            for candidate in gate_result.selected_series
        ),
        provenance={
            "citation_type": "PDF_PROVENANCE"
            if gate_result.selected_series
            else "NONE",
            "forecast_metric": forecast_input.metric,
            "forecast_year": forecast_year,
            "forecast_value": forecast_value,
            "forecast_unit": forecast_input.unit,
            "forecast_scale": forecast_input.scale,
            "forecast_source": forecast_input.source,
            "baseline_status": gate_result.status,
            "gate_confidence": gate_result.confidence,
            "trend_break_type": assessment.trend_break_type,
            "direction_reversal": assessment.direction_reversal,
            "historical_growth_rates": [
                item.model_dump() for item in historical_growth_rates
            ],
            "issue_references": _issue_references(gate_result),
            "selected_series": [
                {
                    "value_year": candidate.value_year,
                    "value": candidate.value,
                    "source_report_year": candidate.source_report_year,
                    "page_number": candidate.page_number,
                    "table_type": candidate.table_type,
                    "source_class": candidate.source_class,
                    "statement_scope": candidate.statement_scope,
                    "normalization_confidence": candidate.normalization_confidence,
                    "source_confidence": candidate.source_confidence,
                    "original_metric": candidate.original_metric,
                    "requires_review": candidate.requires_review,
                }
                for candidate in gate_result.selected_series
            ],
            "source": "RevenueTrendBreakValidationRule",
        },
    )


def _evidence_summary(outcome: ValidationOutcome) -> str:
    if outcome == ValidationOutcome.PASS:
        return "Forecast revenue growth is consistent with the historical trend pattern."
    if outcome == ValidationOutcome.WARNING:
        return "Forecast revenue growth shows a moderate trend-break risk."
    return "Forecast revenue growth shows a material trend break."


def _trend_break_issues(
    *,
    assessment: _TrendBreakAssessment,
    evidence_id: str,
    forecast_year: int,
    forecast_growth_rate: float,
    median_growth_rate: float,
) -> tuple[ValidationIssue, ...]:
    if assessment.outcome == ValidationOutcome.PASS:
        return ()
    if assessment.outcome == ValidationOutcome.WARNING:
        severity = ValidationSeverity.WARNING
        blocking = False
        title = "Revenue forecast shows moderate trend-break risk"
        description = (
            "Forecast revenue growth "
            f"{forecast_growth_rate:.4f} deviates from historical median growth "
            f"{median_growth_rate:.4f} by {assessment.deviation_from_median:.4f}."
        )
    else:
        severity = ValidationSeverity.HIGH
        blocking = True
        title = "Revenue forecast shows material trend break"
        description = (
            "Forecast revenue growth "
            f"{forecast_growth_rate:.4f} materially deviates from historical "
            f"median growth {median_growth_rate:.4f}."
        )

    return (
        ValidationIssue(
            issue_id=f"revenue_trend_break_validation:{assessment.outcome.value}",
            category=ValidationCategory.REVENUE,
            severity=severity,
            outcome=assessment.outcome,
            title=title,
            description=description,
            affected_metrics=(_REVENUE_METRIC,),
            value_years=(forecast_year,),
            evidence_ids=(evidence_id,),
            is_blocking=blocking,
            confidence=ValidationConfidence(
                score=1.0,
                rationale=("Revenue trend-break assessment calculated deterministically.",),
            ),
        ),
    )


def _issue_references(
    gate_result: HistoricalSeriesIntegrityResult,
) -> list[dict[str, object]]:
    return [
        _issue_reference(issue)
        for issue in (*gate_result.blocking_issues, *gate_result.warning_issues)
    ]


def _issue_reference(issue: HistoricalSeriesIntegrityIssue) -> dict[str, object]:
    return {
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "value_years": issue.value_years,
        "blocking": issue.blocking,
        "evidence_ids": issue.evidence_ids,
    }


def _invalid_result(
    *,
    forecast_input: ForecastInput,
    issue_id: str,
    title: str,
    description: str,
    errors: tuple[str, ...],
    gate_result: HistoricalSeriesIntegrityResult | None = None,
) -> ValidationRuleResult:
    evidence = _invalid_evidence(
        forecast_input=forecast_input,
        gate_result=gate_result,
        summary=description,
    )
    issue = ValidationIssue(
        issue_id=issue_id,
        category=ValidationCategory.REVENUE,
        severity=ValidationSeverity.HIGH,
        outcome=ValidationOutcome.FAIL,
        title=title,
        description=description,
        affected_metrics=(_REVENUE_METRIC,),
        value_years=(forecast_input.forecast_year,)
        if forecast_input.forecast_year is not None
        else (),
        historical_baseline_status=gate_result.status if gate_result is not None else None,
        evidence_ids=(evidence.evidence_id,),
        is_blocking=True,
        confidence=ValidationConfidence(score=1.0),
    )
    return ValidationRuleResult(
        rule_id=RevenueTrendBreakValidationRule.rule_id,
        category=ValidationCategory.REVENUE,
        outcome=ValidationOutcome.FAIL,
        confidence=ValidationConfidence(
            score=1.0,
            rationale=("Revenue trend-break validation failed structural rule checks.",),
        ),
        rule_confidence=1.0,
        gate_confidence=gate_result.confidence if gate_result is not None else 1.0,
        evidence_confidence=1.0,
        issues=(issue,),
        evidence=(evidence,),
        errors=errors,
    )


def _invalid_evidence(
    *,
    forecast_input: ForecastInput,
    gate_result: HistoricalSeriesIntegrityResult | None,
    summary: str,
) -> ValidationEvidence:
    return ValidationEvidence(
        evidence_id="revenue_trend_break_validation:invalid_input",
        category=ValidationCategory.REVENUE,
        summary=summary,
        metrics=(_REVENUE_METRIC,),
        value_years=(forecast_input.forecast_year,)
        if forecast_input.forecast_year is not None
        else (),
        historical_baseline_status=gate_result.status if gate_result is not None else None,
        calculations={
            "forecast_year": forecast_input.forecast_year,
            "forecast_value": _numeric_value(forecast_input.value),
            "history_year_count": len(gate_result.value_years)
            if gate_result is not None
            else None,
        },
        citations=tuple(
            ValidationCitation(
                citation_id=(
                    f"revenue_trend_break_pdf_{candidate.value_year}_"
                    f"{candidate.page_number}"
                ),
                page_number=candidate.page_number,
                source_report_year=candidate.source_report_year,
                table_type=candidate.table_type,
            )
            for candidate in (gate_result.selected_series if gate_result is not None else [])
        ),
        provenance={
            "citation_type": "PDF_PROVENANCE"
            if gate_result is not None and gate_result.selected_series
            else "NONE",
            "forecast_metric": forecast_input.metric,
            "forecast_year": forecast_input.forecast_year,
            "forecast_value_present": forecast_input.value is not None,
            "baseline_status": gate_result.status if gate_result is not None else None,
            "source": "RevenueTrendBreakValidationRule",
        },
    )


def _rule_confidence(outcome: ValidationOutcome) -> float:
    if outcome == ValidationOutcome.FAIL:
        return 0.85
    if outcome == ValidationOutcome.WARNING:
        return 0.9
    return 1.0


def _evidence_confidence(gate_result: HistoricalSeriesIntegrityResult) -> float:
    if gate_result.selected_series:
        return 1.0
    return 0.7


__all__ = ["RevenueTrendBreakValidationRule"]
