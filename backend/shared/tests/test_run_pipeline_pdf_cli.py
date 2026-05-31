"""Tests for PDF-first OCR pipeline CLI helpers."""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from run_pipeline import build_context_from_pdf


def test_build_context_from_pdf_infers_report_metadata(tmp_path: Path) -> None:
    """Build a valid single-report context from only a PDF path."""

    pdf_path = tmp_path / "Maple Leaf Annual Report 2024.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    context = build_context_from_pdf(pdf_path=pdf_path)

    assert context.company_name == "Maple Leaf"
    assert len(context.reports) == 1
    assert context.reports[0].year == 2024
    assert context.reports[0].file_name == "Maple Leaf Annual Report 2024.pdf"
    assert context.reports[0].file_path == str(pdf_path.resolve())
    assert context.reports[0].id == "rpt_2024_maple_leaf_annual_report_2024"


def test_build_context_from_pdf_accepts_explicit_metadata(tmp_path: Path) -> None:
    """Use explicit company and year when the filename is not descriptive."""

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    context = build_context_from_pdf(
        pdf_path=pdf_path,
        report_year=2025,
        company_name="Maple Leaf Cement Factory Limited",
    )

    assert context.company_name == "Maple Leaf Cement Factory Limited"
    assert context.reports[0].company_name == "Maple Leaf Cement Factory Limited"
    assert context.reports[0].year == 2025


def test_build_context_from_pdf_requires_existing_pdf(tmp_path: Path) -> None:
    """Fail fast when the PDF path is wrong."""

    missing_pdf = tmp_path / "missing_2024.pdf"

    try:
        build_context_from_pdf(pdf_path=missing_pdf)
    except FileNotFoundError as exc:
        assert str(missing_pdf.resolve()) in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_build_context_from_pdf_requires_year_when_filename_has_none(
    tmp_path: Path,
) -> None:
    """Require report_year when the PDF filename has no year to infer."""

    pdf_path = tmp_path / "annual_report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    try:
        build_context_from_pdf(pdf_path=pdf_path)
    except ValueError as exc:
        assert "--report-year is required" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
