"""Balance sheet accounting equation validators."""

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.validators.base import (
    BALANCE_SHEET_TABLE_TYPES,
    MetricRef,
    RuleValidator,
    ValidationContext,
    validate_arithmetic_rule,
)


class BalanceSheetValidator(RuleValidator):
    """Validate balance sheet formulas using extracted statement rows."""

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run balance sheet validation rules."""

        rules = [
            validate_arithmetic_rule(
                context=context,
                rule_name="accounting_equation",
                actual_ref=MetricRef("total_assets", BALANCE_SHEET_TABLE_TYPES),
                terms=[
                    (MetricRef("total_liabilities", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("total_equity", BALANCE_SHEET_TABLE_TYPES), 1),
                ],
                severity="critical",
                message="Total assets should equal total liabilities plus total equity.",
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="total_assets_breakdown",
                actual_ref=MetricRef("total_assets", BALANCE_SHEET_TABLE_TYPES),
                terms=[
                    (MetricRef("current_assets", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("non_current_assets", BALANCE_SHEET_TABLE_TYPES), 1),
                ],
                severity="major",
                message="Total assets should equal current assets plus non-current assets.",
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="current_assets_breakdown",
                actual_ref=MetricRef("current_assets", BALANCE_SHEET_TABLE_TYPES),
                terms=[
                    (MetricRef("cash", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("inventory", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("trade_receivables", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("other_current_assets", BALANCE_SHEET_TABLE_TYPES), 1),
                ],
                severity="major",
                message=(
                    "Current assets should equal cash, inventory, trade receivables, "
                    "and other current assets."
                ),
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="current_liabilities_breakdown",
                actual_ref=MetricRef("current_liabilities", BALANCE_SHEET_TABLE_TYPES),
                terms=[
                    (MetricRef("trade_payables", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("short_term_borrowings", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("current_portion_of_debt", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("other_current_liabilities", BALANCE_SHEET_TABLE_TYPES), 1),
                ],
                severity="major",
                message=(
                    "Current liabilities should equal trade payables, short-term "
                    "borrowings, current debt portion, and other current liabilities."
                ),
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="total_liabilities_breakdown",
                actual_ref=MetricRef("total_liabilities", BALANCE_SHEET_TABLE_TYPES),
                terms=[
                    (MetricRef("current_liabilities", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("non_current_liabilities", BALANCE_SHEET_TABLE_TYPES), 1),
                ],
                severity="major",
                message=(
                    "Total liabilities should equal current liabilities plus "
                    "non-current liabilities."
                ),
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="total_equity_breakdown",
                actual_ref=MetricRef("total_equity", BALANCE_SHEET_TABLE_TYPES),
                terms=[
                    (MetricRef("share_capital", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("reserves", BALANCE_SHEET_TABLE_TYPES), 1),
                    (MetricRef("retained_earnings", BALANCE_SHEET_TABLE_TYPES), 1),
                ],
                severity="major",
                message=(
                    "Total equity should equal share capital, reserves, and "
                    "retained earnings."
                ),
            ),
        ]

        return [issue for issue in rules if issue is not None]
