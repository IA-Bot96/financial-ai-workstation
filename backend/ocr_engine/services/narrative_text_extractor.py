"""PDF narrative text extraction for OCR insights."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NarrativePage:
    """Extracted text from one PDF page."""

    page_number: int
    text: str


class NarrativeTextExtractor:
    """Extract page-level text from annual-report PDFs using PyMuPDF."""

    def __init__(
        self,
        pdf_loader: Callable[[str], Any] | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the extractor with injectable PDF loading."""

        self._pdf_loader = pdf_loader or self._load_pdf_document
        self._logger = log or logger

    def extract(self, pdf_path: str) -> list[NarrativePage]:
        """Extract text from all readable pages and skip corrupted pages."""

        document = self._pdf_loader(pdf_path)
        pages: list[NarrativePage] = []

        try:
            total_pages = len(document)
            for index in range(total_pages):
                page_number = index + 1
                try:
                    page = document.load_page(index)
                    text = page.get_text("text")
                except Exception:
                    self._logger.exception(
                        "Narrative page skipped due to extraction error",
                        extra={"page_number": page_number},
                    )
                    continue

                if text and text.strip():
                    pages.append(NarrativePage(page_number=page_number, text=text))
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

        self._logger.info(
            "Narrative text extraction complete",
            extra={"pages_extracted": len(pages)},
        )
        return pages

    @staticmethod
    def _load_pdf_document(pdf_path: str) -> Any:
        """Open a PDF document with PyMuPDF."""

        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF is required for narrative text extraction."
            ) from exc

        return fitz.open(pdf_path)
