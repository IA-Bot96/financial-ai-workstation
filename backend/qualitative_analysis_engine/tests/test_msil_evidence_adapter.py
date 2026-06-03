"""Tests for additive QAE consumption of MSIL evidence."""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AnnouncementProvenance,
    AuthorityClass as MSILAuthorityClass,
    ClaimType as MSILClaimType,
    ContentClass as MSILContentClass,
    Divergence,
    DivergenceReference as MSILDivergenceReference,
    DivergenceResult,
    DivergenceType as MSILDivergenceType,
    EntityResolutionResult,
    EntityScope as MSILEntityScope,
    Horizon as MSILHorizon,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    MarketDataProvenance,
    PDFPageProvenance as MSILPDFPageProvenance,
    PayoutProvenance,
    ResolutionMethod,
    ReviewStatus,
    SourceSnapshotReference,
    SourceType as MSILSourceType,
    TimeBasis as MSILTimeBasis,
)
from multi_source_intelligence.models import CorroborationResult  # noqa: E402
from multi_source_intelligence.services import CorroborationService  # noqa: E402
from qualitative_analysis_engine.models import (  # noqa: E402
    AuthorityClass,
    DivergenceType,
    SourceType,
)
from qualitative_analysis_engine.services import (  # noqa: E402
    QAEMSILEvidenceAdapter,
    QualitativeCoverageGate,
    ThemeAssemblyService,
)


NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


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


def _snapshot(source_type: MSILSourceType, snapshot_id: str) -> SourceSnapshotReference:
    return SourceSnapshotReference(
        snapshot_id=snapshot_id,
        source_type=source_type,
        capture_timestamp=NOW,
        source_hash=f"sha256:{snapshot_id}",
        snapshot_uri=f"snapshot://{snapshot_id}",
    )


def _narrative_signal(
    *,
    record_id: str,
    claim: str = "Capacity expansion improved production flexibility.",
    source_type: MSILSourceType = MSILSourceType.ANNUAL_REPORT,
    authority_class: MSILAuthorityClass = MSILAuthorityClass.AUDITED_ISSUER,
    claim_type: MSILClaimType = MSILClaimType.DESCRIPTIVE,
    page_number: int = 10,
    payload_extra: dict | None = None,
) -> IntelligenceSignal:
    payload = {
        "area": "capacity expansion",
        "source_section": "Business Review",
        "page_number": page_number,
        "source_report_year": 2025,
        "value_year": 2025,
        "confidence": 0.9,
        "review_status": "accepted",
        "subject": "capacity expansion",
    }
    payload.update(payload_extra or {})
    provenance = (
        MSILPDFPageProvenance(
            workbook_fingerprint="fp_lucky_2025",
            page_number=page_number,
            report_reference="annual_report:lucky:2025",
            source_report_year=2025,
            source_section="Business Review",
        )
        if source_type == MSILSourceType.ANNUAL_REPORT
        else AnnouncementProvenance(
            announcement_id=record_id,
            snapshot_ref=_snapshot(source_type, f"snap_{record_id}"),
            retrieved_at=NOW,
            verified=True,
            source_lineage=(f"{source_type.value}:{record_id}",),
        )
    )
    return IntelligenceSignal(
        entity_ref="lucky_cement",
        entity_scope=MSILEntityScope.COMPANY,
        entity_resolution=_resolution(),
        content=IntelligenceSignalContent(
            content_class=MSILContentClass.NARRATIVE_CLAIM,
            identity_key=f"{source_type.value}:{record_id}:narrative",
            claim_text=claim,
            normalized_claim_text=claim.lower(),
            payload=payload,
        ),
        classification=IntelligenceSignalClassification(
            content_class=MSILContentClass.NARRATIVE_CLAIM,
            source_type=source_type,
            claim_type=claim_type,
            authority_class=authority_class,
            creation_eligible=True,
            mapping_confidence=1.0,
            authority_confidence=1.0,
        ),
        metadata=IntelligenceSignalMetadata(
            observation_time=NOW,
            subject_period="FY2025",
            time_basis=MSILTimeBasis.FISCAL,
            horizon=MSILHorizon.HISTORICAL,
            source_independent_of_issuer=source_type != MSILSourceType.ANNUAL_REPORT,
            verified=True,
            trust_prior=0.9,
            source_record_id=record_id,
        ),
        provenance=provenance,
    )


