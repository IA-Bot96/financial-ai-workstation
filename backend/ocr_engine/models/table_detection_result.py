"""Models for OCR table detection results."""

from pydantic import BaseModel, ConfigDict, Field


class DetectedPage(BaseModel):
    """Metadata for a PDF page where at least one table was detected."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "page_number": 20,
                    "tables_detected": 3,
                }
            ]
        },
    )

    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year for the source annual report.",
        examples=[2024],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where tables were detected.",
        examples=[20],
    )
    tables_detected: int = Field(
        ...,
        gt=0,
        description="Number of tables detected on the page.",
        examples=[3],
    )


class TableDetectionResult(BaseModel):
    """Result returned by the OCR Table Detection Layer.

    The detection layer identifies PDF pages containing tables and records the
    number of detected tables per page. It does not extract tabular content;
    that responsibility belongs to the table extraction layer.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "detected_pages": [
                        {
                            "year": 2024,
                            "page_number": 20,
                            "tables_detected": 3,
                        },
                        {
                            "year": 2024,
                            "page_number": 25,
                            "tables_detected": 1,
                        },
                        {
                            "year": 2024,
                            "page_number": 42,
                            "tables_detected": 2,
                        },
                    ],
                    "total_pages_processed": 132,
                }
            ]
        },
    )

    detected_pages: list[DetectedPage] = Field(
        ...,
        description="Pages where tables were detected, including per-page table counts.",
        examples=[
            [
                {
                    "year": 2024,
                    "page_number": 20,
                    "tables_detected": 3,
                },
                {
                    "year": 2024,
                    "page_number": 25,
                    "tables_detected": 1,
                },
            ]
        ],
    )
    total_pages_processed: int = Field(
        ...,
        ge=0,
        description="Total number of PDF pages processed by the table detection layer.",
        examples=[132],
    )
