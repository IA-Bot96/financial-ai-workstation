"""Models for source traceability."""

from pydantic import BaseModel, ConfigDict, Field


class SourceReference(BaseModel):
    """Reference to the annual-report location for extracted information."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "section": "Management Discussion & Analysis",
                    "page": 84,
                }
            ]
        },
    )

    section: str = Field(
        ...,
        min_length=1,
        description="Annual-report section where the source information originated.",
        examples=["Management Discussion & Analysis"],
    )
    page: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the source information appears.",
        examples=[84],
    )
