"""Models for OCR financial table classification results."""

from pydantic import BaseModel, ConfigDict, Field


class FinancialTableClassification(BaseModel):
    """Classification for a financial table detected on a single PDF page.

    This model represents only the table category decision. It intentionally
    does not include extracted rows, columns, headers, values, normalized terms,
    or template mapping details.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "page": 20,
                    "table_type": "balance_sheet",
                    "confidence": 0.97,
                }
            ]
        },
    )

    page: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the financial table was classified.",
        examples=[20],
    )
    table_type: str = Field(
        ...,
        description=(
            "Detected financial table category as a string, kept flexible for "
            "new annual-report table types."
        ),
        examples=["balance_sheet", "property_plant_equipment_note"],
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Classifier confidence score from 0 to 1, inclusive.",
        examples=[0.97],
    )


class FinancialTableClassificationResult(BaseModel):
    """Collection of financial table classifications for detected table pages."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "classifications": [
                        {
                            "page": 20,
                            "table_type": "balance_sheet",
                            "confidence": 0.97,
                        },
                        {
                            "page": 25,
                            "table_type": "income_statement",
                            "confidence": 0.95,
                        },
                        {
                            "page": 72,
                            "table_type": "property_plant_equipment_note",
                            "confidence": 0.89,
                        },
                    ]
                }
            ]
        },
    )

    classifications: list[FinancialTableClassification] = Field(
        ...,
        description="Financial table classifications produced for detected table pages.",
    )
