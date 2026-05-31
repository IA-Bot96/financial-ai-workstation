"""Tests for dynamic workbook generation."""

import sys
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl import load_workbook

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.insights_extraction import Insight
from shared.models.metric_value import MetricValue
from workbook_population.services.dynamic_workbook_service import DynamicWorkbookService


def test_dynamic_workbook_service_creates_statement_and_insights_sheets(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dynamic.xlsx"

    sheets, metrics_written, warnings = DynamicWorkbookService().generate(
        output_file_path=str(output_path),
        metric_values=[
            MetricValue(
                metric="revenue",
                value_year=2024,
                value=1500,
                source_report_year=2025,
                page_number=120,
                table_type="income_statement",
            ),
            MetricValue(
                metric="cash",
                value_year=2024,
                value=500,
                source_report_year=2025,
                page_number=121,
                table_type="balance_sheet",
            ),
            MetricValue(
                metric="long_term_debt",
                value_year=2024,
                value=300,
                source_report_year=2025,
                page_number=122,
                table_type="debt_schedule",
            ),
        ],
        insights=[
            Insight(
                value_year=2024,
                source_report_year=2025,
                area="Debt",
                takeaway="Borrowings increased.",
                source_section="Business Review",
                page_number=84,
                confidence=0.9,
            )
        ],
    )

    workbook = load_workbook(output_path)
    assert workbook.sheetnames == [
        "Income Statement",
        "Balance Sheet",
        "Debt Schedule",
        "Insights",
    ]
    assert workbook["Income Statement"]["A2"].value == "revenue"
    assert workbook["Income Statement"]["B2"].value == 1500
    assert workbook["Balance Sheet"]["A2"].value == "cash"
    assert workbook["Debt Schedule"]["A2"].value == "long_term_debt"
    assert workbook["Insights"]["C2"].value == "Debt"
    assert metrics_written == 3
    assert warnings == []
    assert sheets == workbook.sheetnames
    workbook.close()


def test_dynamic_workbook_preserves_duplicate_metrics_across_table_types(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dynamic.xlsx"

    sheets, metrics_written, warnings = DynamicWorkbookService().generate(
        output_file_path=str(output_path),
        metric_values=[
            MetricValue(
                metric="revenue",
                value_year=2024,
                value=1500,
                source_report_year=2025,
                page_number=120,
                table_type="income_statement",
            ),
            MetricValue(
                metric="revenue",
                value_year=2024,
                value=220,
                source_report_year=2025,
                page_number=121,
                table_type="segment_information",
            ),
        ],
        insights=[],
    )

    workbook = load_workbook(output_path)
    assert workbook["Income Statement"]["A2"].value == "revenue"
    assert workbook["Income Statement"]["B2"].value == 1500
    assert workbook["Segment Information"]["A2"].value == "revenue"
    assert workbook["Segment Information"]["B2"].value == 220
    assert metrics_written == 2
    assert warnings == []
    assert sheets == ["Income Statement", "Segment Information"]
    workbook.close()


def test_dynamic_workbook_reports_permission_save_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_permission_error(self: Workbook, filename: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(Workbook, "save", raise_permission_error)

    with pytest.raises(PermissionError, match="Close the Excel file"):
        DynamicWorkbookService().generate(
            output_file_path=str(tmp_path / "locked.xlsx"),
            metric_values=[],
            insights=[],
        )
