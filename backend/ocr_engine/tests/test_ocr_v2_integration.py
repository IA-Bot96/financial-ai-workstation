"""Tests for OCR V2 integration scaffolding."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.pipeline.factory import build_ocr_pipeline  # noqa: E402
from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline  # noqa: E402
from ocr_engine.pipeline.models.pipeline_status import PipelineStatus  # noqa: E402
from ocr_engine.pipeline.ocr_v2_pipeline import OCRV2Pipeline  # noqa: E402
from ocr_engine.pipeline.shadow_ocr_pipeline import ShadowOCRPipeline  # noqa: E402
from shared.config.settings import Settings  # noqa: E402
from shared.models.company_context import CompanyContext  # noqa: E402
from shared.models.report import Report  # noqa: E402
from workbook_population.models.workbook_result import WorkbookResult  # noqa: E402


def _context() -> CompanyContext:
    return CompanyContext(
        company_name="Integration Test Company",
        reports=[
            Report(
                id="rpt_2025",
                company_name="Integration Test Company",
                year=2025,
                file_name="report.pdf",
                file_path="data/report.pdf",
            )
        ],
    )


class _FakePipeline(IOCRPipeline):
    def __init__(self, name: str, workbook_path: str) -> None:
        self.name = name
        self.workbook_path = workbook_path
        self.calls = 0
        self.last_timing_breakdown = {
            "extraction_time_seconds": 0.01,
            "capture_time_seconds": 0.02,
            "governance_time_seconds": 0.03,
            "selection_time_seconds": 0.04,
            "workbook_time_seconds": 0.05,
            "export_time_seconds": 0.0,
        }
        self.last_run_audit = {"source_insufficient_groups": 1}

    def process(self, context: CompanyContext) -> CompanyContext:
        self.calls += 1
        context.pipeline_status = PipelineStatus.COMPLETED
        workbook = WorkbookResult(
            output_file_path=self.workbook_path,
            workbook_mode=self.name,
            workbook_match_score=100.0,
            sheets_created=[self.name],
            metrics_written=1,
        )
        context.generated_workbook = workbook
        context.workbook_result = workbook
        return context


class _FakeOCRV2Runner:
    def run(self, *, tables_dir: Path, workbook_path: Path) -> object:
        workbook_path.parent.mkdir(parents=True, exist_ok=True)
        workbook_path.write_text("fake xlsx payload", encoding="utf-8")
        return SimpleNamespace(
            audit=SimpleNamespace(integrity_violations=()),
            workbook_output=SimpleNamespace(
                sheet_name="OCR V2 Canonical Metrics",
                workbook_rows_generated=2,
            ),
            timing_breakdown=SimpleNamespace(
                model_dump=lambda mode="json": {
                    "extraction_time_seconds": 0.1,
                    "capture_time_seconds": 0.2,
                    "registry_time_seconds": 0.05,
                    "governance_time_seconds": 0.3,
                    "selection_time_seconds": 0.4,
                    "workbook_time_seconds": 0.5,
                    "export_time_seconds": 0.0,
                }
            ),
        )


def _settings(version: str, tmp_path: Path) -> Settings:
    return Settings(
        OPENAI_API_KEY="test-openai-key",
        OCR_ENGINE_VERSION=version,
        OCR_V2_TABLES_DIR=tmp_path / "tables",
        OCR_V2_SHADOW_OUTPUT_DIR=tmp_path / "shadow",
        OUTPUT_DIRECTORY=tmp_path / "output",
    )


def test_ocr_engine_version_defaults_to_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCR_ENGINE_VERSION", raising=False)

    settings = Settings(_env_file=None, OPENAI_API_KEY="test-openai-key")

    assert settings.ocr_engine_version == "v1"


def test_ocr_engine_version_rejects_invalid_value(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _settings("invalid", tmp_path)


def test_factory_selects_v1_v2_and_shadow_without_caller_changes(tmp_path: Path) -> None:
    v1 = _FakePipeline("v1", "v1.xlsx")
    v2 = _FakePipeline("v2", "v2.xlsx")

    assert (
        build_ocr_pipeline(
            _settings("v1", tmp_path),
            v1_builder=lambda *_: v1,
            v2_builder=lambda *_: v2,
        )
        is v1
    )
    assert (
        build_ocr_pipeline(
            _settings("v2", tmp_path),
            v1_builder=lambda *_: v1,
            v2_builder=lambda *_: v2,
        )
        is v2
    )
    shadow = build_ocr_pipeline(
        _settings("shadow", tmp_path),
        v1_builder=lambda *_: v1,
        v2_builder=lambda *_: v2,
    )

    assert isinstance(shadow, ShadowOCRPipeline)


def test_ocr_v2_pipeline_satisfies_interface_and_populates_context(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "ocr_v2_output.xlsx"
    pipeline = OCRV2Pipeline(
        tables_dir=tmp_path / "tables",
        output_xlsx=workbook_path,
        runner_factory=_FakeOCRV2Runner,
    )

    result = pipeline.process(_context())

    assert isinstance(pipeline, IOCRPipeline)
    assert result.pipeline_status is PipelineStatus.COMPLETED
    assert result.pipeline_errors == []
    assert result.generated_workbook is not None
    assert result.generated_workbook.output_file_path == str(workbook_path)
    assert result.generated_workbook.workbook_mode == "ocr_v2"
    assert result.generated_workbook.metrics_written == 2
    assert workbook_path.exists()
    assert pipeline.last_timing_breakdown == {
        "extraction_time_seconds": 0.1,
        "capture_time_seconds": 0.2,
        "registry_time_seconds": 0.05,
        "governance_time_seconds": 0.3,
        "selection_time_seconds": 0.4,
        "workbook_time_seconds": 0.5,
        "export_time_seconds": 0.0,
    }
    assert pipeline.last_run_audit == {"integrity_violations": ()}
    assert [entry.layer_name for entry in result.execution_results] == [
        "OCR V2 Pipeline"
    ]


def test_shadow_pipeline_runs_both_engines_serves_v1_and_persists_v2(
    tmp_path: Path,
) -> None:
    v1 = _FakePipeline("v1", "served_v1.xlsx")
    v2 = _FakePipeline("v2", "shadow_v2.xlsx")
    shadow = ShadowOCRPipeline(
        primary_pipeline=v1,
        shadow_pipeline=v2,
        output_dir=tmp_path / "shadow",
    )

    result = shadow.process(_context())

    assert result.generated_workbook is not None
    assert result.generated_workbook.output_file_path == "served_v1.xlsx"
    assert v1.calls == 1
    assert v2.calls == 1
    assert list((tmp_path / "shadow").glob("*_v2_context.json"))
    comparison_paths = list((tmp_path / "shadow").glob("*_comparison.json"))
    assert comparison_paths
    assert (tmp_path / "shadow" / "ocr_v2_shadow_mode_report.md").exists()
    assert (tmp_path / "shadow" / "ocr_v2_shadow_metrics.json").exists()
    assert (tmp_path / "shadow" / "ocr_v2_shadow_comparison_report.md").exists()
    assert (tmp_path / "shadow" / "ocr_v2_shadow_history.json").exists()
    assert (tmp_path / "shadow" / "ocr_v2_shadow_dashboard.json").exists()
    assert (tmp_path / "shadow" / "ocr_v2_shadow_trend_report.md").exists()
    comparison = json.loads(comparison_paths[0].read_text(encoding="utf-8"))
    assert comparison["production_output_source"] == "v1"
    assert comparison["v2_output_consumed_by_caller"] is False
    metrics = comparison["shadow_metrics"]
    assert metrics["document_identifier"] == (
        "Integration Test Company:2025:report.pdf"
    )
    assert metrics["v1_runtime_seconds"] >= 0
    assert metrics["v2_runtime_seconds"] >= 0
    assert metrics["v1_metrics_count"] == 0
    assert metrics["v2_metrics_count"] == 0
    assert metrics["v1_workbook_rows"] == 1
    assert metrics["v2_workbook_rows"] == 1
    assert metrics["v1_errors"] == []
    assert metrics["v2_errors"] == []
    assert metrics["v2_source_insufficient_count"] == 1
    assert metrics["comparison_status"] == "diverged_counts"
    assert metrics["v2_timing_breakdown"]["governance_time_seconds"] == 0.03
    metrics_payload = json.loads(
        (tmp_path / "shadow" / "ocr_v2_shadow_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert metrics_payload["latest_run"]["run_id"] == comparison["run_id"]
    history_payload = json.loads(
        (tmp_path / "shadow" / "ocr_v2_shadow_history.json").read_text(
            encoding="utf-8"
        )
    )
    assert [record["engine_version"] for record in history_payload["latest_records"]] == [
        "v1",
        "v2",
    ]
    assert {
        "document_id",
        "engine_version",
        "runtime",
        "metric_count",
        "source_insufficient_count",
        "workbook_rows",
        "comparison_status",
        "timestamp",
    }.issubset(history_payload["latest_records"][0])
    dashboard = json.loads(
        (tmp_path / "shadow" / "ocr_v2_shadow_dashboard.json").read_text(
            encoding="utf-8"
        )
    )
    assert dashboard["total_documents_processed"] == 1
    assert dashboard["total_shadow_runs"] == 1
    assert dashboard["average_v1_runtime"] >= 0
    assert dashboard["average_v2_runtime"] >= 0
    assert dashboard["comparison_status_breakdown"] == {"diverged_counts": 1}
    assert dashboard["v2_less_complete_count"] == 1
    assert dashboard["error_counts"] == {"runs_with_errors": 0, "v1": 0, "v2": 0}
