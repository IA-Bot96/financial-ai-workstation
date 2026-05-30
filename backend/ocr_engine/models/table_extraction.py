"""Models for OCR table extraction results."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from shared.models.metric_value import MetricValue


class ExtractedTable(BaseModel):
    """Table data extracted from a financial table on a PDF page.

    Raw rows are retained for OCR traceability. ``metric_values`` is the
    structured extraction contract: each value records the value year and the
    source report year separately.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "source_report_year": 2025,
                    "page_number": 20,
                    "table_type": "balance_sheet",
                    "table_index": 0,
                    "rows": [
                        ["Cash", "1000"],
                        ["Inventory", "500"],
                    ],
                    "metric_values": [
                        {
                            "metric": "Cash",
                            "value_year": 2024,
                            "value": 1000,
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "balance_sheet",
                        }
                    ],
                }
            ]
        },
    )

    source_report_year: int = Field(
        ...,
        ge=1900,
        validation_alias=AliasChoices("source_report_year", "year"),
        description="Annual report year from which this table was extracted.",
        examples=[2025],
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
        default_factory=list,
        description="Raw extracted table rows retained for OCR traceability.",
        examples=[
            [
                ["Cash", "1000"],
                ["Inventory", "500"],
            ]
        ],
    )
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description=(
            "Metric/value pairs extracted from the table with value year and "
            "source report year separated."
        ),
    )

    @property
    def year(self) -> int:
        """Backward-compatible alias for source_report_year."""

        return self.source_report_year


class TableExtractionResult(BaseModel):
    """Collection of tables extracted by the OCR Table Extraction Layer."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tables": [
                        {
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "balance_sheet",
                            "table_index": 0,
                            "rows": [
                                ["Cash", "1000"],
                                ["Inventory", "500"],
                            ],
                            "metric_values": [
                                {
                                    "metric": "Cash",
                                    "value_year": 2024,
                                    "value": 1000,
                                    "source_report_year": 2025,
                                    "page_number": 20,
                                    "table_type": "balance_sheet",
                                }
                            ],
                        }
                    ],
                    "metric_values": [
                        {
                            "metric": "Cash",
                            "value_year": 2024,
                            "value": 1000,
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "balance_sheet",
                        }
                    ],
                }
            ]
        },
    )

    tables: list[ExtractedTable] = Field(
        ...,
        description="Raw financial table data returned by the extraction layer.",
    )
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description="All extracted metric values across tables in this result.",
    )
