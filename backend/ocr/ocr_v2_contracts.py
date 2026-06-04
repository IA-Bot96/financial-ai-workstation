"""Frozen OCR V2 contract substrate.

This module materializes Phase P0 only. It defines immutable contracts,
governance enums, ownership metadata, and version pins. It intentionally does
not implement candidate capture, registry storage, governance rules, canonical
selection, OCR extraction, workbook generation, ranking, authority assignment,
or LLM behavior.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OCR_V2_CONTRACT_VERSION = "2.0.0"
OCR_V2_GOVERNANCE_VERSION = "1.0.0"
OCR_V2_SELECTION_POLICY_VERSION = "1.0.0"
OCR_V2_REGISTRY_VERSION = "1.0.0"

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class OCRV2StatementType(str, Enum):
    """Frozen OCR V2 statement/source classification enum."""

    PRIMARY_STATEMENT = "PRIMARY_STATEMENT"
    SUPPORTING_SCHEDULE = "SUPPORTING_SCHEDULE"
    NOTE = "NOTE"
    SUMMARY_TABLE = "SUMMARY_TABLE"
    ANALYSIS_TABLE = "ANALYSIS_TABLE"


class OCRV2Basis(str, Enum):
    """Frozen declared-basis tags carried by candidate facts."""

    CONSOLIDATED = "consolidated"
    UNCONSOLIDATED = "unconsolidated"
    STANDALONE = "standalone"
    UNKNOWN = "unknown"


class OCRV2EntityScope(str, Enum):
    """Frozen observed entity-scope tags. MSIL owns entity identity."""

    ISSUER = "ISSUER"
    SUBSIDIARY = "SUBSIDIARY"
    ASSOCIATE = "ASSOCIATE"
    JOINT_VENTURE = "JOINT_VENTURE"
    INVESTEE = "INVESTEE"


class OCRV2ScaleRole(str, Enum):
    """Frozen scale governance roles."""

    SOURCE_SCALE = "SOURCE_SCALE"
    TARGET_SCALE = "TARGET_SCALE"
    NORMALIZED_SCALE = "NORMALIZED_SCALE"


class OCRV2VersionPins(BaseModel):
    """Required OCR V2 version pins."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ocr_v2_contract_version: str = Field(
        default=OCR_V2_CONTRACT_VERSION,
        min_length=1,
    )
    ocr_v2_governance_version: str = Field(
        default=OCR_V2_GOVERNANCE_VERSION,
        min_length=1,
    )
    ocr_v2_selection_policy_version: str = Field(
        default=OCR_V2_SELECTION_POLICY_VERSION,
        min_length=1,
    )
    ocr_v2_registry_version: str = Field(
        default=OCR_V2_REGISTRY_VERSION,
        min_length=1,
    )

    @field_validator("*")
    @classmethod
    def _validate_semver(cls, value: str) -> str:
        if not _SEMVER_PATTERN.match(value):
            raise ValueError("OCR V2 version pins must use MAJOR.MINOR.PATCH.")
        return value


def default_ocr_v2_version_pins() -> OCRV2VersionPins:
    """Return frozen OCR V2 default version pins."""

    return OCRV2VersionPins()


class CandidateProvenanceContract(BaseModel):
    """Immutable per-candidate source locator contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_fingerprint: str = Field(..., min_length=1)
    page: int = Field(..., gt=0)
    table_ref: str = Field(..., min_length=1)
    locator: str = Field(..., min_length=1)


class CandidateFactContract(BaseModel):
    """One observed OCR V2 numeric candidate fact.

    This is an observation contract only. It is not a canonical value and does
    not carry any selection behavior.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float | int | str
    value_year: int = Field(..., ge=1900)
    statement_type: OCRV2StatementType
    basis: OCRV2Basis
    entity_scope: OCRV2EntityScope
    unit: str = Field(..., min_length=1)
    scale: str = Field(..., min_length=1)
    page: int = Field(..., gt=0)
    table_ref: str = Field(..., min_length=1)
    provenance: CandidateProvenanceContract
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_provenance_alignment(self) -> "CandidateFactContract":
        if self.provenance.page != self.page:
            raise ValueError("candidate provenance page must match candidate page.")
        if self.provenance.table_ref != self.table_ref:
            raise ValueError(
                "candidate provenance table_ref must match candidate table_ref."
            )
        return self


