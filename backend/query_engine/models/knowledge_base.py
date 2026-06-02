"""Immutable in-memory knowledge-base models for the Financial Query Engine."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.models.financial_year_consolidation import (
    SourceClass,
    StatementScope,
)

ConfidenceBucket = Literal["high", "medium", "low", "review"]


class IndexBucket(BaseModel):
    """Immutable index bucket mapping one key to record ids."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(..., min_length=1, description="Normalized index key.")
    record_ids: tuple[str, ...] = Field(
        default_factory=tuple, description="Record ids matching this key."
    )


class KnowledgeBaseValidationResult(BaseModel):
    """Validation result for a built CompanyKnowledgeBase."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool = Field(..., description="Whether the knowledge base is valid.")
    errors: tuple[str, ...] = Field(default_factory=tuple, description="Blocking errors.")
    warnings: tuple[str, ...] = Field(
        default_factory=tuple, description="Non-blocking validation warnings."
    )


class KnowledgeBaseMetadata(BaseModel):
    """Metadata for one immutable Query Engine knowledge-base snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(..., min_length=1, description="Input schema version.")
    workbook_id: str = Field(..., min_length=1, description="Workbook id.")
    workbook_fingerprint: str = Field(..., min_length=1, description="Workbook hash.")
    company_name: str = Field(..., min_length=1, description="Company name.")
    report_years: tuple[int, ...] = Field(
        ..., min_length=1, description="Report years included in the bundle."
    )
    workbook_output_file_path: str = Field(
        ..., min_length=1, description="Generated workbook path."
    )
    workbook_mode: str = Field(..., min_length=1, description="Workbook mode.")
    metrics_written: int = Field(..., ge=0, description="Workbook metrics written.")
    sheets_created: tuple[str, ...] = Field(default_factory=tuple)
    sheets_reused: tuple[str, ...] = Field(default_factory=tuple)
    sheets_replaced: tuple[str, ...] = Field(default_factory=tuple)


class WorkbookCellCitation(BaseModel):
    """Workbook cell citation attached to a financial record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sheet_name: str | None = Field(default=None, description="Workbook sheet name.")
    row: int | None = Field(default=None, gt=0, description="One-based row.")
    column: int | None = Field(default=None, gt=0, description="One-based column.")
    cell_reference: str | None = Field(
        default=None, description="Excel cell coordinate."
    )
    write_status: str | None = Field(default=None, description="Workbook write status.")
    citation_status: str = Field(
        ..., min_length=1, description="cell_mapped or missing."
    )


class FinancialRecord(BaseModel):
    """Immutable selected financial value consumed by Query Engine services."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(..., min_length=1, description="Stable record id.")
    metric: str = Field(..., min_length=1, description="Metric key.")
    canonical_metric: str = Field(..., min_length=1, description="Canonical metric key.")
    value_year: int = Field(..., ge=1900, description="Analytical value year.")
    source_report_year: int = Field(..., ge=1900, description="Source report year.")
    value: float | int | str = Field(..., description="Selected financial value.")
    page_number: int = Field(..., gt=0, description="Source PDF page.")
    table_type: str = Field(..., min_length=1, description="Source table type.")
    source_class: SourceClass = Field(..., description="Source class.")
    statement_scope: StatementScope = Field(..., description="Statement scope.")
    normalization_confidence: float = Field(
        ..., ge=0, le=1, description="Metric normalization confidence."
    )
    source_confidence: float = Field(
        ..., ge=0, le=1, description="Source confidence."
    )
    original_metric: str = Field(..., min_length=1, description="Original metric label.")
    requires_review: bool = Field(..., description="Review-gated value flag.")
    workbook_citation: WorkbookCellCitation = Field(
        ..., description="Workbook cell citation."
    )
    conflict_group_id: str | None = Field(
        default=None, description="Linked conflict group id."
    )
    candidate_count: int = Field(default=1, ge=1, description="Candidates considered.")
    is_duplicate_group: bool = Field(default=False)
    is_conflict_group: bool = Field(default=False)
    conflict_resolved: bool = Field(default=True)
    unresolved_conflict: bool = Field(default=False)
    conflict_status: str = Field(default="no_conflict", min_length=1)
    resolution_reason: str = Field(default="single_candidate", min_length=1)

    @model_validator(mode="after")
    def _validate_years(self) -> "FinancialRecord":
        """Ensure analytical year does not exceed the report year."""

        if self.value_year > self.source_report_year:
            raise ValueError("value_year must be less than or equal to source_report_year")
        if self.metric != self.canonical_metric:
            raise ValueError("metric and canonical_metric must match for Phase 1")
        return self


