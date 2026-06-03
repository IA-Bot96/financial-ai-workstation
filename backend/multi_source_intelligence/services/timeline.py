"""Timeline assembly and supersession services for MSIL Phase 6."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from multi_source_intelligence.models import (
    AuthorityMatrix,
    ContentClass,
    EventType,
    IntelligenceSignal,
    ProvenanceType,
    default_authority_matrix,
)
from multi_source_intelligence.models.timeline import (
    CorporateEvent,
    EntityTimeline,
    SupersessionCandidate,
    SupersessionLink,
    SupersessionReason,
    SupersessionResult,
    TimelineAssemblyResult,
    TimelineEntry,
    event_sort_key,
    timeline_entry_sort_key,
)


_EVENT_TYPE_TRANSITIONS: set[tuple[EventType, EventType]] = {
    (EventType.DIVIDEND_DECLARED, EventType.DIVIDEND_PAID),
}


class TimelineAssemblyService:
    """Build entity-scoped event timelines from MSIL IntelligenceSignal objects."""

    def assemble(
        self,
        signals: Iterable[IntelligenceSignal],
    ) -> TimelineAssemblyResult:
        """Create corporate events and per-entity timelines deterministically."""

        signal_list = tuple(signals)
        signals_by_record = _signals_by_source_record(signal_list)
        events: list[CorporateEvent] = []
        ignored_signal_refs: list[str] = []

        for signal in signal_list:
            if signal.content.content_class != ContentClass.CORPORATE_EVENT:
                ignored_signal_refs.append(signal.signal_id or "")
                continue

            siblings = signals_by_record[_source_record_key(signal)]
            numeric_refs = tuple(
                sorted(
                    sibling.signal_id or ""
                    for sibling in siblings
                    if sibling.content.content_class == ContentClass.NUMERIC_CLAIM
                )
            )
            narrative_refs = tuple(
                sorted(
                    sibling.signal_id or ""
                    for sibling in siblings
                    if sibling.content.content_class == ContentClass.NARRATIVE_CLAIM
                )
            )

            event = CorporateEvent(
                entity_ref=signal.entity_ref,
                event_type=signal.content.event_type,
                event_time=signal.metadata.observation_time,
                time_basis=signal.metadata.time_basis,
                source_signal_refs=(signal.signal_id or "",),
                numeric_claim_refs=numeric_refs,
                narrative_refs=narrative_refs,
                provenance_refs=(_provenance_reference(signal),),
                source_type=signal.classification.source_type,
                authority_class=signal.classification.authority_class,
                claim_type=signal.classification.claim_type,
                creation_eligible=signal.classification.creation_eligible,
                payload={
                    "source_signal_id": signal.signal_id,
                    "source_record_id": signal.metadata.source_record_id,
                    "source_type": signal.classification.source_type.value,
                    "source_payload": signal.content.payload,
                },
            )
            events.append(event)

        sorted_events = tuple(sorted(events, key=event_sort_key))
        entries = tuple(_timeline_entry_for_event(event) for event in sorted_events)
        timelines = _entity_timelines(entries)
        chronology_passed = _chronology_valid(timelines)

        return TimelineAssemblyResult(
            events=sorted_events,
            timeline_entries=entries,
            timelines=timelines,
            ignored_signal_refs=tuple(ref for ref in ignored_signal_refs if ref),
            chronology_validation_passed=chronology_passed,
            diagnostics={
                "signals_received": len(signal_list),
                "corporate_event_signals": len(sorted_events),
                "ignored_non_event_signals": len(ignored_signal_refs),
                "entity_count": len(timelines),
                "event_type_distribution": dict(
                    Counter(event.event_type.value for event in sorted_events)
                ),
                "time_basis_distribution": dict(
                    Counter(event.time_basis.value for event in sorted_events)
                ),
            },
        )


class SupersessionService:
    """Apply frozen supersession rules without deleting or rewriting history."""

    def __init__(self, authority_matrix: AuthorityMatrix | None = None) -> None:
        self._authority_matrix = authority_matrix or default_authority_matrix()

    def evaluate(
        self,
        events: Iterable[CorporateEvent],
    ) -> SupersessionResult:
        """Return explicit supersession links plus unresolved candidates."""

        sorted_events = tuple(sorted(events, key=event_sort_key))
        links: list[SupersessionLink] = []
        unresolved: list[SupersessionCandidate] = []

        for index, prior in enumerate(sorted_events):
            for later in sorted_events[index + 1 :]:
                if prior.entity_ref != later.entity_ref:
                    continue
                if not _same_or_transition_event_type(prior, later):
                    continue
                if prior.claim_type != later.claim_type:
                    unresolved.append(
                        _candidate(
                            prior,
                            later,
                            SupersessionReason.INCOMPATIBLE_EVENT_OR_CLAIM_TYPE,
                            "same event subject has incompatible claim_type values",
                        )
                    )
                    continue
                if later.event_time <= prior.event_time:
                    unresolved.append(
                        _candidate(
                            prior,
                            later,
                            SupersessionReason.NOT_LATER_EVENT_TIME,
                            "later candidate is not after prior event_time",
                        )
                    )
                    continue

                prior_rank = self._authority_matrix.effective_rank(
                    claim_type=prior.claim_type,
                    authority_class=prior.authority_class,
                )
                later_rank = self._authority_matrix.effective_rank(
                    claim_type=later.claim_type,
                    authority_class=later.authority_class,
                )
                if prior_rank is None or later_rank is None:
                    unresolved.append(
                        _candidate(
                            prior,
                            later,
                            SupersessionReason.MISSING_AUTHORITY_RANK,
                            "one or both authority classes are unranked for claim_type",
                        )
                    )
                    continue
                if later_rank > prior_rank:
                    unresolved.append(
                        _candidate(
                            prior,
                            later,
                            SupersessionReason.LOWER_AUTHORITY,
                            "later candidate has lower claim-scoped authority",
                        )
                    )
                    continue

                links.append(
                    SupersessionLink(
                        prior_event_id=prior.event_id or "",
                        later_event_id=later.event_id or "",
                        entity_ref=prior.entity_ref,
                        event_type=prior.event_type,
                        reason=SupersessionReason.LATER_EQUAL_OR_HIGHER_AUTHORITY,
                        prior_event_time=prior.event_time,
                        later_event_time=later.event_time,
                        prior_authority_class=prior.authority_class,
                        later_authority_class=later.authority_class,
                        claim_type=prior.claim_type,
                    )
                )

        return SupersessionResult(
            links=tuple(sorted(links, key=lambda link: link.link_id or "")),
            unresolved_candidates=tuple(
                sorted(
                    unresolved,
                    key=lambda item: (
                        item.prior_event_id,
                        item.later_event_id,
                        item.reason.value,
                    ),
                )
            ),
            events_preserved=len(sorted_events),
            authority_validation_passed=_links_respect_authority(
                links,
                self._authority_matrix,
            ),
        )


def build_timeline_audit(
    *,
    assembly_result: TimelineAssemblyResult,
    supersession_result: SupersessionResult,
) -> dict[str, Any]:
    """Build the Phase 6 timeline audit payload."""

    return {
        "audit_name": "timeline_audit",
        "phase": "MSIL Phase 6",
        "events_created": len(assembly_result.events),
        "timeline_entries_created": len(assembly_result.timeline_entries),
        "entities_with_timelines": len(assembly_result.timelines),
        "entity_timelines": [
            {
                "entity_ref": timeline.entity_ref,
                "entry_count": len(timeline.entries),
                "entry_ids": [entry.entry_id for entry in timeline.entries],
            }
            for timeline in assembly_result.timelines
        ],
        "event_type_distribution": assembly_result.diagnostics.get(
            "event_type_distribution",
            {},
        ),
        "time_basis_distribution": assembly_result.diagnostics.get(
            "time_basis_distribution",
            {},
        ),
        "supersession_links": len(supersession_result.links),
        "supersession_link_details": [
            link.model_dump(mode="json") for link in supersession_result.links
        ],
        "unresolved_candidates": len(supersession_result.unresolved_candidates),
        "unresolved_candidate_details": [
            candidate.model_dump(mode="json")
            for candidate in supersession_result.unresolved_candidates
        ],
        "chronology_validation": {
            "passed": assembly_result.chronology_validation_passed,
            "timelines_checked": len(assembly_result.timelines),
        },
        "authority_validation": {
            "passed": supersession_result.authority_validation_passed,
            "links_checked": len(supersession_result.links),
        },
        "history_preservation": {
            "events_input": len(assembly_result.events),
            "events_preserved": supersession_result.events_preserved,
            "no_history_deletion": supersession_result.events_preserved
            == len(assembly_result.events),
        },
        "ignored_non_event_signals": len(assembly_result.ignored_signal_refs),
        "diagnostics": assembly_result.diagnostics,
    }


def _timeline_entry_for_event(event: CorporateEvent) -> TimelineEntry:
    return TimelineEntry(
        entity_ref=event.entity_ref,
        event_ref=event.to_reference(),
        event_time=event.event_time,
        time_basis=event.time_basis,
        event_type=event.event_type,
        source_signal_refs=event.source_signal_refs,
        authority_class=event.authority_class,
        claim_type=event.claim_type,
    )


def _entity_timelines(entries: tuple[TimelineEntry, ...]) -> tuple[EntityTimeline, ...]:
    grouped: dict[str, list[TimelineEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.entity_ref].append(entry)
    return tuple(
        EntityTimeline(
            entity_ref=entity_ref,
            entries=tuple(sorted(entity_entries, key=timeline_entry_sort_key)),
        )
        for entity_ref, entity_entries in sorted(grouped.items())
    )


def _chronology_valid(timelines: Iterable[EntityTimeline]) -> bool:
    return all(
        timeline.entries == tuple(sorted(timeline.entries, key=timeline_entry_sort_key))
        for timeline in timelines
    )


def _signals_by_source_record(
    signals: Iterable[IntelligenceSignal],
) -> dict[tuple[str, str, str], list[IntelligenceSignal]]:
    grouped: dict[tuple[str, str, str], list[IntelligenceSignal]] = defaultdict(list)
    for signal in signals:
        grouped[_source_record_key(signal)].append(signal)
    return grouped


def _source_record_key(signal: IntelligenceSignal) -> tuple[str, str, str]:
    record_id = (
        signal.metadata.source_record_id
        or signal.content.identity_key
        or signal.signal_id
        or ""
    )
    return (
        signal.entity_ref,
        signal.classification.source_type.value,
        str(record_id),
    )


def _provenance_reference(signal: IntelligenceSignal) -> str:
    provenance = signal.provenance
    if provenance.provenance_type == ProvenanceType.ANNOUNCEMENT_REF:
        return (
            f"ANNOUNCEMENT_REF:{provenance.announcement_id}:"
            f"{provenance.snapshot_ref.snapshot_id}"
        )
    if provenance.provenance_type == ProvenanceType.PAYOUT_REF:
        return (
            f"PAYOUT_REF:{provenance.payout_id}:"
            f"{provenance.snapshot_ref.snapshot_id}"
        )
    if provenance.provenance_type == ProvenanceType.REGULATORY_REF:
        return (
            f"REGULATORY_REF:{provenance.notice_id}:"
            f"{provenance.snapshot_ref.snapshot_id}"
        )
    if provenance.provenance_type == ProvenanceType.PDF_PAGE:
        report_ref = provenance.report_reference or provenance.workbook_fingerprint
        return f"PDF_PAGE:{report_ref}:page:{provenance.page_number}"
    snapshot_ref = getattr(provenance, "snapshot_ref", None)
    snapshot_id = snapshot_ref.snapshot_id if snapshot_ref else "no_snapshot"
    return f"{provenance.provenance_type.value}:{snapshot_id}:{signal.signal_id}"


def _same_or_transition_event_type(
    prior: CorporateEvent,
    later: CorporateEvent,
) -> bool:
    if prior.event_type == later.event_type:
        return True
    return (prior.event_type, later.event_type) in _EVENT_TYPE_TRANSITIONS


def _candidate(
    prior: CorporateEvent,
    later: CorporateEvent,
    reason: SupersessionReason,
    details: str,
) -> SupersessionCandidate:
    return SupersessionCandidate(
        prior_event_id=prior.event_id or "",
        later_event_id=later.event_id or "",
        reason=reason,
        details=details,
    )


def _links_respect_authority(
    links: Iterable[SupersessionLink],
    authority_matrix: AuthorityMatrix,
) -> bool:
    for link in links:
        prior_rank = authority_matrix.effective_rank(
            claim_type=link.claim_type,
            authority_class=link.prior_authority_class,
        )
        later_rank = authority_matrix.effective_rank(
            claim_type=link.claim_type,
            authority_class=link.later_authority_class,
        )
        if prior_rank is None or later_rank is None or later_rank > prior_rank:
            return False
    return True


__all__ = [
    "SupersessionService",
    "TimelineAssemblyService",
    "build_timeline_audit",
]
