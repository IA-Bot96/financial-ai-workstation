"""Unit tests for financial statement completeness validation."""

from validation_test_helpers import context_for, extracted_table, rule_names

from ocr_engine.validation.validators.completeness_validator import (
    CompletenessValidator,
)


def test_completeness_validator_accepts_major_sections() -> None:
    context = context_for(
        [
            extracted_table(
                [
                    ["Total assets", "2500"],
                    ["Total liabilities", "1500"],
                    ["Total equity", "1000"],
                ],
                "balance_sheet",
                page_number=1,
                table_index=0,
            ),
            extracted_table(
                [
                    ["Revenue", "1000"],
                    ["Operating expenses", "150"],
                    ["Profit after tax", "150"],
                ],
                "income_statement",
                page_number=2,
                table_index=0,
            ),
            extracted_table(
                [
                    ["Net cash generated from operating activities", "500"],
                    ["Net cash used in investing activities", "(200)"],
                    ["Net cash from financing activities", "100"],
                ],
                "cash_flow_statement",
                page_number=3,
                table_index=0,
            ),
        ]
    )

    issues = CompletenessValidator().validate(context)

    assert issues == []


def test_completeness_validator_flags_missing_cash_flow_sections() -> None:
    context = context_for(
        [
            extracted_table(
                [
                    ["Total assets", "2500"],
                    ["Total liabilities", "1500"],
                    ["Total equity", "1000"],
                ],
                "balance_sheet",
            )
        ]
    )

    issues = CompletenessValidator().validate(context)

    assert "cash_flow_operating_section" in rule_names(issues)
    assert "cash_flow_investing_section" in rule_names(issues)
    assert "cash_flow_financing_section" in rule_names(issues)
