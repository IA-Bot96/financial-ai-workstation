"""Deterministic calculation models for the Financial Query Engine."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from query_engine.models.knowledge_base import ConflictRecord, WorkbookCellCitation
from query_engine.models.metric_resolution import MetricResolutionResult
from query_engine.models.retrieval import RetrievalEvidence
from shared.models.financial_year_consolidation import StatementScope

CalculationType = Literal[
    "year_over_year_growth",
    "cagr",
    "percentage_change",
    "absolute_change",
    "trend_direction",
    "multi_year_series",
]
TrendDirection = Literal[
    "increasing",
    "decreasing",
    "flat",
    "mixed",
    "insufficient_data",
]


class CalculationRequest(BaseModel):
    """Request for one deterministic financial calculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    calculation_type: CalculationType = Field(..., description="Calculation to run.")
    metric: str = Field(..., min_length=1, description="User-facing metric label.")
    year: int | None = Field(
        default=None,
        ge=1900,
        description="Target year for year-over-year calculations.",
    )
    start_year: int | None = Field(default=None, ge=1900)
    end_year: int | None = Field(default=None, ge=1900)
    statement_scope: StatementScope | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_year_contract(self) -> "CalculationRequest":
        """Validate calculation-specific year requirements."""

        if self.calculation_type == "year_over_year_growth":
            if self.year is None and self.end_year is None:
                raise ValueError(
                    "year_over_year_growth requires year or end_year."
                )
        elif self.calculation_type in {
            "cagr",
            "percentage_change",
            "absolute_change",
        }:
            if self.start_year is None or self.end_year is None:
                raise ValueError(
                    f"{self.calculation_type} requires start_year and end_year."
                )
            if self.start_year >= self.end_year:
                raise ValueError("start_year must be before end_year.")
        elif self.calculation_type == "trend_direction":
            if (
                self.start_year is not None
                and self.end_year is not None
                and self.start_year >= self.end_year
            ):
                raise ValueError("start_year must be before end_year.")
        return self


class CalculationEvidence(BaseModel):
    """Financial value evidence used in a deterministic calculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    value: float | int | str
    numeric_value: float | None = Field(default=None)
    source_report_year: int = Field(..., ge=1900)
    page_number: int = Field(..., gt=0)
    table_type: str = Field(..., min_length=1)
    statement_scope: StatementScope
    confidence: float = Field(..., ge=0, le=1)
    conflict_status: str = Field(..., min_length=1)
    unresolved_conflict: bool = Field(...)
    workbook_citation: WorkbookCellCitation
    retrieval_evidence: tuple[RetrievalEvidence, ...] = Field(default_factory=tuple)


class CalculationSeries(BaseModel):
    """Ordered source-value series used by a calculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_metric: str = Field(..., min_length=1)
    resolved_metric: str | None = Field(default=None)
    points: tuple[CalculationEvidence, ...] = Field(default_factory=tuple)


class CalculationResult(BaseModel):
    """Result of one deterministic financial calculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: CalculationRequest
    calculation_type: CalculationType
    requested_metric: str = Field(..., min_length=1)
    resolved_metric: str | None = Field(default=None)
    success: bool = Field(..., description="Whether calculation value was produced.")
    value: float | str | None = Field(default=None)
    result_unit: str | None = Field(default=None)
    trend_direction: TrendDirection | None = Field(default=None)
    series: CalculationSeries
    evidence: tuple[CalculationEvidence, ...] = Field(default_factory=tuple)
    retrieval_evidence: tuple[RetrievalEvidence, ...] = Field(default_factory=tuple)
    conflicts: tuple[ConflictRecord, ...] = Field(default_factory=tuple)
    has_unresolved_conflicts: bool = Field(default=False)
    is_ambiguous: bool = Field(default=False)
    statement_scope_differences: tuple[StatementScope, ...] = Field(
        default_factory=tuple
    )
    confidence: float = Field(default=0.0, ge=0, le=1)
    metric_resolution: MetricResolutionResult | None = Field(default=None)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)


__all__ = [
    "CalculationEvidence",
    "CalculationRequest",
    "CalculationResult",
    "CalculationSeries",
    "CalculationType",
    "TrendDirection",
]
