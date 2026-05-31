"""Models returned by the OCR financial validation layer."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ValidationSeverity(str, Enum):
    """Supported severity levels for validation issues."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ValidationIssue(BaseModel):
    """A single accounting, financial, OCR, or completeness validation issue."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "year": 2024,
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

    year: int = Field(
        ...,
        ge=1900,
        description="Financial reporting year where the validation issue occurred.",
        examples=[2024],
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
    severity: ValidationSeverity = Field(
        ...,
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
                            "year": 2024,
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
