"""Unit tests for shared multi-year company context models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_detection_result import DetectedPage, TableDetectionResult
from shared.models.company_context import CompanyContext
from shared.models.report import Report


def _report(year: int) -> Report:
    return Report(
        id=f"rpt_{year}",
        company_name="Maple Leaf Cement Factory Limited",
        year=year,
        file_name=f"MLCF_{year}_Annual_Report.pdf",
        file_path=f"/reports/MLCF_{year}_Annual_Report.pdf",
    )


def test_company_context_accepts_multi_year_results() -> None:
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[_report(2023), _report(2024)],
        table_detection_results={
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=2)
                ],
                total_pages_processed=120,
            )
        },
    )

    assert sorted(report.year for report in context.reports) == [2023, 2024]
    assert list(context.table_detection_results) == [2024]
    assert context.generated_workbook is None


def test_company_context_rejects_result_year_without_report() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CompanyContext(
            company_name="Maple Leaf Cement Factory Limited",
            reports=[_report(2024)],
            table_detection_results={
                2025: TableDetectionResult(
                    detected_pages=[
                        DetectedPage(year=2025, page_number=20, tables_detected=2)
                    ],
                    total_pages_processed=120,
                )
            },
        )

    assert "years not present in reports" in str(exc_info.value)
