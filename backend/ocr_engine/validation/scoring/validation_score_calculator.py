"""Score calculation for OCR financial validation results."""

from ocr_engine.models.validation_result import ValidationIssue


class ValidationScoreCalculator:
    """Calculate validation scores from issue severities."""

    _severity_deductions = {
        "critical": 20,
        "major": 10,
        "minor": 2,
    }

    def calculate_score(self, issues: list[ValidationIssue]) -> float:
        """Return a clamped score from 0 to 100."""

        deductions = sum(
            self._severity_deductions.get(issue.severity.lower(), 10)
            for issue in issues
        )
        return float(max(0, min(100, 100 - deductions)))

    def is_valid(self, score: float) -> bool:
        """Return whether a validation score passes the production threshold."""

        return score >= 80
