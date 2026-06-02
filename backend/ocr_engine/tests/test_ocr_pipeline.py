"""Unit tests for the OCR pipeline orchestrator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.pipeline.models.layer_execution_result import LayerExecutionResult
from ocr_engine.pipeline.models.pipeline_error import PipelineError
from ocr_engine.pipeline.models.pipeline_status import PipelineStatus
from ocr_engine.pipeline.ocr_pipeline import OCRPipeline
from shared.models.company_context import CompanyContext
from shared.models.report import Report


class FakeLayer:
    """Test double for a successful pipeline layer."""

    def __init__(self, name: str, calls: list[str]) -> None:
        self._name = name
        self._calls = calls

    def process(self, context: CompanyContext) -> CompanyContext:
        self._calls.append(self._name)
        return context


class FailingLayer(FakeLayer):
    """Test double for a failed pipeline layer."""

    def process(self, context: CompanyContext) -> CompanyContext:
        self._calls.append(self._name)
        raise RuntimeError("planned failure")


class PartialFailingLayer(FakeLayer):
    """Test double for a layer that isolates one failed report year."""

    def process(self, context: CompanyContext) -> CompanyContext:
        self._calls.append(self._name)
        raise PipelineLayerPartialFailure(
            ["Report year 2023 failed table detection: missing file"],
            context=context,
        )


def _context() -> CompanyContext:
    return CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2025",
                company_name="Maple Leaf Cement Factory Limited",
                year=2025,
                file_name="MLCF_2025_Annual_Report.pdf",
                file_path="/reports/MLCF_2025_Annual_Report.pdf",
            )
        ],
    )


def _pipeline_with_layers(layers: list[object]) -> OCRPipeline:
    return OCRPipeline(
        table_detector=layers[0],
        table_classifier=layers[1],
        table_extractor=layers[2],
        validator=layers[3],
        metric_normalizer=layers[4],
        insights_extractor=layers[5],
        financial_year_consolidator=layers[6],
        workbook_population_service=layers[7],
    )


def test_ocr_pipeline_runs_layers_in_order_and_marks_completed() -> None:
    calls: list[str] = []
    layer_names = [
        "Table Detection",
        "Classification",
        "Table Extraction",
        "Validation",
        "Metric Normalization",
        "Insights Extraction",
        "Financial Year Consolidation",
        "Workbook Population",
    ]
    pipeline = _pipeline_with_layers([FakeLayer(name, calls) for name in layer_names])

    result = pipeline.process(_context())

    assert result.pipeline_status is PipelineStatus.COMPLETED
    assert calls == layer_names
    assert result.pipeline_errors == []
    assert [item.layer_name for item in result.execution_results] == layer_names
    assert all(item.success for item in result.execution_results)


def test_ocr_pipeline_runs_query_engine_bundle_step_after_workbook_population() -> None:
    calls: list[str] = []
    layer_names = [
        "Table Detection",
        "Classification",
        "Table Extraction",
        "Validation",
        "Metric Normalization",
        "Insights Extraction",
        "Financial Year Consolidation",
        "Workbook Population",
        "Query Engine Bundle Generation",
    ]
    layers = [FakeLayer(name, calls) for name in layer_names]
    pipeline = OCRPipeline(
        table_detector=layers[0],
        table_classifier=layers[1],
        table_extractor=layers[2],
        validator=layers[3],
        metric_normalizer=layers[4],
        insights_extractor=layers[5],
        financial_year_consolidator=layers[6],
        workbook_population_service=layers[7],
        query_engine_bundle_service=layers[8],
    )

    result = pipeline.process(_context())

    assert result.pipeline_status is PipelineStatus.COMPLETED
    assert calls == layer_names
    assert [item.layer_name for item in result.execution_results] == layer_names


def test_ocr_pipeline_records_layer_error_and_continues() -> None:
    calls: list[str] = []
    layers: list[object] = [
        FakeLayer("Table Detection", calls),
        FailingLayer("Classification", calls),
        FakeLayer("Table Extraction", calls),
        FakeLayer("Validation", calls),
        FakeLayer("Metric Normalization", calls),
        FakeLayer("Insights Extraction", calls),
        FakeLayer("Financial Year Consolidation", calls),
        FakeLayer("Workbook Population", calls),
    ]

    result = _pipeline_with_layers(layers).process(_context())

    assert result.pipeline_status is PipelineStatus.FAILED
    assert calls == [
        "Table Detection",
        "Classification",
        "Table Extraction",
        "Validation",
        "Metric Normalization",
        "Insights Extraction",
        "Financial Year Consolidation",
        "Workbook Population",
    ]
    assert result.pipeline_errors == [
        PipelineError(
            layer_name="Classification",
            error_message="planned failure",
        )
    ]
    assert result.execution_results[1].layer_name == "Classification"
    assert result.execution_results[1].success is False


def test_ocr_pipeline_centralizes_partial_year_pipeline_errors() -> None:
    calls: list[str] = []
    layers: list[object] = [
        PartialFailingLayer("Table Detection", calls),
        FakeLayer("Classification", calls),
        FakeLayer("Table Extraction", calls),
        FakeLayer("Validation", calls),
        FakeLayer("Metric Normalization", calls),
        FakeLayer("Insights Extraction", calls),
        FakeLayer("Financial Year Consolidation", calls),
        FakeLayer("Workbook Population", calls),
    ]

    result = _pipeline_with_layers(layers).process(_context())

    assert result.pipeline_status is PipelineStatus.FAILED
    assert calls == [
        "Table Detection",
        "Classification",
        "Table Extraction",
        "Validation",
        "Metric Normalization",
        "Insights Extraction",
        "Financial Year Consolidation",
        "Workbook Population",
    ]
    assert result.pipeline_errors == [
        PipelineError(
            layer_name="Table Detection",
            error_message="Report year 2023 failed table detection: missing file",
        )
    ]
    assert result.execution_results[0].layer_name == "Table Detection"
    assert result.execution_results[0].success is False
    assert all(item.success for item in result.execution_results[1:])


def test_ocr_pipeline_execution_results_reflect_mixed_failures() -> None:
    calls: list[str] = []
    layers: list[object] = [
        FakeLayer("Table Detection", calls),
        PartialFailingLayer("Classification", calls),
        FailingLayer("Table Extraction", calls),
        FakeLayer("Validation", calls),
        FakeLayer("Metric Normalization", calls),
        FakeLayer("Insights Extraction", calls),
        FakeLayer("Financial Year Consolidation", calls),
        FakeLayer("Workbook Population", calls),
    ]

    result = _pipeline_with_layers(layers).process(_context())

    success_by_layer = {
        item.layer_name: item.success for item in result.execution_results
    }
    assert success_by_layer == {
        "Table Detection": True,
        "Classification": False,
        "Table Extraction": False,
        "Validation": True,
        "Metric Normalization": True,
        "Insights Extraction": True,
        "Financial Year Consolidation": True,
        "Workbook Population": True,
    }
    assert [error.layer_name for error in result.pipeline_errors] == [
        "Classification",
        "Table Extraction",
    ]


def test_layer_execution_result_rejects_negative_time() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LayerExecutionResult(
            layer_name="Validation",
            execution_time_seconds=-1,
            success=False,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than_equal"
