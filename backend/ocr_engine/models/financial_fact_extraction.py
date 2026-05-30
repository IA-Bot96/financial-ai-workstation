"""Models for OCR financial fact extraction results."""

from pydantic import BaseModel, ConfigDict, Field


class FinancialFact(BaseModel):
    """Structured financial fact extracted from a classified table.

    This model carries a single extracted fact and source table context. It does
    not normalize terminology, perform template mapping, validate the value, or
    generate recommendations.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "Revenue",
                    "value": 1200000,
                    "page": 20,
                    "table_type": "income_statement",
                }
            ]
        },
    )

    name: str = Field(
        ...,
        min_length=1,
        description="Financial fact name as extracted from the source table.",
        examples=["Revenue"],
    )
    value: float | int | str = Field(
        ...,
        description="Extracted financial fact value preserved as number or text.",
        examples=[1200000, "N/A"],
    )
    page: int = Field(
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


class FinancialFactExtractionResult(BaseModel):
    """Collection of financial facts extracted from annual-report tables."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "facts": [
                        {
                            "name": "Revenue",
                            "value": 1200000,
                            "page": 20,
                            "table_type": "income_statement",
                        }
                    ]
                }
            ]
        },
    )

    facts: list[FinancialFact] = Field(
        ...,
        description="Structured financial facts extracted from report tables.",
    )