class FinancialDatasetIndexes(BaseModel):
    """Immutable financial dataset indexes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    by_metric: tuple[IndexBucket, ...] = Field(default_factory=tuple)
    by_canonical_metric: tuple[IndexBucket, ...] = Field(default_factory=tuple)
    by_value_year: tuple[IndexBucket, ...] = Field(default_factory=tuple)
    by_source_report_year: tuple[IndexBucket, ...] = Field(default_factory=tuple)
    by_statement_scope: tuple[IndexBucket, ...] = Field(default_factory=tuple)

    def count_summary(self) -> dict[str, int]:
        """Return bucket counts by index type."""

        return {
            "by_metric": len(self.by_metric),
            "by_canonical_metric": len(self.by_canonical_metric),
            "by_value_year": len(self.by_value_year),
            "by_source_report_year": len(self.by_source_report_year),
            "by_statement_scope": len(self.by_statement_scope),
        }


class FinancialDataset(BaseModel):
    """Immutable financial dataset and its query-ready indexes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[FinancialRecord, ...] = Field(default_factory=tuple)
    indexes: FinancialDatasetIndexes = Field(default_factory=FinancialDatasetIndexes)

    def records_for_metric(self, metric: str) -> tuple[FinancialRecord, ...]:
        """Return financial records for a canonical metric."""

        record_ids = _bucket_record_ids(self.indexes.by_metric, metric)
        return _records_by_id(self.records, record_ids)

    def records_for_value_year(self, value_year: int) -> tuple[FinancialRecord, ...]:
        """Return financial records for an analytical year."""

        record_ids = _bucket_record_ids(self.indexes.by_value_year, str(value_year))
        return _records_by_id(self.records, record_ids)


class InsightRecord(BaseModel):
    """Immutable business insight consumed by the Query Engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    insight_id: str = Field(..., min_length=1, description="Stable insight id.")
    value_year: int = Field(..., ge=1900, description="Year discussed.")
    source_report_year: int = Field(..., ge=1900, description="Source report year.")
    category: str = Field(..., min_length=1, description="Normalized area category.")
    topic: str = Field(..., min_length=1, description="Normalized topic key.")
    area: str = Field(..., min_length=1, description="Original insight area.")
    takeaway: str = Field(..., min_length=1, description="Insight takeaway.")
    source_section: str = Field(..., min_length=1, description="Source section.")
    page_number: int = Field(..., gt=0, description="Source page.")
    confidence: float = Field(..., ge=0, le=1, description="Insight confidence.")
    confidence_bucket: ConfidenceBucket = Field(..., description="Confidence bucket.")
    workbook_sheet_name: str | None = Field(default=None, description="Workbook sheet.")
    workbook_row: int | None = Field(default=None, gt=0, description="Workbook row.")

    @model_validator(mode="after")
    def _validate_years(self) -> "InsightRecord":
        """Ensure insight value year is not after its source report."""

        if self.value_year > self.source_report_year:
            raise ValueError("value_year must be less than or equal to source_report_year")
        return self


class InsightDatasetIndexes(BaseModel):
    """Immutable insight dataset indexes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    by_report_year: tuple[IndexBucket, ...] = Field(default_factory=tuple)
    by_category: tuple[IndexBucket, ...] = Field(default_factory=tuple)
    by_topic: tuple[IndexBucket, ...] = Field(default_factory=tuple)
    by_confidence: tuple[IndexBucket, ...] = Field(default_factory=tuple)

    def count_summary(self) -> dict[str, int]:
        """Return bucket counts by index type."""

        return {
            "by_report_year": len(self.by_report_year),
            "by_category": len(self.by_category),
            "by_topic": len(self.by_topic),
            "by_confidence": len(self.by_confidence),
        }


class InsightDataset(BaseModel):
    """Immutable insight dataset and its query-ready indexes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[InsightRecord, ...] = Field(default_factory=tuple)
    indexes: InsightDatasetIndexes = Field(default_factory=InsightDatasetIndexes)

    def records_for_report_year(self, report_year: int) -> tuple[InsightRecord, ...]:
        """Return insights sourced from a report year."""

        record_ids = _bucket_record_ids(self.indexes.by_report_year, str(report_year))
        return _records_by_id(self.records, record_ids)


class ConflictCandidateRecord(BaseModel):
    """Immutable candidate value represented in a conflict group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    canonical_metric: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    source_report_year: int = Field(..., ge=1900)
    value: float | int | str
    page_number: int = Field(..., gt=0)
    table_type: str = Field(..., min_length=1)
    source_class: SourceClass
    statement_scope: StatementScope
    normalization_confidence: float = Field(..., ge=0, le=1)
    source_confidence: float = Field(..., ge=0, le=1)
    original_metric: str = Field(..., min_length=1)
    requires_review: bool


