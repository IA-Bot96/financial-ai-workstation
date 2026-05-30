"""Unit tests for ratio validation formulas."""

from validation_test_helpers import context_for, extracted_table, rule_names

from ocr_engine.validation.validators.ratio_validator import RatioValidator


def _ratio_tables(eps: str = "1.5") -> list[object]:
    return [
        extracted_table(
            [["Profit after tax", "150"]],
            "income_statement",
            page_number=1,
            table_index=0,
        ),
        extracted_table(
            [
                ["Current assets", "1000"],
                ["Current liabilities", "500"],
            ],
            "balance_sheet",
            page_number=2,
            table_index=0,
        ),
        extracted_table(
            [
                ["Earnings per share", eps],
                ["Weighted average number of ordinary shares", "100"],
                ["Return on equity", "15%"],
                ["Average equity", "1000"],
                ["Current ratio", "2"],
            ],
            "ratio_analysis",
            page_number=3,
            table_index=0,
        ),
    ]


def test_ratio_validator_accepts_valid_ratios() -> None:
    context = context_for(_ratio_tables())

    issues = RatioValidator().validate(context)

    assert issues == []


def test_ratio_validator_flags_eps_mismatch() -> None:
    context = context_for(_ratio_tables(eps="1.4"))

    issues = RatioValidator().validate(context)

    assert "eps_formula" in rule_names(issues)
