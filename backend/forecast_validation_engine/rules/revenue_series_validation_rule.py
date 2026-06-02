"""Revenue historical series readiness validation rule."""

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


class RevenueSeriesValidationRule(BaseMetricValidationRule):
    """Determine whether revenue history is eligible for forecast validation."""

    rule_id = "revenue_series_validation"
    category = ValidationCategory.REVENUE
    metric = "revenue"
    required_metrics = ("revenue",)
    minimum_history_years = 1
    requires_forecast_input = False

    def evaluate_metric(
        self,
        context: MetricValidationContext,
    ) -> MetricValidationResult:
        """Return revenue series readiness for admitted revenue gate statuses."""

        gate_result = context.gate_result
        if gate_result.status == "clean":
            outcome = ValidationOutcome.PASS
            summary = "Revenue historical series is clean and admitted."
            warnings: tuple[str, ...] = ()
        elif gate_result.status == "clean_with_warning":
            outcome = ValidationOutcome.WARNING
            summary = "Revenue historical series is admitted with gate warnings."
            warnings = tuple(issue.description for issue in gate_result.warning_issues)
        else:
            # Admission should skip this branch. Keep deterministic direct usage.
            outcome = ValidationOutcome.SKIPPED
            summary = "Revenue historical series is not admitted by the gate."
            warnings = tuple(issue.description for issue in gate_result.blocking_issues)

        evidence = _revenue_evidence(gate_result=gate_result, summary=summary)
        evidence_confidence = _evidence_confidence(gate_result)
        confidence = ValidationConfidence(
            score=min(gate_result.confidence, evidence_confidence),
            rationale=(
                f"gate_confidence={gate_result.confidence:.4f}",
                f"evidence_confidence={evidence_confidence:.4f}",
                "Revenue series rule does not perform growth, CAGR, trend, or plausibility validation.",
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


def _revenue_evidence(
    *,
    gate_result: HistoricalSeriesIntegrityResult,
    summary: str,
) -> ValidationEvidence:
    return ValidationEvidence(
        evidence_id="revenue_series_validation:revenue",
        category=ValidationCategory.REVENUE,
        summary=summary,
        metrics=("revenue",),
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
                citation_id=(
                    f"revenue_pdf_{candidate.value_year}_"
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
            "gate_metric": gate_result.metric,
            "gate_confidence": gate_result.confidence,
            "issue_references": _issue_references(gate_result),
            "candidate_spread_issues": [
                {
                    "value_year": spread.value_year,
                    "candidate_count": spread.candidate_count,
                    "candidate_spread": spread.candidate_spread,
                    "status": spread.status,
                }
                for spread in gate_result.candidate_spread_by_year
            ],
            "source_policy_issues": [
                _issue_reference(issue)
                for issue in gate_result.source_policy_violations
            ],
            "scale_consistency": {
                "status": gate_result.scale_result.status,
                "max_candidate_spread": gate_result.scale_result.max_candidate_spread,
                "max_yoy_magnitude_ratio": (
                    gate_result.scale_result.max_yoy_magnitude_ratio
                ),
                "blocking_reasons": gate_result.scale_result.blocking_reasons,
                "warning_reasons": gate_result.scale_result.warning_reasons,
            },
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
                for candidate in gate_result.selected_series
            ],
            "source": "HistoricalSeriesIntegrityGate",
        },
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


def _evidence_confidence(gate_result: HistoricalSeriesIntegrityResult) -> float:
    if gate_result.selected_series:
        return 1.0
    return 0.7


def _limitations(gate_result: HistoricalSeriesIntegrityResult) -> tuple[str, ...]:
    limitations = []
    if gate_result.status == "clean_with_warning":
        limitations.append("Revenue baseline is admitted with historical gate warnings.")
    if not gate_result.selected_series:
        limitations.append("Revenue selected-series provenance is unavailable.")
    return tuple(limitations)


__all__ = ["RevenueSeriesValidationRule"]
