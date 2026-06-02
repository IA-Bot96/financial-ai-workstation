"""Deterministic insight retrieval over CompanyKnowledgeBase indexes."""

from __future__ import annotations

import time

from query_engine.models.knowledge_base import (
    CompanyKnowledgeBase,
    IndexBucket,
    InsightRecord,
    normalize_key,
)
from query_engine.models.retrieval import (
    InsightRetrievalResult,
    RetrievalCandidate,
    RetrievalEvidence,
)


class InsightRetrievalService:
    """Retrieve business insights deterministically from immutable indexes."""

    def __init__(self, knowledge_base: CompanyKnowledgeBase) -> None:
        """Initialize retrieval against one immutable knowledge-base snapshot."""

        self._knowledge_base = knowledge_base
        self._last_latency_seconds = 0.0

    @property
    def last_latency_seconds(self) -> float:
        """Return latency for the most recent retrieval call."""

        return self._last_latency_seconds

    def retrieve_by_report_year(self, year: int) -> InsightRetrievalResult:
        """Return insights sourced from a report year."""

        started = time.perf_counter()
        record_ids = _bucket_record_ids(
            self._knowledge_base.insight_dataset.indexes.by_report_year,
            str(year),
        )
        records = _insight_records_by_id(
            self._knowledge_base.insight_dataset.records,
            record_ids,
        )
        result = _result(
            query=str(year),
            normalized_query=str(year),
            query_year=year,
            records=records,
            warnings=(() if records else (f"missing report year: {year}",)),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def retrieve_by_category(self, category: str) -> InsightRetrievalResult:
        """Return insights matching a normalized insight category."""

        started = time.perf_counter()
        normalized_category = normalize_key(category)
        records = self._records_from_index(
            self._knowledge_base.insight_dataset.indexes.by_category,
            normalized_category,
        )
        result = _result(
            query=category,
            normalized_query=normalized_category,
            records=records,
            warnings=(
                () if records else (f"missing insight category: {normalized_category}",)
            ),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def retrieve_by_topic(self, topic: str) -> InsightRetrievalResult:
        """Return insights matching a normalized insight topic."""

        started = time.perf_counter()
        normalized_topic = normalize_key(topic)
        records = self._records_from_index(
            self._knowledge_base.insight_dataset.indexes.by_topic,
            normalized_topic,
        )
        result = _result(
            query=topic,
            normalized_query=normalized_topic,
            records=records,
            warnings=(() if records else (f"missing insight topic: {normalized_topic}",)),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def retrieve_related_to_metric(self, metric: str) -> InsightRetrievalResult:
        """Return insights deterministically related to a canonical metric."""

        started = time.perf_counter()
        normalized_metric = normalize_key(metric)
        indexed_records = [
            *self._records_from_index(
                self._knowledge_base.insight_dataset.indexes.by_category,
                normalized_metric,
            ),
            *self._records_from_index(
                self._knowledge_base.insight_dataset.indexes.by_topic,
                normalized_metric,
            ),
        ]
        metric_tokens = {
            token
            for token in normalized_metric.split("_")
            if len(token) >= 3
        }
        text_matches = [
            record
            for record in self._knowledge_base.insight_dataset.records
            if _record_mentions_tokens(record, metric_tokens)
        ]
        records = _deduplicate_records((*indexed_records, *text_matches))
        result = _result(
            query=metric,
            normalized_query=normalized_metric,
            records=records,
            warnings=(
                () if records else (f"no insights related to metric: {normalized_metric}",)
            ),
        )
        self._last_latency_seconds = time.perf_counter() - started
        return result

    def _records_from_index(
        self,
        buckets: tuple[IndexBucket, ...],
        key: str,
    ) -> tuple[InsightRecord, ...]:
        return _insight_records_by_id(
            self._knowledge_base.insight_dataset.records,
            _bucket_record_ids(buckets, key),
        )


def _result(
    *,
    query: str,
    normalized_query: str,
    records: tuple[InsightRecord, ...],
    query_year: int | None = None,
    warnings: tuple[str, ...] = (),
) -> InsightRetrievalResult:
    sorted_records = tuple(
        sorted(
            records,
            key=lambda record: (
                -record.confidence,
                record.source_report_year,
                record.page_number,
                record.insight_id,
            ),
        )
    )
    candidates = tuple(_candidate_from_insight_record(record) for record in sorted_records)
    return InsightRetrievalResult(
        query=query,
        normalized_query=normalized_query,
        query_year=query_year,
        found=bool(sorted_records),
        insights=sorted_records,
        candidates=candidates,
        evidence=tuple(candidate.evidence for candidate in candidates),
        warnings=warnings,
    )


def _candidate_from_insight_record(record: InsightRecord) -> RetrievalCandidate:
    evidence = RetrievalEvidence(
        evidence_id=record.insight_id,
        evidence_type="insight",
        summary=record.takeaway,
        confidence=record.confidence,
        value_year=record.value_year,
        source_report_year=record.source_report_year,
        page_number=record.page_number,
        source_section=record.source_section,
        provenance={
            "insight_id": record.insight_id,
            "category": record.category,
            "topic": record.topic,
            "area": record.area,
            "confidence_bucket": record.confidence_bucket,
            "workbook_sheet_name": record.workbook_sheet_name,
            "workbook_row": record.workbook_row,
        },
    )
    return RetrievalCandidate(
        candidate_id=record.insight_id,
        candidate_type="insight",
        confidence=record.confidence,
        evidence=evidence,
        provenance=evidence.provenance,
    )


def _record_mentions_tokens(record: InsightRecord, tokens: set[str]) -> bool:
    if not tokens:
        return False
    searchable = normalize_key(
        " ".join(
            [
                record.category,
                record.topic,
                record.area,
                record.takeaway,
                record.source_section,
            ]
        )
    )
    searchable_tokens = set(searchable.split("_"))
    return bool(tokens & searchable_tokens)


def _bucket_record_ids(buckets: tuple[IndexBucket, ...], key: object) -> tuple[str, ...]:
    normalized_key = str(key)
    for bucket in buckets:
        if bucket.key == normalized_key:
            return bucket.record_ids
    return ()


def _insight_records_by_id(
    records: tuple[InsightRecord, ...],
    record_ids: tuple[str, ...],
) -> tuple[InsightRecord, ...]:
    wanted = set(record_ids)
    return tuple(record for record in records if record.insight_id in wanted)


def _deduplicate_records(records: tuple[InsightRecord, ...]) -> tuple[InsightRecord, ...]:
    seen: set[str] = set()
    deduplicated: list[InsightRecord] = []
    for record in records:
        if record.insight_id in seen:
            continue
        seen.add(record.insight_id)
        deduplicated.append(record)
    return tuple(deduplicated)


__all__ = ["InsightRetrievalService"]
