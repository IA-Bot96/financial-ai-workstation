"""Shared metric normalizer interface."""

from abc import ABC, abstractmethod

from shared.normalization.models.normalized_metric import NormalizedMetric


class IMetricNormalizer(ABC):
    """Contract for normalizing a single financial metric name."""

    @abstractmethod
    def normalize_metric(self, metric_name: str) -> NormalizedMetric:
        """Normalize one metric name to the canonical registry."""
