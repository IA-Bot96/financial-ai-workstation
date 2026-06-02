"""Forecast input validation rule."""

from __future__ import annotations

from forecast_validation_engine.models.forecast_input import (
    ForecastInput,
    ForecastInputValidationResult,
)
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
from shared.models.historical_series_integrity import HistoricalSeriesIntegrityResult


class ForecastInputValidationRule(ValidationRule):
    """Validate forecast input structure and historical-baseline comparability."""

    rule_id = "forecast_input_validation"
    category = ValidationCategory.DATA_QUALITY
    required_metrics: tuple[str, ...] = ()
    minimum_history_years = 0
    minimum_required_history_years = 2
    requires_forecast_input = False

    def required_metrics_for_context(
        self,
        context: ValidationContext,
    ) -> tuple[str, ...]:
        """Return canonical metrics declared by forecast inputs."""

        metrics: list[str] = []
        for forecast_input in context.forecast_inputs:
            metric = _clean_metric(forecast_input.metric)
            if metric:
                metrics.append(metric)
        return tuple(dict.fromkeys(metrics))

    def evaluate(self, context: ValidationContext) -> ValidationRuleResult:
        """Validate forecast input rows without forecast plausibility logic."""

        input_results = tuple(
            self._validate_input(context, forecast_input, index)
            for index, forecast_input in enumerate(context.forecast_inputs)
        )
        if not input_results:
            input_results = (
                self._empty_input_result(),
            )

        outcome = _aggregate_outcome(tuple(result.outcome for result in input_results))
        issues = tuple(issue for result in input_results for issue in result.issues)
        evidence = tuple(item for result in input_results for item in result.evidence)
        warnings = tuple(warning for result in input_results for warning in result.warnings)
        errors = tuple(error for result in input_results for error in result.errors)
        gate_confidence = min(
            (
                result.gate_confidence
                for result in input_results
                if result.gate_confidence is not None
            ),
            default=1.0,
        )
        rule_confidence = _rule_confidence(outcome)
        evidence_confidence = min(
            (result.confidence.score for result in input_results),
            default=1.0,
        )
        confidence = ValidationConfidence(
            score=min(rule_confidence, gate_confidence, evidence_confidence),
            rationale=(
                f"rule_confidence={rule_confidence:.4f}",
                f"gate_confidence={gate_confidence:.4f}",
                f"evidence_confidence={evidence_confidence:.4f}",
                "Forecast input validation does not perform forecast plausibility math.",
            ),
            limitations=warnings,
        )

        return ValidationRuleResult(
            rule_id=self.rule_id,
            category=self.category,
            outcome=outcome,
            confidence=confidence,
            rule_confidence=rule_confidence,
            gate_confidence=gate_confidence,
            evidence_confidence=evidence_confidence,
            issues=issues,
            evidence=evidence,
            warnings=warnings,
            errors=errors,
        )

    def _validate_input(
        self,
        context: ValidationContext,
        forecast_input: ForecastInput,
        index: int,
    ) -> ForecastInputValidationResult:
        metric = _clean_metric(forecast_input.metric)
        forecast_year = forecast_input.forecast_year
        evidence_id = f"forecast_input_validation:{index}"
        structural_errors: list[str] = []
        if metric is None:
            structural_errors.append("Forecast metric is missing.")
        if forecast_year is None:
            structural_errors.append("Forecast year is missing.")

        if structural_errors:
            evidence = _forecast_input_evidence(
                evidence_id=evidence_id,
                forecast_input=forecast_input,
                metric=metric,
                forecast_year=forecast_year,
                gate_result=None,
                summary="Forecast input is structurally invalid.",
            )
            issue = _issue(
                issue_id=f"{evidence_id}:structurally_invalid",
                title="Forecast input is structurally invalid",
                description=" ".join(structural_errors),
                evidence_id=evidence.evidence_id,
                metric=metric,
                forecast_year=forecast_year,
                outcome=ValidationOutcome.FAIL,
                severity=ValidationSeverity.HIGH,
                blocking=True,
            )
            confidence = ValidationConfidence(
                score=1.0,
                rationale=("Forecast input structural validation failed.",),
            )
            return ForecastInputValidationResult(
                forecast_input=forecast_input,
                metric=metric,
                forecast_year=forecast_year,
                baseline_status=None,
                gate_confidence=None,
                outcome=ValidationOutcome.FAIL,
                can_proceed=False,
                confidence=confidence,
                issues=(issue,),
                evidence=(evidence,),
                errors=tuple(structural_errors),
            )

        gate_result = _gate_result_for_metric(context, metric)
        if gate_result is None or gate_result.status == "missing":
            evidence = _forecast_input_evidence(
                evidence_id=evidence_id,
                forecast_input=forecast_input,
                metric=metric,
                forecast_year=forecast_year,
                gate_result=gate_result,
                summary="Forecast input cannot be evaluated because the historical metric is missing.",
            )
            issue = _issue(
                issue_id=f"{evidence_id}:historical_metric_missing",
                title="Historical metric is missing",
                description=f"Historical baseline is missing for {metric}.",
                evidence_id=evidence.evidence_id,
                metric=metric,
                forecast_year=forecast_year,
                outcome=ValidationOutcome.SKIPPED,
                severity=ValidationSeverity.HIGH,
                blocking=True,
            )
            confidence = ValidationConfidence(
                score=gate_result.confidence if gate_result is not None else 1.0,
                rationale=("Forecast input skipped because baseline metric is missing.",),
            )
            return ForecastInputValidationResult(
                forecast_input=forecast_input,
                metric=metric,
                forecast_year=forecast_year,
                baseline_status="missing",
                gate_confidence=gate_result.confidence if gate_result is not None else None,
                outcome=ValidationOutcome.SKIPPED,
                can_proceed=False,
                confidence=confidence,
                issues=(issue,),
                evidence=(evidence,),
                warnings=("Historical baseline metric is missing.",),
            )

        if gate_result.status == "baseline_not_validatable":
            evidence = _forecast_input_evidence(
                evidence_id=evidence_id,
                forecast_input=forecast_input,
                metric=metric,
                forecast_year=forecast_year,
                gate_result=gate_result,
                summary="Forecast input cannot be evaluated because the historical baseline is not validatable.",
            )
            issue = _issue(
                issue_id=f"{evidence_id}:baseline_not_validatable",
                title="Historical baseline is not validatable",
                description=f"Historical baseline is not validatable for {metric}.",
                evidence_id=evidence.evidence_id,
                metric=metric,
                forecast_year=forecast_year,
                outcome=ValidationOutcome.SKIPPED,
                severity=ValidationSeverity.HIGH,
                blocking=True,
            )
            confidence = ValidationConfidence(
                score=gate_result.confidence,
                rationale=("Forecast input skipped by historical baseline gate.",),
            )
            return ForecastInputValidationResult(
                forecast_input=forecast_input,
                metric=metric,
                forecast_year=forecast_year,
                baseline_status=gate_result.status,
                gate_confidence=gate_result.confidence,
                outcome=ValidationOutcome.SKIPPED,
                can_proceed=False,
                confidence=confidence,
                issues=(issue,),
                evidence=(evidence,),
                warnings=("Historical baseline is not validatable.",),
            )

        warning_messages: list[str] = []
        warning_issues: list[ValidationIssue] = []
        history_year_count = len(gate_result.value_years)
        if history_year_count < self.minimum_required_history_years:
            warning_messages.append(
                "Historical series has insufficient years for downstream "
                f"validation: required {self.minimum_required_history_years}, "
                f"found {history_year_count}."
            )
        if not gate_result.selected_series:
            warning_messages.append("Historical series provenance is unavailable.")
        if gate_result.status == "clean_with_warning":
            warning_messages.extend(issue.description for issue in gate_result.warning_issues)

        outcome = ValidationOutcome.WARNING if warning_messages else ValidationOutcome.PASS
        evidence = _forecast_input_evidence(
            evidence_id=evidence_id,
            forecast_input=forecast_input,
            metric=metric,
            forecast_year=forecast_year,
            gate_result=gate_result,
            summary=(
                "Forecast input can proceed with limitations."
                if outcome == ValidationOutcome.WARNING
                else "Forecast input can proceed."
            ),
        )
        for warning_index, message in enumerate(warning_messages):
            warning_issues.append(
                _issue(
                    issue_id=f"{evidence_id}:warning_{warning_index}",
                    title="Forecast input can proceed with limitations",
                    description=message,
                    evidence_id=evidence.evidence_id,
                    metric=metric,
                    forecast_year=forecast_year,
                    outcome=ValidationOutcome.WARNING,
                    severity=ValidationSeverity.WARNING,
                    blocking=False,
                )
            )
        confidence_score = min(
            gate_result.confidence,
            0.8 if warning_messages else 1.0,
            1.0 if gate_result.selected_series else 0.7,
        )
        confidence = ValidationConfidence(
            score=confidence_score,
            rationale=(
                f"gate_confidence={gate_result.confidence:.4f}",
                "Forecast input metric and year are present.",
            ),
            limitations=tuple(warning_messages),
        )
        return ForecastInputValidationResult(
            forecast_input=forecast_input,
            metric=metric,
            forecast_year=forecast_year,
            baseline_status=gate_result.status,
            gate_confidence=gate_result.confidence,
            outcome=outcome,
            can_proceed=True,
            confidence=confidence,
            issues=tuple(warning_issues),
            evidence=(evidence,),
            warnings=tuple(warning_messages),
        )

    def _empty_input_result(self) -> ForecastInputValidationResult:
        forecast_input = ForecastInput()
        evidence = _forecast_input_evidence(
            evidence_id="forecast_input_validation:empty",
            forecast_input=forecast_input,
            metric=None,
            forecast_year=None,
            gate_result=None,
            summary="No forecast inputs were supplied.",
        )
        issue = _issue(
            issue_id="forecast_input_validation:empty:missing_input",
            title="No forecast inputs supplied",
            description="At least one forecast input is required.",
            evidence_id=evidence.evidence_id,
            metric=None,
            forecast_year=None,
            outcome=ValidationOutcome.FAIL,
            severity=ValidationSeverity.HIGH,
            blocking=True,
        )
        return ForecastInputValidationResult(
            forecast_input=forecast_input,
            metric=None,
            forecast_year=None,
            baseline_status=None,
            gate_confidence=None,
            outcome=ValidationOutcome.FAIL,
            can_proceed=False,
            confidence=ValidationConfidence(score=1.0),
            issues=(issue,),
            evidence=(evidence,),
            errors=("No forecast inputs were supplied.",),
        )


