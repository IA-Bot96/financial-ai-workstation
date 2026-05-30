"""Unit tests for validation result models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.validation_result import ValidationIssue, ValidationResult


def test_validation_result_accepts_valid_payload() -> None:
    issue = ValidationIssue(
        rule_name="accounting_equation",
        expected=1250.0,
        actual=1240.0,
        severity="critical",
        message="Total assets should equal liabilities plus equity.",
    )

    result = ValidationResult(
        is_valid=False,
        validation_score=80,
        issues=[issue],
    )

    assert result.model_dump() == {
        "is_valid": False,
        "validation_score": 80.0,
        "issues": [
            {
                "rule_name": "accounting_equation",
                "expected": 1250.0,
                "actual": 1240.0,
                "severity": "critical",
                "message": "Total assets should equal liabilities plus equity.",
            }
        ],
    }


def test_validation_issue_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ValidationIssue(
            rule_name="accounting_equation",
            expected=1250.0,
            actual=1240.0,
            severity="critical",
            message="Mismatch.",
            page=20,
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_validation_result_bounds_score() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ValidationResult(is_valid=True, validation_score=120, issues=[])

    assert exc_info.value.errors()[0]["type"] == "less_than_equal"
