"""Version pin models for MSIL contracts."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
CURRENT_MSIL_SCHEMA_VERSION = "1.0.0"
CURRENT_AUTHORITY_MATRIX_VERSION = "1.0.0"
CURRENT_PROVENANCE_SCHEMA_VERSION = "1.0.0"
CURRENT_ENTITY_REGISTRY_VERSION = "1.0.0"
CURRENT_RESOLUTION_LOGIC_VERSION = "1.0.0"
CURRENT_FVE_CONSUMPTION_CONTRACT_VERSION = "1.0.0"
CURRENT_QAE_CONSUMPTION_CONTRACT_VERSION = "1.0.0"
CURRENT_QUERY_CONSUMPTION_CONTRACT_VERSION = "1.0.0"
CURRENT_TAXONOMY_VERSION = "1.0.0"


class MSILVersionPins(BaseModel):
    """Complete version pin set required by MSIL records."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "msil_schema_version": "1.0.0",
                    "authority_matrix_version": "1.0.0",
                    "provenance_schema_version": "1.0.0",
                    "entity_registry_version": "1.0.0",
                    "resolution_logic_version": "1.0.0",
                    "fve_consumption_contract_version": "1.0.0",
                    "qae_consumption_contract_version": "1.0.0",
                    "query_consumption_contract_version": "1.0.0",
                    "taxonomy_version": "1.0.0",
                }
            ]
        },
    )

    msil_schema_version: str = Field(..., min_length=1)
    authority_matrix_version: str = Field(..., min_length=1)
    provenance_schema_version: str = Field(..., min_length=1)
    entity_registry_version: str = Field(..., min_length=1)
    resolution_logic_version: str = Field(..., min_length=1)
    fve_consumption_contract_version: str = Field(..., min_length=1)
    qae_consumption_contract_version: str = Field(..., min_length=1)
    query_consumption_contract_version: str = Field(..., min_length=1)
    taxonomy_version: str | None = Field(
        default=None,
        description="Narrative taxonomy version carried for QAE-compatible records.",
    )

    @field_validator("*")
    @classmethod
    def _validate_version(cls, value: str | None) -> str | None:
        """Require semantic-version-looking pins."""

        if value is not None and not SEMVER_PATTERN.match(value):
            raise ValueError("version pins must use MAJOR.MINOR.PATCH format.")
        return value


def default_version_pins() -> MSILVersionPins:
    """Return frozen Phase 0 default version pins."""

    return MSILVersionPins(
        msil_schema_version=CURRENT_MSIL_SCHEMA_VERSION,
        authority_matrix_version=CURRENT_AUTHORITY_MATRIX_VERSION,
        provenance_schema_version=CURRENT_PROVENANCE_SCHEMA_VERSION,
        entity_registry_version=CURRENT_ENTITY_REGISTRY_VERSION,
        resolution_logic_version=CURRENT_RESOLUTION_LOGIC_VERSION,
        fve_consumption_contract_version=CURRENT_FVE_CONSUMPTION_CONTRACT_VERSION,
        qae_consumption_contract_version=CURRENT_QAE_CONSUMPTION_CONTRACT_VERSION,
        query_consumption_contract_version=CURRENT_QUERY_CONSUMPTION_CONTRACT_VERSION,
        taxonomy_version=CURRENT_TAXONOMY_VERSION,
    )


__all__ = [
    "CURRENT_AUTHORITY_MATRIX_VERSION",
    "CURRENT_ENTITY_REGISTRY_VERSION",
    "CURRENT_FVE_CONSUMPTION_CONTRACT_VERSION",
    "CURRENT_MSIL_SCHEMA_VERSION",
    "CURRENT_PROVENANCE_SCHEMA_VERSION",
    "CURRENT_QAE_CONSUMPTION_CONTRACT_VERSION",
    "CURRENT_QUERY_CONSUMPTION_CONTRACT_VERSION",
    "CURRENT_RESOLUTION_LOGIC_VERSION",
    "CURRENT_TAXONOMY_VERSION",
    "MSILVersionPins",
    "default_version_pins",
]
