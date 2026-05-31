"""Unit tests for the OCR processing result model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.financial_fact_extraction import (
    FinancialFact,
    FinancialFactExtractionResult,
)
from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult
from ocr_engine.models.ocr_processing_result import OCRProcessingResult
from ocr_engine.models.report import Report


def test_ocr_processing_result_serializes_expected_output() -> None:
    result = OCRProcessingResult(
        report=Report(
            id="rpt_001",
            company_name="Maple Leaf Cement Factory Limited",
            year=2024,
            file_name="MLCF_2024_Annual_Report.pdf",
            file_path="/reports/MLCF_2024_Annual_Report.pdf",
        ),
        financial_facts=FinancialFactExtractionResult(
            facts=[
                FinancialFact(
                    year=2024,
                    metric="revenue",
                    value=1200000,
                    page_number=20,
                    table_type="income_statement",
                )
            ]
        ),
        insights=InsightsExtractionResult(
            insights=[
                Insight(
                    value_year=2024,
                    source_report_year=2024,
                    area="Debt",
                    takeaway=(
                        "Debt increased due to Southeast Asia expansion "
                        "financing."
                    ),
                    source_section="Management Discussion & Analysis",
                    page_number=84,
                    confidence=0.91,
                )
            ]
        ),
    )

    assert result.model_dump() == {
        "report": {
            "id": "rpt_001",
            "company_name": "Maple Leaf Cement Factory Limited",
            "year": 2024,
            "file_name": "MLCF_2024_Annual_Report.pdf",
            "file_path": "/reports/MLCF_2024_Annual_Report.pdf",
        },
        "financial_facts": {
            "facts": [
                {
                    "year": 2024,
                    "metric": "revenue",
                    "value": 1200000,
                    "page_number": 20,
                    "table_type": "income_statement",
                }
            ]
        },
        "insights": {
            "insights": [
                {
                    "value_year": 2024,
                    "source_report_year": 2024,
                    "area": "Debt",
                    "takeaway": (
                        "Debt increased due to Southeast Asia expansion "
                        "financing."
                    ),
                    "source_section": "Management Discussion & Analysis",
                    "page_number": 84,
                    "confidence": 0.91,
                }
            ],
            "diagnostics": {
                "total_pages_processed": 0,
                "pages_with_text": 0,
                "total_text_characters": 0,
                "section_pages": 0,
                "total_chunks_created": 0,
                "chunk_size": 0,
                "chunk_overlap": 0,
                "retrieval_strategy": "section_balanced_score_all_relevant_chunks",
                "top_k": None,
                "chunks_sent_to_llm": 0,
                "llm_call_count": 0,
                "generated_insights": 0,
                "section_page_count_by_section": {},
                "chunk_count_by_section": {},
                "ranked_chunk_count_by_section": {},
                "insight_count_by_section": {},
                "rejected_low_confidence_count": 0,
                "review_bucket_count": 0,
                "exported_high_confidence_count": 0,
                "generic_filtered_count": 0,
                "confidence_distribution": {},
                "section_identification_report": {
                    "total_pages": 0,
                    "pages_with_pymupdf_text": 0,
                    "pages_with_ocr_text": 0,
                    "accepted_pages": 0,
                    "rejected_pages": 0,
                    "page_type_counts": {},
                    "text_source_counts": {},
                    "ocr_engine_counts": {},
                    "ocr_pages_escalated": 0,
                    "ocr_pages_recovered": 0,
                    "additional_accepted_pages": 0,
                    "page_diagnostics": [],
                },
            },
        },
    }


def test_ocr_processing_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        OCRProcessingResult(
            report=Report(
                id="rpt_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="/reports/MLCF_2024_Annual_Report.pdf",
            ),
            financial_facts=FinancialFactExtractionResult(facts=[]),
            insights=InsightsExtractionResult(insights=[]),
            status="complete",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
