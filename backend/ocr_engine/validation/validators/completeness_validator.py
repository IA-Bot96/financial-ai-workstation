"""Completeness validators for major financial statement sections."""

from ocr_engine.models.validation_result import ValidationIssue
from ocr_engine.validation.validators.base import (
    BALANCE_SHEET_TABLE_TYPES,
    CASH_FLOW_TABLE_TYPES,
    INCOME_STATEMENT_TABLE_TYPES,
    RuleValidator,
    ValidationContext,
    labels_contain_any,
    make_issue,
)


class CompletenessValidator(RuleValidator):
    """Validate presence of major financial statement sections."""

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Run completeness checks across statement types."""

        section_checks = [
            (
                "balance_sheet_assets_section",
                BALANCE_SHEET_TABLE_TYPES,
                ("total_assets", "current_assets", "non_current_assets", "cash"),
                ("assets", "current assets", "non current assets"),
                "Balance sheet assets section should be present.",
            ),
            (
                "balance_sheet_liabilities_section",
                BALANCE_SHEET_TABLE_TYPES,
                ("total_liabilities", "current_liabilities", "non_current_liabilities"),
                ("liabilities", "current liabilities", "non current liabilities"),
                "Balance sheet liabilities section should be present.",
            ),
            (
                "balance_sheet_equity_section",
                BALANCE_SHEET_TABLE_TYPES,
                ("total_equity", "share_capital", "reserves", "retained_earnings"),
                ("equity", "share capital", "reserves", "retained earnings"),
                "Balance sheet equity section should be present.",
            ),
            (
                "income_statement_revenue_section",
                INCOME_STATEMENT_TABLE_TYPES,
                ("revenue",),
                ("revenue", "sales", "turnover"),
                "Income statement revenue section should be present.",
            ),
            (
                "income_statement_expenses_section",
                INCOME_STATEMENT_TABLE_TYPES,
                ("cost_of_sales", "operating_expenses", "finance_cost", "tax_expense"),
                ("expense", "expenses", "cost of sales", "finance cost", "tax"),
                "Income statement expense section should be present.",
            ),
            (
                "income_statement_profit_section",
                INCOME_STATEMENT_TABLE_TYPES,
                ("gross_profit", "operating_profit", "profit_after_tax"),
                ("profit", "income", "earnings"),
                "Income statement profit section should be present.",
            ),
            (
                "cash_flow_operating_section",
                CASH_FLOW_TABLE_TYPES,
                ("operating_cash_flow",),
                ("operating activities", "operating cash flow"),
                "Cash flow operating activities section should be present.",
            ),
            (
                "cash_flow_investing_section",
                CASH_FLOW_TABLE_TYPES,
                ("investing_cash_flow",),
                ("investing activities", "investing cash flow"),
                "Cash flow investing activities section should be present.",
            ),
            (
                "cash_flow_financing_section",
                CASH_FLOW_TABLE_TYPES,
                ("financing_cash_flow",),
                ("financing activities", "financing cash flow"),
                "Cash flow financing activities section should be present.",
            ),
        ]

        issues: list[ValidationIssue] = []
        for rule_name, table_types, metric_names, keywords, message in section_checks:
            labels = context.labels_for(table_types)
            has_section = context.has_metric(metric_names, table_types) or labels_contain_any(
                labels,
                keywords,
            )
            if has_section:
                continue

            issues.append(
                make_issue(
                    rule_name=rule_name,
                    expected="section present",
                    actual="section missing",
                    severity="major",
                    message=message,
                )
            )
        return issues
