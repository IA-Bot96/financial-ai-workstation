"""Composition-root factory for OCR engine selection."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Callable

from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline
from ocr_engine.pipeline.ocr_pipeline import OCRPipeline
from ocr_engine.services.camelot_table_extractor import CamelotTableExtractor
from ocr_engine.services.openai_insights_extractor import OpenAIInsightsExtractor
from ocr_engine.services.openai_table_classifier import OpenAITableClassifier
from ocr_engine.services.table_metric_normalizer import TableMetricNormalizer
from ocr_engine.services.table_transformer_detector import TableTransformerDetector
from ocr_engine.validation.financial_validation_service import FinancialValidationService
from query_engine.services.bundle_generation_service import (
    QueryEngineBundleGenerationService,
)
from shared.config.settings import Settings, get_settings
from shared.services.financial_year_consolidator import FinancialYearConsolidator
from workbook_population.services.workbook_population_service import (
    OpenPyXLWorkbookPopulationService,
)


class OCREngineVersion(str, Enum):
    """Supported OCR engine composition modes."""

    V1 = "v1"
    V2 = "v2"
    SHADOW = "shadow"


PipelineBuilder = Callable[[Settings, str | Path | None], IOCRPipeline]


def build_ocr_pipeline(
    settings: Settings | None = None,
    *,
    output_xlsx: str | Path | None = None,
    v1_builder: PipelineBuilder | None = None,
    v2_builder: PipelineBuilder | None = None,
) -> IOCRPipeline:
    """Build the configured OCR pipeline without changing caller contracts."""

    settings = settings or get_settings()
    version = OCREngineVersion(settings.ocr_engine_version)
    build_v1 = v1_builder or build_v1_pipeline
    build_v2 = v2_builder or build_v2_pipeline

    if version is OCREngineVersion.V1:
        return build_v1(settings, output_xlsx)
    if version is OCREngineVersion.V2:
        return build_v2(settings, output_xlsx)
    if version is OCREngineVersion.SHADOW:
        from ocr_engine.pipeline.shadow_ocr_pipeline import ShadowOCRPipeline

        return ShadowOCRPipeline(
            primary_pipeline=build_v1(settings, output_xlsx),
            shadow_pipeline=build_v2(settings, None),
            output_dir=settings.ocr_v2_shadow_output_dir,
        )
    raise ValueError(f"Unsupported OCR engine version: {settings.ocr_engine_version}")


def build_v1_pipeline(
    settings: Settings,
    output_xlsx: str | Path | None = None,
) -> OCRPipeline:
    """Build the production OCR V1 pipeline."""

    workbook_population_service = _build_workbook_population_service(output_xlsx)
    query_engine_bundle_service = QueryEngineBundleGenerationService(
        cell_mapping_provider=workbook_population_service,
    )
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
        workbook_population_service=workbook_population_service,
        query_engine_bundle_service=query_engine_bundle_service,
    )


def build_v2_pipeline(
    settings: Settings,
    output_xlsx: str | Path | None = None,
) -> IOCRPipeline:
    """Build the OCR V2 production-interface adapter."""

    from ocr_engine.pipeline.ocr_v2_pipeline import OCRV2Pipeline

    return OCRV2Pipeline(
        tables_dir=settings.ocr_v2_tables_dir,
        output_xlsx=output_xlsx,
        output_dir=settings.output_directory,
    )


def _build_workbook_population_service(
    output_xlsx: str | Path | None,
) -> OpenPyXLWorkbookPopulationService:
    """Create the workbook service, optionally targeting an exact .xlsx path."""

    if output_xlsx is None:
        return OpenPyXLWorkbookPopulationService()

    output_path = Path(output_xlsx).expanduser()
    output_dir = output_path.parent if output_path.parent != Path("") else Path(".")
    return OpenPyXLWorkbookPopulationService(
        output_dir=output_dir,
        output_file_name=output_path.name,
    )


__all__ = [
    "OCREngineVersion",
    "build_ocr_pipeline",
    "build_v1_pipeline",
    "build_v2_pipeline",
]
