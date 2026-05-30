"""Unit tests for validation score calculation."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.scoring.validation_score_calculator import (
    ValidationScoreCalculator,
)


def _issue(severity: str) -> ValidationIssue:
    return ValidationIssue(
        year=2024,
        rule_name=f"{severity}_rule",
        expected="ok",
        actual="bad",
        severity=severity,
        message="Validation failed.",
    )


def test_score_calculator_applies_severity_deductions() -> None:
    calculator = ValidationScoreCalculator()

    score = calculator.calculate_score(
        [_issue("critical"), _issue("major"), _issue("minor")]
    )

    assert score == 68.0
    assert calculator.is_valid(score) is False


def test_score_calculator_clamps_score_at_zero() -> None:
    calculator = ValidationScoreCalculator()

    score = calculator.calculate_score([_issue("critical") for _ in range(8)])

    assert score == 0.0
