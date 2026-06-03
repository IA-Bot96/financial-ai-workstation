"""Tests for additive Query Engine consumption of MSIL evidence."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AuthorityClass,
    ClaimType,
    ContentClass,
    Divergence,
    DivergenceReference,
    DivergenceResult,
    DivergenceType,
    EntityResolutionResult,
    EntityScope,
    EventType,
    Horizon,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    PDFPageProvenance,
    ResolutionMethod,
    ReviewStatus,
    SourceType,
    TimeBasis,
)
from multi_source_intelligence.services import (  # noqa: E402
    AnnualReportAdapter,
    TimelineAssemblyService,
)
from query_engine.services import QueryMSILEvidenceAdapter  # noqa: E402


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


def _adapter() -> AnnualReportAdapter:
    return AnnualReportAdapter(
        entity_resolution=_resolution(),
        workbook_fingerprint="fp_lucky_2025",
        report_reference="annual_report:lucky:2025",
    )


def _insight(**overrides) -> dict:
    payload = {
        "value_year": 2025,
        "source_report_year": 2025,
        "area": "Revenue",
        "takeaway": "Revenue increased due to higher dispatches.",
        "source_section": "Business Review",
        "page_number": 84,
        "confidence": 0.82,
    }
    payload.update(overrides)
    return payload


def test_query_msil_adapter_maps_signal_provenance_and_authority() -> None:
    signal = _adapter().adapt_insight(_insight())[0]

    collection = QueryMSILEvidenceAdapter().adapt(signals=(signal,))

    evidence = collection.evidence[0]
    citation = evidence.citations[0]
    assert evidence.signal_ref == signal.signal_id
    assert evidence.content_class == "narrative_claim"
    assert evidence.authority.authority_class == "audited_issuer"
    assert evidence.authority.source_type == "annual_report"
    assert citation.provenance_type == "PDF_PAGE"
    assert citation.page_number == 84
    assert citation.report_reference == "annual_report:lucky:2025"
    assert citation.workbook_fingerprint == "fp_lucky_2025"
    assert citation.locator["source_section"] == "Business Review"
    assert collection.ownership_boundaries["query_assigns_authority"] is False
    assert collection.ownership_boundaries["query_resolves_entities"] is False


def test_query_msil_adapter_retrieves_numeric_reference_evidence() -> None:
    signals = _adapter().adapt_insight(
        _insight(takeaway="Revenue increased by 10% and reached PKR 25 million.")
    )

    collection = QueryMSILEvidenceAdapter().adapt(signals=signals)
    result = QueryMSILEvidenceAdapter().retrieve_evidence(
        collection,
        content_class="numeric_claim",
        metric_ref="annual_report_numeric_reference:revenue",
    )

    assert result.found is True
    assert len(result.evidence) == 2
    assert all(item.authority.creation_eligible is False for item in result.evidence)
    assert len(result.citations) == 2
    assert {item.value for item in result.evidence} == {"10%", "PKR 25 million"}


def test_query_msil_adapter_surfaces_divergence_without_resolution() -> None:
    left = _adapter().adapt_insight(
        _insight(takeaway="Management expects demand to increase.", page_number=10),
        sequence_index=1,
    )[0]
    right = _adapter().adapt_insight(
        _insight(takeaway="Management expects demand to decline.", page_number=11),
        sequence_index=2,
    )[0]
    divergence = Divergence(
        entity_ref="lucky_cement",
        subject="demand outlook",
        divergence_type=DivergenceType.NARRATIVE_VS_NARRATIVE,
        side_a=_divergence_side(left, "increase"),
        side_b=_divergence_side(right, "decline"),
        authority_weighting={"truth_resolution": "not_determined_by_msil"},
        chronology_comparison="same_period",
    )
    divergence_result = DivergenceResult(
        divergences=(divergence,),
        candidates_evaluated=1,
    )

    collection = QueryMSILEvidenceAdapter().adapt(
        signals=(left, right),
        divergence_result=divergence_result,
    )
    result = QueryMSILEvidenceAdapter().retrieve_divergence_references(
        collection,
        left.signal_id,
    )

    assert result.found is True
    assert len(result.divergence_refs) == 1
    surfaced = result.divergence_refs[0]
    assert surfaced.query_resolution_policy == "surface_only"
    assert surfaced.divergence_type == "narrative_vs_narrative"
    assert surfaced.signal_refs == (left.signal_id, right.signal_id)
    assert surfaced.authority_weighting["truth_resolution"] == "not_determined_by_msil"


def test_query_msil_adapter_consumes_timeline_references_without_recomputing() -> None:
    event_signal = _event_signal()
    timeline_result = TimelineAssemblyService().assemble((event_signal,))

    collection = QueryMSILEvidenceAdapter().adapt(
        signals=(event_signal,),
        timeline_result=timeline_result,
    )

    evidence = collection.evidence[0]
    assert len(evidence.timeline_refs) == 1
    assert evidence.timeline_refs[0].event_type == "capacity_commissioned"
    assert collection.ownership_boundaries["query_recomputes_timeline"] is False


def test_query_msil_adapter_audit_reports_coverage_and_boundaries() -> None:
    signals = _adapter().adapt_insight(
        _insight(takeaway="Exports rose by 12%.")
    )
    adapter = QueryMSILEvidenceAdapter()
    collection = adapter.adapt(signals=signals)

    audit = adapter.audit(collection)

    assert audit["evidence_retrieved"] == 2
    assert audit["provenance_attached"] == 2
    assert audit["authority_attached"] == 2
    assert audit["citation_coverage_percent"] == 100.0
    assert audit["citation_policy"]["synthetic_msil_citations_created"] is False
    assert audit["ownership_boundary_validation"]["query_recomputes_divergence"] is False


def _divergence_side(signal: IntelligenceSignal, assertion_value: str) -> DivergenceReference:
    return DivergenceReference(
        signal_ref=signal.signal_id,
        entity_ref=signal.entity_ref,
        subject="demand outlook",
        claim_summary=signal.content.claim_text,
        assertion_value=assertion_value,
        content_class=signal.content.content_class,
        source_type=signal.classification.source_type,
        authority_class=signal.classification.authority_class,
        claim_type=signal.classification.claim_type,
        observation_time=signal.metadata.observation_time,
        subject_period=signal.metadata.subject_period,
        time_basis=signal.metadata.time_basis,
        provenance_ref=f"PDF_PAGE:{signal.provenance.page_number}",
    )


def _event_signal() -> IntelligenceSignal:
    return IntelligenceSignal(
        entity_ref="lucky_cement",
        entity_scope=EntityScope.COMPANY,
        entity_resolution=_resolution(),
        content=IntelligenceSignalContent(
            content_class=ContentClass.CORPORATE_EVENT,
            identity_key="annual:lucky:2025:capacity",
            event_type=EventType.CAPACITY_COMMISSIONED,
            claim_text=None,
            payload={"source_report_year": 2025, "value_year": 2025},
        ),
        classification=IntelligenceSignalClassification(
            content_class=ContentClass.CORPORATE_EVENT,
            source_type=SourceType.ANNUAL_REPORT,
            claim_type=ClaimType.AUDITED_FACT,
            authority_class=AuthorityClass.AUDITED_ISSUER,
            creation_eligible=True,
        ),
        metadata=IntelligenceSignalMetadata(
            observation_time=NOW,
            subject_period="2025",
            time_basis=TimeBasis.FISCAL,
            horizon=Horizon.HISTORICAL,
            source_independent_of_issuer=False,
            verified=True,
            source_record_id="annual:lucky:2025:capacity",
        ),
        provenance=PDFPageProvenance(
            workbook_fingerprint="fp_lucky_2025",
            page_number=44,
            report_reference="annual_report:lucky:2025",
            source_report_year=2025,
            source_section="Business Review",
        ),
    )
