"""Entity resolution contracts for MSIL Phase 1."""

from __future__ import annotations

from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import EntityScope, EntityType, ResolutionMethod, ReviewStatus
from .versioning import (
    CURRENT_ENTITY_REGISTRY_VERSION,
    CURRENT_RESOLUTION_LOGIC_VERSION,
)

EntityResolutionMethod: TypeAlias = ResolutionMethod


class EntityResolutionRequest(BaseModel):
    """Request to resolve one raw source identifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_identifier: str = Field(..., min_length=1)
    entity_scope: EntityScope | None = Field(
        default=None,
        description="Optional consuming scope hint; never overrides precedence.",
    )
    allow_fuzzy: bool = Field(default=True)
    source_context: str | None = Field(default=None)


class EntityResolutionCandidate(BaseModel):
    """One candidate produced by deterministic resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_id: str = Field(..., min_length=1)
    entity_type: EntityType = Field(..., description="Matched registry entity type.")
    display_name: str = Field(..., min_length=1)
    method: ResolutionMethod = Field(..., description="Candidate match method.")
    confidence: float = Field(..., ge=0, le=1)
    matched_value: str | None = Field(default=None)
    final_entity_ref: str | None = Field(
        default=None,
        description="Company/entity reached after security-to-company chaining.",
    )
    resolution_path: tuple[str, ...] = Field(default_factory=tuple)
    evidence: dict[str, Any] = Field(default_factory=dict)


class EntityResolutionResult(BaseModel):
    """Resolution result with quarantine-not-force semantics."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "raw_identifier": "LUCK",
                    "normalized_identifier": "luck",
                    "method": "exact",
                    "confidence": 0.99,
                    "review_status": "resolved",
                    "resolved_entity_ref": "lucky_cement",
                    "resolved_security_ref": "sec_luck",
                    "review_required": False,
                    "entity_registry_version": "1.0.0",
                    "resolution_logic_version": "1.0.0",
                }
            ]
        },
    )

    raw_identifier: str = Field(..., min_length=1)
    normalized_identifier: str = Field(..., min_length=1)
    method: ResolutionMethod = Field(..., description="Winning resolution method.")
    confidence: float = Field(..., ge=0, le=1)
    review_status: ReviewStatus = Field(..., description="Resolution review state.")
    resolved_entity_ref: str | None = Field(
        default=None,
        description="Final attributed entity. Null for review/quarantine.",
    )
    resolved_entity_type: EntityType | None = Field(default=None)
    resolved_security_ref: str | None = Field(
        default=None,
        description="Security id when ticker chaining was used.",
    )
    candidates: tuple[EntityResolutionCandidate, ...] = Field(default_factory=tuple)
    review_required: bool = Field(default=False)
    evidence: dict[str, Any] = Field(default_factory=dict)
    entity_registry_version: str = Field(
        default=CURRENT_ENTITY_REGISTRY_VERSION,
        min_length=1,
    )
    resolution_logic_version: str = Field(
        default=CURRENT_RESOLUTION_LOGIC_VERSION,
        min_length=1,
    )

    @model_validator(mode="after")
    def _validate_resolution_state(self) -> "EntityResolutionResult":
        if self.review_status == ReviewStatus.RESOLVED:
            if not self.resolved_entity_ref:
                raise ValueError("resolved results require resolved_entity_ref.")
            if self.review_required:
                raise ValueError("resolved results cannot require review.")
        if self.review_status in {ReviewStatus.REVIEW, ReviewStatus.QUARANTINED}:
            if self.resolved_entity_ref is not None:
                raise ValueError("review/quarantined results cannot be attributed.")
            if not self.review_required:
                raise ValueError("review/quarantined results must require review.")
        if self.review_status == ReviewStatus.QUARANTINED and self.candidates:
            raise ValueError("quarantined results cannot carry attribution candidates.")
        return self


__all__ = [
    "EntityResolutionCandidate",
    "EntityResolutionMethod",
    "EntityResolutionRequest",
    "EntityResolutionResult",
]
