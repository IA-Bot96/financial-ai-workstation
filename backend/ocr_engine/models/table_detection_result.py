"""Models for OCR table detection results."""

from pydantic import BaseModel, ConfigDict, Field


BBox = list[float]


class DetectedTable(BaseModel):
    """Metadata for one table detected on a PDF page."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "page_number": 20,
                    "detected_table_id": "2024:20:0",
                    "page_table_index": 0,
                    "bbox": [72.0, 144.0, 540.0, 320.0],
                    "detection_confidence": 0.97,
                    "label": "table",
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
        description="One-based PDF page number where the table was detected.",
        examples=[20],
    )
    detected_table_id: str = Field(
        ...,
        min_length=1,
        description="Stable table identity within the source report.",
        examples=["2024:20:0"],
    )
    page_table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the PDF page from detection order.",
        examples=[0],
    )
    bbox: BBox | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="Detected table bounding box as [x0, y0, x1, y1].",
        examples=[[72.0, 144.0, 540.0, 320.0]],
    )
    detection_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Detector confidence score for this table.",
        examples=[0.97],
    )
    label: str | None = Field(
        default=None,
        description="Raw detector label, when available.",
        examples=["table"],
    )


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
                    "detected_tables": [
                        {
                            "year": 2024,
                            "page_number": 20,
                            "detected_table_id": "2024:20:0",
                            "page_table_index": 0,
                            "bbox": [72.0, 144.0, 540.0, 320.0],
                            "detection_confidence": 0.97,
                            "label": "table",
                        }
                    ],
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
    detected_tables: list[DetectedTable] = Field(
        default_factory=list,
        description="Individual table detections on the page with identity metadata.",
    )


class FailedPage(BaseModel):
    """Metadata for a PDF page that could not be processed."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "page_number": 21,
                    "error_message": "corrupted page",
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
        description="One-based PDF page number that could not be processed.",
        examples=[21],
    )
    error_message: str = Field(
        ...,
        min_length=1,
        description="Human-readable reason the page was skipped.",
        examples=["corrupted page"],
    )


class TableDetectionResult(BaseModel):
    """Result returned by the OCR Table Detection Layer.

    The detection layer identifies PDF pages containing tables and records the
    number of detected tables per page. Page-level failures are retained so
    corrupted pages are visible to downstream monitoring instead of being
    silently dropped. It does not extract tabular content; that responsibility
    belongs to the table extraction layer.
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
                    "failed_pages": [
                        {
                            "year": 2024,
                            "page_number": 21,
                            "error_message": "corrupted page",
                        }
                    ],
                    "total_pages_processed": 132,
                }
            ]
        },
    )

    detected_pages: list[DetectedPage] = Field(
        ...,
        description=(
            "Pages where tables were detected, including per-page table counts."
        ),
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
    failed_pages: list[FailedPage] = Field(
        default_factory=list,
        description="Pages skipped due to page-level detection or rendering failures.",
        examples=[
            [
                {
                    "year": 2024,
                    "page_number": 21,
                    "error_message": "corrupted page",
                }
            ]
        ],
    )
    total_pages_processed: int = Field(
        ...,
        ge=0,
        description=(
            "Total number of PDF pages processed by the table detection layer."
        ),
        examples=[132],
    )
