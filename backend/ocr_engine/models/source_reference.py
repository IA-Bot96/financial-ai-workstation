"""Models for source traceability."""

from pydantic import BaseModel, ConfigDict, Field


class SourceReference(BaseModel):
    """Reference to a report location with year preserved for traceability."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "section": "Management Discussion & Analysis",
                    "page_number": 84,
                }
            ]
        },
    )

    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year where the source information originated.",
        examples=[2024],
    )
    section: str = Field(
        ...,
        min_length=1,
        description="Annual-report section where the source information originated.",
        examples=["Management Discussion & Analysis"],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the source information appears.",
        examples=[84],
    )
