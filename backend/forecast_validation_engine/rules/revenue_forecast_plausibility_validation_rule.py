"""Revenue forecast plausibility validation rule."""

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
from forecast_validation_engine.services.validation_framework import ValidationRule
from shared.models.historical_series_integrity import (
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
    SeriesValueCandidateEvidence,
)

_REVENUE_METRIC: Final[str] = "revenue"
_MINIMUM_HISTORY_YEARS: Final[int] = 2
_WARNING_UPSIDE_MULTIPLE: Final[float] = 1.50
_FAIL_UPSIDE_MULTIPLE: Final[float] = 2.00
_WARNING_DOWNSIDE_MULTIPLE: Final[float] = 0.50
_FAIL_DOWNSIDE_MULTIPLE: Final[float] = 0.25
_WARNING_DISTANCE_FROM_LATEST: Final[float] = 0.50
_FAIL_DISTANCE_FROM_LATEST: Final[float] = 1.00
_WARNING_DISTANCE_FROM_AVERAGE: Final[float] = 0.75
_FAIL_DISTANCE_FROM_AVERAGE: Final[float] = 1.50


class RevenueForecastPlausibilityValidationRule(ValidationRule):
    """Validate whether forecast revenue is plausible against historical scale."""

    rule_id = "revenue_forecast_plausibility_validation"
    category = ValidationCategory.FORECAST_PLAUSIBILITY
    required_metrics = (_REVENUE_METRIC,)
    minimum_history_years = _MINIMUM_HISTORY_YEARS
    requires_forecast_input = True

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        """Evaluate revenue forecast plausibility after admission succeeds."""

        gate_result = _gate_result_for_metric(context, _REVENUE_METRIC)
        forecast_input = _revenue_forecast_input(context)
        if gate_result is None:
            return _invalid_result(
                forecast_input=forecast_input or ForecastInput(metric=_REVENUE_METRIC),
                issue_id="revenue_forecast_plausibility_validation:missing_gate_result",
                title="Revenue gate result is missing",
                description="Revenue forecast plausibility requires an admitted revenue baseline.",
                errors=("Revenue gate result is missing.",),
            )
        if forecast_input is None:
            return _invalid_result(
                forecast_input=ForecastInput(metric=_REVENUE_METRIC),
                gate_result=gate_result,
                issue_id="revenue_forecast_plausibility_validation:missing_forecast_input",
                title="Revenue forecast input is missing",
                description="Revenue forecast plausibility requires a revenue forecast input.",
                errors=("Revenue forecast input is missing.",),
            )

        forecast_year = forecast_input.forecast_year
        forecast_value = _numeric_value(forecast_input.value)
        if forecast_year is None or forecast_value is None:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_forecast_plausibility_validation:invalid_forecast_input",
                title="Revenue forecast input is invalid",
                description="Revenue forecast year and numeric value are required.",
                errors=("Revenue forecast year and numeric value are required.",),
            )

        selected_series = _numeric_selected_series(gate_result)
        if len(selected_series) < self.minimum_history_years:
            return _invalid_result(
                forecast_input=forecast_input,
                gate_result=gate_result,
                issue_id="revenue_forecast_plausibility_validation:insufficient_numeric_history",
                title="Revenue numeric history is insufficient",
                description=(
                    "At least two numeric revenue history years are required "
                    "for forecast plausibility validation."
                ),
                errors=("At least two numeric revenue history years are required.",),
            )

        historical_values = tuple(value for _, value in selected_series)
        historical_minimum = min(historical_values)
        historical_maximum = max(historical_values)
        historical_average = mean(historical_values)
        latest_candidate, latest_revenue = selected_series[-1]
        forecast_multiple = _safe_ratio(forecast_value, historical_maximum)
        distance_from_latest = _relative_distance(forecast_value, latest_revenue)
        distance_from_average = _relative_distance(forecast_value, historical_average)

        assessment = _assess_plausibility(
            forecast_value=forecast_value,
            historical_minimum=historical_minimum,
            historical_maximum=historical_maximum,
            historical_average=historical_average,
            forecast_multiple=forecast_multiple,
            distance_from_latest=distance_from_latest,
            distance_from_average=distance_from_average,
        )
        evidence = _plausibility_evidence(
            forecast_input=forecast_input,
            gate_result=gate_result,
            selected_series=selected_series,
            historical_minimum=historical_minimum,
            historical_maximum=historical_maximum,
            historical_average=historical_average,
            latest_candidate=latest_candidate,
            latest_revenue=latest_revenue,
            forecast_value=forecast_value,
            forecast_multiple=forecast_multiple,
            distance_from_latest=distance_from_latest,
            distance_from_average=distance_from_average,
            assessment=assessment,
        )
        issues = _plausibility_issues(
            assessment=assessment,
            evidence_id=evidence.evidence_id,
            forecast_year=forecast_year,
            forecast_value=forecast_value,
            historical_minimum=historical_minimum,
            historical_maximum=historical_maximum,
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
                "Revenue forecast compared against admitted historical revenue scale.",
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


class _PlausibilityAssessment:
    """Internal deterministic revenue plausibility decision."""

    def __init__(
        self,
        *,
        outcome: ValidationOutcome,
        reason: str,
        scale_position: str,
    ) -> None:
        self.outcome = outcome
        self.reason = reason
        self.scale_position = scale_position


def _assess_plausibility(
    *,
    forecast_value: float,
    historical_minimum: float,
    historical_maximum: float,
    historical_average: float,
    forecast_multiple: float | None,
    distance_from_latest: float | None,
    distance_from_average: float | None,
) -> _PlausibilityAssessment:
    scale_position = _scale_position(
        forecast_value=forecast_value,
        historical_minimum=historical_minimum,
        historical_maximum=historical_maximum,
    )
    if forecast_multiple is None:
        return _PlausibilityAssessment(
            outcome=ValidationOutcome.FAIL,
            reason="historical_maximum_zero",
            scale_position=scale_position,
        )

    if (
        forecast_multiple >= _FAIL_UPSIDE_MULTIPLE
        or forecast_multiple <= _FAIL_DOWNSIDE_MULTIPLE
        or _exceeds(distance_from_latest, _FAIL_DISTANCE_FROM_LATEST)
        or _exceeds(distance_from_average, _FAIL_DISTANCE_FROM_AVERAGE)
    ):
        return _PlausibilityAssessment(
            outcome=ValidationOutcome.FAIL,
            reason="materially_outside_historical_scale",
            scale_position=scale_position,
        )
    if (
        forecast_multiple >= _WARNING_UPSIDE_MULTIPLE
        or forecast_multiple <= _WARNING_DOWNSIDE_MULTIPLE
        or _exceeds(distance_from_latest, _WARNING_DISTANCE_FROM_LATEST)
        or _exceeds(distance_from_average, _WARNING_DISTANCE_FROM_AVERAGE)
    ):
        return _PlausibilityAssessment(
            outcome=ValidationOutcome.WARNING,
            reason="moderately_outside_historical_scale",
            scale_position=scale_position,
        )
    return _PlausibilityAssessment(
        outcome=ValidationOutcome.PASS,
        reason="aligned_with_historical_scale",
        scale_position=scale_position,
    )


def _scale_position(
    *,
    forecast_value: float,
    historical_minimum: float,
    historical_maximum: float,
) -> str:
    if forecast_value > historical_maximum:
        return "above_historical_maximum"
    if forecast_value < historical_minimum:
        return "below_historical_minimum"
    return "within_historical_range"


def _exceeds(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _relative_distance(value: float, anchor: float) -> float | None:
    if anchor == 0:
        return None
    return abs(value - anchor) / abs(anchor)


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


def _plausibility_evidence(
    *,
    forecast_input: ForecastInput,
    gate_result: HistoricalSeriesIntegrityResult,
    selected_series: list[tuple[SeriesValueCandidateEvidence, float]],
    historical_minimum: float,
    historical_maximum: float,
    historical_average: float,
    latest_candidate: SeriesValueCandidateEvidence,
    latest_revenue: float,
    forecast_value: float,
    forecast_multiple: float | None,
    distance_from_latest: float | None,
    distance_from_average: float | None,
    assessment: _PlausibilityAssessment,
) -> ValidationEvidence:
    forecast_year = forecast_input.forecast_year
    value_years = list(gate_result.value_years)
    if forecast_year is not None:
        value_years.append(forecast_year)
    return ValidationEvidence(
        evidence_id="revenue_forecast_plausibility_validation:revenue_plausibility",
        category=ValidationCategory.FORECAST_PLAUSIBILITY,
        summary=_evidence_summary(assessment.outcome),
        metrics=(_REVENUE_METRIC,),
        value_years=tuple(dict.fromkeys(value_years)),
        historical_baseline_status=gate_result.status,
        calculations={
            "historical_minimum": historical_minimum,
            "historical_maximum": historical_maximum,
            "historical_average": historical_average,
            "latest_revenue": latest_revenue,
            "latest_historical_year": latest_candidate.value_year,
            "forecast_year": forecast_year,
            "forecast_revenue": forecast_value,
            "forecast_multiple": forecast_multiple,
            "distance_from_latest": distance_from_latest,
            "distance_from_average": distance_from_average,
            "historical_value_count": len(selected_series),
        },
        citations=tuple(
            ValidationCitation(
                citation_id=(
                    f"revenue_plausibility_pdf_{candidate.value_year}_"
                    f"{candidate.page_number}"
                ),
                page_number=candidate.page_number,
                source_report_year=candidate.source_report_year,
                table_type=candidate.table_type,
            )
            for candidate, _ in selected_series
        ),
        provenance={
            "citation_type": "PDF_PROVENANCE" if selected_series else "NONE",
            "forecast_metric": forecast_input.metric,
            "forecast_year": forecast_year,
            "forecast_value": forecast_value,
            "forecast_unit": forecast_input.unit,
            "forecast_scale": forecast_input.scale,
            "forecast_source": forecast_input.source,
            "baseline_status": gate_result.status,
            "gate_confidence": gate_result.confidence,
            "plausibility_reason": assessment.reason,
            "scale_position": assessment.scale_position,
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
                for candidate, _ in selected_series
            ],
            "source": "RevenueForecastPlausibilityValidationRule",
        },
    )


def _evidence_summary(outcome: ValidationOutcome) -> str:
    if outcome == ValidationOutcome.PASS:
        return "Forecast revenue is aligned with historical revenue scale."
    if outcome == ValidationOutcome.WARNING:
        return "Forecast revenue is moderately outside historical revenue scale."
    return "Forecast revenue is materially outside historical revenue scale."


def _plausibility_issues(
    *,
    assessment: _PlausibilityAssessment,
    evidence_id: str,
    forecast_year: int,
    forecast_value: float,
    historical_minimum: float,
    historical_maximum: float,
) -> tuple[ValidationIssue, ...]:
    if assessment.outcome == ValidationOutcome.PASS:
        return ()
    if assessment.outcome == ValidationOutcome.WARNING:
        severity = ValidationSeverity.WARNING
        blocking = False
        title = "Revenue forecast is moderately outside historical scale"
        description = (
            f"Forecast revenue {forecast_value:.4f} is moderately outside "
            f"historical scale {historical_minimum:.4f} to {historical_maximum:.4f}."
        )
    else:
        severity = ValidationSeverity.HIGH
        blocking = True
        title = "Revenue forecast is materially outside historical scale"
        description = (
            f"Forecast revenue {forecast_value:.4f} is materially outside "
            f"historical scale {historical_minimum:.4f} to {historical_maximum:.4f}."
        )

    return (
        ValidationIssue(
            issue_id=f"revenue_forecast_plausibility_validation:{assessment.outcome.value}",
            category=ValidationCategory.FORECAST_PLAUSIBILITY,
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
                rationale=("Revenue scale plausibility calculated deterministically.",),
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
        category=ValidationCategory.FORECAST_PLAUSIBILITY,
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
        rule_id=RevenueForecastPlausibilityValidationRule.rule_id,
        category=ValidationCategory.FORECAST_PLAUSIBILITY,
        outcome=ValidationOutcome.FAIL,
        confidence=ValidationConfidence(
            score=1.0,
            rationale=("Revenue forecast plausibility failed structural rule checks.",),
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
        evidence_id="revenue_forecast_plausibility_validation:invalid_input",
        category=ValidationCategory.FORECAST_PLAUSIBILITY,
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
                    f"revenue_plausibility_pdf_{candidate.value_year}_"
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
            "source": "RevenueForecastPlausibilityValidationRule",
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


__all__ = ["RevenueForecastPlausibilityValidationRule"]
