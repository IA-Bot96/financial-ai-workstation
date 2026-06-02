"""Revenue forecast growth validation rule."""

from __future__ import annotations

from statistics import mean
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
    HistoricalSeriesIntegrityResult,
    SeriesValueCandidateEvidence,
)

_REVENUE_METRIC: Final[str] = "revenue"
_MODERATE_DEVIATION_THRESHOLD: Final[float] = 0.10
_GROWTH_RATE_TOLERANCE: Final[float] = 1e-9


class RevenueGrowthValidationRule(ValidationRule):
    """Validate a revenue forecast against historical revenue growth behavior."""

    rule_id = "revenue_growth_validation"
    category = ValidationCategory.REVENUE
    required_metrics = (_REVENUE_METRIC,)
    minimum_history_years = 2
    requires_forecast_input = True

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        """Evaluate forecast revenue growth after framework admission succeeds."""

        gate_result = _gate_result_for_metric(context, _REVENUE_METRIC)
        forecast_input = _revenue_forecast_input(context)
        if gate_result is None:
            return _invalid_result(
                forecast_input=forecast_input or ForecastInput(metric=_REVENUE_METRIC),
                issue_id="revenue_growth_validation:missing_gate_result",
                title="Revenue gate result is missing",
                description="Revenue growth validation requires an admitted revenue baseline.",
                errors=("Revenue gate result is missing.",),
            )
        if forecast_input is None:
            return _invalid_result(
                forecast_input=ForecastInput(metric=_REVENUE_METRIC),
                gate_result=gate_result,
                issue_id="revenue_growth_validation:missing_forecast_input",
                title="Revenue forecast input is missing",
                description="Revenue growth validation requires a revenue forecast input.",
                errors=("Revenue forecast input is missing.",),
            )

        forecast_value = _numeric_value(forecast_input.value)
        forecast_year = forecast_input.forecast_year
        if forecast_value is None or forecast_year is None:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_growth_validation:invalid_forecast_input",
                title="Revenue forecast input is invalid",
                description="Revenue forecast year and numeric value are required.",
                errors=("Revenue forecast year and numeric value are required.",),
            )

        selected_series = _numeric_selected_series(gate_result)
        if len(selected_series) < self.minimum_history_years:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_growth_validation:insufficient_numeric_history",
                title="Revenue numeric history is insufficient",
                description="At least two numeric revenue history years are required.",
                errors=("At least two numeric revenue history years are required.",),
            )

        historical_growth_rates = _historical_growth_rates(selected_series)
        if not historical_growth_rates:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_growth_validation:no_growth_rates",
                title="Revenue growth rates cannot be calculated",
                description="Historical revenue growth cannot be calculated from zero or invalid base values.",
                errors=("Historical revenue growth cannot be calculated.",),
            )

        latest_candidate, latest_value = selected_series[-1]
        forecast_growth_rate = _growth_rate(latest_value, forecast_value)
        if forecast_growth_rate is None:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_growth_validation:invalid_forecast_growth",
                title="Forecast revenue growth cannot be calculated",
                description="Forecast revenue growth cannot be calculated from a zero latest historical value.",
                errors=("Forecast revenue growth cannot be calculated.",),
            )

        min_growth_rate = min(item.growth_rate for item in historical_growth_rates)
        max_growth_rate = max(item.growth_rate for item in historical_growth_rates)
        average_growth_rate = mean(item.growth_rate for item in historical_growth_rates)
        outcome = _growth_outcome(
            forecast_growth_rate=forecast_growth_rate,
            min_growth_rate=min_growth_rate,
            max_growth_rate=max_growth_rate,
        )
        evidence = _growth_evidence(
            forecast_input=forecast_input,
            gate_result=gate_result,
            historical_growth_rates=historical_growth_rates,
            average_growth_rate=average_growth_rate,
            min_growth_rate=min_growth_rate,
            max_growth_rate=max_growth_rate,
            forecast_growth_rate=forecast_growth_rate,
            latest_candidate=latest_candidate,
            latest_value=latest_value,
            outcome=outcome,
        )
        issues = _growth_issues(
            outcome=outcome,
            evidence_id=evidence.evidence_id,
            forecast_year=forecast_year,
            forecast_growth_rate=forecast_growth_rate,
            min_growth_rate=min_growth_rate,
            max_growth_rate=max_growth_rate,
        )
        warnings = tuple(issue.description for issue in issues if not issue.is_blocking)
        rule_confidence = _rule_confidence(outcome)
        evidence_confidence = _evidence_confidence(gate_result)
        confidence = ValidationConfidence(
            score=min(rule_confidence, gate_result.confidence, evidence_confidence),
            rationale=(
                f"rule_confidence={rule_confidence:.4f}",
                f"gate_confidence={gate_result.confidence:.4f}",
                f"evidence_confidence={evidence_confidence:.4f}",
                "Revenue forecast growth compared against admitted historical revenue growth range.",
            ),
            limitations=warnings,
        )

        return ValidationRuleResult(
            rule_id=self.rule_id,
            category=self.category,
            outcome=outcome,
            confidence=confidence,
            rule_confidence=rule_confidence,
            gate_confidence=gate_result.confidence,
            evidence_confidence=evidence_confidence,
            issues=issues,
            evidence=(evidence,),
            warnings=warnings,
        )


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
    for candidate in sorted(
        gate_result.selected_series,
        key=lambda item: item.value_year,
    ):
        value = _numeric_value(candidate.value)
        if value is not None:
            selected.append((candidate, value))
    return selected


