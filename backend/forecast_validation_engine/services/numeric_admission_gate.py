"""Numeric Admission Gate for FVE multi-source numeric governance."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from forecast_validation_engine.models.numeric_admission import (
    NUMERIC_ADMISSION_POLICY_VERSION,
    NumericAdmissionDecision,
    NumericAdmissionGateResult,
    NumericEvidence,
    NumericEvidenceStatus,
    NumericRole,
)
from multi_source_intelligence.models import (
    ClaimType,
    ContentClass,
    IntelligenceSignal,
    SourceType,
)
from shared.models.historical_series_integrity import (
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityResult,
)


class NumericAdmissionPolicy:
    """Route MSIL numeric claims into FVE numeric roles without changing HSIG."""

    policy_version: str = NUMERIC_ADMISSION_POLICY_VERSION

    def decide(
        self,
        signal: IntelligenceSignal,
        *,
        historical_gate_result: HistoricalSeriesIntegrityGateResult | None = None,
    ) -> NumericAdmissionDecision:
        """Return a deterministic admission decision for one numeric claim."""

        if signal.content.content_class != ContentClass.NUMERIC_CLAIM:
            raise ValueError("NumericAdmissionPolicy only accepts numeric_claim signals.")

        signal_ref = signal.signal_id or ""
        source_type = signal.classification.source_type
        authority_class = signal.classification.authority_class
        claim_type = signal.classification.claim_type

        if _is_reference_only_numeric(signal):
            return NumericAdmissionDecision(
                signal_ref=signal_ref,
                source_type=source_type,
                authority_class=authority_class,
                claim_type=claim_type,
                role=NumericRole.NON_AUTHORITATIVE,
                status=NumericEvidenceStatus.EXCLUDED_NON_AUTHORITATIVE,
                admitted=False,
                can_be_baseline=False,
                integrity_verdict="non_authoritative_excluded",
                reasons=(
                    "reference_only_numeric",
                    "cannot_enter_baseline_or_forecast_math",
                ),
                policy_version=self.policy_version,
            )

        if source_type == SourceType.ANNUAL_REPORT:
            return self._annual_report_baseline_decision(
                signal,
                historical_gate_result=historical_gate_result,
            )

        if source_type == SourceType.COMPANY_PAYOUTS:
            return NumericAdmissionDecision(
                signal_ref=signal_ref,
                source_type=source_type,
                authority_class=authority_class,
                claim_type=claim_type,
                role=NumericRole.EVENT_FACT,
                status=NumericEvidenceStatus.ADMITTED,
                admitted=True,
                can_be_baseline=False,
                integrity_verdict="source_policy_event_fact",
                reasons=("company_payout_event_fact", "not_statement_line_baseline"),
                policy_version=self.policy_version,
            )

        if source_type == SourceType.SECP_NOTICES:
            return NumericAdmissionDecision(
                signal_ref=signal_ref,
                source_type=source_type,
                authority_class=authority_class,
                claim_type=claim_type,
                role=NumericRole.SUPPORTING,
                status=NumericEvidenceStatus.REVALIDATION_TRIGGER,
                admitted=True,
                can_be_baseline=False,
                integrity_verdict="source_policy_revalidation_trigger",
                reasons=("regulatory_numeric_supporting", "may_trigger_revalidation"),
                policy_version=self.policy_version,
            )

        if source_type == SourceType.PSX_ANNOUNCEMENTS:
            role = (
                NumericRole.FORECAST_CONTEXT
                if _is_forecast_context_signal(signal)
                else NumericRole.SUPPORTING
            )
            verdict = (
                "source_policy_forecast_context"
                if role == NumericRole.FORECAST_CONTEXT
                else "source_policy_supporting"
            )
            return NumericAdmissionDecision(
                signal_ref=signal_ref,
                source_type=source_type,
                authority_class=authority_class,
                claim_type=claim_type,
                role=role,
                status=NumericEvidenceStatus.ADMITTED,
                admitted=True,
                can_be_baseline=False,
                integrity_verdict=verdict,
                reasons=("issuer_disclosure_not_standalone_baseline",),
                policy_version=self.policy_version,
            )

        if source_type in {
            SourceType.ANALYSIS_REPORTS,
            SourceType.MARKET_WATCH,
            SourceType.FUTURES_MARKET_WATCH,
        }:
            return NumericAdmissionDecision(
                signal_ref=signal_ref,
                source_type=source_type,
                authority_class=authority_class,
                claim_type=claim_type,
                role=NumericRole.FORECAST_CONTEXT,
                status=NumericEvidenceStatus.ADMITTED,
                admitted=True,
                can_be_baseline=False,
                integrity_verdict="source_policy_forecast_context",
                reasons=("external_forecast_or_market_context_never_baseline",),
                policy_version=self.policy_version,
            )

        if source_type in {
            SourceType.SECTOR_SUMMARY,
            SourceType.COMPANY_OVERVIEW,
        }:
            return NumericAdmissionDecision(
                signal_ref=signal_ref,
                source_type=source_type,
                authority_class=authority_class,
                claim_type=claim_type,
                role=NumericRole.SUPPORTING,
                status=NumericEvidenceStatus.ADMITTED,
                admitted=True,
                can_be_baseline=False,
                integrity_verdict="source_policy_supporting",
                reasons=("contextual_numeric_not_baseline",),
                policy_version=self.policy_version,
            )

        return NumericAdmissionDecision(
            signal_ref=signal_ref,
            source_type=source_type,
            authority_class=authority_class,
            claim_type=claim_type,
            role=NumericRole.NON_AUTHORITATIVE,
            status=NumericEvidenceStatus.EXCLUDED_NON_AUTHORITATIVE,
            admitted=False,
            can_be_baseline=False,
            integrity_verdict="unsupported_or_low_authority_numeric_excluded",
            reasons=("unsupported_numeric_source_for_fve",),
            policy_version=self.policy_version,
        )

    def _annual_report_baseline_decision(
        self,
        signal: IntelligenceSignal,
        *,
        historical_gate_result: HistoricalSeriesIntegrityGateResult | None,
    ) -> NumericAdmissionDecision:
        metric = _metric(signal)
        series_result = _series_result_for_metric(historical_gate_result, metric)
        if series_result is None:
            return NumericAdmissionDecision(
                signal_ref=signal.signal_id or "",
                source_type=signal.classification.source_type,
                authority_class=signal.classification.authority_class,
                claim_type=signal.classification.claim_type,
                role=NumericRole.BASELINE,
                status=NumericEvidenceStatus.SKIPPED_REQUIRED_METRIC_MISSING,
                admitted=False,
                can_be_baseline=False,
                hsig_delegated=True,
                hsig_status=None,
                integrity_verdict="hsig_missing_metric_result",
                reasons=("ocr_historical_value_requires_hsig", "hsig_metric_missing"),
                policy_version=self.policy_version,
            )

        if series_result.status == "clean":
            return _hsig_decision(signal, series_result, NumericEvidenceStatus.ADMITTED)
        if series_result.status == "clean_with_warning":
            return _hsig_decision(
                signal,
                series_result,
                NumericEvidenceStatus.ADMITTED_WITH_WARNING,
            )
        if series_result.status == "missing":
            return _hsig_decision(
                signal,
                series_result,
                NumericEvidenceStatus.SKIPPED_REQUIRED_METRIC_MISSING,
                admitted=False,
            )
        return _hsig_decision(
            signal,
            series_result,
            NumericEvidenceStatus.SKIPPED_BASELINE_NOT_VALIDATABLE,
            admitted=False,
        )


class NumericAdmissionGate:
    """Convert MSIL numeric claims into FVE NumericEvidence records."""

    def __init__(self, policy: NumericAdmissionPolicy | None = None) -> None:
        self._policy = policy or NumericAdmissionPolicy()

    @property
    def policy(self) -> NumericAdmissionPolicy:
        return self._policy

    def evaluate(
        self,
        signals: Iterable[IntelligenceSignal],
        *,
        historical_gate_result: HistoricalSeriesIntegrityGateResult | None = None,
    ) -> NumericAdmissionGateResult:
        """Evaluate all numeric_claim signals and preserve excluded evidence."""

        decisions: list[NumericAdmissionDecision] = []
        evidence: list[NumericEvidence] = []
        ignored_non_numeric = 0

        for signal in signals:
            if signal.content.content_class != ContentClass.NUMERIC_CLAIM:
                ignored_non_numeric += 1
                continue
            decision = self._policy.decide(
                signal,
                historical_gate_result=historical_gate_result,
            )
            decisions.append(decision)
            evidence.append(_numeric_evidence(signal, decision))

        diagnostics = _diagnostics(decisions, evidence, ignored_non_numeric)
        return NumericAdmissionGateResult(
            policy_version=self._policy.policy_version,
            numeric_claims_processed=len(decisions),
            decisions=tuple(decisions),
            evidence=tuple(evidence),
            ignored_non_numeric_signals=ignored_non_numeric,
            diagnostics=diagnostics,
        )


def build_numeric_admission_audit(result: NumericAdmissionGateResult) -> dict[str, Any]:
    """Build the FVE Phase 11 numeric admission audit payload."""

    return {
        "audit_name": "fve_numeric_admission_audit",
        "phase": "FVE Phase 11",
        "policy_version": result.policy_version,
        "numeric_claims_processed": result.numeric_claims_processed,
        "evidence_records_created": len(result.evidence),
        "admission_decisions": result.diagnostics.get("admission_decisions", {}),
        "role_distribution": result.diagnostics.get("role_distribution", {}),
        "source_distribution": result.diagnostics.get("source_distribution", {}),
        "authority_distribution": result.diagnostics.get("authority_distribution", {}),
        "hsig_delegations": result.diagnostics.get("hsig_delegations", 0),
        "baseline_admissions": result.diagnostics.get("baseline_admissions", 0),
        "supporting_evidence_counts": result.diagnostics.get(
            "supporting_evidence_counts", 0
        ),
        "event_fact_counts": result.diagnostics.get("event_fact_counts", 0),
        "forecast_context_counts": result.diagnostics.get("forecast_context_counts", 0),
        "revalidation_trigger_counts": result.diagnostics.get(
            "revalidation_trigger_counts", 0
        ),
        "non_authoritative_exclusions": result.diagnostics.get(
            "non_authoritative_exclusions", 0
        ),
        "reference_only_exclusions": result.diagnostics.get(
            "reference_only_exclusions", 0
        ),
        "external_baseline_admissions": result.diagnostics.get(
            "external_baseline_admissions", 0
        ),
        "analyst_baseline_admissions": result.diagnostics.get(
            "analyst_baseline_admissions", 0
        ),
        "ignored_non_numeric_signals": result.ignored_non_numeric_signals,
        "excluded_signal_refs": [
            item.signal_ref
            for item in result.evidence
            if item.status == NumericEvidenceStatus.EXCLUDED_NON_AUTHORITATIVE
        ],
        "diagnostics": result.diagnostics,
    }


def _hsig_decision(
    signal: IntelligenceSignal,
    series_result: HistoricalSeriesIntegrityResult,
    status: NumericEvidenceStatus,
    *,
    admitted: bool = True,
) -> NumericAdmissionDecision:
    return NumericAdmissionDecision(
        signal_ref=signal.signal_id or "",
        source_type=signal.classification.source_type,
        authority_class=signal.classification.authority_class,
        claim_type=signal.classification.claim_type,
        role=NumericRole.BASELINE,
        status=status,
        admitted=admitted,
        can_be_baseline=admitted,
        hsig_delegated=True,
        hsig_status=series_result.status,
        integrity_verdict=f"hsig_{series_result.status}",
        reasons=("ocr_historical_value_requires_hsig", f"hsig:{series_result.status}"),
        policy_version=NUMERIC_ADMISSION_POLICY_VERSION,
    )


def _numeric_evidence(
    signal: IntelligenceSignal,
    decision: NumericAdmissionDecision,
) -> NumericEvidence:
    value_year = _optional_int(signal.content.payload.get("value_year"))
    source_report_year = _optional_int(signal.content.payload.get("source_report_year"))
    period = _period(signal, value_year)
    supersession_refs = tuple(
        ref
        for ref in (signal.supersedes, signal.superseded_by)
        if ref is not None and str(ref).strip()
    )
    return NumericEvidence(
        signal_ref=signal.signal_id or "",
        value=signal.content.value,
        metric=_metric(signal),
        period=period,
        value_year=value_year,
        source_report_year=source_report_year,
        authority=signal.classification.authority_class,
        source_type=signal.classification.source_type,
        claim_type=signal.classification.claim_type,
        provenance=signal.provenance,
        role=decision.role,
        status=decision.status,
        admitted=decision.admitted,
        can_be_baseline=decision.can_be_baseline,
        integrity_verdict=decision.integrity_verdict,
        hsig_status=decision.hsig_status,
        divergence_refs=signal.divergence_refs,
        supersession_refs=supersession_refs,
        admission_decision=decision,
        metadata={
            "policy_reasons": list(decision.reasons),
            "source_record_id": signal.metadata.source_record_id,
            "creation_eligible": signal.classification.creation_eligible,
            "numeric_reference_only": bool(
                signal.content.payload.get("numeric_reference_only", False)
            ),
        },
        policy_version=decision.policy_version,
    )


def _diagnostics(
    decisions: list[NumericAdmissionDecision],
    evidence: list[NumericEvidence],
    ignored_non_numeric: int,
) -> dict[str, Any]:
    role_distribution = Counter(decision.role.value for decision in decisions)
    status_distribution = Counter(decision.status.value for decision in decisions)
    source_distribution = Counter(decision.source_type.value for decision in decisions)
    authority_distribution = Counter(
        decision.authority_class.value for decision in decisions
    )
    hsig_delegations = sum(1 for decision in decisions if decision.hsig_delegated)
    external_baseline_admissions = sum(
        1
        for decision in decisions
        if decision.can_be_baseline and decision.source_type != SourceType.ANNUAL_REPORT
    )
    analyst_baseline_admissions = sum(
        1
        for decision in decisions
        if decision.can_be_baseline and decision.source_type == SourceType.ANALYSIS_REPORTS
    )
    return {
        "admission_decisions": dict(status_distribution),
        "role_distribution": dict(role_distribution),
        "source_distribution": dict(source_distribution),
        "authority_distribution": dict(authority_distribution),
        "hsig_delegations": hsig_delegations,
        "baseline_admissions": sum(
            1 for decision in decisions if decision.role == NumericRole.BASELINE and decision.admitted
        ),
        "supporting_evidence_counts": role_distribution.get(NumericRole.SUPPORTING.value, 0),
        "event_fact_counts": role_distribution.get(NumericRole.EVENT_FACT.value, 0),
        "forecast_context_counts": role_distribution.get(
            NumericRole.FORECAST_CONTEXT.value, 0
        ),
        "revalidation_trigger_counts": status_distribution.get(
            NumericEvidenceStatus.REVALIDATION_TRIGGER.value, 0
        ),
        "non_authoritative_exclusions": status_distribution.get(
            NumericEvidenceStatus.EXCLUDED_NON_AUTHORITATIVE.value, 0
        ),
        "reference_only_exclusions": sum(
            1
            for item in evidence
            if item.status == NumericEvidenceStatus.EXCLUDED_NON_AUTHORITATIVE
            and item.metadata.get("numeric_reference_only") is True
        ),
        "external_baseline_admissions": external_baseline_admissions,
        "analyst_baseline_admissions": analyst_baseline_admissions,
        "ignored_non_numeric_signals": ignored_non_numeric,
        "admitted_evidence_count": sum(1 for item in evidence if item.admitted),
        "excluded_evidence_count": sum(1 for item in evidence if not item.admitted),
    }


def _is_reference_only_numeric(signal: IntelligenceSignal) -> bool:
    if signal.content.payload.get("authoritative_numeric_value") is True:
        return False
    if signal.content.payload.get("numeric_reference_only") is True:
        return True
    if signal.content.payload.get("not_authoritative_value") is True:
        return True
    return signal.classification.creation_eligible is False


def _is_forecast_context_signal(signal: IntelligenceSignal) -> bool:
    if signal.classification.claim_type == ClaimType.FORWARD_EXPECTATION:
        return True
    return any(
        bool(signal.content.payload.get(key))
        for key in (
            "forecast_context",
            "guidance",
            "analyst_expectation",
            "forward_expectation",
        )
    )


def _series_result_for_metric(
    historical_gate_result: HistoricalSeriesIntegrityGateResult | None,
    metric: str,
) -> HistoricalSeriesIntegrityResult | None:
    if historical_gate_result is None:
        return None
    for result in historical_gate_result.series_results:
        if result.metric == metric:
            return result
    return None


def _metric(signal: IntelligenceSignal) -> str:
    for key in ("canonical_metric", "normalized_metric", "metric"):
        value = signal.content.payload.get(key)
        if value not in (None, ""):
            return str(value)
    return signal.content.metric_ref or "unknown_metric"


def _period(signal: IntelligenceSignal, value_year: int | None) -> str:
    if value_year is not None:
        return str(value_year)
    if signal.metadata.subject_period:
        return signal.metadata.subject_period
    source_report_year = _optional_int(signal.content.payload.get("source_report_year"))
    if source_report_year is not None:
        return str(source_report_year)
    return signal.metadata.observation_time.date().isoformat()


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "NumericAdmissionGate",
    "NumericAdmissionPolicy",
    "build_numeric_admission_audit",
]
