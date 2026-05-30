"""Unit tests for cross-statement validation formulas."""

from validation_test_helpers import context_for, extracted_table, rule_names

from ocr_engine.validation.validators.cross_statement_validator import (
    CrossStatementValidator,
)


def _cross_statement_tables(closing_cash: str = "450") -> list[object]:
    return [
        extracted_table(
            [["Cash and bank balances", "450"]],
            "balance_sheet",
            page_number=1,
            table_index=0,
        ),
        extracted_table(
            [["Cash and cash equivalents at end of year", closing_cash]],
            "cash_flow_statement",
            page_number=2,
            table_index=0,
        ),
        extracted_table(
            [
                ["Retained earnings at beginning of year", "100"],
                ["Dividend paid", "50"],
                ["Retained earnings at end of year", "200"],
            ],
            "statement_of_changes_in_equity",
            page_number=3,
            table_index=0,
        ),
        extracted_table(
            [
                ["Opening written down value", "1000"],
                ["Additions to property plant and equipment", "200"],
                ["Depreciation charge", "100"],
                ["Closing written down value", "1100"],
            ],
            "property_plant_equipment_note",
            page_number=4,
            table_index=0,
        ),
        extracted_table(
            [
                ["Opening borrowings", "500"],
                ["Proceeds from borrowings", "250"],
                ["Repayment of borrowings", "100"],
                ["Closing borrowings", "650"],
            ],
            "debt_schedule",
            page_number=5,
            table_index=0,
        ),
        extracted_table(
            [["Profit after tax", "150"]],
            "income_statement",
            page_number=6,
            table_index=0,
        ),
    ]


def test_cross_statement_validator_accepts_consistent_roll_forwards() -> None:
    context = context_for(_cross_statement_tables())

    issues = CrossStatementValidator().validate(context)

    assert issues == []


def test_cross_statement_validator_flags_cash_consistency_mismatch() -> None:
    context = context_for(_cross_statement_tables(closing_cash="440"))

    issues = CrossStatementValidator().validate(context)

    assert "cash_consistency" in rule_names(issues)
