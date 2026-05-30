"""Canonical metric registry loading for shared normalization."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
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

        registry_path = Path(__file__).resolve().parents[1] / "canonical_metric_registry.json"
        return self.load_from_file(registry_path)

    def load_from_file(self, registry_path: str | Path) -> tuple[CanonicalMetric, ...]:
        """Load and validate a JSON canonical metric registry from disk."""

        path = Path(registry_path)
        registry = json.loads(path.read_text(encoding="utf-8"))
        return self.load_from_dict(registry)

    def load_from_dict(
        self,
        canonical_metric_registry: Mapping[str, Any],
    ) -> tuple[CanonicalMetric, ...]:
        """Validate a registry dictionary and return canonical metric entries."""

        metrics: list[CanonicalMetric] = []
        for key, payload in canonical_metric_registry.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Canonical metric keys must be non-empty strings.")
            if not isinstance(payload, Mapping):
                raise ValueError(f"Registry entry '{key}' must be an object.")

            display_name = payload.get("display_name")
            aliases = payload.get("aliases", [])
            category = payload.get("category")

            if not isinstance(display_name, str) or not display_name.strip():
                raise ValueError(f"Registry entry '{key}' requires display_name.")
            if not isinstance(category, str) or not category.strip():
                raise ValueError(f"Registry entry '{key}' requires category.")
            if not isinstance(aliases, list):
                raise ValueError(f"Registry entry '{key}' aliases must be a list.")

            deduped_aliases = tuple(
                dict.fromkeys(
                    alias.strip()
                    for alias in aliases
                    if isinstance(alias, str) and alias.strip()
                )
            )
            metrics.append(
                CanonicalMetric(
                    key=key.strip(),
                    display_name=display_name.strip(),
                    aliases=deduped_aliases,
                    category=category.strip(),
                )
            )

        return tuple(metrics)
