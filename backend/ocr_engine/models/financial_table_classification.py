"""Models for OCR financial table classification results."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

TableType = Annotated[str, Field(min_length=1)]


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
                    "page_number": 20,
                    "table_types": [
                        "balance_sheet",
                        "debt_schedule",
                    ],
                }
            ]
        },
    )

    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where financial tables were classified.",
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


class FinancialTableClassificationResult(BaseModel):
    """Collection of page-level financial table classifications."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "page_table_types": [
                        {
                            "page_number": 20,
                            "table_types": [
                                "balance_sheet",
                                "debt_schedule",
                            ],
                        },
                        {
                            "page_number": 25,
                            "table_types": [
                                "income_statement",
                            ],
                        },
                    ]
                }
            ]
        },
    )

    page_table_types: list[PageTableType] = Field(
        ...,
        description="Financial table type classifications grouped by detected page.",
    )
