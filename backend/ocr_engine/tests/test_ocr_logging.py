"""Tests for OCR logging foundation."""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.pipeline.ocr_logging import (  # noqa: E402
    OCRRunLogger,
    write_ocr_logging_artifacts,
)
from shared.models.company_context import CompanyContext  # noqa: E402
from shared.models.report import Report  # noqa: E402


def _context() -> CompanyContext:
    return CompanyContext(
        company_name="Logging Test Company",
        reports=[
            Report(
                id="rpt_2025",
                company_name="Logging Test Company",
                year=2025,
                file_name="logging_test.pdf",
                file_path="data/logging_test.pdf",
            )
        ],
    )


def test_ocr_run_logger_writes_timestamped_log_and_artifacts(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    context = _context()

    with OCRRunLogger(
        context,
        component="OCRLoggingTest",
        log_dir=log_dir,
        level="DEBUG",
    ) as run_log:
        run_log.debug("Candidate debug detail")
        run_log.write_summary(
            document=run_log.document_id,
            runtime_seconds=1.25,
            stage_timings={
                "Extraction": 0.1,
                "Capture": 0.2,
                "Registry": 0.3,
                "Statement Governance": 0.4,
                "Scale Governance": 0.5,
                "Entity Governance": 0.6,
                "Selection": 0.7,
                "Workbook": 0.8,
                "MSIL Export": 0.9,
            },
            candidate_count=10,
            canonical_count=6,
            workbook_rows=6,
            status="completed",
        )

    log_files = list(log_dir.glob("*.log"))
    assert len(log_files) == 1
    assert re.match(
        r"^\d{8}_\d{6}_logging_test_company_2025\.log$",
        log_files[0].name,
    )
    log_lines = [
        line
        for line in log_files[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert all(
        re.match(
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} "
            r"\| (INFO|DEBUG) \| OCRLoggingTest \| .+",
            line,
        )
        for line in log_lines
    )
    assert any("Candidate debug detail" in line for line in log_lines)
    assert any("Summary stage MSIL Export: 0.900000s" in line for line in log_lines)

    audit = write_ocr_logging_artifacts(
        log_dir=log_dir,
        audit_path=tmp_path / "ocr_logging_audit.json",
        report_path=tmp_path / "ocr_logging_report.md",
    )

    assert audit["log_file_count"] == 1
    assert audit["timestamped_log_files"] == 1
    assert audit["summary_section_count"] == 1
    assert audit["integrity_violations"] == []
    assert (tmp_path / "ocr_logging_audit.json").exists()
    assert (tmp_path / "ocr_logging_report.md").exists()
