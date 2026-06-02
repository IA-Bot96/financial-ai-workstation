"""Loader for the frozen canonical qualitative taxonomy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qualitative_analysis_engine.taxonomy_integrity import (
    DEFAULT_TAXONOMY_PATH,
    load_taxonomy,
    validate_taxonomy,
)

from .text_normalization import normalize_text


@dataclass(frozen=True)
class CategoryDefinition:
    """Frozen qualitative category definition."""

    category_ref: str
    name: str
    description: str


@dataclass(frozen=True)
class ThemeDefinition:
    """Frozen qualitative theme definition."""

    theme_ref: str
    category_ref: str
    secondary_categories: tuple[str, ...]
    description: str
    aliases: tuple[str, ...]
    example_area_labels: tuple[str, ...]
    sector_neutral: bool
    never_merge_with: tuple[str, ...]

    @property
    def normalized_theme_ref(self) -> str:
        """Return normalized theme ref text for exact matching."""

        return normalize_text(self.theme_ref)


@dataclass(frozen=True)
class TaxonomyDefinition:
    """Loaded frozen qualitative taxonomy and normalized lookup indexes."""

    taxonomy_version: str
    categories: dict[str, CategoryDefinition]
    themes: dict[str, ThemeDefinition]
    exact_theme_index: dict[str, str]
    alias_index: dict[str, str]
    keyword_index: dict[str, tuple[str, ...]]

    def category_exists(self, category_ref: str) -> bool:
        """Return whether a category ref is in the frozen taxonomy."""

        return category_ref in self.categories

    def theme_exists(self, theme_ref: str) -> bool:
        """Return whether a theme ref is in the frozen taxonomy."""

        return theme_ref in self.themes


class TaxonomyLoader:
    """Load and validate the frozen canonical qualitative taxonomy JSON."""

    def __init__(self, taxonomy_path: str | Path = DEFAULT_TAXONOMY_PATH) -> None:
        self._taxonomy_path = Path(taxonomy_path)

    def load(self) -> TaxonomyDefinition:
        """Load the taxonomy and fail fast if integrity validation fails."""

        payload = load_taxonomy(self._taxonomy_path)
        audit = validate_taxonomy(payload)
        if not audit["validation_passed"]:
            raise ValueError(
                "Canonical qualitative taxonomy failed integrity validation: "
                f"{audit['integrity_failures']}"
            )

        categories = {
            item["category_ref"]: CategoryDefinition(
                category_ref=item["category_ref"],
                name=item["name"],
                description=item["description"],
            )
            for item in payload["categories"]
        }
        themes = {
            item["theme_ref"]: ThemeDefinition(
                theme_ref=item["theme_ref"],
                category_ref=item["category_ref"],
                secondary_categories=tuple(item.get("secondary_categories", [])),
                description=item["description"],
                aliases=tuple(item.get("aliases", [])),
                example_area_labels=tuple(item.get("example_area_labels", [])),
                sector_neutral=bool(item.get("sector_neutral", True)),
                never_merge_with=tuple(item.get("never_merge_with", [])),
            )
            for item in payload["themes"]
        }

        exact_theme_index = {
            normalize_text(theme_ref): theme_ref for theme_ref in themes
        }
        alias_index: dict[str, str] = {}
        keyword_index: dict[str, list[str]] = {}
        for theme in themes.values():
            for alias in theme.aliases:
                normalized_alias = normalize_text(alias)
                alias_index[normalized_alias] = theme.theme_ref
                keyword_index.setdefault(normalized_alias, []).append(theme.theme_ref)
            for label in theme.example_area_labels:
                normalized_label = normalize_text(label)
                alias_index[normalized_label] = theme.theme_ref
                keyword_index.setdefault(normalized_label, []).append(theme.theme_ref)

        return TaxonomyDefinition(
            taxonomy_version=str(payload["taxonomy_version"]),
            categories=categories,
            themes=themes,
            exact_theme_index=exact_theme_index,
            alias_index=alias_index,
            keyword_index={
                keyword: tuple(theme_refs)
                for keyword, theme_refs in keyword_index.items()
            },
        )

__all__ = [
    "CategoryDefinition",
    "TaxonomyDefinition",
    "TaxonomyLoader",
    "ThemeDefinition",
]
