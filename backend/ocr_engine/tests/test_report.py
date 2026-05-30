"""Unit tests for the shared report model."""

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
        company_name="Maple Leaf Cement Factory Limited",
        year=2024,
        file_name="MLCF_2024_Annual_Report.pdf",
        file_path="/reports/MLCF_2024_Annual_Report.pdf",
    )

    assert report.model_dump() == {
        "id": "rpt_001",
        "company_name": "Maple Leaf Cement Factory Limited",
        "year": 2024,
        "file_name": "MLCF_2024_Annual_Report.pdf",
        "file_path": "/reports/MLCF_2024_Annual_Report.pdf",
    }


@pytest.mark.parametrize("field_name", ["company_name", "file_name", "file_path"])
def test_report_requires_non_empty_text_fields(field_name: str) -> None:
    payload = {
        "id": "rpt_001",
        "company_name": "Maple Leaf Cement Factory Limited",
        "year": 2024,
        "file_name": "MLCF_2024_Annual_Report.pdf",
        "file_path": "/reports/MLCF_2024_Annual_Report.pdf",
    }
    payload[field_name] = ""

    with pytest.raises(ValidationError) as exc_info:
        Report(**payload)

    assert exc_info.value.errors()[0]["type"] == "string_too_short"


def test_report_requires_year_at_or_after_1900() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Report(
            id="rpt_001",
            company_name="Maple Leaf Cement Factory Limited",
            year=1899,
            file_name="MLCF_1899_Annual_Report.pdf",
            file_path="/reports/MLCF_1899_Annual_Report.pdf",
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than_equal"


def test_report_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Report(
            id="rpt_001",
            company_name="Maple Leaf Cement Factory Limited",
            year=2024,
            file_name="MLCF_2024_Annual_Report.pdf",
            file_path="/reports/MLCF_2024_Annual_Report.pdf",
            uploaded_by="analyst",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
