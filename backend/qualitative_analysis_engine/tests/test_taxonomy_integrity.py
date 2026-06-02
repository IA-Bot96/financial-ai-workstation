"""Tests for qualitative taxonomy integrity validation."""

import copy
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from qualitative_analysis_engine.taxonomy_integrity import (  # noqa: E402
    EXPECTED_CATEGORY_COUNT,
    EXPECTED_THEME_COUNT,
    TAXONOMY_VERSION,
    load_taxonomy,
    validate_taxonomy,
)


def _canonical_taxonomy() -> dict:
    return load_taxonomy()


def test_canonical_taxonomy_integrity_passes() -> None:
    result = validate_taxonomy(_canonical_taxonomy())

    assert result["validation_passed"] is True
    assert result["taxonomy_version"] == TAXONOMY_VERSION
    assert result["category_count"] == EXPECTED_CATEGORY_COUNT
    assert result["theme_count"] == EXPECTED_THEME_COUNT
    assert result["alias_count"] > 140
    assert result["integrity_failures"] == []
    assert all(check["passed"] for check in result["checks"].values())


def test_duplicate_aliases_are_detected_after_normalization() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["themes"][1]["aliases"].append("Demand   Outlook")

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["duplicate_aliases"]["passed"] is False
    duplicate_aliases = result["checks"]["duplicate_aliases"]["failures"]
    assert duplicate_aliases[0]["normalized_alias"] == "demand outlook"


def test_duplicate_category_refs_are_detected() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["categories"][1]["category_ref"] = "outlook"

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["unique_category_ref"]["failures"] == ["outlook"]


def test_duplicate_theme_refs_are_detected() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["themes"][1]["theme_ref"] = "demand_outlook"

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["unique_theme_ref"]["failures"] == ["demand_outlook"]


def test_invalid_category_references_are_detected() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["themes"][0]["category_ref"] = "invalid_category"
    taxonomy["themes"][1]["secondary_categories"] = ["strategy", "not_real"]

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["valid_category_references"]["passed"] is False
    failures = result["checks"]["valid_category_references"]["failures"]
    assert {"theme_ref": "demand_outlook", "category_ref": "invalid_category"} in (
        failures
    )
    assert {
        "theme_ref": "margin_pricing_outlook",
        "secondary_category": "not_real",
    } in failures


def test_secondary_category_limit_is_enforced() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["themes"][0]["secondary_categories"] = [
        "strategy",
        "outlook",
        "business_risk",
    ]

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["secondary_categories_limit"]["passed"] is False
    assert result["checks"]["secondary_categories_limit"]["failures"][0][
        "theme_ref"
    ] == "demand_outlook"


def test_never_merge_references_must_exist() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["themes"][0]["never_merge_with"].append("not_a_theme")

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["never_merge_references_exist"]["passed"] is False
    assert result["checks"]["never_merge_references_exist"]["failures"][0] == {
        "theme_ref": "demand_outlook",
        "never_merge_with": "not_a_theme",
    }


def test_never_merge_relationships_must_be_symmetric() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["themes"][12]["never_merge_with"] = []

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["never_merge_relationships_symmetric"]["passed"] is False
    failures = result["checks"]["never_merge_relationships_symmetric"]["failures"]
    assert {
        "theme_ref": "demand_outlook",
        "never_merge_with": "demand_competition",
        "missing_reverse_reference": "demand_outlook",
    } in failures


def test_forbidden_ambiguous_aliases_are_detected() -> None:
    taxonomy = copy.deepcopy(_canonical_taxonomy())
    taxonomy["themes"][0]["aliases"].append("energy")

    result = validate_taxonomy(taxonomy)

    assert result["validation_passed"] is False
    assert result["checks"]["forbidden_ambiguous_aliases"]["passed"] is False
    assert result["checks"]["forbidden_ambiguous_aliases"]["failures"][0] == {
        "theme_ref": "demand_outlook",
        "alias": "energy",
    }
