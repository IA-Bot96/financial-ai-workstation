"""Corroboration and divergence services for MSIL Phase 7."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from math import isclose
from typing import Any, Iterable

from multi_source_intelligence.models import (
    AuthorityMatrix,
    ClaimType,
    ContentClass,
    CorroborationCandidateDiagnostic,
    CorroborationGroup,
    CorroborationReference,
    CorroborationResult,
    Divergence,
    DivergenceCandidateDiagnostic,
    DivergenceReference,
    DivergenceResult,
    DivergenceStatus,
    DivergenceType,
    EvidenceComparisonReason,
    IntelligenceSignal,
    ProvenanceType,
    SourceType,
    default_authority_matrix,
)
from multi_source_intelligence.models.entity_registry import normalize_identifier


class CorroborationService:
    """Compute independent-origin corroboration without circular evidence credit."""

    def evaluate_signals(
        self,
        signals: Iterable[IntelligenceSignal],
    ) -> CorroborationResult:
        """Build corroboration groups from compatible signal subjects."""

        references = [_corroboration_reference(signal) for signal in signals]
        grouped: dict[tuple[str, str, str, str | None, str | None, str], list[CorroborationReference]] = (
            defaultdict(list)
        )
        for reference in references:
            grouped[_corroboration_key(reference)].append(reference)

        groups: list[CorroborationGroup] = []
        rejected: list[CorroborationCandidateDiagnostic] = []
        candidates_evaluated = 0
        lineage_checks = 0
        circularity_rejections = 0

        for members in grouped.values():
            if len(members) < 2:
                continue
            members = sorted(members, key=_reference_sort_key)
            selected: list[CorroborationReference] = []
            for candidate in members:
                if not selected:
                    selected.append(candidate)
                    continue

                candidate_accepted = True
                for existing in selected:
                    candidates_evaluated += 1
                    lineage_checks += 1
                    independence = _independence_result(existing, candidate)
                    if independence.reason != EvidenceComparisonReason.INDEPENDENT_ORIGIN:
                        rejected.append(
                            CorroborationCandidateDiagnostic(
                                signal_ref_a=existing.signal_ref,
                                signal_ref_b=candidate.signal_ref,
                                reason=independence.reason,
                                details=independence.details,
                                circular=independence.circular,
                            )
                        )
                        if independence.circular:
                            circularity_rejections += 1
                        candidate_accepted = False
                        break
                if candidate_accepted:
                    selected.append(candidate)

            if len(selected) >= 2:
                authority_classes = tuple(
                    sorted(
                        {reference.authority_class for reference in selected},
                        key=lambda item: item.value,
                    )
                )
                groups.append(
                    CorroborationGroup(
                        entity_ref=selected[0].entity_ref,
                        subject=selected[0].subject,
                        claim_type=selected[0].claim_type,
                        event_type=selected[0].event_type,
                        member_signal_refs=tuple(
                            reference.signal_ref for reference in selected
                        ),
                        member_references=tuple(selected),
                        independent_origin_count=len(authority_classes),
                        authority_classes_present=authority_classes,
                        lineage_checked=True,
                        is_circular=False,
                        strength=_corroboration_strength(len(authority_classes)),
                    )
                )

            for left, right in combinations(members, 2):
                if any(
                    diagnostic.signal_ref_a == left.signal_ref
                    and diagnostic.signal_ref_b == right.signal_ref
                    for diagnostic in rejected
                ):
                    continue
                if left in selected and right in selected:
                    continue
                candidates_evaluated += 1
                lineage_checks += 1
                independence = _independence_result(left, right)
                if independence.reason != EvidenceComparisonReason.INDEPENDENT_ORIGIN:
                    rejected.append(
                        CorroborationCandidateDiagnostic(
                            signal_ref_a=left.signal_ref,
                            signal_ref_b=right.signal_ref,
                            reason=independence.reason,
                            details=independence.details,
                            circular=independence.circular,
                        )
                    )
                    if independence.circular:
                        circularity_rejections += 1

        sorted_groups = tuple(
            sorted(groups, key=lambda group: group.corroboration_group_id or "")
        )
        return CorroborationResult(
            groups=sorted_groups,
            rejected_candidates=tuple(
                sorted(
                    rejected,
                    key=lambda item: (
                        item.signal_ref_a,
                        item.signal_ref_b,
                        item.reason.value,
                    ),
                )
            ),
            candidates_evaluated=candidates_evaluated,
            lineage_checks_performed=lineage_checks,
            circularity_rejections=circularity_rejections,
            diagnostics={
                "subjects_evaluated": len(grouped),
                "signals_evaluated": len(references),
                "corroborated_signals": len(
                    {
                        signal_ref
                        for group in sorted_groups
                        for signal_ref in group.member_signal_refs
                    }
                ),
                "authority_distribution": dict(
                    Counter(
                        reference.authority_class.value for reference in references
                    )
                ),
            },
        )


class DivergenceService:
    """Surface material disagreements while preserving both sides."""

    def __init__(self, authority_matrix: AuthorityMatrix | None = None) -> None:
        self._authority_matrix = authority_matrix or default_authority_matrix()

    def evaluate_signals(
        self,
        signals: Iterable[IntelligenceSignal],
    ) -> DivergenceResult:
        """Detect deterministic divergence candidates among compatible signals."""

        signal_list = tuple(signals)
        grouped: dict[tuple[str, str, str, str | None, str | None, str], list[IntelligenceSignal]] = (
            defaultdict(list)
        )
        for signal in signal_list:
            grouped[_signal_comparison_key(signal)].append(signal)

        divergences: list[Divergence] = []
        unresolved: list[DivergenceCandidateDiagnostic] = []
        candidates_evaluated = 0

        for members in grouped.values():
            if len(members) < 2:
                continue
            for left, right in combinations(sorted(members, key=_signal_sort_key), 2):
                candidates_evaluated += 1
                comparison = _material_conflict(left, right)
                if not comparison["is_conflict"]:
                    unresolved.append(
                        DivergenceCandidateDiagnostic(
                            signal_ref_a=left.signal_id or "",
                            signal_ref_b=right.signal_id or "",
                            reason=comparison["reason"],
                            details=comparison["details"],
                        )
                    )
                    continue

                side_a = _divergence_reference(
                    left,
                    assertion_value=comparison["left_assertion"],
                )
                side_b = _divergence_reference(
                    right,
                    assertion_value=comparison["right_assertion"],
                )
                divergences.append(
                    Divergence(
                        entity_ref=left.entity_ref,
                        subject=_signal_subject(left),
                        divergence_type=_divergence_type(left, right),
                        side_a=side_a,
                        side_b=side_b,
                        authority_weighting=_authority_weighting(
                            side_a,
                            side_b,
                            self._authority_matrix,
                        ),
                        chronology_comparison=_chronology_comparison(side_a, side_b),
                        status=DivergenceStatus.SURFACED,
                        detected_by="msil",
                        pending_corroboration=(
                            side_a.source_type == SourceType.NEWS_SOURCES
                            or side_b.source_type == SourceType.NEWS_SOURCES
                        ),
                    )
                )

        sorted_divergences = tuple(
            sorted(divergences, key=lambda item: item.divergence_id or "")
        )
        return DivergenceResult(
            divergences=sorted_divergences,
            unresolved_candidates=tuple(
                sorted(
                    unresolved,
                    key=lambda item: (
                        item.signal_ref_a,
                        item.signal_ref_b,
                        item.reason.value,
                    ),
                )
            ),
            candidates_evaluated=candidates_evaluated,
            diagnostics={
                "subjects_evaluated": len(grouped),
                "signals_evaluated": len(signal_list),
                "authority_distribution": dict(
                    Counter(
                        signal.classification.authority_class.value
                        for signal in signal_list
                    )
                ),
            },
        )


def build_corroboration_audit(result: CorroborationResult) -> dict[str, Any]:
    """Build the Phase 7 corroboration audit payload."""

    groups = result.groups
    corroborated_signals = sorted(
        {
            signal_ref
            for group in groups
            for signal_ref in group.member_signal_refs
        }
    )
    return {
        "audit_name": "corroboration_audit",
        "phase": "MSIL Phase 7",
        "corroboration_groups": len(groups),
        "group_details": [group.model_dump(mode="json") for group in groups],
        "independent_origin_checks": {
            "candidates_evaluated": result.candidates_evaluated,
            "lineage_checks_performed": result.lineage_checks_performed,
            "passed_groups": len(groups),
            "rejected_candidates": len(result.rejected_candidates),
        },
        "circularity_rejections": result.circularity_rejections,
        "circularity_rejection_details": [
            item.model_dump(mode="json")
            for item in result.rejected_candidates
            if item.circular
        ],
        "corroborated_signals": len(corroborated_signals),
        "corroborated_signal_refs": corroborated_signals,
        "authority_classes_present": sorted(
            {
                authority.value
                for group in groups
                for authority in group.authority_classes_present
            }
        ),
        "strength_distribution": dict(
            Counter(str(group.strength) for group in groups)
        ),
        "diagnostics": result.diagnostics,
    }


def build_divergence_audit(result: DivergenceResult) -> dict[str, Any]:
    """Build the Phase 7 divergence audit payload."""

    divergences = result.divergences
    authority_values = [
        side.authority_class.value
        for divergence in divergences
        for side in (divergence.side_a, divergence.side_b)
    ]
    return {
        "audit_name": "divergence_audit",
        "phase": "MSIL Phase 7",
        "divergences_detected": len(divergences),
        "divergence_details": [
            divergence.model_dump(mode="json") for divergence in divergences
        ],
        "authority_distributions": dict(Counter(authority_values)),
        "chronology_distributions": dict(
            Counter(divergence.chronology_comparison for divergence in divergences)
        ),
        "unresolved_divergences": len(result.unresolved_candidates),
        "unresolved_divergence_details": [
            item.model_dump(mode="json") for item in result.unresolved_candidates
        ],
        "status_distribution": dict(
            Counter(divergence.status.value for divergence in divergences)
        ),
        "surfaced_never_resolved": all(
            divergence.status == DivergenceStatus.SURFACED
            for divergence in divergences
        ),
        "pending_corroboration_count": sum(
            1 for divergence in divergences if divergence.pending_corroboration
        ),
        "diagnostics": result.diagnostics,
    }


def _corroboration_reference(signal: IntelligenceSignal) -> CorroborationReference:
    return CorroborationReference(
        signal_ref=signal.signal_id or "",
        entity_ref=signal.entity_ref,
        subject=_signal_subject(signal),
        content_class=signal.content.content_class,
        source_type=signal.classification.source_type,
        authority_class=signal.classification.authority_class,
        claim_type=signal.classification.claim_type,
        event_type=signal.content.event_type,
        observation_time=signal.metadata.observation_time,
        subject_period=signal.metadata.subject_period,
        time_basis=signal.metadata.time_basis,
        provenance_ref=_provenance_reference(signal),
        source_lineage=_source_lineage(signal),
        derived_from=_payload_tuple(signal, "derived_from"),
        re_reported_from=_payload_tuple(signal, "re_reported_from"),
    )


def _divergence_reference(
    signal: IntelligenceSignal,
    *,
    assertion_value: str,
) -> DivergenceReference:
    claim_summary = (
        signal.content.claim_text
        or signal.content.normalized_claim_text
        or signal.content.metric_ref
        or (signal.content.event_type.value if signal.content.event_type else None)
        or signal.content.content_class.value
    )
    return DivergenceReference(
        signal_ref=signal.signal_id or "",
        entity_ref=signal.entity_ref,
        subject=_signal_subject(signal),
        claim_summary=str(claim_summary),
        assertion_value=assertion_value,
        content_class=signal.content.content_class,
        source_type=signal.classification.source_type,
        authority_class=signal.classification.authority_class,
        claim_type=signal.classification.claim_type,
        event_type=signal.content.event_type,
        observation_time=signal.metadata.observation_time,
        subject_period=signal.metadata.subject_period,
        time_basis=signal.metadata.time_basis,
        provenance_ref=_provenance_reference(signal),
    )


def _signal_comparison_key(
    signal: IntelligenceSignal,
) -> tuple[str, str, str, str | None, str | None, str]:
    return (
        signal.entity_ref,
        _signal_subject(signal),
        signal.classification.claim_type.value,
        signal.content.event_type.value if signal.content.event_type else None,
        signal.metadata.subject_period,
        signal.metadata.time_basis.value,
    )


def _corroboration_key(
    reference: CorroborationReference,
) -> tuple[str, str, str, str | None, str | None, str]:
    return (
        reference.entity_ref,
        reference.subject,
        reference.claim_type.value,
        reference.event_type.value if reference.event_type else None,
        reference.subject_period,
        reference.time_basis.value,
    )


def _signal_subject(signal: IntelligenceSignal) -> str:
    payload_subject = (
        signal.content.payload.get("subject")
        or signal.content.payload.get("claim_subject")
        or signal.content.payload.get("event_subject")
    )
    if payload_subject:
        return normalize_identifier(str(payload_subject))
    if signal.content.content_class == ContentClass.CORPORATE_EVENT:
        return f"event:{signal.content.event_type.value}"
    if signal.content.content_class == ContentClass.NUMERIC_CLAIM:
        return f"metric:{normalize_identifier(signal.content.metric_ref or '')}"
    if signal.content.content_class == ContentClass.MARKET_OBSERVATION:
        return f"market:{normalize_identifier(signal.content.market_series_ref or '')}"
    return f"narrative:{normalize_identifier(signal.content.normalized_claim_text or signal.content.claim_text or '')}"


class _IndependenceResult:
    def __init__(
        self,
        reason: EvidenceComparisonReason,
        details: str,
        *,
        circular: bool = False,
    ) -> None:
        self.reason = reason
        self.details = details
        self.circular = circular


def _independence_result(
    left: CorroborationReference,
    right: CorroborationReference,
) -> _IndependenceResult:
    if left.signal_ref == right.signal_ref:
        return _IndependenceResult(
            EvidenceComparisonReason.DUPLICATE_SIGNAL,
            "same signal cannot corroborate itself",
        )
    if left.authority_class == right.authority_class:
        return _IndependenceResult(
            EvidenceComparisonReason.SAME_AUTHORITY_CLASS,
            "corroboration requires distinct authority classes",
        )
    left_tokens = _lineage_tokens(left)
    right_tokens = _lineage_tokens(right)
    if left_tokens & right_tokens:
        return _IndependenceResult(
            EvidenceComparisonReason.LINEAGE_LINKED,
            "source lineage overlaps",
            circular=True,
        )
    if (set(left.derived_from) | set(left.re_reported_from)) & right_tokens:
        return _IndependenceResult(
            EvidenceComparisonReason.LINEAGE_LINKED,
            "left source is derived from or re-reported from right source",
            circular=True,
        )
    if (set(right.derived_from) | set(right.re_reported_from)) & left_tokens:
        return _IndependenceResult(
            EvidenceComparisonReason.LINEAGE_LINKED,
            "right source is derived from or re-reported from left source",
            circular=True,
        )
    if _same_source_replay(left, right):
        return _IndependenceResult(
            EvidenceComparisonReason.SAME_SOURCE_REPLAY,
            "candidate pair shares the same source/provenance origin",
        )
    return _IndependenceResult(
        EvidenceComparisonReason.INDEPENDENT_ORIGIN,
        "distinct authority classes and no lineage link",
    )


def _same_source_replay(
    left: CorroborationReference,
    right: CorroborationReference,
) -> bool:
    if left.source_type != right.source_type:
        return False
    return bool({left.provenance_ref} & {right.provenance_ref})


def _lineage_tokens(reference: CorroborationReference) -> set[str]:
    return {
        _normalize_lineage_token(token)
        for token in (
            reference.source_lineage
            + reference.derived_from
            + reference.re_reported_from
            + (reference.provenance_ref,)
        )
        if str(token).strip()
    }


def _source_lineage(signal: IntelligenceSignal) -> tuple[str, ...]:
    tokens = []
    tokens.extend(signal.metadata.source_lineage)
    tokens.extend(signal.metadata.source_lineage_hooks)
    tokens.extend(getattr(signal.provenance, "source_lineage", ()))
    tokens.extend(_payload_tuple(signal, "source_lineage"))
    tokens.append(_provenance_reference(signal))
    record_id = signal.metadata.source_record_id or signal.content.payload.get("record_id")
    if record_id:
        tokens.append(f"{signal.classification.source_type.value}:{record_id}")
    return tuple(_normalize_lineage_token(token) for token in tokens if str(token).strip())


def _payload_tuple(signal: IntelligenceSignal, key: str) -> tuple[str, ...]:
    value = signal.content.payload.get(key)
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(_normalize_lineage_token(item) for item in value if str(item).strip())
    return (_normalize_lineage_token(value),)


def _normalize_lineage_token(value: Any) -> str:
    return str(value).strip().lower()


def _material_conflict(
    left: IntelligenceSignal,
    right: IntelligenceSignal,
) -> dict[str, Any]:
    left_assertion = _assertion_value(left)
    right_assertion = _assertion_value(right)
    if left_assertion is None or right_assertion is None:
        return {
            "is_conflict": False,
            "reason": EvidenceComparisonReason.MISSING_ASSERTION_VALUE,
            "details": "one or both signals lack deterministic assertion values",
            "left_assertion": "",
            "right_assertion": "",
        }
    if left.content.content_class == ContentClass.NUMERIC_CLAIM and right.content.content_class == ContentClass.NUMERIC_CLAIM:
        conflict = _numeric_conflict(left_assertion, right_assertion)
    else:
        conflict = normalize_identifier(str(left_assertion)) != normalize_identifier(
            str(right_assertion)
        )
    if not conflict:
        return {
            "is_conflict": False,
            "reason": EvidenceComparisonReason.NO_MATERIAL_CONFLICT,
            "details": "assertions are equivalent within deterministic tolerance",
            "left_assertion": str(left_assertion),
            "right_assertion": str(right_assertion),
        }
    return {
        "is_conflict": True,
        "reason": EvidenceComparisonReason.INDEPENDENT_ORIGIN,
        "details": "materially conflicting assertions",
        "left_assertion": str(left_assertion),
        "right_assertion": str(right_assertion),
    }


def _assertion_value(signal: IntelligenceSignal) -> Any:
    for key in (
        "assertion_value",
        "assertion_state",
        "stance",
        "outcome",
        "status",
        "event_status",
    ):
        value = signal.content.payload.get(key)
        if value not in (None, ""):
            return value
    if signal.content.content_class == ContentClass.NUMERIC_CLAIM:
        return signal.content.value
    return None


def _numeric_conflict(left: Any, right: Any) -> bool:
    try:
        left_value = float(str(left).replace(",", ""))
        right_value = float(str(right).replace(",", ""))
    except ValueError:
        return normalize_identifier(str(left)) != normalize_identifier(str(right))
    if isclose(left_value, right_value, rel_tol=0.01, abs_tol=1e-9):
        return False
    return True


def _divergence_type(
    left: IntelligenceSignal,
    right: IntelligenceSignal,
) -> DivergenceType:
    classes = {left.content.content_class, right.content.content_class}
    if classes == {ContentClass.NARRATIVE_CLAIM}:
        return DivergenceType.NARRATIVE_VS_NARRATIVE
    if ContentClass.MARKET_OBSERVATION in classes:
        return DivergenceType.SENTIMENT_VS_FUNDAMENTALS
    if classes == {ContentClass.NUMERIC_CLAIM, ContentClass.NARRATIVE_CLAIM}:
        return DivergenceType.NARRATIVE_VS_NUMBERS
    return DivergenceType.FACT_VS_FACT


def _authority_weighting(
    side_a: DivergenceReference,
    side_b: DivergenceReference,
    authority_matrix: AuthorityMatrix,
) -> dict[str, Any]:
    side_a_rank = authority_matrix.effective_rank(
        claim_type=side_a.claim_type,
        authority_class=side_a.authority_class,
    )
    side_b_rank = authority_matrix.effective_rank(
        claim_type=side_b.claim_type,
        authority_class=side_b.authority_class,
    )
    if side_a_rank is None or side_b_rank is None:
        comparison = "unranked"
    elif side_a_rank < side_b_rank:
        comparison = "side_a_higher_authority"
    elif side_b_rank < side_a_rank:
        comparison = "side_b_higher_authority"
    else:
        comparison = "equal_claim_scoped_authority"
    return {
        "claim_type": side_a.claim_type.value,
        "side_a_authority_class": side_a.authority_class.value,
        "side_b_authority_class": side_b.authority_class.value,
        "side_a_effective_rank": side_a_rank,
        "side_b_effective_rank": side_b_rank,
        "comparison": comparison,
        "truth_resolution": "not_determined_by_msil",
    }


def _chronology_comparison(
    side_a: DivergenceReference,
    side_b: DivergenceReference,
) -> str:
    if side_a.observation_time < side_b.observation_time:
        return "side_a_older"
    if side_b.observation_time < side_a.observation_time:
        return "side_b_older"
    return "same_observation_time"


def _provenance_reference(signal: IntelligenceSignal) -> str:
    provenance = signal.provenance
    if provenance.provenance_type == ProvenanceType.ANNOUNCEMENT_REF:
        return f"ANNOUNCEMENT_REF:{provenance.announcement_id}:{provenance.snapshot_ref.snapshot_id}"
    if provenance.provenance_type == ProvenanceType.PAYOUT_REF:
        return f"PAYOUT_REF:{provenance.payout_id}:{provenance.snapshot_ref.snapshot_id}"
    if provenance.provenance_type == ProvenanceType.REGULATORY_REF:
        return f"REGULATORY_REF:{provenance.notice_id}:{provenance.snapshot_ref.snapshot_id}"
    if provenance.provenance_type == ProvenanceType.PDF_PAGE:
        report_ref = provenance.report_reference or provenance.workbook_fingerprint
        return f"PDF_PAGE:{report_ref}:page:{provenance.page_number}"
    snapshot_ref = getattr(provenance, "snapshot_ref", None)
    snapshot_id = snapshot_ref.snapshot_id if snapshot_ref else "no_snapshot"
    return f"{provenance.provenance_type.value}:{snapshot_id}:{signal.signal_id}"


def _corroboration_strength(independent_origin_count: int) -> float:
    return round(min(0.95, 1 - (0.5 ** (independent_origin_count - 1))), 4)


def _reference_sort_key(reference: CorroborationReference) -> tuple[str, str, str]:
    return (
        reference.authority_class.value,
        reference.source_type.value,
        reference.signal_ref,
    )


def _signal_sort_key(signal: IntelligenceSignal) -> tuple[str, str, str]:
    return (
        signal.classification.authority_class.value,
        signal.classification.source_type.value,
        signal.signal_id or "",
    )


__all__ = [
    "CorroborationService",
    "DivergenceService",
    "build_corroboration_audit",
    "build_divergence_audit",
]
