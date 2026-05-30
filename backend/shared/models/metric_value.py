"""Shared canonical financial metric value model."""

from pydantic import BaseModel, ConfigDict, Field


class MetricValue(BaseModel):
    """Financial metric value with analytical year and source-report provenance.

    ``value_year`` is the year the number represents. ``source_report_year`` is
    the annual report where the number was found. These are intentionally
    separate because later reports can restate or reclassify comparative years.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "metric": "revenue",
                    "value_year": 2024,
                    "value": 1500,
                    "source_report_year": 2025,
                    "page_number": 120,
                    "table_type": "income_statement",
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
    value_year: int = Field(
        ...,
        ge=1900,
        description="Financial year represented by the metric value.",
        examples=[2024],
    )
    value: float | int | str = Field(
        ...,
        description="Extracted metric value for value_year.",
        examples=[1500],
    )
    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which this value was sourced.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the value originated.",
        examples=[120],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the value originated.",
        examples=["income_statement"],
    )
