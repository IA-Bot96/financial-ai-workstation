"""Tests for MSIL Phase 2 signal, provenance, and snapshot contracts."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AnnouncementProvenance,
    AuthorityClass,
    ClaimType,
    ContentClass,
    EntityScope,
    EventType,
    FuturesProvenance,
    Horizon,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    IntelligenceSignalProvenance,
    MarketDataProvenance,
    NewsProvenance,
    PDFPageProvenance,
    PayoutProvenance,
    ProvenanceType,
    RegulatoryProvenance,
    ResolutionMethod,
    ReviewStatus,
    SectorProvenance,
    SnapshotMetadata,
    SourceSnapshotReference,
    SourceType,
    TimeBasis,
    URLSnapshotProvenance,
)
from multi_source_intelligence.models import EntityResolutionResult  # noqa: E402


NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def _snapshot(
    source_type: SourceType,
    snapshot_id: str = "snap_001",
) -> SourceSnapshotReference:
    return SourceSnapshotReference(
        snapshot_id=snapshot_id,
        source_type=source_type,
        capture_timestamp=NOW,
        source_hash=f"sha256:{snapshot_id}",
    )


def _resolution(entity_ref: str = "lucky_cement") -> EntityResolutionResult:
    return EntityResolutionResult(
        raw_identifier="Lucky Cement Limited",
        normalized_identifier="lucky cement limited",
        method=ResolutionMethod.EXACT,
        confidence=0.98,
        review_status=ReviewStatus.RESOLVED,
        resolved_entity_ref=entity_ref,
        resolved_entity_type="company",
        candidates=(),
        review_required=False,
        evidence={"resolution_reason": "test"},
    )


def _classification(
    *,
    content_class: ContentClass,
    source_type: SourceType = SourceType.ANNUAL_REPORT,
    authority_class: AuthorityClass = AuthorityClass.AUDITED_ISSUER,
    claim_type: ClaimType = ClaimType.DESCRIPTIVE,
) -> IntelligenceSignalClassification:
    return IntelligenceSignalClassification(
        content_class=content_class,
        source_type=source_type,
        claim_type=claim_type,
        authority_class=authority_class,
        creation_eligible=True,
    )


def _metadata() -> IntelligenceSignalMetadata:
    return IntelligenceSignalMetadata(
        observation_time=NOW,
        subject_period="FY2025",
        time_basis=TimeBasis.FISCAL,
        horizon=Horizon.HISTORICAL,
        source_independent_of_issuer=False,
        verified=True,
        source_record_id="record-001",
    )


def _pdf_provenance() -> PDFPageProvenance:
    return PDFPageProvenance(
        workbook_fingerprint="workbook_fingerprint_001",
        page_number=84,
        retrieved_at=NOW,
    )


def _signal(
    *,
    content: IntelligenceSignalContent,
    classification: IntelligenceSignalClassification | None = None,
    provenance: IntelligenceSignalProvenance | None = None,
    snapshot_metadata: SnapshotMetadata | None = None,
) -> IntelligenceSignal:
    return IntelligenceSignal(
        entity_ref="lucky_cement",
        entity_scope=EntityScope.COMPANY,
        entity_resolution=_resolution(),
        content=content,
        classification=classification
        or _classification(content_class=content.content_class),
        metadata=_metadata(),
        provenance=provenance or _pdf_provenance(),
        snapshot_metadata=snapshot_metadata,
    )


def test_all_content_classes_can_build_signals() -> None:
    contents = (
        IntelligenceSignalContent(
            content_class=ContentClass.NUMERIC_CLAIM,
            metric_ref="revenue",
            value=100,
            unit="PKR",
        ),
        IntelligenceSignalContent(
            content_class=ContentClass.NARRATIVE_CLAIM,
            identity_key="page-84-insight-1",
            claim_text="Revenue increased due to stronger demand.",
        ),
        IntelligenceSignalContent(
            content_class=ContentClass.CORPORATE_EVENT,
            event_type=EventType.RESULTS_ANNOUNCED,
            identity_key="event-results-2025",
        ),
        IntelligenceSignalContent(
            content_class=ContentClass.MARKET_OBSERVATION,
            market_series_ref="LUCK.close",
            value=742.5,
            unit="PKR",
        ),
    )

    for content in contents:
        source_type = (
            SourceType.MARKET_WATCH
            if content.content_class == ContentClass.MARKET_OBSERVATION
            else SourceType.ANNUAL_REPORT
        )
        provenance = (
            MarketDataProvenance(
                series_id="LUCK.close",
                trade_date=date(2026, 6, 3),
                snapshot_ref=_snapshot(SourceType.MARKET_WATCH),
                retrieved_at=NOW,
            )
            if content.content_class == ContentClass.MARKET_OBSERVATION
            else _pdf_provenance()
        )
        signal = _signal(
            content=content,
            classification=_classification(
                content_class=content.content_class,
                source_type=source_type,
                authority_class=(
                    AuthorityClass.MARKET_REVEALED
                    if source_type == SourceType.MARKET_WATCH
                    else AuthorityClass.AUDITED_ISSUER
                ),
                claim_type=(
                    ClaimType.SENTIMENT
                    if source_type == SourceType.MARKET_WATCH
                    else ClaimType.DESCRIPTIVE
                ),
            ),
            provenance=provenance,
        )

        assert signal.signal_id is not None
        assert signal.content.content_class == content.content_class
        assert signal.version_pins.msil_schema_version == "1.0.0"


def test_all_provenance_variants_parse_through_discriminated_union() -> None:
    provenances = (
        _pdf_provenance(),
        AnnouncementProvenance(
            announcement_id="ann-001",
            snapshot_ref=_snapshot(SourceType.PSX_ANNOUNCEMENTS, "snap_ann"),
            retrieved_at=NOW,
        ),
        RegulatoryProvenance(
            notice_id="notice-001",
            snapshot_ref=_snapshot(SourceType.SECP_NOTICES, "snap_reg"),
            retrieved_at=NOW,
        ),
        PayoutProvenance(
            payout_id="payout-001",
            snapshot_ref=_snapshot(SourceType.COMPANY_PAYOUTS, "snap_pay"),
            retrieved_at=NOW,
        ),
        MarketDataProvenance(
            series_id="LUCK.close",
            trade_date=date(2026, 6, 3),
            snapshot_ref=_snapshot(SourceType.MARKET_WATCH, "snap_market"),
            retrieved_at=NOW,
        ),
        FuturesProvenance(
            series_id="cotton.future",
            contract="JUN2026",
            trade_date=date(2026, 6, 3),
            snapshot_ref=_snapshot(SourceType.FUTURES_MARKET_WATCH, "snap_futures"),
            retrieved_at=NOW,
        ),
        SectorProvenance(
            sector_ref="cement",
            snapshot_ref=_snapshot(SourceType.SECTOR_SUMMARY, "snap_sector"),
            retrieved_at=NOW,
        ),
        URLSnapshotProvenance(
            source_type=SourceType.COMPANY_OVERVIEW,
            url="https://example.test/lucky",
            snapshot_ref=_snapshot(SourceType.COMPANY_OVERVIEW, "snap_url"),
            retrieved_at=NOW,
        ),
        NewsProvenance(
            publisher="Example News",
            url="https://news.example.test/lucky",
            snapshot_ref=_snapshot(SourceType.NEWS_SOURCES, "snap_news"),
            retrieved_at=NOW,
        ),
    )

    adapter = TypeAdapter(IntelligenceSignalProvenance)
    for provenance in provenances:
        restored = adapter.validate_python(provenance.model_dump(mode="json"))
        assert restored.provenance_type == provenance.provenance_type


def test_none_provenance_is_rejected_by_signal_union() -> None:
    content = IntelligenceSignalContent(
        content_class=ContentClass.NARRATIVE_CLAIM,
        identity_key="page-1-insight-1",
        claim_text="A claim.",
    )
    payload = {
        "entity_ref": "lucky_cement",
        "entity_scope": "company",
        "entity_resolution": _resolution().model_dump(mode="json"),
        "content": content.model_dump(mode="json"),
        "classification": _classification(
            content_class=ContentClass.NARRATIVE_CLAIM
        ).model_dump(mode="json"),
        "metadata": _metadata().model_dump(mode="json"),
        "provenance": {"provenance_type": ProvenanceType.NONE.value},
    }

    with pytest.raises(ValidationError):
        IntelligenceSignal.model_validate(payload)


def test_non_pdf_provenance_requires_snapshot_reference() -> None:
    with pytest.raises(ValidationError):
        AnnouncementProvenance(
            announcement_id="ann-001",
            retrieved_at=NOW,
        )


def test_snapshot_metadata_must_match_provenance_snapshot() -> None:
    content = IntelligenceSignalContent(
        content_class=ContentClass.NARRATIVE_CLAIM,
        identity_key="announcement-claim-1",
        claim_text="Board approved a dividend.",
    )
    provenance = AnnouncementProvenance(
        announcement_id="ann-001",
        snapshot_ref=_snapshot(SourceType.PSX_ANNOUNCEMENTS, "snap_ann"),
        retrieved_at=NOW,
    )
    wrong_metadata = SnapshotMetadata(
        snapshot_ref=_snapshot(SourceType.PSX_ANNOUNCEMENTS, "snap_other"),
    )

    with pytest.raises(ValidationError):
        _signal(
            content=content,
            classification=_classification(
                content_class=ContentClass.NARRATIVE_CLAIM,
                source_type=SourceType.PSX_ANNOUNCEMENTS,
                authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
                claim_type=ClaimType.CORPORATE_ACTION_FACT,
            ),
            provenance=provenance,
            snapshot_metadata=wrong_metadata,
        )


def test_signal_requires_resolved_entity_resolution() -> None:
    review_resolution = EntityResolutionResult(
        raw_identifier="Lucky",
        normalized_identifier="lucky",
        method=ResolutionMethod.FUZZY,
        confidence=0.74,
        review_status=ReviewStatus.REVIEW,
        candidates=(),
        review_required=True,
        evidence={"resolution_reason": "ambiguous"},
    )
    content = IntelligenceSignalContent(
        content_class=ContentClass.NARRATIVE_CLAIM,
        identity_key="page-1-insight-1",
        claim_text="A claim.",
    )

    with pytest.raises(ValidationError):
        IntelligenceSignal(
            entity_ref="lucky_cement",
            entity_scope=EntityScope.COMPANY,
            entity_resolution=review_resolution,
            content=content,
            classification=_classification(content_class=ContentClass.NARRATIVE_CLAIM),
            metadata=_metadata(),
            provenance=_pdf_provenance(),
        )


def test_signal_identity_is_stable_and_claim_text_independent() -> None:
    content = IntelligenceSignalContent(
        content_class=ContentClass.NARRATIVE_CLAIM,
        identity_key="page-84-insight-1",
        claim_text="Initial wording.",
    )
    changed_text = IntelligenceSignalContent(
        content_class=ContentClass.NARRATIVE_CLAIM,
        identity_key="page-84-insight-1",
        claim_text="Different wording from a later extraction.",
    )

    first = _signal(content=content)
    second = _signal(content=changed_text)

    assert first.signal_id == second.signal_id


def test_supplied_signal_id_must_match_deterministic_identity() -> None:
    content = IntelligenceSignalContent(
        content_class=ContentClass.NARRATIVE_CLAIM,
        identity_key="page-84-insight-1",
        claim_text="A claim.",
    )

    with pytest.raises(ValidationError):
        IntelligenceSignal(
            signal_id="sig_wrong",
            entity_ref="lucky_cement",
            entity_scope=EntityScope.COMPANY,
            entity_resolution=_resolution(),
            content=content,
            classification=_classification(content_class=ContentClass.NARRATIVE_CLAIM),
            metadata=_metadata(),
            provenance=_pdf_provenance(),
        )


def test_signal_serialization_roundtrip_preserves_identity_and_versions() -> None:
    content = IntelligenceSignalContent(
        content_class=ContentClass.NUMERIC_CLAIM,
        metric_ref="revenue",
        value=100,
        unit="PKR",
    )
    signal = _signal(
        content=content,
        classification=_classification(
            content_class=ContentClass.NUMERIC_CLAIM,
            claim_type=ClaimType.AUDITED_FACT,
        ),
    )

    restored = IntelligenceSignal.model_validate_json(signal.model_dump_json())

    assert restored == signal
    assert restored.signal_id == signal.signal_id
    assert restored.version_pins.authority_matrix_version == "1.0.0"


def test_signal_rejects_missing_version_pin_values() -> None:
    content = IntelligenceSignalContent(
        content_class=ContentClass.NARRATIVE_CLAIM,
        identity_key="page-84-insight-1",
        claim_text="A claim.",
    )
    signal = _signal(content=content)
    payload = signal.model_dump(mode="json")
    payload["version_pins"]["msil_schema_version"] = ""

    with pytest.raises(ValidationError):
        IntelligenceSignal.model_validate(payload)
