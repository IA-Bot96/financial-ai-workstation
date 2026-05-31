"""Rule-based annual-report narrative section identification."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable

from ocr_engine.constants.insights_constants import (
    INSIGHTS_IGNORED_SECTION_KEYWORDS,
    INSIGHTS_RELEVANT_SECTIONS,
)
from ocr_engine.models.insights_extraction import (
    SectionIdentificationPageDiagnostic,
    SectionIdentificationReport,
)
from ocr_engine.services.narrative_text_extractor import NarrativePage
from ocr_engine.services.page_type_classifier import (
    PAGE_TYPE_AUDITOR_REPORT,
    PAGE_TYPE_FINANCIAL_STATEMENT,
    PAGE_TYPE_NARRATIVE,
    PAGE_TYPE_NOTES,
    PAGE_TYPE_PROXY,
    PAGE_TYPE_SHAREHOLDER,
    PAGE_TYPE_TABLE_HEAVY,
    PAGE_TYPE_UNKNOWN,
    PageTypeClassifier,
)


@dataclass(frozen=True)
class SectionPage:
    """Narrative text assigned to a relevant annual-report section."""

    page_number: int
    section: str
    text: str


class SectionIdentifier:
    """Identify business narrative sections and exclude boilerplate pages."""

    _acceptance_threshold = 0.55
    _terminal_page_types = {
        PAGE_TYPE_AUDITOR_REPORT,
        PAGE_TYPE_FINANCIAL_STATEMENT,
        PAGE_TYPE_NOTES,
        PAGE_TYPE_PROXY,
        PAGE_TYPE_SHAREHOLDER,
        PAGE_TYPE_TABLE_HEAVY,
    }
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
            "company overview",
            "key performance indicators",
            "segmental review of business performance",
        ),
        "Risks": (
            "risks and opportunities",
            "operational risks",
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
        "Strategy": (
            "strategy",
            "pestle analysis",
            "swot analysis",
            "strategic objectives",
            "strategy and resource allocation",
        ),
        "Financial Review": (
            "financial review",
            "financial performance",
            "financial results",
            "financial overview",
            "key figures",
            "financial highlights",
            "dupont analysis",
        ),
        "Sustainability": (
            "sustainability",
            "sustainability review",
            "corporate social responsibility",
            "csr",
        ),
        "ESG": (
            "esg",
            "environmental social and governance",
            "environment social governance",
        ),
    }

    def __init__(
        self,
        *,
        page_type_classifier: PageTypeClassifier | None = None,
        acceptance_threshold: float = _acceptance_threshold,
    ) -> None:
        """Initialize section identification dependencies."""

        if not 0 <= acceptance_threshold <= 1:
            raise ValueError("acceptance_threshold must be between 0 and 1.")

        self._page_type_classifier = page_type_classifier or PageTypeClassifier()
        self._acceptance_threshold = acceptance_threshold
        self._last_report = SectionIdentificationReport()

    @property
    def last_report(self) -> SectionIdentificationReport:
        """Return diagnostics from the most recent section-identification run."""

        return self._last_report

    def identify_sections(self, pages: list[NarrativePage]) -> list[SectionPage]:
        """Return pages that belong to relevant narrative sections."""

        section_pages: list[SectionPage] = []
        current_section: str | None = None
        page_diagnostics: list[SectionIdentificationPageDiagnostic] = []

        for page in pages:
            decision = self._diagnose_page(page, current_section)
            page_diagnostics.append(decision)

            if decision.detected_section is None:
                current_section = None
                continue

            current_section = decision.detected_section
            section_pages.append(
                SectionPage(
                    page_number=page.page_number,
                    section=decision.detected_section,
                    text=page.text,
                )
            )

        self._last_report = SectionIdentificationReport(
            total_pages=len(pages),
            pages_with_pymupdf_text=sum(1 for page in pages if page.pymupdf),
            pages_with_ocr_text=sum(1 for page in pages if page.ocr),
            accepted_pages=len(section_pages),
            rejected_pages=len(pages) - len(section_pages),
            page_type_counts=_count_values(
                diagnostic.page_type for diagnostic in page_diagnostics
            ),
            text_source_counts=_count_values(page.text_source for page in pages),
            ocr_engine_counts=_count_values(
                page.ocr_engine_selected
                for page in pages
                if page.ocr_engine_selected
            ),
            ocr_pages_escalated=sum(
                1 for page in pages if page.ocr_escalated
            ),
            ocr_pages_recovered=sum(
                1 for page in pages if page.ocr_recovered
            ),
            additional_accepted_pages=sum(
                1 for page in pages if page.ocr_recovered
            ),
            page_diagnostics=page_diagnostics,
        )
        return section_pages

    def _diagnose_page(
        self,
        page: NarrativePage,
        current_section: str | None,
    ) -> SectionIdentificationPageDiagnostic:
        """Build a page-level section decision with diagnostics."""

        page_type = self._page_type_classifier.classify(page.text)
        ignored_keywords = self._ignored_keywords(page.text)
        direct_section, _, heading_match = self._section_match(page.text)
        candidate_section = direct_section
        continuation = False
        if candidate_section is None and current_section is not None:
            candidate_section = current_section
            continuation = True

        confidence_score = _confidence_score(
            page_type=page_type.page_type,
            narrative_density=page_type.narrative_density,
            table_density=page_type.table_density,
            ignored_keyword_count=len(ignored_keywords),
            has_section_alias=direct_section is not None,
            has_heading_match=heading_match,
            is_continuation=continuation,
        )
        rejection_reason = _rejection_reason(
            page=page,
            page_type=page_type.page_type,
            candidate_section=candidate_section,
            confidence_score=confidence_score,
            acceptance_threshold=self._acceptance_threshold,
            terminal_page_types=self._terminal_page_types,
            ignored_keywords=ignored_keywords,
        )
        detected_section = None if rejection_reason else candidate_section

        return SectionIdentificationPageDiagnostic(
            page_number=page.page_number,
            text_source=page.text_source,
            pymupdf=page.pymupdf,
            ocr=page.ocr,
            page_type=page_type.page_type,
            detected_section=detected_section,
            confidence_score=confidence_score,
            rejection_reason=rejection_reason,
            heading_match=heading_match,
            section_alias_match=direct_section is not None,
            narrative_density=page_type.narrative_density,
            table_density=page_type.table_density,
            ignored_keyword_count=len(ignored_keywords),
            ocr_engine_selected=page.ocr_engine_selected,
            pymupdf_ocr_confidence=page.pymupdf_ocr_confidence,
            tesseract_ocr_confidence=page.tesseract_ocr_confidence,
            ocr_escalation_reason=page.ocr_escalation_reason,
            ocr_escalated=page.ocr_escalated,
            ocr_recovered=page.ocr_recovered,
            ocr_heading_alias_match_count=page.ocr_heading_alias_match_count,
            ocr_heading_fragmentation_ratio=(
                page.ocr_heading_fragmentation_ratio
            ),
            ocr_single_character_line_count=(
                page.ocr_single_character_line_count
            ),
        )

    def _identify_section(self, text: str) -> str | None:
        """Identify a relevant section from the page heading area."""

        section, _, _ = self._section_match(text)
        return section

    def _section_match(self, text: str) -> tuple[str | None, str | None, bool]:
        """Identify a relevant section and whether the hit is heading-like."""

        heading_area = _normalize_text(text[:1200])
        heading_block = _heading_block(text)
        top_heading_block = _normalize_text(text[:500])
        for section in INSIGHTS_RELEVANT_SECTIONS:
            aliases = self._section_aliases.get(section, (section.lower(),))
            for alias in aliases:
                normalized_alias = _normalize_text(alias)
                if not normalized_alias:
                    continue
                if _alias_matches_heading(normalized_alias, heading_block):
                    return (section, alias, True)
                if _alias_matches_heading(normalized_alias, top_heading_block):
                    return (section, alias, True)
                if _contains_normalized_phrase(heading_area, normalized_alias):
                    return (section, alias, False)
        return None, None, False

    def _is_ignored_page(self, text: str) -> bool:
        """Return whether a page belongs to an ignored report area."""

        return bool(self._ignored_keywords(text))

    def _ignored_keywords(self, text: str) -> list[str]:
        """Return ignored keyword signals from the page heading area."""

        heading_area = _normalize_text(text[:900])
        return [
            keyword
            for keyword in INSIGHTS_IGNORED_SECTION_KEYWORDS
            if _normalize_text(keyword) in heading_area
        ]


def _normalize_text(value: str) -> str:
    """Normalize text for section matching."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _heading_block(text: str, max_lines: int = 12) -> str:
    """Return a normalized heading block with adjacent short OCR lines merged."""

    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    heading_lines = raw_lines[:max_lines]
    candidates = list(heading_lines)

    short_buffer: list[str] = []
    for line in heading_lines:
        clean_line = re.sub(r"\s+", " ", line).strip()
        if not clean_line:
            continue
        if _is_short_heading_fragment(clean_line):
            short_buffer.append(clean_line)
            continue

        if short_buffer:
            candidates.append(" ".join(short_buffer))
            short_buffer.clear()
        candidates.append(clean_line)

    if short_buffer:
        candidates.append(" ".join(short_buffer))

    return _normalize_text(" ".join(candidates))


