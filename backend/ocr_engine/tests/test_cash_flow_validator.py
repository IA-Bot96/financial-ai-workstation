"""Unit tests for cash flow validation formulas."""

from validation_test_helpers import context_for, extracted_table, rule_names

from ocr_engine.validation.validators.cash_flow_validator import CashFlowValidator


def _cash_flow_rows(closing_cash: str = "450") -> list[list[str]]:
    return [
        ["Net cash generated from operating activities", "500"],
        ["Net cash used in investing activities", "(200)"],
        ["Net cash from financing activities", "100"],
        ["Net change in cash and cash equivalents", "400"],
        ["Cash and cash equivalents at beginning of year", "50"],
        ["Cash and cash equivalents at end of year", closing_cash],
    ]


def test_cash_flow_validator_accepts_valid_cash_flow() -> None:
    context = context_for(
        [extracted_table(_cash_flow_rows(), "cash_flow_statement")]
    )

    issues = CashFlowValidator().validate(context)

    assert issues == []


def test_cash_flow_validator_flags_closing_cash_mismatch() -> None:
    context = context_for(
        [
            extracted_table(
                _cash_flow_rows(closing_cash="440"),
                "cash_flow_statement",
            )
        ]
    )

    issues = CashFlowValidator().validate(context)

    assert "closing_cash_formula" in rule_names(issues)
