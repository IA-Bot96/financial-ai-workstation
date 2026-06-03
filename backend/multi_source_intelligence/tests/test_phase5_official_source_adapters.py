"""Tests for MSIL Phase 5 official structured-source adapters."""

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AuthorityClass,
    ContentClass,
    EventType,
    ProvenanceType,
    ReviewStatus,
    SourceSnapshotReference,
    SourceType,
)
from multi_source_intelligence.services import (  # noqa: E402
    CompanyPayoutAdapter,
    PSXAnnouncementAdapter,
    SECPNoticeAdapter,
    build_official_sources_audit,
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


def test_psx_announcement_adapter_generates_narrative_and_event_signals() -> None:
    result = PSXAnnouncementAdapter().adapt_records([_psx_record()])

    assert result.records_processed == 1
    assert result.signals_generated == 2
    assert result.failures == ()
    assert result.entity_resolution_results[0].resolved_entity_ref == "lucky_cement"
    assert {signal.content.content_class for signal in result.signals} == {
        ContentClass.NARRATIVE_CLAIM,
        ContentClass.CORPORATE_EVENT,
    }
    assert {signal.provenance.provenance_type for signal in result.signals} == {
        ProvenanceType.ANNOUNCEMENT_REF
    }
    assert result.authority_distribution == {"exchange_official": 2}
    assert all(
        signal.classification.authority_class == AuthorityClass.EXCHANGE_OFFICIAL
        for signal in result.signals
    )


def test_company_payout_adapter_generates_event_and_numeric_claim_signal() -> None:
    result = CompanyPayoutAdapter().adapt_records([_payout_record()])

    assert result.records_processed == 1
    assert result.signals_generated == 2
    assert result.failures == ()
    numeric_signal = next(
        signal
        for signal in result.signals
        if signal.content.content_class == ContentClass.NUMERIC_CLAIM
    )
    event_signal = next(
        signal
        for signal in result.signals
        if signal.content.content_class == ContentClass.CORPORATE_EVENT
    )

    assert numeric_signal.content.metric_ref == "payout_amount"
    assert numeric_signal.content.value == "15.00"
    assert numeric_signal.content.payload["fve_candidate"] is True
    assert numeric_signal.classification.creation_eligible is True
    assert event_signal.content.event_type == EventType.DIVIDEND_DECLARED
    assert {signal.provenance.provenance_type for signal in result.signals} == {
        ProvenanceType.PAYOUT_REF
    }


def test_secp_notice_adapter_generates_regulatory_narrative_and_event_signals() -> None:
    result = SECPNoticeAdapter().adapt_records([_secp_record()])

    assert result.records_processed == 1
    assert result.signals_generated == 2
    assert result.failures == ()
    assert result.authority_distribution == {"regulatory_independent": 2}
    assert {signal.provenance.provenance_type for signal in result.signals} == {
        ProvenanceType.REGULATORY_REF
    }
    assert all(signal.metadata.source_independent_of_issuer for signal in result.signals)


def test_unresolved_entity_is_recorded_as_failure_without_signals() -> None:
    result = PSXAnnouncementAdapter().adapt_records(
        [_psx_record(issuer_identifier="AGCO")]
    )

    assert result.records_processed == 1
    assert result.signals_generated == 0
    assert len(result.failures) == 1
    assert result.failures[0].reason == "entity_resolution_not_resolved"
    assert result.failures[0].resolution_status == ReviewStatus.QUARANTINED.value


def test_missing_snapshot_is_recorded_as_failure() -> None:
    malformed = _secp_record()
    malformed.pop("snapshot_ref")

    result = SECPNoticeAdapter().adapt_records([malformed])

    assert result.records_processed == 1
    assert result.signals_generated == 0
    assert len(result.failures) == 1
    assert "snapshot_ref" in result.failures[0].reason


def test_snapshot_source_mismatch_is_recorded_as_failure() -> None:
    result = CompanyPayoutAdapter().adapt_records(
        [
            _payout_record(
                snapshot_ref=_snapshot(SourceType.PSX_ANNOUNCEMENTS, "wrong_source")
            )
        ]
    )

    assert result.signals_generated == 0
    assert len(result.failures) == 1
    assert "company_payouts" in result.failures[0].reason


def test_official_sources_audit_aggregates_all_three_adapters() -> None:
    psx = PSXAnnouncementAdapter().adapt_records([_psx_record()])
    payout = CompanyPayoutAdapter().adapt_records([_payout_record()])
    secp = SECPNoticeAdapter().adapt_records([_secp_record()])

    audit = build_official_sources_audit([psx, payout, secp])

    assert audit["records_processed"] == 3
    assert audit["signals_generated"] == 6
    assert audit["content_class_distribution"] == {
        "narrative_claim": 2,
        "corporate_event": 3,
        "numeric_claim": 1,
    }
    assert audit["authority_distribution"] == {
        "exchange_official": 4,
        "regulatory_independent": 2,
    }
    assert audit["provenance_distribution"] == {
        "ANNOUNCEMENT_REF": 2,
        "PAYOUT_REF": 2,
        "REGULATORY_REF": 2,
    }
    assert audit["snapshot_coverage"]["all_signals_snapshot_backed"] is True
    assert audit["failures_recorded"] == 0
