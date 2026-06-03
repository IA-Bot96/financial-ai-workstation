"""Official structured-source adapters for MSIL Phase 5."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from multi_source_intelligence.models import (
    AnnouncementProvenance,
    ClaimType,
    ContentClass,
    EntityResolutionResult,
    EntityScope,
    EventType,
    Horizon,
    IntelligenceSignal,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    PayoutProvenance,
    RegulatoryProvenance,
    ReviewStatus,
    SourceSnapshotReference,
    SourceType,
    TimeBasis,
)
from multi_source_intelligence.models.entity_registry import normalize_identifier

from .authority_assignment import AuthorityAssignmentService
from .authority_assignment import AuthorityAssignmentRequest
from .entity_resolver import EntityResolver


class OfficialSourceIngestionFailure(BaseModel):
    """Failure diagnostic for an official-source record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_name: str = Field(..., min_length=1)
    record_index: int = Field(..., ge=0)
    record_id: str | None = Field(default=None)
    issuer_identifier: str | None = Field(default=None)
    reason: str = Field(..., min_length=1)
    resolution_status: str | None = Field(default=None)


class OfficialSourceAdapterResult(BaseModel):
    """Adapter output for one official source family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_name: str = Field(..., min_length=1)
    source_type: SourceType
    records_processed: int = Field(..., ge=0)
    signals_generated: int = Field(..., ge=0)
    signals: tuple[IntelligenceSignal, ...] = Field(default_factory=tuple)
    failures: tuple[OfficialSourceIngestionFailure, ...] = Field(default_factory=tuple)
    entity_resolution_results: tuple[EntityResolutionResult, ...] = Field(
        default_factory=tuple
    )
    content_class_distribution: dict[str, int] = Field(default_factory=dict)
    authority_distribution: dict[str, int] = Field(default_factory=dict)
    provenance_distribution: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_counts(self) -> "OfficialSourceAdapterResult":
        if self.signals_generated != len(self.signals):
            raise ValueError("signals_generated must equal len(signals).")
        if self.records_processed < len(self.failures):
            raise ValueError("failures cannot exceed records_processed.")
        return self


class _OfficialSourceRecord(BaseModel):
    """Common fields for official structured-source records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issuer_identifier: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    snapshot_ref: SourceSnapshotReference
    retrieved_at: datetime
    verified: bool = Field(default=True)
    source_url: str | None = Field(default=None)

    @field_validator("retrieved_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware.")
        return value


