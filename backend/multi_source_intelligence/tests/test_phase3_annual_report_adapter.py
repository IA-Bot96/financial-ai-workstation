"""Tests for MSIL Phase 3 annual-report adapter."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AuthorityClass,
    ClaimType,
    ContentClass,
    EntityResolutionResult,
    Horizon,
    ProvenanceType,
    ResolutionMethod,
    ReviewStatus,
    SourceType,
    TimeBasis,
)
from multi_source_intelligence.services import AnnualReportAdapter  # noqa: E402
from ocr_engine.models.insights_extraction import Insight  # noqa: E402


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
        "area": "Capacity Expansion",
        "takeaway": "New production line increased capacity by 10%.",
        "source_section": "Business Review",
        "page_number": 84,
        "confidence": 0.82,
    }
    payload.update(overrides)
    return payload


def test_adapter_requires_resolved_entity_resolution() -> None:
    unresolved = EntityResolutionResult(
        raw_identifier="Lucky",
        normalized_identifier="lucky",
        method=ResolutionMethod.FUZZY,
        confidence=0.74,
        review_status=ReviewStatus.REVIEW,
        candidates=(),
        review_required=True,
        evidence={"resolution_reason": "ambiguous"},
    )

    with pytest.raises(ValueError, match="resolved entity_resolution"):
        AnnualReportAdapter(
            entity_resolution=unresolved,
            workbook_fingerprint="fp_lucky_2025",
            report_reference="annual_report:lucky:2025",
        )


def test_ocr_insight_maps_to_narrative_intelligence_signal() -> None:
    signals = _adapter().adapt_insight(Insight(**_insight(takeaway="Exports grew.")))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.signal_id.startswith("sig_")
    assert signal.entity_ref == "lucky_cement"
    assert signal.content.content_class == ContentClass.NARRATIVE_CLAIM
    assert signal.content.claim_text == "Exports grew."
    assert signal.classification.source_type == SourceType.ANNUAL_REPORT
    assert signal.classification.authority_class == AuthorityClass.AUDITED_ISSUER
    assert signal.classification.claim_type == ClaimType.AUDITED_FACT
    assert signal.classification.creation_eligible is True
    assert signal.metadata.time_basis == TimeBasis.FISCAL
    assert signal.metadata.horizon == Horizon.HISTORICAL


def test_pdf_page_provenance_preserves_report_reference_and_source_metadata() -> None:
    signal = _adapter().adapt_insight(_insight(source_section="CEO Review"))[0]

    assert signal.provenance.provenance_type == ProvenanceType.PDF_PAGE
    assert signal.provenance.page_number == 84
    assert signal.provenance.workbook_fingerprint == "fp_lucky_2025"
    assert signal.provenance.report_reference == "annual_report:lucky:2025"
    assert signal.provenance.source_report_year == 2025
    assert signal.provenance.source_section == "CEO Review"
    assert signal.content.payload["source_report_year"] == 2025
    assert signal.content.payload["value_year"] == 2025
    assert signal.content.payload["confidence"] == 0.82
    assert signal.content.payload["review_status"] == "accepted"


def test_source_section_drives_claim_type_and_horizon() -> None:
    ceo = _adapter().adapt_insight(_insight(source_section="CEO Review"))[0]
    directors = _adapter().adapt_insight(_insight(source_section="Directors Report"))[0]
    risks = _adapter().adapt_insight(_insight(source_section="Risks"))[0]

    assert ceo.classification.claim_type == ClaimType.FORWARD_EXPECTATION
    assert ceo.metadata.horizon == Horizon.FORWARD
    assert directors.classification.claim_type == ClaimType.REGULATORY_COMPLIANCE
    assert directors.metadata.horizon == Horizon.HISTORICAL
    assert risks.classification.claim_type == ClaimType.DESCRIPTIVE
    assert risks.metadata.horizon == Horizon.FORWARD


def test_numeric_mentions_create_reference_only_numeric_claim_signals() -> None:
    signals = _adapter().adapt_insight(
        _insight(
            area="Exports",
            takeaway="Export sales increased by 10% and reached PKR 25 million.",
        )
    )

    narrative = signals[0]
    numeric_refs = [
        signal for signal in signals if signal.content.content_class == ContentClass.NUMERIC_CLAIM
    ]

    assert narrative.content.content_class == ContentClass.NARRATIVE_CLAIM
    assert len(numeric_refs) == 2
    assert all(ref.classification.creation_eligible is False for ref in numeric_refs)
    assert all(ref.content.payload["numeric_reference_only"] is True for ref in numeric_refs)
    assert all(ref.content.payload["not_authoritative_value"] is True for ref in numeric_refs)
    assert {ref.content.value for ref in numeric_refs} == {"10%", "PKR 25 million"}
    assert {ref.content.unit for ref in numeric_refs} == {"%", "million"}
    assert {
        ref.content.payload["originating_narrative_signal_id"] for ref in numeric_refs
    } == {narrative.signal_id}


def test_adapter_result_summarizes_audit_distributions_and_failures() -> None:
    result = _adapter().adapt_insights(
        [
            _insight(takeaway="Business improved."),
            _insight(takeaway="Margins improved by 5%."),
            {"takeaway": "Missing required fields."},
        ]
    )
    audit = _adapter().audit_result(result)

    assert result.insights_processed == 3
    assert result.signals_generated == 3
    assert len(result.mapping_failures) == 1
    assert result.content_class_distribution == {
        "narrative_claim": 2,
        "numeric_claim": 1,
    }
    assert result.provenance_coverage["all_signals_provenance_backed"] is True
    assert result.provenance_coverage["signals_with_report_reference"] == 3
    assert result.authority_distribution == {"audited_issuer": 3}
    assert audit["mapping_failures"][0]["reason"].startswith("insight missing")


def test_signal_ids_are_deterministic_and_text_independent_for_same_source_key() -> None:
    first = _adapter().adapt_insight(
        _insight(takeaway="Original extraction wording."),
        sequence_index=3,
    )[0]
    second = _adapter().adapt_insight(
        _insight(takeaway="Reworded extraction from the same source location."),
        sequence_index=3,
    )[0]

    assert first.signal_id == second.signal_id


def test_supplied_missing_report_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="report_reference"):
        AnnualReportAdapter(
            entity_resolution=_resolution(),
            workbook_fingerprint="fp_lucky_2025",
            report_reference="",
        )


def test_result_serialization_roundtrip() -> None:
    result = _adapter().adapt_insights([_insight(takeaway="Business improved.")])

    restored = type(result).model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.signals[0].signal_id == result.signals[0].signal_id
