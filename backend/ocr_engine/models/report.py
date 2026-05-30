"""Models for uploaded annual reports."""

from pydantic import BaseModel, ConfigDict, Field


class Report(BaseModel):
    """Metadata for an uploaded annual report processed by the OCR engine."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "rpt_001",
                    "file_name": "MLCF_2024_Annual_Report.pdf",
                    "company": "Maple Leaf Cement Factory Limited",
                    "year": 2024,
                }
            ]
        },
    )

    id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier assigned to the uploaded report.",
        examples=["rpt_001"],
    )
    file_name: str = Field(
        ...,
        min_length=1,
        description="Original annual-report file name.",
        examples=["MLCF_2024_Annual_Report.pdf"],
    )
    company: str | None = Field(
        default=None,
        description="Company name associated with the report, when known.",
        examples=["Maple Leaf Cement Factory Limited"],
    )
    year: int | None = Field(
        default=None,
        gt=1900,
        description="Financial reporting year, when known.",
        examples=[2024],
    )
