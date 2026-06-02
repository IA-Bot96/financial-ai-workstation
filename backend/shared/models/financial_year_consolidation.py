"""Models for financial-year consolidation diagnostics."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.models.metric_value import MetricValue

SourceClass = Literal[
    "primary_statement",
    "note_disclosure",
    "analysis_or_ratio",
    "supporting_schedule",
    "unclassified",
]
StatementScope = Literal["consolidated", "standalone", "unknown"]


class ConsolidationCandidate(BaseModel):
    """Provenance for one candidate value considered during consolidation."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    value_year: int = Field(..., ge=1900, description="Financial year represented.")
    value: float | int | str = Field(..., description="Extracted metric value.")
    source_report_year: int = Field(
        ..., ge=1900, description="Annual report year that supplied the value."
    )
    page_number: int = Field(..., gt=0, description="Source PDF page number.")
    table_type: str = Field(..., min_length=1, description="Source table type.")
    source_class: SourceClass = Field(
        ..., description="Coarse source class derived from table_type."
    )
    statement_scope: StatementScope = Field(
        ..., description="Explicit statement scope when detectable."
    )
    normalization_confidence: float = Field(
        ..., ge=0, le=1, description="Metric normalization confidence."
    )
    source_confidence: float = Field(
        ..., ge=0, le=1, description="Backward-compatible confidence alias."
    )
    original_metric: str = Field(
        ..., min_length=1, description="Raw metric label before normalization."
    )
    requires_review: bool = Field(
        ..., description="Whether the normalization mapping requires review."
    )
    label_cleanliness_score: int = Field(
        ..., ge=0, description="Heuristic score for label reconstruction quality."
    )
    source_context_score: int = Field(
        ..., ge=0, description="Heuristic score for available source context."
    )
    table_type_priority: int = Field(
        ..., ge=0, description="Priority assigned to the source table type."
    )


class ConsolidationGroup(BaseModel):
    """Duplicate or conflict group considered during consolidation."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    value_year: int = Field(..., ge=1900, description="Financial year represented.")
    candidate_count: int = Field(..., gt=1, description="Candidates in this group.")
    selected: ConsolidationCandidate = Field(
        ..., description="Candidate selected as source of truth."
    )
    competing_candidates: list[ConsolidationCandidate] = Field(
        default_factory=list,
        description="Candidates not selected for the metric/year.",
    )
    is_duplicate_group: bool = Field(
        ..., description="Whether multiple candidates existed for this key."
    )
    is_conflict_group: bool = Field(
        ..., description="Whether candidates had distinct values."
    )
    conflict_resolved: bool = Field(
        ..., description="Whether a value conflict was resolved deterministically."
    )
    unresolved_conflict: bool = Field(
        ..., description="Whether the group still needs review or policy."
    )
    conflict_status: str = Field(
        ..., description="Human-readable conflict status for downstream engines."
    )
    resolution_reason: str = Field(
        ..., description="Deterministic precedence rule that selected the value."
    )


class FinancialYearConsolidationResult(BaseModel):
    """Final consolidation output and auditable candidate diagnostics."""

    model_config = ConfigDict(extra="forbid")

    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description="Consolidated source-of-truth metric values.",
    )
    duplicate_groups_resolved: int = Field(
        default=0, ge=0, description="Duplicate groups evaluated."
    )
    conflict_groups_resolved: int = Field(
        default=0, ge=0, description="Conflict groups resolved deterministically."
    )
    unresolved_conflict_groups: int = Field(
        default=0, ge=0, description="Conflict groups still unresolved."
    )
    quality_overrode_recency: int = Field(
        default=0,
        ge=0,
        description="Cases where quality beat newer source report year.",
    )
    metric_values_removed: int = Field(
        default=0, ge=0, description="Candidates removed by consolidation."
    )
    review_mappings_reduced: int = Field(
        default=0, ge=0, description="Review-gated mappings removed by consolidation."
    )
    groups: list[ConsolidationGroup] = Field(
        default_factory=list,
        description="Per metric/year duplicate and conflict diagnostics.",
    )
