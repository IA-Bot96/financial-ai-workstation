"""Unit tests for OCR validation rules."""

from validation_test_helpers import context_for, extracted_table, rule_names

from ocr_engine.validation.validators.ocr_validator import OCRValidator


def test_ocr_validator_flags_duplicate_rows_and_year_ordering() -> None:
    context = context_for(
        [
            extracted_table(
                [
                    ["Particulars", "2023", "2024"],
                    ["Revenue", "1000"],
                    ["Revenue", "1000"],
                    ["Profit after tax", "150"],
                ],
                "income_statement",
                page_number=1,
                table_index=0,
            ),
            extracted_table(
                [
                    ["Total assets", "2500"],
                    ["Total liabilities", "1500"],
                    ["Total equity", "1000"],
                ],
                "balance_sheet",
                page_number=2,
                table_index=0,
            ),
        ]
    )

    issues = OCRValidator().validate(context)

    assert "duplicate_rows" in rule_names(issues)
    assert "year_ordering" in rule_names(issues)


def test_ocr_validator_flags_missing_critical_metric_and_negative_value() -> None:
    context = context_for(
        [
            extracted_table(
                [["Revenue", "(1000)"]],
                "income_statement",
            )
        ]
    )

    issues = OCRValidator().validate(context)

    assert "missing_critical_metric" in rule_names(issues)
    assert "invalid_negative_value" in rule_names(issues)
