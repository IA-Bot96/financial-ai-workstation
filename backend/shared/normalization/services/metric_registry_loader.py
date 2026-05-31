"""Canonical metric registry loading for shared normalization."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class CanonicalMetric:
    """Validated canonical metric definition from the registry."""

    key: str
    display_name: str
    aliases: tuple[str, ...]
    category: str


class MetricRegistryLoader:
    """Load and validate canonical metric registry data."""

    def load_default(self) -> tuple[CanonicalMetric, ...]:
        """Load the canonical registry bundled with the shared module."""

        registry_path = (
            Path(__file__).resolve().parents[1] / "canonical_metric_registry.json"
        )
        return self.load_from_file(registry_path)

    def load_from_file(self, registry_path: str | Path) -> tuple[CanonicalMetric, ...]:
        """Load and validate a JSON canonical metric registry from disk."""

        path = Path(registry_path)
        registry = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        return self.load_from_dict(registry)

    def load_from_dict(
        self,
        canonical_metric_registry: Mapping[str, Any],
    ) -> tuple[CanonicalMetric, ...]:
        """Validate a registry dictionary and return canonical metric entries."""

        if not canonical_metric_registry:
            raise ValueError("Canonical metric registry cannot be empty.")

        metrics: list[CanonicalMetric] = []
        seen_keys: dict[str, str] = {}
        seen_display_names: dict[str, str] = {}
        seen_aliases: dict[str, str] = {}
        seen_terms: dict[str, str] = {}
        for key, payload in canonical_metric_registry.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Canonical metric keys must be non-empty strings.")
            if not isinstance(payload, Mapping):
                raise ValueError(f"Registry entry '{key}' must be an object.")

            canonical_key = key.strip()
            normalized_key_text = _normalize_registry_text(canonical_key)
            normalized_key = normalized_key_text.replace(" ", "_")
            _raise_if_collision(
                seen=seen_keys,
                normalized_value=normalized_key,
                owner=canonical_key,
                label="canonical metric name",
                original_value=canonical_key,
            )
            _raise_if_collision(
                seen=seen_terms,
                normalized_value=normalized_key_text,
                owner=canonical_key,
                label="registry term",
                original_value=canonical_key,
            )

            display_name = payload.get("display_name")
            aliases = payload.get("aliases", [])
            category = payload.get("category")

            if not isinstance(display_name, str) or not display_name.strip():
                raise ValueError(f"Registry entry '{key}' requires display_name.")
            if not isinstance(category, str) or not category.strip():
                raise ValueError(f"Registry entry '{key}' requires category.")
            if not isinstance(aliases, list):
                raise ValueError(f"Registry entry '{key}' aliases must be a list.")

            display_name = display_name.strip()
            normalized_display_name = _normalize_registry_text(display_name)
            _raise_if_collision(
                seen=seen_display_names,
                normalized_value=normalized_display_name,
                owner=canonical_key,
                label="display name",
                original_value=display_name,
            )
            _raise_if_collision(
                seen=seen_terms,
                normalized_value=normalized_display_name,
                owner=canonical_key,
                label="registry term",
                original_value=display_name,
            )

            deduped_aliases: list[str] = []
            local_aliases: set[str] = set()
            for alias in aliases:
                if not isinstance(alias, str) or not alias.strip():
                    continue
                alias_value = alias.strip()
                normalized_alias = _normalize_registry_text(alias_value)
                if normalized_alias in local_aliases:
                    raise ValueError(
                        "Duplicate alias "
                        f"'{alias_value}' found in registry entry '{canonical_key}'."
                    )
                local_aliases.add(normalized_alias)
                _raise_if_collision(
                    seen=seen_aliases,
                    normalized_value=normalized_alias,
                    owner=canonical_key,
                    label="alias",
                    original_value=alias_value,
                )
                _raise_if_collision(
                    seen=seen_terms,
                    normalized_value=normalized_alias,
                    owner=canonical_key,
                    label="registry term",
                    original_value=alias_value,
                )
                deduped_aliases.append(alias_value)

            metrics.append(
                CanonicalMetric(
                    key=canonical_key,
                    display_name=display_name,
                    aliases=tuple(deduped_aliases),
                    category=category.strip(),
                )
            )

        return tuple(metrics)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON object keys while loading registry files."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate registry key '{key}' found.")
        result[key] = value
    return result


def _raise_if_collision(
    *,
    seen: dict[str, str],
    normalized_value: str,
    owner: str,
    label: str,
    original_value: str,
) -> None:
    """Raise when a normalized registry term is owned by two metrics."""

    previous_owner = seen.get(normalized_value)
    if previous_owner is not None and previous_owner != owner:
        raise ValueError(
            f"Duplicate {label} '{original_value}' found in registry entries "
            f"'{previous_owner}' and '{owner}'."
        )
    seen[normalized_value] = owner


def _normalize_registry_text(value: str) -> str:
    """Normalize registry text for collision detection."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