def _is_short_heading_fragment(line: str) -> bool:
    """Return whether a line is likely part of an OCR-split heading."""

    words = re.findall(r"[A-Za-z0-9']+", line)
    if not words:
        return False
    return len(words) <= 3 and len(line) <= 36


def _alias_matches_heading(normalized_alias: str, normalized_heading: str) -> bool:
    """Return whether an alias matches a heading block, allowing OCR noise."""

    if _contains_normalized_phrase(normalized_heading, normalized_alias):
        return True

    alias_words = normalized_alias.split()
    heading_words = normalized_heading.split()
    if (
        len(alias_words) < 2
        or len(normalized_alias) < 10
        or any(len(word) <= 1 for word in alias_words)
        or not heading_words
    ):
        return False

    min_window = max(1, len(alias_words) - 1)
    max_window = min(len(heading_words), len(alias_words) + 2)
    for window_size in range(min_window, max_window + 1):
        for index in range(0, len(heading_words) - window_size + 1):
            candidate = " ".join(heading_words[index : index + window_size])
            if _fuzzy_ratio(normalized_alias, candidate) >= 0.86:
                return True

    return False


def _contains_normalized_phrase(normalized_text: str, normalized_phrase: str) -> bool:
    """Return whether a normalized phrase appears on word boundaries."""

    return f" {normalized_phrase} " in f" {normalized_text} "


