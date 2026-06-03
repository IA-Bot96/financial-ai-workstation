"""Truth-set driven tests for MSIL Phase 1 entity resolution."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AliasType,
    Entity,
    EntityAlias,
    EntityRegistry,
    EntityRelationship,
    EntityType,
    RelationshipType,
    ResolutionMethod,
    ReviewStatus,
)
from multi_source_intelligence.services import (  # noqa: E402
    EntityResolver,
    default_entity_registry,
)


POSITIVE_CASES = (
    ("LUCK", "lucky_cement", "sec_luck", ResolutionMethod.EXACT, 0.99),
    ("MTL", "millat_tractors", "sec_mtl", ResolutionMethod.EXACT, 0.99),
    ("Lucky Cement Limited", "lucky_cement", None, ResolutionMethod.EXACT, 0.98),
    ("Lucky Cement", "lucky_cement", None, ResolutionMethod.ALIAS, 0.95),
    (
        "Millat Tractors Limited",
        "millat_tractors",
        None,
        ResolutionMethod.EXACT,
        0.98,
    ),
    ("LEPL", "lucky_electric_power", None, ResolutionMethod.ALIAS, 0.90),
    ("LMC", "lucky_motor_corporation", None, ResolutionMethod.ALIAS, 0.90),
    ("YTML", "yunus_textile_mills", None, ResolutionMethod.ALIAS, 0.90),
    (
        "Lucky Core Industries Limited",
        "lucky_core_industries",
        None,
        ResolutionMethod.EXACT,
        0.98,
    ),
    ("Bolan Castings Limited", "bolan_castings", None, ResolutionMethod.EXACT, 0.95),
    ("Lucky Cement Ltd.", "lucky_cement", None, ResolutionMethod.ALIAS, 0.92),
)


AMBIGUOUS_CASES = (
    (
        "Lucky",
        {
            "lucky_cement",
            "lucky_core_industries",
            "lucky_motor_corporation",
            "lucky_electric_power",
        },
    ),
    (
        "Millat",
        {"millat_tractors", "millat_industrial_products", "millat_equipment"},
    ),
    ("ICI", {"lucky_core_industries"}),
    ("Lucky Power", {"lucky_electric_power"}),
    ("Millat I", {"millat_industrial_products", "millat_equipment"}),
    ("Yunus", {"yunus_brothers_group", "yunus_textile_mills"}),
)


QUARANTINE_CASES = (
    "AGCO",
    "Massey Ferguson",
    "ATF",
    "Aziz Tabba Foundation",
    "XYZ Cement Limited",
    "LUCKX",
    "LUK",
    "Lucky Goldstar",
    "LG",
    "News mention: Lucky in a non-financial context",
)


def test_default_registry_loads_expected_entities_aliases_and_relationships() -> None:
    registry = default_entity_registry()

    assert len(registry.entities) == 20
    assert registry.alias_count() >= 45
    assert registry.relationship_count() >= 20
    assert registry.entity_by_id("lucky_cement") is not None
    assert registry.entity_by_id("millat_tractors") is not None
    assert registry.entity_by_id("sec_luck") is not None


def test_registry_rejects_duplicate_canonical_ids() -> None:
    entity = Entity(
        canonical_id="duplicate",
        entity_type=EntityType.COMPANY,
        display_name="Duplicate Limited",
    )

    with pytest.raises(ValidationError):
        EntityRegistry(entities=(entity, entity))


def test_registry_rejects_duplicate_aliases_within_entity_type() -> None:
    first = Entity(
        canonical_id="first_company",
        entity_type=EntityType.COMPANY,
        display_name="First Company",
        aliases=(EntityAlias(value="DUP", alias_type=AliasType.NAME_VARIANT),),
    )
    second = Entity(
        canonical_id="second_company",
        entity_type=EntityType.COMPANY,
        display_name="Second Company",
        aliases=(EntityAlias(value="DUP", alias_type=AliasType.NAME_VARIANT),),
    )

    with pytest.raises(ValidationError):
        EntityRegistry(entities=(first, second))


def test_registry_allows_same_alias_value_across_entity_types_for_ticker_chaining() -> None:
    company = Entity(
        canonical_id="sample_company",
        entity_type=EntityType.COMPANY,
        display_name="Sample Company",
        aliases=(EntityAlias(value="SMP", alias_type=AliasType.NAME_VARIANT),),
    )
    security = Entity(
        canonical_id="sec_smp",
        entity_type=EntityType.SECURITY,
        display_name="SMP Share",
        aliases=(EntityAlias(value="SMP", alias_type=AliasType.TICKER, exact_match=True),),
        relationships=(
            EntityRelationship(
                rel_type=RelationshipType.SECURITY_OF,
                target_canonical_id="sample_company",
            ),
        ),
    )

    registry = EntityRegistry(entities=(company, security))

    assert registry.alias_count() == 2


def test_registry_validates_relationship_shape() -> None:
    company = Entity(
        canonical_id="sample_company",
        entity_type=EntityType.COMPANY,
        display_name="Sample Company",
        relationships=(
            EntityRelationship(
                rel_type=RelationshipType.SECURITY_OF,
                target_canonical_id="sample_sector",
            ),
        ),
    )
    sector = Entity(
        canonical_id="sample_sector",
        entity_type=EntityType.SECTOR,
        display_name="Sample Sector",
    )

    with pytest.raises(ValidationError):
        EntityRegistry(entities=(company, sector))


def test_registry_supports_merged_tombstones() -> None:
    active = Entity(
        canonical_id="active_company",
        entity_type=EntityType.COMPANY,
        display_name="Active Company",
    )
    merged = Entity(
        canonical_id="old_company",
        entity_type=EntityType.COMPANY,
        display_name="Old Company",
        status="merged",
        merged_into="active_company",
    )

    registry = EntityRegistry(entities=(active, merged))

    assert registry.entity_by_id("old_company").merged_into == "active_company"


@pytest.mark.parametrize(
    ("raw_identifier", "expected_entity", "expected_security", "method", "min_conf"),
    POSITIVE_CASES,
)
def test_positive_truth_set_cases_resolve_correctly(
    raw_identifier: str,
    expected_entity: str,
    expected_security: str | None,
    method: ResolutionMethod,
    min_conf: float,
) -> None:
    result = EntityResolver().resolve(raw_identifier)

    assert result.review_status == ReviewStatus.RESOLVED
    assert result.review_required is False
    assert result.resolved_entity_ref == expected_entity
    assert result.resolved_security_ref == expected_security
    assert result.method == method
    assert result.confidence >= min_conf


def test_ticker_resolution_chains_security_to_company() -> None:
    result = EntityResolver().resolve("LUCK")

    assert result.resolved_security_ref == "sec_luck"
    assert result.resolved_entity_ref == "lucky_cement"
    assert result.candidates[0].canonical_id == "sec_luck"
    assert result.candidates[0].resolution_path == ("sec_luck", "lucky_cement")


@pytest.mark.parametrize(("raw_identifier", "expected_candidates"), AMBIGUOUS_CASES)
def test_ambiguous_truth_set_cases_route_to_review(
    raw_identifier: str,
    expected_candidates: set[str],
) -> None:
    result = EntityResolver().resolve(raw_identifier)
    candidate_entities = {
        candidate.final_entity_ref or candidate.canonical_id
        for candidate in result.candidates
    }

    assert result.review_status == ReviewStatus.REVIEW
    assert result.review_required is True
    assert result.resolved_entity_ref is None
    assert candidate_entities.issuperset(expected_candidates)


@pytest.mark.parametrize("raw_identifier", QUARANTINE_CASES)
def test_quarantine_truth_set_cases_never_bind_to_group_entities(
    raw_identifier: str,
) -> None:
    result = EntityResolver().resolve(raw_identifier)

    assert result.review_status == ReviewStatus.QUARANTINED
    assert result.review_required is True
    assert result.resolved_entity_ref is None
    assert result.candidates == ()
    assert result.method == ResolutionMethod.UNRESOLVED


def test_confidence_does_not_override_precedence() -> None:
    exact = EntityResolver().resolve("LUCK")
    fuzzy_review = EntityResolver().resolve("Lucky Power")

    assert exact.method == ResolutionMethod.EXACT
    assert exact.review_status == ReviewStatus.RESOLVED
    assert fuzzy_review.method == ResolutionMethod.FUZZY
    assert fuzzy_review.review_status == ReviewStatus.REVIEW
    assert fuzzy_review.resolved_entity_ref is None


def test_group_aware_resolution_keeps_lucky_and_millat_entities_distinct() -> None:
    resolver = EntityResolver()
    cases = {
        "Lucky Cement Limited": "lucky_cement",
        "Lucky Core Industries Limited": "lucky_core_industries",
        "LMC": "lucky_motor_corporation",
        "LEPL": "lucky_electric_power",
        "Millat Tractors Limited": "millat_tractors",
        "Millat Industrial": "millat_industrial_products",
        "Millat Equipment": "millat_equipment",
    }

    for raw_identifier, expected_entity in cases.items():
        result = resolver.resolve(raw_identifier)
        assert result.resolved_entity_ref == expected_entity


def test_fuzzy_unknowns_do_not_auto_select_single_candidate() -> None:
    result = EntityResolver().resolve("Lucky Electrc Power")

    assert result.review_status in {ReviewStatus.REVIEW, ReviewStatus.QUARANTINED}
    assert result.resolved_entity_ref is None
