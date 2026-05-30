"""Shared canonical numeric metric value model."""

from pydantic import BaseModel, ConfigDict, Field


class MetricValue(BaseModel):
    """Canonical numeric value for one financial metric in one reporting year."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "metric": "revenue",
                    "year": 2024,
                    "value": 1500000.0,
                }
            ]
        },
    )

    metric: str = Field(
        ...,
        min_length=1,
        description="Canonical financial metric key.",
        examples=["revenue"],
    )
    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year for this metric value.",
        examples=[2024],
    )
    value: float = Field(
        ...,
        description="Numeric financial metric value for the reporting year.",
        examples=[1500000.0],
    )