class CandidateRegistryContract(BaseModel):
    """Frozen candidate registry behavior contract.

    This model states registry invariants only. It is not a storage
    implementation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    append_only: bool = True
    exact_only_dedup: bool = True
    retain_losing_candidates: bool = True
    provenance_required: bool = True
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_registry_contract(self) -> "CandidateRegistryContract":
        if not (
            self.append_only
            and self.exact_only_dedup
            and self.retain_losing_candidates
            and self.provenance_required
        ):
            raise ValueError("all candidate registry contract invariants must be true.")
        return self


class StatementGovernanceContract(BaseModel):
    """Frozen statement governance classification contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement_type_enum: tuple[OCRV2StatementType, ...] = Field(
        default_factory=lambda: tuple(OCRV2StatementType)
    )
    eligibility_classifications: dict[str, str] = Field(
        default_factory=lambda: {
            OCRV2StatementType.PRIMARY_STATEMENT.value: "canonical_eligible_by_basis",
            OCRV2StatementType.SUPPORTING_SCHEDULE.value: "supporting_or_fallback",
            OCRV2StatementType.NOTE.value: "supporting_only_when_primary_exists",
            OCRV2StatementType.SUMMARY_TABLE.value: "supporting_only",
            OCRV2StatementType.ANALYSIS_TABLE.value: "never_canonical_selectable",
        }
    )
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )


class EntityGovernanceContract(BaseModel):
    """Frozen entity governance contract. MSIL remains identity owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_scope_enum: tuple[OCRV2EntityScope, ...] = Field(
        default_factory=lambda: tuple(OCRV2EntityScope)
    )
    msil_owns_entity_identity: bool = True
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_entity_ownership(self) -> "EntityGovernanceContract":
        if not self.msil_owns_entity_identity:
            raise ValueError("MSIL must remain owner of entity identity.")
        return self


class ScaleGovernanceContract(BaseModel):
    """Frozen scale governance contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scale_roles: tuple[OCRV2ScaleRole, ...] = Field(
        default_factory=lambda: tuple(OCRV2ScaleRole)
    )
    source_scale_from_header_required: bool = True
    magnitude_inference_prohibited: bool = True
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_scale_contract(self) -> "ScaleGovernanceContract":
        if not self.source_scale_from_header_required:
            raise ValueError("source scale must be captured from source headers.")
        if not self.magnitude_inference_prohibited:
            raise ValueError("magnitude-based scale inference is prohibited.")
        return self


class CanonicalSelectionContract(BaseModel):
    """Frozen canonical selection contract without selection implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    one_canonical_value_per_metric_year: bool = True
    eligibility_gated: bool = True
    losing_candidates_retained: bool = True
    rationale_required: bool = True
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_selection_contract(self) -> "CanonicalSelectionContract":
        if not (
            self.one_canonical_value_per_metric_year
            and self.eligibility_gated
            and self.losing_candidates_retained
            and self.rationale_required
        ):
            raise ValueError("all canonical selection contract invariants must be true.")
        return self


class OCRExportContract(BaseModel):
    """Frozen OCR export contract preserving V1 output equivalence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_equivalent_to_v1: bool = True
    one_value_per_metric_year: bool = True
    provenance_required: bool = True
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_export_contract(self) -> "OCRExportContract":
        if not (
            self.output_equivalent_to_v1
            and self.one_value_per_metric_year
            and self.provenance_required
        ):
            raise ValueError("all OCR export contract invariants must be true.")
        return self


FROZEN_OCR_V2_CONTRACTS: tuple[str, ...] = (
    "CandidateFactContract",
    "CandidateRegistryContract",
    "StatementGovernanceContract",
    "EntityGovernanceContract",
    "ScaleGovernanceContract",
    "CanonicalSelectionContract",
    "OCRExportContract",
)

