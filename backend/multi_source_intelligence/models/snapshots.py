"""Immutable source snapshot references for MSIL Phase 2."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import SourceType
from .versioning import (
    CURRENT_MSIL_SCHEMA_VERSION,
    CURRENT_PROVENANCE_SCHEMA_VERSION,
)


class SourceSnapshotReference(BaseModel):
    """Reference to an immutable captured source artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str = Field(..., min_length=1)
    source_type: SourceType
    capture_timestamp: datetime
    source_hash: str = Field(..., min_length=1)
    snapshot_uri: str | None = Field(
        default=None,
        description="Optional local/object-store pointer for retained source content.",
    )
    msil_schema_version: str = Field(
        default=CURRENT_MSIL_SCHEMA_VERSION,
        min_length=1,
    )
    provenance_schema_version: str = Field(
        default=CURRENT_PROVENANCE_SCHEMA_VERSION,
        min_length=1,
    )

    @field_validator("capture_timestamp")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        """Snapshots must carry an unambiguous capture time."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capture_timestamp must be timezone-aware.")
        return value


class SnapshotMetadata(BaseModel):
    """Operational metadata for a retained immutable snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_ref: SourceSnapshotReference
    content_type: str | None = Field(default=None)
    byte_size: int | None = Field(default=None, ge=0)
    storage_backend: str | None = Field(default=None)
    retention_policy: str | None = Field(default=None)
    captured_by: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    msil_schema_version: str = Field(
        default=CURRENT_MSIL_SCHEMA_VERSION,
        min_length=1,
    )
    provenance_schema_version: str = Field(
        default=CURRENT_PROVENANCE_SCHEMA_VERSION,
        min_length=1,
    )

    @field_validator("created_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        """Snapshot metadata timestamps must be timezone-aware."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_versions(self) -> "SnapshotMetadata":
        """Keep metadata version pins aligned with the referenced snapshot."""

        if self.msil_schema_version != self.snapshot_ref.msil_schema_version:
            raise ValueError("SnapshotMetadata msil_schema_version must match snapshot_ref.")
        if (
            self.provenance_schema_version
            != self.snapshot_ref.provenance_schema_version
        ):
            raise ValueError(
                "SnapshotMetadata provenance_schema_version must match snapshot_ref."
            )
        return self


__all__ = ["SnapshotMetadata", "SourceSnapshotReference"]