def _numeric_value(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
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


def _growth_outcome(
    *,
    forecast_growth_rate: float,
    min_growth_rate: float,
    max_growth_rate: float,
) -> ValidationOutcome:
    if (
        min_growth_rate - _GROWTH_RATE_TOLERANCE
        <= forecast_growth_rate
        <= max_growth_rate + _GROWTH_RATE_TOLERANCE
    ):
        return ValidationOutcome.PASS
    boundary = (
        min_growth_rate
        if forecast_growth_rate < min_growth_rate
        else max_growth_rate
    )
    deviation = abs(forecast_growth_rate - boundary)
    if deviation <= _MODERATE_DEVIATION_THRESHOLD:
        return ValidationOutcome.WARNING
    return ValidationOutcome.FAIL


def _growth_evidence(
    *,
    forecast_input: ForecastInput,
    gate_result: HistoricalSeriesIntegrityResult,
    historical_growth_rates: tuple[GrowthEvidence, ...],
    average_growth_rate: float,
    min_growth_rate: float,
    max_growth_rate: float,
    forecast_growth_rate: float,
    latest_candidate: SeriesValueCandidateEvidence,
    latest_value: float,
    outcome: ValidationOutcome,
) -> ValidationEvidence:
    forecast_year = forecast_input.forecast_year
    forecast_value = _numeric_value(forecast_input.value)
    value_years = list(gate_result.value_years)
    if forecast_year is not None:
        value_years.append(forecast_year)
    return ValidationEvidence(
        evidence_id="revenue_growth_validation:revenue_growth",
        category=ValidationCategory.REVENUE,
        summary=_evidence_summary(outcome),
        metrics=(_REVENUE_METRIC,),
        value_years=tuple(dict.fromkeys(value_years)),
        historical_baseline_status=gate_result.status,
        calculations={
            "average_growth_rate": average_growth_rate,
            "min_growth_rate": min_growth_rate,
            "max_growth_rate": max_growth_rate,
            "forecast_growth_rate": forecast_growth_rate,
            "latest_historical_year": latest_candidate.value_year,
            "latest_historical_value": latest_value,
            "forecast_year": forecast_year,
            "forecast_value": forecast_value,
            "historical_growth_count": len(historical_growth_rates),
        },
        citations=tuple(
            ValidationCitation(
                citation_id=(
                    f"revenue_growth_pdf_{candidate.value_year}_"
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
            "historical_growth_rates": [
                item.model_dump() for item in historical_growth_rates
            ],
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
            "source": "RevenueGrowthValidationRule",
        },
    )


def _evidence_summary(outcome: ValidationOutcome) -> str:
    if outcome == ValidationOutcome.PASS:
        return "Forecast revenue growth is within the historical growth range."
    if outcome == ValidationOutcome.WARNING:
        return "Forecast revenue growth is moderately outside the historical growth range."
    return "Forecast revenue growth is materially outside the historical growth range."


def _growth_issues(
    *,
    outcome: ValidationOutcome,
    evidence_id: str,
    forecast_year: int,
    forecast_growth_rate: float,
    min_growth_rate: float,
    max_growth_rate: float,
) -> tuple[ValidationIssue, ...]:
    if outcome == ValidationOutcome.PASS:
        return ()
    if outcome == ValidationOutcome.WARNING:
        severity = ValidationSeverity.WARNING
        blocking = False
        title = "Revenue forecast growth is moderately outside historical range"
        description = (
            "Forecast revenue growth "
            f"{forecast_growth_rate:.4f} is outside historical range "
            f"{min_growth_rate:.4f} to {max_growth_rate:.4f}, but within the "
            "moderate deviation band."
        )
    else:
        severity = ValidationSeverity.HIGH
        blocking = True
        title = "Revenue forecast growth is materially outside historical range"
        description = (
            "Forecast revenue growth "
            f"{forecast_growth_rate:.4f} is materially outside historical range "
            f"{min_growth_rate:.4f} to {max_growth_rate:.4f}."
        )

    return (
        ValidationIssue(
            issue_id=f"revenue_growth_validation:{outcome.value}",
            category=ValidationCategory.REVENUE,
            severity=severity,
            outcome=outcome,
            title=title,
            description=description,
            affected_metrics=(_REVENUE_METRIC,),
            value_years=(forecast_year,),
            historical_baseline_status=None,
            evidence_ids=(evidence_id,),
            is_blocking=blocking,
            confidence=ValidationConfidence(
                score=1.0,
                rationale=("Revenue growth deviation calculated deterministically.",),
            ),
        ),
    )


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
        rule_id=RevenueGrowthValidationRule.rule_id,
        category=ValidationCategory.REVENUE,
        outcome=ValidationOutcome.FAIL,
        confidence=ValidationConfidence(
            score=1.0,
            rationale=("Revenue growth validation failed structural rule checks.",),
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
        evidence_id="revenue_growth_validation:invalid_input",
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
                    f"revenue_growth_pdf_{candidate.value_year}_"
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
            "source": "RevenueGrowthValidationRule",
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


__all__ = ["RevenueGrowthValidationRule"]
