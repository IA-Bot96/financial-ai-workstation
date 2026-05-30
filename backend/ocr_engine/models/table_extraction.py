"""Models for OCR table extraction results."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedTable(BaseModel):
    """Raw table data extracted from a financial table on a PDF page.

    This model preserves OCR/PDF extraction output as rows and cells. It does
    not infer headers, normalize financial terminology, extract financial facts,
    or map the table to a reporting template.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "page": 20,
                    "table_type": "balance_sheet",
                    "rows": [
                        ["Revenue", "1200000", "1100000"],
                        ["Debt", "450000", "500000"],
                        ["Cash", "250000", "200000"],
                    ],
                }
            ]
        },
    )

    page: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the table was extracted.",
        examples=[20],
    )
    table_type: str = Field(
        ...,
        description="Financial table category assigned by the classification layer.",
        examples=["balance_sheet"],
    )
    rows: list[list[str]] = Field(
        ...,
        description="Raw extracted table rows, where each cell is preserved as text.",
        examples=[
            [
                ["Revenue", "1200000", "1100000"],
                ["Debt", "450000", "500000"],
            ]
        ],
    )


class TableExtractionResult(BaseModel):
    """Collection of tables extracted by the OCR Table Extraction Layer."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tables": [
                        {
                            "page": 20,
                            "table_type": "balance_sheet",
                            "rows": [
                                ["Revenue", "1200000", "1100000"],
                                ["Debt", "450000", "500000"],
                                ["Cash", "250000", "200000"],
                            ],
                        }
                    ]
                }
            ]
        },
    )

    tables: list[ExtractedTable] = Field(
        ...,
        description="Raw financial table data returned by the extraction layer.",
    )
