"""Models for historical financial series integrity gating."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.models.financial_year_consolidation import SourceClass, StatementScope

IntegrityStatus = Literal[
    "clean",
    "clean_with_warning",
    "baseline_not_validatable",
    "missing",
]
IntegritySeverity = Literal["info", "warning", "high", "critical"]
IntegrityFixability = Literal[
    "automatic",
    "policy",
    "review_only",
    "not_applicable",
]
ScaleCheckStatus = Literal[
    "pass",
    "warning",
    "warning_or_block",
    "block",
    "not_applicable",
]
ScaleResultStatus = Literal["pass", "warning", "fail", "not_applicable"]


class SeriesValueCandidateEvidence(BaseModel):
    """Comparable selected or competing value used by the integrity gate."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(
        ..., min_length=1, description="Canonical metric key.", examples=["revenue"]
    )
    value_year: int = Field(
        ..., ge=1900, description="Financial year represented.", examples=[2025]
    )
    value: float | int | str = Field(
        ..., description="Candidate metric value.", examples=[1000000]
    )
    source_report_year: int = Field(
        ..., ge=1900, description="Annual report year that supplied the value."
    )
    page_number: int = Field(
        ..., gt=0, description="One-based PDF page number for source provenance."
    )
    table_type: str = Field(
        ..., min_length=1, description="Source table type.", examples=["income_statement"]
    )
    source_class: SourceClass = Field(
        ..., description="Coarse source class derived from the table type."
    )
    statement_scope: StatementScope = Field(
        ..., description="Consolidated, standalone, or unknown statement scope."
    )
    normalization_confidence: float = Field(
        ..., ge=0, le=1, description="Metric normalization confidence."
    )
    source_confidence: float = Field(
        ..., ge=0, le=1, description="Candidate source confidence."
    )
    original_metric: str = Field(
        ..., min_length=1, description="Raw or reconstructed metric label."
    )
    requires_review: bool = Field(
        ..., description="Whether upstream normalization requires review."
    )
    is_currently_selected: bool = Field(
        ..., description="Whether upstream consolidation selected this candidate."
    )


class CandidateSpreadEvidence(BaseModel):
    """Same-year candidate spread result for one metric/year."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    value_year: int = Field(..., ge=1900, description="Financial year checked.")
    candidate_count: int = Field(
        ..., ge=0, description="Number of numeric candidates compared."
    )
    candidate_spread: float | None = Field(
        default=None,
        ge=0,
        description="Max absolute value divided by min non-zero absolute value.",
    )
    status: ScaleCheckStatus = Field(
        ..., description="Candidate spread status against MVP thresholds."
    )
    selected_candidate: SeriesValueCandidateEvidence | None = Field(
        default=None, description="Selected candidate for the year."
    )
    sample_competing_candidates: list[SeriesValueCandidateEvidence] = Field(
        default_factory=list,
        description="Competing candidates used as evidence.",
    )


class YoYScaleEvidence(BaseModel):
    """Year-over-year magnitude consistency check for selected values."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    from_year: int = Field(..., ge=1900, description="Prior financial year.")
    to_year: int = Field(..., ge=1900, description="Current financial year.")
    previous_value: float = Field(..., description="Numeric value for from_year.")
    current_value: float = Field(..., description="Numeric value for to_year.")
    ratio: float | None = Field(
        default=None,
        ge=0,
        description="Magnitude ratio between current and previous selected values.",
    )
    status: ScaleCheckStatus = Field(
        ..., description="YoY scale status against MVP thresholds."
    )


