"""Deterministic source-section to category routing."""

from __future__ import annotations

from dataclasses import dataclass

from qualitative_analysis_engine.models import RoutingBasis

from .text_normalization import normalize_text


@dataclass(frozen=True)
class SectionRoute:
    """Source-section category prior."""

    source_section: str
    normalized_section: str
    primary_category_ref: str | None
    secondary_category_refs: tuple[str, ...]
    routing_basis: RoutingBasis
    route_confidence: float
    recognized: bool

    @property
    def category_refs(self) -> tuple[str, ...]:
        """Return all category refs allowed by this section prior."""

        if self.primary_category_ref is None:
            return self.secondary_category_refs
        return (self.primary_category_ref, *self.secondary_category_refs)


class SourceSectionRouter:
    """Route OCR-normalized source sections to frozen QAE category priors."""

    ROUTE_CONFIDENCE = 0.9

    _SECTION_CATEGORY_PRIORS = {
        "chairman review": ("outlook", ("strategy", "governance")),
        "ceo review": ("outlook", ("strategy",)),
        "directors report": ("governance", ("outlook", "strategy")),
        "management discussion and analysis": (
            "strategy",
            ("outlook", "business_risk"),
        ),
        "business review": ("strategy", ("operational_risk", "outlook")),
        "risks": ("business_risk", ("operational_risk",)),
        "opportunities": ("strategy", ("outlook",)),
        "outlook": ("outlook", ()),
        "strategy": ("strategy", ("outlook",)),
        "financial review": ("business_risk", ("outlook",)),
        "sustainability": ("esg", ()),
        "esg": ("esg", ()),
    }

    def route(self, source_section: str | None) -> SectionRoute:
        """Return the deterministic category prior for a source section."""

        source_section = (source_section or "").strip()
        normalized_section = normalize_text(source_section)
        route = self._SECTION_CATEGORY_PRIORS.get(normalized_section)
        if route is None:
            return SectionRoute(
                source_section=source_section,
                normalized_section=normalized_section,
                primary_category_ref=None,
                secondary_category_refs=(),
                routing_basis=RoutingBasis.NONE,
                route_confidence=0.0,
                recognized=False,
            )
        return SectionRoute(
            source_section=source_section,
            normalized_section=normalized_section,
            primary_category_ref=route[0],
            secondary_category_refs=route[1],
            routing_basis=RoutingBasis.SECTION_PRIOR,
            route_confidence=self.ROUTE_CONFIDENCE,
            recognized=True,
        )


__all__ = ["SectionRoute", "SourceSectionRouter"]

