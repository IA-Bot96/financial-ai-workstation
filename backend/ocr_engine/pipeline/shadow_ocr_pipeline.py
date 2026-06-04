"""Shadow OCR pipeline wrapper.

Shadow mode runs V1 and V2 from the same input context, returns the V1 result,
and persists V2 plus comparison artifacts. It does not alter V1 output or make
V2 output visible to callers.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline
from shared.models.company_context import CompanyContext

logger = logging.getLogger(__name__)


class ShadowOCRPipeline(IOCRPipeline):
    """Run V1 as served output and V2 as non-serving shadow evidence."""

    def __init__(
        self,
        *,
        primary_pipeline: IOCRPipeline,
        shadow_pipeline: IOCRPipeline,
        output_dir: str | Path = Path("output/ocr_v2_shadow"),
    ) -> None:
        self._primary_pipeline = primary_pipeline
        self._shadow_pipeline = shadow_pipeline
        self._output_dir = Path(output_dir)

    @property
    def output_dir(self) -> Path:
        """Return the shadow artifact directory."""

        return self._output_dir

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run both engines and return only the primary/V1 result."""

        logger.info(
            "Running V1 + V2",
            extra={
                "component": "ShadowOCRPipeline",
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )
        run_id = _run_id(context)
        primary_context = context.model_copy(deep=True)
        shadow_context = context.model_copy(deep=True)

        primary_start = time.perf_counter()
        primary_result = self._primary_pipeline.process(primary_context)
        primary_runtime_seconds = time.perf_counter() - primary_start

        shadow_error: str | None = None
        shadow_result: CompanyContext | None = None
        shadow_start = time.perf_counter()
        try:
            shadow_result = self._shadow_pipeline.process(shadow_context)
        except Exception as exc:  # pragma: no cover - defensive wrapper.
            shadow_error = str(exc) or exc.__class__.__name__
        shadow_runtime_seconds = time.perf_counter() - shadow_start

        self._persist_shadow_artifacts(
            run_id=run_id,
            original_context=context,
            primary_result=primary_result,
            shadow_result=shadow_result,
            shadow_error=shadow_error,
            primary_runtime_seconds=primary_runtime_seconds,
            shadow_runtime_seconds=shadow_runtime_seconds,
            shadow_timing_breakdown=_shadow_timing_breakdown(self._shadow_pipeline),
            shadow_run_audit=_shadow_run_audit(self._shadow_pipeline),
        )
        logger.info(
            "Serving V1 output",
            extra={
                "component": "ShadowOCRPipeline",
                "run_id": run_id,
                "v2_output_consumed_by_caller": False,
            },
        )
        return primary_result

    def _persist_shadow_artifacts(
        self,
        *,
        run_id: str,
        original_context: CompanyContext,
        primary_result: CompanyContext,
        shadow_result: CompanyContext | None,
        shadow_error: str | None,
        primary_runtime_seconds: float,
        shadow_runtime_seconds: float,
        shadow_timing_breakdown: dict[str, Any],
        shadow_run_audit: dict[str, Any],
    ) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        shadow_context_path = self._output_dir / f"{run_id}_v2_context.json"
        comparison_path = self._output_dir / f"{run_id}_comparison.json"
        report_path = self._output_dir / "ocr_v2_shadow_mode_report.md"
        metrics_path = self._output_dir / "ocr_v2_shadow_metrics.json"
        history_path = self._output_dir / "ocr_v2_shadow_history.json"
        dashboard_path = self._output_dir / "ocr_v2_shadow_dashboard.json"
        comparison_report_path = self._output_dir / "ocr_v2_shadow_comparison_report.md"
        trend_report_path = self._output_dir / "ocr_v2_shadow_trend_report.md"

        if shadow_result is not None:
            shadow_context_path.write_text(
                json.dumps(shadow_result.model_dump(mode="json"), indent=2, sort_keys=True),
                encoding="utf-8",
            )

        metrics_record = _shadow_metrics_record(
            run_id=run_id,
            original_context=original_context,
            primary_result=primary_result,
            shadow_result=shadow_result,
            shadow_error=shadow_error,
            primary_runtime_seconds=primary_runtime_seconds,
            shadow_runtime_seconds=shadow_runtime_seconds,
            shadow_timing_breakdown=shadow_timing_breakdown,
            shadow_run_audit=shadow_run_audit,
        )
        comparison = _comparison_payload(
            run_id=run_id,
            primary_result=primary_result,
            shadow_result=shadow_result,
            shadow_error=shadow_error,
            shadow_context_path=shadow_context_path if shadow_result is not None else None,
            metrics_record=metrics_record,
        )
        comparison_path.write_text(
            json.dumps(comparison, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _append_metrics_record(metrics_path, metrics_record)
        history = _append_history_records(
            history_path,
            _history_records(metrics_record),
        )
        dashboard = _dashboard_from_history(history["records"])
        dashboard_path.write_text(
            json.dumps(dashboard, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        comparison_report_path.write_text(
            _shadow_comparison_report(comparison),
            encoding="utf-8",
        )
        trend_report_path.write_text(
            _shadow_trend_report(dashboard, history["records"]),
            encoding="utf-8",
        )
        report_path.write_text(_shadow_report(comparison), encoding="utf-8")


def _comparison_payload(
    *,
    run_id: str,
    primary_result: CompanyContext,
    shadow_result: CompanyContext | None,
    shadow_error: str | None,
    shadow_context_path: Path | None,
    metrics_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact": "ocr_v2_shadow_comparison",
        "run_id": run_id,
        "served_engine": "v1",
        "shadow_engine": "v2",
        "production_output_source": "v1",
        "v2_output_consumed_by_caller": False,
        "v1": _context_summary(primary_result),
        "v2": _context_summary(shadow_result) if shadow_result is not None else None,
        "shadow_error": shadow_error,
        "shadow_context_path": str(shadow_context_path) if shadow_context_path else None,
        "shadow_metrics": metrics_record,
        "comparison": {
            "status_match": (
                shadow_result is not None
                and primary_result.pipeline_status == shadow_result.pipeline_status
            ),
            "metric_value_delta": (
                metrics_record["v2_metrics_count"] - metrics_record["v1_metrics_count"]
                if shadow_result is not None
                else None
            ),
            "workbook_both_generated": (
                primary_result.generated_workbook is not None
                and shadow_result is not None
                and shadow_result.generated_workbook is not None
            ),
        },
        "integrity": {
            "caller_receives_v1": True,
            "v2_persisted_only": True,
            "api_contract_changed": False,
        },
    }


def _shadow_metrics_record(
    *,
    run_id: str,
    original_context: CompanyContext,
    primary_result: CompanyContext,
    shadow_result: CompanyContext | None,
    shadow_error: str | None,
    primary_runtime_seconds: float,
    shadow_runtime_seconds: float,
    shadow_timing_breakdown: dict[str, Any],
    shadow_run_audit: dict[str, Any],
) -> dict[str, Any]:
    v1_errors = _pipeline_errors(primary_result)
    v2_errors = _pipeline_errors(shadow_result) if shadow_result is not None else []
    if shadow_error:
        v2_errors = [*v2_errors, {"layer_name": "Shadow OCR Pipeline", "error_message": shadow_error}]
    v1_metrics_count = _metrics_count(primary_result)
    v2_metrics_count = _metrics_count(shadow_result, run_audit=shadow_run_audit)
    v1_workbook_rows = _workbook_rows(primary_result)
    v2_workbook_rows = _workbook_rows(shadow_result)
    v1_source_insufficient_count = _source_insufficient_count(primary_result)
    v2_source_insufficient_count = _source_insufficient_count(
        shadow_result,
        run_audit=shadow_run_audit,
    )
    return {
        "run_id": run_id,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_identifier": _document_identifier(original_context),
        "v1_runtime_seconds": round(primary_runtime_seconds, 6),
        "v2_runtime_seconds": round(shadow_runtime_seconds, 6),
        "v1_metrics_count": v1_metrics_count,
        "v2_metrics_count": v2_metrics_count,
        "v1_source_insufficient_count": v1_source_insufficient_count,
        "v2_source_insufficient_count": v2_source_insufficient_count,
        "v1_workbook_rows": v1_workbook_rows,
        "v2_workbook_rows": v2_workbook_rows,
        "v1_errors": v1_errors,
        "v2_errors": v2_errors,
        "comparison_status": _comparison_status(
            shadow_result=shadow_result,
            shadow_error=shadow_error,
            v1_errors=v1_errors,
            v2_errors=v2_errors,
            v1_metrics_count=v1_metrics_count,
            v2_metrics_count=v2_metrics_count,
            v1_workbook_rows=v1_workbook_rows,
            v2_workbook_rows=v2_workbook_rows,
            v1_source_insufficient_count=v1_source_insufficient_count,
            v2_source_insufficient_count=v2_source_insufficient_count,
        ),
        "v2_timing_breakdown": shadow_timing_breakdown,
    }


def _context_summary(context: CompanyContext | None) -> dict[str, Any] | None:
    if context is None:
        return None
    return {
        "company_name": context.company_name,
        "report_years": [report.year for report in context.reports],
        "pipeline_status": context.pipeline_status.value,
        "pipeline_errors": [
            error.model_dump(mode="json") for error in context.pipeline_errors
        ],
        "execution_layers": [
            result.model_dump(mode="json") for result in context.execution_results
        ],
        "metric_values": len(context.metric_values),
        "generated_workbook": (
            context.generated_workbook.model_dump(mode="json")
            if context.generated_workbook is not None
            else None
        ),
    }


def _shadow_report(comparison: dict[str, Any]) -> str:
    v1 = comparison["v1"]
    v2 = comparison["v2"] or {}
    metrics = comparison["shadow_metrics"]
    return "\n".join(
        [
            "# OCR V2 Shadow Mode Report",
            "",
            f"Run ID: `{comparison['run_id']}`",
            "",
            "## Serving Behavior",
            "",
            "- Served engine: V1",
            "- Shadow engine: V2",
            "- V2 output consumed by caller: false",
            "- API contract changed: false",
            "",
            "## Comparison",
            "",
            f"- V1 status: {v1['pipeline_status']}",
            f"- V2 status: {v2.get('pipeline_status', 'not_available')}",
            f"- V1 metric values: {v1['metric_values']}",
            f"- V2 metric values: {v2.get('metric_values', 'not_available')}",
            f"- Status match: {comparison['comparison']['status_match']}",
            f"- Metric value delta: {comparison['comparison']['metric_value_delta']}",
            f"- Comparison status: {metrics['comparison_status']}",
            f"- Shadow error: {comparison['shadow_error'] or 'none'}",
            "",
            "## Observability",
            "",
            f"- V1 runtime seconds: {metrics['v1_runtime_seconds']}",
            f"- V2 runtime seconds: {metrics['v2_runtime_seconds']}",
            f"- V2 extraction seconds: {metrics['v2_timing_breakdown']['extraction_time_seconds']}",
            f"- V2 capture seconds: {metrics['v2_timing_breakdown']['capture_time_seconds']}",
            f"- V2 governance seconds: {metrics['v2_timing_breakdown']['governance_time_seconds']}",
            f"- V2 selection seconds: {metrics['v2_timing_breakdown']['selection_time_seconds']}",
            f"- V2 workbook seconds: {metrics['v2_timing_breakdown']['workbook_time_seconds']}",
            f"- V2 export seconds: {metrics['v2_timing_breakdown']['export_time_seconds']}",
            "",
        ]
    )


def _shadow_comparison_report(comparison: dict[str, Any]) -> str:
    metrics = comparison["shadow_metrics"]
    timing = metrics["v2_timing_breakdown"]
    return "\n".join(
        [
            "# OCR V2 Shadow Comparison Report",
            "",
            f"Run ID: `{comparison['run_id']}`",
            f"Document: `{metrics['document_identifier']}`",
            "",
            "## Serving Contract",
            "",
            "- Served output: V1",
            "- V2 consumed by caller: false",
            "- Production behavior changed: false",
            "",
            "## Runtime",
            "",
            f"- V1 runtime seconds: {metrics['v1_runtime_seconds']}",
            f"- V2 runtime seconds: {metrics['v2_runtime_seconds']}",
            "",
            "## Counts",
            "",
            f"- V1 metrics count: {metrics['v1_metrics_count']}",
            f"- V2 metrics count: {metrics['v2_metrics_count']}",
            f"- V1 source-insufficient count: {metrics['v1_source_insufficient_count']}",
            f"- V2 source-insufficient count: {metrics['v2_source_insufficient_count']}",
            f"- V1 workbook rows: {metrics['v1_workbook_rows']}",
            f"- V2 workbook rows: {metrics['v2_workbook_rows']}",
            f"- Comparison status: {metrics['comparison_status']}",
            "",
            "## V2 Timing Breakdown",
            "",
            f"- Extraction: {timing['extraction_time_seconds']}s",
            f"- Capture: {timing['capture_time_seconds']}s",
            f"- Governance: {timing['governance_time_seconds']}s",
            f"- Selection: {timing['selection_time_seconds']}s",
            f"- Workbook: {timing['workbook_time_seconds']}s",
            f"- Export: {timing['export_time_seconds']}s",
            "",
            "## Errors",
            "",
            f"- V1 errors: {len(metrics['v1_errors'])}",
            f"- V2 errors: {len(metrics['v2_errors'])}",
            "",
        ]
    )


def _append_metrics_record(path: Path, record: dict[str, Any]) -> None:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        runs = list(payload.get("runs", []))
    else:
        payload = {
            "artifact": "ocr_v2_shadow_metrics",
            "schema_version": "1.0.0",
            "runs": [],
        }
        runs = []
    runs.append(record)
    payload["runs"] = runs
    payload["latest_run"] = record
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _history_records(record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    document_id = record["document_identifier"]
    timestamp = record["captured_at_utc"]
    comparison_status = record["comparison_status"]
    return (
        {
            "run_id": record["run_id"],
            "document_id": document_id,
            "engine_version": "v1",
            "runtime": record["v1_runtime_seconds"],
            "metric_count": record["v1_metrics_count"],
            "source_insufficient_count": record["v1_source_insufficient_count"],
            "workbook_rows": record["v1_workbook_rows"],
            "comparison_status": comparison_status,
            "timestamp": timestamp,
            "error_count": len(record["v1_errors"]),
        },
        {
            "run_id": record["run_id"],
            "document_id": document_id,
            "engine_version": "v2",
            "runtime": record["v2_runtime_seconds"],
            "metric_count": record["v2_metrics_count"],
            "source_insufficient_count": record["v2_source_insufficient_count"],
            "workbook_rows": record["v2_workbook_rows"],
            "comparison_status": comparison_status,
            "timestamp": timestamp,
            "error_count": len(record["v2_errors"]),
        },
    )


def _append_history_records(
    path: Path,
    records: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        existing_records = list(payload.get("records", []))
    else:
        payload = {
            "artifact": "ocr_v2_shadow_history",
            "schema_version": "1.0.0",
            "records": [],
        }
        existing_records = []
    existing_records.extend(records)
    payload["records"] = existing_records
    payload["latest_records"] = list(records)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _dashboard_from_history(records: list[dict[str, Any]]) -> dict[str, Any]:
    v1_records = [record for record in records if record.get("engine_version") == "v1"]
    v2_records = [record for record in records if record.get("engine_version") == "v2"]
    run_pairs = _history_run_pairs(records)
    return {
        "artifact": "ocr_v2_shadow_dashboard",
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_documents_processed": len(
            {record["document_id"] for record in records}
        ),
        "total_shadow_runs": len(run_pairs),
        "average_v1_runtime": _average_runtime(v1_records),
        "average_v2_runtime": _average_runtime(v2_records),
        "runtime_ratio": _runtime_ratio(v1_records, v2_records),
        "comparison_status_breakdown": _status_breakdown(run_pairs),
        "v2_more_complete_count": _v2_more_complete_count(run_pairs),
        "v2_less_complete_count": _v2_less_complete_count(run_pairs),
        "error_counts": {
            "v1": sum(int(record.get("error_count", 0)) for record in v1_records),
            "v2": sum(int(record.get("error_count", 0)) for record in v2_records),
            "runs_with_errors": sum(
                1
                for pair in run_pairs.values()
                if _record_error_count(pair.get("v1")) > 0
                or _record_error_count(pair.get("v2")) > 0
            ),
        },
    }


def _history_run_pairs(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    pairs: dict[str, dict[str, Any]] = {}
    for record in records:
        run_id = str(record.get("run_id", "unknown"))
        engine_version = str(record.get("engine_version", "unknown"))
        pairs.setdefault(run_id, {})[engine_version] = record
    return pairs


def _average_runtime(records: list[dict[str, Any]]) -> float | None:
    if not records:
        return None
    return round(sum(float(record["runtime"]) for record in records) / len(records), 6)


def _runtime_ratio(
    v1_records: list[dict[str, Any]],
    v2_records: list[dict[str, Any]],
) -> float | None:
    average_v1 = _average_runtime(v1_records)
    average_v2 = _average_runtime(v2_records)
    if average_v1 is None or average_v2 is None or average_v1 == 0:
        return None
    return round(average_v2 / average_v1, 6)


def _status_breakdown(run_pairs: dict[str, dict[str, Any]]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for pair in run_pairs.values():
        record = pair.get("v1") or pair.get("v2")
        if record is None:
            continue
        status = str(record.get("comparison_status", "unknown"))
        breakdown[status] = breakdown.get(status, 0) + 1
    return dict(sorted(breakdown.items()))


def _v2_more_complete_count(run_pairs: dict[str, dict[str, Any]]) -> int:
    return sum(1 for pair in run_pairs.values() if _v2_completeness_delta(pair) > 0)


def _v2_less_complete_count(run_pairs: dict[str, dict[str, Any]]) -> int:
    return sum(1 for pair in run_pairs.values() if _v2_completeness_delta(pair) < 0)


def _v2_completeness_delta(pair: dict[str, Any]) -> int:
    v1 = pair.get("v1")
    v2 = pair.get("v2")
    if v1 is None or v2 is None:
        return 0
    metric_delta = int(v2["metric_count"]) - int(v1["metric_count"])
    row_delta = int(v2["workbook_rows"]) - int(v1["workbook_rows"])
    source_insufficient_delta = (
        int(v1["source_insufficient_count"])
        - int(v2["source_insufficient_count"])
    )
    if metric_delta != 0:
        return metric_delta
    if row_delta != 0:
        return row_delta
    return source_insufficient_delta


def _record_error_count(record: dict[str, Any] | None) -> int:
    if record is None:
        return 0
    return int(record.get("error_count", 0))


def _shadow_trend_report(
    dashboard: dict[str, Any],
    records: list[dict[str, Any]],
) -> str:
    run_pairs = _history_run_pairs(records)
    status_lines = [
        f"- {status}: {count}"
        for status, count in dashboard["comparison_status_breakdown"].items()
    ] or ["- none"]
    bottleneck_lines = _candidate_bottleneck_lines(run_pairs)
    return "\n".join(
        [
            "# OCR V2 Shadow Trend Report",
            "",
            "## Corpus",
            "",
            f"- Documents processed: {dashboard['total_documents_processed']}",
            f"- Shadow runs: {dashboard['total_shadow_runs']}",
            "",
            "## Performance Trends",
            "",
            f"- Average V1 runtime: {_display_number(dashboard['average_v1_runtime'])}s",
            f"- Average V2 runtime: {_display_number(dashboard['average_v2_runtime'])}s",
            f"- Runtime ratio V2/V1: {_display_number(dashboard['runtime_ratio'])}",
            "",
            "## Completeness Trends",
            "",
            f"- V2 more complete runs: {dashboard['v2_more_complete_count']}",
            f"- V2 less complete runs: {dashboard['v2_less_complete_count']}",
            "",
            "## Recurring Comparison Differences",
            "",
            *status_lines,
            "",
            "## Candidate Bottlenecks",
            "",
            *bottleneck_lines,
            "",
            "## Error Trends",
            "",
            f"- V1 errors: {dashboard['error_counts']['v1']}",
            f"- V2 errors: {dashboard['error_counts']['v2']}",
            f"- Runs with errors: {dashboard['error_counts']['runs_with_errors']}",
            "",
        ]
    )


def _candidate_bottleneck_lines(
    run_pairs: dict[str, dict[str, Any]],
) -> list[str]:
    if not run_pairs:
        return ["- No shadow history available yet."]
    v2_source_insufficient_total = sum(
        int(pair["v2"]["source_insufficient_count"])
        for pair in run_pairs.values()
        if "v2" in pair
    )
    diverged_runs = sum(
        1
        for pair in run_pairs.values()
        if (pair.get("v1") or pair.get("v2") or {}).get("comparison_status")
        == "diverged_counts"
    )
    return [
        f"- V2 source-insufficient total: {v2_source_insufficient_total}",
        f"- Diverged count runs: {diverged_runs}",
        "- Inspect V2 timing breakdowns in `ocr_v2_shadow_metrics.json` for phase-level bottlenecks.",
    ]


def _display_number(value: Any) -> str:
    return "not_available" if value is None else str(value)


def _shadow_timing_breakdown(pipeline: IOCRPipeline) -> dict[str, Any]:
    timing = getattr(pipeline, "last_timing_breakdown", None)
    if callable(timing):
        timing = timing()
    if timing is None:
        timing = _empty_timing_breakdown()
    else:
        timing = dict(timing)
    for key, value in _empty_timing_breakdown().items():
        timing.setdefault(key, value)
    return timing


def _shadow_run_audit(pipeline: IOCRPipeline) -> dict[str, Any]:
    audit = getattr(pipeline, "last_run_audit", None)
    if callable(audit):
        audit = audit()
    return dict(audit) if isinstance(audit, dict) else {}


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


def _document_identifier(context: CompanyContext) -> str:
    reports = [
        report.file_name or report.file_path or str(report.year)
        for report in context.reports
    ]
    report_part = ",".join(reports) if reports else "no_reports"
    years = ",".join(str(report.year) for report in context.reports) or "unknown_years"
    return f"{context.company_name}:{years}:{report_part}"


def _pipeline_errors(context: CompanyContext | None) -> list[dict[str, Any]]:
    if context is None:
        return []
    return [error.model_dump(mode="json") for error in context.pipeline_errors]


def _workbook_rows(context: CompanyContext | None) -> int:
    if context is None or context.generated_workbook is None:
        return 0
    return int(context.generated_workbook.metrics_written or 0)


def _metrics_count(
    context: CompanyContext | None,
    *,
    run_audit: dict[str, Any] | None = None,
) -> int:
    if run_audit and "canonical_values_selected" in run_audit:
        return int(run_audit["canonical_values_selected"] or 0)
    if context is None:
        return 0
    return len(context.metric_values)


def _source_insufficient_count(
    context: CompanyContext | None,
    *,
    run_audit: dict[str, Any] | None = None,
) -> int:
    if run_audit and "source_insufficient_groups" in run_audit:
        return int(run_audit["source_insufficient_groups"] or 0)
    if context is None or context.financial_year_consolidation_result is None:
        return 0
    payload = context.financial_year_consolidation_result.model_dump(mode="json")
    return _count_source_insufficient_markers(payload)


def _count_source_insufficient_markers(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_source_insufficient_markers(item) for item in value.values())
    if isinstance(value, list | tuple):
        return sum(_count_source_insufficient_markers(item) for item in value)
    if isinstance(value, str) and value.lower() == "source_insufficient":
        return 1
    return 0


def _comparison_status(
    *,
    shadow_result: CompanyContext | None,
    shadow_error: str | None,
    v1_errors: list[dict[str, Any]],
    v2_errors: list[dict[str, Any]],
    v1_metrics_count: int,
    v2_metrics_count: int,
    v1_workbook_rows: int,
    v2_workbook_rows: int,
    v1_source_insufficient_count: int,
    v2_source_insufficient_count: int,
) -> str:
    if shadow_error or shadow_result is None:
        return "v2_failed"
    if v1_errors and not v2_errors:
        return "v1_failed_v2_completed"
    if v2_errors and not v1_errors:
        return "v2_completed_with_errors"
    if v1_errors and v2_errors:
        return "both_completed_with_errors"
    if (
        v1_metrics_count == v2_metrics_count
        and v1_workbook_rows == v2_workbook_rows
        and v1_source_insufficient_count == v2_source_insufficient_count
    ):
        return "matched_counts"
    return "diverged_counts"


def _run_id(context: CompanyContext) -> str:
    years = "_".join(str(report.year) for report in context.reports) or "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_slugify(context.company_name)}_{years}_{timestamp}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "company"


__all__ = ["ShadowOCRPipeline"]
