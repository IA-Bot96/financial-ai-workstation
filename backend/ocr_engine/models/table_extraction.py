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
                    "page_number": 20,
                    "table_type": "balance_sheet",
                    "table_index": 0,
                    "rows": [
                        ["Cash", "1000"],
                        ["Inventory", "500"],
                    ],
                }
            ]
        },
    )

    page_number: int = Field(
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
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source PDF page.",
        examples=[0],
    )
    rows: list[list[str]] = Field(
        ...,
        description="Raw extracted table rows, where each cell is preserved as text.",
        examples=[
            [
                ["Cash", "1000"],
                ["Inventory", "500"],
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
                            "page_number": 20,
                            "table_type": "balance_sheet",
                            "table_index": 0,
                            "rows": [
                                ["Cash", "1000"],
                                ["Inventory", "500"],
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
