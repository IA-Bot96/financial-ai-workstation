"""Cash flow statement formula validators."""

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.validators.base import (
    CASH_FLOW_TABLE_TYPES,
    MetricRef,
    RuleValidator,
    ValidationContext,
    validate_arithmetic_rule,
)


class CashFlowValidator(RuleValidator):
    """Validate core cash flow statement formulas."""

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run cash flow validation rules."""

        rules = [
            validate_arithmetic_rule(
                context=context,
                rule_name="net_change_in_cash_formula",
                actual_ref=MetricRef("net_change_in_cash", CASH_FLOW_TABLE_TYPES),
                terms=[
                    (MetricRef("operating_cash_flow", CASH_FLOW_TABLE_TYPES), 1),
                    (MetricRef("investing_cash_flow", CASH_FLOW_TABLE_TYPES), 1),
                    (MetricRef("financing_cash_flow", CASH_FLOW_TABLE_TYPES), 1),
                ],
                severity="major",
                message=(
                    "Net change in cash should equal operating, investing, "
                    "and financing cash flows."
                ),
            ),
            validate_arithmetic_rule(
                context=context,
                rule_name="closing_cash_formula",
                actual_ref=MetricRef("closing_cash", CASH_FLOW_TABLE_TYPES),
                terms=[
                    (MetricRef("opening_cash", CASH_FLOW_TABLE_TYPES), 1),
                    (MetricRef("net_change_in_cash", CASH_FLOW_TABLE_TYPES), 1),
                ],
                severity="major",
                message="Closing cash should equal opening cash plus net change in cash.",
            ),
        ]

        return [issue for issue in rules if issue is not None]
