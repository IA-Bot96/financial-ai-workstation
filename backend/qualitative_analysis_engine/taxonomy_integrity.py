"""Integrity validation for the frozen qualitative taxonomy asset."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


TAXONOMY_VERSION = "1.0.0"
EXPECTED_CATEGORY_COUNT = 6
EXPECTED_THEME_COUNT = 27
FORBIDDEN_AMBIGUOUS_ALIASES = frozenset({"energy", "cost", "regulatory"})
DEFAULT_TAXONOMY_PATH = (
    Path(__file__).resolve().parent
    / "config"
    / "canonical_qualitative_taxonomy.json"
)


def load_taxonomy(path: str | Path = DEFAULT_TAXONOMY_PATH) -> dict[str, Any]:
    """Load the canonical qualitative taxonomy JSON asset."""

    taxonomy_path = Path(path)
    return json.loads(taxonomy_path.read_text(encoding="utf-8"))


def validate_taxonomy(taxonomy: Mapping[str, Any]) -> dict[str, Any]:
    """Validate taxonomy integrity and return an audit-ready result payload."""

    categories = _as_list(taxonomy.get("categories"))
    themes = _as_list(taxonomy.get("themes"))
    category_refs = [_as_str(item.get("category_ref")) for item in categories]
    theme_refs = [_as_str(item.get("theme_ref")) for item in themes]
    category_ref_set = set(category_refs)
    theme_ref_set = set(theme_refs)

    checks: dict[str, dict[str, Any]] = {}

    _add_check(
        checks,
        "taxonomy_version",
        taxonomy.get("taxonomy_version") == TAXONOMY_VERSION,
        []
        if taxonomy.get("taxonomy_version") == TAXONOMY_VERSION
        else [f"Expected taxonomy_version {TAXONOMY_VERSION}."],
    )
    _add_check(
        checks,
        "category_count",
        len(categories) == EXPECTED_CATEGORY_COUNT,
        []
        if len(categories) == EXPECTED_CATEGORY_COUNT
        else [
            "Expected "
            f"{EXPECTED_CATEGORY_COUNT} categories, found {len(categories)}."
        ],
    )
    _add_check(
        checks,
        "theme_count",
        len(themes) == EXPECTED_THEME_COUNT,
        []
        if len(themes) == EXPECTED_THEME_COUNT
        else [f"Expected {EXPECTED_THEME_COUNT} themes, found {len(themes)}."],
    )

    duplicate_category_refs = _duplicates(category_refs)
    _add_check(
        checks,
        "unique_category_ref",
        not duplicate_category_refs,
        duplicate_category_refs,
    )

    duplicate_theme_refs = _duplicates(theme_refs)
    _add_check(
        checks,
        "unique_theme_ref",
        not duplicate_theme_refs,
        duplicate_theme_refs,
    )

    invalid_theme_categories = [
        {
            "theme_ref": theme.get("theme_ref"),
            "category_ref": theme.get("category_ref"),
        }
        for theme in themes
        if _as_str(theme.get("category_ref")) not in category_ref_set
    ]
    invalid_secondary_categories = [
        {
            "theme_ref": theme.get("theme_ref"),
            "secondary_category": secondary_category,
        }
        for theme in themes
        for secondary_category in _as_list(theme.get("secondary_categories"))
        if _as_str(secondary_category) not in category_ref_set
    ]
    _add_check(
        checks,
        "valid_category_references",
        not invalid_theme_categories and not invalid_secondary_categories,
        invalid_theme_categories + invalid_secondary_categories,
    )

    excessive_secondary_categories = [
        {
            "theme_ref": theme.get("theme_ref"),
            "secondary_categories": theme.get("secondary_categories", []),
        }
        for theme in themes
        if len(_as_list(theme.get("secondary_categories"))) > 2
    ]
    _add_check(
        checks,
        "secondary_categories_limit",
        not excessive_secondary_categories,
        excessive_secondary_categories,
    )

    invalid_never_merge_refs = [
        {"theme_ref": theme.get("theme_ref"), "never_merge_with": ref}
        for theme in themes
        for ref in _as_list(theme.get("never_merge_with"))
        if _as_str(ref) not in theme_ref_set
    ]
    _add_check(
        checks,
        "never_merge_references_exist",
        not invalid_never_merge_refs,
        invalid_never_merge_refs,
    )

    theme_by_ref = {_as_str(theme.get("theme_ref")): theme for theme in themes}
    asymmetric_never_merge_refs = []
    for theme_ref, theme in theme_by_ref.items():
        for target_ref in _as_list(theme.get("never_merge_with")):
            target_ref = _as_str(target_ref)
            target = theme_by_ref.get(target_ref)
            if not target:
                continue
            target_pairs = {_as_str(item) for item in _as_list(target.get("never_merge_with"))}
            if theme_ref not in target_pairs:
                asymmetric_never_merge_refs.append(
                    {
                        "theme_ref": theme_ref,
                        "never_merge_with": target_ref,
                        "missing_reverse_reference": theme_ref,
                    }
                )
    _add_check(
        checks,
        "never_merge_relationships_symmetric",
        not asymmetric_never_merge_refs,
        asymmetric_never_merge_refs,
    )

    duplicate_aliases = _find_duplicate_aliases(themes)
    _add_check(
        checks,
        "duplicate_aliases",
        not duplicate_aliases,
        duplicate_aliases,
    )

    forbidden_aliases = [
        {"theme_ref": theme.get("theme_ref"), "alias": alias}
        for theme in themes
        for alias in _as_list(theme.get("aliases"))
        if _normalize_text(_as_str(alias)) in FORBIDDEN_AMBIGUOUS_ALIASES
    ]
    _add_check(
        checks,
        "forbidden_ambiguous_aliases",
        not forbidden_aliases,
        forbidden_aliases,
    )

    failures = [
        {"check": name, "failures": check["failures"]}
        for name, check in checks.items()
        if not check["passed"]
    ]

    return {
        "taxonomy_version": taxonomy.get("taxonomy_version"),
        "category_count": len(categories),
        "theme_count": len(themes),
        "alias_count": sum(len(_as_list(theme.get("aliases"))) for theme in themes),
        "validation_passed": not failures,
        "checks": checks,
        "integrity_failures": failures,
    }


def validate_taxonomy_file(
    path: str | Path = DEFAULT_TAXONOMY_PATH,
) -> dict[str, Any]:
    """Load and validate a taxonomy JSON file."""

    return validate_taxonomy(load_taxonomy(path))


def write_taxonomy_integrity_audit(
    output_path: str | Path,
    taxonomy_path: str | Path = DEFAULT_TAXONOMY_PATH,
) -> dict[str, Any]:
    """Validate the taxonomy and persist the Phase 0 integrity audit JSON."""

    result = validate_taxonomy_file(taxonomy_path)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def _add_check(
    checks: dict[str, dict[str, Any]],
    name: str,
    passed: bool,
    failures: list[Any],
) -> None:
    checks[name] = {"passed": passed, "failures": failures}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _find_duplicate_aliases(themes: list[Any]) -> list[dict[str, Any]]:
    alias_locations: dict[str, list[dict[str, str]]] = defaultdict(list)
    for theme in themes:
        theme_ref = _as_str(theme.get("theme_ref"))
        for alias in _as_list(theme.get("aliases")):
            normalized_alias = _normalize_text(_as_str(alias))
            alias_locations[normalized_alias].append(
                {"theme_ref": theme_ref, "alias": _as_str(alias)}
            )

    return [
        {"normalized_alias": alias, "locations": locations}
        for alias, locations in sorted(alias_locations.items())
        if alias and len(locations) > 1
    ]


def _normalize_text(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


__all__ = [
    "DEFAULT_TAXONOMY_PATH",
    "EXPECTED_CATEGORY_COUNT",
    "EXPECTED_THEME_COUNT",
    "FORBIDDEN_AMBIGUOUS_ALIASES",
    "TAXONOMY_VERSION",
    "load_taxonomy",
    "validate_taxonomy",
    "validate_taxonomy_file",
    "write_taxonomy_integrity_audit",
]

