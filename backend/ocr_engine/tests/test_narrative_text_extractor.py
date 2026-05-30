"""Unit tests for narrative PDF text extraction."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.narrative_text_extractor import NarrativeTextExtractor


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
