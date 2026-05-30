"""FastAPI route adapter for OCR pipeline execution."""

from typing import Any, Callable

try:
    from fastapi import APIRouter, Depends
except ImportError:  # pragma: no cover - FastAPI is provided by the API runtime.
    APIRouter = None

    def Depends(dependency: Callable[..., Any]) -> Callable[..., Any]:
        """Fallback that keeps this example module importable without FastAPI."""

        return dependency

from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline
from shared.models.company_context import CompanyContext


class _UnavailableRouter:
    """Import-time placeholder used only when FastAPI is not installed."""

    @staticmethod
    def post(*_: Any, **__: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Return a no-op decorator for environments without FastAPI."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator


router = APIRouter(tags=["OCR"]) if APIRouter is not None else _UnavailableRouter()


def get_ocr_pipeline() -> IOCRPipeline:
    """Return the configured OCR pipeline dependency.

    The application composition root should override this dependency with a
    fully wired ``OCRPipeline`` instance. OCR workflow logic belongs inside the
    pipeline service, not inside this route.
    """

    raise RuntimeError("OCRPipeline dependency has not been configured.")


@router.post("/ocr/process", response_model=CompanyContext)
def process_ocr(
    context: CompanyContext,
    ocr_pipeline: IOCRPipeline = Depends(get_ocr_pipeline),
) -> CompanyContext:
    """Execute the OCR pipeline for a company context."""

    return ocr_pipeline.process(context)
