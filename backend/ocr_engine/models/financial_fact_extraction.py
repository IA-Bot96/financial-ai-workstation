"""Models for OCR financial fact extraction results."""

from pydantic import BaseModel, ConfigDict, Field

from shared.models.financial_fact import FinancialFact


class FinancialFactExtractionResult(BaseModel):
    """Collection of multi-year financial facts extracted from report tables."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "facts": [
                        {
                            "year": 2024,
                            "metric": "revenue",
                            "value": 1200000,
                            "page_number": 20,
                            "table_type": "income_statement",
                        }
                    ]
                }
            ]
        },
    )

    facts: list[FinancialFact] = Field(
        ...,
        description="Structured financial facts extracted from report tables.",
    )


__all__ = ["FinancialFact", "FinancialFactExtractionResult"]
