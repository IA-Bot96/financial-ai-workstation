"""OCR quality and sanity validators."""

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.validators.base import (
    BALANCE_SHEET_TABLE_TYPES,
    INCOME_STATEMENT_TABLE_TYPES,
    RuleValidator,
    ValidationContext,
    duplicate_labels,
    make_issue,
    round_number,
    years_are_descending,
)


class OCRValidator(RuleValidator):
    """Validate OCR output quality signals before downstream processing."""

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run OCR sanity checks over raw extracted tables."""

        issues: list[ValidationIssue] = []
        issues.extend(self._validate_duplicate_rows(context))
        issues.extend(self._validate_missing_critical_metrics(context))
        issues.extend(self._validate_invalid_negative_values(context))
        issues.extend(self._validate_year_ordering(context))
        return issues

    def _validate_duplicate_rows(
        self,
        context: ValidationContext,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for key, labels in context.labels_by_table.items():
            duplicates = duplicate_labels(labels)
            if not duplicates:
                continue

            table = context.tables_by_key[key]
            issues.append(
                make_issue(
                    year=table.year,
                    rule_name="duplicate_rows",
                    expected="unique row labels",
                    actual=", ".join(duplicates),
                    severity="minor",
                    message=(
                        "Duplicate metric labels were detected on "
                        f"page {table.page_number}, table {table.table_index}."
                    ),
                )
            )
        return issues

    def _validate_missing_critical_metrics(
        self,
        context: ValidationContext,
    ) -> list[ValidationIssue]:
        critical_metrics = {
            "revenue": INCOME_STATEMENT_TABLE_TYPES,
            "profit_after_tax": INCOME_STATEMENT_TABLE_TYPES,
            "total_assets": BALANCE_SHEET_TABLE_TYPES,
            "total_liabilities": BALANCE_SHEET_TABLE_TYPES,
            "total_equity": BALANCE_SHEET_TABLE_TYPES,
        }

        issues: list[ValidationIssue] = []
        for metric_name, table_types in critical_metrics.items():
            if context.value_for(metric_name, table_types) is not None:
                continue

            issues.append(
                make_issue(
                    year=context.primary_year,
                    rule_name="missing_critical_metric",
                    expected=metric_name,
                    actual=None,
                    severity="critical",
                    message=(
                        f"Critical metric '{metric_name}' was not found in "
                        "the extracted financial tables."
                    ),
                )
            )
        return issues

    def _validate_invalid_negative_values(
        self,
        context: ValidationContext,
    ) -> list[ValidationIssue]:
        checks = {
            "revenue": INCOME_STATEMENT_TABLE_TYPES,
            "total_assets": BALANCE_SHEET_TABLE_TYPES,
            "current_assets": BALANCE_SHEET_TABLE_TYPES,
            "non_current_assets": BALANCE_SHEET_TABLE_TYPES,
            "inventory": BALANCE_SHEET_TABLE_TYPES,
        }

        issues: list[ValidationIssue] = []
        for metric_name, table_types in checks.items():
            for observation in context.observations_for(metric_name, table_types):
                if observation.value >= 0:
                    continue

                issues.append(
                    make_issue(
                        year=observation.year,
                        rule_name="invalid_negative_value",
                        expected=f"{metric_name} >= 0",
                        actual=round_number(observation.value),
                        severity="major",
                        message=(
                            f"Metric '{metric_name}' should not be negative "
                            "for financial statement validation."
                        ),
                    )
                )
        return issues

    def _validate_year_ordering(
        self,
        context: ValidationContext,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for key, year_sequences in context.year_sequences_by_table.items():
            table = context.tables_by_key[key]
            for years in year_sequences:
                if years_are_descending(years):
                    continue

                issues.append(
                    make_issue(
                        year=table.year,
                        rule_name="year_ordering",
                        expected="descending years",
                        actual=", ".join(str(year) for year in years),
                        severity="minor",
                        message=(
                            "Reporting years should be ordered descending "
                            f"on page {table.page_number}, table {table.table_index}."
                        ),
                    )
                )
        return issues
