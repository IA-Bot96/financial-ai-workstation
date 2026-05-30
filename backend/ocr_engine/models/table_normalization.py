"""Models for OCR table metric normalization output."""

from pydantic import BaseModel, ConfigDict, Field


class NormalizedTable(BaseModel):
    """Extracted table rows after OCR metric labels have been normalized."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "page_number": 20,
                    "table_type": "income_statement",
                    "table_index": 0,
                    "rows": [
                        ["revenue", "1200000", "1100000"],
                        ["cost_of_sales", "800000", "760000"],
                    ],
                }
            ]
        },
    )

    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the table was extracted.",
        examples=[20],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category assigned by the classification layer.",
        examples=["income_statement"],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source PDF page.",
        examples=[0],
    )
    rows: list[list[str]] = Field(
        ...,
        description="Normalized table rows with canonical metric labels where available.",
    )


class NormalizationResult(BaseModel):
    """OCR metric normalization result consumed by downstream OCR layers."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tables": [
                        {
                            "page_number": 20,
                            "table_type": "income_statement",
                            "table_index": 0,
                            "rows": [["revenue", "1200000", "1100000"]],
                        }
                    ]
                }
            ]
        },
    )

    tables: list[NormalizedTable] = Field(
        ...,
        description="Normalized OCR tables available as financial context.",
    )
