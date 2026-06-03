"""Timeline, corporate event, and supersession models for MSIL Phase 6."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import AuthorityClass, ClaimType, EventType, SourceType, TimeBasis
from .versioning import MSILVersionPins, default_version_pins


class EventParticipant(BaseModel):
    """Entity participating in a corporate event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_ref: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)


class EventRelationship(BaseModel):
    """Explicit relationship between two corporate events."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relationship_type: str = Field(..., min_length=1)
    target_event_id: str = Field(..., min_length=1)
    reason: str | None = Field(default=None)


class CorporateEventReference(BaseModel):
    """Lightweight reference to a corporate event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    event_type: EventType
    event_time: datetime
    time_basis: TimeBasis
    source_signal_refs: tuple[str, ...] = Field(..., min_length=1)

    @field_validator("event_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware.")
        return value


class CorporateEvent(BaseModel):
    """First-class dated corporate occurrence derived from event signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str | None = Field(default=None)
    entity_ref: str = Field(..., min_length=1)
    event_type: EventType
    event_time: datetime
    time_basis: TimeBasis
    source_signal_refs: tuple[str, ...] = Field(..., min_length=1)
    numeric_claim_refs: tuple[str, ...] = Field(default_factory=tuple)
    narrative_refs: tuple[str, ...] = Field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = Field(..., min_length=1)
    participants: tuple[EventParticipant, ...] = Field(default_factory=tuple)
    relationships: tuple[EventRelationship, ...] = Field(default_factory=tuple)
    source_type: SourceType
    authority_class: AuthorityClass
    claim_type: ClaimType
    creation_eligible: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    version_pins: MSILVersionPins = Field(default_factory=default_version_pins)

    @field_validator("event_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_and_set_id(self) -> "CorporateEvent":
        if not self.participants:
            object.__setattr__(
                self,
                "participants",
                (EventParticipant(entity_ref=self.entity_ref, role="subject"),),
            )
        if self.entity_ref not in {participant.entity_ref for participant in self.participants}:
            raise ValueError("CorporateEvent participants must include entity_ref.")

        expected_event_id = generate_event_id(self)
        if self.event_id is not None and self.event_id != expected_event_id:
            raise ValueError("event_id does not match deterministic derivation.")
        object.__setattr__(self, "event_id", expected_event_id)
        return self

    def to_reference(self) -> CorporateEventReference:
        """Return a lightweight event reference."""

        return CorporateEventReference(
            event_id=self.event_id or generate_event_id(self),
            entity_ref=self.entity_ref,
            event_type=self.event_type,
            event_time=self.event_time,
            time_basis=self.time_basis,
            source_signal_refs=self.source_signal_refs,
        )


class TimelineEntry(BaseModel):
    """One ordered entry in an entity timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str | None = Field(default=None)
    entity_ref: str = Field(..., min_length=1)
    event_ref: CorporateEventReference
    event_time: datetime
    time_basis: TimeBasis
    event_type: EventType
    source_signal_refs: tuple[str, ...] = Field(..., min_length=1)
    authority_class: AuthorityClass
    claim_type: ClaimType
    current_flag: bool = Field(default=True)
    superseded_by: str | None = Field(default=None)
    supersedes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("event_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_and_set_id(self) -> "TimelineEntry":
        if self.event_ref.entity_ref != self.entity_ref:
            raise ValueError("TimelineEntry entity_ref must match event_ref.entity_ref.")
        if self.event_ref.event_time != self.event_time:
            raise ValueError("TimelineEntry event_time must match event_ref.event_time.")
        if self.event_ref.time_basis != self.time_basis:
            raise ValueError("TimelineEntry time_basis must match event_ref.time_basis.")
        if self.event_ref.event_type != self.event_type:
            raise ValueError("TimelineEntry event_type must match event_ref.event_type.")
        if self.superseded_by and self.current_flag:
            raise ValueError("Superseded entries cannot be current.")

        expected_entry_id = generate_timeline_entry_id(self)
        if self.entry_id is not None and self.entry_id != expected_entry_id:
            raise ValueError("entry_id does not match deterministic derivation.")
        object.__setattr__(self, "entry_id", expected_entry_id)
        return self


class EntityTimeline(BaseModel):
    """Entity-scoped ordered timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_ref: str = Field(..., min_length=1)
    entries: tuple[TimelineEntry, ...] = Field(default_factory=tuple)
    version_pins: MSILVersionPins = Field(default_factory=default_version_pins)

    @model_validator(mode="after")
    def _validate_ordering(self) -> "EntityTimeline":
        if any(entry.entity_ref != self.entity_ref for entry in self.entries):
            raise ValueError("All timeline entries must match entity_ref.")
        sorted_entries = tuple(sorted(self.entries, key=timeline_entry_sort_key))
        if self.entries != sorted_entries:
            raise ValueError("EntityTimeline entries must be chronologically ordered.")
        return self


class TimelineAssemblyResult(BaseModel):
    """Output from timeline assembly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    events: tuple[CorporateEvent, ...] = Field(default_factory=tuple)
    timeline_entries: tuple[TimelineEntry, ...] = Field(default_factory=tuple)
    timelines: tuple[EntityTimeline, ...] = Field(default_factory=tuple)
    ignored_signal_refs: tuple[str, ...] = Field(default_factory=tuple)
    chronology_validation_passed: bool = Field(default=True)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_counts_and_chronology(self) -> "TimelineAssemblyResult":
        if len(self.events) != len(self.timeline_entries):
            raise ValueError("events and timeline_entries counts must match.")
        if self.chronology_validation_passed and not all(
            timeline.entries == tuple(sorted(timeline.entries, key=timeline_entry_sort_key))
            for timeline in self.timelines
        ):
            raise ValueError("chronology_validation_passed cannot be true for unordered timelines.")
        return self


class SupersessionReason(str, Enum):
    """Reason an event supersession candidate was linked or rejected."""

    LATER_EQUAL_OR_HIGHER_AUTHORITY = "later_equal_or_higher_authority"
    NOT_LATER_EVENT_TIME = "not_later_event_time"
    LOWER_AUTHORITY = "lower_authority"
    DIFFERENT_ENTITY = "different_entity"
    INCOMPATIBLE_EVENT_OR_CLAIM_TYPE = "incompatible_event_or_claim_type"
    MISSING_AUTHORITY_RANK = "missing_authority_rank"


class SupersessionLink(BaseModel):
    """Explicit supersession edge. Prior/current records remain preserved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    link_id: str | None = Field(default=None)
    prior_event_id: str = Field(..., min_length=1)
    later_event_id: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    event_type: EventType
    reason: SupersessionReason
    prior_event_time: datetime
    later_event_time: datetime
    prior_authority_class: AuthorityClass
    later_authority_class: AuthorityClass
    claim_type: ClaimType

    @field_validator("prior_event_time", "later_event_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event times must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_and_set_id(self) -> "SupersessionLink":
        if self.later_event_time <= self.prior_event_time:
            raise ValueError("SupersessionLink later_event_time must be after prior_event_time.")
        expected_link_id = generate_supersession_link_id(self)
        if self.link_id is not None and self.link_id != expected_link_id:
            raise ValueError("link_id does not match deterministic derivation.")
        object.__setattr__(self, "link_id", expected_link_id)
        return self


class SupersessionCandidate(BaseModel):
    """Rejected or unresolved supersession candidate diagnostic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prior_event_id: str = Field(..., min_length=1)
    later_event_id: str = Field(..., min_length=1)
    reason: SupersessionReason
    details: str = Field(..., min_length=1)


class SupersessionResult(BaseModel):
    """Supersession links plus unresolved candidate diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    links: tuple[SupersessionLink, ...] = Field(default_factory=tuple)
    unresolved_candidates: tuple[SupersessionCandidate, ...] = Field(default_factory=tuple)
    events_preserved: int = Field(..., ge=0)
    authority_validation_passed: bool = Field(default=True)


def generate_event_id(event: CorporateEvent) -> str:
    """Generate deterministic event id without text payload churn."""

    payload = {
        "entity_ref": event.entity_ref,
        "event_type": event.event_type.value,
        "event_time": event.event_time.isoformat(),
        "time_basis": event.time_basis.value,
        "source_signal_refs": sorted(event.source_signal_refs),
        "provenance_refs": sorted(event.provenance_refs),
        "source_type": event.source_type.value,
        "authority_class": event.authority_class.value,
        "claim_type": event.claim_type.value,
        "msil_schema_version": event.version_pins.msil_schema_version,
    }
    return "evt_" + _digest(payload)


def generate_timeline_entry_id(entry: TimelineEntry) -> str:
    """Generate deterministic timeline entry id."""

    payload = {
        "entity_ref": entry.entity_ref,
        "event_id": entry.event_ref.event_id,
        "event_time": entry.event_time.isoformat(),
    }
    return "tle_" + _digest(payload)


def generate_supersession_link_id(link: SupersessionLink) -> str:
    """Generate deterministic supersession link id."""

    payload = {
        "prior_event_id": link.prior_event_id,
        "later_event_id": link.later_event_id,
        "reason": link.reason.value,
    }
    return "sup_" + _digest(payload)


def event_sort_key(event: CorporateEvent) -> tuple[str, str, str, str]:
    """Chronological deterministic event ordering key."""

    return (
        event.event_time.isoformat(),
        event.entity_ref,
        event.event_type.value,
        event.event_id or generate_event_id(event),
    )


def timeline_entry_sort_key(entry: TimelineEntry) -> tuple[str, str, str, str]:
    """Chronological deterministic timeline-entry ordering key."""

    return (
        entry.event_time.isoformat(),
        entry.entity_ref,
        entry.event_type.value,
        entry.event_ref.event_id,
    )


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "CorporateEvent",
    "CorporateEventReference",
    "EntityTimeline",
    "EventParticipant",
    "EventRelationship",
    "SupersessionCandidate",
    "SupersessionLink",
    "SupersessionReason",
    "SupersessionResult",
    "TimelineAssemblyResult",
    "TimelineEntry",
    "event_sort_key",
    "generate_event_id",
    "timeline_entry_sort_key",
]