class IntegrityEvidence(BaseModel):
    """Auditable evidence supporting a gate decision."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(
        ..., min_length=1, description="Deterministic evidence identifier."
    )
    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    value_year: int | None = Field(
        default=None, ge=1900, description="Financial year when evidence is year-scoped."
    )
    evidence_type: str = Field(
        ..., min_length=1, description="Stable evidence category."
    )
    candidate_values: list[SeriesValueCandidateEvidence] = Field(
        default_factory=list, description="Selected and competing candidates."
    )
    calculations: dict[str, float | int | str | None] = Field(
        default_factory=dict, description="Calculated spread or ratio values."
    )
    policy_applied: str | None = Field(
        default=None, description="Policy that produced the evidence."
    )


class HistoricalSeriesIntegrityIssue(BaseModel):
    """Blocking or warning issue emitted by the integrity gate."""

    model_config = ConfigDict(extra="forbid")

    issue_type: str = Field(
        ..., min_length=1, description="Stable issue code."
    )
    severity: IntegritySeverity = Field(
        ..., description="Issue severity for downstream consumers."
    )
    metric: str = Field(..., min_length=1, description="Affected canonical metric.")
    value_years: list[int] = Field(
        default_factory=list, description="Affected financial years."
    )
    description: str = Field(
        ..., min_length=1, description="Human-readable issue explanation."
    )
    blocking: bool = Field(
        ..., description="Whether the issue prevents Forecast Validation usage."
    )
    fixability: IntegrityFixability = Field(
        ..., description="How the issue can be resolved."
    )
    evidence_ids: list[str] = Field(
        default_factory=list, description="References to supporting evidence records."
    )


class ScaleConsistencyResult(BaseModel):
    """Series-level scale decision for the integrity gate."""

    model_config = ConfigDict(extra="forbid")

    status: ScaleResultStatus = Field(
        ..., description="Overall scale consistency status."
    )
    max_candidate_spread: float | None = Field(
        default=None, ge=0, description="Largest same-year candidate spread observed."
    )
    max_yoy_magnitude_ratio: float | None = Field(
        default=None, ge=0, description="Largest selected-series YoY ratio observed."
    )
    blocking_reasons: list[str] = Field(
        default_factory=list, description="Scale reasons that block validation."
    )
    warning_reasons: list[str] = Field(
        default_factory=list, description="Scale reasons that allow validation with warning."
    )


class HistoricalSeriesIntegrityResult(BaseModel):
    """Integrity decision for one canonical historical metric series."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    status: IntegrityStatus = Field(
        ..., description="Forecast Validation baseline readiness status."
    )
    value_years: list[int] = Field(
        default_factory=list, description="Selected years available for the metric."
    )
    selected_series: list[SeriesValueCandidateEvidence] = Field(
        default_factory=list, description="Selected values by year."
    )
    blocking_issues: list[HistoricalSeriesIntegrityIssue] = Field(
        default_factory=list, description="Issues that block Forecast Validation."
    )
    warning_issues: list[HistoricalSeriesIntegrityIssue] = Field(
        default_factory=list, description="Non-blocking integrity warnings."
    )
    candidate_spread_by_year: list[CandidateSpreadEvidence] = Field(
        default_factory=list, description="Same-year candidate spread checks."
    )
    yoy_scale_issues: list[YoYScaleEvidence] = Field(
        default_factory=list, description="Selected-series YoY magnitude checks."
    )
    source_policy_violations: list[HistoricalSeriesIntegrityIssue] = Field(
        default_factory=list, description="Source policy issues for the series."
    )
    scale_result: ScaleConsistencyResult = Field(
        ..., description="Series-level scale result."
    )
    evidence: list[IntegrityEvidence] = Field(
        default_factory=list, description="Evidence records supporting the decision."
    )
    confidence: float = Field(
        ..., ge=0, le=1, description="Confidence in the gate status assignment."
    )
    validation_readiness: bool = Field(
        ..., description="Whether Forecast Validation may calculate over this series."
    )


class HistoricalSeriesIntegrityGateResult(BaseModel):
    """Root integrity-gate result for a set of canonical metrics."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "metrics_evaluated": ["revenue", "earnings_per_share"],
                    "overall_status": "baseline_not_validatable",
                    "status_counts": {
                        "clean": 0,
                        "clean_with_warning": 1,
                        "baseline_not_validatable": 1,
                        "missing": 0,
                    },
                }
            ]
        },
    )

    metrics_evaluated: list[str] = Field(
        ..., description="Canonical metric keys evaluated by the gate."
    )
    series_results: list[HistoricalSeriesIntegrityResult] = Field(
        ..., description="One integrity result per metric."
    )
    overall_status: IntegrityStatus = Field(
        ..., description="Worst status across all evaluated metrics."
    )
    status_counts: dict[str, int] = Field(
        ..., description="Metric counts grouped by integrity status."
    )
    metrics_by_status: dict[str, list[str]] = Field(
        ..., description="Metric names grouped by integrity status."
    )
    clean_metrics: list[str] = Field(
        default_factory=list, description="Metrics that passed without warnings."
    )
    warning_metrics: list[str] = Field(
        default_factory=list, description="Metrics that passed with warnings."
    )
    blocked_metrics: list[str] = Field(
        default_factory=list, description="Metrics blocked from Forecast Validation."
    )
    missing_metrics: list[str] = Field(
        default_factory=list, description="Metrics absent from the source data."
    )
    critical_issue_count: int = Field(
        ..., ge=0, description="Total blocking issue count."
    )
    warning_count: int = Field(
        ..., ge=0, description="Total non-blocking warning count."
    )
