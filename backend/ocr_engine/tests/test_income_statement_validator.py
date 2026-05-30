"""Unit tests for income statement validation formulas."""

from validation_test_helpers import context_for, extracted_table, rule_names

from ocr_engine.validation.validators.income_statement_validator import (
    IncomeStatementValidator,
)


def _income_statement_rows(profit_after_tax: str = "150") -> list[list[str]]:
    return [
        ["Revenue", "1000"],
        ["Cost of sales", "600"],
        ["Gross profit", "400"],
        ["Operating expenses", "150"],
        ["Operating profit", "250"],
        ["Other income", "50"],
        ["EBIT", "300"],
        ["Finance cost", "80"],
        ["Profit before tax", "220"],
        ["Tax expense", "70"],
        ["Profit after tax", profit_after_tax],
    ]


def test_income_statement_validator_accepts_valid_formulas() -> None:
    context = context_for(
        [extracted_table(_income_statement_rows(), "income_statement")]
    )

    issues = IncomeStatementValidator().validate(context)

    assert issues == []


def test_income_statement_validator_flags_profit_after_tax_mismatch() -> None:
    context = context_for(
        [
            extracted_table(
                _income_statement_rows(profit_after_tax="160"),
                "income_statement",
            )
        ]
    )

    issues = IncomeStatementValidator().validate(context)

    assert "profit_after_tax_formula" in rule_names(issues)
