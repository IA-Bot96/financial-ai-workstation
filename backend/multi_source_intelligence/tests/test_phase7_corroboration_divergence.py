"""Tests for MSIL Phase 7 corroboration and divergence."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AnnouncementProvenance,
    AuthorityClass,
    ClaimType,
    ContentClass,
    DivergenceStatus,
    DivergenceType,
    EntityResolutionResult,
    EntityScope,
    EntityType,
    EventType,
    Horizon,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    PDFPageProvenance,
    PayoutProvenance,
    RegulatoryProvenance,
    ResolutionMethod,
    ReviewStatus,
    SourceSnapshotReference,
    SourceType,
    TimeBasis,
)
from multi_source_intelligence.services import (  # noqa: E402
    CorroborationService,
    DivergenceService,
    build_corroboration_audit,
    build_divergence_audit,
)


NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def test_corroboration_groups_independent_origin_event_signals() -> None:
    annual_report_event = _event_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-dividend-2025",
        subject="dividend declared fy2025",
        observation_time=NOW,
    )
    psx_event = _event_signal(
        source_type=SourceType.PSX_ANNOUNCEMENTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="psx-dividend-2025",
        subject="dividend declared fy2025",
        observation_time=NOW + timedelta(hours=1),
    )

    result = CorroborationService().evaluate_signals((annual_report_event, psx_event))

    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.entity_ref == "lucky_cement"
    assert group.independent_origin_count == 2
    assert group.strength == 0.5
    assert group.is_circular is False
    assert group.authority_classes_present == (
        AuthorityClass.AUDITED_ISSUER,
        AuthorityClass.EXCHANGE_OFFICIAL,
    )


def test_corroboration_rejects_same_authority_source_volume() -> None:
    psx_event = _event_signal(
        source_type=SourceType.PSX_ANNOUNCEMENTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="psx-dividend-2025",
        subject="dividend declared fy2025",
    )
    payout_event = _event_signal(
        source_type=SourceType.COMPANY_PAYOUTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="payout-dividend-2025",
        subject="dividend declared fy2025",
    )

    result = CorroborationService().evaluate_signals((psx_event, payout_event))

    assert result.groups == ()
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].reason.value == "same_authority_class"


def test_corroboration_rejects_lineage_descendant_as_circular() -> None:
    annual_report_event = _event_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-capacity-2025",
        subject="capacity commissioned plant x",
        event_type=EventType.CAPACITY_COMMISSIONED,
    )
    psx_echo = _event_signal(
        source_type=SourceType.PSX_ANNOUNCEMENTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="psx-capacity-echo",
        subject="capacity commissioned plant x",
        event_type=EventType.CAPACITY_COMMISSIONED,
        derived_from=("PDF_PAGE:lucky-2025:page:10",),
    )

    result = CorroborationService().evaluate_signals((annual_report_event, psx_echo))

    assert result.groups == ()
    assert result.circularity_rejections == 1
    assert result.rejected_candidates[0].circular is True
    assert result.rejected_candidates[0].reason.value == "lineage_linked"


def test_corroboration_audit_reports_groups_and_circular_rejections() -> None:
    valid_left = _event_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-dividend-2025",
        subject="dividend declared fy2025",
    )
    valid_right = _event_signal(
        source_type=SourceType.PSX_ANNOUNCEMENTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="psx-dividend-2025",
        subject="dividend declared fy2025",
    )
    circular = _event_signal(
        source_type=SourceType.PSX_ANNOUNCEMENTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="psx-capacity-echo",
        subject="capacity commissioned plant x",
        event_type=EventType.CAPACITY_COMMISSIONED,
        derived_from=("PDF_PAGE:lucky-2025:page:10",),
    )
    circular_origin = _event_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-capacity-2025",
        subject="capacity commissioned plant x",
        event_type=EventType.CAPACITY_COMMISSIONED,
    )
    result = CorroborationService().evaluate_signals(
        (valid_left, valid_right, circular, circular_origin)
    )

    audit = build_corroboration_audit(result)

    assert audit["corroboration_groups"] == 1
    assert audit["circularity_rejections"] == 1
    assert audit["independent_origin_checks"]["lineage_checks_performed"] >= 2
    assert audit["corroborated_signals"] == 2


def test_divergence_surfaces_numeric_fact_conflict_with_authority_metadata() -> None:
    annual_report_value = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-payout-value",
        metric_ref="payout_amount",
        value=15,
        subject="dividend payout amount fy2025",
    )
    payout_value = _numeric_signal(
        source_type=SourceType.COMPANY_PAYOUTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="payout-value",
        metric_ref="payout_amount",
        value=10,
        subject="dividend payout amount fy2025",
    )

    result = DivergenceService().evaluate_signals((annual_report_value, payout_value))

    assert len(result.divergences) == 1
    divergence = result.divergences[0]
    assert divergence.divergence_type == DivergenceType.FACT_VS_FACT
    assert divergence.status == DivergenceStatus.SURFACED
    assert divergence.authority_weighting["truth_resolution"] == "not_determined_by_msil"
    assert {divergence.side_a.assertion_value, divergence.side_b.assertion_value} == {
        "15",
        "10",
    }


def test_divergence_preserves_narrative_disagreement() -> None:
    annual_report_claim = _narrative_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        claim_type=ClaimType.REGULATORY_COMPLIANCE,
        record_id="annual-compliance",
        subject="regulatory compliance status",
        assertion_value="compliant",
    )
    secp_claim = _narrative_signal(
        source_type=SourceType.SECP_NOTICES,
        authority_class=AuthorityClass.REGULATORY_INDEPENDENT,
        claim_type=ClaimType.REGULATORY_COMPLIANCE,
        record_id="secp-compliance",
        subject="regulatory compliance status",
        assertion_value="non-compliant",
        observation_time=NOW + timedelta(days=1),
    )

    result = DivergenceService().evaluate_signals((annual_report_claim, secp_claim))

    assert len(result.divergences) == 1
    divergence = result.divergences[0]
    assert divergence.divergence_type == DivergenceType.NARRATIVE_VS_NARRATIVE
    assert divergence.chronology_comparison == "side_a_older"
    assert divergence.authority_weighting["comparison"] == "side_b_higher_authority"


def test_divergence_records_unresolved_when_no_material_conflict() -> None:
    left = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-sales",
        metric_ref="revenue",
        value=100,
        subject="revenue fy2025",
    )
    right = _numeric_signal(
        source_type=SourceType.COMPANY_PAYOUTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="external-sales",
        metric_ref="revenue",
        value=100.5,
        subject="revenue fy2025",
    )

    result = DivergenceService().evaluate_signals((left, right))

    assert result.divergences == ()
    assert len(result.unresolved_candidates) == 1
    assert result.unresolved_candidates[0].reason.value == "no_material_conflict"


def test_divergence_audit_reports_status_authority_and_unresolved_cases() -> None:
    conflict_left = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-payout-value",
        metric_ref="payout_amount",
        value=15,
        subject="dividend payout amount fy2025",
    )
    conflict_right = _numeric_signal(
        source_type=SourceType.COMPANY_PAYOUTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="payout-value",
        metric_ref="payout_amount",
        value=10,
        subject="dividend payout amount fy2025",
    )
    equivalent_left = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        record_id="annual-revenue",
        metric_ref="revenue",
        value=100,
        subject="revenue fy2025",
    )
    equivalent_right = _numeric_signal(
        source_type=SourceType.COMPANY_PAYOUTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        record_id="external-revenue",
        metric_ref="revenue",
        value=100.5,
        subject="revenue fy2025",
    )

    result = DivergenceService().evaluate_signals(
        (conflict_left, conflict_right, equivalent_left, equivalent_right)
    )
    audit = build_divergence_audit(result)

    assert audit["divergences_detected"] == 1
    assert audit["unresolved_divergences"] == 1
    assert audit["surfaced_never_resolved"] is True
    assert audit["status_distribution"] == {"surfaced": 1}
    assert audit["authority_distributions"]["audited_issuer"] >= 1


def _resolution() -> EntityResolutionResult:
    return EntityResolutionResult(
        raw_identifier="LUCK",
        normalized_identifier="luck",
        method=ResolutionMethod.EXACT,
        confidence=1.0,
        review_status=ReviewStatus.RESOLVED,
        resolved_entity_ref="lucky_cement",
        resolved_entity_type=EntityType.COMPANY,
        review_required=False,
    )


def _snapshot(source_type: SourceType, record_id: str) -> SourceSnapshotReference:
    return SourceSnapshotReference(
        snapshot_id=f"snap_{record_id}",
        source_type=source_type,
        capture_timestamp=NOW,
        source_hash=f"sha256:{record_id}",
        snapshot_uri=f"snapshot://{record_id}",
    )


def _event_signal(
    *,
    source_type: SourceType,
    authority_class: AuthorityClass,
    record_id: str,
    subject: str,
    event_type: EventType = EventType.DIVIDEND_DECLARED,
    claim_type: ClaimType = ClaimType.CORPORATE_ACTION_FACT,
    observation_time: datetime = NOW,
    derived_from: tuple[str, ...] = (),
) -> IntelligenceSignal:
    return _signal(
        source_type=source_type,
        authority_class=authority_class,
        claim_type=claim_type,
        record_id=record_id,
        observation_time=observation_time,
        content=IntelligenceSignalContent(
            content_class=ContentClass.CORPORATE_EVENT,
            identity_key=f"{source_type.value}:{record_id}:event",
            event_type=event_type,
            payload={
                "subject": subject,
                "record_id": record_id,
                "derived_from": list(derived_from),
            },
        ),
    )


def _numeric_signal(
    *,
    source_type: SourceType,
    authority_class: AuthorityClass,
    record_id: str,
    metric_ref: str,
    value: float | int,
    subject: str,
    observation_time: datetime = NOW,
) -> IntelligenceSignal:
    return _signal(
        source_type=source_type,
        authority_class=authority_class,
        claim_type=ClaimType.CORPORATE_ACTION_FACT,
        record_id=record_id,
        observation_time=observation_time,
        content=IntelligenceSignalContent(
            content_class=ContentClass.NUMERIC_CLAIM,
            identity_key=f"{source_type.value}:{record_id}:numeric",
            metric_ref=metric_ref,
            value=value,
            unit="PKR/share",
            payload={"subject": subject, "record_id": record_id},
        ),
    )


def _narrative_signal(
    *,
    source_type: SourceType,
    authority_class: AuthorityClass,
    claim_type: ClaimType,
    record_id: str,
    subject: str,
    assertion_value: str,
    observation_time: datetime = NOW,
) -> IntelligenceSignal:
    return _signal(
        source_type=source_type,
        authority_class=authority_class,
        claim_type=claim_type,
        record_id=record_id,
        observation_time=observation_time,
        content=IntelligenceSignalContent(
            content_class=ContentClass.NARRATIVE_CLAIM,
            identity_key=f"{source_type.value}:{record_id}:narrative",
            claim_text=f"{subject}: {assertion_value}",
            normalized_claim_text=f"{subject} {assertion_value}",
            payload={
                "subject": subject,
                "assertion_value": assertion_value,
                "record_id": record_id,
            },
        ),
    )


def _signal(
    *,
    source_type: SourceType,
    authority_class: AuthorityClass,
    claim_type: ClaimType,
    record_id: str,
    observation_time: datetime,
    content: IntelligenceSignalContent,
) -> IntelligenceSignal:
    return IntelligenceSignal(
        entity_ref="lucky_cement",
        entity_scope=EntityScope.COMPANY,
        entity_resolution=_resolution(),
        content=content,
        classification=IntelligenceSignalClassification(
            content_class=content.content_class,
            source_type=source_type,
            claim_type=claim_type,
            authority_class=authority_class,
            creation_eligible=True,
            mapping_confidence=1.0,
            authority_confidence=1.0,
        ),
        metadata=IntelligenceSignalMetadata(
            observation_time=observation_time,
            subject_period="FY2025",
            time_basis=TimeBasis.CALENDAR,
            horizon=Horizon.CURRENT,
            source_independent_of_issuer=source_type == SourceType.SECP_NOTICES,
            verified=True,
            source_record_id=record_id,
            source_lineage_hooks=(f"{source_type.value}:{record_id}",),
        ),
        provenance=_provenance(source_type, record_id),
    )


def _provenance(source_type: SourceType, record_id: str):
    if source_type == SourceType.ANNUAL_REPORT:
        return PDFPageProvenance(
            workbook_fingerprint="wf_lucky_2025",
            page_number=10,
            report_reference="lucky-2025",
            source_report_year=2025,
            source_section="Directors Report",
            source_lineage=(f"annual_report:{record_id}",),
        )
    if source_type == SourceType.PSX_ANNOUNCEMENTS:
        return AnnouncementProvenance(
            announcement_id=record_id,
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
            source_lineage=(f"psx_announcement:{record_id}",),
        )
    if source_type == SourceType.COMPANY_PAYOUTS:
        return PayoutProvenance(
            payout_id=record_id,
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
            source_lineage=(f"company_payout:{record_id}",),
        )
    if source_type == SourceType.SECP_NOTICES:
        return RegulatoryProvenance(
            notice_id=record_id,
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
            source_lineage=(f"secp_notice:{record_id}",),
        )
    raise ValueError(f"Unsupported test source_type: {source_type.value}")
