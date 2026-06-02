"""OCR pipeline orchestration service."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline
from ocr_engine.pipeline.models.layer_execution_result import LayerExecutionResult
from ocr_engine.pipeline.models.pipeline_error import PipelineError
from ocr_engine.pipeline.models.pipeline_status import PipelineStatus
from shared.models.company_context import CompanyContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PipelineLayer:
    """Internal layer adapter definition."""

    name: str
    service: Any
    fallback_method_name: str


class OCRPipeline(IOCRPipeline):
    """Coordinate all OCR layers in the required business workflow order.

    This service is the single entry point for OCR workflow execution. FastAPI,
    CLI runners, batch jobs, and future services should call ``process`` rather
    than embedding OCR workflow decisions in controllers or scripts.
    """

    def __init__(
        self,
        table_detector: Any,
        table_classifier: Any,
        table_extractor: Any,
        validator: Any,
        metric_normalizer: Any,
        insights_extractor: Any,
        financial_year_consolidator: Any,
        workbook_population_service: Any,
        query_engine_bundle_service: Any | None = None,
        *,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the pipeline with injected OCR workflow dependencies."""

        layers = [
            _PipelineLayer("Table Detection", table_detector, "detect_tables_for_context"),
            _PipelineLayer(
                "Classification",
                table_classifier,
                "classify_tables_for_context",
            ),
            _PipelineLayer(
                "Table Extraction",
                table_extractor,
                "extract_tables_for_context",
            ),
            _PipelineLayer("Validation", validator, "validate_for_context"),
            _PipelineLayer(
                "Metric Normalization",
                metric_normalizer,
                "normalize_for_context",
            ),
            _PipelineLayer(
                "Insights Extraction",
                insights_extractor,
                "extract_insights_for_context",
            ),
            _PipelineLayer(
                "Financial Year Consolidation",
                financial_year_consolidator,
                "consolidate_context",
            ),
            _PipelineLayer(
                "Workbook Population",
                workbook_population_service,
                "process",
            ),
        ]
        if query_engine_bundle_service is not None:
            layers.append(
                _PipelineLayer(
                    "Query Engine Bundle Generation",
                    query_engine_bundle_service,
                    "process",
                )
            )

        self._layers = tuple(layers)
        self._logger = log or logger

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run the OCR workflow and return the populated company context."""

        context.pipeline_status = PipelineStatus.RUNNING
        context.pipeline_errors = []
        context.execution_results = []

        self._logger.info(
            "Pipeline Started",
            extra={
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )

        for layer in self._layers:
            context = self._execute_layer(layer, context)

        context.pipeline_status = (
            PipelineStatus.FAILED
            if context.pipeline_errors
            else PipelineStatus.COMPLETED
        )
        self._logger.info(
            "Pipeline Completed",
            extra={
                "company_name": context.company_name,
                "pipeline_status": context.pipeline_status.value,
                "error_count": len(context.pipeline_errors),
            },
        )
        return context

    def _execute_layer(
        self,
        layer: _PipelineLayer,
        context: CompanyContext,
    ) -> CompanyContext:
        start_time = time.perf_counter()
        self._logger.info(
            "%s Started",
            layer.name,
            extra={"layer_name": layer.name},
        )

        try:
            layer_callable = self._resolve_layer_callable(layer)
            updated_context = layer_callable(context)
            execution_time_seconds = time.perf_counter() - start_time
            updated_context.execution_results.append(
                LayerExecutionResult(
                    layer_name=layer.name,
                    execution_time_seconds=execution_time_seconds,
                    success=True,
                )
            )
            self._logger.info(
                "%s Completed",
                layer.name,
                extra={
                    "layer_name": layer.name,
                    "execution_time_seconds": execution_time_seconds,
                },
            )
            return updated_context
        except PipelineLayerPartialFailure as exc:
            execution_time_seconds = time.perf_counter() - start_time
            updated_context = exc.context
            for error_message in exc.error_messages:
                updated_context.pipeline_errors.append(
                    self._pipeline_error(layer.name, error_message)
                )
            updated_context.execution_results.append(
                LayerExecutionResult(
                    layer_name=layer.name,
                    execution_time_seconds=execution_time_seconds,
                    success=False,
                )
            )
            self._logger.warning(
                "Layer Partially Failed: %s",
                layer.name,
                extra={
                    "layer_name": layer.name,
                    "execution_time_seconds": execution_time_seconds,
                    "error_count": len(exc.error_messages),
                },
            )
            return updated_context
        except Exception as exc:
            execution_time_seconds = time.perf_counter() - start_time
            context.pipeline_errors.append(
                self._pipeline_error(
                    layer.name,
                    str(exc) or exc.__class__.__name__,
                )
            )
            context.execution_results.append(
                LayerExecutionResult(
                    layer_name=layer.name,
                    execution_time_seconds=execution_time_seconds,
                    success=False,
                )
            )
            self._logger.exception(
                "Layer Failed: %s",
                layer.name,
                extra={
                    "layer_name": layer.name,
                    "execution_time_seconds": execution_time_seconds,
                },
            )
            return context

    @staticmethod
    def _resolve_layer_callable(
        layer: _PipelineLayer,
    ) -> Callable[[CompanyContext], CompanyContext]:
        process = getattr(layer.service, "process", None)
        if callable(process):
            return process

        fallback = getattr(layer.service, layer.fallback_method_name, None)
        if callable(fallback):
            return fallback

        raise TypeError(
            f"{layer.name} service must expose process(context) or "
            f"{layer.fallback_method_name}(context)."
        )

    @staticmethod
    def _pipeline_error(layer_name: str, error_message: str) -> PipelineError:
        """Create the pipeline error model in one orchestration-owned place."""

        return PipelineError(
            layer_name=layer_name,
            error_message=error_message or "Unknown pipeline error.",
        )
