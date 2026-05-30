"""Cross-statement consistency validators."""

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.validators.base import (
    BALANCE_SHEET_TABLE_TYPES,
    CASH_FLOW_TABLE_TYPES,
    DEBT_TABLE_TYPES,
    EQUITY_TABLE_TYPES,
    INCOME_STATEMENT_TABLE_TYPES,
    PPE_TABLE_TYPES,
    MetricRef,
    RuleValidator,
    ValidationContext,
    validate_arithmetic_rule,
)


class CrossStatementValidator(RuleValidator):
    """Validate consistency across financial statements and notes."""

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run cross-statement validation rules."""

        balance_sheet_and_ppe = BALANCE_SHEET_TABLE_TYPES + PPE_TABLE_TYPES
        balance_sheet_and_debt = BALANCE_SHEET_TABLE_TYPES + DEBT_TABLE_TYPES

        rules = [
            validate_arithmetic_rule(
                context=context,
                rule_name="cash_consistency",
                actual_ref=MetricRef("cash", BALANCE_SHEET_TABLE_TYPES),
                terms=[(MetricRef("closing_cash", CASH_FLOW_TABLE_TYPES), 1)],
                severity="critical",
                message=(
                    "Balance sheet cash should equal closing cash from the "
                    "cash flow statement."
                ),
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="retained_earnings_roll_forward",
                actual_ref=MetricRef("ending_retained_earnings", EQUITY_TABLE_TYPES),
                terms=[
                    (MetricRef("beginning_retained_earnings", EQUITY_TABLE_TYPES), 1),
                    (MetricRef("profit_after_tax", INCOME_STATEMENT_TABLE_TYPES), 1),
                    (MetricRef("dividends", EQUITY_TABLE_TYPES), -1),
                ],
                severity="major",
                message=(
                    "Ending retained earnings should equal beginning retained "
                    "earnings plus profit after tax less dividends."
                ),
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="ppe_roll_forward",
                actual_ref=MetricRef("ending_ppe", balance_sheet_and_ppe),
                terms=[
                    (MetricRef("beginning_ppe", balance_sheet_and_ppe), 1),
                    (MetricRef("capex", PPE_TABLE_TYPES), 1),
                    (MetricRef("depreciation", PPE_TABLE_TYPES), -1),
                ],
                severity="major",
                message=(
                    "Ending PPE should equal beginning PPE plus capex less "
                    "depreciation."
                ),
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="debt_roll_forward",
                actual_ref=MetricRef("ending_debt", balance_sheet_and_debt),
                terms=[
                    (MetricRef("beginning_debt", balance_sheet_and_debt), 1),
                    (MetricRef("new_borrowings", DEBT_TABLE_TYPES), 1),
                    (MetricRef("repayments", DEBT_TABLE_TYPES), -1),
                ],
                severity="major",
                message=(
                    "Ending debt should equal beginning debt plus new borrowings "
                    "less repayments."
                ),
            ),
        ]

        return [issue for issue in rules if issue is not None]
