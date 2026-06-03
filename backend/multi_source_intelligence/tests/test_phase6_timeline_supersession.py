"""Tests for MSIL Phase 6 timeline and supersession services."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AuthorityClass,
    ClaimType,
    CorporateEvent,
    EventType,
    SourceSnapshotReference,
    SourceType,
    SupersessionReason,
    TimeBasis,
)
from multi_source_intelligence.services import (  # noqa: E402
    CompanyPayoutAdapter,
    PSXAnnouncementAdapter,
    SECPNoticeAdapter,
    SupersessionService,
    TimelineAssemblyService,
    build_timeline_audit,
)


NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def _snapshot(source_type: SourceType, snapshot_id: str) -> SourceSnapshotReference:
    return SourceSnapshotReference(
        snapshot_id=snapshot_id,
        source_type=source_type,
        capture_timestamp=NOW,
        source_hash=f"sha256:{snapshot_id}",
        snapshot_uri=f"snapshot://{snapshot_id}",
    )


def _psx_record(**overrides) -> dict:
    payload = {
        "announcement_id": "psx-ann-001",
        "issuer_identifier": "LUCK",
        "title": "Financial results announced",
        "body": "Board announced annual results for Lucky Cement.",
        "announcement_time": NOW,
        "event_type": EventType.RESULTS_ANNOUNCED,
        "snapshot_ref": _snapshot(SourceType.PSX_ANNOUNCEMENTS, "snap_psx_001"),
        "retrieved_at": NOW,
        "source_url": "https://psx.example.test/announcements/psx-ann-001",
    }
    payload.update(overrides)
    return payload


def _payout_record(**overrides) -> dict:
    payload = {
        "payout_id": "payout-001",
        "issuer_identifier": "LUCK",
        "title": "Final cash dividend",
        "body": "Final dividend declared.",
        "payout_time": NOW,
        "payout_type": EventType.DIVIDEND_DECLARED,
        "amount": "15.00",
        "unit": "PKR/share",
        "snapshot_ref": _snapshot(SourceType.COMPANY_PAYOUTS, "snap_payout_001"),
        "retrieved_at": NOW,
        "source_url": "https://psx.example.test/payouts/payout-001",
    }
    payload.update(overrides)
    return payload


def _secp_record(**overrides) -> dict:
    payload = {
        "notice_id": "secp-001",
        "issuer_identifier": "Lucky Cement Limited",
        "title": "SECP action notice",
        "body": "SECP issued a compliance notice.",
        "notice_time": NOW,
        "event_type": EventType.SECP_ACTION,
        "snapshot_ref": _snapshot(SourceType.SECP_NOTICES, "snap_secp_001"),
        "retrieved_at": NOW,
        "source_url": "https://secp.example.test/notices/secp-001",
    }
    payload.update(overrides)
    return payload


def test_timeline_assembly_creates_events_only_from_corporate_event_signals() -> None:
    result = PSXAnnouncementAdapter().adapt_records([_psx_record()])

    assembly = TimelineAssemblyService().assemble(result.signals)

    assert len(assembly.events) == 1
    assert len(assembly.timeline_entries) == 1
    assert len(assembly.timelines) == 1
    assert len(assembly.ignored_signal_refs) == 1
    assert assembly.events[0].event_type == EventType.RESULTS_ANNOUNCED
    assert len(assembly.events[0].narrative_refs) == 1
    assert assembly.events[0].numeric_claim_refs == ()
    assert assembly.chronology_validation_passed is True


def test_timeline_assembly_links_sibling_numeric_claims_by_source_record() -> None:
    result = CompanyPayoutAdapter().adapt_records([_payout_record()])

    assembly = TimelineAssemblyService().assemble(result.signals)

    assert len(assembly.events) == 1
    event = assembly.events[0]
    assert event.event_type == EventType.DIVIDEND_DECLARED
    assert len(event.numeric_claim_refs) == 1
    assert event.narrative_refs == ()


def test_entity_timeline_is_chronologically_sorted_with_deterministic_tiebreak() -> None:
    payout = CompanyPayoutAdapter().adapt_records(
        [_payout_record(payout_time=NOW + timedelta(days=2))]
    )
    psx = PSXAnnouncementAdapter().adapt_records(
        [_psx_record(announcement_time=NOW + timedelta(days=1))]
    )
    secp = SECPNoticeAdapter().adapt_records([_secp_record(notice_time=NOW)])
    unordered_signals = payout.signals + psx.signals + secp.signals

    assembly = TimelineAssemblyService().assemble(unordered_signals)

    timeline = assembly.timelines[0]
    event_times = [entry.event_time for entry in timeline.entries]
    assert event_times == sorted(event_times)
    assert [entry.event_type for entry in timeline.entries] == [
        EventType.SECP_ACTION,
        EventType.RESULTS_ANNOUNCED,
        EventType.DIVIDEND_DECLARED,
    ]


def test_corporate_event_identity_is_stable_across_serialization() -> None:
    result = PSXAnnouncementAdapter().adapt_records([_psx_record()])
    event = TimelineAssemblyService().assemble(result.signals).events[0]

    restored = CorporateEvent.model_validate_json(event.model_dump_json())

    assert restored.event_id == event.event_id
    assert restored.version_pins == event.version_pins
    assert restored.provenance_refs == event.provenance_refs


def test_supersession_links_later_equal_authority_event_without_deleting_history() -> None:
    first = _psx_record(
        announcement_id="psx-ann-001",
        announcement_time=NOW,
        snapshot_ref=_snapshot(SourceType.PSX_ANNOUNCEMENTS, "snap_psx_001"),
    )
    revised = _psx_record(
        announcement_id="psx-ann-002",
        announcement_time=NOW + timedelta(days=1),
        title="Revised financial results announced",
        snapshot_ref=_snapshot(SourceType.PSX_ANNOUNCEMENTS, "snap_psx_002"),
    )
    signals = PSXAnnouncementAdapter().adapt_records([revised, first]).signals
    assembly = TimelineAssemblyService().assemble(signals)

    supersession = SupersessionService().evaluate(assembly.events)

    assert supersession.events_preserved == len(assembly.events)
    assert len(supersession.links) == 1
    assert supersession.unresolved_candidates == ()
    link = supersession.links[0]
    assert link.reason == SupersessionReason.LATER_EQUAL_OR_HIGHER_AUTHORITY
    assert link.prior_event_time == NOW
    assert link.later_event_time == NOW + timedelta(days=1)


def test_supersession_preserves_lower_authority_later_candidate_as_unresolved() -> None:
    prior = _event(
        event_type=EventType.SECP_ACTION,
        event_time=NOW,
        source_type=SourceType.SECP_NOTICES,
        authority_class=AuthorityClass.REGULATORY_INDEPENDENT,
        claim_type=ClaimType.REGULATORY_COMPLIANCE,
        source_signal_ref="sig_prior_regulatory",
    )
    later = _event(
        event_type=EventType.SECP_ACTION,
        event_time=NOW + timedelta(days=1),
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        claim_type=ClaimType.REGULATORY_COMPLIANCE,
        source_signal_ref="sig_later_audited",
    )

    supersession = SupersessionService().evaluate((prior, later))

    assert supersession.links == ()
    assert len(supersession.unresolved_candidates) == 1
    assert supersession.unresolved_candidates[0].reason == SupersessionReason.LOWER_AUTHORITY
    assert supersession.events_preserved == 2


def test_supersession_records_incompatible_same_event_subject() -> None:
    prior = _event(
        event_type=EventType.RESULTS_ANNOUNCED,
        event_time=NOW,
        claim_type=ClaimType.CORPORATE_ACTION_FACT,
        source_signal_ref="sig_prior_results",
    )
    later = _event(
        event_type=EventType.RESULTS_ANNOUNCED,
        event_time=NOW + timedelta(days=1),
        claim_type=ClaimType.DESCRIPTIVE,
        source_signal_ref="sig_later_descriptive_results",
    )

    supersession = SupersessionService().evaluate((prior, later))

    assert supersession.links == ()
    assert len(supersession.unresolved_candidates) == 1
    assert (
        supersession.unresolved_candidates[0].reason
        == SupersessionReason.INCOMPATIBLE_EVENT_OR_CLAIM_TYPE
    )


def test_timeline_audit_reports_chronology_authority_and_history_preservation() -> None:
    first = _psx_record(announcement_id="psx-ann-001", announcement_time=NOW)
    revised = _psx_record(
        announcement_id="psx-ann-002",
        announcement_time=NOW + timedelta(days=1),
        snapshot_ref=_snapshot(SourceType.PSX_ANNOUNCEMENTS, "snap_psx_002"),
    )
    signals = PSXAnnouncementAdapter().adapt_records([first, revised]).signals
    assembly = TimelineAssemblyService().assemble(signals)
    supersession = SupersessionService().evaluate(assembly.events)

    audit = build_timeline_audit(
        assembly_result=assembly,
        supersession_result=supersession,
    )

    assert audit["events_created"] == 2
    assert audit["timeline_entries_created"] == 2
    assert audit["entities_with_timelines"] == 1
    assert audit["supersession_links"] == 1
    assert audit["chronology_validation"]["passed"] is True
    assert audit["authority_validation"]["passed"] is True
    assert audit["history_preservation"]["no_history_deletion"] is True


def _event(
    *,
    event_type: EventType,
    event_time: datetime,
    source_signal_ref: str,
    source_type: SourceType = SourceType.PSX_ANNOUNCEMENTS,
    authority_class: AuthorityClass = AuthorityClass.EXCHANGE_OFFICIAL,
    claim_type: ClaimType = ClaimType.CORPORATE_ACTION_FACT,
) -> CorporateEvent:
    return CorporateEvent(
        entity_ref="lucky_cement",
        event_type=event_type,
        event_time=event_time,
        time_basis=TimeBasis.CALENDAR,
        source_signal_refs=(source_signal_ref,),
        provenance_refs=(f"{source_type.value}:{source_signal_ref}",),
        source_type=source_type,
        authority_class=authority_class,
        claim_type=claim_type,
        creation_eligible=True,
    )