def _numeric_signal() -> IntelligenceSignal:
    return IntelligenceSignal(
        entity_ref="lucky_cement",
        entity_scope=MSILEntityScope.COMPANY,
        entity_resolution=_resolution(),
        content=IntelligenceSignalContent(
            content_class=MSILContentClass.NUMERIC_CLAIM,
            identity_key="company_payouts:payout-001:numeric",
            metric_ref="payout_amount",
            value="15.00",
            unit="PKR/share",
            payload={"fve_candidate": True},
        ),
        classification=IntelligenceSignalClassification(
            content_class=MSILContentClass.NUMERIC_CLAIM,
            source_type=MSILSourceType.COMPANY_PAYOUTS,
            claim_type=MSILClaimType.CORPORATE_ACTION_FACT,
            authority_class=MSILAuthorityClass.EXCHANGE_OFFICIAL,
            creation_eligible=True,
        ),
        metadata=IntelligenceSignalMetadata(
            observation_time=NOW,
            subject_period=None,
            time_basis=MSILTimeBasis.CALENDAR,
            horizon=MSILHorizon.CURRENT,
            source_independent_of_issuer=False,
            verified=True,
            trust_prior=0.95,
            source_record_id="payout-001",
        ),
        provenance=PayoutProvenance(
            payout_id="payout-001",
            snapshot_ref=_snapshot(MSILSourceType.COMPANY_PAYOUTS, "snap_payout"),
            retrieved_at=NOW,
        ),
    )


def _market_signal() -> IntelligenceSignal:
    return IntelligenceSignal(
        entity_ref="lucky_cement",
        entity_scope=MSILEntityScope.COMPANY,
        entity_resolution=_resolution(),
        content=IntelligenceSignalContent(
            content_class=MSILContentClass.MARKET_OBSERVATION,
            identity_key="market:luck:price:2026-06-03",
            market_series_ref="LUCK_PRICE",
            value="120.50",
            unit="PKR",
        ),
        classification=IntelligenceSignalClassification(
            content_class=MSILContentClass.MARKET_OBSERVATION,
            source_type=MSILSourceType.MARKET_WATCH,
            claim_type=MSILClaimType.SENTIMENT,
            authority_class=MSILAuthorityClass.MARKET_REVEALED,
            creation_eligible=False,
        ),
        metadata=IntelligenceSignalMetadata(
            observation_time=NOW,
            subject_period=None,
            time_basis=MSILTimeBasis.CONTINUOUS,
            horizon=MSILHorizon.CURRENT,
            source_independent_of_issuer=True,
            verified=True,
            trust_prior=0.8,
            source_record_id="market-001",
        ),
        provenance=MarketDataProvenance(
            series_id="LUCK_PRICE",
            trade_date=date(2026, 6, 3),
            snapshot_ref=_snapshot(MSILSourceType.MARKET_WATCH, "snap_market"),
            retrieved_at=NOW,
        ),
    )


def _assemble(signals):
    gate = QualitativeCoverageGate().evaluate(signals)
    return ThemeAssemblyService().assemble(signals, gate)


def test_msil_narrative_claim_maps_to_qae_signal_and_preserves_metadata() -> None:
    signal = _narrative_signal(
        record_id="psx-001",
        source_type=MSILSourceType.PSX_ANNOUNCEMENTS,
        authority_class=MSILAuthorityClass.EXCHANGE_OFFICIAL,
        claim_type=MSILClaimType.OFFICIAL_UNAUDITED_FACT,
    )

    result = QAEMSILEvidenceAdapter().adapt((signal,))

    assert result.narrative_claims_consumed == 1
    qae_signal = result.qae_signals[0]
    assert qae_signal.signal_id == signal.signal_id
    assert qae_signal.source_type == SourceType.COMPANY_ANNOUNCEMENTS
    assert qae_signal.theme_ref == "capacity_expansion"
    assert qae_signal.creation_eligible is True
    assert qae_signal.source_metadata["msil_authority_class"] == "exchange_official"
    assert qae_signal.authority_class == AuthorityClass.OFFICIAL_ISSUER_UNAUDITED
    assert (
        qae_signal.source_metadata["authority_class_compatibility_mapping"]
        == "exchange_official->official_issuer_unaudited"
    )


def test_section_theme_conflict_stays_diagnostic_without_blocking_signal() -> None:
    signal = _narrative_signal(
        record_id="annual-risk-energy",
        claim="Renewable energy investments reduced the emissions profile.",
        payload_extra={
            "area": "renewable energy",
            "source_section": "Risks",
            "confidence": 0.9,
        },
    )

    result = QAEMSILEvidenceAdapter().adapt((signal,))

    assert result.narrative_claims_consumed == 1
    assert result.unsupported_references == ()
    assert result.warnings == ()
    qae_signal = result.qae_signals[0]
    assert qae_signal.theme_ref == "energy_transition"
    assert qae_signal.source_metadata["section_theme_conflict"] is True
    assert qae_signal.signal_confidence == min(
        qae_signal.extraction_confidence,
        qae_signal.mapping_confidence,
        qae_signal.structure_confidence or 1.0,
    )


def test_numeric_claims_events_and_market_observations_do_not_create_themes() -> None:
    numeric = _numeric_signal()
    market = _market_signal()

    result = QAEMSILEvidenceAdapter().adapt((numeric, market))

    assert result.qae_signals == ()
    assert len(result.numeric_claim_references) == 1
    assert result.numeric_claim_references[0].reference_role == "numeric_context_only"
    assert len(result.market_observation_references) == 1
    assert (
        result.market_observation_references[0].reference_role
        == "market_divergence_context_only"
    )
    assert result.ownership_boundaries["qae_creates_themes_from_numeric_claims"] is False
    assert result.ownership_boundaries["qae_creates_themes_from_market_observations"] is False


