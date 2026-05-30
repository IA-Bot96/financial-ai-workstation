"""Template compatibility validation result model."""

from pydantic import BaseModel, ConfigDict, Field

from workbook_population.models.sheet_validation_result import SheetValidationResult


class TemplateValidationResult(BaseModel):
    """Aggregate compatibility score and diagnostics for an uploaded template."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "is_match": True,
                    "match_score": 97.5,
                    "sheet_results": [
                        {
                            "sheet_name": "Income Statement",
                            "match_score": 98.0,
                            "is_compatible": True,
                            "missing_metrics": [],
                            "extra_metrics": [],
                            "warnings": [],
                        }
                    ],
                    "missing_metrics": [],
                    "extra_metrics": ["dividend_payout_ratio"],
                    "warnings": [],
                }
            ]
        },
    )

    is_match: bool = Field(
        ...,
        description="Whether the template score is high enough for automatic use.",
        examples=[True],
    )
    match_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Aggregate workbook compatibility score from 0 to 100.",
        examples=[97.5],
    )
    sheet_results: list[SheetValidationResult] = Field(
        default_factory=list,
        description="Per-sheet compatibility decisions and diagnostics.",
    )
    missing_metrics: list[str] = Field(
        default_factory=list,
        description="Canonical metrics present in extracted data but absent from matching sheets.",
        examples=[["ebitda"]],
    )
    extra_metrics: list[str] = Field(
        default_factory=list,
        description="Canonical-looking template metrics absent from extracted data.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable compatibility warnings for users and logs.",
    )
