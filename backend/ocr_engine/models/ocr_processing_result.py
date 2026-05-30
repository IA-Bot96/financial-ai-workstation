"""Models for final OCR engine processing output."""

from pydantic import BaseModel, ConfigDict, Field

from .financial_fact_extraction import FinancialFactExtractionResult
from .insights_extraction import InsightsExtractionResult
from .report import Report


class OCRProcessingResult(BaseModel):
    """Final output returned by the OCR engine after processing a report."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
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
                                "year": 2024,
                                "area": "Debt",
                                "takeaway": (
                                    "Debt increased due to Southeast Asia "
                                    "expansion financing."
                                ),
                                "source_section": (
                                    "Management Discussion & Analysis"
                                ),
                                "page_number": 84,
                                "confidence": 0.91,
                            }
                        ]
                    },
                }
            ]
        },
    )

    report: Report = Field(
        ...,
        description="Annual report processed by the OCR engine.",
    )
    financial_facts: FinancialFactExtractionResult = Field(
        ...,
        description="Financial facts extracted from the report's tables.",
    )
    insights: InsightsExtractionResult = Field(
        ...,
        description="Business insights extracted from narrative report text.",
    )
