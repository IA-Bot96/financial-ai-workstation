"""Unit tests for the Camelot table extractor service."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_detection_result import (
    DetectedPage,
    TableDetectionResult,
)
import ocr_engine.services.camelot_table_extractor as extractor_module
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.camelot_table_extractor import CamelotTableExtractor
from ocr_engine.services.interfaces.table_extractor import ITableExtractor
from ocr_engine.services.table_metric_normalizer import TableMetricNormalizer
from shared.models.company_context import CompanyContext
from shared.models.report import Report
from shared.normalization.interfaces.metric_normalizer import IMetricNormalizer
from shared.normalization.models.normalized_metric import NormalizedMetric
from shared.services.financial_year_consolidator import FinancialYearConsolidator
from workbook_population.services.workbook_population_service import (
    OpenPyXLWorkbookPopulationService,
)


class FakeValues:
    def __init__(self, rows: list[list[object]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[object]]:
        return self._rows


class FakeDataFrame:
    def __init__(self, rows: list[list[object]]) -> None:
        self.values = FakeValues(rows)


class FakeCamelotTable:
    def __init__(self, rows: list[list[object]]) -> None:
        self.df = FakeDataFrame(rows)


class FakePdfplumberPage:
    def __init__(
        self,
        tables: list[list[list[object]]],
        text_tables: list[list[list[object]]] | None = None,
    ) -> None:
        self._tables = tables
        self._text_tables = text_tables

    def extract_tables(
        self,
        table_settings: dict[str, str] | None = None,
    ) -> list[list[list[object]]]:
        if table_settings is not None and self._text_tables is not None:
            return self._text_tables
        return self._tables


class FakePdfplumberDocument:
    def __init__(self, pages: list[FakePdfplumberPage]) -> None:
        self.pages = pages

    def __enter__(self) -> "FakePdfplumberDocument":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeMetricNormalizer(IMetricNormalizer):
    def normalize_metric(self, metric_name: str) -> NormalizedMetric:
        lookup = {
            "Revenue": "revenue",
            "Cash": "cash",
        }
        normalized_metric = lookup.get(metric_name, metric_name)
        return NormalizedMetric(
            original_metric=metric_name,
            normalized_metric=normalized_metric,
            confidence=0.96,
            requires_review=False,
        )


def _classification_result() -> FinancialTableClassificationResult:
    return FinancialTableClassificationResult(
        page_table_types=[
            PageTableType(
                year=2024,
                page_number=20,
                table_types=["balance_sheet", "debt_schedule"],
            )
        ]
    )


def test_camelot_table_extractor_implements_interface() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    assert isinstance(extractor, ITableExtractor)


def test_extract_tables_uses_camelot_first() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([[" Cash ", 1000], ["Inventory", None]]),
            FakeCamelotTable([["Debt", " 450 "]]),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=_classification_result(),
    )

    assert result.model_dump(exclude={"extraction_summary"}) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "balance_sheet",
                "table_index": 0,
                "source_table_index": 0,
                "split_table_index": None,
                "split_reason": None,
                "rows": [["Cash", "1000"], ["Inventory", ""]],
                "metric_values": [],
            },
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "debt_schedule",
                "table_index": 1,
                "source_table_index": 1,
                "split_table_index": None,
                "split_reason": None,
                "rows": [["Debt", "450"]],
                "metric_values": [],
            },
        ],
        "metric_values": [],
    }


def test_extract_tables_identifies_metric_value_years() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025", "2024"],
                    ["Revenue", "100", "80"],
                    ["Debt", "45", "50"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=120,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    assert [
        (
            metric_value.metric,
            metric_value.value_year,
            metric_value.value,
            metric_value.source_report_year,
        )
        for metric_value in result.metric_values
    ] == [
        ("Revenue", 2025, 100, 2025),
        ("Revenue", 2024, 80, 2025),
        ("Debt", 2025, 45, 2025),
        ("Debt", 2024, 50, 2025),
    ]


def test_extract_tables_reconstructs_fragmented_metric_labels() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "", "", "", "", "2025", "2024"],
                    [
                        "Fair value reserve - In",
                        "vestments",
                        "measured",
                        "at FVOCI",
                        "",
                        "1,674",
                        "1,769",
                    ],
                    ["Long term i", "nvestments", "", "", "", "5,874", "6,028"],
                    ["Bank Al Ha", "bib", "A1+", "AAA", "PACRA", "312", "1,485"],
                    ["Fair value of plan a", "ssets", "", "", "", "25,642", "27,283"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=225,
                    table_types=["balance_sheet"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Fair value reserve - Investments measured at FVOCI", 2025, 1674),
        ("Fair value reserve - Investments measured at FVOCI", 2024, 1769),
        ("Long term investments", 2025, 5874),
        ("Long term investments", 2024, 6028),
        ("Bank Al Habib", 2025, 312),
        ("Bank Al Habib", 2024, 1485),
        ("Fair value of plan assets", 2025, 25642),
        ("Fair value of plan assets", 2024, 27283),
    ]

    quality_report = result.extraction_summary.quality_report
    assert quality_report.labels_reconstructed == 4
    assert quality_report.metric_values_improved_by_label_reconstruction == 8
    assert [
        (
            diagnostic.original_label,
            diagnostic.reconstructed_label,
            diagnostic.stop_reason,
        )
        for diagnostic in quality_report.label_reconstruction_diagnostics
    ] == [
        (
            "Fair value reserve - In",
            "Fair value reserve - Investments measured at FVOCI",
            "year_column",
        ),
        ("Long term i", "Long term investments", "year_column"),
        ("Bank Al Ha", "Bank Al Habib", "rating"),
        ("Fair value of plan a", "Fair value of plan assets", "year_column"),
    ]
    assert all(
        diagnostic.reconstruction_confidence >= 0.9
        for diagnostic in quality_report.label_reconstruction_diagnostics
    )


def test_label_reconstruction_stops_before_note_and_percentage_columns() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "Note", "Change", "2025", "2024"],
                    ["Revenue from contracts", "28.1", "", "100", "80"],
                    ["Bank balances", "+5%", "", "19,428", "24,830"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=267,
                    table_types=["notes"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Revenue from contracts", 2025, 100),
        ("Revenue from contracts", 2024, 80),
        ("Bank balances", 2025, 19428),
        ("Bank balances", 2024, 24830),
    ]
    assert result.extraction_summary.quality_report.labels_reconstructed == 0


def test_extract_tables_deglues_lucky_and_millat_label_fragments() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025", "2024"],
                    ["Current Asse ts", "100", "80"],
                    ["Current Liabi lities", "45", "50"],
                    ["Distribution Co st", "11", "9"],
                    ["Operating Pro fit", "30", "25"],
                    ["Loans to e mployees", "5", "4"],
                    ["Cash and b ank balances", "19", "24"],
                    ["Trade and o ther payables", "7", "8"],
                    ["Salaries and amenitie s", "3", "2"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=164,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Current Assets", 2025, 100),
        ("Current Assets", 2024, 80),
        ("Current Liabilities", 2025, 45),
        ("Current Liabilities", 2024, 50),
        ("Distribution Cost", 2025, 11),
        ("Distribution Cost", 2024, 9),
        ("Operating Profit", 2025, 30),
        ("Operating Profit", 2024, 25),
        ("Loans to employees", 2025, 5),
        ("Loans to employees", 2024, 4),
        ("Cash and bank balances", 2025, 19),
        ("Cash and bank balances", 2024, 24),
        ("Trade and other payables", 2025, 7),
        ("Trade and other payables", 2024, 8),
        ("Salaries and amenities", 2025, 3),
        ("Salaries and amenities", 2024, 2),
    ]

    quality_report = result.extraction_summary.quality_report
    assert quality_report.labels_deglued == 8
    assert quality_report.metric_values_improved_by_label_degluing == 16
    assert [
        (diagnostic.original_label, diagnostic.deglued_label)
        for diagnostic in quality_report.label_degluing_diagnostics
    ] == [
        ("Current Asse ts", "Current Assets"),
        ("Current Liabi lities", "Current Liabilities"),
        ("Distribution Co st", "Distribution Cost"),
        ("Operating Pro fit", "Operating Profit"),
        ("Loans to e mployees", "Loans to employees"),
        ("Cash and b ank balances", "Cash and bank balances"),
        ("Trade and o ther payables", "Trade and other payables"),
        ("Salaries and amenitie s", "Salaries and amenities"),
    ]


def test_label_degluing_preserves_non_label_tokens() -> None:
    deglued = extractor_module._deglue_label_text("Note 28.1 2025 A1+ +5% PKR 10")

    assert deglued.deglued_label == "Note 28.1 2025 A1+ +5% PKR 10"
    assert deglued.rules_applied == ()


def test_extract_tables_completes_remaining_fragmented_lucky_labels() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "", "2025", "2024"],
                    ["(Other Income)/Charg es", "", "100", "80"],
                    ["Property, plant a nd equipment", "", "200", "180"],
                    ["Cash flow Coverage ra tio times", "", "3", "2"],
                    ["Net assets (100", "%)", "50", "40"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=164,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("(Other Income)/Charges", 2025, 100),
        ("(Other Income)/Charges", 2024, 80),
        ("Property, plant and equipment", 2025, 200),
        ("Property, plant and equipment", 2024, 180),
        ("Cash flow Coverage ratio times", 2025, 3),
        ("Cash flow Coverage ratio times", 2024, 2),
        ("Net assets (100%)", 2025, 50),
        ("Net assets (100%)", 2024, 40),
    ]

    quality_report = result.extraction_summary.quality_report
    assert quality_report.labels_completed == 4
    assert quality_report.metric_values_improved_by_fragmentation_cleanup == 8
    assert [
        (
            diagnostic.original_label,
            diagnostic.completed_label,
            diagnostic.reconstruction_reason,
            diagnostic.completion_source,
        )
        for diagnostic in quality_report.fragmentation_cleanup_diagnostics
    ] == [
        (
            "(Other Income)/Charg es",
            "(Other Income)/Charges",
            "remaining_spacing_repair",
            "spacing_repair",
        ),
        (
            "Property, plant a nd equipment",
            "Property, plant and equipment",
            "remaining_spacing_repair",
            "spacing_repair",
        ),
        (
            "Cash flow Coverage ra tio times",
            "Cash flow Coverage ratio times",
            "remaining_spacing_repair",
            "spacing_repair",
        ),
        (
            "Net assets (100",
            "Net assets (100%)",
            "unit_context_completion",
            "adjacent_unit_cell",
        ),
    ]
    assert quality_report.fragmentation_cleanup_diagnostics[3].source_cells == [
        "Net assets (100",
        "%)",
    ]


def test_extract_tables_filters_non_metric_note_rows_before_metric_values() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025", "2024"],
                    ["Note", "1", "2"],
                    ["(PKR in '00", "3", "4"],
                    ["----do----", "5", "6"],
                    ["Note 28.1", "7", "8"],
                    ["continued", "9", "10"],
                    ["Managerial remuneration", "11", "12"],
                    ["Number of persons", "13", "14"],
                    ["ordinary shares of PKR 10 each", "15", "16"],
                    ["Total", "17", "18"],
                    ["Year High Close Rupees", "19", "20"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=353,
                    table_types=["notes"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Managerial remuneration", 2025, 11),
        ("Managerial remuneration", 2024, 12),
        ("Managerial remuneration - Number of persons", 2025, 13),
        ("Managerial remuneration - Number of persons", 2024, 14),
        ("ordinary shares of PKR 10 each", 2025, 15),
        ("ordinary shares of PKR 10 each", 2024, 16),
        ("Total", 2025, 17),
        ("Total", 2024, 18),
        ("Year High Close Rupees", 2025, 19),
        ("Year High Close Rupees", 2024, 20),
    ]

    quality_report = result.extraction_summary.quality_report
    assert quality_report.note_rows_filtered == 5
    assert quality_report.metric_values_removed_by_note_row_filtering == 10
    assert [
        (diagnostic.label, diagnostic.filtering_reason)
        for diagnostic in quality_report.note_row_filtering_diagnostics
    ] == [
        ("Note", "note_header"),
        ("(PKR in '00", "unit_row"),
        ("----do----", "continuation_marker"),
        ("Note 28.1", "standalone_note_reference"),
        ("continued", "continuation_marker"),
    ]


def test_extract_tables_inherits_note_context_for_generic_labels() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025", "2024"],
                    ["Capital work-in-progress", "", ""],
                    ["Opening balance", "100", "80"],
                    ["Closing balance", "120", "100"],
                    ["Other expenses", "", ""],
                    ["Others", "5", "4"],
                    ["Cash and b ank balances", "30", "28"],
                    ["Managerial remuneration", "", ""],
                    ["Number of persons", "3", "2"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=321,
                    table_types=["notes"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Capital work-in-progress - Opening balance", 2025, 100),
        ("Capital work-in-progress - Opening balance", 2024, 80),
        ("Capital work-in-progress - Closing balance", 2025, 120),
        ("Capital work-in-progress - Closing balance", 2024, 100),
        ("Other expenses - Others", 2025, 5),
        ("Other expenses - Others", 2024, 4),
        ("Cash and bank balances", 2025, 30),
        ("Cash and bank balances", 2024, 28),
        ("Managerial remuneration - Number of persons", 2025, 3),
        ("Managerial remuneration - Number of persons", 2024, 2),
    ]

    quality_report = result.extraction_summary.quality_report
    assert quality_report.context_inheritances_applied == 4
    assert quality_report.metric_values_improved_by_context_inheritance == 8
    assert [
        (
            diagnostic.original_label,
            diagnostic.inherited_context,
            diagnostic.context_source,
            diagnostic.reconstruction_reason,
            diagnostic.inherited_label,
        )
        for diagnostic in quality_report.note_context_inheritance_diagnostics
    ] == [
        (
            "Opening balance",
            "Capital work-in-progress",
            "section_header",
            "movement_label",
            "Capital work-in-progress - Opening balance",
        ),
        (
            "Closing balance",
            "Capital work-in-progress",
            "section_header",
            "movement_label",
            "Capital work-in-progress - Closing balance",
        ),
        (
            "Others",
            "Other expenses",
            "section_header",
            "generic_note_label",
            "Other expenses - Others",
        ),
        (
            "Number of persons",
            "Managerial remuneration",
            "section_header",
            "short_disclosure_label",
            "Managerial remuneration - Number of persons",
        ),
    ]


def test_extract_tables_inherits_header_context_for_fragmented_labels() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "", "", "2025", "2024"],
                    ["except EPS", "", "", "", ""],
                    ["GP as % of Net", "", "", "34%", "35%"],
                    ["Long-term liabilities", "", "", "", ""],
                    ["Current portion", "of long ter", "m finance", "127", "507"],
                    ["Lucky Holdings Limited", "", "", "", ""],
                    ["ordinary shares o", "f PKR 10 each", "", "32,145", "32,145"],
                    [
                        "The Group's interest in LRHL's assets and liabilities",
                        "is as follows:",
                        "",
                        "",
                        "",
                    ],
                    ["Net assets (100", "%)", "", "81,312", "66,460"],
                    ["Non-Financial Ratios", "", "", "", ""],
                    ["% of Plant Availability", "", "", "76.42%", "89.63%"],
                    ["Investment at cost", "", "", "6,870", "3,399"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=321,
                    table_types=["investment_valuation_ratios"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("GP as % of Net", 2025, 34),
        ("GP as % of Net", 2024, 35),
        (
            "Long-term liabilities - Current portion of long term finance",
            2025,
            127,
        ),
        (
            "Long-term liabilities - Current portion of long term finance",
            2024,
            507,
        ),
        (
            "Lucky Holdings Limited - ordinary shares of PKR 10 each",
            2025,
            32145,
        ),
        (
            "Lucky Holdings Limited - ordinary shares of PKR 10 each",
            2024,
            32145,
        ),
        ("Net assets (100%)", 2025, 81312),
        ("Net assets (100%)", 2024, 66460),
        (
            "Non-Financial Ratios - % of Plant Availability",
            2025,
            76.42,
        ),
        (
            "Non-Financial Ratios - % of Plant Availability",
            2024,
            89.63,
        ),
        ("Non-Financial Ratios - Investment at cost", 2025, 6870),
        ("Non-Financial Ratios - Investment at cost", 2024, 3399),
    ]

    quality_report = result.extraction_summary.quality_report
    assert quality_report.header_inheritances_applied == 4
    assert quality_report.metric_values_improved_by_header_inheritance == 8
    assert quality_report.labels_completed == 1
    assert quality_report.metric_values_improved_by_fragmentation_cleanup == 2
    assert [
        (
            diagnostic.original_label,
            diagnostic.completed_label,
            diagnostic.reconstruction_reason,
            diagnostic.completion_source,
        )
        for diagnostic in quality_report.fragmentation_cleanup_diagnostics
    ] == [
        (
            "Net assets (100",
            "Net assets (100%)",
            "unit_context_completion",
            "adjacent_unit_cell",
        )
    ]
    assert [
        (
            diagnostic.original_label,
            diagnostic.inherited_header,
            diagnostic.inheritance_source,
            diagnostic.reconstruction_reason,
            diagnostic.inherited_label,
        )
        for diagnostic in quality_report.header_inheritance_diagnostics
    ] == [
        (
            "Current portion of long term finance",
            "Long-term liabilities",
            "table_section_context",
            "section_context_inheritance",
            "Long-term liabilities - Current portion of long term finance",
        ),
        (
            "ordinary shares of PKR 10 each",
            "Lucky Holdings Limited",
            "table_header_context",
            "security_header_inheritance",
            "Lucky Holdings Limited - ordinary shares of PKR 10 each",
        ),
        (
            "% of Plant Availability",
            "Non-Financial Ratios",
            "table_section_context",
            "unit_context_inheritance",
            "Non-Financial Ratios - % of Plant Availability",
        ),
        (
            "Investment at cost",
            "Non-Financial Ratios",
            "table_section_context",
            "table_header_inheritance",
            "Non-Financial Ratios - Investment at cost",
        ),
    ]


def test_extract_tables_applies_financial_scale_conversion() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Rupees in thousand"],
                    ["Metric", "2025"],
                    ["Revenue", "1.5"],
                ]
            ),
            FakeCamelotTable(
                [
                    ["Amounts in million"],
                    ["Metric", "2025"],
                    ["EBITDA", "2"],
                ]
            ),
            FakeCamelotTable(
                [
                    ["USD in billion"],
                    ["Metric", "2025"],
                    ["Debt", "3"],
                ]
            ),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=120,
                    table_types=[
                        "income_statement",
                        "income_statement",
                        "debt_schedule",
                    ],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Revenue", 1500),
        ("EBITDA", 2_000_000),
        ("Debt", 3_000_000_000),
    ]


def test_extract_tables_parses_accounting_negatives_only_when_numeric() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2024"],
                    ["Profit", "(1,250)"],
                    ["Expense", "-25"],
                    ["Restated value", "(Restated) 100"],
                    ["Disclosure", "Note 12"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2024,
                    page_number=20,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    assert [
        (metric_value.metric, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Profit", -1250),
        ("Expense", -25),
    ]


def test_extract_tables_logs_type_count_mismatch_and_preserves_extra_tables(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Cash", "1000"]]),
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "500"]]),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet"],
                    )
                ]
            ),
        )

    assert len(result.tables) == 2
    assert result.tables[0].table_type == "balance_sheet"
    assert result.tables[0].rows == [["Metric", "2024"], ["Cash", "1000"]]
    assert result.tables[1].table_type == "unclassified_table"
    assert result.tables[1].rows == [["Metric", "2024"], ["Revenue", "500"]]
    assert result.metric_values[0].metric == "Cash"
    assert result.metric_values[1].metric == "Revenue"
    assert "Table count and classification type count mismatch" in caplog.text
    assert "could not be matched to a classified table type" in caplog.text


def test_extract_tables_corrects_classification_ordering_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "1000"]]),
            FakeCamelotTable([["Metric", "2024"], ["Cash", "600"]]),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet", "income_statement"],
                    )
                ]
            ),
        )

    assert [
        (table.table_index, table.table_type, table.rows[1][0])
        for table in result.tables
    ] == [
        (0, "income_statement", "Revenue"),
        (1, "balance_sheet", "Cash"),
    ]
    assert "Table classification ordering mismatch corrected" in caplog.text


def test_extract_tables_logs_extra_classified_tables(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Cash", "1000"]]),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet", "income_statement"],
                    )
                ]
            ),
        )

    assert len(result.tables) == 1
    assert result.tables[0].table_type == "balance_sheet"
    assert "Table count and classification type count mismatch" in caplog.text
    assert "Classified table type did not match an extracted table" in caplog.text


def test_extract_tables_splits_balance_sheet_analysis_table() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["PKR in '000", "2020", "2021"],
                    ["Share Capital & Reserves", "100", "110"],
                    ["Total Assets", "200", "220"],
                    ["Vertical Analysis - (%)", "2020", "2021"],
                    ["Share Capital & Reserves", "50", "50"],
                    ["Total Assets", "100", "100"],
                    ["Horizontal Analysis", "2020", "2021"],
                    ["Share Capital & Reserves", "10", "20"],
                    ["Total Assets", "0", "10"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=163,
                    table_types=[
                        "balance_sheet",
                        "vertical_analysis",
                        "horizontal_analysis",
                    ],
                )
            ]
        ),
        table_detection_result=TableDetectionResult(
            detected_pages=[
                DetectedPage(year=2025, page_number=163, tables_detected=1),
            ],
            total_pages_processed=400,
        ),
    )

    assert [table.table_type for table in result.tables] == [
        "balance_sheet",
        "vertical_analysis",
        "horizontal_analysis",
    ]
    assert [
        (table.table_index, table.source_table_index, table.split_table_index)
        for table in result.tables
    ] == [(0, 0, 0), (1, 0, 1), (2, 0, 2)]
    assert result.extraction_summary.total_extracted_tables == 3
    assert result.extraction_summary.total_matched_tables == 3
    assert result.extraction_summary.unmatched_classifications == []
    assert result.extraction_summary.tables_split == 2
    assert result.extraction_summary.logical_types_created == [
        "balance_sheet",
        "vertical_analysis",
        "horizontal_analysis",
    ]
    assert result.extraction_summary.split_reasons == [
        "analysis_section_markers_with_repeated_year_headers_and_subtotal_rows"
    ]
    assert result.extraction_summary.page_diagnostics[0].tables_split == 2
    assert len(result.metric_values) == 12


def test_extract_tables_splits_income_statement_analysis_table() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["OF", "PROFIT", "OR", "LOSS"],
                    ["PKR in '000", "2020", "2021"],
                    ["Turnover", "1000", "1100"],
                    ["Gross Profit", "300", "350"],
                    ["Profit after taxation", "120", "150"],
                    ["Vertical Analysis - (%)", "2020", "2021"],
                    ["Turnover", "100", "100"],
                    ["Gross Profit", "30", "32"],
                    ["Profit after taxation", "12", "14"],
                    ["Horizontal Analysis", "2020", "2021"],
                    ["Turnover", "0", "10"],
                    ["Gross Profit", "0", "16.7"],
                    ["Profit after taxation", "0", "25"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=164,
                    table_types=[
                        "income_statement",
                        "vertical_analysis",
                        "horizontal_analysis",
                    ],
                )
            ]
        ),
    )

    assert [table.table_type for table in result.tables] == [
        "income_statement",
        "vertical_analysis",
        "horizontal_analysis",
    ]
    assert all(table.source_table_index == 0 for table in result.tables)
    assert [table.split_table_index for table in result.tables] == [0, 1, 2]
    assert result.extraction_summary.total_matched_tables == 3
    assert result.extraction_summary.unmatched_classifications == []
    assert result.extraction_summary.tables_split == 2
    assert len(result.metric_values) == 18


def test_extract_tables_reports_page_diagnostics_from_detection_to_extraction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "1000"]]),
            FakeCamelotTable([["Metric", "2024"], ["Unmapped Disclosure", "9"]]),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    with caplog.at_level(logging.INFO):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement"],
                    )
                ]
            ),
            table_detection_result=TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=2),
                ],
                total_pages_processed=100,
            ),
        )

    summary = result.extraction_summary
    assert summary.total_detected_tables == 2
    assert summary.total_classified_tables == 1
    assert summary.total_extracted_tables == 2
    assert summary.total_matched_tables == 1
    assert summary.unmatched_extractions == ["page=20 table_index=1"]
    assert summary.unmatched_classifications == []
    assert summary.page_diagnostics[0].model_dump() == {
        "source_report_year": 2024,
        "page_number": 20,
        "detected_table_count": 2,
        "classified_table_count": 1,
        "extracted_table_count": 2,
        "matched_table_count": 1,
        "extraction_strategy": "full_page_camelot",
        "quality_score": 57.0,
        "year_column_count": 2,
        "metric_label_count": 4,
        "metric_value_count": 2,
        "numeric_only_table_count": 0,
        "unmatched_classifications": [],
        "unmatched_extractions": [1],
        "tables_split": 0,
        "split_reason": None,
        "logical_types_created": [],
    }
    assert "Extraction page diagnostics" in caplog.text


def test_extract_tables_for_context_fails_when_no_tables_match() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Unmapped Disclosure", "9"]]),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
        classification_results={
            2024: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement", "balance_sheet"],
                    )
                ]
            )
        },
        table_detection_results={
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=2),
                ],
                total_pages_processed=100,
            )
        },
    )

    with pytest.raises(PipelineLayerPartialFailure, match="no matched tables"):
        extractor.extract_tables_for_context(context)

    summary = context.extraction_results[2024].extraction_summary
    assert summary.total_detected_tables == 2
    assert summary.total_classified_tables == 2
    assert summary.total_extracted_tables == 1
    assert summary.total_matched_tables == 0


def test_extract_tables_for_context_stores_results_by_report_year() -> None:
    def camelot_reader(pdf_path: str, pages: str) -> list[FakeCamelotTable]:
        raw_tables_by_page = {
            ("reports/MLCF_2023.pdf", "10"): [
                FakeCamelotTable([["Cash", "800"]]),
            ],
            ("reports/MLCF_2024.pdf", "20"): [
                FakeCamelotTable([["Cash", "1000"]]),
                FakeCamelotTable([["Debt", "450"]]),
            ],
        }
        return raw_tables_by_page[(pdf_path, pages)]

    extractor = CamelotTableExtractor(
        camelot_reader=camelot_reader,
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2023_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2023,
                file_name="MLCF_2023_Annual_Report.pdf",
                file_path="reports/MLCF_2023.pdf",
            ),
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            ),
        ],
        classification_results={
            2023: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2023,
                        page_number=10,
                        table_types=["balance_sheet"],
                    ),
                ]
            ),
            2024: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet", "debt_schedule"],
                    ),
                ]
            ),
        },
        table_detection_results={
            2023: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2023, page_number=10, tables_detected=1),
                ],
                total_pages_processed=100,
            ),
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=2),
                ],
                total_pages_processed=132,
            ),
        },
    )

    updated_context = extractor.extract_tables_for_context(context)

    assert updated_context is context
    assert set(context.extraction_results) == {2023, 2024}
    assert context.extraction_results[2023].model_dump(
        exclude={"extraction_summary"}
    ) == {
        "tables": [
            {
                "source_report_year": 2023,
                "page_number": 10,
                "table_type": "balance_sheet",
                "table_index": 0,
                "source_table_index": 0,
                "split_table_index": None,
                "split_reason": None,
                "rows": [["Cash", "800"]],
                "metric_values": [],
            }
        ],
        "metric_values": [],
    }
    assert context.extraction_results[2024].model_dump(
        exclude={"extraction_summary"}
    ) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "balance_sheet",
                "table_index": 0,
                "source_table_index": 0,
                "split_table_index": None,
                "split_reason": None,
                "rows": [["Cash", "1000"]],
                "metric_values": [],
            },
            {
                "source_report_year": 2024,
                "page_number": 20,
                "table_type": "debt_schedule",
                "table_index": 1,
                "source_table_index": 1,
                "split_table_index": None,
                "split_reason": None,
                "rows": [["Debt", "450"]],
                "metric_values": [],
            },
        ],
        "metric_values": [],
    }
    assert context.extraction_results[2023] is not context.extraction_results[2024]


def test_extract_tables_for_context_isolates_year_failures() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Metric", "2024"], ["Revenue", "1000"]])
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2023_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2023,
                file_name="MLCF_2023_Annual_Report.pdf",
                file_path="reports/MLCF_2023.pdf",
            ),
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
        classification_results={
            2024: FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["income_statement"],
                    )
                ]
            )
        },
        table_detection_results={
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=1),
                ],
                total_pages_processed=132,
            )
        },
    )

    with pytest.raises(PipelineLayerPartialFailure) as exc_info:
        extractor.extract_tables_for_context(context)

    assert exc_info.value.context is context
    assert set(context.extraction_results) == {2023, 2024}
    assert context.extraction_results[2023].model_dump(
        exclude={"extraction_summary"}
    ) == {
        "tables": [],
        "metric_values": [],
    }
    assert context.extraction_results[2024].metric_values[0].metric == "Revenue"
    assert "Report year 2023 failed table extraction" in (
        exc_info.value.error_messages[0]
    )
    assert context.pipeline_errors == []


def test_extract_tables_falls_back_to_pdfplumber_when_camelot_returns_no_tables(
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [],
        pdfplumber_open=lambda _: FakePdfplumberDocument(
            [
                FakePdfplumberPage(
                    [
                        [[" Cash ", "1000"], ["Inventory", None]],
                    ]
                )
            ]
        ),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2024,
                    page_number=1,
                    table_types=["balance_sheet"],
                )
            ]
        ),
    )

    assert result.model_dump(exclude={"extraction_summary"}) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 1,
                "table_type": "balance_sheet",
                "table_index": 0,
                "source_table_index": 0,
                "split_table_index": None,
                "split_reason": None,
                "rows": [["Cash", "1000"], ["Inventory", ""]],
                "metric_values": [],
            }
        ],
        "metric_values": [],
    }


def test_extract_tables_uses_pdfplumber_text_when_default_loses_financial_structure(
) -> None:
    numeric_fragments = [
        [["1,674,225", "", "1,769,093"], ["951,736"]],
    ]
    text_mode_tables = [
        [
            ["Restated", "2025", "2024"],
            ["Capital reserve", "1,674,225", "1,769,093"],
            [
                "Fair value reserve - Investments measured at FVOCI",
                "1,674,225",
                "1,769,093",
            ],
            ["Long term loan", "951,736", "1,438,764"],
        ]
    ]

    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [],
        pdfplumber_open=lambda _: FakePdfplumberDocument(
            [
                FakePdfplumberPage(
                    numeric_fragments,
                    text_tables=text_mode_tables,
                )
            ]
        ),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=1,
                    table_types=["debt_schedule"],
                )
            ]
        ),
    )

    diagnostic = result.extraction_summary.page_diagnostics[0]
    assert diagnostic.extraction_strategy == "full_page_pdfplumber_text"
    assert diagnostic.year_column_count == 2
    assert diagnostic.metric_label_count == 4
    assert diagnostic.metric_value_count == 6
    assert diagnostic.numeric_only_table_count == 0
    assert [
        (metric_value.metric, metric_value.value_year, metric_value.value)
        for metric_value in result.metric_values
    ] == [
        ("Capital reserve", 2025, 1_674_225),
        ("Capital reserve", 2024, 1_769_093),
        (
            "Fair value reserve - Investments measured at FVOCI",
            2025,
            1_674_225,
        ),
        (
            "Fair value reserve - Investments measured at FVOCI",
            2024,
            1_769_093,
        ),
        ("Long term loan", 2025, 951_736),
        ("Long term loan", 2024, 1_438_764),
    ]


def test_extraction_quality_report_flags_duplicate_conflicting_and_unclassified(
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025"],
                    ["Revenue", "100"],
                    ["Revenue", "110"],
                ]
            ),
            FakeCamelotTable(
                [
                    ["Metric", "2025"],
                    ["Cash", "50"],
                ]
            ),
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=1,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    quality_report = result.extraction_summary.quality_report
    assert quality_report.tables_extracted == 2
    assert quality_report.metric_values_generated == 3
    assert quality_report.duplicate_metric_group_count == 1
    assert quality_report.duplicate_metric_value_count == 1
    assert quality_report.conflicting_metric_group_count == 1
    assert quality_report.unclassified_table_count == 1
    assert quality_report.top_suspicious_metrics[0].metric == "Revenue"
    assert quality_report.top_suspicious_metrics[0].reasons == [
        "duplicate_metric_values",
        "conflicting_values",
    ]
    assert quality_report.top_suspicious_metrics[0].distinct_values == [100, 110]
    assert quality_report.top_suspicious_tables[0].table_type == "unclassified_table"
    assert "unclassified_table" in quality_report.top_suspicious_tables[0].reasons


def test_extraction_quality_report_flags_numeric_only_tables() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["2025", "2024"],
                    ["100", "200"],
                    ["300", "400"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=1,
                    table_types=["income_statement"],
                )
            ]
        ),
    )

    quality_report = result.extraction_summary.quality_report
    assert quality_report.tables_extracted == 1
    assert quality_report.tables_rejected == 1
    assert quality_report.metric_values_generated == 0
    assert quality_report.missing_label_table_count == 1
    assert quality_report.numeric_only_table_count == 1
    assert quality_report.confidence_distribution["20-40"] == 1
    assert quality_report.top_suspicious_tables[0].reasons == [
        "missing_labels",
        "numeric_only_table",
        "no_metric_values",
    ]


def test_label_reconstruction_diagnostic_failure_preserves_downstream_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_label_diagnostic_failure(tables: object) -> object:
        raise ValueError("LabelReconstructionDiagnostic stop_reason failure")

    monkeypatch.setattr(
        extractor_module,
        "_label_reconstruction_diagnostics",
        raise_label_diagnostic_failure,
    )
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025"],
                    ["Revenue", "1000"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    extraction_result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2025,
                    page_number=143,
                    table_types=["income_statement"],
                )
            ]
        ),
    )
    normalization_result = TableMetricNormalizer(
        metric_normalizer=FakeMetricNormalizer()
    ).normalize_tables(extraction_result)
    consolidated_metric_values = FinancialYearConsolidator().consolidate(
        normalization_result.metric_values
    )
    workbook_output_dir = Path("output") / "test_extraction_persistence"
    workbook_output_dir.mkdir(parents=True, exist_ok=True)
    workbook_result = OpenPyXLWorkbookPopulationService(
        output_dir=workbook_output_dir
    ).generate_workbook(
        metric_values=consolidated_metric_values,
        insights=[],
        template_path=None,
    )

    assert len(extraction_result.tables) == 1
    assert extraction_result.metric_values[0].metric == "Revenue"
    assert extraction_result.extraction_summary.quality_report.tables_extracted == 1
    assert (
        extraction_result.extraction_summary.quality_report.metric_values_generated
        == 1
    )
    assert extraction_result.extraction_summary.quality_report.tables_rejected == 0
    assert normalization_result.metric_values[0].metric == "revenue"
    assert consolidated_metric_values[0].metric == "revenue"
    assert workbook_result.metrics_written == 1
    assert "Income Statement" in workbook_result.sheets_created
    assert Path(workbook_result.output_file_path).exists()


def test_quality_report_exception_does_not_fail_extraction(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def raise_quality_report_failure(tables: object) -> object:
        raise RuntimeError("quality report failure")

    monkeypatch.setattr(
        extractor_module,
        "_build_extraction_quality_report",
        raise_quality_report_failure,
    )
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable(
                [
                    ["Metric", "2025"],
                    ["Cash", "500"],
                ]
            )
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2025,
                        page_number=20,
                        table_types=["balance_sheet"],
                    )
                ]
            ),
        )

    assert len(result.tables) == 1
    assert result.metric_values[0].metric == "Cash"
    assert result.extraction_summary.quality_report.tables_extracted == 1
    assert result.extraction_summary.quality_report.metric_values_generated == 1
    assert "Extraction quality diagnostics failed" in caplog.text


def test_extract_tables_returns_empty_when_both_extractors_fail() -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("camelot failure")
        ),
        pdfplumber_open=lambda _: (_ for _ in ()).throw(
            RuntimeError("pdfplumber failure")
        ),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=_classification_result(),
    )

    assert result.tables == []


def test_extract_tables_continues_processing_remaining_pages() -> None:
    def camelot_reader(pdf_path: str, pages: str) -> list[FakeCamelotTable]:
        if pages == "20":
            raise RuntimeError("page failed")
        return [FakeCamelotTable([["Revenue", "1000"]])]

    extractor = CamelotTableExtractor(
        camelot_reader=camelot_reader,
        pdfplumber_open=lambda _: FakePdfplumberDocument(
            [FakePdfplumberPage([]) for _ in range(30)]
        ),
    )

    result = extractor.extract_tables(
        pdf_path="annual_report.pdf",
        classification_result=FinancialTableClassificationResult(
            page_table_types=[
                PageTableType(
                    year=2024,
                    page_number=20,
                    table_types=["balance_sheet"],
                ),
                PageTableType(
                    year=2024,
                    page_number=25,
                    table_types=["income_statement"],
                ),
            ]
        ),
    )

    assert result.model_dump(exclude={"extraction_summary"}) == {
        "tables": [
            {
                "source_report_year": 2024,
                "page_number": 25,
                "table_type": "income_statement",
                "table_index": 0,
                "source_table_index": 0,
                "split_table_index": None,
                "split_reason": None,
                "rows": [["Revenue", "1000"]],
                "metric_values": [],
            }
        ],
        "metric_values": [],
    }


def test_extract_tables_logs_processing_and_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    extractor = CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [
            FakeCamelotTable([["Cash", "1000"]])
        ],
        pdfplumber_open=lambda _: FakePdfplumberDocument([]),
    )

    with caplog.at_level(logging.INFO):
        extractor.extract_tables(
            pdf_path="annual_report.pdf",
            classification_result=FinancialTableClassificationResult(
                page_table_types=[
                    PageTableType(
                        year=2024,
                        page_number=20,
                        table_types=["balance_sheet"],
                    )
                ]
            ),
        )

    assert "Processing page 20" in caplog.text
    assert "Camelot succeeded" in caplog.text
    assert "Extraction completed" in caplog.text
