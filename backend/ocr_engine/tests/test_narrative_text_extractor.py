"""Unit tests for narrative PDF text extraction."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.narrative_text_extractor import NarrativeTextExtractor
from ocr_engine.services.section_identifier import SectionIdentifier


class FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self, mode: str) -> str:
        assert mode == "text"
        return self._text


class FakeDocument:
    def __init__(self, pages: list[FakePage]) -> None:
        self._pages = pages
        self.closed = False

    def __len__(self) -> int:
        return len(self._pages)

    def load_page(self, index: int) -> FakePage:
        if index == 1:
            raise RuntimeError("corrupted page")
        return self._pages[index]

    def close(self) -> None:
        self.closed = True


def test_narrative_text_extractor_skips_corrupted_pages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document = FakeDocument(
        [
            FakePage("Business Review\nExport sales increased."),
            FakePage("bad"),
            FakePage("Outlook\nCapacity expansion is planned."),
        ]
    )
    extractor = NarrativeTextExtractor(pdf_loader=lambda _: document)

    with caplog.at_level(logging.INFO):
        pages = extractor.extract("annual_report.pdf")

    assert [page.page_number for page in pages] == [1, 3]
    assert document.closed is True
    assert "Narrative text extraction complete" in caplog.text


class ReadableFakeDocument:
    def __init__(self, pages: list[FakePage]) -> None:
        self._pages = pages
        self.closed = False

    def __len__(self) -> int:
        return len(self._pages)

    def load_page(self, index: int) -> FakePage:
        return self._pages[index]

    def close(self) -> None:
        self.closed = True


def test_narrative_text_extractor_uses_ocr_fallback_for_empty_pymupdf_text() -> None:
    document = ReadableFakeDocument(
        [
            FakePage(""),
            FakePage("Business Review\nExports increased."),
        ]
    )
    extractor = NarrativeTextExtractor(
        pdf_loader=lambda _: document,
        ocr_reader=lambda page, page_number: (
            "Chairman Review\nDemand improved." if page_number == 1 else ""
        ),
    )

    pages = extractor.extract("annual_report.pdf")

    assert [(page.page_number, page.text_source) for page in pages] == [
        (1, "ocr"),
        (2, "pymupdf"),
    ]
    assert pages[0].pymupdf is False
    assert pages[0].ocr is True
    assert pages[0].text.startswith("Chairman Review")


class QualityAwareOCRExtractor(NarrativeTextExtractor):
    def __init__(
        self,
        *,
        document: ReadableFakeDocument,
        pymupdf_ocr: str,
        tesseract_ocr: str,
    ) -> None:
        super().__init__(pdf_loader=lambda _: document)
        self._pymupdf_ocr = pymupdf_ocr
        self._tesseract_ocr = tesseract_ocr
        self.tesseract_calls = 0

    def _extract_pymupdf_ocr_text(self, page: FakePage, page_number: int) -> str:
        return self._pymupdf_ocr

    def _extract_tesseract_ocr_text(self, page: FakePage, page_number: int) -> str:
        self.tesseract_calls += 1
        return self._tesseract_ocr


def test_narrative_text_extractor_escalates_weak_pymupdf_ocr_to_tesseract() -> None:
    document = ReadableFakeDocument([FakePage("")])
    extractor = QualityAwareOCRExtractor(
        document=document,
        pymupdf_ocr=(
            "c\n"
            "te\n"
            "Social\n"
            "R\n"
            "ibilit\n"
            "MTL strongly believes in discharging its responsibilities."
        ),
        tesseract_ocr=(
            "Corporate Social\n"
            "Responsibility\n"
            "The company continued community, safety, employee, and "
            "environment initiatives during the year."
        ),
    )

    pages = extractor.extract("annual_report.pdf")

    assert len(pages) == 1
    assert pages[0].text.startswith("Corporate Social")
    assert pages[0].ocr_engine_selected == "tesseract_ocr"
    assert pages[0].ocr_escalated is True
    assert pages[0].ocr_recovered is True
    assert pages[0].pymupdf_ocr_confidence is not None
    assert pages[0].tesseract_ocr_confidence is not None
    assert pages[0].tesseract_ocr_confidence > pages[0].pymupdf_ocr_confidence
    assert extractor.tesseract_calls == 1

    identifier = SectionIdentifier()
    section_pages = identifier.identify_sections(pages)

    assert [(page.page_number, page.section) for page in section_pages] == [
        (1, "Sustainability")
    ]
    assert identifier.last_report.ocr_pages_escalated == 1
    assert identifier.last_report.ocr_pages_recovered == 1
    assert identifier.last_report.additional_accepted_pages == 1
    assert identifier.last_report.ocr_engine_counts == {"tesseract_ocr": 1}
    diagnostic = identifier.last_report.page_diagnostics[0]
    assert diagnostic.ocr_engine_selected == "tesseract_ocr"
    assert diagnostic.tesseract_ocr_confidence == pages[0].tesseract_ocr_confidence


def test_narrative_text_extractor_keeps_strong_pymupdf_ocr_without_escalation() -> None:
    document = ReadableFakeDocument([FakePage("")])
    extractor = QualityAwareOCRExtractor(
        document=document,
        pymupdf_ocr=(
            "Business Review\n"
            "Exports increased in the Middle East and management expects "
            "continued growth."
        ),
        tesseract_ocr="",
    )

    pages = extractor.extract("annual_report.pdf")

    assert pages[0].text.startswith("Business Review")
    assert pages[0].ocr_engine_selected == "pymupdf_ocr"
    assert pages[0].ocr_escalated is False
    assert pages[0].ocr_recovered is False
    assert pages[0].tesseract_ocr_confidence is None
    assert extractor.tesseract_calls == 0
