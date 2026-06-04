"""OCR run logging foundation.

This module provides observability-only logging helpers. It does not alter OCR
extraction, governance, selection, workbook generation, or export behavior.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from shared.models.company_context import CompanyContext

OCR_LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)s | %(component)s | %(message)s"
OCR_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_OCR_LOG_DIR = Path("logs")
DEFAULT_OCR_LOG_LEVEL = "INFO"
OCR_STAGE_NAMES = (
    "Extraction",
    "Capture",
    "Registry",
    "Statement Governance",
    "Scale Governance",
    "Entity Governance",
    "Selection",
    "Workbook",
    "MSIL Export",
)


class OCRLogFormatter(logging.Formatter):
    """Timestamped OCR formatter with a stable component column."""

    def __init__(self) -> None:
        super().__init__(OCR_LOG_FORMAT, datefmt=OCR_LOG_DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "component"):
            record.component = _component_from_logger(record.name)
        return super().format(record).replace("\n", "\\n")


@dataclass
class OCRRunLogger:
    """Temporary run logger that writes console and per-run file output."""

    context: CompanyContext
    component: str
    log_dir: str | Path = DEFAULT_OCR_LOG_DIR
    level: str | int | None = None
    logger: logging.Logger = field(init=False)
    log_path: Path = field(init=False)
    document_id: str = field(init=False)
    start_time: float = field(init=False)
    _root_logger: logging.Logger = field(init=False)
    _file_handler: logging.Handler = field(init=False)
    _console_handler: logging.Handler = field(init=False)
    _previous_root_level: int = field(init=False)

    def __post_init__(self) -> None:
        self.logger = logging.getLogger(self.component)
        self.document_id = document_id_for_context(self.context)
        self.log_path = _unique_log_path(Path(self.log_dir), self.document_id)

    def __enter__(self) -> "OCRRunLogger":
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.start_time = time.perf_counter()
        level = _normalize_level(self.level)
        formatter = OCRLogFormatter()

        self._file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        self._file_handler.setFormatter(formatter)
        self._file_handler.setLevel(level)

        self._console_handler = logging.StreamHandler(sys.stderr)
        self._console_handler.setFormatter(formatter)
        self._console_handler.setLevel(level)

        self._root_logger = logging.getLogger()
        self._previous_root_level = self._root_logger.level
        if self._root_logger.level == logging.NOTSET:
            self._root_logger.setLevel(level)
        else:
            self._root_logger.setLevel(min(self._root_logger.level, level))
        self._root_logger.addHandler(self._file_handler)
        self._root_logger.addHandler(self._console_handler)
        self.info("Starting OCR run")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc is not None:
            self.logger.exception(
                "OCR run exited with exception",
                extra={"component": self.component},
            )
        self._root_logger.removeHandler(self._file_handler)
        self._root_logger.removeHandler(self._console_handler)
        self._file_handler.close()
        self._console_handler.close()
        self._root_logger.setLevel(self._previous_root_level)

    def info(self, message: str, **extra: Any) -> None:
        self.logger.info(message, extra={"component": self.component, **extra})

    def debug(self, message: str, **extra: Any) -> None:
        self.logger.debug(message, extra={"component": self.component, **extra})

    def write_summary(
        self,
        *,
        document: str,
        runtime_seconds: float,
        stage_timings: dict[str, float],
        candidate_count: int,
        canonical_count: int,
        workbook_rows: int,
        status: str,
    ) -> None:
        """Append a final run-summary section to the run log."""

        normalized_stage_timings = normalize_stage_timings(stage_timings)
        self.info("OCR RUN SUMMARY")
        self.info("Run Summary")
        self.info(f"Summary document: {document}")
        self.info(f"Summary runtime seconds: {runtime_seconds:.6f}")
        self.info("Stage timing summary")
        for stage_name in OCR_STAGE_NAMES:
            self.info(
                f"Summary stage {stage_name}: "
                f"{normalized_stage_timings[stage_name]:.6f}s"
            )
        self.info(f"Summary candidate count: {candidate_count}")
        self.info(f"Summary canonical count: {canonical_count}")
        self.info(f"Summary workbook rows: {workbook_rows}")
        self.info(f"Summary status: {status}")


def document_id_for_context(context: CompanyContext) -> str:
    """Return the stable log document identifier for a company context."""

    years = "_".join(str(report.year) for report in context.reports) or "unknown"
    return _slugify(f"{context.company_name}_{years}")


def normalize_stage_timings(stage_timings: dict[str, float] | None = None) -> dict[str, float]:
    """Return all required OCR stage timing keys with non-negative float values."""

    source = stage_timings or {}
    return {
        stage_name: max(float(source.get(stage_name, 0.0) or 0.0), 0.0)
        for stage_name in OCR_STAGE_NAMES
    }


def stage_timings_from_v2_breakdown(timing_breakdown: dict[str, Any] | None) -> dict[str, float]:
    """Map OCR V2 timing telemetry into the frozen stage names."""

    timing = timing_breakdown or {}
    return normalize_stage_timings(
        {
            "Extraction": float(timing.get("extraction_time_seconds", 0.0) or 0.0),
            "Capture": float(timing.get("capture_time_seconds", 0.0) or 0.0),
            "Registry": float(timing.get("registry_time_seconds", 0.0) or 0.0),
            "Statement Governance": float(
                timing.get("statement_governance_time_seconds", 0.0) or 0.0
            ),
            "Scale Governance": float(
                timing.get("scale_governance_time_seconds", 0.0) or 0.0
            ),
            "Entity Governance": float(
                timing.get("entity_governance_time_seconds", 0.0) or 0.0
            ),
            "Selection": float(timing.get("selection_time_seconds", 0.0) or 0.0),
            "Workbook": float(timing.get("workbook_time_seconds", 0.0) or 0.0),
            "MSIL Export": float(timing.get("export_time_seconds", 0.0) or 0.0),
        }
    )


def stage_timings_from_context(context: CompanyContext) -> dict[str, float]:
    """Summarize V1 execution results into the common stage timing shape."""

    by_layer = {
        result.layer_name: result.execution_time_seconds
        for result in context.execution_results
    }
    return normalize_stage_timings(
        {
            "Extraction": sum(
                float(by_layer.get(layer_name, 0.0) or 0.0)
                for layer_name in (
                    "Table Detection",
                    "Classification",
                    "Table Extraction",
                )
            ),
            "Workbook": float(by_layer.get("Workbook Population", 0.0) or 0.0),
            "MSIL Export": 0.0,
        }
    )


def write_ocr_logging_artifacts(
    *,
    log_dir: str | Path = DEFAULT_OCR_LOG_DIR,
    audit_path: str | Path = "ocr_logging_audit.json",
    report_path: str | Path = "ocr_logging_report.md",
) -> dict[str, Any]:
    """Generate the requested OCR logging audit and report artifacts."""

    audit = build_ocr_logging_audit(log_dir=log_dir)
    Path(audit_path).write_text(
        json.dumps(audit, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    Path(report_path).write_text(
        build_ocr_logging_report(audit),
        encoding="utf-8",
    )
    return audit


def build_ocr_logging_audit(*, log_dir: str | Path = DEFAULT_OCR_LOG_DIR) -> dict[str, Any]:
    """Inspect run logs and report logging-foundation integrity."""

    log_path = Path(log_dir)
    log_files = sorted(log_path.glob("*.log")) if log_path.exists() else []
    timestamped_files = [
        path
        for path in log_files
        if re.match(r"^\d{8}_\d{6}_[a-z0-9_]+(?:_\d+)?\.log$", path.name)
    ]
    summary_files = [
        path
        for path in log_files
        if "Run Summary" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    timestamped_lines_missing = _log_files_with_bad_timestamp_lines(log_files)
    violations: list[dict[str, Any]] = []
    if len(timestamped_files) != len(log_files):
        violations.append(_violation("log_file_naming", "Some OCR log files are not timestamped."))
    if len(summary_files) != len(log_files):
        violations.append(_violation("summary_missing", "Some OCR log files lack a run summary."))
    if timestamped_lines_missing:
        violations.append(
            _violation(
                "line_timestamp_missing",
                f"Timestamp format missing in: {timestamped_lines_missing}",
            )
        )
    return {
        "artifact": "ocr_logging_audit",
        "log_dir": str(log_path),
        "log_file_count": len(log_files),
        "timestamped_log_files": len(timestamped_files),
        "summary_section_count": len(summary_files),
        "timestamped_console_output_configured": True,
        "dedicated_log_file_per_run": True,
        "log_format": "YYYY-MM-DD HH:MM:SS.mmm | LEVEL | COMPONENT | MESSAGE",
        "supported_levels": ["INFO", "DEBUG"],
        "default_level": DEFAULT_OCR_LOG_LEVEL,
        "candidate_level_logging": "DEBUG-only",
        "stage_timing_fields": list(OCR_STAGE_NAMES),
        "latest_log_file": str(log_files[-1]) if log_files else None,
        "integrity_violations": violations,
    }


def build_ocr_logging_report(audit: dict[str, Any]) -> str:
    """Return the human-readable OCR logging report."""

    return "\n".join(
        [
            "# OCR Logging Report",
            "",
            "## Status",
            "",
            f"- Log files found: {audit['log_file_count']}",
            f"- Timestamped log files: {audit['timestamped_log_files']}",
            f"- Summary sections found: {audit['summary_section_count']}",
            f"- Default level: {audit['default_level']}",
            f"- Candidate-level logging: {audit['candidate_level_logging']}",
            "",
            "## Format",
            "",
            f"`{audit['log_format']}`",
            "",
            "## Stage Timing",
            "",
            *[f"- {stage_name}" for stage_name in audit["stage_timing_fields"]],
            "",
            "## Integrity",
            "",
            f"- Violations: {len(audit['integrity_violations'])}",
            f"- Latest log file: {audit['latest_log_file'] or 'none'}",
            "",
        ]
    )


def _normalize_level(level: str | int | None) -> int:
    raw_level = level if level is not None else os.getenv("OCR_LOG_LEVEL", DEFAULT_OCR_LOG_LEVEL)
    if isinstance(raw_level, int):
        return raw_level
    normalized = raw_level.strip().upper()
    if normalized == "DEBUG":
        return logging.DEBUG
    return logging.INFO


def _unique_log_path(log_dir: Path, document_id: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_path = log_dir / f"{timestamp}_{document_id}.log"
    if not base_path.exists():
        return base_path
    counter = 2
    while True:
        candidate = log_dir / f"{timestamp}_{document_id}_{counter}.log"
        if not candidate.exists():
            return candidate
        counter += 1


def _component_from_logger(logger_name: str) -> str:
    return logger_name.rsplit(".", 1)[-1] if logger_name else "OCR"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "document"


def _log_files_with_bad_timestamp_lines(log_files: list[Path]) -> list[str]:
    bad_files: list[str] = []
    pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \| "
        r"(INFO|DEBUG|WARNING|ERROR|CRITICAL) \| [^|]+ \| .+"
    )
    for path in log_files:
        lines = [
            line
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip()
        ]
        if lines and not all(pattern.match(line) for line in lines):
            bad_files.append(path.name)
    return bad_files


def _violation(check_id: str, message: str) -> dict[str, str]:
    return {
        "check_id": check_id,
        "severity": "warning",
        "message": message,
    }


__all__ = [
    "DEFAULT_OCR_LOG_DIR",
    "DEFAULT_OCR_LOG_LEVEL",
    "OCR_LOG_FORMAT",
    "OCR_STAGE_NAMES",
    "OCRRunLogger",
    "build_ocr_logging_audit",
    "build_ocr_logging_report",
    "document_id_for_context",
    "normalize_stage_timings",
    "stage_timings_from_context",
    "stage_timings_from_v2_breakdown",
    "write_ocr_logging_artifacts",
]
