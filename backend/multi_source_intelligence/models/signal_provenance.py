"""Concrete provenance references for emitted MSIL signals."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import ProvenanceType, SourceType
from .snapshots import SourceSnapshotReference
from .versioning import CURRENT_PROVENANCE_SCHEMA_VERSION


class _ProvenanceBase(BaseModel):
    """Common immutable provenance fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retrieved_at: datetime | None = Field(default=None)
    verified: bool = Field(default=True)
    source_lineage: tuple[str, ...] = Field(default_factory=tuple)
    provenance_schema_version: str = Field(
        default=CURRENT_PROVENANCE_SCHEMA_VERSION,
        min_length=1,
    )

    @field_validator("retrieved_at")
    @classmethod
    def _require_timezone(cls, value: datetime | None) -> datetime | None:
        """Require unambiguous retrieval timestamps when present."""

        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("retrieved_at must be timezone-aware.")
        return value


class PDFPageProvenance(_ProvenanceBase):
    """Annual-report workbook/page provenance."""

    provenance_type: Literal[ProvenanceType.PDF_PAGE] = ProvenanceType.PDF_PAGE
    source_type: Literal[SourceType.ANNUAL_REPORT] = SourceType.ANNUAL_REPORT
    workbook_fingerprint: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=1)
    report_reference: str | None = Field(
        default=None,
        description="Stable annual-report source reference used by adapters.",
    )
    source_report_year: int | None = Field(default=None, ge=1900)
    source_section: str | None = Field(default=None, min_length=1)
    cell_reference: str | None = Field(default=None)
    snapshot_ref: None = Field(
        default=None,
        description="Annual-report PDF provenance uses workbook fingerprint, not a web snapshot.",
    )


class AnnouncementProvenance(_ProvenanceBase):
    """PSX announcement reference provenance."""

    provenance_type: Literal[ProvenanceType.ANNOUNCEMENT_REF] = (
        ProvenanceType.ANNOUNCEMENT_REF
    )
    source_type: Literal[SourceType.PSX_ANNOUNCEMENTS] = (
        SourceType.PSX_ANNOUNCEMENTS
    )
    announcement_id: str = Field(..., min_length=1)
    snapshot_ref: SourceSnapshotReference


class RegulatoryProvenance(_ProvenanceBase):
    """SECP/regulatory notice reference provenance."""

    provenance_type: Literal[ProvenanceType.REGULATORY_REF] = (
        ProvenanceType.REGULATORY_REF
    )
    source_type: Literal[SourceType.SECP_NOTICES] = SourceType.SECP_NOTICES
    notice_id: str = Field(..., min_length=1)
    snapshot_ref: SourceSnapshotReference


class PayoutProvenance(_ProvenanceBase):
    """Company payout reference provenance."""

    provenance_type: Literal[ProvenanceType.PAYOUT_REF] = ProvenanceType.PAYOUT_REF
    source_type: Literal[SourceType.COMPANY_PAYOUTS] = SourceType.COMPANY_PAYOUTS
    payout_id: str = Field(..., min_length=1)
    snapshot_ref: SourceSnapshotReference


class MarketDataProvenance(_ProvenanceBase):
    """Market Watch date/series provenance."""

    provenance_type: Literal[ProvenanceType.MARKET_DATA_REF] = (
        ProvenanceType.MARKET_DATA_REF
    )
    source_type: Literal[SourceType.MARKET_WATCH] = SourceType.MARKET_WATCH
    series_id: str = Field(..., min_length=1)
    trade_date: date
    snapshot_ref: SourceSnapshotReference


class FuturesProvenance(_ProvenanceBase):
    """Futures Market Watch date/contract/series provenance."""

    provenance_type: Literal[ProvenanceType.FUTURES_REF] = ProvenanceType.FUTURES_REF
    source_type: Literal[SourceType.FUTURES_MARKET_WATCH] = (
        SourceType.FUTURES_MARKET_WATCH
    )
    series_id: str = Field(..., min_length=1)
    contract: str = Field(..., min_length=1)
    trade_date: date
    snapshot_ref: SourceSnapshotReference


class SectorProvenance(_ProvenanceBase):
    """Sector summary provenance."""

    provenance_type: Literal[ProvenanceType.SECTOR_REF] = ProvenanceType.SECTOR_REF
    source_type: Literal[SourceType.SECTOR_SUMMARY] = SourceType.SECTOR_SUMMARY
    sector_ref: str = Field(..., min_length=1)
    snapshot_ref: SourceSnapshotReference


class URLSnapshotProvenance(_ProvenanceBase):
    """URL-backed source provenance for overview and analysis sources."""

    provenance_type: Literal[ProvenanceType.URL_SNAPSHOT] = ProvenanceType.URL_SNAPSHOT
    source_type: SourceType = Field(
        ...,
        description="Must be company_overview or analysis_reports.",
    )
    url: str = Field(..., min_length=1)
    snapshot_ref: SourceSnapshotReference

    @model_validator(mode="after")
    def _validate_source_type(self) -> "URLSnapshotProvenance":
        """Constrain URL snapshots to frozen URL-backed source families."""

        if self.source_type not in {
            SourceType.COMPANY_OVERVIEW,
            SourceType.ANALYSIS_REPORTS,
        }:
            raise ValueError(
                "URL_SNAPSHOT provenance requires company_overview or analysis_reports."
            )
        return self


class NewsProvenance(_ProvenanceBase):
    """News source provenance."""

    provenance_type: Literal[ProvenanceType.NEWS_REF] = ProvenanceType.NEWS_REF
    source_type: Literal[SourceType.NEWS_SOURCES] = SourceType.NEWS_SOURCES
    publisher: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    snapshot_ref: SourceSnapshotReference


IntelligenceSignalProvenance = Annotated[
    PDFPageProvenance
    | AnnouncementProvenance
    | RegulatoryProvenance
    | PayoutProvenance
    | MarketDataProvenance
    | FuturesProvenance
    | SectorProvenance
    | URLSnapshotProvenance
    | NewsProvenance,
    Field(discriminator="provenance_type"),
]


__all__ = [
    "AnnouncementProvenance",
    "FuturesProvenance",
    "IntelligenceSignalProvenance",
    "MarketDataProvenance",
    "NewsProvenance",
    "PDFPageProvenance",
    "PayoutProvenance",
    "RegulatoryProvenance",
    "SectorProvenance",
    "URLSnapshotProvenance",
]
