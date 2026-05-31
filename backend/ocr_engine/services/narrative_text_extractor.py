"""PDF narrative text extraction for OCR insights."""

from __future__ import annotations

from dataclasses import dataclass
import io
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NarrativePage:
    """Extracted text from one PDF page."""

    page_number: int
    text: str
    text_source: str = "pymupdf"
    pymupdf: bool = True
    ocr: bool = False


class NarrativeTextExtractor:
    """Extract page-level text from annual-report PDFs using PyMuPDF."""

    def __init__(
        self,
        pdf_loader: Callable[[str], Any] | None = None,
        ocr_reader: Callable[[Any, int], str] | None = None,
        enable_ocr_fallback: bool = True,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the extractor with injectable PDF loading."""

        self._pdf_loader = pdf_loader or self._load_pdf_document
        self._ocr_reader = ocr_reader or self._extract_ocr_text
        self._enable_ocr_fallback = enable_ocr_fallback
        self._logger = log or logger
        self._last_total_pages_processed = 0

    @property
    def last_total_pages_processed(self) -> int:
        """Return the total page count from the most recent extraction run."""

        return self._last_total_pages_processed

    def extract(self, pdf_path: str) -> list[NarrativePage]:
        """Extract text from all readable pages and skip corrupted pages."""

        self._last_total_pages_processed = 0
        document = self._pdf_loader(pdf_path)
        pages: list[NarrativePage] = []

        try:
            total_pages = len(document)
            self._last_total_pages_processed = total_pages
            for index in range(total_pages):
                page_number = index + 1
                try:
                    page = document.load_page(index)
                    pymupdf_text = page.get_text("text") or ""
                except Exception:
                    self._logger.exception(
                        "Narrative page skipped due to extraction error",
                        extra={"page_number": page_number},
                    )
                    continue

                ocr_text = ""
                if not pymupdf_text.strip() and self._enable_ocr_fallback:
                    try:
                        ocr_text = self._ocr_reader(page, page_number) or ""
                    except Exception:
                        self._logger.exception(
                            "Narrative OCR fallback failed",
                            extra={"page_number": page_number},
                        )
                        ocr_text = ""

                text, text_source = _select_text_source(pymupdf_text, ocr_text)
                pages.append(
                    NarrativePage(
                        page_number=page_number,
                        text=text,
                        text_source=text_source,
                        pymupdf=bool(pymupdf_text.strip()),
                        ocr=bool(ocr_text.strip()),
                    )
                )
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

        self._logger.info(
            "Narrative text extraction complete",
            extra={
                "total_pages_processed": self._last_total_pages_processed,
                "pages_extracted": sum(1 for page in pages if page.text.strip()),
                "pages_with_pymupdf_text": sum(1 for page in pages if page.pymupdf),
                "pages_with_ocr_text": sum(1 for page in pages if page.ocr),
                "total_text_characters": sum(len(page.text) for page in pages),
            },
        )
        return pages

    def _extract_ocr_text(self, page: Any, page_number: int) -> str:
        """Extract OCR text from a page using optional local OCR capabilities."""

        get_textpage_ocr = getattr(page, "get_textpage_ocr", None)
        if callable(get_textpage_ocr):
            try:
                text_page = get_textpage_ocr(language="eng", dpi=200, full=True)
                return page.get_text("text", textpage=text_page) or ""
            except Exception:
                self._logger.debug(
                    "PyMuPDF OCR fallback unavailable for page",
                    extra={"page_number": page_number},
                    exc_info=True,
                )

        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            self._logger.debug(
                "pytesseract is not installed; OCR fallback skipped",
                extra={"page_number": page_number},
            )
            return ""

        get_pixmap = getattr(page, "get_pixmap", None)
        if not callable(get_pixmap):
            return ""

        pixmap = get_pixmap(alpha=False)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image) or ""

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


def _select_text_source(pymupdf_text: str, ocr_text: str) -> tuple[str, str]:
    """Return selected page text and its source label."""

    if pymupdf_text.strip():
        return pymupdf_text, "pymupdf"
    if ocr_text.strip():
        return ocr_text, "ocr"
    return "", "none"
