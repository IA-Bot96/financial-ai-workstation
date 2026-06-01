"""Models for OCR financial table classification results."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ocr_engine.models.table_detection_result import BBox, FailedPage

TableType = Annotated[str, Field(min_length=1)]


class ClassifiedTable(BaseModel):
    """Financial table type assigned to one detected table identity."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "page_number": 20,
                    "table_type": "balance_sheet",
                    "detected_table_id": "2024:20:0",
                    "page_table_index": 0,
                    "bbox": [72.0, 144.0, 540.0, 320.0],
                    "detection_confidence": 0.97,
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
        description="One-based PDF page number where the table was classified.",
        examples=[20],
    )
    table_type: TableType = Field(
        ...,
        description="Detected financial table category.",
        examples=["balance_sheet"],
    )
    detected_table_id: str | None = Field(
        default=None,
        description="Detected table identity propagated from detection.",
        examples=["2024:20:0"],
    )
    page_table_index: int | None = Field(
        default=None,
        ge=0,
        description="Zero-based table index on the page from detection order.",
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
        description="Detector confidence score for the classified table.",
        examples=[0.97],
    )


class PageTableType(BaseModel):
    """Financial table types identified on a detected PDF page.

    This model supports multiple table types per page and keeps table type
    values as flexible strings so new annual-report table categories can appear
    without requiring enum changes.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "page_number": 20,
                    "table_types": [
                        "balance_sheet",
                        "debt_schedule",
                    ],
                    "classified_tables": [
                        {
                            "year": 2024,
                            "page_number": 20,
                            "table_type": "balance_sheet",
                            "detected_table_id": "2024:20:0",
                            "page_table_index": 0,
                            "bbox": [72.0, 144.0, 540.0, 320.0],
                            "detection_confidence": 0.97,
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
        description=(
            "One-based PDF page number where financial tables were classified."
        ),
        examples=[20],
    )
    table_types: list[TableType] = Field(
        ...,
        description=(
            "Detected financial table categories on the page, kept as flexible "
            "strings for forward compatibility."
        ),
        examples=[["balance_sheet", "debt_schedule"]],
    )
    classified_tables: list[ClassifiedTable] = Field(
        default_factory=list,
        description=(
            "Table-level classifications with propagated detection identity. "
            "When absent, consumers may fall back to page-level table_types."
        ),
    )

    @model_validator(mode="after")
    def _populate_classified_tables(self) -> "PageTableType":
        """Backfill table-level classifications for legacy payloads."""

        if self.classified_tables:
            return self
        self.classified_tables = [
            ClassifiedTable(
                year=self.year,
                page_number=self.page_number,
                table_type=table_type,
            )
            for index, table_type in enumerate(self.table_types)
        ]
        return self


class FinancialTableClassificationResult(BaseModel):
    """Collection of page-level financial table classifications."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "page_table_types": [
                        {
                            "year": 2024,
                            "page_number": 20,
                            "table_types": [
                                "balance_sheet",
                                "debt_schedule",
                            ],
                        },
                        {
                            "year": 2024,
                            "page_number": 25,
                            "table_types": [
                                "income_statement",
                            ],
                        },
                    ],
                    "failed_pages": [],
                }
            ]
        },
    )

    page_table_types: list[PageTableType] = Field(
        ...,
        description="Financial table type classifications grouped by detected page.",
    )
    failed_pages: list[FailedPage] = Field(
        default_factory=list,
        description="Pages skipped due to page-level classification failures.",
    )
