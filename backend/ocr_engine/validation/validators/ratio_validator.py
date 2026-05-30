"""Financial ratio validators."""

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.validators.base import (
    BALANCE_SHEET_TABLE_TYPES,
    INCOME_STATEMENT_TABLE_TYPES,
    MetricRef,
    RuleValidator,
    ValidationContext,
    validate_ratio_rule,
)


class RatioValidator(RuleValidator):
    """Validate common ratio formulas when ratio rows are extracted."""

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run ratio validation rules."""

        rules = [
            validate_ratio_rule(
                context=context,
                rule_name="eps_formula",
                actual_ref=MetricRef("eps"),
                numerator_ref=MetricRef("profit_after_tax", INCOME_STATEMENT_TABLE_TYPES),
                denominator_ref=MetricRef("weighted_average_shares"),
                severity="major",
                message="EPS should equal profit after tax divided by weighted average shares.",
            ),
            validate_ratio_rule(
                context=context,
                rule_name="roe_formula",
                actual_ref=MetricRef("roe"),
                numerator_ref=MetricRef("profit_after_tax", INCOME_STATEMENT_TABLE_TYPES),
                denominator_ref=MetricRef("average_equity"),
                severity="major",
                message="ROE should equal profit after tax divided by average equity.",
            ),
            validate_ratio_rule(
                context=context,
                rule_name="current_ratio_formula",
                actual_ref=MetricRef("current_ratio"),
                numerator_ref=MetricRef("current_assets", BALANCE_SHEET_TABLE_TYPES),
                denominator_ref=MetricRef("current_liabilities", BALANCE_SHEET_TABLE_TYPES),
                severity="major",
                message="Current ratio should equal current assets divided by current liabilities.",
            ),
        ]

        return [issue for issue in rules if issue is not None]