def _forecast_input_evidence(
    *,
    evidence_id: str,
    forecast_input: ForecastInput,
    metric: str | None,
    forecast_year: int | None,
    gate_result: HistoricalSeriesIntegrityResult | None,
    summary: str,
) -> ValidationEvidence:
    return ValidationEvidence(
        evidence_id=evidence_id,
        category=ValidationCategory.DATA_QUALITY,
        summary=summary,
        metrics=(metric,) if metric is not None else (),
        value_years=(forecast_year,) if forecast_year is not None else (),
        historical_baseline_status=gate_result.status if gate_result is not None else None,
        calculations={
            "forecast_year": forecast_year,
            "gate_confidence": gate_result.confidence
            if gate_result is not None
            else None,
            "history_year_count": len(gate_result.value_years)
            if gate_result is not None
            else None,
        },
        citations=tuple(
            ValidationCitation(
                citation_id=f"{metric}_forecast_input_pdf_{candidate.value_year}_{candidate.page_number}",
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
            "forecast_metric": metric,
            "forecast_year": forecast_year,
            "forecast_value_present": forecast_input.value is not None,
            "forecast_unit": forecast_input.unit,
            "forecast_scale": forecast_input.scale,
            "forecast_source": forecast_input.source,
            "baseline_status": gate_result.status if gate_result is not None else None,
            "gate_confidence": gate_result.confidence if gate_result is not None else None,
            "selected_series": [
                {
                    "value_year": candidate.value_year,
                    "value": candidate.value,
                    "source_report_year": candidate.source_report_year,
                    "page_number": candidate.page_number,
                    "table_type": candidate.table_type,
                    "source_class": candidate.source_class,
                    "statement_scope": candidate.statement_scope,
                    "original_metric": candidate.original_metric,
                    "requires_review": candidate.requires_review,
                }
                for candidate in (gate_result.selected_series if gate_result is not None else [])
            ],
            "source": "ForecastInputValidationRule",
        },
    )


def _issue(
    *,
    issue_id: str,
    title: str,
    description: str,
    evidence_id: str,
    metric: str | None,
    forecast_year: int | None,
    outcome: ValidationOutcome,
    severity: ValidationSeverity,
    blocking: bool,
) -> ValidationIssue:
    return ValidationIssue(
        issue_id=issue_id,
        category=ValidationCategory.DATA_QUALITY,
        severity=severity,
        outcome=outcome,
        title=title,
        description=description,
        affected_metrics=(metric,) if metric is not None else (),
        value_years=(forecast_year,) if forecast_year is not None else (),
        evidence_ids=(evidence_id,),
        is_blocking=blocking,
        confidence=ValidationConfidence(score=1.0),
    )


def _gate_result_for_metric(
    context: ValidationContext,
    metric: str,
) -> HistoricalSeriesIntegrityResult | None:
    for result in context.historical_gate_result.series_results:
        if result.metric == metric:
            return result
    return None


def _clean_metric(metric: str | None) -> str | None:
    if metric is None:
        return None
    normalized = metric.strip()
    return normalized or None


def _aggregate_outcome(outcomes: tuple[ValidationOutcome, ...]) -> ValidationOutcome:
    if ValidationOutcome.FAIL in outcomes:
        return ValidationOutcome.FAIL
    if ValidationOutcome.SKIPPED in outcomes and len(set(outcomes)) == 1:
        return ValidationOutcome.SKIPPED
    if ValidationOutcome.WARNING in outcomes or ValidationOutcome.SKIPPED in outcomes:
        return ValidationOutcome.WARNING
    return ValidationOutcome.PASS


def _rule_confidence(outcome: ValidationOutcome) -> float:
    if outcome == ValidationOutcome.PASS:
        return 1.0
    if outcome == ValidationOutcome.WARNING:
        return 0.8
    if outcome == ValidationOutcome.SKIPPED:
        return 1.0
    return 1.0


__all__ = ["ForecastInputValidationRule"]
