"""Deterministic retrieval result models for the Financial Query Engine."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.knowledge_base import (
    ConflictRecord,
    FinancialRecord,
    InsightRecord,
    WorkbookCellCitation,
)
from shared.models.financial_year_consolidation import StatementScope

EvidenceType = Literal["financial_record", "conflict_candidate", "insight"]
CandidateType = Literal[
    "selected_financial_record",
    "competing_conflict_candidate",
    "insight",
]


class RetrievalEvidence(BaseModel):
    """Auditable evidence item returned by deterministic retrieval services."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(..., min_length=1, description="Stable evidence id.")
    evidence_type: EvidenceType = Field(..., description="Evidence source type.")
    summary: str = Field(..., min_length=1, description="Human-readable summary.")
    confidence: float = Field(..., ge=0, le=1, description="Evidence confidence.")
    metric: str | None = Field(default=None, description="Canonical metric key.")
    value_year: int | None = Field(default=None, ge=1900)
    source_report_year: int | None = Field(default=None, ge=1900)
    page_number: int | None = Field(default=None, gt=0)
    table_type: str | None = Field(default=None)
    statement_scope: StatementScope | None = Field(default=None)
    conflict_status: str | None = Field(default=None)
    workbook_citation: WorkbookCellCitation | None = Field(default=None)
    source_section: str | None = Field(default=None)
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured provenance copied from the knowledge base.",
    )


class RetrievalCandidate(BaseModel):
    """Rankable deterministic retrieval candidate with provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(..., min_length=1, description="Candidate id.")
    candidate_type: CandidateType = Field(..., description="Candidate source type.")
    confidence: float = Field(..., ge=0, le=1, description="Candidate confidence.")
    statement_scope: StatementScope | None = Field(default=None)
    conflict_status: str | None = Field(default=None)
    workbook_citation: WorkbookCellCitation | None = Field(default=None)
    evidence: RetrievalEvidence = Field(..., description="Evidence backing candidate.")
    provenance: dict[str, Any] = Field(default_factory=dict)


class FinancialRetrievalResult(BaseModel):
    """Result returned by deterministic financial metric retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_metric: str = Field(..., min_length=1)
    normalized_metric: str = Field(..., min_length=1)
    query_year: int | None = Field(default=None, ge=1900)
    query_statement_scope: StatementScope | None = Field(default=None)
    found: bool = Field(..., description="Whether matching financial records exist.")
    is_ambiguous: bool = Field(..., description="Whether multiple records match.")
    has_unresolved_conflicts: bool = Field(
        ..., description="Whether unresolved conflicts affect the result."
    )
    financial_records: tuple[FinancialRecord, ...] = Field(default_factory=tuple)
    conflicts: tuple[ConflictRecord, ...] = Field(default_factory=tuple)
    candidates: tuple[RetrievalCandidate, ...] = Field(default_factory=tuple)
    evidence: tuple[RetrievalEvidence, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)


class InsightRetrievalResult(BaseModel):
    """Result returned by deterministic insight retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(..., min_length=1)
    normalized_query: str = Field(..., min_length=1)
    query_year: int | None = Field(default=None, ge=1900)
    found: bool = Field(..., description="Whether matching insights exist.")
    insights: tuple[InsightRecord, ...] = Field(default_factory=tuple)
    candidates: tuple[RetrievalCandidate, ...] = Field(default_factory=tuple)
    evidence: tuple[RetrievalEvidence, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)


__all__ = [
    "CandidateType",
    "EvidenceType",
    "FinancialRetrievalResult",
    "InsightRetrievalResult",
    "RetrievalCandidate",
    "RetrievalEvidence",
]
