"""Tests for QAE Phase 3 annual-report Insight to Signal adapter."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import Insight  # noqa: E402
from qualitative_analysis_engine.models import (  # noqa: E402
    AuthorityClass,
    ClaimType,
    EntityScope,
    Horizon,
    MappingMethod,
    ProvenanceType,
    SourceType,
    TimeBasis,
)
from qualitative_analysis_engine.services import InsightToSignalAdapter  # noqa: E402


def _adapter() -> InsightToSignalAdapter:
    return InsightToSignalAdapter(
        entity_ref="lucky_cement",
        workbook_fingerprint="fp_lucky_2025",
    )


def _insight(**overrides):
    payload = {
        "value_year": 2025,
        "source_report_year": 2025,
        "area": "capacity expansion",
        "takeaway": "New line increased capacity by 10%.",
        "source_section": "Business Review",
        "page_number": 10,
        "confidence": 0.8,
    }
    payload.update(overrides)
    return payload


def test_mapped_signal_generation_from_ocr_insight_model() -> None:
    insight = Insight(**_insight())

    signal = _adapter().adapt_insight(insight)

    assert signal.signal_id.startswith(
        "qae:v1_0_0:lucky_cement:annual_report:2025:p10"
    )
    assert signal.signal_version == "1.0.0"
    assert signal.entity_ref == "lucky_cement"
    assert signal.entity_scope == EntityScope.COMPANY
    assert signal.source_type == SourceType.ANNUAL_REPORT
    assert signal.claim == "New line increased capacity by 10%."
    assert signal.normalized_claim_text == "new line increased capacity by 10"
    assert signal.category_ref == "strategy"
    assert signal.theme_ref == "capacity_expansion"
    assert signal.subtheme_ref is None
    assert signal.mapping_method == MappingMethod.EXACT
    assert signal.mapping_confidence == 1.0
    assert signal.creation_eligible is True


def test_unmapped_signal_generation_preserves_section_category() -> None:
    signal = _adapter().adapt_insight(
        _insight(
            area="Unusual unexplained topic",
            takeaway="This does not map to the frozen taxonomy.",
            source_section="Business Review",
        )
    )

    assert signal.unmapped is True
    assert signal.theme_ref is None
    assert signal.category_ref == "strategy"
    assert signal.mapping_method == MappingMethod.UNMAPPED
    assert signal.mapping_confidence == 0.0
    assert signal.signal_confidence == 0.0
    assert signal.creation_eligible is False
    assert signal.source_metadata["canonicalization_evidence"] == [
        "unmapped",
        "section_prior_fallback",
    ]


def test_pdf_page_provenance_and_ocr_metadata_are_preserved() -> None:
    signal = _adapter().adapt_insight(
        _insight(
            area="export sales",
            source_section="CEO Review",
            page_number=15,
            source_report_year=2025,
            value_year=2024,
            confidence=0.65,
            review_status="review",
        )
    )

    assert signal.provenance.provenance_type == ProvenanceType.PDF_PAGE
    assert signal.provenance.page_number == 15
    assert signal.provenance.source_section == "CEO Review"
    assert signal.provenance.workbook_fingerprint == "fp_lucky_2025"
    assert signal.page_number == 15
    assert signal.source_section == "CEO Review"
    assert signal.source_report_year == 2025
    assert signal.value_year == 2024
    assert signal.extraction_confidence == 0.65
    assert signal.review_status == "review"
    assert signal.source_metadata["review_status"] == "review"


def test_signal_confidence_uses_min_of_extraction_mapping_and_section() -> None:
    signal = _adapter().adapt_insight(
        _insight(
            area="export sales",
            confidence=0.95,
        ),
        section_confidence=0.72,
    )

    assert signal.mapping_method == MappingMethod.ALIAS
    assert signal.mapping_confidence == 0.9
    assert signal.structure_confidence == 0.72
    assert signal.signal_confidence == 0.72


def test_taxonomy_and_authority_versions_are_pinned() -> None:
    signal = _adapter().adapt_insight(_insight())

    assert signal.taxonomy_version == "1.0.0"
    assert signal.authority_matrix_version == "1.0.0"
    assert signal.signal_version == "1.0.0"


def test_authority_class_is_audited_issuer_for_annual_reports() -> None:
    signal = _adapter().adapt_insight(_insight())

    assert signal.authority_class == AuthorityClass.AUDITED_ISSUER
    assert signal.source_independent_of_issuer is False
    assert signal.verified is True
    assert signal.trust_prior == 0.9


def test_claim_type_and_horizon_are_derived_from_source_section() -> None:
    ceo_signal = _adapter().adapt_insight(_insight(source_section="CEO Review"))
    directors_signal = _adapter().adapt_insight(
        _insight(source_section="Directors Report")
    )
    business_signal = _adapter().adapt_insight(
        _insight(source_section="Business Review")
    )

    assert ceo_signal.claim_type == ClaimType.FORWARD_EXPECTATION
    assert ceo_signal.horizon == Horizon.FORWARD
    assert directors_signal.claim_type == ClaimType.REGULATORY_COMPLIANCE
    assert directors_signal.horizon == Horizon.HISTORICAL
    assert business_signal.claim_type == ClaimType.AUDITED_FACT
    assert business_signal.horizon == Horizon.HISTORICAL
    assert business_signal.time_basis == TimeBasis.FISCAL


def test_review_status_is_derived_when_missing() -> None:
    accepted = _adapter().adapt_insight(_insight(confidence=0.8))
    review = _adapter().adapt_insight(_insight(confidence=0.6))
    rejected = _adapter().adapt_insight(_insight(confidence=0.4))

    assert accepted.review_status == "accepted"
    assert review.review_status == "review"
    assert rejected.review_status == "rejected_low_confidence"


def test_adapt_insights_generates_unique_deterministic_signal_ids() -> None:
    insights = [
        _insight(area="capacity expansion", page_number=10),
        _insight(area="capacity expansion", page_number=10),
    ]

    signals = _adapter().adapt_insights(insights)

    assert len(signals) == 2
    assert signals[0].signal_id.endswith(":i0")
    assert signals[1].signal_id.endswith(":i1")
    assert signals[0].signal_id != signals[1].signal_id


def test_signal_generation_audit_summarizes_distributions() -> None:
    audit = _adapter().audit_signals(
        [
            _insight(area="capacity expansion"),
            _insight(area="export sales", source_section="CEO Review"),
            _insight(
                area="Unusual unexplained topic",
                takeaway="This narrative does not match any frozen taxonomy seed.",
            ),
        ]
    )

    assert audit["total_insights_processed"] == 3
    assert audit["total_signals_generated"] == 3
    assert audit["mapped_signals"] == 2
    assert audit["unmapped_signals"] == 1
    assert audit["category_distribution"]["strategy"] == 3
    assert audit["authority_class_distribution"]["audited_issuer"] == 3
    assert audit["claim_type_distribution"]["audited_fact"] == 2
    assert audit["claim_type_distribution"]["forward_expectation"] == 1
