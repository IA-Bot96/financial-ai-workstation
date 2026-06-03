"""MSIL contract integrity validation models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ContractIntegrityIssue(BaseModel):
    """One contract integrity issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(..., min_length=1)
    severity: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    affected_contract: str = Field(..., min_length=1)


class ContractIntegrityValidationResult(BaseModel):
    """Result of Phase 0 contract integrity validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool = Field(..., description="True when no issues were found.")
    issues: tuple[ContractIntegrityIssue, ...] = Field(default_factory=tuple)
    checks_executed: tuple[str, ...] = Field(default_factory=tuple)
    enum_counts: dict[str, int] = Field(default_factory=dict)
    authority_matrix_claim_types: int = Field(default=0, ge=0)
    provenance_schema_entries: int = Field(default=0, ge=0)
    version_pin_count: int = Field(default=0, ge=0)


__all__ = [
    "ContractIntegrityIssue",
    "ContractIntegrityValidationResult",
]
