"""OCR pipeline orchestration package.

Import concrete classes from their modules to avoid circular imports while the
shared ``CompanyContext`` model is being initialized.
"""

from typing import Any

__all__ = [
    "IOCRPipeline",
    "LayerExecutionResult",
    "OCRPipeline",
    "PipelineLayerPartialFailure",
    "PipelineError",
    "PipelineStatus",
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
