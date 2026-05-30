"""Unit tests for narrative section identification."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.narrative_text_extractor import NarrativePage
from ocr_engine.services.section_identifier import SectionIdentifier


def test_section_identifier_keeps_relevant_sections_and_ignores_boilerplate() -> None:
    pages = [
        NarrativePage(1, "Business Review\nExports increased in the Middle East."),
        NarrativePage(2, "Capacity expansion continued during the year."),
        NarrativePage(3, "Independent Auditor's Report\nOpinion on statements."),
    ]

    section_pages = SectionIdentifier().identify_sections(pages)

    assert [(page.page_number, page.section) for page in section_pages] == [
        (1, "Business Review"),
        (2, "Business Review"),
    ]
