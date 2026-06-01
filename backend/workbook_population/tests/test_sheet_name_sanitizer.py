"""Tests for Excel worksheet name sanitization."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from workbook_population.services.sheet_name_sanitizer import sanitize_sheet_name


def test_sanitize_sheet_name_shortens_long_names_readably() -> None:
    assert (
        sanitize_sheet_name("Financial Instruments By Category", set())
        == "Financial Instruments By Cate"
    )
    assert (
        sanitize_sheet_name("Contingent Liabilities And Assets Note", set())
        == "Contingent Liabilities And Ass"
    )


def test_sanitize_sheet_name_removes_invalid_excel_characters() -> None:
    assert sanitize_sheet_name(r"Cash/Bank:*?[Notes]\ ", set()) == "CashBankNotes"


def test_sanitize_sheet_name_prevents_duplicate_names_after_truncation() -> None:
    existing_names = {"Very Long Sheet Name With Same"}

    sanitized = sanitize_sheet_name(
        "Very Long Sheet Name With Same Prefix",
        existing_names,
    )

    assert sanitized == "Very Long Sheet Name With Sam_2"
    assert len(sanitized) <= 31
