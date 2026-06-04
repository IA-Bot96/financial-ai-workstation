"""OCR pipeline orchestration package.

Import concrete classes from their modules to avoid circular imports while the
shared ``CompanyContext`` model is being initialized.
"""

from typing import Any

__all__ = [
    "IOCRPipeline",
    "LayerExecutionResult",
    "OCREngineVersion",
    "OCRPipeline",
    "OCRV2Pipeline",
    "PipelineLayerPartialFailure",
    "PipelineError",
    "PipelineStatus",
    "ShadowOCRPipeline",
    "build_ocr_pipeline",
    "build_v1_pipeline",
    "build_v2_pipeline",
]


def __getattr__(name: str) -> Any:
    """Lazily expose pipeline classes without creating import cycles."""

    if name == "IOCRPipeline":
        from .interfaces.ocr_pipeline import IOCRPipeline

        return IOCRPipeline
    if name == "LayerExecutionResult":
        from .models.layer_execution_result import LayerExecutionResult

        return LayerExecutionResult
    if name == "OCRPipeline":
        from .ocr_pipeline import OCRPipeline

        return OCRPipeline
    if name == "OCRV2Pipeline":
        from .ocr_v2_pipeline import OCRV2Pipeline

        return OCRV2Pipeline
    if name == "ShadowOCRPipeline":
        from .shadow_ocr_pipeline import ShadowOCRPipeline

        return ShadowOCRPipeline
    if name in {
        "OCREngineVersion",
        "build_ocr_pipeline",
        "build_v1_pipeline",
        "build_v2_pipeline",
    }:
        from .factory import (
            OCREngineVersion,
            build_ocr_pipeline,
            build_v1_pipeline,
            build_v2_pipeline,
        )

        return {
            "OCREngineVersion": OCREngineVersion,
            "build_ocr_pipeline": build_ocr_pipeline,
            "build_v1_pipeline": build_v1_pipeline,
            "build_v2_pipeline": build_v2_pipeline,
        }[name]
    if name == "PipelineLayerPartialFailure":
        from .exceptions import PipelineLayerPartialFailure

        return PipelineLayerPartialFailure
    if name == "PipelineError":
        from .models.pipeline_error import PipelineError

        return PipelineError
    if name == "PipelineStatus":
        from .models.pipeline_status import PipelineStatus

        return PipelineStatus

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
