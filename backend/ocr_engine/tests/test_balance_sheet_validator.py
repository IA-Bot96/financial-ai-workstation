"""Unit tests for balance sheet validation formulas."""

from validation_test_helpers import context_for, extracted_table, rule_names

from ocr_engine.validation.validators.balance_sheet_validator import (
    BalanceSheetValidator,
)


def _balance_sheet_rows(total_assets: str = "2500") -> list[list[str]]:
    return [
        ["Particulars", "2024", "2023"],
        ["Cash and bank balances", "100"],
        ["Stock in trade", "200"],
        ["Trade debts", "300"],
        ["Other current assets", "400"],
        ["Current assets", "1000"],
        ["Non-current assets", "1500"],
        ["Total assets", total_assets],
        ["Trade and other payables", "200"],
        ["Short term borrowings", "300"],
        ["Current portion of long term debt", "100"],
        ["Other current liabilities", "100"],
        ["Current liabilities", "700"],
        ["Non-current liabilities", "800"],
        ["Total liabilities", "1500"],
        ["Share capital", "500"],
        ["Reserves", "300"],
        ["Retained earnings", "200"],
        ["Total equity", "1000"],
    ]


def test_balance_sheet_validator_accepts_balanced_statement() -> None:
    context = context_for(
        [extracted_table(_balance_sheet_rows(), "balance_sheet")]
    )

    issues = BalanceSheetValidator().validate(context)

    assert issues == []


def test_balance_sheet_validator_flags_accounting_equation_mismatch() -> None:
    context = context_for(
        [extracted_table(_balance_sheet_rows(total_assets="2400"), "balance_sheet")]
    )

    issues = BalanceSheetValidator().validate(context)

    assert "accounting_equation" in rule_names(issues)
    assert "total_assets_breakdown" in rule_names(issues)
