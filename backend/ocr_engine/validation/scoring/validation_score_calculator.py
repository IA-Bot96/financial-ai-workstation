"""Score calculation for OCR financial validation results."""

from ocr_engine.models.validation_result import ValidationIssue, ValidationSeverity


class ValidationScoreCalculator:
    """Calculate validation scores from issue severities."""

    _severity_deductions = {
        ValidationSeverity.CRITICAL: 20,
        ValidationSeverity.MAJOR: 10,
        ValidationSeverity.MINOR: 2,
    }

    def calculate_score(self, issues: list[ValidationIssue]) -> float:
        """Return a clamped score from 0 to 100 without duplicate penalties."""

        deductions = sum(
            self._severity_deductions.get(issue.severity, 10)
            for issue in self._deduplicate_issues(issues)
        )
        return float(max(0, min(100, 100 - deductions)))

    def is_valid(
        self,
        score: float,
        issues: list[ValidationIssue] | None = None,
    ) -> bool:
        """Return whether a validation score passes the production threshold."""

        if issues and self.has_critical_issue(issues):
            return False
        return score >= 80

    @staticmethod
    def has_critical_issue(issues: list[ValidationIssue]) -> bool:
        """Return whether any issue is production-critical."""

        return any(issue.severity == ValidationSeverity.CRITICAL for issue in issues)

    @staticmethod
    def _deduplicate_issues(
        issues: list[ValidationIssue],
    ) -> tuple[ValidationIssue, ...]:
        """Avoid scoring the same rule observation repeatedly across value years."""

        unique: list[ValidationIssue] = []
        seen: set[tuple[ValidationSeverity, str, str, str, str]] = set()
        for issue in issues:
            key = (
                issue.severity,
                issue.rule_name,
                str(issue.expected),
                str(issue.actual),
                issue.message,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(issue)
        return tuple(unique)
