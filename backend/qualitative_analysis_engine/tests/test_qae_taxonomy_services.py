"""Tests for QAE Phase 2 deterministic taxonomy services."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from qualitative_analysis_engine.models import MappingMethod, RoutingBasis  # noqa: E402
from qualitative_analysis_engine.services import (  # noqa: E402
    MappingConfidenceComposer,
    SourceSectionRouter,
    TaxonomyLoader,
    TaxonomyMappingAuditService,
    ThemeCanonicalizer,
)


def test_taxonomy_loader_materializes_frozen_taxonomy() -> None:
    taxonomy = TaxonomyLoader().load()

    assert taxonomy.taxonomy_version == "1.0.0"
    assert len(taxonomy.categories) == 6
    assert len(taxonomy.themes) == 27
    assert taxonomy.themes["capacity_expansion"].category_ref == "strategy"
    assert taxonomy.alias_index["exports"] == "market_geographic_expansion"


def test_taxonomy_loader_fails_when_integrity_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from qualitative_analysis_engine.services import taxonomy_loader

    monkeypatch.setattr(taxonomy_loader, "load_taxonomy", lambda _path: {})
    monkeypatch.setattr(
        taxonomy_loader,
        "validate_taxonomy",
        lambda _payload: {
            "validation_passed": False,
            "integrity_failures": [{"check": "forbidden_ambiguous_aliases"}],
        },
    )

    with pytest.raises(ValueError, match="integrity validation"):
        TaxonomyLoader().load()


def test_section_router_maps_canonical_sections() -> None:
    route = SourceSectionRouter().route("Management Discussion & Analysis")

    assert route.recognized is True
    assert route.primary_category_ref == "strategy"
    assert route.secondary_category_refs == ("outlook", "business_risk")
    assert route.routing_basis == RoutingBasis.SECTION_PRIOR


def test_section_router_returns_unknown_route_for_unrecognized_section() -> None:
    route = SourceSectionRouter().route("Random Back Matter")

    assert route.recognized is False
    assert route.primary_category_ref is None
    assert route.routing_basis == RoutingBasis.NONE


def test_theme_canonicalizer_exact_theme_match() -> None:
    result = ThemeCanonicalizer().canonicalize(
        "capacity expansion",
        source_section="Business Review",
    )

    assert result.theme_ref == "capacity_expansion"
    assert result.category_ref == "strategy"
    assert result.mapping_method == MappingMethod.EXACT
    assert result.confidence == 0.9
    assert result.unmapped is False


def test_theme_canonicalizer_alias_match() -> None:
    result = ThemeCanonicalizer().canonicalize(
        "export sales",
        source_section="CEO Review",
    )

    assert result.theme_ref == "market_geographic_expansion"
    assert result.mapping_method == MappingMethod.ALIAS
    assert result.mapping_confidence == 0.9
    assert "alias_match" in result.evidence


def test_theme_canonicalizer_keyword_match_uses_area_and_takeaway() -> None:
    result = ThemeCanonicalizer().canonicalize(
        "Exports and Margin Drivers",
        takeaway="Export volumes increased after entering new overseas markets.",
        source_section="CEO Review",
    )

    assert result.theme_ref == "market_geographic_expansion"
    assert result.mapping_method == MappingMethod.KEYWORD
    assert result.mapping_confidence == 0.65
    assert result.matched_text in {"exports", "export sales", "overseas"}


def test_theme_canonicalizer_returns_unmapped_with_section_prior() -> None:
    result = ThemeCanonicalizer().canonicalize(
        "Unusual unexplained topic",
        source_section="Business Review",
    )

    assert result.unmapped is True
    assert result.theme_ref is None
    assert result.category_ref == "strategy"
    assert result.mapping_method == MappingMethod.UNMAPPED
    assert result.routing_basis == RoutingBasis.SECTION_PRIOR
    assert "section_prior_fallback" in result.evidence


def test_section_theme_conflict_reduces_confidence() -> None:
    result = ThemeCanonicalizer().canonicalize(
        "renewable energy",
        source_section="Risks",
        extraction_confidence=0.95,
    )

    assert result.theme_ref == "energy_transition"
    assert result.section_theme_conflict is True
    assert result.confidence == 0.75
    assert "section_theme_conflict" in result.evidence


def test_confidence_composer_uses_min_floor_and_conflict_penalty() -> None:
    composer = MappingConfidenceComposer()

    confidence = composer.compose(
        mapping_confidence=1.0,
        extraction_confidence=0.8,
        section_confidence=0.9,
        section_theme_conflict=True,
    )

    assert confidence == 0.65


def test_mapping_audit_counts_methods_categories_and_confidence() -> None:
    insights = [
        {
            "area": "capacity expansion",
            "takeaway": "New line increased capacity.",
            "source_section": "Business Review",
            "confidence": 0.9,
        },
        {
            "area": "export sales",
            "takeaway": "Exports increased.",
            "source_section": "CEO Review",
            "confidence": 0.8,
        },
        {
            "area": "Unusual unexplained topic",
            "takeaway": "No known taxonomy term.",
            "source_section": "Business Review",
            "confidence": 0.8,
        },
    ]

    audit = TaxonomyMappingAuditService().audit_insights(insights)

    assert audit["insight_count"] == 3
    assert audit["mapping_method_counts"] == {
        "alias": 1,
        "exact": 1,
        "unmapped": 1,
    }
    assert audit["unmapped_count"] == 1
    assert audit["category_distribution"]["strategy"] == 3
    assert audit["confidence_distribution"]["0.0"] == 1