class PSXAnnouncementRecord(_OfficialSourceRecord):
    """Structured PSX announcement record."""

    announcement_id: str = Field(..., min_length=1)
    announcement_time: datetime
    event_type: EventType = Field(default=EventType.RESULTS_ANNOUNCED)

    @field_validator("announcement_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("announcement_time must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_snapshot_source(self) -> "PSXAnnouncementRecord":
        if self.snapshot_ref.source_type != SourceType.PSX_ANNOUNCEMENTS:
            raise ValueError("PSX announcement snapshot_ref must use psx_announcements.")
        return self


class CompanyPayoutRecord(_OfficialSourceRecord):
    """Structured Company Payouts record."""

    payout_id: str = Field(..., min_length=1)
    payout_time: datetime
    payout_type: EventType = Field(default=EventType.DIVIDEND_DECLARED)
    metric_ref: str = Field(default="payout_amount", min_length=1)
    amount: float | int | str = Field(..., description="Raw payout amount/value.")
    unit: str = Field(default="PKR", min_length=1)

    @field_validator("payout_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("payout_time must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_snapshot_source(self) -> "CompanyPayoutRecord":
        if self.snapshot_ref.source_type != SourceType.COMPANY_PAYOUTS:
            raise ValueError("Company payout snapshot_ref must use company_payouts.")
        return self


class SECPNoticeRecord(_OfficialSourceRecord):
    """Structured SECP notice record."""

    notice_id: str = Field(..., min_length=1)
    notice_time: datetime
    event_type: EventType = Field(default=EventType.SECP_ACTION)

    @field_validator("notice_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("notice_time must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_snapshot_source(self) -> "SECPNoticeRecord":
        if self.snapshot_ref.source_type != SourceType.SECP_NOTICES:
            raise ValueError("SECP notice snapshot_ref must use secp_notices.")
        return self


class _OfficialSourceAdapter:
    """Shared adapter mechanics for official structured sources."""

    adapter_name = "OfficialSourceAdapter"
    source_type: SourceType
    record_model: type[_OfficialSourceRecord]

    def __init__(
        self,
        *,
        entity_resolver: EntityResolver | None = None,
        authority_service: AuthorityAssignmentService | None = None,
        entity_scope: EntityScope = EntityScope.COMPANY,
    ) -> None:
        self._entity_resolver = entity_resolver or EntityResolver()
        self._authority_service = authority_service or AuthorityAssignmentService()
        self._entity_scope = entity_scope

    def adapt_records(
        self,
        records: Iterable[_OfficialSourceRecord | dict[str, Any]],
    ) -> OfficialSourceAdapterResult:
        """Convert source records into MSIL signals with failure diagnostics."""

        signals: list[IntelligenceSignal] = []
        failures: list[OfficialSourceIngestionFailure] = []
        resolutions: list[EntityResolutionResult] = []
        records_processed = 0
        for index, raw_record in enumerate(records):
            records_processed += 1
            try:
                record = self.record_model.model_validate(raw_record)
                resolution = self._entity_resolver.resolve(record.issuer_identifier)
                resolutions.append(resolution)
                if resolution.review_status != ReviewStatus.RESOLVED:
                    failures.append(
                        self._failure(
                            index=index,
                            record=record,
                            reason="entity_resolution_not_resolved",
                            resolution_status=resolution.review_status.value,
                        )
                    )
                    continue
                signals.extend(self._signals_for_record(record, resolution, index))
            except Exception as exc:  # noqa: BLE001 - diagnostics required.
                failures.append(
                    OfficialSourceIngestionFailure(
                        adapter_name=self.adapter_name,
                        record_index=index,
                        record_id=_record_id(raw_record),
                        issuer_identifier=_issuer_identifier(raw_record),
                        reason=str(exc),
                    )
                )

        return OfficialSourceAdapterResult(
            adapter_name=self.adapter_name,
            source_type=self.source_type,
            records_processed=records_processed,
            signals_generated=len(signals),
            signals=tuple(signals),
            failures=tuple(failures),
            entity_resolution_results=tuple(resolutions),
            content_class_distribution=dict(
                Counter(signal.content.content_class.value for signal in signals)
            ),
            authority_distribution=dict(
                Counter(signal.classification.authority_class.value for signal in signals)
            ),
            provenance_distribution=dict(
                Counter(signal.provenance.provenance_type.value for signal in signals)
            ),
        )

    def audit_result(self, result: OfficialSourceAdapterResult) -> dict[str, Any]:
        """Build JSON-serializable audit metrics for one result."""

        return {
            "adapter_name": result.adapter_name,
            "source_type": result.source_type.value,
            "records_processed": result.records_processed,
            "signals_generated": result.signals_generated,
            "entity_resolution_results": [
                item.model_dump(mode="json") for item in result.entity_resolution_results
            ],
            "entity_resolution_status_distribution": dict(
                Counter(item.review_status.value for item in result.entity_resolution_results)
            ),
            "content_class_distribution": result.content_class_distribution,
            "authority_distribution": result.authority_distribution,
            "provenance_distribution": result.provenance_distribution,
            "failures_recorded": len(result.failures),
            "failures": [failure.model_dump(mode="json") for failure in result.failures],
        }

    def _signals_for_record(
        self,
        record: _OfficialSourceRecord,
        resolution: EntityResolutionResult,
        index: int,
    ) -> tuple[IntelligenceSignal, ...]:
        raise RuntimeError("_signals_for_record must be implemented by concrete adapters.")

    def _classification(
        self,
        *,
        content_class: ContentClass,
        claim_type: ClaimType | None = None,
        numeric_reference_only: bool = False,
        verified: bool = True,
    ):
        assignment = self._authority_service.assign(
            AuthorityAssignmentRequest(
                source_type=self.source_type,
                content_class=content_class,
                claim_type=claim_type,
                verified=verified,
                numeric_reference_only=numeric_reference_only,
            )
        )
        if not assignment.is_valid:
            raise ValueError(
                "invalid authority assignment: "
                + "; ".join(assignment.invalid_mappings)
            )
        return assignment.to_classification()

    def _metadata(
        self,
        *,
        record: _OfficialSourceRecord,
        observation_time: datetime,
        horizon: Horizon = Horizon.CURRENT,
        source_record_id: str,
    ) -> IntelligenceSignalMetadata:
        return IntelligenceSignalMetadata(
            observation_time=observation_time,
            subject_period=None,
            time_basis=TimeBasis.CALENDAR,
            horizon=horizon,
            source_independent_of_issuer=self._source_independent_of_issuer(),
            verified=record.verified,
            trust_prior=0.95,
            source_record_id=source_record_id,
            source_lineage_hooks=tuple(
                item
                for item in (
                    f"{self.source_type.value}:{source_record_id}",
                    record.source_url,
                )
                if item
            ),
        )

    def _source_independent_of_issuer(self) -> bool:
        return self.source_type == SourceType.SECP_NOTICES

    def _failure(
        self,
        *,
        index: int,
        record: _OfficialSourceRecord,
        reason: str,
        resolution_status: str | None = None,
    ) -> OfficialSourceIngestionFailure:
        return OfficialSourceIngestionFailure(
            adapter_name=self.adapter_name,
            record_index=index,
            record_id=_record_id(record),
            issuer_identifier=record.issuer_identifier,
            reason=reason,
            resolution_status=resolution_status,
        )


class PSXAnnouncementAdapter(_OfficialSourceAdapter):
    """Convert PSX announcements into narrative and event signals."""

    adapter_name = "PSXAnnouncementAdapter"
    source_type = SourceType.PSX_ANNOUNCEMENTS
    record_model = PSXAnnouncementRecord

    def _signals_for_record(
        self,
        record: PSXAnnouncementRecord,
        resolution: EntityResolutionResult,
        index: int,
    ) -> tuple[IntelligenceSignal, ...]:
        provenance = AnnouncementProvenance(
            announcement_id=record.announcement_id,
            snapshot_ref=record.snapshot_ref,
            retrieved_at=record.retrieved_at,
            verified=record.verified,
            source_lineage=(f"psx_announcement:{record.announcement_id}",),
        )
        return (
            self._narrative_signal(record, resolution, index, provenance),
            self._event_signal(record, resolution, index, provenance),
        )

    def _narrative_signal(
        self,
        record: PSXAnnouncementRecord,
        resolution: EntityResolutionResult,
        index: int,
        provenance: AnnouncementProvenance,
    ) -> IntelligenceSignal:
        record_id = record.announcement_id
        return IntelligenceSignal(
            entity_ref=resolution.resolved_entity_ref or "",
            entity_scope=self._entity_scope,
            entity_resolution=resolution,
            content=IntelligenceSignalContent(
                content_class=ContentClass.NARRATIVE_CLAIM,
                identity_key=_identity_key(self.source_type, record_id, index, "narrative"),
                claim_text=_join_text(record.title, record.body),
                normalized_claim_text=normalize_identifier(_join_text(record.title, record.body)),
                payload=_common_payload(record, record_id),
            ),
            classification=self._classification(
                content_class=ContentClass.NARRATIVE_CLAIM,
                verified=record.verified,
            ),
            metadata=self._metadata(
                record=record,
                observation_time=record.announcement_time,
                source_record_id=record_id,
            ),
            provenance=provenance,
        )

    def _event_signal(
        self,
        record: PSXAnnouncementRecord,
        resolution: EntityResolutionResult,
        index: int,
        provenance: AnnouncementProvenance,
    ) -> IntelligenceSignal:
        record_id = record.announcement_id
        return IntelligenceSignal(
            entity_ref=resolution.resolved_entity_ref or "",
            entity_scope=self._entity_scope,
            entity_resolution=resolution,
            content=IntelligenceSignalContent(
                content_class=ContentClass.CORPORATE_EVENT,
                identity_key=_identity_key(self.source_type, record_id, index, "event"),
                event_type=record.event_type,
                payload={**_common_payload(record, record_id), "event_type": record.event_type.value},
            ),
            classification=self._classification(
                content_class=ContentClass.CORPORATE_EVENT,
                verified=record.verified,
            ),
            metadata=self._metadata(
                record=record,
                observation_time=record.announcement_time,
                source_record_id=record_id,
            ),
            provenance=provenance,
        )


class CompanyPayoutAdapter(_OfficialSourceAdapter):
    """Convert Company Payouts records into event and numeric claim signals."""

    adapter_name = "CompanyPayoutAdapter"
    source_type = SourceType.COMPANY_PAYOUTS
    record_model = CompanyPayoutRecord

    def _signals_for_record(
        self,
        record: CompanyPayoutRecord,
        resolution: EntityResolutionResult,
        index: int,
    ) -> tuple[IntelligenceSignal, ...]:
        provenance = PayoutProvenance(
            payout_id=record.payout_id,
            snapshot_ref=record.snapshot_ref,
            retrieved_at=record.retrieved_at,
            verified=record.verified,
            source_lineage=(f"company_payout:{record.payout_id}",),
        )
        return (
            self._event_signal(record, resolution, index, provenance),
            self._numeric_signal(record, resolution, index, provenance),
        )

    def _event_signal(
        self,
        record: CompanyPayoutRecord,
        resolution: EntityResolutionResult,
        index: int,
        provenance: PayoutProvenance,
    ) -> IntelligenceSignal:
        record_id = record.payout_id
        return IntelligenceSignal(
            entity_ref=resolution.resolved_entity_ref or "",
            entity_scope=self._entity_scope,
            entity_resolution=resolution,
            content=IntelligenceSignalContent(
                content_class=ContentClass.CORPORATE_EVENT,
                identity_key=_identity_key(self.source_type, record_id, index, "event"),
                event_type=record.payout_type,
                payload={
                    **_common_payload(record, record_id),
                    "event_type": record.payout_type.value,
                    "amount": record.amount,
                    "unit": record.unit,
                },
            ),
            classification=self._classification(
                content_class=ContentClass.CORPORATE_EVENT,
                verified=record.verified,
            ),
            metadata=self._metadata(
                record=record,
                observation_time=record.payout_time,
                source_record_id=record_id,
            ),
            provenance=provenance,
        )

    def _numeric_signal(
        self,
        record: CompanyPayoutRecord,
        resolution: EntityResolutionResult,
        index: int,
        provenance: PayoutProvenance,
    ) -> IntelligenceSignal:
        record_id = record.payout_id
        return IntelligenceSignal(
            entity_ref=resolution.resolved_entity_ref or "",
            entity_scope=self._entity_scope,
            entity_resolution=resolution,
            content=IntelligenceSignalContent(
                content_class=ContentClass.NUMERIC_CLAIM,
                identity_key=_identity_key(self.source_type, record_id, index, "numeric"),
                metric_ref=record.metric_ref,
                value=record.amount,
                unit=record.unit,
                payload={
                    **_common_payload(record, record_id),
                    "numeric_reference_only": False,
                    "fve_candidate": True,
                },
            ),
            classification=self._classification(
                content_class=ContentClass.NUMERIC_CLAIM,
                claim_type=ClaimType.CORPORATE_ACTION_FACT,
                verified=record.verified,
            ),
            metadata=self._metadata(
                record=record,
                observation_time=record.payout_time,
                source_record_id=record_id,
            ),
            provenance=provenance,
        )


class SECPNoticeAdapter(_OfficialSourceAdapter):
    """Convert SECP notices into regulatory narrative and event signals."""

    adapter_name = "SECPNoticeAdapter"
    source_type = SourceType.SECP_NOTICES
    record_model = SECPNoticeRecord

    def _signals_for_record(
        self,
        record: SECPNoticeRecord,
        resolution: EntityResolutionResult,
        index: int,
    ) -> tuple[IntelligenceSignal, ...]:
        provenance = RegulatoryProvenance(
            notice_id=record.notice_id,
            snapshot_ref=record.snapshot_ref,
            retrieved_at=record.retrieved_at,
            verified=record.verified,
            source_lineage=(f"secp_notice:{record.notice_id}",),
        )
        return (
            self._narrative_signal(record, resolution, index, provenance),
            self._event_signal(record, resolution, index, provenance),
        )

    def _narrative_signal(
        self,
        record: SECPNoticeRecord,
        resolution: EntityResolutionResult,
        index: int,
        provenance: RegulatoryProvenance,
    ) -> IntelligenceSignal:
        record_id = record.notice_id
        return IntelligenceSignal(
            entity_ref=resolution.resolved_entity_ref or "",
            entity_scope=self._entity_scope,
            entity_resolution=resolution,
            content=IntelligenceSignalContent(
                content_class=ContentClass.NARRATIVE_CLAIM,
                identity_key=_identity_key(self.source_type, record_id, index, "narrative"),
                claim_text=_join_text(record.title, record.body),
                normalized_claim_text=normalize_identifier(_join_text(record.title, record.body)),
                payload=_common_payload(record, record_id),
            ),
            classification=self._classification(
                content_class=ContentClass.NARRATIVE_CLAIM,
                verified=record.verified,
            ),
            metadata=self._metadata(
                record=record,
                observation_time=record.notice_time,
                source_record_id=record_id,
            ),
            provenance=provenance,
        )

    def _event_signal(
        self,
        record: SECPNoticeRecord,
        resolution: EntityResolutionResult,
        index: int,
        provenance: RegulatoryProvenance,
    ) -> IntelligenceSignal:
        record_id = record.notice_id
        return IntelligenceSignal(
            entity_ref=resolution.resolved_entity_ref or "",
            entity_scope=self._entity_scope,
            entity_resolution=resolution,
            content=IntelligenceSignalContent(
                content_class=ContentClass.CORPORATE_EVENT,
                identity_key=_identity_key(self.source_type, record_id, index, "event"),
                event_type=record.event_type,
                payload={**_common_payload(record, record_id), "event_type": record.event_type.value},
            ),
            classification=self._classification(
                content_class=ContentClass.CORPORATE_EVENT,
                verified=record.verified,
            ),
            metadata=self._metadata(
                record=record,
                observation_time=record.notice_time,
                source_record_id=record_id,
            ),
            provenance=provenance,
        )

    def _source_independent_of_issuer(self) -> bool:
        return True


def build_official_sources_audit(
    results: Iterable[OfficialSourceAdapterResult],
) -> dict[str, Any]:
    """Aggregate official-source adapter results into the Phase 5 audit."""

    result_list = list(results)
    signals = [signal for result in result_list for signal in result.signals]
    failures = [failure for result in result_list for failure in result.failures]
    resolutions = [
        resolution
        for result in result_list
        for resolution in result.entity_resolution_results
    ]
    return {
        "audit_name": "msil_official_sources_audit",
        "phase": "MSIL Phase 5",
        "records_processed": sum(result.records_processed for result in result_list),
        "signals_generated": len(signals),
        "source_results": [
            {
                "adapter_name": result.adapter_name,
                "source_type": result.source_type.value,
                "records_processed": result.records_processed,
                "signals_generated": result.signals_generated,
                "failures_recorded": len(result.failures),
            }
            for result in result_list
        ],
        "entity_resolution_results": [
            item.model_dump(mode="json") for item in resolutions
        ],
        "entity_resolution_status_distribution": dict(
            Counter(item.review_status.value for item in resolutions)
        ),
        "content_class_distribution": dict(
            Counter(signal.content.content_class.value for signal in signals)
        ),
        "authority_distribution": dict(
            Counter(signal.classification.authority_class.value for signal in signals)
        ),
        "provenance_distribution": dict(
            Counter(signal.provenance.provenance_type.value for signal in signals)
        ),
        "failures_recorded": len(failures),
        "failures": [failure.model_dump(mode="json") for failure in failures],
        "snapshot_coverage": {
            "signals_with_snapshot_ref": sum(
                1 for signal in signals if getattr(signal.provenance, "snapshot_ref", None)
            ),
            "signals_generated": len(signals),
            "all_signals_snapshot_backed": all(
                bool(getattr(signal.provenance, "snapshot_ref", None))
                for signal in signals
            )
            if signals
            else True,
        },
    }


def _identity_key(
    source_type: SourceType,
    record_id: str,
    index: int,
    suffix: str,
) -> str:
    return f"{source_type.value}:{record_id}:index:{index}:{suffix}"


def _join_text(title: str, body: str) -> str:
    return " ".join(part.strip() for part in (title, body) if part.strip())


def _common_payload(record: _OfficialSourceRecord, record_id: str) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "issuer_identifier": record.issuer_identifier,
        "title": record.title,
        "source_url": record.source_url,
        "verified": record.verified,
        "snapshot_id": record.snapshot_ref.snapshot_id,
    }


def _record_id(record: Any) -> str | None:
    for field in ("announcement_id", "payout_id", "notice_id"):
        if isinstance(record, dict):
            value = record.get(field)
        else:
            value = getattr(record, field, None)
        if value:
            return str(value)
    return None


def _issuer_identifier(record: Any) -> str | None:
    if isinstance(record, dict):
        value = record.get("issuer_identifier")
    else:
        value = getattr(record, "issuer_identifier", None)
    return str(value) if value else None


__all__ = [
    "CompanyPayoutAdapter",
    "CompanyPayoutRecord",
    "OfficialSourceAdapterResult",
    "OfficialSourceIngestionFailure",
    "PSXAnnouncementAdapter",
    "PSXAnnouncementRecord",
    "SECPNoticeAdapter",
    "SECPNoticeRecord",
    "build_official_sources_audit",
]
