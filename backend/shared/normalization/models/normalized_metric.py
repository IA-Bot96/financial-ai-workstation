"""Model returned when a single financial metric name is normalized."""

from pydantic import BaseModel, ConfigDict, Field


class NormalizedMetric(BaseModel):
    """Normalized representation of one financial metric name."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "original_metric": "Net Sales",
                    "normalized_metric": "revenue",
                    "confidence": 0.96,
                    "requires_review": False,
                }
            ]
        },
    )

    original_metric: str = Field(
        ...,
        min_length=1,
        description="Metric name as supplied by a consuming engine.",
        examples=["Net Sales"],
    )
    normalized_metric: str | None = Field(
        ...,
        description=(
            "Canonical metric key from the registry, or null when confidence "
            "is below the manual review threshold."
        ),
        examples=["revenue"],
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence score for the selected canonical metric mapping.",
        examples=[0.96],
    )
    requires_review: bool = Field(
        ...,
        description="Whether the normalized metric needs manual review.",
        examples=[False],
    )


class MetricMapping(BaseModel):
    """Report-originated metric normalization mapping with reporting year."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "original_metric": "Net Sales",
                    "normalized_metric": "revenue",
                    "confidence": 0.96,
                    "requires_review": False,
                }
            ]
        },
    )

    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year for this metric mapping.",
        examples=[2024],
    )
    original_metric: str = Field(
        ...,
        min_length=1,
        description="Raw metric label from the originating report.",
        examples=["Net Sales"],
    )
    normalized_metric: str | None = Field(
        ...,
        description="Canonical metric key or null when manual review is required.",
        examples=["revenue"],
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence score for the normalization result.",
        examples=[0.96],
    )
    requires_review: bool = Field(
        ...,
        description="Whether this mapping needs manual review.",
        examples=[False],
    )