def test_msil_corroboration_applies_only_to_existing_themes() -> None:
    annual = _narrative_signal(record_id="annual-001")
    psx = _narrative_signal(
        record_id="psx-001",
        source_type=MSILSourceType.PSX_ANNOUNCEMENTS,
        authority_class=MSILAuthorityClass.EXCHANGE_OFFICIAL,
        claim_type=MSILClaimType.DESCRIPTIVE,
    )
    corroboration = CorroborationService().evaluate_signals((annual, psx))
    assert len(corroboration.groups) == 1

    adapter = QAEMSILEvidenceAdapter()
    consumption = adapter.adapt(
        (annual, psx),
        corroboration_result=corroboration,
    )
    assembly = _assemble(consumption.qae_signals)
    before = assembly.themes[0].theme_confidence

    application = adapter.apply_msil_references(
        assembly_result=assembly,
        consumption_result=consumption,
    )

    after_theme = application.assembly_result.themes[0]
    assert application.corroboration_references_applied == 1
    assert after_theme.theme_confidence >= before
    assert after_theme.materiality >= assembly.themes[0].materiality
    assert any(
        origin.startswith("msil:") for origin in after_theme.evidence.independent_origins
    )


def test_msil_divergence_is_surfaced_without_resolution_and_adjusts_theme() -> None:
    left = _narrative_signal(
        record_id="annual-001",
        claim="Capacity expansion is progressing as planned.",
    )
    right = _narrative_signal(
        record_id="psx-001",
        claim="Capacity expansion faces execution delays.",
        source_type=MSILSourceType.PSX_ANNOUNCEMENTS,
        authority_class=MSILAuthorityClass.EXCHANGE_OFFICIAL,
    )
    divergence = Divergence(
        entity_ref="lucky_cement",
        subject="capacity expansion",
        divergence_type=MSILDivergenceType.NARRATIVE_VS_NARRATIVE,
        side_a=_divergence_side(left, "progressing"),
        side_b=_divergence_side(right, "delayed"),
        authority_weighting={"truth_resolution": "not_determined_by_msil"},
        chronology_comparison="same_period",
    )
    divergence_result = DivergenceResult(divergences=(divergence,), candidates_evaluated=1)

    adapter = QAEMSILEvidenceAdapter()
    consumption = adapter.adapt((left, right), divergence_result=divergence_result)
    assembly = _assemble(consumption.qae_signals)
    before = assembly.themes[0].theme_confidence

    application = adapter.apply_msil_references(
        assembly_result=assembly,
        consumption_result=consumption,
    )

    after_theme = application.assembly_result.themes[0]
    assert application.divergence_references_applied == 1
    assert after_theme.divergence_refs[0].divergence_type == DivergenceType.NARRATIVE_VS_NARRATIVE
    assert after_theme.divergence_refs[0].auto_resolved is False
    assert after_theme.theme_confidence < before
    assert after_theme.materiality > assembly.themes[0].materiality


def test_qae_msil_integration_audit_reports_boundaries_and_counts() -> None:
    annual = _narrative_signal(record_id="annual-001")
    numeric = _numeric_signal()
    adapter = QAEMSILEvidenceAdapter()
    consumption = adapter.adapt(
        (annual, numeric),
        corroboration_result=CorroborationResult(
            candidates_evaluated=0,
            lineage_checks_performed=0,
            circularity_rejections=0,
        ),
    )
    assembly = _assemble(consumption.qae_signals)
    application = adapter.apply_msil_references(
        assembly_result=assembly,
        consumption_result=consumption,
    )

    audit = adapter.audit(consumption, application_result=application)

    assert audit["signals_consumed"] == 2
    assert audit["narrative_claims_consumed"] == 1
    assert audit["numeric_claims_referenced"] == 1
    assert audit["content_class_boundary"]["numeric_claim_theme_source"] is False
    assert audit["ownership_boundary_validation"]["qae_recomputes_corroboration"] is False
    assert audit["ownership_boundary_validation"]["qae_recomputes_divergence"] is False


def _divergence_side(signal: IntelligenceSignal, assertion: str) -> MSILDivergenceReference:
    return MSILDivergenceReference(
        signal_ref=signal.signal_id,
        entity_ref=signal.entity_ref,
        subject="capacity expansion",
        claim_summary=signal.content.claim_text,
        assertion_value=assertion,
        content_class=signal.content.content_class,
        source_type=signal.classification.source_type,
        authority_class=signal.classification.authority_class,
        claim_type=signal.classification.claim_type,
        observation_time=signal.metadata.observation_time,
        subject_period=signal.metadata.subject_period,
        time_basis=signal.metadata.time_basis,
        provenance_ref=f"{signal.provenance.provenance_type.value}:{signal.signal_id}",
    )
