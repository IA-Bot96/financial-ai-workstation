"""OCR V2 production-interface adapter.

This module is integration scaffolding. It adapts the validated OCR V2 path to
the existing IOCRPipeline contract without changing OCR V2 capture, governance,
selection, workbook generation, MSIL export, or OCR V1 behavior.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ocr.ocr_v2_lucky_run import OCRV2LuckyRun
from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline
from ocr_engine.pipeline.models.layer_execution_result import LayerExecutionResult
from ocr_engine.pipeline.ocr_logging import (
    DEFAULT_OCR_LOG_DIR,
    OCRRunLogger,
    stage_timings_from_v2_breakdown,
)
from ocr_engine.pipeline.models.pipeline_error import PipelineError
from ocr_engine.pipeline.models.pipeline_status import PipelineStatus
from shared.models.company_context import CompanyContext
from workbook_population.models.workbook_result import WorkbookResult

logger = logging.getLogger(__name__)


class OCRV2Pipeline(IOCRPipeline):
    """Run the validated OCR V2 path through the production OCR interface."""

    def __init__(
        self,
        *,
        tables_dir: str | Path = Path("output/ocr_v2_final_validation_tables"),
        output_xlsx: str | Path | None = None,
        output_dir: str | Path = Path("output"),
        runner_factory: Callable[[], Any] = OCRV2LuckyRun,
        log: logging.Logger | None = None,
        log_dir: str | Path = DEFAULT_OCR_LOG_DIR,
        log_level: str | int | None = None,
    ) -> None:
        self._tables_dir = Path(tables_dir)
        self._output_xlsx = Path(output_xlsx) if output_xlsx is not None else None
        self._output_dir = Path(output_dir)
        self._runner_factory = runner_factory
        self._logger = log or logger
        self._log_dir = Path(log_dir)
        self._log_level = log_level
        self._last_timing_breakdown: dict[str, Any] | None = None
        self._last_run_audit: dict[str, Any] | None = None

    @property
    def tables_dir(self) -> Path:
        """Return the V2 raw-table artifact directory used by this adapter."""

        return self._tables_dir

    @property
    def last_timing_breakdown(self) -> dict[str, Any] | None:
        """Return the most recent OCR V2 phase timing payload, if available."""

        return self._last_timing_breakdown.copy() if self._last_timing_breakdown else None

    @property
    def last_run_audit(self) -> dict[str, Any] | None:
        """Return the most recent OCR V2 run audit payload, if available."""

        return self._last_run_audit.copy() if self._last_run_audit else None

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run OCR V2 and return a CompanyContext-compatible result."""

        start_time = time.perf_counter()
        self._last_timing_breakdown = None
        self._last_run_audit = None
        result: Any | None = None
        with OCRRunLogger(
            context,
            component="OCRV2Pipeline",
            log_dir=self._log_dir,
            level=self._log_level,
        ) as run_log:
            context.pipeline_status = PipelineStatus.RUNNING
            context.pipeline_errors = []
            context.execution_results = []

            try:
                workbook_path = self._resolve_workbook_path(context)
                self._logger.info(
                    "Starting OCR run",
                    extra={
                        "component": "OCRV2Pipeline",
                        "company_name": context.company_name,
                        "tables_dir": str(self._tables_dir),
                        "workbook_path": str(workbook_path),
                    },
                )
                result = self._runner_factory().run(
                    tables_dir=self._tables_dir,
                    workbook_path=workbook_path,
                )
                self._last_timing_breakdown = _extract_timing_breakdown(result)
                self._last_run_audit = _model_dump_or_dict(getattr(result, "audit", None))
                if result.audit.integrity_violations:
                    for violation in result.audit.integrity_violations:
                        context.pipeline_errors.append(
                            PipelineError(
                                layer_name="OCR V2 Pipeline",
                                error_message=str(violation.get("message", violation)),
                            )
                        )
                workbook_result = WorkbookResult(
                    output_file_path=str(workbook_path),
                    workbook_mode="ocr_v2",
                    workbook_match_score=100.0,
                    sheets_reused=[],
                    sheets_replaced=[],
                    sheets_created=[result.workbook_output.sheet_name],
                    metrics_written=result.workbook_output.workbook_rows_generated,
                    warnings=[],
                )
                context.workbook_result = workbook_result
                context.generated_workbook = workbook_result
                context.execution_results.append(
                    LayerExecutionResult(
                        layer_name="OCR V2 Pipeline",
                        execution_time_seconds=time.perf_counter() - start_time,
                        success=not context.pipeline_errors,
                    )
                )
                context.pipeline_status = (
                    PipelineStatus.FAILED
                    if context.pipeline_errors
                    else PipelineStatus.COMPLETED
                )
                self._logger.info(
                    "OCR run completed",
                    extra={
                        "component": "OCRV2Pipeline",
                        "pipeline_status": context.pipeline_status.value,
                    },
                )
            except Exception as exc:
                self._last_timing_breakdown = None
                self._last_run_audit = None
                context.pipeline_errors.append(
                    PipelineError(
                        layer_name="OCR V2 Pipeline",
                        error_message=str(exc) or exc.__class__.__name__,
                    )
                )
                context.execution_results.append(
                    LayerExecutionResult(
                        layer_name="OCR V2 Pipeline",
                        execution_time_seconds=time.perf_counter() - start_time,
                        success=False,
                    )
                )
                context.pipeline_status = PipelineStatus.FAILED
                self._logger.exception(
                    "OCR run failed",
                    extra={"component": "OCRV2Pipeline"},
                )
            finally:
                run_log.write_summary(
                    document=run_log.document_id,
                    runtime_seconds=time.perf_counter() - start_time,
                    stage_timings=stage_timings_from_v2_breakdown(
                        self._last_timing_breakdown
                    ),
                    candidate_count=_audit_count(
                        self._last_run_audit,
                        "candidate_rows_generated",
                        len(context.metric_values),
                    ),
                    canonical_count=_audit_count(
                        self._last_run_audit,
                        "canonical_values_selected",
                        len(context.metric_values),
                    ),
                    workbook_rows=_workbook_rows(context),
                    status=context.pipeline_status.value,
                )
            return context

    def _resolve_workbook_path(self, context: CompanyContext) -> Path:
        if self._output_xlsx is not None:
            path = self._output_xlsx
        else:
            years = "_".join(str(report.year) for report in context.reports) or "unknown"
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"ocr_v2_{_slugify(context.company_name)}_{years}_{timestamp}.xlsx"
            path = self._output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "company"


def _extract_timing_breakdown(result: Any) -> dict[str, Any]:
    timing = getattr(result, "timing_breakdown", None)
    if timing is None:
        return _empty_timing_breakdown()
    payload = _model_dump_or_dict(timing)
    for key, value in _empty_timing_breakdown().items():
        payload.setdefault(key, value)
    return payload


def _empty_timing_breakdown() -> dict[str, float]:
    return {
        "extraction_time_seconds": 0.0,
        "capture_time_seconds": 0.0,
        "registry_time_seconds": 0.0,
        "governance_time_seconds": 0.0,
        "statement_governance_time_seconds": 0.0,
        "scale_governance_time_seconds": 0.0,
        "entity_governance_time_seconds": 0.0,
        "selection_time_seconds": 0.0,
        "workbook_time_seconds": 0.0,
        "export_time_seconds": 0.0,
    }


def _model_dump_or_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _audit_count(audit: dict[str, Any] | None, key: str, fallback: int) -> int:
    if audit and key in audit:
        return int(audit[key] or 0)
    return fallback


def _workbook_rows(context: CompanyContext) -> int:
    if context.generated_workbook is None:
        return 0
    return int(context.generated_workbook.metrics_written or 0)


__all__ = ["OCRV2Pipeline"]
