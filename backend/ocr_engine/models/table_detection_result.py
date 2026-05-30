"""Models for OCR table detection results."""

from pydantic import BaseModel, ConfigDict, Field


class TableDetectionResult(BaseModel):
    """Result returned by the OCR Table Detection Layer.

    The detection layer identifies which PDF pages contain tables. It does not
    extract tabular content; that responsibility belongs to the table extraction
    layer.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "table_pages": [24, 25, 42],
                    "total_detected_tables": 7,
                }
            ]
        },
    )

    table_pages: list[int] = Field(
        ...,
        description="One-based PDF page numbers where at least one table was detected.",
        examples=[[24, 25, 42]],
    )
    total_detected_tables: int = Field(
        ...,
        ge=0,
        description="Total number of individual tables detected across all detected table pages.",
        examples=[7],
    )
