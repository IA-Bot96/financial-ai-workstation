"""Coverage-first QAE scorecard and run-result generation."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qualitative_analysis_engine.models import (
    CategoryStatus,
    ConfidenceDistribution,
    DivergenceSummary,
    FVEHandoffPayload,
    QualitativeCategoryResult,
    QualitativeRunResult,
    RunCoverageSummary,
    RunMaterialitySummary,
    RunStatus,
    RunVersions,
    SourceSnapshot,
    SourceType,
    UnmappedSummary,
)

from .coverage_gate import QualitativeCoverageGateResult
from .theme_assembly import ThemeAssemblyResult


class QualitativeScorecardService:
    """Generate coverage-first QAE run results from category aggregation."""

    ASSEMBLY_CONTRACT_VERSION = "1.0.0"
    SCORECARD_CONTRACT_VERSION = "1.0.0"

    def build_run_result(
        self,
        *,
        entity_ref: str,
        entity_scope: str,
        workbook_fingerprint: str | None,
        coverage_result: QualitativeCoverageGateResult,
        assembly_result: ThemeAssemblyResult,
        category_results: tuple[QualitativeCategoryResult, ...],
        source_set: tuple[SourceSnapshot, ...] | None = None,
    ) -> QualitativeRunResult:
        """Build the QAE root run result without orchestration logic."""

        versions = RunVersions(
            taxonomy_version=coverage_result.taxonomy_version,
            authority_matrix_version=coverage_result.authority_matrix_versions[0]
            if coverage_result.authority_matrix_versions
            else "1.0.0",
            assembly_contract_version=self.ASSEMBLY_CONTRACT_VERSION,
            scorecard_contract_version=self.SCORECARD_CONTRACT_VERSION,
        )
        return QualitativeRunResult(
            entity_ref=entity_ref,
            entity_scope=entity_scope,
            source_set=source_set
            or (
                SourceSnapshot(
                    source_type=SourceType.ANNUAL_REPORT,
                    snapshot_ref=workbook_fingerprint or "unknown",
                ),
            ),
            observation_window=self._observation_window(assembly_result),
            category_results=category_results,
            coverage_summary=self._coverage_summary(coverage_result, category_results),
            confidence_summary=self._confidence_summary(assembly_result),
            materiality_summary=self._materiality_summary(assembly_result),
            divergence_summary=self._divergence_summary(assembly_result),
            unmapped_summary=self._unmapped_summary(assembly_result),
            recurring_analysis={
                "status": "not_evaluated",
                "reason": "Phase 6 does not implement recurring theme analysis.",
            },
            yoy_analysis={
                "status": "SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY",
                "reason": "YoY analysis requires multiple observation periods.",
            },
            fve_handoff=FVEHandoffPayload(
                handoff_id=f"qae_handoff:{entity_ref}:{coverage_result.taxonomy_version}",
                entity_ref=entity_ref,
                taxonomy_version=coverage_result.taxonomy_version,
                authority_matrix_version=versions.authority_matrix_version,
                workbook_fingerprint=workbook_fingerprint,
                coverage_caveats=tuple(coverage_result.warnings),
            ),
            run_status=self._run_status(category_results),
            versions=versions,
            generated_at=datetime.now(timezone.utc),
        )

    def write_audit(
        self,
        output_path: str | Path,
        *,
        run_result: QualitativeRunResult,
        coverage_result: QualitativeCoverageGateResult,
        assembly_result: ThemeAssemblyResult,
    ) -> None:
        """Persist the Phase 6 scorecard audit JSON."""

        category_statuses = {
            result.category_ref: result.status.value
            for result in run_result.category_results
        }
        audit = {
            "taxonomy_version": run_result.versions.taxonomy_version,
            "authority_matrix_version": run_result.versions.authority_matrix_version,
            "category_results": [
                {
                    "category_ref": result.category_ref,
                    "status": result.status.value,
                    "theme_count": len(result.owned_themes),
                    "signal_count": result.coverage.raw,
                    "mapped_count": result.coverage.mapped,
                    "unmapped_rate": result.coverage.unmapped_rate,
                    "divergence_count": len(result.divergence_refs),
                    "top_material_themes": list(
                        result.category_materiality.top_theme_refs
                    ),
                }
                for result in run_result.category_results
            ],
            "category_statuses": category_statuses,
            "analyzed_categories": [
                category
                for category, status in category_statuses.items()
                if status == CategoryStatus.ANALYZED.value
            ],
            "warning_categories": [
                category
                for category, status in category_statuses.items()
                if status == CategoryStatus.ANALYZED_WITH_WARNING.value
            ],
            "skipped_categories": [
                category
                for category, status in category_statuses.items()
                if status.startswith("SKIPPED")
            ],
            "run_coverage": run_result.coverage_summary.model_dump(mode="json"),
            "confidence_summary": run_result.confidence_summary.model_dump(mode="json"),
            "materiality_summary": run_result.materiality_summary.model_dump(
                mode="json"
            ),
            "divergence_counts": run_result.divergence_summary.model_dump(
                mode="json"
            ),
            "unmapped_counts": run_result.unmapped_summary.model_dump(mode="json"),
            "themes_created": len(assembly_result.themes),
            "signals_processed": coverage_result.total_signal_count,
            "run_status": run_result.run_status.value,
        }
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _coverage_summary(
        self,
        coverage_result: QualitativeCoverageGateResult,
        category_results: tuple[QualitativeCategoryResult, ...],
    ) -> RunCoverageSummary:
        category_status_counts = Counter(
            result.status for result in category_results
        )
        analyzable_categories = sum(
            1
            for result in category_results
            if result.status
            in {CategoryStatus.ANALYZED, CategoryStatus.ANALYZED_WITH_WARNING}
        )
        return RunCoverageSummary(
            analyzable_categories=analyzable_categories,
            total_categories=len(coverage_result.category_coverage),
            analyzable_percentage=round(
                (analyzable_categories / len(coverage_result.category_coverage)) * 100,
                6,
            )
            if coverage_result.category_coverage
            else 0.0,
            category_status_counts=dict(category_status_counts),
            per_source_coverage_matrix={
                SourceType.ANNUAL_REPORT: {
                    decision.category_ref: decision.raw_signal_count
                    for decision in coverage_result.category_coverage
                }
            },
            section_presence_map={
                section: count > 0
                for section, count in coverage_result.source_section_coverage.items()
            },
            mapped=coverage_result.mapped_signal_count,
            raw=coverage_result.total_signal_count,
            unmapped_rate=coverage_result.unmapped_rate,
        )

    def _confidence_summary(
        self,
        assembly_result: ThemeAssemblyResult,
    ) -> ConfidenceDistribution:
        buckets = assembly_result.confidence_distribution
        return ConfidenceDistribution(
            bucket_0=buckets.get("0.0", 0),
            bucket_0_1_to_0_5=buckets.get("0.1-0.5", 0),
            bucket_0_5_to_0_7=buckets.get("0.5-0.7", 0),
            bucket_0_7_to_0_9=buckets.get("0.7-0.9", 0),
            bucket_0_9_plus=buckets.get("0.9+", 0),
            ceiling_reasons=("keyword_or_review_confidence_ceiling",),
        )

    def _materiality_summary(
        self,
        assembly_result: ThemeAssemblyResult,
    ) -> RunMaterialitySummary:
        themes = tuple(
            sorted(
                assembly_result.themes,
                key=lambda theme: (
                    -theme.materiality,
                    theme.theme_reference.theme_ref,
                ),
            )
        )
        return RunMaterialitySummary(
            top_theme_refs=tuple(
                theme.theme_reference.theme_ref for theme in themes[:10]
            ),
            top_risk_refs=tuple(
                theme.theme_reference.theme_ref
                for theme in themes
                if theme.category_ref in {"business_risk", "operational_risk", "governance"}
            )[:10],
            ranking_basis="materiality_desc_confidence_reported_separately",
        )

    def _divergence_summary(
        self,
        assembly_result: ThemeAssemblyResult,
    ) -> DivergenceSummary:
        return DivergenceSummary(
            total_divergences=len(assembly_result.divergences),
            count_by_category=dict(
                Counter(divergence.category_ref for divergence in assembly_result.divergences)
            ),
            count_by_type=dict(
                Counter(
                    divergence.divergence_type
                    for divergence in assembly_result.divergences
                )
            ),
            cross_engine_candidates=tuple(
                divergence.divergence_id
                for divergence in assembly_result.divergences
                if divergence.divergence_type.value == "narrative_vs_numbers_candidate"
            ),
        )

    def _unmapped_summary(
        self,
        assembly_result: ThemeAssemblyResult,
    ) -> UnmappedSummary:
        return UnmappedSummary(
            total_unmapped=len(assembly_result.unmapped_queue),
            unmapped_by_category_prior=dict(
                Counter(
                    item.category_ref or "unknown"
                    for item in assembly_result.unmapped_queue
                )
            ),
            sample_claims=tuple(
                item.claim for item in assembly_result.unmapped_queue[:10]
            ),
            suggested_terms=tuple(
                sorted(
                    {
                        item.area
                        for item in assembly_result.unmapped_queue
                        if item.area
                    }
                )
            )[:25],
        )

    def _observation_window(
        self,
        assembly_result: ThemeAssemblyResult,
    ) -> dict[str, Any]:
        observations = [
            value
            for theme in assembly_result.themes
            for value in theme.evidence.observation_times.values()
            if isinstance(value, int)
        ]
        time_basis = sorted(
            {
                value.value
                for theme in assembly_result.themes
                for value in theme.evidence.time_basis_by_signal.values()
            }
        )
        return {
            "min": min(observations) if observations else None,
            "max": max(observations) if observations else None,
            "time_basis": ",".join(time_basis) if time_basis else None,
        }

    def _run_status(
        self,
        category_results: tuple[QualitativeCategoryResult, ...],
    ) -> RunStatus:
        if not category_results:
            return RunStatus.INSUFFICIENT_COVERAGE
        analyzed = sum(
            1
            for result in category_results
            if result.status
            in {CategoryStatus.ANALYZED, CategoryStatus.ANALYZED_WITH_WARNING}
        )
        ratio = analyzed / len(category_results)
        if ratio == 1.0:
            return RunStatus.ANALYZED_WITH_COVERAGE
        if ratio >= 0.5:
            return RunStatus.PARTIAL_COVERAGE
        return RunStatus.INSUFFICIENT_COVERAGE


__all__ = ["QualitativeScorecardService"]
