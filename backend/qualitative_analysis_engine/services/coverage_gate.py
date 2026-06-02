"""Coverage gate and category admission for generated qualitative signals."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from qualitative_analysis_engine.models import QualitativeSignal

from .taxonomy_loader import TaxonomyDefinition, TaxonomyLoader
from .text_normalization import normalize_text


class CategoryAdmissionStatus(str, Enum):
    """Deterministic category admission decision."""

    ADMITTED = "ADMITTED"
    ADMITTED_WITH_WARNING = "ADMITTED_WITH_WARNING"
    SKIPPED_INSUFFICIENT_COVERAGE = "SKIPPED_INSUFFICIENT_COVERAGE"
    SKIPPED_NO_ELIGIBLE_SIGNALS = "SKIPPED_NO_ELIGIBLE_SIGNALS"


class CategoryCoverageDecision(BaseModel):
    """Coverage and admission details for one qualitative category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category_ref: str = Field(..., min_length=1)
    admission_status: CategoryAdmissionStatus = Field(
        ..., description="Category admission decision."
    )
    raw_signal_count: int = Field(..., ge=0)
    mapped_signal_count: int = Field(..., ge=0)
    unmapped_signal_count: int = Field(..., ge=0)
    eligible_signal_count: int = Field(
        ..., ge=0, description="Mapped creation-eligible signals over confidence floor."
    )
    mapped_coverage_percent: float = Field(..., ge=0, le=100)
    unmapped_rate: float = Field(..., ge=0, le=1)
    source_section_counts: dict[str, int] = Field(default_factory=dict)
    expected_source_sections: tuple[str, ...] = Field(default_factory=tuple)
    expected_sections_present: tuple[str, ...] = Field(default_factory=tuple)
    expected_sections_absent: tuple[str, ...] = Field(default_factory=tuple)
    warning_reasons: tuple[str, ...] = Field(default_factory=tuple)
    skip_reason: str | None = Field(default=None)
    signal_ids: tuple[str, ...] = Field(default_factory=tuple)
    mapped_signal_ids: tuple[str, ...] = Field(default_factory=tuple)
    unmapped_signal_ids: tuple[str, ...] = Field(default_factory=tuple)
    eligible_signal_ids: tuple[str, ...] = Field(default_factory=tuple)
    provenance_records: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QualitativeCoverageGateResult(BaseModel):
    """Run-level coverage gate result for qualitative signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str = Field(..., min_length=1)
    authority_matrix_versions: tuple[str, ...] = Field(default_factory=tuple)
    total_signal_count: int = Field(..., ge=0)
    mapped_signal_count: int = Field(..., ge=0)
    unmapped_signal_count: int = Field(..., ge=0)
    mapped_coverage_percent: float = Field(..., ge=0, le=100)
    unmapped_rate: float = Field(..., ge=0, le=1)
    admitted_categories: tuple[str, ...] = Field(default_factory=tuple)
    warning_categories: tuple[str, ...] = Field(default_factory=tuple)
    skipped_categories: tuple[str, ...] = Field(default_factory=tuple)
    category_coverage: tuple[CategoryCoverageDecision, ...] = Field(
        default_factory=tuple
    )
    source_section_coverage: dict[str, int] = Field(default_factory=dict)
    warnings: tuple[str, ...] = Field(default_factory=tuple)

    def to_audit_payload(self) -> dict[str, Any]:
        """Return the JSON audit payload required by Phase 4."""

        return {
            "taxonomy_version": self.taxonomy_version,
            "authority_matrix_versions": list(self.authority_matrix_versions),
            "total_signal_count": self.total_signal_count,
            "mapped_signal_count": self.mapped_signal_count,
            "unmapped_signal_count": self.unmapped_signal_count,
            "mapped_coverage_percent": self.mapped_coverage_percent,
            "unmapped_rate": self.unmapped_rate,
            "admitted_categories": list(self.admitted_categories),
            "warning_categories": list(self.warning_categories),
            "skipped_categories": list(self.skipped_categories),
            "mapped_coverage": {
                "mapped_signals": self.mapped_signal_count,
                "total_signals": self.total_signal_count,
                "mapped_coverage_percent": self.mapped_coverage_percent,
            },
            "unmapped_coverage": {
                "unmapped_signals": self.unmapped_signal_count,
                "total_signals": self.total_signal_count,
                "unmapped_rate": self.unmapped_rate,
            },
            "source_section_coverage": self.source_section_coverage,
            "category_coverage_breakdown": [
                decision.model_dump(mode="json")
                for decision in self.category_coverage
            ],
            "warnings": list(self.warnings),
        }


class QualitativeCoverageGate:
    """Evaluate qualitative signal coverage and category admission."""

    SIGNAL_CONFIDENCE_FLOOR = 0.50
    UNMAPPED_WARNING_RATE = 0.25
    UNMAPPED_SKIP_RATE = 0.50
    MAPPED_COVERAGE_FLOOR_PERCENT = 50.0
    MIN_ELIGIBLE_SIGNALS_FOR_FULL_ADMISSION = 2

    EXPECTED_SOURCE_SECTIONS_BY_CATEGORY = {
        "outlook": (
            "Chairman Review",
            "CEO Review",
            "Directors Report",
            "Management Discussion & Analysis",
            "Business Review",
            "Opportunities",
            "Outlook",
            "Strategy",
            "Financial Review",
        ),
        "strategy": (
            "Chairman Review",
            "CEO Review",
            "Directors Report",
            "Management Discussion & Analysis",
            "Business Review",
            "Opportunities",
            "Strategy",
        ),
        "business_risk": (
            "Management Discussion & Analysis",
            "Risks",
            "Financial Review",
        ),
        "operational_risk": ("Business Review", "Risks"),
        "governance": ("Chairman Review", "Directors Report"),
        "esg": ("Sustainability", "ESG"),
    }

    def __init__(
        self,
        taxonomy: TaxonomyDefinition | None = None,
        *,
        taxonomy_loader: TaxonomyLoader | None = None,
        expected_source_sections_by_category: Mapping[str, tuple[str, ...]]
        | None = None,
    ) -> None:
        self._taxonomy = taxonomy or (taxonomy_loader or TaxonomyLoader()).load()
        self._expected_source_sections_by_category = (
            dict(expected_source_sections_by_category)
            if expected_source_sections_by_category is not None
            else dict(self.EXPECTED_SOURCE_SECTIONS_BY_CATEGORY)
        )

    def evaluate(
        self,
        signals: Iterable[QualitativeSignal],
    ) -> QualitativeCoverageGateResult:
        """Evaluate coverage and admission for generated qualitative signals."""

        signal_list = tuple(signals)
        taxonomy_version = self._validate_taxonomy_versions(signal_list)
        authority_matrix_versions = tuple(
            sorted({signal.authority_matrix_version for signal in signal_list})
        )
        by_category: dict[str, list[QualitativeSignal]] = defaultdict(list)
        for signal in signal_list:
            if signal.category_ref:
                by_category[signal.category_ref].append(signal)

        category_decisions: list[CategoryCoverageDecision] = []
        for category_ref in sorted(self._taxonomy.categories):
            category_decisions.append(
                self._evaluate_category(
                    category_ref,
                    tuple(by_category.get(category_ref, ())),
                )
            )

        mapped_signal_count = sum(1 for signal in signal_list if not signal.unmapped)
        unmapped_signal_count = sum(1 for signal in signal_list if signal.unmapped)
        total_signal_count = len(signal_list)
        admitted_categories = tuple(
            decision.category_ref
            for decision in category_decisions
            if decision.admission_status == CategoryAdmissionStatus.ADMITTED
        )
        warning_categories = tuple(
            decision.category_ref
            for decision in category_decisions
            if decision.admission_status
            == CategoryAdmissionStatus.ADMITTED_WITH_WARNING
        )
        skipped_categories = tuple(
            decision.category_ref
            for decision in category_decisions
            if decision.admission_status
            in {
                CategoryAdmissionStatus.SKIPPED_INSUFFICIENT_COVERAGE,
                CategoryAdmissionStatus.SKIPPED_NO_ELIGIBLE_SIGNALS,
            }
        )

        return QualitativeCoverageGateResult(
            taxonomy_version=taxonomy_version,
            authority_matrix_versions=authority_matrix_versions,
            total_signal_count=total_signal_count,
            mapped_signal_count=mapped_signal_count,
            unmapped_signal_count=unmapped_signal_count,
            mapped_coverage_percent=_percent(mapped_signal_count, total_signal_count),
            unmapped_rate=_rate(unmapped_signal_count, total_signal_count),
            admitted_categories=admitted_categories,
            warning_categories=warning_categories,
            skipped_categories=skipped_categories,
            category_coverage=tuple(category_decisions),
            source_section_coverage=dict(
                sorted(
                    Counter(
                        signal.source_section or "UNKNOWN"
                        for signal in signal_list
                    ).items()
                )
            ),
            warnings=tuple(
                warning
                for decision in category_decisions
                for warning in decision.warning_reasons
            ),
        )

    def write_audit(
        self,
        output_path: str | Path,
        signals: Iterable[QualitativeSignal],
    ) -> QualitativeCoverageGateResult:
        """Evaluate signals and persist the Phase 4 coverage-gate audit."""

        result = self.evaluate(signals)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_audit_payload(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return result

    def _evaluate_category(
        self,
        category_ref: str,
        signals: tuple[QualitativeSignal, ...],
    ) -> CategoryCoverageDecision:
        raw_signal_count = len(signals)
        mapped_signals = tuple(signal for signal in signals if not signal.unmapped)
        unmapped_signals = tuple(signal for signal in signals if signal.unmapped)
        eligible_signals = tuple(
            signal
            for signal in mapped_signals
            if signal.creation_eligible
            and signal.signal_confidence >= self.SIGNAL_CONFIDENCE_FLOOR
        )
        source_section_counts = Counter(
            signal.source_section or "UNKNOWN" for signal in signals
        )
        expected_sections = self._expected_source_sections_by_category.get(
            category_ref, ()
        )
        expected_present = tuple(
            section
            for section in expected_sections
            if normalize_text(section)
            in {normalize_text(value) for value in source_section_counts}
        )
        expected_absent = tuple(
            section for section in expected_sections if section not in expected_present
        )
        mapped_coverage_percent = _percent(len(mapped_signals), raw_signal_count)
        unmapped_rate = _rate(len(unmapped_signals), raw_signal_count)

        status, warnings, skip_reason = self._decide_admission(
            raw_signal_count=raw_signal_count,
            mapped_signal_count=len(mapped_signals),
            eligible_signal_count=len(eligible_signals),
            mapped_coverage_percent=mapped_coverage_percent,
            unmapped_rate=unmapped_rate,
            expected_sections_present=expected_present,
        )

        return CategoryCoverageDecision(
            category_ref=category_ref,
            admission_status=status,
            raw_signal_count=raw_signal_count,
            mapped_signal_count=len(mapped_signals),
            unmapped_signal_count=len(unmapped_signals),
            eligible_signal_count=len(eligible_signals),
            mapped_coverage_percent=mapped_coverage_percent,
            unmapped_rate=unmapped_rate,
            source_section_counts=dict(sorted(source_section_counts.items())),
            expected_source_sections=expected_sections,
            expected_sections_present=expected_present,
            expected_sections_absent=expected_absent,
            warning_reasons=warnings,
            skip_reason=skip_reason,
            signal_ids=tuple(signal.signal_id for signal in signals),
            mapped_signal_ids=tuple(signal.signal_id for signal in mapped_signals),
            unmapped_signal_ids=tuple(signal.signal_id for signal in unmapped_signals),
            eligible_signal_ids=tuple(signal.signal_id for signal in eligible_signals),
            provenance_records=tuple(_provenance_record(signal) for signal in signals),
        )

    def _decide_admission(
        self,
        *,
        raw_signal_count: int,
        mapped_signal_count: int,
        eligible_signal_count: int,
        mapped_coverage_percent: float,
        unmapped_rate: float,
        expected_sections_present: tuple[str, ...],
    ) -> tuple[CategoryAdmissionStatus, tuple[str, ...], str | None]:
        warnings: list[str] = []
        if eligible_signal_count == 0:
            return (
                CategoryAdmissionStatus.SKIPPED_NO_ELIGIBLE_SIGNALS,
                ("no_eligible_signals",),
                "No mapped creation-eligible signals met the confidence floor.",
            )

        if (
            raw_signal_count > 0
            and mapped_signal_count > 0
            and (
                mapped_coverage_percent < self.MAPPED_COVERAGE_FLOOR_PERCENT
                or unmapped_rate > self.UNMAPPED_SKIP_RATE
            )
        ):
            return (
                CategoryAdmissionStatus.SKIPPED_INSUFFICIENT_COVERAGE,
                ("insufficient_mapped_coverage",),
                "Mapped coverage is below the category coverage floor.",
            )

        if unmapped_rate > self.UNMAPPED_WARNING_RATE:
            warnings.append("elevated_unmapped_rate")
        if eligible_signal_count < self.MIN_ELIGIBLE_SIGNALS_FOR_FULL_ADMISSION:
            warnings.append("insufficient_category_evidence")
        if raw_signal_count > 0 and not expected_sections_present:
            warnings.append("missing_source_section_coverage")

        if warnings:
            return (
                CategoryAdmissionStatus.ADMITTED_WITH_WARNING,
                tuple(warnings),
                None,
            )
        return CategoryAdmissionStatus.ADMITTED, (), None

    def _validate_taxonomy_versions(
        self,
        signals: tuple[QualitativeSignal, ...],
    ) -> str:
        versions = {signal.taxonomy_version for signal in signals}
        if len(versions) > 1:
            raise ValueError("QualitativeCoverageGate cannot mix taxonomy versions.")
        if versions:
            version = next(iter(versions))
            if version != self._taxonomy.taxonomy_version:
                raise ValueError(
                    "Signal taxonomy_version does not match loaded taxonomy."
                )
            return version
        return self._taxonomy.taxonomy_version


def _percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 6)


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _provenance_record(signal: QualitativeSignal) -> dict[str, Any]:
    return {
        "signal_id": signal.signal_id,
        "provenance_type": signal.provenance.provenance_type.value,
        "page_number": signal.page_number,
        "source_section": signal.source_section,
        "source_report_year": signal.source_report_year,
        "value_year": signal.value_year,
        "workbook_fingerprint": getattr(
            signal.provenance, "workbook_fingerprint", None
        ),
    }


__all__ = [
    "CategoryAdmissionStatus",
    "CategoryCoverageDecision",
    "QualitativeCoverageGate",
    "QualitativeCoverageGateResult",
]

