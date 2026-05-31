"""Unit tests for the shared canonical metric registry loader."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.normalization.services.metric_registry_loader import MetricRegistryLoader


def test_registry_loader_validates_registry_entries() -> None:
    loader = MetricRegistryLoader()

    metrics = loader.load_from_dict(
        {
            "revenue": {
                "display_name": "Revenue",
                "aliases": ["sales", "turnover"],
                "category": "income_statement",
            }
        }
    )

    assert metrics[0].key == "revenue"
    assert metrics[0].aliases == ("sales", "turnover")


def test_registry_loader_loads_bundled_registry() -> None:
    loader = MetricRegistryLoader()

    metrics = loader.load_default()

    assert len(metrics) >= 200
    assert any(metric.key == "revenue" for metric in metrics)


def test_registry_loader_rejects_missing_display_name() -> None:
    loader = MetricRegistryLoader()

    with pytest.raises(ValueError, match="display_name"):
        loader.load_from_dict(
            {
                "revenue": {
                    "aliases": ["sales"],
                    "category": "income_statement",
                }
            }
        )


def test_registry_loader_rejects_duplicate_aliases() -> None:
    loader = MetricRegistryLoader()

    with pytest.raises(ValueError, match="Duplicate alias"):
        loader.load_from_dict(
            {
                "revenue": {
                    "display_name": "Revenue",
                    "aliases": ["sales"],
                    "category": "income_statement",
                },
                "gross_sales": {
                    "display_name": "Gross Sales",
                    "aliases": ["Sales"],
                    "category": "income_statement",
                },
            }
        )


def test_registry_loader_rejects_duplicate_aliases_within_metric() -> None:
    loader = MetricRegistryLoader()

    with pytest.raises(ValueError, match="Duplicate alias"):
        loader.load_from_dict(
            {
                "revenue": {
                    "display_name": "Revenue",
                    "aliases": ["net sales", "Net Sales"],
                    "category": "income_statement",
                }
            }
        )


def test_registry_loader_rejects_duplicate_display_names() -> None:
    loader = MetricRegistryLoader()

    with pytest.raises(ValueError, match="Duplicate display name"):
        loader.load_from_dict(
            {
                "revenue": {
                    "display_name": "Revenue",
                    "aliases": ["sales"],
                    "category": "income_statement",
                },
                "net_revenue": {
                    "display_name": "revenue",
                    "aliases": ["net sales"],
                    "category": "income_statement",
                },
            }
        )


def test_registry_loader_rejects_duplicate_canonical_metric_names() -> None:
    loader = MetricRegistryLoader()

    with pytest.raises(ValueError, match="Duplicate canonical metric name"):
        loader.load_from_dict(
            {
                "net_revenue": {
                    "display_name": "Net Revenue",
                    "aliases": ["net sales"],
                    "category": "income_statement",
                },
                " net revenue ": {
                    "display_name": "Reported Net Revenue",
                    "aliases": ["reported net sales"],
                    "category": "income_statement",
                },
            }
        )


def test_registry_loader_rejects_empty_registry() -> None:
    loader = MetricRegistryLoader()

    with pytest.raises(ValueError, match="cannot be empty"):
        loader.load_from_dict({})
