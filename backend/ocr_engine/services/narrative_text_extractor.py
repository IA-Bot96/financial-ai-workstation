"""PDF narrative text extraction for OCR insights."""

from __future__ import annotations

from dataclasses import dataclass
import io
import logging
import re
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
    ocr_engine_selected: str | None = None
    pymupdf_ocr_confidence: float | None = None
    tesseract_ocr_confidence: float | None = None
    ocr_escalation_reason: str | None = None
    ocr_escalated: bool = False
    ocr_recovered: bool = False
    ocr_heading_alias_match_count: int = 0
    ocr_heading_fragmentation_ratio: float = 0.0
    ocr_single_character_line_count: int = 0


class NarrativeTextExtractor:
    """Extract page-level text from annual-report PDFs using PyMuPDF."""

    _ocr_confidence_threshold = 0.55
    _heading_fragmentation_threshold = 0.35

    def __init__(
        self,
        pdf_loader: Callable[[str], Any] | None = None,
        ocr_reader: Callable[[Any, int], str] | None = None,
        enable_ocr_fallback: bool = True,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the extractor with injectable PDF loading."""

        self._pdf_loader = pdf_loader or self._load_pdf_document
        self._custom_ocr_reader = ocr_reader
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
                ocr_selection = _OCRSelection(text="")
                if not pymupdf_text.strip() and self._enable_ocr_fallback:
                    try:
                        ocr_selection = self._extract_ocr_text(page, page_number)
                        ocr_text = ocr_selection.text
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
                        ocr_engine_selected=ocr_selection.engine,
                        pymupdf_ocr_confidence=(
                            ocr_selection.pymupdf_confidence
                        ),
                        tesseract_ocr_confidence=(
                            ocr_selection.tesseract_confidence
                        ),
                        ocr_escalation_reason=(
                            ocr_selection.escalation_reason
                        ),
                        ocr_escalated=ocr_selection.escalated,
                        ocr_recovered=ocr_selection.recovered,
                        ocr_heading_alias_match_count=(
                            ocr_selection.heading_alias_match_count
                        ),
                        ocr_heading_fragmentation_ratio=(
                            ocr_selection.heading_fragmentation_ratio
                        ),
                        ocr_single_character_line_count=(
                            ocr_selection.single_character_line_count
                        ),
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
                "ocr_pages_escalated": sum(
                    1 for page in pages if page.ocr_escalated
                ),
                "ocr_pages_recovered": sum(
                    1 for page in pages if page.ocr_recovered
                ),
                "additional_accepted_pages": sum(
                    1 for page in pages if page.ocr_recovered
                ),
                "ocr_engine_counts": _count_values(
                    page.ocr_engine_selected
                    for page in pages
                    if page.ocr_engine_selected
                ),
                "total_text_characters": sum(len(page.text) for page in pages),
            },
        )
        return pages

    def _extract_ocr_text(self, page: Any, page_number: int) -> "_OCRSelection":
        """Extract OCR text from a page using quality-aware OCR routing."""

        if self._custom_ocr_reader is not None:
            text = self._custom_ocr_reader(page, page_number) or ""
            return _OCRSelection(
                text=text,
                engine="custom",
                pymupdf_confidence=None,
                tesseract_confidence=None,
            )

        pymupdf_text = self._extract_pymupdf_ocr_text(page, page_number)
        pymupdf_quality = self._diagnose_ocr_quality(
            text=pymupdf_text,
            engine="pymupdf_ocr",
            page_number=page_number,
        )
        escalation_reasons = self._escalation_reasons(pymupdf_quality)

        tesseract_quality: _OCRQualityDiagnostic | None = None
        if escalation_reasons:
            tesseract_text = self._extract_tesseract_ocr_text(page, page_number)
            tesseract_quality = self._diagnose_ocr_quality(
                text=tesseract_text,
                engine="tesseract_ocr",
                page_number=page_number,
            )

        selected = self._select_ocr_candidate(pymupdf_quality, tesseract_quality)
        recovered = (
            selected.engine == "tesseract_ocr"
            and not pymupdf_quality.accepted
            and selected.accepted
        )
        escalation_reason = ",".join(escalation_reasons) or None

        self._logger.debug(
            "Narrative OCR routing decision",
            extra={
                "page_number": page_number,
                "ocr_engine_selected": selected.engine if selected.text else None,
                "pymupdf_ocr_confidence": pymupdf_quality.confidence_score,
                "tesseract_ocr_confidence": (
                    tesseract_quality.confidence_score
                    if tesseract_quality is not None
                    else None
                ),
                "ocr_escalation_reason": escalation_reason,
                "ocr_escalated": bool(escalation_reasons),
                "ocr_recovered": recovered,
            },
        )

        return _OCRSelection(
            text=selected.text,
            engine=selected.engine if selected.text else None,
            pymupdf_confidence=pymupdf_quality.confidence_score,
            tesseract_confidence=(
                tesseract_quality.confidence_score
                if tesseract_quality is not None
                else None
            ),
            escalation_reason=escalation_reason,
            escalated=bool(escalation_reasons),
            recovered=recovered,
            heading_alias_match_count=selected.heading_alias_match_count,
            heading_fragmentation_ratio=selected.heading_fragmentation_ratio,
            single_character_line_count=selected.single_character_line_count,
        )

    def _extract_pymupdf_ocr_text(self, page: Any, page_number: int) -> str:
        """Extract OCR text with PyMuPDF's OCR text-page integration."""

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

        return ""

    def _extract_tesseract_ocr_text(self, page: Any, page_number: int) -> str:
        """Extract OCR text by rendering the page and calling pytesseract."""

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

        try:
            pixmap = get_pixmap(dpi=200, alpha=False)
        except TypeError:
            try:
                import fitz
            except ImportError:
                pixmap = get_pixmap(alpha=False)
            else:
                zoom = 200 / 72
                pixmap = get_pixmap(
                    matrix=fitz.Matrix(zoom, zoom),
                    alpha=False,
                )
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image) or ""

    def _diagnose_ocr_quality(
        self,
        *,
        text: str,
        engine: str,
        page_number: int,
    ) -> "_OCRQualityDiagnostic":
        """Score OCR text quality using the same classifier used downstream."""

        if not text.strip():
            return _OCRQualityDiagnostic(engine=engine, text="")

        from ocr_engine.services.section_identifier import SectionIdentifier

        page = NarrativePage(
            page_number=page_number,
            text=text,
            text_source="ocr",
            pymupdf=False,
            ocr=True,
            ocr_engine_selected=engine,
        )
        identifier = SectionIdentifier()
        identifier.identify_sections([page])
        page_diagnostic = identifier.last_report.page_diagnostics[0]

        return _OCRQualityDiagnostic(
            engine=engine,
            text=text,
            confidence_score=page_diagnostic.confidence_score,
            accepted=page_diagnostic.detected_section is not None,
            rejection_reason=page_diagnostic.rejection_reason,
            heading_alias_match_count=_heading_alias_match_count(text, identifier),
            heading_fragmentation_ratio=_heading_fragmentation_ratio(text),
            single_character_line_count=_single_character_heading_line_count(text),
            narrative_density=page_diagnostic.narrative_density,
        )

    def _escalation_reasons(
        self,
        quality: "_OCRQualityDiagnostic",
    ) -> list[str]:
        """Return reasons to escalate from PyMuPDF OCR to direct Tesseract."""

        reasons: list[str] = []
        if not quality.text.strip():
            reasons.append("pymupdf_ocr_empty")
            return reasons
        if quality.confidence_score < self._ocr_confidence_threshold:
            reasons.append("classifier_confidence_below_threshold")
        if (
            quality.heading_fragmentation_ratio
            > self._heading_fragmentation_threshold
        ):
            reasons.append("heading_fragmentation_exceeds_threshold")
        if quality.heading_alias_match_count == 0:
            reasons.append("weak_heading_alias_match")
        return reasons

    @staticmethod
    def _select_ocr_candidate(
        pymupdf_quality: "_OCRQualityDiagnostic",
        tesseract_quality: "_OCRQualityDiagnostic | None",
    ) -> "_OCRQualityDiagnostic":
        """Return the OCR candidate with the strongest classifier signal."""

        if tesseract_quality is None or not tesseract_quality.text.strip():
            return pymupdf_quality
        if tesseract_quality.confidence_score > pymupdf_quality.confidence_score:
            return tesseract_quality
        if tesseract_quality.confidence_score < pymupdf_quality.confidence_score:
            return pymupdf_quality
        if tesseract_quality.quality_score > pymupdf_quality.quality_score:
            return tesseract_quality
        return pymupdf_quality

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


