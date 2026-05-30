"""Rule-based annual-report narrative section identification."""

from __future__ import annotations

from dataclasses import dataclass
import re

from ocr_engine.constants.insights_constants import (
    INSIGHTS_IGNORED_SECTION_KEYWORDS,
    INSIGHTS_RELEVANT_SECTIONS,
)
from ocr_engine.services.narrative_text_extractor import NarrativePage


@dataclass(frozen=True)
class SectionPage:
    """Narrative text assigned to a relevant annual-report section."""

    page_number: int
    section: str
    text: str


class SectionIdentifier:
    """Identify business narrative sections and exclude boilerplate pages."""

    _section_aliases = {
        "Chairman Review": (
            "chairman review",
            "chairman's review",
            "chairman statement",
            "chairman's statement",
        ),
        "CEO Review": (
            "ceo review",
            "chief executive review",
            "chief executive officer review",
            "ceo message",
        ),
        "Directors Report": (
            "directors report",
            "directors' report",
            "report of the directors",
        ),
        "Management Discussion & Analysis": (
            "management discussion and analysis",
            "management discussion & analysis",
            "md&a",
            "management review",
        ),
        "Business Review": (
            "business review",
            "operating review",
            "performance review",
            "business operations",
        ),
        "Risks": (
            "risks",
            "risk factors",
            "principal risks",
            "risk management",
        ),
        "Opportunities": (
            "opportunities",
            "future opportunities",
            "growth opportunities",
        ),
        "Outlook": (
            "outlook",
            "future outlook",
            "future prospects",
            "market outlook",
        ),
    }

    def identify_sections(self, pages: list[NarrativePage]) -> list[SectionPage]:
        """Return pages that belong to relevant narrative sections."""

        section_pages: list[SectionPage] = []
        current_section: str | None = None

        for page in pages:
            if self._is_ignored_page(page.text):
                current_section = None
                continue

            section = self._identify_section(page.text)
            if section is not None:
                current_section = section

            if current_section is None:
                continue

            section_pages.append(
                SectionPage(
                    page_number=page.page_number,
                    section=current_section,
                    text=page.text,
                )
            )

        return section_pages

    def _identify_section(self, text: str) -> str | None:
        """Identify a relevant section from the page heading area."""

        heading_area = _normalize_text(text[:1200])
        for section in INSIGHTS_RELEVANT_SECTIONS:
            aliases = self._section_aliases.get(section, (section.lower(),))
            if any(_normalize_text(alias) in heading_area for alias in aliases):
                return section
        return None

    def _is_ignored_page(self, text: str) -> bool:
        """Return whether a page belongs to an ignored report area."""

        heading_area = _normalize_text(text[:900])
        return any(
            _normalize_text(keyword) in heading_area
            for keyword in INSIGHTS_IGNORED_SECTION_KEYWORDS
        )


def _normalize_text(value: str) -> str:
    """Normalize text for section matching."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
