"""MSIL NumericEvidence consumption for FVE reporting and plausibility flows."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from forecast_validation_engine.models.forecast_validation import (
    ValidationCategory,
    ValidationEvidence,
)
from forecast_validation_engine.models.forecast_input import ForecastInput
from forecast_validation_engine.models.msil_integration import (
    ForecastContextBenchmark,
    ForecastContextPlausibilityAssessment,
    ForecastContextPlausibilityStatus,
    MSILNumericConfidenceAdjustment,
    MSILNumericEvidenceConsumptionResult,
    MSILNumericInfluence,
)
from forecast_validation_engine.models.numeric_admission import (
    NumericAdmissionGateResult,
    NumericEvidence,
    NumericRole,
)


class MSILNumericEvidenceConsumer:
    """Consume non-baseline MSIL NumericEvidence without altering HSIG."""

    _OWNERSHIP_BOUNDARIES = {
        "fve_modifies_hsig": False,
        "fve_assigns_authority": False,
        "fve_modifies_authority": False,
        "fve_resolves_divergence": False,
        "fve_selects_winning_source": False,
        "supporting_enters_calculations": False,
        "event_fact_enters_calculations": False,
        "forecast_context_enters_calculations": False,
        "supporting_replaces_baseline": False,
        "event_fact_replaces_baseline": False,
        "forecast_context_replaces_baseline": False,
        "forecast_context_influences_hsig": False,
        "forecast_context_influences_historical_validation": False,
        "forecast_context_modifies_validation_truth": False,
        "baseline_delegation_implemented": False,
    }

    def consume(
        self,
        evidence_source: NumericAdmissionGateResult | Iterable[NumericEvidence],
        *,
        forecast_inputs: Iterable[ForecastInput] = (),
    ) -> MSILNumericEvidenceConsumptionResult:
        """Consume MSIL evidence as non-baseline context."""

        evidence_items = _evidence_tuple(evidence_source)
        forecast_input_tuple = tuple(forecast_inputs)
        supporting: list[NumericEvidence] = []
        event_facts: list[NumericEvidence] = []
        forecast_context: list[NumericEvidence] = []
        validation_evidence: list[ValidationEvidence] = []
        confidence_adjustments: list[MSILNumericConfidenceAdjustment] = []
        plausibility_assessments: list[ForecastContextPlausibilityAssessment] = []
        warnings: list[str] = []
        forecast_context_ignored = 0
        baseline_evidence_ignored = 0
        non_authoritative_ignored = 0
        hsig_bypass_attempts = 0

        for item in evidence_items:
            if _is_hsig_bypass_attempt(item):
                hsig_bypass_attempts += 1
                warnings.append(
                    f"HSIG bypass attempt blocked for {item.signal_ref}; "
                    "MSIL Stage 1 cannot create baseline evidence."
                )

            if item.role == NumericRole.SUPPORTING and item.admitted:
                supporting.append(item)
                validation_evidence.append(_validation_evidence(item))
                confidence_adjustments.append(_confidence_adjustment(item))
                warnings.extend(_warnings_for_evidence(item))
                continue

            if item.role == NumericRole.EVENT_FACT and item.admitted:
                event_facts.append(item)
                validation_evidence.append(_validation_evidence(item))
                confidence_adjustments.append(_confidence_adjustment(item))
                warnings.extend(_warnings_for_evidence(item))
                continue

            if item.role == NumericRole.FORECAST_CONTEXT and item.admitted:
                forecast_context.append(item)
                validation_evidence.append(_validation_evidence(item))
                assessment = _plausibility_assessment(item, forecast_input_tuple)
                plausibility_assessments.append(assessment)
                confidence_adjustments.append(
                    _confidence_adjustment(item, plausibility_assessment=assessment)
                )
                warnings.extend(assessment.warnings)
                warnings.extend(_warnings_for_evidence(item))
                continue

            if item.role == NumericRole.FORECAST_CONTEXT:
                forecast_context_ignored += 1
            elif item.role == NumericRole.BASELINE:
                baseline_evidence_ignored += 1
            elif item.role == NumericRole.NON_AUTHORITATIVE:
                non_authoritative_ignored += 1

        divergences_surfaced = sum(
            len(item.divergence_refs)
            for item in (*supporting, *event_facts, *forecast_context)
        )
        consumed_items = (*supporting, *event_facts, *forecast_context)
        diagnostics = {
            "role_distribution": dict(Counter(item.role.value for item in evidence_items)),
            "source_distribution": dict(
                Counter(item.source_type.value for item in evidence_items)
            ),
            "authority_distribution": dict(
                Counter(item.authority.value for item in evidence_items)
            ),
            "authority_classes_consumed": dict(
                Counter(item.authority.value for item in consumed_items)
            ),
            "forecast_context_authority_classes": dict(
                Counter(item.authority.value for item in forecast_context)
            ),
            "forecast_context_authority_labels": dict(
                Counter(
                    _authority_profile(item)["label"]
                    for item in forecast_context
                )
            ),
            "consumed_signal_refs": [item.signal_ref for item in consumed_items],
            "divergent_signal_refs": [
                item.signal_ref
                for item in consumed_items
                if item.divergence_refs
            ],
            "plausibility_status_distribution": dict(
                Counter(assessment.status.value for assessment in plausibility_assessments)
            ),
        }
        return MSILNumericEvidenceConsumptionResult(
            evidence_processed=len(evidence_items),
            supporting_evidence_consumed=len(supporting),
            event_facts_consumed=len(event_facts),
            forecast_context_consumed=len(forecast_context),
            forecast_context_ignored=forecast_context_ignored,
            baseline_evidence_ignored=baseline_evidence_ignored,
            non_authoritative_ignored=non_authoritative_ignored,
            divergences_surfaced=divergences_surfaced,
            confidence_adjustments=tuple(confidence_adjustments),
            plausibility_assessments=tuple(plausibility_assessments),
            warnings=tuple(dict.fromkeys(warnings)),
            validation_evidence=tuple(validation_evidence),
            hsig_bypass_attempts=hsig_bypass_attempts,
            baseline_modifications=0,
            calculations_modified=0,
            ownership_boundaries=dict(self._OWNERSHIP_BOUNDARIES),
            diagnostics=diagnostics,
        )

    def build_audit(
        self,
        result: MSILNumericEvidenceConsumptionResult,
        *,
        audit_scope: str | None = None,
    ) -> dict[str, Any]:
        """Build a deterministic Stage 2 audit payload."""

        return {
            "audit_name": "fve_phase8c_stage2_audit",
            "phase": "MSIL Phase 8C - FVE Integration Stage 2",
            "audit_scope": audit_scope,
            "evidence_processed": result.evidence_processed,
            "supporting_evidence_consumed": result.supporting_evidence_consumed,
            "event_facts_consumed": result.event_facts_consumed,
            "forecast_context_consumed": result.forecast_context_consumed,
            "forecast_context_ignored": result.forecast_context_ignored,
            "baseline_evidence_ignored": result.baseline_evidence_ignored,
            "non_authoritative_ignored": result.non_authoritative_ignored,
            "divergences_surfaced": result.divergences_surfaced,
            "plausibility_assessments_generated": len(
                result.plausibility_assessments
            ),
            "plausibility_assessments": [
                assessment.model_dump(mode="json")
                for assessment in result.plausibility_assessments
            ],
            "confidence_adjustments": [
                adjustment.model_dump(mode="json")
                for adjustment in result.confidence_adjustments
            ],
            "warnings_generated": len(result.warnings),
            "warnings": list(result.warnings),
            "validation_evidence_created": len(result.validation_evidence),
            "hsig_bypass_attempts": result.hsig_bypass_attempts,
            "hsig_influence_attempts": result.hsig_bypass_attempts,
            "baseline_influence_attempts": (
                result.hsig_bypass_attempts + result.baseline_modifications
            ),
            "baseline_modifications": result.baseline_modifications,
            "calculations_modified": result.calculations_modified,
            "ownership_boundary_validation": result.ownership_boundaries,
            "diagnostics": result.diagnostics,
        }

    def write_audit(
        self,
        output_path: str | Path,
        result: MSILNumericEvidenceConsumptionResult,
        *,
        audit_scope: str | None = None,
    ) -> dict[str, Any]:
        """Persist a Stage 1 audit payload."""

        audit = self.build_audit(result, audit_scope=audit_scope)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        return audit


def _evidence_tuple(
    evidence_source: NumericAdmissionGateResult | Iterable[NumericEvidence],
) -> tuple[NumericEvidence, ...]:
    if isinstance(evidence_source, NumericAdmissionGateResult):
        return evidence_source.evidence
    return tuple(evidence_source)


def _is_hsig_bypass_attempt(item: NumericEvidence) -> bool:
    if item.can_be_baseline and not item.admission_decision.hsig_delegated:
        return True
    return item.role in {
        NumericRole.SUPPORTING,
        NumericRole.EVENT_FACT,
        NumericRole.FORECAST_CONTEXT,
    } and (
        item.can_be_baseline or item.admission_decision.hsig_delegated
    )


def _validation_evidence(item: NumericEvidence) -> ValidationEvidence:
    role_label = item.role.value
    value_years = (item.value_year,) if item.value_year is not None else ()
    if item.role == NumericRole.FORECAST_CONTEXT:
        summary = (
            "MSIL forecast-context numeric evidence retained as a plausibility "
            "benchmark only; it is not validation truth."
        )
        plausibility_usage = "allowed"
    else:
        summary = (
            f"MSIL {role_label} numeric evidence retained for FVE reporting only; "
            "it is not a baseline value and is not a validation calculation input."
        )
        plausibility_usage = "reporting_context_only"
    return ValidationEvidence(
        evidence_id=f"msil_numeric:{role_label}:{item.evidence_id or item.signal_ref}",
        category=ValidationCategory.DATA_QUALITY,
        summary=summary,
        metrics=(item.metric,),
        value_years=value_years,
        calculations={
            "benchmark_value" if item.role == NumericRole.FORECAST_CONTEXT else "value": item.value,
            "calculation_usage": "forbidden",
            "baseline_usage": "forbidden",
            "plausibility_usage": plausibility_usage,
        },
        provenance={
            "source": "MSILNumericEvidenceConsumer",
            "signal_ref": item.signal_ref,
            "role": item.role.value,
            "status": item.status.value,
            "source_type": item.source_type.value,
            "authority_class": item.authority.value,
            "claim_type": item.claim_type.value,
            "integrity_verdict": item.integrity_verdict,
            "baseline_usage": "forbidden",
            "calculation_usage": "forbidden",
            "historical_validation_usage": "forbidden",
            "plausibility_usage": plausibility_usage,
            "authority_label": _authority_profile(item)["label"],
            "divergence_refs": item.divergence_refs,
            "supersession_refs": item.supersession_refs,
            "msil_provenance": item.provenance.model_dump(mode="json"),
            "metadata": item.metadata,
        },
    )


def _confidence_adjustment(
    item: NumericEvidence,
    *,
    plausibility_assessment: ForecastContextPlausibilityAssessment | None = None,
) -> MSILNumericConfidenceAdjustment:
    corroboration_refs = _corroboration_refs(item)
    profile = _authority_profile(item)
    if item.role == NumericRole.FORECAST_CONTEXT:
        if item.divergence_refs or (
            plausibility_assessment
            and plausibility_assessment.status
            == ForecastContextPlausibilityStatus.IMPLAUSIBLE_REQUIRES_REVIEW
        ):
            influence = MSILNumericInfluence.DECREASE_CONFIDENCE
            adjustment = -min(0.30, 0.08 * max(1, len(item.divergence_refs)))
            reason = (
                "Forecast-context divergence or severe benchmark deviation lowered "
                "plausibility confidence only."
            )
        elif (
            plausibility_assessment
            and plausibility_assessment.status
            == ForecastContextPlausibilityStatus.PLAUSIBLE_WITH_WARNINGS
        ):
            influence = MSILNumericInfluence.DECREASE_CONFIDENCE
            adjustment = -0.05
            reason = (
                "Forecast-context warning lowered plausibility confidence only."
            )
        else:
            influence = MSILNumericInfluence.REPORTING_CONTEXT_ONLY
            adjustment = 0.0
            reason = (
                "Forecast context retained as plausibility benchmark; no historical "
                "confidence movement."
            )
        applies_to = "plausibility_confidence_only"
    elif item.divergence_refs:
        influence = MSILNumericInfluence.DECREASE_CONFIDENCE
        adjustment = -min(0.20, 0.05 * len(item.divergence_refs))
        reason = "MSIL divergence surfaced; FVE reports contradiction without resolving it."
        applies_to = "reporting_confidence_only"
    elif item.role == NumericRole.SUPPORTING and corroboration_refs:
        influence = MSILNumericInfluence.INCREASE_CONFIDENCE
        adjustment = min(0.05, 0.02 * len(corroboration_refs))
        reason = "MSIL corroboration referenced; FVE may raise reporting confidence only."
        applies_to = "reporting_confidence_only"
    else:
        influence = MSILNumericInfluence.REPORTING_CONTEXT_ONLY
        adjustment = 0.0
        reason = (
            "MSIL evidence retained as reporting context only; no confidence movement."
        )
        applies_to = "reporting_confidence_only"
    return MSILNumericConfidenceAdjustment(
        evidence_id=item.evidence_id or item.signal_ref,
        signal_ref=item.signal_ref,
        metric=item.metric,
        role=item.role.value,
        authority_class=item.authority.value,
        influence=influence,
        adjustment=round(adjustment, 6),
        reason=reason,
        divergence_refs=item.divergence_refs,
        corroboration_refs=corroboration_refs,
        authority_ceiling=profile["ceiling"],
        applies_to=applies_to,
    )


def _corroboration_refs(item: NumericEvidence) -> tuple[str, ...]:
    raw_value = (
        item.metadata.get("corroboration_refs")
        or item.metadata.get("corroboration_groups")
        or ()
    )
    if isinstance(raw_value, str):
        return (raw_value,) if raw_value.strip() else ()
    return tuple(str(value) for value in raw_value if str(value).strip())


def _warnings_for_evidence(item: NumericEvidence) -> tuple[str, ...]:
    warnings: list[str] = []
    if item.divergence_refs:
        warnings.append(
            f"MSIL divergence surfaced for {item.metric} "
            f"({item.role.value}, {item.authority.value}); FVE did not resolve it."
        )
    if item.role == NumericRole.EVENT_FACT:
        warnings.append(
            f"MSIL event fact {item.metric} retained as timeline/reporting context only."
        )
    if item.status.value == "revalidation_trigger":
        warnings.append(
            f"MSIL regulatory supporting evidence for {item.metric} may trigger review; "
            "HSIG verdict was not modified."
        )
    if item.role == NumericRole.FORECAST_CONTEXT:
        profile = _authority_profile(item)
        warnings.append(
            f"MSIL forecast context {item.metric} retained as "
            f"{profile['label']} plausibility benchmark only."
        )
    return tuple(warnings)


def _plausibility_assessment(
    item: NumericEvidence,
    forecast_inputs: tuple[ForecastInput, ...],
) -> ForecastContextPlausibilityAssessment:
    profile = _authority_profile(item)
    matching_input = _matching_forecast_input(item, forecast_inputs)
    forecast_year = _forecast_year(item, matching_input)
    benchmark = ForecastContextBenchmark(
        evidence_id=item.evidence_id or item.signal_ref,
        signal_ref=item.signal_ref,
        metric=item.metric,
        forecast_year=forecast_year,
        benchmark_value=item.value,
        authority_label=profile["label"],
        authority_class=item.authority.value,
        source_type=item.source_type.value,
        uncertainty_indicator=profile["uncertainty"],
        divergence_refs=item.divergence_refs,
        provenance={
            "msil_provenance": item.provenance.model_dump(mode="json"),
            "source_type": item.source_type.value,
            "authority_class": item.authority.value,
            "claim_type": item.claim_type.value,
        },
    )
    warnings: list[str] = []
    deviation_ratio = None
    status = ForecastContextPlausibilityStatus.PLAUSIBLE
    confidence = profile["ceiling"]
    if matching_input is None:
        status = ForecastContextPlausibilityStatus.PLAUSIBLE_WITH_WARNINGS
        confidence = min(confidence, 0.65)
        warnings.append(
            "Forecast context benchmark surfaced, but no matching submitted forecast "
            "was available for comparison."
        )
    else:
        deviation_ratio = _deviation_ratio(matching_input.value, item.value)
        if deviation_ratio is None:
            status = ForecastContextPlausibilityStatus.PLAUSIBLE_WITH_WARNINGS
            confidence = min(confidence, 0.60)
            warnings.append(
                "Forecast context benchmark could not be numerically compared."
            )
        elif deviation_ratio > 0.50:
            status = (
                ForecastContextPlausibilityStatus.IMPLAUSIBLE_REQUIRES_REVIEW
            )
            confidence = min(confidence, 0.45)
            warnings.append(
                "Submitted forecast is materially outside the MSIL benchmark."
            )
        elif deviation_ratio > 0.15:
            status = ForecastContextPlausibilityStatus.PLAUSIBLE_WITH_WARNINGS
            confidence = min(confidence, 0.65)
            warnings.append(
                "Submitted forecast moderately differs from the MSIL benchmark."
            )

    if item.divergence_refs:
        status = max(
            status,
            ForecastContextPlausibilityStatus.PLAUSIBLE_WITH_WARNINGS,
            key=_plausibility_rank,
        )
        confidence = min(confidence, 0.55)
        warnings.append(
            "MSIL forecast-context divergence surfaced; FVE did not resolve it."
        )
    if profile["risk_flag"]:
        warnings.append(profile["risk_flag"])

    return ForecastContextPlausibilityAssessment(
        assessment_id=f"fve_plausibility:{item.evidence_id or item.signal_ref}",
        metric=item.metric,
        forecast_year=forecast_year,
        status=status,
        plausibility_confidence=round(confidence, 6),
        authority_ceiling=profile["ceiling"],
        benchmark_values=(benchmark,),
        submitted_forecast_value=matching_input.value if matching_input else None,
        deviation_ratio=round(deviation_ratio, 6)
        if deviation_ratio is not None
        else None,
        uncertainty_indicator=profile["uncertainty"],
        warnings=tuple(dict.fromkeys(warnings)),
        divergence_refs=item.divergence_refs,
    )


def _authority_profile(item: NumericEvidence) -> dict[str, float | str | None]:
    metadata = item.metadata
    if item.source_type.value == "psx_announcements" or metadata.get("guidance"):
        return {
            "label": "management_guidance",
            "ceiling": 0.85,
            "uncertainty": "issuer_forward_expectation_with_optimism_bias",
            "risk_flag": "Management guidance may carry issuer optimism bias.",
        }
    if metadata.get("analyst_consensus") or metadata.get("consensus"):
        return {
            "label": "analyst_consensus",
            "ceiling": 0.80,
            "uncertainty": "consensus_benchmark_with_herding_risk",
            "risk_flag": "Analyst consensus may include herding or circularity.",
        }
    if item.source_type.value == "analysis_reports":
        return {
            "label": "individual_analyst",
            "ceiling": 0.65,
            "uncertainty": "single_independent_opinion",
            "risk_flag": "Individual analyst view is a benchmark, not truth.",
        }
    if item.source_type.value == "sector_summary":
        return {
            "label": "sector_outlook",
            "ceiling": 0.55,
            "uncertainty": "sector_level_context_not_company_specific",
            "risk_flag": "Sector outlook frames context but does not target the company.",
        }
    if item.source_type.value in {"market_watch", "futures_market_watch"}:
        return {
            "label": "market_sentiment",
            "ceiling": 0.40,
            "uncertainty": "market_revealed_noisy_context",
            "risk_flag": "Market sentiment is noisy and cannot validate forecasts.",
        }
    return {
        "label": item.authority.value,
        "ceiling": 0.60,
        "uncertainty": "forecast_context",
        "risk_flag": None,
    }


def _matching_forecast_input(
    item: NumericEvidence,
    forecast_inputs: tuple[ForecastInput, ...],
) -> ForecastInput | None:
    item_year = _forecast_year(item, None)
    for forecast_input in forecast_inputs:
        if forecast_input.metric != item.metric:
            continue
        if item_year is not None and forecast_input.forecast_year != item_year:
            continue
        return forecast_input
    return None


def _forecast_year(
    item: NumericEvidence,
    forecast_input: ForecastInput | None,
) -> int | None:
    if forecast_input and forecast_input.forecast_year:
        return forecast_input.forecast_year
    raw_value = (
        item.metadata.get("forecast_year")
        or item.metadata.get("target_year")
        or item.value_year
        or item.source_report_year
    )
    try:
        return int(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        return None


def _deviation_ratio(
    forecast_value: float | int | str | None,
    benchmark_value: float | int | str,
) -> float | None:
    forecast_number = _number(forecast_value)
    benchmark_number = _number(benchmark_value)
    if forecast_number is None or benchmark_number in (None, 0):
        return None
    return abs(forecast_number - benchmark_number) / abs(benchmark_number)


def _number(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _plausibility_rank(status: ForecastContextPlausibilityStatus) -> int:
    ranks = {
        ForecastContextPlausibilityStatus.PLAUSIBLE: 0,
        ForecastContextPlausibilityStatus.PLAUSIBLE_WITH_WARNINGS: 1,
        ForecastContextPlausibilityStatus.IMPLAUSIBLE_REQUIRES_REVIEW: 2,
    }
    return ranks[status]


__all__ = ["MSILNumericEvidenceConsumer"]
