"""Tests for OCR V2 Phase P0 contract-only foundation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    FROZEN_OCR_V2_CONTRACTS,
    FROZEN_OCR_V2_ENUM_VALUES,
    FROZEN_OCR_V2_OWNERSHIP_TABLE,
    CandidateFactContract,
    CandidateProvenanceContract,
    CandidateRegistryContract,
    CanonicalSelectionContract,
    EntityGovernanceContract,
    OCRExportContract,
    OCRV2Basis,
    OCRV2ContractIntegrityValidator,
    OCRV2EntityScope,
    OCRV2FoundationConfig,
    OCRV2ScaleRole,
    OCRV2StatementType,
    OCRV2VersionPins,
    ScaleGovernanceContract,
    StatementGovernanceContract,
    default_ocr_v2_foundation_config,
    default_ocr_v2_version_pins,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _provenance() -> CandidateProvenanceContract:
    return CandidateProvenanceContract(
        document_fingerprint="fp_123",
        page=292,
        table_ref="table_292_1",
        locator="row:12:col:3",
    )


def test_ocr_v2_enums_are_frozen() -> None:
    assert FROZEN_OCR_V2_ENUM_VALUES["statement_type"] == (
        "PRIMARY_STATEMENT",
        "SUPPORTING_SCHEDULE",
        "NOTE",
        "SUMMARY_TABLE",
        "ANALYSIS_TABLE",
    )
    assert FROZEN_OCR_V2_ENUM_VALUES["entity_scope"] == (
        "ISSUER",
        "SUBSIDIARY",
        "ASSOCIATE",
        "JOINT_VENTURE",
        "INVESTEE",
    )
    assert FROZEN_OCR_V2_ENUM_VALUES["scale_role"] == (
        "SOURCE_SCALE",
        "TARGET_SCALE",
        "NORMALIZED_SCALE",
    )
    assert OCRV2StatementType.ANALYSIS_TABLE.value == "ANALYSIS_TABLE"
    assert OCRV2EntityScope.JOINT_VENTURE.value == "JOINT_VENTURE"
    assert OCRV2ScaleRole.SOURCE_SCALE.value == "SOURCE_SCALE"


def test_ocr_v2_version_pins_are_complete_and_serializable() -> None:
    pins = default_ocr_v2_version_pins()
    restored = OCRV2VersionPins.model_validate_json(pins.model_dump_json())

    assert restored == pins
    assert pins.ocr_v2_contract_version == "2.0.0"
    assert pins.ocr_v2_governance_version == "1.0.0"
    assert pins.ocr_v2_selection_policy_version == "1.0.0"
    assert pins.ocr_v2_registry_version == "1.0.0"


def test_ocr_v2_version_pins_reject_non_semver_values() -> None:
    with pytest.raises(ValidationError):
        OCRV2VersionPins(ocr_v2_contract_version="v2")


def test_candidate_fact_contract_instantiates_and_requires_provenance_alignment() -> None:
    candidate = CandidateFactContract(
        value=52530000000,
        value_year=2025,
        statement_type=OCRV2StatementType.PRIMARY_STATEMENT,
        basis=OCRV2Basis.UNCONSOLIDATED,
        entity_scope=OCRV2EntityScope.ISSUER,
        unit="PKR",
        scale="thousands",
        page=292,
        table_ref="table_292_1",
        provenance=_provenance(),
    )

    assert candidate.value_year == 2025
    assert candidate.provenance.document_fingerprint == "fp_123"

    with pytest.raises(ValidationError):
        CandidateFactContract(
            value=1,
            value_year=2025,
            statement_type=OCRV2StatementType.PRIMARY_STATEMENT,
            basis=OCRV2Basis.UNCONSOLIDATED,
            entity_scope=OCRV2EntityScope.ISSUER,
            unit="PKR",
            scale="thousands",
            page=293,
            table_ref="table_292_1",
            provenance=_provenance(),
        )


def test_contract_models_instantiate_without_behavioral_services() -> None:
    registry = CandidateRegistryContract()
    statement = StatementGovernanceContract()
    entity = EntityGovernanceContract()
    scale = ScaleGovernanceContract()
    selection = CanonicalSelectionContract()
    export = OCRExportContract()

    assert registry.append_only is True
    assert registry.exact_only_dedup is True
    assert registry.retain_losing_candidates is True
    assert registry.provenance_required is True
    assert OCRV2StatementType.ANALYSIS_TABLE in statement.statement_type_enum
    assert OCRV2EntityScope.INVESTEE in entity.entity_scope_enum
    assert OCRV2ScaleRole.NORMALIZED_SCALE in scale.scale_roles
    assert selection.rationale_required is True
    assert export.output_equivalent_to_v1 is True


def test_contract_invariants_reject_disabled_required_guarantees() -> None:
    with pytest.raises(ValidationError):
        CandidateRegistryContract(retain_losing_candidates=False)
    with pytest.raises(ValidationError):
        EntityGovernanceContract(msil_owns_entity_identity=False)
    with pytest.raises(ValidationError):
        ScaleGovernanceContract(magnitude_inference_prohibited=False)
    with pytest.raises(ValidationError):
        CanonicalSelectionContract(eligibility_gated=False)
    with pytest.raises(ValidationError):
        OCRExportContract(provenance_required=False)


def test_foundation_config_is_immutable_and_configuration_only() -> None:
    config = default_ocr_v2_foundation_config()

    assert isinstance(config, OCRV2FoundationConfig)
    assert config.declared_basis == OCRV2Basis.UNCONSOLIDATED
    assert config.target_scale == "source_declared_target"
    assert tuple(config.statement_type_enum) == tuple(OCRV2StatementType)
    assert tuple(config.entity_scope_enum) == tuple(OCRV2EntityScope)

    with pytest.raises(ValidationError):
        OCRV2FoundationConfig(extra_field="not allowed")


def test_ocr_v2_ownership_table_preserves_engine_boundaries() -> None:
    assert FROZEN_OCR_V2_OWNERSHIP_TABLE == {
        "entity_identity": "MSIL",
        "candidate_capture": "OCR",
        "candidate_retention": "Candidate Registry",
        "canonical_choice": "Canonical Selection",
    }


def test_contract_integrity_validator_writes_required_audit_and_report() -> None:
    tmp_path = _workspace_tmp("contract_integrity")
    audit_path = tmp_path / "ocr_v2_contract_integrity_audit.json"
    report_path = tmp_path / "ocr_v2_phase0_report.json"

    report = OCRV2ContractIntegrityValidator().write_phase0_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["contract_count"] == len(FROZEN_OCR_V2_CONTRACTS)
    assert audit["all_contracts_present"] is True
    assert audit["all_enums_present"] is True
    assert audit["all_version_pins_present"] is True
    assert audit["ownership_consistent"] is True
    assert audit["integrity_violations"] == []
    assert report.phase == "P0"
    assert report.scope == "foundations_only"
    assert report.contracts_frozen is True
    assert report.implementation_logic_added is False
    assert report.integrity_audit_passed is True
