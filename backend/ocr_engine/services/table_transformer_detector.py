"""Microsoft Table Transformer implementation for table page detection."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import Any, Callable

from ocr_engine.constants.detection_constants import (
    TABLE_DETECTION_CONFIDENCE_THRESHOLD,
    TABLE_DETECTION_MODEL_NAME,
)
from ocr_engine.models.table_detection_result import (
    DetectedPage,
    FailedPage,
    TableDetectionResult,
)
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.interfaces.table_detector import ITableDetector
from shared.models.company_context import CompanyContext

logger = logging.getLogger(__name__)


class TableTransformerDetector(ITableDetector):
    """Detect PDF pages containing tables using Microsoft Table Transformer.

    Dependencies can be injected for testing or for future detector backends.
    When omitted, the implementation lazy-loads PyMuPDF, Pillow, Torch, and the
    Hugging Face Table Transformer model.
    """

    def __init__(
        self,
        *,
        processor: Any | None = None,
        model: Any | None = None,
        pdf_loader: Callable[[str], Any] | None = None,
        page_renderer: Callable[[Any, int], Any] | None = None,
        confidence_threshold: float = TABLE_DETECTION_CONFIDENCE_THRESHOLD,
        model_name: str = TABLE_DETECTION_MODEL_NAME,
        device: str | None = None,
        log: logging.Logger | None = None,
        torch_module: Any | None = None,
    ) -> None:
        """Initialize a table detector with optional injected dependencies."""

        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1.")
        if (processor is None) != (model is None):
            raise ValueError("processor and model must be injected together.")

        self._confidence_threshold = confidence_threshold
        self._model_name = model_name
        self._pdf_loader = pdf_loader or self._load_pdf_document
        self._page_renderer = page_renderer or self._render_pdf_page
        self._logger = log or logger
        self._torch = torch_module or self._try_import_torch()
        self._device = device or self._resolve_device()

        if processor is None and model is None:
            processor, model = self._load_processor_and_model(model_name)

        self._processor = processor
        self._model = model
        self._prepare_model()

    def detect_tables_for_context(self, context: CompanyContext) -> CompanyContext:
        """Detect table pages for every report and store results by report year.

        Each annual report is processed independently and written to
        ``context.table_detection_results[report.year]``. Results from different
        years are never combined.
        """

        self._logger.info(
            "Starting table detection for company context",
            extra={
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )

        failures: list[str] = []
        for report in context.reports:
            self._logger.info(
                "Detecting tables for report year %s",
                report.year,
                extra={
                    "company_name": context.company_name,
                    "year": report.year,
                    "file_path": report.file_path,
                },
            )
            try:
                context.table_detection_results[report.year] = self.detect_tables(
                    report.file_path,
                    year=report.year,
                )
            except Exception as exc:
                failures.append(
                    f"Report year {report.year} failed table detection: "
                    f"{_error_message(exc)}"
                )
                context.table_detection_results[report.year] = TableDetectionResult(
                    detected_pages=[],
                    failed_pages=[],
                    total_pages_processed=0,
                )
                self._logger.exception(
                    "Table detection failed for report; continuing",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                        "file_path": report.file_path,
                    },
                )
                continue

        self._logger.info(
            "Company context table detection complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.table_detection_results),
            },
        )
        if failures:
            raise PipelineLayerPartialFailure(failures, context=context)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run table detection as a pipeline layer."""

        return self.detect_tables_for_context(context)

    def detect_tables(self, pdf_path: str, year: int) -> TableDetectionResult:
        """Return page-level table detection metadata for a PDF."""

        detected_pages: dict[int, int] = {}
        failed_pages: list[FailedPage] = []
        document = None
        total_pages_processed = 0

        try:
            document = self._pdf_loader(pdf_path)
            total_pages_processed = len(document)
        except Exception:
            self._logger.exception(
                "Failed to open PDF for table detection",
                extra={"pdf_path": pdf_path},
            )
            raise

        try:
            for page_index in range(total_pages_processed):
                page_number = page_index + 1
                self._logger.debug(
                    "Processing page %s/%s",
                    page_number,
                    total_pages_processed,
                    extra={
                        "page": page_number,
                        "total_pages": total_pages_processed,
                    },
                )

                try:
                    image = self._page_renderer(document, page_index)
                    tables_detected = self._count_tables_in_image(image)
                    if tables_detected > 0:
                        detected_pages[page_number] = tables_detected
                        self._logger.debug(
                            "Tables detected on page %s",
                            page_number,
                            extra={
                                "page": page_number,
                                "tables_detected": tables_detected,
                            },
                        )
                except Exception as exc:
                    failed_pages.append(
                        FailedPage(
                            year=year,
                            page_number=page_number,
                            error_message=_error_message(exc),
                        )
                    )
                    self._logger.exception(
                        "Page skipped due to error",
                        extra={"page": page_number},
                    )
                    continue
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

        result = TableDetectionResult(
            detected_pages=[
                DetectedPage(
                    year=year,
                    page_number=page_number,
                    tables_detected=tables_detected,
                )
                for page_number, tables_detected in sorted(detected_pages.items())
            ],
            failed_pages=failed_pages,
            total_pages_processed=total_pages_processed,
        )
        self._logger.info(
            "Detection complete",
            extra={
                "detected_pages": [
                    detected_page.model_dump()
                    for detected_page in result.detected_pages
                ],
                "failed_pages": [
                    failed_page.model_dump() for failed_page in result.failed_pages
                ],
                "total_pages_processed": result.total_pages_processed,
            },
        )
        return result

    def _count_tables_in_image(self, image: Any) -> int:
        """Run the detection model for a rendered page image."""

        inputs = self._processor(images=image, return_tensors="pt")
        inputs = self._move_to_device(inputs)

        context = self._torch.no_grad() if self._torch is not None else nullcontext()
        with context:
            outputs = self._model(**inputs)

        detections = self._processor.post_process_object_detection(
            outputs,
            threshold=self._confidence_threshold,
            target_sizes=self._target_sizes_for(image),
        )
        return self._count_detections(detections)

    def _move_to_device(self, inputs: Any) -> Any:
        """Move processor tensors to the configured torch device when possible."""

        if not self._device:
            return inputs
        if hasattr(inputs, "to"):
            return inputs.to(self._device)
        if isinstance(inputs, dict):
            return {
                key: value.to(self._device) if hasattr(value, "to") else value
                for key, value in inputs.items()
            }
        return inputs

    def _target_sizes_for(self, image: Any) -> Any:
        """Build target image sizes in the format expected by Transformers."""

        height_width = [image.size[::-1]]
        if self._torch is None:
            return height_width
        return self._torch.tensor(height_width, device=self._device)

    @staticmethod
    def _count_detections(detections: Any) -> int:
        """Return the number of table detections from model post-processing."""

        if not detections:
            return 0

        first_result = detections[0]
        if isinstance(first_result, dict):
            for key in ("scores", "labels", "boxes"):
                values = first_result.get(key)
                if values is not None:
                    return len(values)
            return 0

        return len(first_result)

    def _prepare_model(self) -> None:
        """Move model to device and set evaluation mode when supported."""

        if self._device and hasattr(self._model, "to"):
            self._model.to(self._device)
        if hasattr(self._model, "eval"):
            self._model.eval()

    def _resolve_device(self) -> str | None:
        """Resolve the torch device for inference."""

        if self._torch is None:
            return None
        return "cuda" if self._torch.cuda.is_available() else "cpu"

    @staticmethod
    def _try_import_torch() -> Any | None:
        """Import torch when available without making module import fail."""

        try:
            import torch
        except ImportError:
            return None
        return torch

    def _load_processor_and_model(self, model_name: str) -> tuple[Any, Any]:
        """Load the Hugging Face processor and Table Transformer model."""

        if self._torch is None:
            raise RuntimeError(
                "Torch is required when processor and model are not injected."
            )

        try:
            from transformers import AutoImageProcessor
            from transformers import TableTransformerForObjectDetection
        except ImportError as exc:
            raise RuntimeError(
                "transformers is required to load the Table Transformer detector."
            ) from exc

        processor = AutoImageProcessor.from_pretrained(model_name)
        model = TableTransformerForObjectDetection.from_pretrained(model_name)
        return processor, model

    @staticmethod
    def _load_pdf_document(pdf_path: str) -> Any:
        """Open a PDF document with PyMuPDF."""

        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF table detection.") from exc

        return fitz.open(pdf_path)

    @staticmethod
    def _render_pdf_page(document: Any, page_index: int) -> Any:
        """Render a PDF page to a Pillow RGB image using PyMuPDF."""

        try:
            import fitz
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF and Pillow are required to render PDF pages."
            ) from exc

        page = document.load_page(page_index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return Image.frombytes(
            "RGB",
            (pixmap.width, pixmap.height),
            pixmap.samples,
        )


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for logging and result metadata."""

    return str(exc) or exc.__class__.__name__