def _fuzzy_ratio(left: str, right: str) -> float:
    """Return a deterministic similarity score for OCR-tolerant heading matches."""

    return SequenceMatcher(None, left, right).ratio()


def _confidence_score(
    *,
    page_type: str,
    narrative_density: float,
    table_density: float,
    ignored_keyword_count: int,
    has_section_alias: bool,
    has_heading_match: bool,
    is_continuation: bool,
) -> float:
    """Return a bounded section-identification confidence score."""

    score = 0.0
    if has_heading_match:
        score += 0.78
    elif has_section_alias:
        score += 0.45
    elif is_continuation:
        score += 0.62

    if page_type == PAGE_TYPE_NARRATIVE:
        score += 0.18
    elif page_type == PAGE_TYPE_UNKNOWN:
        score -= 0.05
    elif page_type in {
        PAGE_TYPE_AUDITOR_REPORT,
        PAGE_TYPE_FINANCIAL_STATEMENT,
        PAGE_TYPE_NOTES,
        PAGE_TYPE_PROXY,
        PAGE_TYPE_SHAREHOLDER,
        PAGE_TYPE_TABLE_HEAVY,
    }:
        score -= 0.35

    score += min(0.22, narrative_density * 0.22)
    score -= min(0.22, table_density * 0.22)
    score -= min(0.25, ignored_keyword_count * 0.1)
    return round(max(0.0, min(score, 1.0)), 3)


def _rejection_reason(
    *,
    page: NarrativePage,
    page_type: str,
    candidate_section: str | None,
    confidence_score: float,
    acceptance_threshold: float,
    terminal_page_types: set[str],
    ignored_keywords: list[str],
) -> str | None:
    """Return a stable rejection reason, or None when the page is accepted."""

    if not page.text.strip():
        return "no_text"
    if page_type in terminal_page_types:
        return f"page_type_{page_type}"
    if candidate_section is None:
        if ignored_keywords:
            return "ignored_keywords:" + ",".join(ignored_keywords)
        return "no_section_candidate"
    if confidence_score < acceptance_threshold:
        return "low_confidence"
    return None


def _count_values(values: Iterable[str]) -> dict[str, int]:
    """Return stable frequency counts for diagnostics."""

    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