@dataclass(frozen=True)
class _OCRSelection:
    """Selected OCR text and routing diagnostics for one page."""

    text: str
    engine: str | None = None
    pymupdf_confidence: float | None = None
    tesseract_confidence: float | None = None
    escalation_reason: str | None = None
    escalated: bool = False
    recovered: bool = False
    heading_alias_match_count: int = 0
    heading_fragmentation_ratio: float = 0.0
    single_character_line_count: int = 0


@dataclass(frozen=True)
class _OCRQualityDiagnostic:
    """Quality signals for one OCR engine's page text."""

    engine: str
    text: str
    confidence_score: float = 0.0
    accepted: bool = False
    rejection_reason: str | None = None
    heading_alias_match_count: int = 0
    heading_fragmentation_ratio: float = 0.0
    single_character_line_count: int = 0
    narrative_density: float = 0.0

    @property
    def quality_score(self) -> float:
        """Return a bounded tie-break score for equally confident OCR text."""

        score = self.confidence_score
        score += min(0.2, self.heading_alias_match_count * 0.05)
        score += min(0.15, self.narrative_density * 0.15)
        score -= min(0.2, self.heading_fragmentation_ratio * 0.2)
        score -= min(0.15, self.single_character_line_count * 0.02)
        return round(max(0.0, min(score, 1.0)), 3)


