"""Models for OCR table extraction results."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from shared.models.metric_value import MetricValue


class PageExtractionDiagnostic(BaseModel):
    """Per-page extraction linkage diagnostics."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year for this page diagnostic.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number being diagnosed.",
        examples=[20],
    )
    detected_table_count: int = Field(
        ...,
        ge=0,
        description="Number of tables reported by the detection layer.",
        examples=[2],
    )
    classified_table_count: int = Field(
        ...,
        ge=0,
        description="Number of table types returned by classification.",
        examples=[2],
    )
    extracted_table_count: int = Field(
        ...,
        ge=0,
        description="Number of raw tables extracted from the page.",
        examples=[2],
    )
    matched_table_count: int = Field(
        ...,
        ge=0,
        description="Number of extracted tables matched to classified table types.",
        examples=[2],
    )
    unmatched_classifications: list[str] = Field(
        default_factory=list,
        description="Classified table types that did not match an extracted table.",
        examples=[["income_statement"]],
    )
    unmatched_extractions: list[int] = Field(
        default_factory=list,
        description="Extracted table indexes that did not match a classification.",
        examples=[[1]],
    )


class ExtractionSummary(BaseModel):
    """Aggregated extraction linkage diagnostics for one report."""

    model_config = ConfigDict(extra="forbid")

    total_detected_tables: int = Field(
        default=0,
        ge=0,
        description="Total tables reported by the detection layer.",
        examples=[7],
    )
    total_classified_tables: int = Field(
        default=0,
        ge=0,
        description="Total table types returned by classification.",
        examples=[7],
    )
    total_extracted_tables: int = Field(
        default=0,
        ge=0,
        description="Total raw tables extracted by Camelot/pdfplumber.",
        examples=[6],
    )
    total_matched_tables: int = Field(
        default=0,
        ge=0,
        description="Total extracted tables matched to classified table types.",
        examples=[5],
    )
    unmatched_classifications: list[str] = Field(
        default_factory=list,
        description="Flattened page/table-type labels that were not matched.",
        examples=[["page=20 table_type=income_statement"]],
    )
    unmatched_extractions: list[str] = Field(
        default_factory=list,
        description="Flattened page/table-index labels that were not matched.",
        examples=[["page=20 table_index=1"]],
    )
    page_diagnostics: list[PageExtractionDiagnostic] = Field(
        default_factory=list,
        description="Detailed per-page extraction linkage diagnostics.",
    )


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
                    "extraction_summary": {
                        "total_detected_tables": 1,
                        "total_classified_tables": 1,
                        "total_extracted_tables": 1,
                        "total_matched_tables": 1,
                        "unmatched_classifications": [],
                        "unmatched_extractions": [],
                        "page_diagnostics": [
                            {
                                "source_report_year": 2025,
                                "page_number": 20,
                                "detected_table_count": 1,
                                "classified_table_count": 1,
                                "extracted_table_count": 1,
                                "matched_table_count": 1,
                                "unmatched_classifications": [],
                                "unmatched_extractions": [],
                            }
                        ],
                    },
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
    extraction_summary: ExtractionSummary = Field(
        default_factory=ExtractionSummary,
        description="Detection/classification/extraction linkage summary.",
    )
