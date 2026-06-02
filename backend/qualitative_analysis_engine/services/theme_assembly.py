"""Deterministic theme assembly for admitted qualitative categories."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from qualitative_analysis_engine.models import (
    AuthorityClass,
    ClaimType,
    DivergenceReference,
    DivergenceType,
    Horizon,
    MappingMethod,
    QualitativeSignal,
    QualitativeTheme,
    SourceType,
    ThemeEvidence,
    ThemeReference,
    ThemeRole,
    ThemeSalience,
    TimeBasis,
)

from .coverage_gate import (
    CategoryAdmissionStatus,
    QualitativeCoverageGateResult,
)


class UnmappedSignalReference(BaseModel):
    """Unmapped signal retained for the taxonomy review queue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(..., min_length=1)
    category_ref: str | None = Field(default=None)
    source_section: str | None = Field(default=None)
    page_number: int | None = Field(default=None, gt=0)
    area: str | None = Field(default=None)
    claim: str = Field(..., min_length=1)


class ThemeAssemblyResult(BaseModel):
    """Result produced by deterministic QAE theme assembly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str = Field(..., min_length=1)
    authority_matrix_versions: tuple[str, ...] = Field(default_factory=tuple)
    admitted_categories: tuple[str, ...] = Field(default_factory=tuple)
    themes: tuple[QualitativeTheme, ...] = Field(default_factory=tuple)
    themes_by_category: dict[str, int] = Field(default_factory=dict)
    signals_per_theme: dict[str, int] = Field(default_factory=dict)
    unmapped_queue: tuple[UnmappedSignalReference, ...] = Field(default_factory=tuple)
    confidence_distribution: dict[str, int] = Field(default_factory=dict)
    materiality_distribution: dict[str, int] = Field(default_factory=dict)
    divergences: tuple[DivergenceReference, ...] = Field(default_factory=tuple)
    duplicate_artifacts_removed: int = Field(default=0, ge=0)

    def to_audit_payload(self) -> dict[str, Any]:
        """Return the Phase 5 audit payload."""

        return {
            "taxonomy_version": self.taxonomy_version,
            "authority_matrix_versions": list(self.authority_matrix_versions),
            "admitted_categories": list(self.admitted_categories),
            "themes_created": len(self.themes),
            "themes_by_category": self.themes_by_category,
            "signals_per_theme": self.signals_per_theme,
            "unmapped_queue_size": len(self.unmapped_queue),
            "unmapped_queue_samples": [
                item.model_dump(mode="json") for item in self.unmapped_queue[:25]
            ],
            "confidence_distribution": self.confidence_distribution,
            "materiality_distribution": self.materiality_distribution,
            "divergence_count": len(self.divergences),
            "duplicate_artifacts_removed": self.duplicate_artifacts_removed,
            "theme_refs": [
                theme.theme_reference.theme_ref for theme in self.themes
            ],
        }


class ThemeAssemblyService:
    """Assemble grounded theme instances from admitted qualitative signals."""

    CATEGORY_MATERIALITY_PRIOR = {
        "business_risk": 0.65,
        "governance": 0.65,
        "operational_risk": 0.58,
        "esg": 0.55,
        "strategy": 0.52,
        "outlook": 0.48,
    }

    POSITIVE_DIRECTION_TERMS = (
        "increase",
        "increased",
        "growth",
        "grew",
        "higher",
        "improved",
        "expanded",
        "surged",
        "recovery",
        "strong",
    )
    NEGATIVE_DIRECTION_TERMS = (
        "decline",
        "declined",
        "decrease",
        "decreased",
        "lower",
        "fell",
        "reduced",
        "weak",
        "slowdown",
        "pressure",
        "risk",
    )

    def assemble(
        self,
        signals: Iterable[QualitativeSignal],
        coverage_result: QualitativeCoverageGateResult,
    ) -> ThemeAssemblyResult:
        """Assemble themes for categories admitted by the coverage gate."""

        signal_list = tuple(signals)
        taxonomy_version = self._validate_taxonomy_versions(signal_list)
        admitted_categories = self._admitted_categories(coverage_result)
        unmapped_queue = tuple(
            UnmappedSignalReference(
                signal_id=signal.signal_id,
                category_ref=signal.category_ref,
                source_section=signal.source_section,
                page_number=signal.page_number,
                area=signal.source_metadata.get("area"),
                claim=signal.claim,
            )
            for signal in signal_list
            if signal.unmapped
        )

        grouped: dict[tuple[str, str, str, str], list[QualitativeSignal]] = (
            defaultdict(list)
        )
        eligible_signal_ids = self._eligible_signal_ids(coverage_result)
        for signal in signal_list:
            if signal.unmapped or not signal.creation_eligible:
                continue
            if signal.signal_id not in eligible_signal_ids:
                continue
            if not signal.theme_ref or not signal.category_ref:
                continue
            if signal.category_ref not in admitted_categories:
                continue
            key = (
                signal.entity_ref,
                signal.entity_scope.value,
                signal.theme_ref,
                signal.taxonomy_version,
            )
            grouped[key].append(signal)

        themes: list[QualitativeTheme] = []
        divergences: list[DivergenceReference] = []
        duplicate_artifacts_removed = 0
        for key in sorted(grouped):
            raw_group = tuple(sorted(grouped[key], key=lambda signal: signal.signal_id))
            unique_group, removed = self._deduplicate(raw_group)
            duplicate_artifacts_removed += removed
            if not unique_group:
                continue

            group_divergences = self._build_divergences(unique_group)
            divergences.extend(group_divergences)
            themes.append(
                self._build_theme(
                    key=key,
                    raw_signals=raw_group,
                    signals=unique_group,
                    divergences=tuple(group_divergences),
                )
            )

        themes = sorted(
            themes,
            key=lambda theme: (
                theme.category_ref,
                theme.theme_reference.theme_ref,
                theme.theme_reference.entity_ref,
            ),
        )

        return ThemeAssemblyResult(
            taxonomy_version=taxonomy_version,
            authority_matrix_versions=tuple(
                sorted({signal.authority_matrix_version for signal in signal_list})
            ),
            admitted_categories=tuple(sorted(admitted_categories)),
            themes=tuple(themes),
            themes_by_category=dict(
                sorted(Counter(theme.category_ref for theme in themes).items())
            ),
            signals_per_theme={
                theme.theme_reference.theme_ref: len(theme.signal_ids)
                for theme in themes
            },
            unmapped_queue=unmapped_queue,
            confidence_distribution=_distribution(
                [theme.theme_confidence for theme in themes]
            ),
            materiality_distribution=_distribution(
                [theme.materiality for theme in themes]
            ),
            divergences=tuple(divergences),
            duplicate_artifacts_removed=duplicate_artifacts_removed,
        )

    def write_audit(
        self,
        output_path: str | Path,
        signals: Iterable[QualitativeSignal],
        coverage_result: QualitativeCoverageGateResult,
    ) -> ThemeAssemblyResult:
        """Assemble themes and persist the Phase 5 audit JSON."""

        result = self.assemble(signals, coverage_result)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_audit_payload(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return result

    def _build_theme(
        self,
        *,
        key: tuple[str, str, str, str],
        raw_signals: tuple[QualitativeSignal, ...],
        signals: tuple[QualitativeSignal, ...],
        divergences: tuple[DivergenceReference, ...],
    ) -> QualitativeTheme:
        entity_ref, entity_scope, theme_ref, taxonomy_version = key
        category_ref = signals[0].category_ref or "unmapped"
        secondary_categories = _common_secondary_categories(signals)
        signal_ids = tuple(signal.signal_id for signal in signals)
        salience = (
            ThemeSalience.FULL_SALIENCE
            if len(signals) > 1
            else ThemeSalience.LOW_SALIENCE
        )
        low_salience = salience == ThemeSalience.LOW_SALIENCE
        theme_confidence = self._theme_confidence(signals, divergences)
        materiality = self._theme_materiality(signals, divergences)
        evidence_weight = self._evidence_weight(signals)

        evidence = ThemeEvidence(
            evidence_id=f"theme_evidence:{entity_ref}:{theme_ref}:{taxonomy_version}",
            theme_ref=theme_ref,
            signal_ids=signal_ids,
            signal_claims={signal.signal_id: signal.claim for signal in signals},
            signal_roles={
                signal.signal_id: ThemeRole.CREATES
                if signal.creation_eligible
                else ThemeRole.CONTEXTUALIZES
                for signal in signals
            },
            provenance_refs=tuple(_provenance_ref(signal) for signal in signals),
            observation_times={
                signal.signal_id: signal.observation_time for signal in signals
            },
            subject_periods={
                signal.signal_id: signal.subject_period for signal in signals
            },
            time_basis_by_signal={
                signal.signal_id: signal.time_basis for signal in signals
            },
            horizon_by_signal={
                signal.signal_id: signal.horizon for signal in signals
            },
            authority_class_by_signal={
                signal.signal_id: signal.authority_class for signal in signals
            },
            claim_type_by_signal={
                signal.signal_id: signal.claim_type for signal in signals
            },
            mapping_method_by_signal={
                signal.signal_id: signal.mapping_method for signal in signals
            },
            source_mix=dict(Counter(signal.source_type for signal in signals)),
            independent_origins=tuple(
                sorted({signal.source_type.value for signal in signals})
            ),
            divergence_refs=tuple(
                divergence.divergence_id for divergence in divergences
            ),
            duplicate_count=len(raw_signals),
            salience=salience,
            low_salience=low_salience,
        )

        return QualitativeTheme(
            theme_reference=ThemeReference(
                entity_ref=entity_ref,
                entity_scope=entity_scope,
                theme_ref=theme_ref,
                taxonomy_version=taxonomy_version,
            ),
            category_ref=category_ref,
            secondary_categories=secondary_categories,
            signal_ids=signal_ids,
            created_by_signal_ids=tuple(
                signal.signal_id for signal in signals if signal.creation_eligible
            ),
            evidence=evidence,
            divergence_refs=divergences,
            source_mix=dict(Counter(signal.source_type for signal in signals)),
            salience=salience,
            theme_confidence=theme_confidence,
            evidence_weight=evidence_weight,
            materiality=materiality,
            low_salience=low_salience,
            taxonomy_version=taxonomy_version,
            authority_matrix_version=signals[0].authority_matrix_version,
        )

    def _deduplicate(
        self,
        signals: tuple[QualitativeSignal, ...],
    ) -> tuple[tuple[QualitativeSignal, ...], int]:
        by_key: dict[tuple[Any, ...], QualitativeSignal] = {}
        for signal in signals:
            key = _dedup_key(signal)
            existing = by_key.get(key)
            if existing is None or signal.signal_confidence > existing.signal_confidence:
                by_key[key] = signal
        unique = tuple(sorted(by_key.values(), key=lambda signal: signal.signal_id))
        return unique, len(signals) - len(unique)

    def _build_divergences(
        self,
        signals: tuple[QualitativeSignal, ...],
    ) -> tuple[DivergenceReference, ...]:
        positive = [
            signal
            for signal in signals
            if _claim_direction(signal.claim) == "positive"
        ]
        negative = [
            signal
            for signal in signals
            if _claim_direction(signal.claim) == "negative"
        ]
        if not positive or not negative:
            return ()

        side_a = positive[0]
        side_b = negative[0]
        divergence = DivergenceReference(
            divergence_id=(
                f"divergence:{side_a.theme_ref}:{side_a.signal_id}:{side_b.signal_id}"
            ),
            divergence_type=DivergenceType.NARRATIVE_VS_NARRATIVE,
            theme_ref=side_a.theme_ref or "unknown_theme",
            category_ref=side_a.category_ref or "unknown_category",
            signal_ids=(side_a.signal_id, side_b.signal_id),
            side_a_signal_id=side_a.signal_id,
            side_b_signal_id=side_b.signal_id,
            side_a_authority_class=side_a.authority_class,
            side_b_authority_class=side_b.authority_class,
            summary="Signals carry opposing directional language for the same theme.",
            confidence_impact=0.1,
            materiality_impact=0.15,
            auto_resolved=False,
        )
        return (divergence,)

    def _theme_confidence(
        self,
        signals: tuple[QualitativeSignal, ...],
        divergences: tuple[DivergenceReference, ...],
    ) -> float:
        base = max(signal.signal_confidence for signal in signals)
        penalty = min(0.3, sum(item.confidence_impact for item in divergences))
        ceiling = 1.0
        if all(signal.mapping_method == MappingMethod.KEYWORD for signal in signals):
            ceiling = min(ceiling, 0.7)
        if all(signal.review_status == "review" for signal in signals):
            ceiling = min(ceiling, 0.7)
        if all(signal.review_status == "rejected_low_confidence" for signal in signals):
            ceiling = min(ceiling, 0.5)
        return round(max(0.0, min(ceiling, base - penalty)), 6)

    def _evidence_weight(self, signals: tuple[QualitativeSignal, ...]) -> float:
        authority_weight = max(_authority_weight(signal.authority_class) for signal in signals)
        section_spread = len({signal.source_section for signal in signals if signal.source_section})
        support_lift = min(0.15, (len(signals) - 1) * 0.03)
        section_lift = min(0.15, max(0, section_spread - 1) * 0.05)
        specificity_lift = 0.05 if any(signal.is_quantified for signal in signals) else 0.0
        return round(min(1.0, authority_weight * 0.65 + support_lift + section_lift + specificity_lift), 6)

    def _theme_materiality(
        self,
        signals: tuple[QualitativeSignal, ...],
        divergences: tuple[DivergenceReference, ...],
    ) -> float:
        category_ref = signals[0].category_ref or "unknown"
        materiality = self.CATEGORY_MATERIALITY_PRIOR.get(category_ref, 0.5)
        materiality += min(0.18, (len(signals) - 1) * 0.03)
        if any(signal.horizon == Horizon.FORWARD for signal in signals):
            materiality += 0.05
        if any(signal.is_quantified for signal in signals):
            materiality += 0.05
        materiality += min(0.2, sum(item.materiality_impact for item in divergences))
        return round(min(1.0, materiality), 6)

    def _admitted_categories(
        self,
        coverage_result: QualitativeCoverageGateResult,
    ) -> set[str]:
        return {
            decision.category_ref
            for decision in coverage_result.category_coverage
            if decision.admission_status
            in {
                CategoryAdmissionStatus.ADMITTED,
                CategoryAdmissionStatus.ADMITTED_WITH_WARNING,
            }
        }

    def _eligible_signal_ids(
        self,
        coverage_result: QualitativeCoverageGateResult,
    ) -> set[str]:
        return {
            signal_id
            for decision in coverage_result.category_coverage
            if decision.admission_status
            in {
                CategoryAdmissionStatus.ADMITTED,
                CategoryAdmissionStatus.ADMITTED_WITH_WARNING,
            }
            for signal_id in decision.eligible_signal_ids
        }

    def _validate_taxonomy_versions(
        self,
        signals: tuple[QualitativeSignal, ...],
    ) -> str:
        versions = {signal.taxonomy_version for signal in signals}
        if len(versions) > 1:
            raise ValueError("ThemeAssemblyService cannot mix taxonomy versions.")
        return next(iter(versions)) if versions else "1.0.0"


def _dedup_key(signal: QualitativeSignal) -> tuple[Any, ...]:
    provenance = signal.provenance
    return (
        signal.source_type.value,
        provenance.provenance_type.value,
        signal.page_number,
        signal.source_section,
        getattr(provenance, "workbook_fingerprint", None),
        signal.observation_time,
        signal.subject_period,
        signal.theme_ref,
    )


def _provenance_ref(signal: QualitativeSignal) -> str:
    return (
        f"{signal.provenance.provenance_type.value}:"
        f"{signal.page_number}:"
        f"{signal.source_section or 'UNKNOWN'}"
    )


def _common_secondary_categories(
    signals: tuple[QualitativeSignal, ...],
) -> tuple[str, ...]:
    values = {
        category
        for signal in signals
        for category in signal.source_metadata.get("secondary_categories", ())
    }
    return tuple(sorted(values))[:2]


def _authority_weight(authority_class: AuthorityClass) -> float:
    weights = {
        AuthorityClass.REGULATORY_INDEPENDENT: 1.0,
        AuthorityClass.AUDITED_ISSUER: 0.9,
        AuthorityClass.OFFICIAL_ISSUER_UNAUDITED: 0.8,
        AuthorityClass.INDEPENDENT_OPINION: 0.75,
        AuthorityClass.SECTOR_AGGREGATE: 0.65,
        AuthorityClass.MARKET_REVEALED: 0.6,
        AuthorityClass.ISSUER_DESCRIPTIVE: 0.5,
    }
    return weights[authority_class]


def _claim_direction(claim: str) -> str | None:
    normalized = claim.lower()
    positive = any(term in normalized for term in ThemeAssemblyService.POSITIVE_DIRECTION_TERMS)
    negative = any(term in normalized for term in ThemeAssemblyService.NEGATIVE_DIRECTION_TERMS)
    if positive and not negative:
        return "positive"
    if negative and not positive:
        return "negative"
    return None


def _distribution(values: list[float]) -> dict[str, int]:
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


__all__ = [
    "ThemeAssemblyResult",
    "ThemeAssemblyService",
    "UnmappedSignalReference",
]
