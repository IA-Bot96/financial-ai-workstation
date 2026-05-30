"""Models returned by the OCR financial validation layer."""

from pydantic import BaseModel, ConfigDict, Field


class ValidationIssue(BaseModel):
    """A single accounting, financial, OCR, or completeness validation issue."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "rule_name": "accounting_equation",
                    "expected": 1250000.0,
                    "actual": 1240000.0,
                    "severity": "critical",
                    "message": (
                        "Total assets should equal total liabilities plus "
                        "total equity."
                    ),
                }
            ]
        },
    )

    rule_name: str = Field(
        ...,
        min_length=1,
        description="Stable validation rule identifier.",
        examples=["accounting_equation"],
    )
    expected: float | str | None = Field(
        ...,
        description="Expected value or condition calculated by the validation rule.",
        examples=[1250000.0],
    )
    actual: float | str | None = Field(
        ...,
        description="Actual extracted value or observed condition.",
        examples=[1240000.0],
    )
    severity: str = Field(
        ...,
        min_length=1,
        description="Issue severity. Expected values are critical, major, or minor.",
        examples=["critical"],
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Human-readable explanation of the failed validation rule.",
        examples=[
            "Total assets should equal total liabilities plus total equity."
        ],
    )


class ValidationResult(BaseModel):
    """Aggregated validation result for extracted financial statement tables."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "is_valid": False,
                    "validation_score": 70.0,
                    "issues": [
                        {
                            "rule_name": "accounting_equation",
                            "expected": 1250000.0,
                            "actual": 1240000.0,
                            "severity": "critical",
                            "message": (
                                "Total assets should equal total liabilities "
                                "plus total equity."
                            ),
                        }
                    ],
                }
            ]
        },
    )

    is_valid: bool = Field(
        ...,
        description="Whether the extracted financial data passed validation.",
        examples=[False],
    )
    validation_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Validation score from 0 to 100 after severity deductions.",
        examples=[70.0],
    )
    issues: list[ValidationIssue] = Field(
        ...,
        description="All validation issues found across rule categories.",
    )
