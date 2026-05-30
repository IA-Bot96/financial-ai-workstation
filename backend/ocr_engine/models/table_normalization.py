"""Models for OCR table metric normalization output."""

from pydantic import BaseModel, ConfigDict, Field


class NormalizedTable(BaseModel):
    """Extracted table rows after OCR metric labels have been normalized."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "page_number": 20,
                    "table_type": "income_statement",
                    "table_index": 0,
                    "rows": [
                        ["revenue", "1200000", "1100000"],
                        ["cost_of_sales", "800000", "760000"],
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
    rows: list[list[str]] = Field(
        ...,
        description="Normalized table rows with canonical metric labels where available.",
    )


class NormalizationResult(BaseModel):
    """OCR metric normalization result consumed by downstream OCR layers."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tables": [
                        {
                            "year": 2024,
                            "page_number": 20,
                            "table_type": "income_statement",
                            "table_index": 0,
                            "rows": [["revenue", "1200000", "1100000"]],
                        }
                    ],
                    "mappings": [
                        {
                            "year": 2024,
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
    mappings: list["MetricMapping"] = Field(
        default_factory=list,
        description="Metric normalization mappings generated for report-originated rows.",
    )


class MetricMapping(BaseModel):
    """Mapping between a raw OCR metric label and a canonical metric for one year."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
                    "original_metric": "Net Sales",
                    "normalized_metric": "revenue",
                    "confidence": 0.96,
                    "requires_review": False,
                }
            ]
        },
    )

    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year for the mapped metric.",
        examples=[2024],
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
