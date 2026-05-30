"""Shared financial fact model for multi-year analysis."""

from pydantic import BaseModel, ConfigDict, Field


class FinancialFact(BaseModel):
    """A single structured financial fact tied to a reporting year."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "metric": "revenue",
                    "value": 1500000,
                    "page_number": 20,
                    "table_type": "income_statement",
                }
            ]
        },
    )

    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year from which the fact originated.",
        examples=[2024],
    )
    metric: str = Field(
        ...,
        min_length=1,
        description="Canonical or extracted metric name for the fact.",
        examples=["revenue"],
    )
    value: float | int | str = Field(
        ...,
        description="Extracted financial fact value preserved as number or text.",
        examples=[1500000, "N/A"],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the fact was extracted.",
        examples=[20],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category from which the fact was extracted.",
        examples=["income_statement"],
    )
