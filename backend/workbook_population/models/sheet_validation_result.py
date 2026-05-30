"""Sheet-level template compatibility validation result model."""

from pydantic import BaseModel, ConfigDict, Field


class SheetValidationResult(BaseModel):
    """Compatibility score and diagnostics for one workbook sheet."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "sheet_name": "Income Statement",
                    "match_score": 98.0,
                    "is_compatible": True,
                    "missing_metrics": [],
                    "extra_metrics": ["dividend_payout_ratio"],
                    "warnings": [],
                },
                {
                    "sheet_name": "Cash Flow",
                    "match_score": 71.0,
                    "is_compatible": False,
                    "missing_metrics": ["operating_cash_flow"],
                    "extra_metrics": [],
                    "warnings": ["Cash Flow sheet is below 80% compatibility."],
                },
            ]
        },
    )

    sheet_name: str = Field(
        ...,
        min_length=1,
        description="Canonical workbook sheet name evaluated for compatibility.",
        examples=["Income Statement"],
    )
    match_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Sheet compatibility score from 0 to 100.",
        examples=[98.0],
    )
    is_compatible: bool = Field(
        ...,
        description="Whether this sheet can be reused automatically.",
        examples=[True],
    )
    missing_metrics: list[str] = Field(
        default_factory=list,
        description="Canonical metrics required by extracted data but absent from this sheet.",
        examples=[["ebitda"]],
    )
    extra_metrics: list[str] = Field(
        default_factory=list,
        description="Template metrics present on this sheet but absent from extracted data.",
        examples=[["dividend_payout_ratio"]],
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable sheet compatibility warnings.",
    )
