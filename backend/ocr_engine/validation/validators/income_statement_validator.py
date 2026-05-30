"""Income statement formula validators."""

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.validators.base import (
    INCOME_STATEMENT_TABLE_TYPES,
    MetricRef,
    RuleValidator,
    ValidationContext,
    validate_arithmetic_rule,
)


class IncomeStatementValidator(RuleValidator):
    """Validate core income statement formulas."""

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run income statement validation rules."""

        rules = [
            validate_arithmetic_rule(
                context=context,
                rule_name="gross_profit_formula",
                actual_ref=MetricRef("gross_profit", INCOME_STATEMENT_TABLE_TYPES),
                terms=[
                    (MetricRef("revenue", INCOME_STATEMENT_TABLE_TYPES), 1),
                    (MetricRef("cost_of_sales", INCOME_STATEMENT_TABLE_TYPES), -1),
                ],
                severity="major",
                message="Gross profit should equal revenue less cost of sales.",
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="operating_profit_formula",
                actual_ref=MetricRef("operating_profit", INCOME_STATEMENT_TABLE_TYPES),
                terms=[
                    (MetricRef("gross_profit", INCOME_STATEMENT_TABLE_TYPES), 1),
                    (MetricRef("operating_expenses", INCOME_STATEMENT_TABLE_TYPES), -1),
                ],
                severity="major",
                message="Operating profit should equal gross profit less operating expenses.",
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="ebit_formula",
                actual_ref=MetricRef("ebit", INCOME_STATEMENT_TABLE_TYPES),
                terms=[
                    (MetricRef("operating_profit", INCOME_STATEMENT_TABLE_TYPES), 1),
                    (MetricRef("other_income", INCOME_STATEMENT_TABLE_TYPES), 1),
                ],
                severity="major",
                message="EBIT should equal operating profit plus other income.",
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="profit_before_tax_formula",
                actual_ref=MetricRef("profit_before_tax", INCOME_STATEMENT_TABLE_TYPES),
                terms=[
                    (MetricRef("ebit", INCOME_STATEMENT_TABLE_TYPES), 1),
                    (MetricRef("finance_cost", INCOME_STATEMENT_TABLE_TYPES), -1),
                ],
                severity="major",
                message="Profit before tax should equal EBIT less finance cost.",
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="profit_after_tax_formula",
                actual_ref=MetricRef("profit_after_tax", INCOME_STATEMENT_TABLE_TYPES),
                terms=[
                    (MetricRef("profit_before_tax", INCOME_STATEMENT_TABLE_TYPES), 1),
                    (MetricRef("tax_expense", INCOME_STATEMENT_TABLE_TYPES), -1),
                ],
                severity="major",
                message="Profit after tax should equal profit before tax less tax expense.",
            ),
        ]

        return [issue for issue in rules if issue is not None]
