"""Tests for MSIL Phase 0 contract and matrix materialization."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AuthorityClass,
    AuthorityMatrix,
    AuthorityMatrixEntry,
    AuthoritySpecialRule,
    ClaimType,
    ContentClass,
    MSILVersionPins,
    ProvenanceRequirement,
    ProvenanceSchema,
    ProvenanceType,
    SourceType,
    default_authority_matrix,
    default_provenance_schema,
    default_version_pins,
)
from multi_source_intelligence.models.enums import (  # noqa: E402
    AliasType,
    DivergenceStatus,
    DivergenceType,
    EntityScope,
    EntityStatus,
    EntityType,
    EventType,
    Horizon,
    RelationshipType,
    ResolutionMethod,
    ReviewStatus,
    TimeBasis,
)
from multi_source_intelligence.services import ContractIntegrityValidator  # noqa: E402


ENUM_REGISTRY = (
    EntityType,
    EntityScope,
    AliasType,
    RelationshipType,
    EntityStatus,
    ResolutionMethod,
    ReviewStatus,
    ContentClass,
    SourceType,
    AuthorityClass,
    ClaimType,
    TimeBasis,
    Horizon,
    ProvenanceType,
    EventType,
    DivergenceType,
    DivergenceStatus,
)


def test_enum_values_are_unique_and_expected_core_values_exist() -> None:
    for enum_cls in ENUM_REGISTRY:
        values = [item.value for item in enum_cls]
        assert len(values) == len(set(values)), enum_cls.__name__

    assert ContentClass.NUMERIC_CLAIM.value == "numeric_claim"
    assert ContentClass.NARRATIVE_CLAIM.value == "narrative_claim"
    assert ContentClass.CORPORATE_EVENT.value == "corporate_event"
    assert ContentClass.MARKET_OBSERVATION.value == "market_observation"
    assert ProvenanceType.NONE.value == "NONE"
    assert DivergenceStatus.SURFACED.value == "surfaced"


def test_default_version_pins_are_semver_and_serializable() -> None:
    pins = default_version_pins()

    payload = pins.model_dump_json()
    restored = MSILVersionPins.model_validate_json(payload)

    assert restored == pins
    assert restored.msil_schema_version == "1.0.0"
    assert restored.authority_matrix_version == "1.0.0"
    assert restored.provenance_schema_version == "1.0.0"
    assert restored.taxonomy_version == "1.0.0"


def test_version_pins_reject_non_semver_values() -> None:
    with pytest.raises(ValidationError):
        MSILVersionPins(
            msil_schema_version="v1",
            authority_matrix_version="1.0.0",
            provenance_schema_version="1.0.0",
            entity_registry_version="1.0.0",
            resolution_logic_version="1.0.0",
            fve_consumption_contract_version="1.0.0",
            qae_consumption_contract_version="1.0.0",
            query_consumption_contract_version="1.0.0",
        )


def test_default_authority_matrix_is_total_per_claim_type() -> None:
    matrix = default_authority_matrix()

    assert {entry.claim_type for entry in matrix.entries} == set(ClaimType)
    assert matrix.ranking_for(ClaimType.AUDITED_FACT)[0] == AuthorityClass.AUDITED_ISSUER
    assert (
        matrix.ranking_for(ClaimType.REGULATORY_COMPLIANCE)[0]
        == AuthorityClass.REGULATORY_INDEPENDENT
    )
    assert (
        matrix.effective_rank(
            claim_type=ClaimType.FORWARD_EXPECTATION,
            authority_class=AuthorityClass.INDEPENDENT_OPINION,
        )
        == 0
    )


def test_authority_matrix_requires_news_and_market_special_rules() -> None:
    with pytest.raises(ValidationError):
        AuthorityMatrix(
            authority_matrix_version="1.0.0",
            entries=default_authority_matrix().entries,
            special_rules=(
                AuthoritySpecialRule(
                    rule_id="news_media_corroboration_only",
                    authority_class=AuthorityClass.NEWS_MEDIA,
                    applies_to_content_classes=(ContentClass.NARRATIVE_CLAIM,),
                    description="News is corroboration-only.",
                    standalone_fact_authority_allowed=False,
                ),
            ),
        )


def test_authority_matrix_rejects_duplicate_claim_type_entries() -> None:
    entries = default_authority_matrix().entries
    with pytest.raises(ValidationError):
        AuthorityMatrix(
            authority_matrix_version="1.0.0",
            entries=(entries[0], *entries),
            special_rules=default_authority_matrix().special_rules,
        )


def test_authority_matrix_serialization_roundtrip() -> None:
    matrix = default_authority_matrix()

    restored = AuthorityMatrix.model_validate_json(matrix.model_dump_json())

    assert restored == matrix
    assert len(restored.entries) == len(ClaimType)


def test_default_provenance_schema_is_total_and_forbids_none() -> None:
    schema = default_provenance_schema()

    assert {item.provenance_type for item in schema.requirements} == set(ProvenanceType)
    assert schema.requirement_for(ProvenanceType.NONE).forbidden_to_emit is True
    assert schema.requirement_for(ProvenanceType.PDF_PAGE).snapshot_required is False
    assert schema.requirement_for(ProvenanceType.NEWS_REF).snapshot_required is True
    assert "publisher" in schema.requirement_for(ProvenanceType.NEWS_REF).required_fields
    assert "url" in schema.requirement_for(ProvenanceType.NEWS_REF).required_fields


def test_provenance_schema_requires_non_pdf_snapshots() -> None:
    with pytest.raises(ValidationError):
        ProvenanceRequirement(
            provenance_type=ProvenanceType.NEWS_REF,
            source_types=(SourceType.NEWS_SOURCES,),
            snapshot_required=False,
            required_fields=("publisher", "url", "retrieved_at"),
        )


def test_provenance_schema_requires_every_provenance_type() -> None:
    requirements = tuple(
        requirement
        for requirement in default_provenance_schema().requirements
        if requirement.provenance_type != ProvenanceType.PAYOUT_REF
    )

    with pytest.raises(ValidationError):
        ProvenanceSchema(
            provenance_schema_version="1.0.0",
            requirements=requirements,
        )


def test_provenance_schema_serialization_roundtrip() -> None:
    schema = default_provenance_schema()

    restored = ProvenanceSchema.model_validate_json(schema.model_dump_json())

    assert restored == schema
    assert restored.requirement_for(ProvenanceType.MARKET_DATA_REF).snapshot_required


def test_contract_integrity_validator_passes_default_contracts() -> None:
    result = ContractIntegrityValidator().validate()

    assert result.is_valid is True
    assert result.issues == ()
    assert result.authority_matrix_claim_types == len(ClaimType)
    assert result.provenance_schema_entries == len(ProvenanceType)
    assert result.enum_counts["ContentClass"] == 4
    assert "authority_matrix_total_per_claim_type" in result.checks_executed


def test_contract_integrity_validator_reports_manual_matrix_failure() -> None:
    matrix = AuthorityMatrix.model_construct(
        authority_matrix_version="1.0.0",
        entries=(
            AuthorityMatrixEntry(
                claim_type=ClaimType.AUDITED_FACT,
                authority_order=(AuthorityClass.AUDITED_ISSUER,),
                rationale="Deliberately incomplete test matrix.",
            ),
        ),
        special_rules=default_authority_matrix().special_rules,
    )

    result = ContractIntegrityValidator().validate(authority_matrix=matrix)

    assert result.is_valid is False
    assert any(
        issue.check_id == "authority_matrix_total_per_claim_type"
        for issue in result.issues
    )
