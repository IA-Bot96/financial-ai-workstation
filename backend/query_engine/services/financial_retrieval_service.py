"""Deterministic financial retrieval over CompanyKnowledgeBase indexes."""

from __future__ import annotations

import time

from query_engine.models.knowledge_base import (
    CompanyKnowledgeBase,
    ConflictCandidateRecord,
    ConflictRecord,
    FinancialRecord,
    IndexBucket,
    WorkbookCellCitation,
    normalize_key,
)
from query_engine.models.retrieval import (
    FinancialRetrievalResult,
    RetrievalCandidate,
    RetrievalEvidence,
)
from shared.models.financial_year_consolidation import StatementScope


class FinancialRetrievalService:
    """Retrieve financial records deterministically from immutable indexes."""

    def __init__(self, knowledge_base: CompanyKnowledgeBase) -> None:
        """Initialize retrieval against one immutable knowledge-base snapshot."""

        self._knowledge_base = knowledge_base
        self._last_latency_seconds = 0.0

    @property
    def last_latency_seconds(self) -> float:
        """Return latency for the most recent retrieval call."""

        return self._last_latency_seconds

    def retrieve_by_metric(self, metric: str) -> FinancialRetrievalResult:
        """Return all records matching a canonical metric key."""

        started = time.perf_counter()
        normalized_metric = normalize_key(metric)
        records = self._records_for_metric(normalized_metric)
        result = self._result(
            query_metric=metric,
            normalized_metric=normalized_metric,
            records=records,
            warnings=(
                () if records else (f"missing metric: {normalized_metric}",)
            ),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def retrieve_by_metric_and_year(
        self,
        metric: str,
        year: int,
    ) -> FinancialRetrievalResult:
        """Return records for a canonical metric and analytical value year."""

        started = time.perf_counter()
        normalized_metric = normalize_key(metric)
        metric_records = self._records_for_metric(normalized_metric)
        records = tuple(
            record for record in metric_records if record.value_year == year
        )
        warnings: list[str] = []
        if not metric_records:
            warnings.append(f"missing metric: {normalized_metric}")
        elif not records:
            warnings.append(f"missing year {year} for metric: {normalized_metric}")
        result = self._result(
            query_metric=metric,
            normalized_metric=normalized_metric,
            query_year=year,
            records=records,
            warnings=tuple(warnings),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def retrieve_metric_history(self, metric: str) -> FinancialRetrievalResult:
        """Return metric records sorted by value_year then source_report_year."""

        started = time.perf_counter()
        normalized_metric = normalize_key(metric)
        records = tuple(
            sorted(
                self._records_for_metric(normalized_metric),
                key=lambda record: (
                    record.value_year,
                    record.source_report_year,
                    record.statement_scope,
                    record.table_type,
                ),
            )
        )
        result = self._result(
            query_metric=metric,
            normalized_metric=normalized_metric,
            records=records,
            warnings=(
                () if records else (f"missing metric: {normalized_metric}",)
            ),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def retrieve_by_statement_scope(
        self,
        metric: str,
        scope: StatementScope,
    ) -> FinancialRetrievalResult:
        """Return records matching both metric and statement scope."""

        started = time.perf_counter()
        normalized_metric = normalize_key(metric)
        metric_records = self._records_for_metric(normalized_metric)
        scoped_ids = set(
            _bucket_record_ids(
                self._knowledge_base.financial_dataset.indexes.by_statement_scope,
                scope,
            )
        )
        records = tuple(
            record for record in metric_records if record.record_id in scoped_ids
        )
        warnings: list[str] = []
        if not metric_records:
            warnings.append(f"missing metric: {normalized_metric}")
        elif not records:
            warnings.append(
                f"missing statement scope {scope} for metric: {normalized_metric}"
            )
        result = self._result(
            query_metric=metric,
            normalized_metric=normalized_metric,
            query_statement_scope=scope,
            records=records,
            warnings=tuple(warnings),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def retrieve_metric_candidates(self, metric: str) -> FinancialRetrievalResult:
        """Return selected records and competing conflict candidates for a metric."""

        started = time.perf_counter()
        normalized_metric = normalize_key(metric)
        records = self._records_for_metric(normalized_metric)
        conflicts = self._conflicts_for_metric(normalized_metric)
        candidates = [
            _candidate_from_financial_record(record) for record in records
        ]
        for conflict in conflicts:
            candidates.extend(
                _candidate_from_conflict_candidate(
                    candidate,
                    conflict_status=conflict.conflict_status,
                )
                for candidate in conflict.competing_candidates
            )
        evidence = tuple(candidate.evidence for candidate in candidates)
        warnings: list[str] = []
        if not records and not conflicts:
            warnings.append(f"missing metric: {normalized_metric}")
        if any(conflict.unresolved_conflict for conflict in conflicts):
            warnings.append(f"unresolved conflicts for metric: {normalized_metric}")
        result = FinancialRetrievalResult(
            query_metric=metric,
            normalized_metric=normalized_metric,
            found=bool(records or conflicts),
            is_ambiguous=len(candidates) > 1,
            has_unresolved_conflicts=any(
                conflict.unresolved_conflict for conflict in conflicts
            ),
            financial_records=records,
            conflicts=conflicts,
            candidates=tuple(candidates),
            evidence=evidence,
            warnings=tuple(_deduplicate(warnings)),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def _records_for_metric(self, normalized_metric: str) -> tuple[FinancialRecord, ...]:
        record_ids = _bucket_record_ids(
            self._knowledge_base.financial_dataset.indexes.by_metric,
            normalized_metric,
        )
        if not record_ids:
            record_ids = _bucket_record_ids(
                self._knowledge_base.financial_dataset.indexes.by_canonical_metric,
                normalized_metric,
            )
        return _financial_records_by_id(
            self._knowledge_base.financial_dataset.records,
            record_ids,
        )

    def _conflicts_for_records(
        self,
        records: tuple[FinancialRecord, ...],
    ) -> tuple[ConflictRecord, ...]:
        conflict_ids = {
            record.conflict_group_id
            for record in records
            if record.conflict_group_id is not None
        }
        return tuple(
            conflict
            for conflict in self._knowledge_base.conflict_dataset.records
            if conflict.conflict_group_id in conflict_ids
        )

    def _conflicts_for_metric(self, normalized_metric: str) -> tuple[ConflictRecord, ...]:
        return tuple(
            conflict
            for conflict in self._knowledge_base.conflict_dataset.records
            if conflict.metric == normalized_metric
            or conflict.canonical_metric == normalized_metric
        )

    def _result(
        self,
        *,
        query_metric: str,
        normalized_metric: str,
        records: tuple[FinancialRecord, ...],
        query_year: int | None = None,
        query_statement_scope: StatementScope | None = None,
        warnings: tuple[str, ...] = (),
    ) -> FinancialRetrievalResult:
        conflicts = self._conflicts_for_records(records)
        candidates = tuple(_candidate_from_financial_record(record) for record in records)
        evidence = tuple(candidate.evidence for candidate in candidates)
        result_warnings = list(warnings)
        ambiguous = len(records) > 1
        if ambiguous:
            result_warnings.append(
                "ambiguous metric result; multiple records matched the query"
            )
        if any(conflict.unresolved_conflict for conflict in conflicts):
            result_warnings.append("unresolved conflicts affect this result")
        return FinancialRetrievalResult(
            query_metric=query_metric,
            normalized_metric=normalized_metric,
            query_year=query_year,
            query_statement_scope=query_statement_scope,
            found=bool(records),
            is_ambiguous=ambiguous,
            has_unresolved_conflicts=any(
                conflict.unresolved_conflict for conflict in conflicts
            ),
            financial_records=records,
            conflicts=conflicts,
            candidates=candidates,
            evidence=evidence,
            warnings=tuple(_deduplicate(result_warnings)),
        )


def _candidate_from_financial_record(record: FinancialRecord) -> RetrievalCandidate:
    evidence = _evidence_from_financial_record(record)
    return RetrievalCandidate(
        candidate_id=record.record_id,
        candidate_type="selected_financial_record",
        confidence=record.normalization_confidence,
        statement_scope=record.statement_scope,
        conflict_status=record.conflict_status,
        workbook_citation=record.workbook_citation,
        evidence=evidence,
        provenance={
            "record_id": record.record_id,
            "metric": record.metric,
            "value_year": record.value_year,
            "source_report_year": record.source_report_year,
            "table_type": record.table_type,
            "page_number": record.page_number,
            "source_class": record.source_class,
            "requires_review": record.requires_review,
            "resolution_reason": record.resolution_reason,
        },
    )


def _candidate_from_conflict_candidate(
    candidate: ConflictCandidateRecord,
    *,
    conflict_status: str,
) -> RetrievalCandidate:
    citation = WorkbookCellCitation(citation_status="missing")
    evidence = RetrievalEvidence(
        evidence_id=candidate.candidate_id,
        evidence_type="conflict_candidate",
        summary=(
            f"{candidate.metric} {candidate.value_year}: {candidate.value} "
            f"from {candidate.table_type}"
        ),
        confidence=candidate.normalization_confidence,
        metric=candidate.metric,
        value_year=candidate.value_year,
        source_report_year=candidate.source_report_year,
        page_number=candidate.page_number,
        table_type=candidate.table_type,
        statement_scope=candidate.statement_scope,
        conflict_status=conflict_status,
        workbook_citation=citation,
        provenance={
            "candidate_id": candidate.candidate_id,
            "source_class": candidate.source_class,
            "original_metric": candidate.original_metric,
            "requires_review": candidate.requires_review,
        },
    )
    return RetrievalCandidate(
        candidate_id=candidate.candidate_id,
        candidate_type="competing_conflict_candidate",
        confidence=candidate.normalization_confidence,
        statement_scope=candidate.statement_scope,
        conflict_status=conflict_status,
        workbook_citation=citation,
        evidence=evidence,
        provenance=evidence.provenance,
    )


def _evidence_from_financial_record(record: FinancialRecord) -> RetrievalEvidence:
    return RetrievalEvidence(
        evidence_id=record.record_id,
        evidence_type="financial_record",
        summary=f"{record.metric} {record.value_year}: {record.value}",
        confidence=record.normalization_confidence,
        metric=record.metric,
        value_year=record.value_year,
        source_report_year=record.source_report_year,
        page_number=record.page_number,
        table_type=record.table_type,
        statement_scope=record.statement_scope,
        conflict_status=record.conflict_status,
        workbook_citation=record.workbook_citation,
        provenance={
            "record_id": record.record_id,
            "source_class": record.source_class,
            "source_confidence": record.source_confidence,
            "original_metric": record.original_metric,
            "requires_review": record.requires_review,
            "candidate_count": record.candidate_count,
            "resolution_reason": record.resolution_reason,
        },
    )


def _bucket_record_ids(buckets: tuple[IndexBucket, ...], key: object) -> tuple[str, ...]:
    normalized_key = str(key)
    for bucket in buckets:
        if bucket.key == normalized_key:
            return bucket.record_ids
    return ()


def _financial_records_by_id(
    records: tuple[FinancialRecord, ...],
    record_ids: tuple[str, ...],
) -> tuple[FinancialRecord, ...]:
    wanted = set(record_ids)
    return tuple(record for record in records if record.record_id in wanted)


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


__all__ = ["FinancialRetrievalService"]