class ConflictRecord(BaseModel):
    """Immutable duplicate/conflict group derived from consolidation output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conflict_group_id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    canonical_metric: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    selected_candidate_id: str = Field(..., min_length=1)
    candidate_count: int = Field(..., gt=1)
    candidates: tuple[ConflictCandidateRecord, ...] = Field(default_factory=tuple)
    competing_candidates: tuple[ConflictCandidateRecord, ...] = Field(
        default_factory=tuple
    )
    is_duplicate_group: bool
    is_conflict_group: bool
    conflict_resolved: bool
    unresolved_conflict: bool
    conflict_status: str = Field(..., min_length=1)
    resolution_reason: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_selected_candidate(self) -> "ConflictRecord":
        """Ensure selected candidate is represented in the candidate list."""

        candidate_ids = {candidate.candidate_id for candidate in self.candidates}
        if self.selected_candidate_id not in candidate_ids:
            raise ValueError("selected_candidate_id must exist in candidates")
        if self.candidate_count != len(self.candidates):
            raise ValueError("candidate_count must equal len(candidates)")
        return self


class ConflictDataset(BaseModel):
    """Immutable conflict dataset derived from consolidation results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[ConflictRecord, ...] = Field(default_factory=tuple)
    unresolved_conflicts: tuple[ConflictRecord, ...] = Field(default_factory=tuple)

    def competing_candidates_for(
        self, metric: str, value_year: int
    ) -> tuple[ConflictCandidateRecord, ...]:
        """Return competing candidates for a metric/year conflict group."""

        for record in self.records:
            if record.metric == metric and record.value_year == value_year:
                return record.competing_candidates
        return ()


class CompanyKnowledgeBase(BaseModel):
    """Immutable root object consumed by future Query Engine services."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: KnowledgeBaseMetadata
    financial_dataset: FinancialDataset
    insight_dataset: InsightDataset
    conflict_dataset: ConflictDataset
    validation_result: KnowledgeBaseValidationResult


def stable_id(prefix: str, payload: dict[str, object]) -> str:
    """Return a deterministic id from a small JSON-serializable payload."""

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def normalize_key(value: object) -> str:
    """Normalize labels to a stable lowercase snake-case key."""

    normalized = str(value).lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_") or "unknown"


def confidence_bucket(confidence: float, *, requires_review: bool = False) -> ConfidenceBucket:
    """Bucket a confidence score for indexing and validation."""

    if requires_review:
        return "review"
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.65:
        return "medium"
    return "low"


def make_index(pairs: list[tuple[str, str]]) -> tuple[IndexBucket, ...]:
    """Build immutable index buckets from key/record-id pairs."""

    grouped: dict[str, list[str]] = {}
    for key, record_id in pairs:
        grouped.setdefault(str(key), []).append(record_id)
    return tuple(
        IndexBucket(key=key, record_ids=tuple(sorted(record_ids)))
        for key, record_ids in sorted(grouped.items())
    )


def _bucket_record_ids(buckets: tuple[IndexBucket, ...], key: str) -> tuple[str, ...]:
    normalized = str(key)
    for bucket in buckets:
        if bucket.key == normalized:
            return bucket.record_ids
    return ()


def _records_by_id(records: tuple[object, ...], record_ids: tuple[str, ...]) -> tuple:
    wanted = set(record_ids)
    return tuple(record for record in records if getattr(record, "record_id", getattr(record, "insight_id", None)) in wanted)


__all__ = [
    "CompanyKnowledgeBase",
    "ConflictCandidateRecord",
    "ConflictDataset",
    "ConflictRecord",
    "FinancialDataset",
    "FinancialDatasetIndexes",
    "FinancialRecord",
    "IndexBucket",
    "InsightDataset",
    "InsightDatasetIndexes",
    "InsightRecord",
    "KnowledgeBaseMetadata",
    "KnowledgeBaseValidationResult",
    "WorkbookCellCitation",
    "confidence_bucket",
    "make_index",
    "normalize_key",
    "stable_id",
]
