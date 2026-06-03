"""Query-facing MSIL evidence adapter.

The adapter consumes already-produced MSIL records. It never resolves entities,
assigns authority, assembles timelines, computes corroboration, or computes
divergence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from multi_source_intelligence.models import (
    Divergence,
    DivergenceResult,
    IntelligenceSignal,
    TimelineAssemblyResult,
)

from query_engine.models.msil_evidence import (
    QueryMSILAuthority,
    QueryMSILCitation,
    QueryMSILDivergenceReference,
    QueryMSILEvidence,
    QueryMSILEvidenceCollection,
    QueryMSILEvidenceRetrievalResult,
    QueryMSILTimelineReference,
)


class QueryMSILEvidenceAdapter:
    """Convert MSIL evidence into Query-consumable retrieval records."""

    _OWNERSHIP_BOUNDARIES = {
        "query_resolves_entities": False,
        "query_assigns_authority": False,
        "query_recomputes_timeline": False,
        "query_recomputes_corroboration": False,
        "query_recomputes_divergence": False,
        "query_resolves_divergence": False,
        "query_changes_retrieval_ranking_policy": False,
        "query_generates_synthetic_msil_citations": False,
        "query_preserves_existing_workbook_citations": True,
    }

    def adapt(
        self,
        *,
        signals: Iterable[IntelligenceSignal],
        timeline_result: TimelineAssemblyResult | None = None,
        divergence_result: DivergenceResult | None = None,
    ) -> QueryMSILEvidenceCollection:
        """Return Query evidence records for supplied MSIL signals."""

        signal_list = tuple(signals)
        timeline_index = _timeline_refs_by_signal(timeline_result)
        divergence_index = _divergence_refs_by_signal(divergence_result)
        warnings: list[str] = []
        evidence: list[QueryMSILEvidence] = []

        for signal in signal_list:
            try:
                evidence.append(
                    self._adapt_signal(
                        signal,
                        timeline_refs=timeline_index.get(signal.signal_id or "", ()),
                        divergence_refs=(
                            *divergence_index.get(signal.signal_id or "", ()),
                            *_signal_only_divergence_refs(signal),
                        ),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - surfaced as adapter warning.
                warnings.append(
                    f"signal {signal.signal_id or '<missing>'} could not be adapted: {exc}"
                )

        return QueryMSILEvidenceCollection(
            evidence=tuple(evidence),
            warnings=tuple(warnings),
            ownership_boundaries=dict(self._OWNERSHIP_BOUNDARIES),
        )

    def retrieve_evidence(
        self,
        collection: QueryMSILEvidenceCollection,
        *,
        signal_refs: Iterable[str] | None = None,
        entity_ref: str | None = None,
        content_class: str | None = None,
        metric_ref: str | None = None,
        source_type: str | None = None,
        claim_type: str | None = None,
    ) -> QueryMSILEvidenceRetrievalResult:
        """Retrieve MSIL evidence records without ranking-policy changes."""

        requested_signal_refs = set(signal_refs or ())
        matches: list[QueryMSILEvidence] = []
        for item in collection.evidence:
            if requested_signal_refs and item.signal_ref not in requested_signal_refs:
                continue
            if entity_ref is not None and item.entity_ref != entity_ref:
                continue
            if content_class is not None and item.content_class != content_class:
                continue
            if metric_ref is not None and item.metric_ref != metric_ref:
                continue
            if source_type is not None and item.authority.source_type != source_type:
                continue
            if claim_type is not None and item.authority.claim_type != claim_type:
                continue
            matches.append(item)

        warnings = () if matches else ("no MSIL evidence matched the query filters",)
        return _retrieval_result(tuple(matches), warnings=warnings)

    def retrieve_provenance(
        self,
        collection: QueryMSILEvidenceCollection,
        signal_ref: str,
    ) -> QueryMSILEvidenceRetrievalResult:
        """Return provenance/citation records for one MSIL signal."""

        return self.retrieve_evidence(collection, signal_refs=(signal_ref,))

    def retrieve_authority(
        self,
        collection: QueryMSILEvidenceCollection,
        signal_ref: str,
    ) -> QueryMSILEvidenceRetrievalResult:
        """Return authority metadata for one MSIL signal."""

        return self.retrieve_evidence(collection, signal_refs=(signal_ref,))

    def retrieve_divergence_references(
        self,
        collection: QueryMSILEvidenceCollection,
        signal_ref: str,
    ) -> QueryMSILEvidenceRetrievalResult:
        """Return divergences already surfaced by MSIL for one signal."""

        base = self.retrieve_evidence(collection, signal_refs=(signal_ref,))
        warnings = (
            ()
            if base.divergence_refs
            else ("no MSIL divergence references surfaced for signal",)
        )
        return QueryMSILEvidenceRetrievalResult(
            found=bool(base.divergence_refs),
            evidence=base.evidence,
            citations=base.citations,
            authorities=base.authorities,
            divergence_refs=base.divergence_refs,
            warnings=warnings,
        )

    def audit(self, collection: QueryMSILEvidenceCollection) -> dict[str, Any]:
        """Build JSON-serializable integration audit payload."""

        evidence = collection.evidence
        citation_count = sum(len(item.citations) for item in evidence)
        authority_count = sum(1 for item in evidence if item.authority is not None)
        divergence_ref_count = sum(len(item.divergence_refs) for item in evidence)
        timeline_ref_count = sum(len(item.timeline_refs) for item in evidence)
        citation_coverage = (
            round(citation_count / len(evidence) * 100, 2) if evidence else 0.0
        )
        authority_coverage = (
            round(authority_count / len(evidence) * 100, 2) if evidence else 0.0
        )

        return {
            "audit_name": "query_msil_integration_audit",
            "integration_phase": "MSIL Phase 8A: Query Engine Integration",
            "evidence_retrieved": len(evidence),
            "provenance_attached": citation_count,
            "authority_attached": authority_count,
            "timeline_references_attached": timeline_ref_count,
            "divergence_references_surfaced": divergence_ref_count,
            "citation_coverage_percent": citation_coverage,
            "authority_coverage_percent": authority_coverage,
            "content_class_distribution": dict(
                Counter(item.content_class for item in evidence)
            ),
            "source_type_distribution": dict(
                Counter(item.authority.source_type for item in evidence)
            ),
            "authority_class_distribution": dict(
                Counter(item.authority.authority_class for item in evidence)
            ),
            "claim_type_distribution": dict(
                Counter(item.authority.claim_type for item in evidence)
            ),
            "provenance_type_distribution": dict(
                Counter(
                    citation.provenance_type
                    for item in evidence
                    for citation in item.citations
                )
            ),
            "divergence_surface_policy": {
                "query_resolves_divergence": False,
                "query_selects_winning_source": False,
                "surface_only": True,
            },
            "citation_policy": {
                "msil_provenance_is_source": True,
                "synthetic_msil_citations_created": False,
                "existing_query_workbook_citations_preserved": True,
            },
            "ownership_boundary_validation": collection.ownership_boundaries,
            "warnings": list(collection.warnings),
        }

    def _adapt_signal(
        self,
        signal: IntelligenceSignal,
        *,
        timeline_refs: tuple[QueryMSILTimelineReference, ...],
        divergence_refs: tuple[QueryMSILDivergenceReference, ...],
    ) -> QueryMSILEvidence:
        payload = signal.content.payload
        citation = _citation_from_provenance(signal.provenance)
        authority = QueryMSILAuthority(
            source_type=signal.classification.source_type.value,
            authority_class=signal.classification.authority_class.value,
            claim_type=signal.classification.claim_type.value,
            creation_eligible=signal.classification.creation_eligible,
            mapping_confidence=signal.classification.mapping_confidence,
            authority_confidence=signal.classification.authority_confidence,
            independence_metadata=dict(signal.classification.independence_metadata),
        )
        return QueryMSILEvidence(
            evidence_id=signal.signal_id or "",
            signal_ref=signal.signal_id or "",
            entity_ref=signal.entity_ref,
            entity_scope=signal.entity_scope.value,
            content_class=signal.content.content_class.value,
            claim_text=signal.content.claim_text,
            normalized_claim_text=signal.content.normalized_claim_text,
            metric_ref=signal.content.metric_ref,
            value=signal.content.value,
            unit=signal.content.unit,
            event_type=signal.content.event_type.value
            if signal.content.event_type
            else None,
            source_report_year=_optional_int(payload.get("source_report_year")),
            value_year=_optional_int(payload.get("value_year")),
            source_section=payload.get("source_section"),
            review_status=payload.get("review_status"),
            extraction_confidence=_optional_float(payload.get("confidence")),
            observation_time=signal.metadata.observation_time.isoformat(),
            subject_period=signal.metadata.subject_period,
            time_basis=signal.metadata.time_basis.value,
            horizon=signal.metadata.horizon.value,
            source_record_id=signal.metadata.source_record_id,
            authority=authority,
            citations=(citation,),
            timeline_refs=timeline_refs,
            divergence_refs=divergence_refs,
            provenance_payload=signal.provenance.model_dump(mode="json"),
            source_payload=dict(payload),
            version_pins=signal.version_pins.model_dump(mode="json"),
        )


def _retrieval_result(
    evidence: tuple[QueryMSILEvidence, ...],
    *,
    warnings: tuple[str, ...] = (),
) -> QueryMSILEvidenceRetrievalResult:
    citations = tuple(citation for item in evidence for citation in item.citations)
    authorities = tuple(item.authority for item in evidence)
    divergences = tuple(
        divergence for item in evidence for divergence in item.divergence_refs
    )
    return QueryMSILEvidenceRetrievalResult(
        found=bool(evidence),
        evidence=evidence,
        citations=citations,
        authorities=authorities,
        divergence_refs=divergences,
        warnings=warnings,
    )


def _citation_from_provenance(provenance: Any) -> QueryMSILCitation:
    payload = provenance.model_dump(mode="json")
    snapshot_ref = payload.get("snapshot_ref")
    snapshot_id = (
        snapshot_ref.get("snapshot_id")
        if isinstance(snapshot_ref, dict)
        else None
    )
    locator = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "verified",
            "retrieved_at",
            "source_lineage",
            "provenance_schema_version",
        }
        and value is not None
    }
    return QueryMSILCitation(
        provenance_type=_enum_or_value(payload["provenance_type"]),
        source_type=_enum_or_value(payload["source_type"]),
        verified=bool(payload.get("verified", True)),
        workbook_fingerprint=payload.get("workbook_fingerprint"),
        page_number=payload.get("page_number"),
        report_reference=payload.get("report_reference"),
        source_report_year=payload.get("source_report_year"),
        source_section=payload.get("source_section"),
        cell_reference=payload.get("cell_reference"),
        snapshot_id=snapshot_id,
        url=payload.get("url"),
        retrieved_at=payload.get("retrieved_at"),
        source_lineage=tuple(payload.get("source_lineage") or ()),
        locator=locator,
    )


def _timeline_refs_by_signal(
    timeline_result: TimelineAssemblyResult | None,
) -> dict[str, tuple[QueryMSILTimelineReference, ...]]:
    if timeline_result is None:
        return {}
    grouped: dict[str, list[QueryMSILTimelineReference]] = defaultdict(list)
    for entry in timeline_result.timeline_entries:
        reference = QueryMSILTimelineReference(
            event_id=entry.event_ref.event_id,
            entry_id=entry.entry_id,
            entity_ref=entry.entity_ref,
            event_type=entry.event_type.value,
            event_time=entry.event_time.isoformat(),
            time_basis=entry.time_basis.value,
            source_signal_refs=entry.source_signal_refs,
            authority_class=entry.authority_class.value,
            claim_type=entry.claim_type.value,
            current_flag=entry.current_flag,
            superseded_by=entry.superseded_by,
            supersedes=entry.supersedes,
        )
        for signal_ref in entry.source_signal_refs:
            grouped[signal_ref].append(reference)
    return {key: tuple(value) for key, value in grouped.items()}


def _divergence_refs_by_signal(
    divergence_result: DivergenceResult | None,
) -> dict[str, tuple[QueryMSILDivergenceReference, ...]]:
    if divergence_result is None:
        return {}
    grouped: dict[str, list[QueryMSILDivergenceReference]] = defaultdict(list)
    for divergence in divergence_result.divergences:
        reference = _divergence_reference(divergence)
        for signal_ref in reference.signal_refs:
            grouped[signal_ref].append(reference)
    return {key: tuple(value) for key, value in grouped.items()}


def _divergence_reference(divergence: Divergence) -> QueryMSILDivergenceReference:
    side_refs = (divergence.side_a, divergence.side_b)
    return QueryMSILDivergenceReference(
        divergence_id=divergence.divergence_id or "",
        divergence_type=divergence.divergence_type.value,
        status=divergence.status.value,
        entity_ref=divergence.entity_ref,
        subject=divergence.subject,
        signal_refs=tuple(side.signal_ref for side in side_refs),
        authority_classes=tuple(side.authority_class.value for side in side_refs),
        source_types=tuple(side.source_type.value for side in side_refs),
        chronology_comparison=divergence.chronology_comparison,
        authority_weighting=dict(divergence.authority_weighting),
    )


def _signal_only_divergence_refs(
    signal: IntelligenceSignal,
) -> tuple[QueryMSILDivergenceReference, ...]:
    return tuple(
        QueryMSILDivergenceReference(
            divergence_id=divergence_ref,
            entity_ref=signal.entity_ref,
            signal_refs=(signal.signal_id or "",),
            authority_classes=(signal.classification.authority_class.value,),
            source_types=(signal.classification.source_type.value,),
        )
        for divergence_ref in signal.divergence_refs
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _enum_or_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


__all__ = ["QueryMSILEvidenceAdapter"]
