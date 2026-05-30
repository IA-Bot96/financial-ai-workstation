"""Unit tests for workbook cell mapping."""

import sys
from pathlib import Path

from openpyxl import Workbook

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.models.metric_value import MetricValue
from workbook_population.services.workbook_mapper import WorkbookMapper


def test_workbook_mapper_resolves_metric_year_cell() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Income Statement"
    worksheet.append(["Metric", 2024, 2025])
    worksheet.append(["revenue", None, None])

    mapping = WorkbookMapper().resolve_template_mapping(
        workbook,
        MetricValue(
            metric="revenue",
            value_year=2025,
            value=1500,
            source_report_year=2025,
            page_number=120,
            table_type="income_statement",
        ),
    )

    assert mapping is not None
    assert mapping.sheet_name == "Income Statement"
    assert mapping.row == 2
    assert mapping.column == 3
