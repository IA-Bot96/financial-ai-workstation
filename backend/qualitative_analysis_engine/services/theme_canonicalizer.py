"""Theme canonicalization over the frozen qualitative taxonomy."""

from __future__ import annotations

from dataclasses import dataclass

from qualitative_analysis_engine.models import MappingMethod, RoutingBasis

from .mapping_confidence import MappingConfidenceComposer
from .section_router import SectionRoute, SourceSectionRouter
from .taxonomy_loader import TaxonomyDefinition, TaxonomyLoader
from .text_normalization import normalize_text


@dataclass(frozen=True)
class ThemeCanonicalizationResult:
    """Deterministic area-to-theme classification result."""

    original_text: str
    normalized_text: str
    theme_ref: str | None
    category_ref: str | None
    secondary_categories: tuple[str, ...]
    mapping_method: MappingMethod
    mapping_confidence: float
    confidence: float
    matched_text: str | None
    routing_basis: RoutingBasis
    section_route: SectionRoute | None
    section_theme_conflict: bool
    unmapped: bool
    evidence: tuple[str, ...]


class ThemeCanonicalizer:
    """Canonicalize free-text insight areas into frozen taxonomy themes."""

    def __init__(
        self,
        taxonomy: TaxonomyDefinition | None = None,
        *,
        section_router: SourceSectionRouter | None = None,
        confidence_composer: MappingConfidenceComposer | None = None,
    ) -> None:
        self._taxonomy = taxonomy or TaxonomyLoader().load()
        self._section_router = section_router or SourceSectionRouter()
        self._confidence_composer = (
            confidence_composer or MappingConfidenceComposer()
        )

    def canonicalize(
        self,
        area: str | None,
        *,
        takeaway: str | None = None,
        source_section: str | None = None,
        extraction_confidence: float = 1.0,
        section_confidence: float | None = None,
    ) -> ThemeCanonicalizationResult:
        """Canonicalize an insight area into a theme or explicit unmapped result."""

        original_text = (area or "").strip()
        normalized_text = normalize_text(original_text)
        section_route = self._section_router.route(source_section)

        exact_theme_ref = self._taxonomy.exact_theme_index.get(normalized_text)
        if exact_theme_ref:
            return self._build_mapped_result(
                original_text=original_text,
                normalized_text=normalized_text,
                theme_ref=exact_theme_ref,
                mapping_method=MappingMethod.EXACT,
                matched_text=normalized_text,
                section_route=section_route,
                extraction_confidence=extraction_confidence,
                section_confidence=section_confidence,
                evidence=("exact_theme_match",),
            )

        alias_theme_ref = self._taxonomy.alias_index.get(normalized_text)
        if alias_theme_ref:
            return self._build_mapped_result(
                original_text=original_text,
                normalized_text=normalized_text,
                theme_ref=alias_theme_ref,
                mapping_method=MappingMethod.ALIAS,
                matched_text=normalized_text,
                section_route=section_route,
                extraction_confidence=extraction_confidence,
                section_confidence=section_confidence,
                evidence=("alias_match",),
            )

        keyword_theme_ref, matched_keyword = self._match_keyword(
            normalized_text,
            normalize_text(takeaway or ""),
        )
        if keyword_theme_ref:
            return self._build_mapped_result(
                original_text=original_text,
                normalized_text=normalized_text,
                theme_ref=keyword_theme_ref,
                mapping_method=MappingMethod.KEYWORD,
                matched_text=matched_keyword,
                section_route=section_route,
                extraction_confidence=extraction_confidence,
                section_confidence=section_confidence,
                evidence=("keyword_match",),
            )

        return self._build_unmapped_result(
            original_text=original_text,
            normalized_text=normalized_text,
            section_route=section_route,
        )

    def _build_mapped_result(
        self,
        *,
        original_text: str,
        normalized_text: str,
        theme_ref: str,
        mapping_method: MappingMethod,
        matched_text: str,
        section_route: SectionRoute,
        extraction_confidence: float,
        section_confidence: float | None,
        evidence: tuple[str, ...],
    ) -> ThemeCanonicalizationResult:
        theme = self._taxonomy.themes[theme_ref]
        section_categories = set(section_route.category_refs)
        section_theme_conflict = (
            section_route.recognized
            and theme.category_ref not in section_categories
            and not (set(theme.secondary_categories) & section_categories)
        )
        effective_section_confidence = (
            section_confidence
            if section_confidence is not None
            else section_route.route_confidence
            if section_route.recognized
            else None
        )
        mapping_confidence = self._confidence_composer.method_confidence(
            mapping_method
        )
        confidence = self._confidence_composer.compose(
            mapping_confidence=mapping_confidence,
            extraction_confidence=extraction_confidence,
            section_confidence=effective_section_confidence,
            section_theme_conflict=section_theme_conflict,
        )
        evidence_items = list(evidence)
        if section_theme_conflict:
            evidence_items.append("section_theme_conflict")
        elif section_route.recognized:
            evidence_items.append("section_prior_consistent")

        return ThemeCanonicalizationResult(
            original_text=original_text,
            normalized_text=normalized_text,
            theme_ref=theme.theme_ref,
            category_ref=theme.category_ref,
            secondary_categories=theme.secondary_categories,
            mapping_method=mapping_method,
            mapping_confidence=mapping_confidence,
            confidence=confidence,
            matched_text=matched_text,
            routing_basis=section_route.routing_basis
            if section_route.recognized
            else RoutingBasis.NONE,
            section_route=section_route,
            section_theme_conflict=section_theme_conflict,
            unmapped=False,
            evidence=tuple(evidence_items),
        )

    def _build_unmapped_result(
        self,
        *,
        original_text: str,
        normalized_text: str,
        section_route: SectionRoute,
    ) -> ThemeCanonicalizationResult:
        evidence = ["unmapped"]
        if section_route.recognized:
            evidence.append("section_prior_fallback")
        return ThemeCanonicalizationResult(
            original_text=original_text,
            normalized_text=normalized_text,
            theme_ref=None,
            category_ref=section_route.primary_category_ref,
            secondary_categories=section_route.secondary_category_refs,
            mapping_method=MappingMethod.UNMAPPED,
            mapping_confidence=self._confidence_composer.method_confidence(
                MappingMethod.UNMAPPED
            ),
            confidence=0.0,
            matched_text=None,
            routing_basis=section_route.routing_basis
            if section_route.recognized
            else RoutingBasis.NONE,
            section_route=section_route,
            section_theme_conflict=False,
            unmapped=True,
            evidence=tuple(evidence),
        )

    def _match_keyword(
        self,
        normalized_area: str,
        normalized_takeaway: str,
    ) -> tuple[str | None, str | None]:
        haystack = f"{normalized_area} {normalized_takeaway}".strip()
        if not haystack:
            return None, None

        matches: list[tuple[int, str, str]] = []
        for keyword, theme_refs in self._taxonomy.keyword_index.items():
            if not keyword:
                continue
            if _contains_phrase(haystack, keyword):
                for theme_ref in theme_refs:
                    matches.append((len(keyword), keyword, theme_ref))
        if not matches:
            return None, None

        matches.sort(key=lambda item: (-item[0], item[1], item[2]))
        _, keyword, theme_ref = matches[0]
        return theme_ref, keyword


def _contains_phrase(haystack: str, phrase: str) -> bool:
    return f" {phrase} " in f" {haystack} "


__all__ = ["ThemeCanonicalizationResult", "ThemeCanonicalizer"]

