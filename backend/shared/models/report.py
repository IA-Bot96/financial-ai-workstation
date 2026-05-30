"""Shared report model for multi-year company processing."""

from pydantic import BaseModel, ConfigDict, Field


class Report(BaseModel):
    """Annual report metadata with year preserved as first-class context."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "rpt_2024_001",
                    "company_name": "Maple Leaf Cement Factory Limited",
                    "year": 2024,
                    "file_name": "MLCF_2024_Annual_Report.pdf",
                    "file_path": "/reports/MLCF_2024_Annual_Report.pdf",
                }
            ]
        },
    )

    id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier assigned to the uploaded annual report.",
        examples=["rpt_2024_001"],
    )
    company_name: str = Field(
        ...,
        min_length=1,
        description="Legal or commonly used company name for the report issuer.",
        examples=["Maple Leaf Cement Factory Limited"],
    )
    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year for this annual report.",
        examples=[2024],
    )
    file_name: str = Field(
        ...,
        min_length=1,
        description="Original report file name.",
        examples=["MLCF_2024_Annual_Report.pdf"],
    )
    file_path: str = Field(
        ...,
        min_length=1,
        description="Filesystem or object-storage path to the annual report.",
        examples=["/reports/MLCF_2024_Annual_Report.pdf"],
    )