def _heading_alias_match_count(text: str, identifier: Any) -> int:
    """Count section aliases that match the OCR heading area."""

    from ocr_engine.services.section_identifier import (
        _alias_matches_heading,
        _contains_normalized_phrase,
        _heading_block,
        _normalize_text,
    )

    heading_area = _normalize_text(text[:1200])
    heading_block = _heading_block(text)
    top_heading_block = _normalize_text(text[:500])
    matches: set[str] = set()

    for aliases in getattr(identifier, "_section_aliases", {}).values():
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if not normalized_alias:
                continue
            if (
                _alias_matches_heading(normalized_alias, heading_block)
                or _alias_matches_heading(normalized_alias, top_heading_block)
                or _contains_normalized_phrase(heading_area, normalized_alias)
            ):
                matches.add(normalized_alias)

    return len(matches)


def _heading_fragmentation_ratio(text: str, max_lines: int = 12) -> float:
    """Estimate OCR heading fragmentation from the first lines of text."""

    lines = _heading_lines(text, max_lines=max_lines)
    if not lines:
        return 0.0
    fragmented_count = sum(1 for line in lines if _is_fragmented_heading_line(line))
    return round(fragmented_count / len(lines), 3)


def _single_character_heading_line_count(text: str, max_lines: int = 12) -> int:
    """Count one-character OCR fragments in the page heading area."""

    count = 0
    for line in _heading_lines(text, max_lines=max_lines):
        alnum = re.sub(r"[^A-Za-z0-9]", "", line)
        if 0 < len(alnum) <= 1:
            count += 1
    return count


def _heading_lines(text: str, *, max_lines: int) -> list[str]:
    """Return stripped non-empty heading lines."""

    return [line.strip() for line in text.splitlines() if line.strip()][:max_lines]


def _is_fragmented_heading_line(line: str) -> bool:
    """Return whether a heading line appears fragmented by OCR."""

    alnum = re.sub(r"[^A-Za-z0-9]", "", line)
    if not alnum:
        return False
    words = re.findall(r"[A-Za-z0-9]+", line)
    return len(alnum) <= 3 or (len(words) <= 2 and len(line) <= 10)


def _count_values(values: Any) -> dict[str, int]:
    """Return stable value counts for extraction diagnostics."""

    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))
