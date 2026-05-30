"""Unit tests for the report model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.report import Report


def test_report_accepts_valid_payload() -> None:
    report = Report(
        id="rpt_001",
        file_name="MLCF_2024_Annual_Report.pdf",
        company="Maple Leaf Cement Factory Limited",
        year=2024,
    )

    assert report.model_dump() == {
        "id": "rpt_001",
        "file_name": "MLCF_2024_Annual_Report.pdf",
        "company": "Maple Leaf Cement Factory Limited",
        "year": 2024,
    }


def test_report_allows_unknown_company_and_year() -> None:
    report = Report(
        id="rpt_002",
        file_name="Annual_Report.pdf",
        company=None,
        year=None,
    )

    assert report.company is None
    assert report.year is None


def test_report_requires_year_after_1900_when_provided() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Report(
            id="rpt_001",
            file_name="MLCF_1900_Annual_Report.pdf",
            company="Maple Leaf Cement Factory Limited",
            year=1900,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


def test_report_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Report(
            id="rpt_001",
            file_name="MLCF_2024_Annual_Report.pdf",
            company="Maple Leaf Cement Factory Limited",
            year=2024,
            uploaded_by="analyst",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
