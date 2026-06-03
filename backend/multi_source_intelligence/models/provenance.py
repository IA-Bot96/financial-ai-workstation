"""Frozen MSIL provenance schema models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ProvenanceType, SourceType
from .versioning import CURRENT_PROVENANCE_SCHEMA_VERSION


class ProvenanceRequirement(BaseModel):
    """Schema requirement for one provenance discriminator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: ProvenanceType = Field(..., description="Discriminator.")
    source_types: tuple[SourceType, ...] = Field(
        default_factory=tuple,
        description="Source families that use this provenance type.",
    )
    snapshot_required: bool = Field(
        ..., description="Whether immutable snapshot_ref is mandatory."
    )
    required_fields: tuple[str, ...] = Field(
        ..., min_length=1, description="Required locator fields."
    )
    verified_required_for_full_authority: bool = Field(
        default=True,
        description="Unverified sources may be authority-capped in later phases.",
    )
    forbidden_to_emit: bool = Field(
        default=False,
        description="Whether this provenance type may appear on emitted records.",
    )
    false_precision_warning: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_requirement(self) -> "ProvenanceRequirement":
        """Validate frozen provenance invariants."""

        if self.provenance_type == ProvenanceType.NONE:
            if not self.forbidden_to_emit:
                raise ValueError("NONE provenance must be forbidden_to_emit.")
            return self
        if self.forbidden_to_emit:
            raise ValueError("Only NONE provenance may be forbidden_to_emit.")
        if self.provenance_type != ProvenanceType.PDF_PAGE and not self.snapshot_required:
            raise ValueError("Non-PDF provenance requires immutable snapshot_ref.")
        if len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError("required_fields cannot contain duplicates.")
        return self


class ProvenanceSchema(BaseModel):
    """Versioned provenance schema registry."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "provenance_schema_version": "1.0.0",
                    "requirements": [
                        {
                            "provenance_type": "PDF_PAGE",
                            "source_types": ["annual_report"],
                            "snapshot_required": False,
                            "required_fields": [
                                "workbook_fingerprint",
                                "page_number",
                            ],
                        }
                    ],
                }
            ]
        },
    )

    provenance_schema_version: str = Field(..., min_length=1)
    requirements: tuple[ProvenanceRequirement, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_schema_totality(self) -> "ProvenanceSchema":
        """Require exactly one schema requirement for every provenance type."""

        provenance_types = [requirement.provenance_type for requirement in self.requirements]
        duplicates = {
            provenance_type
            for provenance_type in provenance_types
            if provenance_types.count(provenance_type) > 1
        }
        if duplicates:
            raise ValueError(
                "provenance schema contains duplicate provenance_type entries: "
                + ", ".join(sorted(item.value for item in duplicates))
            )
        missing = set(ProvenanceType) - set(provenance_types)
        if missing:
            raise ValueError(
                "provenance schema missing provenance_type entries: "
                + ", ".join(sorted(item.value for item in missing))
            )
        none_requirement = self.requirement_for(ProvenanceType.NONE)
        if not none_requirement.forbidden_to_emit:
            raise ValueError("NONE provenance must be forbidden.")
        return self

    def requirement_for(self, provenance_type: ProvenanceType) -> ProvenanceRequirement:
        """Return the requirement for a provenance discriminator."""

        for requirement in self.requirements:
            if requirement.provenance_type == provenance_type:
                return requirement
        raise KeyError(f"Provenance type is not present: {provenance_type.value}")


def default_provenance_schema() -> ProvenanceSchema:
    """Return the frozen Phase 0 provenance schema."""

    return ProvenanceSchema(
        provenance_schema_version=CURRENT_PROVENANCE_SCHEMA_VERSION,
        requirements=(
            ProvenanceRequirement(
                provenance_type=ProvenanceType.PDF_PAGE,
                source_types=(SourceType.ANNUAL_REPORT,),
                snapshot_required=False,
                required_fields=("workbook_fingerprint", "page_number"),
                false_precision_warning="PDF citations use page/workbook fingerprint.",
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.ANNOUNCEMENT_REF,
                source_types=(SourceType.PSX_ANNOUNCEMENTS,),
                snapshot_required=True,
                required_fields=("announcement_id", "snapshot_ref", "retrieved_at"),
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.REGULATORY_REF,
                source_types=(SourceType.SECP_NOTICES,),
                snapshot_required=True,
                required_fields=("notice_id", "snapshot_ref", "retrieved_at"),
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.PAYOUT_REF,
                source_types=(SourceType.COMPANY_PAYOUTS,),
                snapshot_required=True,
                required_fields=("payout_id", "snapshot_ref", "retrieved_at"),
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.MARKET_DATA_REF,
                source_types=(SourceType.MARKET_WATCH,),
                snapshot_required=True,
                required_fields=("series_id", "trade_date", "snapshot_ref", "retrieved_at"),
                false_precision_warning="Market data cites date and series, not a page.",
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.FUTURES_REF,
                source_types=(SourceType.FUTURES_MARKET_WATCH,),
                snapshot_required=True,
                required_fields=("series_id", "contract", "trade_date", "snapshot_ref", "retrieved_at"),
                false_precision_warning="Futures data cites contract/date/series.",
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.SECTOR_REF,
                source_types=(SourceType.SECTOR_SUMMARY,),
                snapshot_required=True,
                required_fields=("sector_ref", "snapshot_ref", "retrieved_at"),
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.URL_SNAPSHOT,
                source_types=(
                    SourceType.COMPANY_OVERVIEW,
                    SourceType.ANALYSIS_REPORTS,
                ),
                snapshot_required=True,
                required_fields=("url", "snapshot_ref", "retrieved_at"),
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.NEWS_REF,
                source_types=(SourceType.NEWS_SOURCES,),
                snapshot_required=True,
                required_fields=("publisher", "url", "snapshot_ref", "retrieved_at"),
            ),
            ProvenanceRequirement(
                provenance_type=ProvenanceType.NONE,
                source_types=(),
                snapshot_required=False,
                required_fields=("forbidden",),
                forbidden_to_emit=True,
                false_precision_warning="NONE provenance is forbidden for emitted records.",
            ),
        ),
    )


__all__ = [
    "ProvenanceRequirement",
    "ProvenanceSchema",
    "default_provenance_schema",
]
