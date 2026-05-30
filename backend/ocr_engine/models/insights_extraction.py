"""Models for OCR insights extraction results."""

from pydantic import BaseModel, ConfigDict, Field


class Insight(BaseModel):
    """Business insight extracted from narrative annual-report text.

    ``value_year`` is the year the insight discusses. ``source_report_year`` is
    the annual report where the narrative was found.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "value_year": 2024,
                    "source_report_year": 2025,
                    "area": "Debt",
                    "takeaway": "Borrowings increased to finance expansion.",
                    "source_section": "Management Discussion & Analysis",
                    "page_number": 84,
                    "confidence": 0.93,
                }
            ]
        },
    )

    value_year: int = Field(
        ...,
        ge=1900,
        description="Financial year discussed by the insight.",
        examples=[2024],
    )
    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the insight originated.",
        examples=[2025],
    )
    area: str = Field(
        ...,
        min_length=1,
        description="Business topic or theme associated with the extracted insight.",
        examples=["Debt", "Geographic Expansion"],
    )
    takeaway: str = Field(
        ...,
        min_length=1,
        description="Concise extracted business insight from the report text.",
        examples=["Borrowings increased to finance expansion."],
    )
    source_section: str = Field(
        ...,
        min_length=1,
        description="Annual-report section where the insight was found.",
        examples=["Management Discussion & Analysis"],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the source narrative appears.",
        examples=[84],
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence score for the extracted insight.",
        examples=[0.93],
    )


class InsightsExtractionResult(BaseModel):
    """Collection of business insights extracted from annual-report text."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "insights": [
                        {
                            "value_year": 2024,
                            "source_report_year": 2025,
                            "area": "Debt",
                            "takeaway": "Borrowings increased to finance expansion.",
                            "source_section": "Management Discussion & Analysis",
                            "page_number": 84,
                            "confidence": 0.93,
                        },
                        {
                            "value_year": 2025,
                            "source_report_year": 2025,
                            "area": "Exports",
                            "takeaway": (
                                "Export sales increased due to Middle East "
                                "expansion."
                            ),
                            "source_section": "Business Review",
                            "page_number": 92,
                            "confidence": 0.9,
                        },
                    ]
                }
            ]
        },
    )

    insights: list[Insight] = Field(
        ...,
        description="Business insights extracted from narrative annual-report sections.",
    )
