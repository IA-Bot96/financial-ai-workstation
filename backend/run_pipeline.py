"""CLI entry point for running the OCR pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from ocr_engine.pipeline.ocr_pipeline import OCRPipeline
from ocr_engine.services.camelot_table_extractor import CamelotTableExtractor
from ocr_engine.services.openai_insights_extractor import OpenAIInsightsExtractor
from ocr_engine.services.openai_table_classifier import OpenAITableClassifier
from ocr_engine.services.table_metric_normalizer import TableMetricNormalizer
from ocr_engine.services.table_transformer_detector import TableTransformerDetector
from ocr_engine.validation.financial_validation_service import FinancialValidationService
from shared.config.settings import ConfigurationValidator, Settings, get_settings
from shared.models.company_context import CompanyContext
from shared.services.financial_year_consolidator import FinancialYearConsolidator
from workbook_population.services.workbook_population_service import (
    OpenPyXLWorkbookPopulationService,
)


def build_default_pipeline(settings: Settings | None = None) -> OCRPipeline:
    """Build the production OCR pipeline using the default service implementations."""

    settings = settings or get_settings()
    return OCRPipeline(
        table_detector=TableTransformerDetector(),
        table_classifier=OpenAITableClassifier(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        ),
        table_extractor=CamelotTableExtractor(),
        validator=FinancialValidationService(),
        metric_normalizer=TableMetricNormalizer(),
        insights_extractor=OpenAIInsightsExtractor(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        ),
        financial_year_consolidator=FinancialYearConsolidator(),
        workbook_population_service=OpenPyXLWorkbookPopulationService(),
    )


def main() -> None:
    """Load a company context JSON file, run the pipeline, and write JSON output."""

    parser = argparse.ArgumentParser(description="Run the OCR pipeline.")
    parser.add_argument(
        "--context-json",
        default=os.getenv("OCR_CONTEXT_JSON"),
        help="Path to a CompanyContext JSON input file.",
    )
    parser.add_argument(
        "--output-json",
        default=os.getenv("OCR_OUTPUT_JSON"),
        help="Optional path for the populated CompanyContext JSON output.",
    )
    args = parser.parse_args()

    if not args.context_json:
        parser.error("--context-json or OCR_CONTEXT_JSON is required.")

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    ConfigurationValidator(settings).validate_startup()
    input_path = Path(args.context_json)
    context = CompanyContext.model_validate_json(input_path.read_text(encoding="utf-8"))
    result = build_default_pipeline(settings).process(context)
    output_text = json.dumps(result.model_dump(mode="json"), indent=2)

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
