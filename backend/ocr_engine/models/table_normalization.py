"""Models for OCR table metric normalization output."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from ocr_engine.models.table_detection_result import BBox
from shared.models.metric_value import MetricValue


class NormalizedTable(BaseModel):
    """Extracted table rows and metric values after metric labels are normalized."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "source_report_year": 2025,
                    "page_number": 20,
                    "table_type": "income_statement",
                    "table_index": 0,
                    "source_table_index": 0,
                    "split_table_index": None,
                    "split_reason": None,
                    "rows": [
                        ["revenue", "1200000", "1100000"],
                        ["cost_of_sales", "800000", "760000"],
                    ],
                    "metric_values": [
                        {
                            "metric": "revenue",
                            "value_year": 2024,
                            "value": 1500,
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "income_statement",
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
        min_length=1,
        description="Financial table category assigned by the classification layer.",
        examples=["income_statement"],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source PDF page.",
        examples=[0],
    )
    source_table_index: int = Field(
        default=0,
        ge=0,
        description=(
            "Zero-based physical table index before any scoped logical splitting."
        ),
        examples=[0],
    )
    split_table_index: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Zero-based logical split index within the source table, when scoped "
            "table splitting created this table."
        ),
        examples=[1],
    )
    split_reason: str | None = Field(
        default=None,
        description="Reason code for scoped logical table splitting.",
        examples=["analysis_section_markers_with_repeated_year_headers_and_subtotal_rows"],
    )
    detected_table_id: str | None = Field(
        default=None,
        description="Detected table identity propagated from extraction.",
        examples=["2025:20:0"],
    )
    page_table_index: int | None = Field(
        default=None,
        ge=0,
        description="Zero-based table index on the source page from detection order.",
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
        description="Detector confidence propagated with the table.",
        examples=[0.97],
    )
    match_method: str | None = Field(
        default=None,
        description="Matching strategy used to assign table_type.",
        examples=["detected_table_id"],
    )
    rows: list[list[str]] = Field(
        default_factory=list,
        description="Normalized table rows with canonical metric labels where available.",
    )
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description=(
            "Normalized metric values with value_year and source_report_year "
            "preserved."
        ),
    )

    @property
    def year(self) -> int:
        """Backward-compatible alias for source_report_year."""

        return self.source_report_year


class NormalizationResult(BaseModel):
    """OCR metric normalization result consumed by downstream OCR layers."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tables": [
                        {
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "income_statement",
                            "table_index": 0,
                            "rows": [["revenue", "1200000", "1100000"]],
                            "metric_values": [
                                {
                                    "metric": "revenue",
                                    "value_year": 2024,
                                    "value": 1500,
                                    "source_report_year": 2025,
                                    "page_number": 20,
                                    "table_type": "income_statement",
                                }
                            ],
                        }
                    ],
                    "metric_values": [
                        {
                            "metric": "revenue",
                            "value_year": 2024,
                            "value": 1500,
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "income_statement",
                        }
                    ],
                    "mappings": [
                        {
                            "value_year": 2024,
                            "source_report_year": 2025,
                            "original_metric": "Net Sales",
                            "normalized_metric": "revenue",
                            "confidence": 0.96,
                            "requires_review": False,
                        }
                    ],
                }
            ]
        },
    )

    tables: list[NormalizedTable] = Field(
        ...,
        description="Normalized OCR tables available as financial context.",
    )
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description="All normalized metric values across tables in this result.",
    )
    mappings: list["MetricMapping"] = Field(
        default_factory=list,
        description="Metric normalization mappings generated for report-originated rows.",
    )


class MetricMapping(BaseModel):
    """Mapping between a raw OCR metric label and a canonical metric."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "value_year": 2024,
                    "source_report_year": 2025,
                    "original_metric": "Net Sales",
                    "normalized_metric": "revenue",
                    "confidence": 0.96,
                    "requires_review": False,
                }
            ]
        },
    )

    value_year: int = Field(
        ...,
        ge=1900,
        validation_alias=AliasChoices("value_year", "year"),
        description="Financial year represented by the mapped metric value.",
        examples=[2024],
    )
    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which this mapping originated.",
        examples=[2025],
    )
    original_metric: str = Field(
        ...,
        min_length=1,
        description="Raw metric label extracted from the source report.",
        examples=["Net Sales"],
    )
    normalized_metric: str | None = Field(
        ...,
        description="Canonical metric key or null when manual review is required.",
        examples=["revenue"],
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence score for the metric normalization decision.",
        examples=[0.96],
    )
    requires_review: bool = Field(
        ...,
        description="Whether this metric mapping should be reviewed manually.",
        examples=[False],
    )
    page_number: int | None = Field(
        default=None,
        gt=0,
        description="Source page for the mapped metric value.",
        examples=[20],
    )
    table_type: str | None = Field(
        default=None,
        description="Source table type for the mapped metric value.",
        examples=["income_statement"],
    )
    table_index: int | None = Field(
        default=None,
        ge=0,
        description="Source extracted table index for the mapped metric value.",
        examples=[0],
    )
    detected_table_id: str | None = Field(
        default=None,
        description="Detected table identity for the mapped metric value.",
        examples=["2025:20:0"],
    )
    match_method: str | None = Field(
        default=None,
        description="Matching strategy used for the source table.",
        examples=["detected_table_id"],
    )
    normalization_input_metric: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Metric text actually submitted to canonical normalization when it "
            "differs from original_metric."
        ),
        examples=["Depreciation"],
    )
    parent_metric_context: str | None = Field(
        default=None,
        min_length=1,
        description="Preserved parent note or section context stripped from the child metric.",
        examples=["COST OF SALES"],
    )
    child_metric: str | None = Field(
        default=None,
        min_length=1,
        description="Child metric label used after parent-prefix stripping.",
        examples=["Depreciation"],
    )
    parent_prefix_stripped: bool = Field(
        default=False,
        description="Whether parent context was stripped before canonical normalization.",
        examples=[True],
    )
    normalization_rule: str | None = Field(
        default=None,
        description="Rule responsible for a normalization preprocessing decision.",
        examples=["parent_prefix_stripping"],
    )

    @property
    def year(self) -> int:
        """Backward-compatible alias for value_year."""

        return self.value_year
