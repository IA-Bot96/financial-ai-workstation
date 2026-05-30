"""Models for OCR insights extraction results."""

from pydantic import BaseModel, ConfigDict, Field


class Insight(BaseModel):
    """Business insight extracted from narrative annual-report text.

    This model preserves the extracted insight and its source location. It does
    not perform forecasting, choose variables to track, generate analyst
    recommendations, or validate the business claim.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "area": "Debt",
                    "takeaway": "Debt increased due to Southeast Asia expansion financing.",
                    "source_section": "Management Discussion & Analysis",
                    "page": 84,
                }
            ]
        },
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
        examples=["Debt increased due to Southeast Asia expansion financing."],
    )
    source_section: str = Field(
        ...,
        min_length=1,
        description="Annual-report section where the insight was found.",
        examples=["Management Discussion & Analysis"],
    )
    page: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the source narrative appears.",
        examples=[84],
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
                            "area": "Debt",
                            "takeaway": (
                                "Debt increased due to Southeast Asia expansion "
                                "financing."
                            ),
                            "source_section": "Management Discussion & Analysis",
                            "page": 84,
                        },
                        {
                            "area": "Geographic Expansion",
                            "takeaway": (
                                "The company plans to expand into Africa and the "
                                "Middle East."
                            ),
                            "source_section": "Risks & Opportunities",
                            "page": 92,
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
