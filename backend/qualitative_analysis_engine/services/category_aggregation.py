"""Category aggregation for assembled qualitative themes."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from qualitative_analysis_engine.models import (
    CategoryCoverage,
    CategoryMateriality,
    CategoryStatus,
    ConfidenceDistribution,
    QualitativeCategoryResult,
    QualitativeTheme,
    SourceType,
    ThemeSalience,
)

from .coverage_gate import (
    CategoryAdmissionStatus,
    CategoryCoverageDecision,
    QualitativeCoverageGateResult,
)
from .theme_assembly import ThemeAssemblyResult


class CategoryAggregationService:
    """Aggregate assembled themes into category-level QAE results."""

    def aggregate(
        self,
        *,
        coverage_result: QualitativeCoverageGateResult,
        assembly_result: ThemeAssemblyResult,
    ) -> tuple[QualitativeCategoryResult, ...]:
        """Create one QualitativeCategoryResult for every taxonomy category."""

        themes_by_category: dict[str, list[QualitativeTheme]] = defaultdict(list)
        for theme in assembly_result.themes:
            themes_by_category[theme.category_ref].append(theme)

        category_results: list[QualitativeCategoryResult] = []
        for decision in coverage_result.category_coverage:
            owned_themes = tuple(
                sorted(
                    themes_by_category.get(decision.category_ref, ()),
                    key=lambda theme: theme.theme_reference.theme_ref,
                )
            )
            category_results.append(
                QualitativeCategoryResult(
                    category_ref=decision.category_ref,
                    status=self._category_status(decision, owned_themes),
                    owned_themes=owned_themes,
                    theme_count_by_salience=self._theme_count_by_salience(
                        owned_themes
                    ),
                    coverage=CategoryCoverage(
                        mapped=decision.mapped_signal_count,
                        raw=decision.raw_signal_count,
                        unmapped_rate=decision.unmapped_rate,
                        source_mix=self._source_mix(owned_themes),
                        expected_sections_present=decision.expected_sections_present,
                        expected_sections_absent=decision.expected_sections_absent,
                    ),
                    category_confidence=_confidence_distribution(
                        [theme.theme_confidence for theme in owned_themes],
                        ceiling_reasons=decision.warning_reasons,
                    ),
                    category_materiality=self._category_materiality(owned_themes),
                    divergence_refs=tuple(
                        divergence
                        for divergence in assembly_result.divergences
                        if divergence.category_ref == decision.category_ref
                    ),
                    unmapped_pool_ref=f"unmapped:{decision.category_ref}"
                    if decision.unmapped_signal_count > 0
                    else None,
                    skip_reason=decision.skip_reason,
                    evidence_refs=self._evidence_refs(decision, owned_themes),
                    taxonomy_version=coverage_result.taxonomy_version,
                    authority_matrix_version=(
                        coverage_result.authority_matrix_versions[0]
                        if coverage_result.authority_matrix_versions
                        else "1.0.0"
                    ),
                )
            )
        return tuple(category_results)

    def _category_status(
        self,
        decision: CategoryCoverageDecision,
        owned_themes: tuple[QualitativeTheme, ...],
    ) -> CategoryStatus:
        if (
            decision.admission_status
            == CategoryAdmissionStatus.SKIPPED_NO_ELIGIBLE_SIGNALS
        ):
            return CategoryStatus.SKIPPED_NO_ELIGIBLE_SIGNALS
        if (
            decision.admission_status
            == CategoryAdmissionStatus.SKIPPED_INSUFFICIENT_COVERAGE
        ):
            return CategoryStatus.SKIPPED_INSUFFICIENT_COVERAGE
        if (
            decision.admission_status == CategoryAdmissionStatus.ADMITTED_WITH_WARNING
            or decision.warning_reasons
            or any(theme.low_salience for theme in owned_themes)
            or not owned_themes
        ):
            return CategoryStatus.ANALYZED_WITH_WARNING
        return CategoryStatus.ANALYZED

    def _theme_count_by_salience(
        self,
        themes: Iterable[QualitativeTheme],
    ) -> dict[ThemeSalience, int]:
        return dict(Counter(theme.salience for theme in themes))

    def _category_materiality(
        self,
        themes: tuple[QualitativeTheme, ...],
    ) -> CategoryMateriality:
        if not themes:
            return CategoryMateriality(
                max_materiality=None,
                weighted_materiality=None,
                aggregation_method="max",
                top_theme_refs=(),
            )
        sorted_themes = tuple(
            sorted(
                themes,
                key=lambda theme: (
                    -theme.materiality,
                    theme.theme_reference.theme_ref,
                ),
            )
        )
        max_materiality = sorted_themes[0].materiality
        total_weight = sum(theme.evidence_weight for theme in themes)
        weighted_materiality = (
            sum(theme.materiality * theme.evidence_weight for theme in themes)
            / total_weight
            if total_weight
            else max_materiality
        )
        return CategoryMateriality(
            max_materiality=max_materiality,
            weighted_materiality=round(weighted_materiality, 6),
            aggregation_method="max_plus_weighted_non_dilutive",
            top_theme_refs=tuple(
                theme.theme_reference.theme_ref for theme in sorted_themes[:5]
            ),
        )

    def _source_mix(
        self,
        themes: tuple[QualitativeTheme, ...],
    ) -> dict[SourceType, int]:
        counts: Counter[SourceType] = Counter()
        for theme in themes:
            for source_type, count in theme.source_mix.items():
                counts[source_type] += count
        return dict(counts)

    def _evidence_refs(
        self,
        decision: CategoryCoverageDecision,
        themes: tuple[QualitativeTheme, ...],
    ) -> tuple[str, ...]:
        refs = [theme.evidence.evidence_id for theme in themes]
        if decision.skip_reason:
            refs.append(f"coverage_gap:{decision.category_ref}")
        if decision.unmapped_signal_count:
            refs.append(f"unmapped:{decision.category_ref}")
        return tuple(refs)


def _confidence_distribution(
    values: list[float],
    *,
    ceiling_reasons: tuple[str, ...] = (),
) -> ConfidenceDistribution:
    buckets = _bucket_counts(values)
    return ConfidenceDistribution(
        bucket_0=buckets["0.0"],
        bucket_0_1_to_0_5=buckets["0.1-0.5"],
        bucket_0_5_to_0_7=buckets["0.5-0.7"],
        bucket_0_7_to_0_9=buckets["0.7-0.9"],
        bucket_0_9_plus=buckets["0.9+"],
        ceiling_reasons=ceiling_reasons,
    )


def _bucket_counts(values: list[float]) -> dict[str, int]:
    distribution = {
        "0.0": 0,
        "0.1-0.5": 0,
        "0.5-0.7": 0,
        "0.7-0.9": 0,
        "0.9+": 0,
    }
    for value in values:
        if value == 0:
            distribution["0.0"] += 1
        elif value < 0.5:
            distribution["0.1-0.5"] += 1
        elif value < 0.7:
            distribution["0.5-0.7"] += 1
        elif value < 0.9:
            distribution["0.7-0.9"] += 1
        else:
            distribution["0.9+"] += 1
    return distribution


__all__ = ["CategoryAggregationService"]