FROZEN_OCR_V2_ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "statement_type": tuple(item.value for item in OCRV2StatementType),
    "basis": tuple(item.value for item in OCRV2Basis),
    "entity_scope": tuple(item.value for item in OCRV2EntityScope),
    "scale_role": tuple(item.value for item in OCRV2ScaleRole),
}

FROZEN_OCR_V2_VERSION_PIN_FIELDS: tuple[str, ...] = (
    "ocr_v2_contract_version",
    "ocr_v2_governance_version",
    "ocr_v2_selection_policy_version",
    "ocr_v2_registry_version",
)

FROZEN_OCR_V2_OWNERSHIP_TABLE: dict[str, str] = {
    "entity_identity": "MSIL",
    "candidate_capture": "OCR",
    "candidate_retention": "Candidate Registry",
    "canonical_choice": "Canonical Selection",
}

FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS: dict[str, bool] = {
    "selection_during_capture_implemented": False,
    "entity_resolution_inside_ocr_implemented": False,
    "scale_inference_from_magnitude_implemented": False,
    "authority_assignment_implemented": False,
    "ranking_logic_implemented": False,
}

FROZEN_OCR_V2_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "CandidateFactContract": (
        "value",
        "value_year",
        "statement_type",
        "basis",
        "entity_scope",
        "unit",
        "scale",
        "page",
        "table_ref",
        "provenance",
    ),
    "CandidateRegistryContract": (
        "append_only",
        "exact_only_dedup",
        "retain_losing_candidates",
        "provenance_required",
    ),
    "StatementGovernanceContract": (
        "statement_type_enum",
        "eligibility_classifications",
    ),
    "EntityGovernanceContract": (
        "entity_scope_enum",
        "msil_owns_entity_identity",
    ),
    "ScaleGovernanceContract": (
        "scale_roles",
        "source_scale_from_header_required",
        "magnitude_inference_prohibited",
    ),
    "CanonicalSelectionContract": (
        "one_canonical_value_per_metric_year",
        "eligibility_gated",
        "losing_candidates_retained",
        "rationale_required",
    ),
    "OCRExportContract": (
        "output_equivalent_to_v1",
        "one_value_per_metric_year",
        "provenance_required",
    ),
}

OCR_V2_CONTRACT_MODEL_REGISTRY: dict[str, type[BaseModel]] = {
    "CandidateFactContract": CandidateFactContract,
    "CandidateRegistryContract": CandidateRegistryContract,
    "StatementGovernanceContract": StatementGovernanceContract,
    "EntityGovernanceContract": EntityGovernanceContract,
    "ScaleGovernanceContract": ScaleGovernanceContract,
    "CanonicalSelectionContract": CanonicalSelectionContract,
    "OCRExportContract": OCRExportContract,
}


__all__ = [
    "FROZEN_OCR_V2_CONTRACTS",
    "FROZEN_OCR_V2_ENUM_VALUES",
    "FROZEN_OCR_V2_OWNERSHIP_TABLE",
    "FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS",
    "FROZEN_OCR_V2_REQUIRED_FIELDS",
    "FROZEN_OCR_V2_VERSION_PIN_FIELDS",
    "OCR_V2_CONTRACT_MODEL_REGISTRY",
    "OCR_V2_CONTRACT_VERSION",
    "OCR_V2_GOVERNANCE_VERSION",
    "OCR_V2_REGISTRY_VERSION",
    "OCR_V2_SELECTION_POLICY_VERSION",
    "CandidateFactContract",
    "CandidateProvenanceContract",
    "CandidateRegistryContract",
    "CanonicalSelectionContract",
    "EntityGovernanceContract",
    "OCRExportContract",
    "OCRV2Basis",
    "OCRV2EntityScope",
    "OCRV2ScaleRole",
    "OCRV2StatementType",
    "OCRV2VersionPins",
    "ScaleGovernanceContract",
    "StatementGovernanceContract",
    "default_ocr_v2_version_pins",
]
