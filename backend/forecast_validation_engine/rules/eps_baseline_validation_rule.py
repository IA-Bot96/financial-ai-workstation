"""EPS historical baseline validation rule."""

from __future__ import annotations

from forecast_validation_engine.models.forecast_validation import (
    ValidationCategory,
    ValidationCitation,
    ValidationConfidence,
    ValidationEvidence,
    ValidationOutcome,
)
from forecast_validation_engine.models.metric_validation import (
    MetricValidationContext,
    MetricValidationResult,
)
from forecast_validation_engine.rules.metric_validation_rule import (
    BaseMetricValidationRule,
)
from shared.models.historical_series_integrity import (
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
)


class EPSBaselineValidationRule(BaseMetricValidationRule):
    """Validate that EPS historical baseline is admitted for downstream use."""

    rule_id = "eps_baseline_validation"
    category = ValidationCategory.HISTORICAL_BASELINE
    metric = "earnings_per_share"
    required_metrics = ("earnings_per_share",)
    minimum_history_years = 1
    requires_forecast_input = False

    def evaluate_metric(
        self,
        context: MetricValidationContext,
    ) -> MetricValidationResult:
        """Return EPS baseline readiness for admitted EPS gate statuses."""

        gate_result = context.gate_result
        if gate_result.status == "clean":
            outcome = ValidationOutcome.PASS
            summary = "EPS historical baseline is clean and admitted."
            warnings: tuple[str, ...] = ()
        elif gate_result.status == "clean_with_warning":
            outcome = ValidationOutcome.WARNING
            summary = "EPS historical baseline is admitted with gate warnings."
            warnings = tuple(issue.description for issue in gate_result.warning_issues)
        else:
            # Phase 2 admission should prevent this branch from executing. Keep a
            # defensive result so direct rule usage remains deterministic.
            outcome = ValidationOutcome.SKIPPED
            summary = (
                "EPS historical baseline is not admitted by the integrity gate."
            )
            warnings = tuple(issue.description for issue in gate_result.blocking_issues)

        evidence = _eps_evidence(gate_result=gate_result, summary=summary)
        evidence_confidence = _evidence_confidence(gate_result)
        confidence = ValidationConfidence(
            score=min(gate_result.confidence, evidence_confidence),
            rationale=(
                f"gate_confidence={gate_result.confidence:.4f}",
                f"evidence_confidence={evidence_confidence:.4f}",
                "EPS baseline rule does not perform forecast plausibility math.",
            ),
            limitations=_limitations(gate_result),
        )
        return MetricValidationResult(
            metric=self.metric,
            baseline_status=gate_result.status,
            outcome=outcome,
            confidence=confidence,
            rule_confidence=1.0,
            evidence_confidence=evidence_confidence,
            value_years=tuple(gate_result.value_years),
            evidence=(evidence,),
            warnings=warnings,
        )


def _eps_evidence(
    *,
    gate_result: HistoricalSeriesIntegrityResult,
    summary: str,
) -> ValidationEvidence:
    issue_refs = [
        _issue_reference(issue)
        for issue in (*gate_result.blocking_issues, *gate_result.warning_issues)
    ]
    selected_series = [
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
        for candidate in gate_result.selected_series
    ]
    return ValidationEvidence(
        evidence_id="eps_baseline_validation:earnings_per_share",
        category=ValidationCategory.HISTORICAL_BASELINE,
        summary=summary,
        metrics=("earnings_per_share",),
        value_years=tuple(gate_result.value_years),
        historical_baseline_status=gate_result.status,
        calculations={
            "gate_confidence": gate_result.confidence,
            "max_candidate_spread": gate_result.scale_result.max_candidate_spread,
            "max_yoy_magnitude_ratio": (
                gate_result.scale_result.max_yoy_magnitude_ratio
            ),
            "blocking_issue_count": len(gate_result.blocking_issues),
            "warning_issue_count": len(gate_result.warning_issues),
        },
        citations=tuple(
            ValidationCitation(
                citation_id=f"eps_pdf_{candidate.value_year}_{candidate.page_number}",
                page_number=candidate.page_number,
                source_report_year=candidate.source_report_year,
                table_type=candidate.table_type,
            )
            for candidate in gate_result.selected_series
        ),
        provenance={
            "citation_type": "PDF_PROVENANCE",
            "gate_metric": gate_result.metric,
            "gate_confidence": gate_result.confidence,
            "issue_references": issue_refs,
            "selected_series": selected_series,
            "source": "HistoricalSeriesIntegrityGate",
        },
    )


def _issue_reference(issue: HistoricalSeriesIntegrityIssue) -> dict[str, object]:
    return {
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "value_years": issue.value_years,
        "blocking": issue.blocking,
        "evidence_ids": issue.evidence_ids,
    }


def _evidence_confidence(gate_result: HistoricalSeriesIntegrityResult) -> float:
    if gate_result.selected_series:
        return 1.0
    return 0.7


def _limitations(gate_result: HistoricalSeriesIntegrityResult) -> tuple[str, ...]:
    limitations = []
    if gate_result.status == "clean_with_warning":
        limitations.append("EPS baseline is admitted with historical gate warnings.")
    if not gate_result.selected_series:
        limitations.append("EPS selected-series provenance is unavailable.")
    return tuple(limitations)


__all__ = ["EPSBaselineValidationRule"]
