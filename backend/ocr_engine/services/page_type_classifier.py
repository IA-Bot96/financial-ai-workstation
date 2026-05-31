"""Heuristic page-type classification for narrative insight diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import re


PAGE_TYPE_NARRATIVE = "narrative"
PAGE_TYPE_FINANCIAL_STATEMENT = "financial_statement"
PAGE_TYPE_NOTES = "notes"
PAGE_TYPE_AUDITOR_REPORT = "auditor_report"
PAGE_TYPE_GOVERNANCE = "governance"
PAGE_TYPE_SHAREHOLDER = "shareholder"
PAGE_TYPE_PROXY = "proxy"
PAGE_TYPE_TABLE_HEAVY = "table_heavy"
PAGE_TYPE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class PageTypeClassification:
    """Heuristic page-type classification with diagnostic signals."""

    page_type: str
    confidence_score: float
    narrative_density: float
    table_density: float
    ignored_keyword_count: int


class PageTypeClassifier:
    """Classify report pages before narrative section identification.

    This classifier is intentionally deterministic and lightweight. It provides
    diagnostics for routing and section-identification decisions; it does not
    call AI services and does not modify downstream insight generation.
    """

    _auditor_markers = (
        "independent auditor",
        "auditor s report",
        "auditor report",
        "key audit matter",
        "basis for opinion",
    )
    _notes_markers = (
        "notes to the unconsolidated financial statements",
        "notes to the consolidated financial statements",
        "notes to the financial statements",
    )
    _financial_statement_markers = (
        "statement of financial position",
        "statement of profit or loss",
        "statement of comprehensive income",
        "statement of cash flow",
        "statement of cash flows",
        "statement of changes in equity",
    )
    _governance_markers = (
        "corporate governance",
        "statement of compliance",
        "board committees",
        "audit committee",
    )
    _shareholder_markers = (
        "pattern of shareholding",
        "shareholding pattern",
        "shareholders information",
        "categories of shareholders",
    )
    _proxy_markers = (
        "proxy form",
        "form of proxy",
        "notice of annual general meeting",
        "electronic transmission consent",
    )
    _narrative_markers = (
        "chairman",
        "chief executive",
        "directors are pleased",
        "directors report",
        "business review",
        "management discussion",
        "management review",
        "future prospects",
        "outlook",
        "sustainability",
        "principal activities",
        "performance of company",
    )
    _ignored_markers = (
        "auditor",
        "financial statements",
        "notes to the financial statements",
        "corporate information",
        "proxy form",
        "pattern of shareholding",
    )

    def classify(self, text: str) -> PageTypeClassification:
        """Return a deterministic page-type classification."""

        normalized = _normalize_text(text)
        if not normalized:
            return PageTypeClassification(
                page_type=PAGE_TYPE_UNKNOWN,
                confidence_score=0.0,
                narrative_density=0.0,
                table_density=0.0,
                ignored_keyword_count=0,
            )

        heading = _normalize_text(text[:1200])
        narrative_density = _narrative_density(text)
        table_density = _table_density(text)
        ignored_keyword_count = sum(
            1 for marker in self._ignored_markers if marker in heading
        )

        if _contains_any(heading, self._proxy_markers):
            return self._result(
                PAGE_TYPE_PROXY,
                0.95,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )
        if _contains_any(heading, self._auditor_markers):
            return self._result(
                PAGE_TYPE_AUDITOR_REPORT,
                0.95,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )
        if _contains_any(heading, self._notes_markers):
            return self._result(
                PAGE_TYPE_NOTES,
                0.95,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )
        if _contains_any(heading, self._shareholder_markers):
            return self._result(
                PAGE_TYPE_SHAREHOLDER,
                0.9,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )
        if _contains_any(heading, self._governance_markers):
            return self._result(
                PAGE_TYPE_GOVERNANCE,
                0.85,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )
        if _contains_any(heading, self._financial_statement_markers):
            return self._result(
                PAGE_TYPE_FINANCIAL_STATEMENT,
                0.9,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )

        narrative_marker_hit = _contains_any(heading, self._narrative_markers)
        if narrative_marker_hit and narrative_density >= 0.35:
            return self._result(
                PAGE_TYPE_NARRATIVE,
                0.8,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )
        if table_density >= 0.55 and narrative_density < 0.45:
            return self._result(
                PAGE_TYPE_TABLE_HEAVY,
                0.8,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )
        if narrative_density >= 0.55 and table_density < 0.45:
            return self._result(
                PAGE_TYPE_NARRATIVE,
                0.65,
                narrative_density,
                table_density,
                ignored_keyword_count,
            )

        return self._result(
            PAGE_TYPE_UNKNOWN,
            0.35,
            narrative_density,
            table_density,
            ignored_keyword_count,
        )

    @staticmethod
    def _result(
        page_type: str,
        base_confidence: float,
        narrative_density: float,
        table_density: float,
        ignored_keyword_count: int,
    ) -> PageTypeClassification:
        """Build a bounded classification result."""

        confidence = base_confidence
        if page_type == PAGE_TYPE_NARRATIVE:
            confidence += min(0.15, narrative_density * 0.15)
            confidence -= min(0.2, table_density * 0.15)
        elif page_type in {PAGE_TYPE_TABLE_HEAVY, PAGE_TYPE_FINANCIAL_STATEMENT}:
            confidence += min(0.1, table_density * 0.1)

        return PageTypeClassification(
            page_type=page_type,
            confidence_score=round(max(0.0, min(confidence, 1.0)), 3),
            narrative_density=round(narrative_density, 3),
            table_density=round(table_density, 3),
            ignored_keyword_count=ignored_keyword_count,
        )


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    """Return whether normalized text contains any normalized marker."""

    return any(_normalize_text(marker) in text for marker in markers)


def _narrative_density(text: str) -> float:
    """Estimate how much of the page is prose-like text."""

    lines = _non_empty_lines(text)
    if not lines:
        return 0.0

    narrative_lines = [
        line
        for line in lines
        if len(line.split()) >= 6 and _alpha_ratio(line) >= 0.55
    ]
    return len(narrative_lines) / len(lines)


def _table_density(text: str) -> float:
    """Estimate how table-like a page is from line-level numeric density."""

    lines = _non_empty_lines(text)
    if not lines:
        return 0.0

    table_like_lines = [
        line
        for line in lines
        if _digit_ratio(line) >= 0.25
        or re.search(r"\b(?:19|20)\d{2}\b", line)
        or len(re.findall(r"\s{2,}", line)) >= 2
    ]
    return len(table_like_lines) / len(lines)


def _non_empty_lines(text: str) -> list[str]:
    """Return stripped non-empty text lines."""

    return [line.strip() for line in text.splitlines() if line.strip()]


def _alpha_ratio(text: str) -> float:
    """Return alphabetic-character density for text."""

    chars = [char for char in text if not char.isspace()]
    if not chars:
        return 0.0
    return sum(1 for char in chars if char.isalpha()) / len(chars)


def _digit_ratio(text: str) -> float:
    """Return digit-character density for text."""

    chars = [char for char in text if not char.isspace()]
    if not chars:
        return 0.0
    return sum(1 for char in chars if char.isdigit()) / len(chars)


def _normalize_text(value: str) -> str:
    """Normalize text for deterministic page-type matching."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()

