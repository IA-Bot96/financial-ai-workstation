"""Deterministic QAE orchestration over existing Phase 3-6 services."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ocr_engine.models.insights_extraction import Insight
from qualitative_analysis_engine.models import (
    CategoryStatus,
    QualitativeCategoryResult,
    QualitativeRunResult,
    QualitativeSignal,
    SourceSnapshot,
)

from .category_aggregation import CategoryAggregationService
from .coverage_gate import QualitativeCoverageGate, QualitativeCoverageGateResult
from .insight_to_signal_adapter import InsightToSignalAdapter
from .scorecard import QualitativeScorecardService
from .theme_assembly import ThemeAssemblyResult, ThemeAssemblyService


@dataclass(frozen=True)
class QualitativeAnalysisRunArtifacts:
    """Intermediate deterministic QAE artifacts plus the authoritative run result."""

    signals: tuple[QualitativeSignal, ...]
    coverage_result: QualitativeCoverageGateResult
    assembly_result: ThemeAssemblyResult
    category_results: tuple[QualitativeCategoryResult, ...]
    run_result: QualitativeRunResult

    @property
    def run_metadata(self) -> dict[str, Any]:
        """Return compact run-level metadata for diagnostics and audits."""

        analyzed_statuses = {
            CategoryStatus.ANALYZED,
            CategoryStatus.ANALYZED_WITH_WARNING,
        }
        skipped_statuses = {
            CategoryStatus.SKIPPED_NO_ELIGIBLE_SIGNALS,
            CategoryStatus.SKIPPED_INSUFFICIENT_COVERAGE,
            CategoryStatus.SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY,
        }
        analyzed = [
            result.category_ref
            for result in self.category_results
            if result.status in analyzed_statuses
        ]
        skipped = [
            result.category_ref
            for result in self.category_results
            if result.status in skipped_statuses
        ]
        return {
            "signals_processed": len(self.signals),
            "themes_created": len(self.assembly_result.themes),
            "categories_analyzed": analyzed,
            "categories_skipped": skipped,
            "coverage_percent": self.run_result.coverage_summary.analyzable_percentage,
            "divergence_count": self.run_result.divergence_summary.total_divergences,
            "unmapped_count": self.run_result.unmapped_summary.total_unmapped,
        }


class QualitativeAnalysisOrchestrator:
    """Run QAE's deterministic annual-report pipeline end to end."""

    def __init__(
        self,
        *,
        coverage_gate: QualitativeCoverageGate | None = None,
        theme_assembly_service: ThemeAssemblyService | None = None,
        category_aggregation_service: CategoryAggregationService | None = None,
        scorecard_service: QualitativeScorecardService | None = None,
    ) -> None:
        self._coverage_gate = coverage_gate or QualitativeCoverageGate()
        self._theme_assembly_service = theme_assembly_service or ThemeAssemblyService()
        self._category_aggregation_service = (
            category_aggregation_service or CategoryAggregationService()
        )
        self._scorecard_service = scorecard_service or QualitativeScorecardService()

    def run(
        self,
        insights: Iterable[Insight | Mapping[str, Any]],
        *,
        entity_ref: str,
        workbook_fingerprint: str,
        entity_scope: str = "company",
        source_set: tuple[SourceSnapshot, ...] | None = None,
        section_confidence_by_page: Mapping[int, float] | None = None,
    ) -> QualitativeRunResult:
        """Execute QAE and return the authoritative QualitativeRunResult."""

        return self.run_with_artifacts(
            insights,
            entity_ref=entity_ref,
            workbook_fingerprint=workbook_fingerprint,
            entity_scope=entity_scope,
            source_set=source_set,
            section_confidence_by_page=section_confidence_by_page,
        ).run_result

    def run_with_artifacts(
        self,
        insights: Iterable[Insight | Mapping[str, Any]],
        *,
        entity_ref: str,
        workbook_fingerprint: str,
        entity_scope: str = "company",
        source_set: tuple[SourceSnapshot, ...] | None = None,
        section_confidence_by_page: Mapping[int, float] | None = None,
    ) -> QualitativeAnalysisRunArtifacts:
        """Execute all deterministic QAE services and return intermediate artifacts."""

        insight_list = tuple(insights)
        adapter = InsightToSignalAdapter(
            entity_ref=entity_ref,
            workbook_fingerprint=workbook_fingerprint,
        )
        signals = adapter.adapt_insights(
            insight_list,
            section_confidence_by_page=section_confidence_by_page,
        )
        coverage_result = self._coverage_gate.evaluate(signals)
        assembly_result = self._theme_assembly_service.assemble(
            signals,
            coverage_result,
        )
        category_results = self._category_aggregation_service.aggregate(
            coverage_result=coverage_result,
            assembly_result=assembly_result,
        )
        run_result = self._scorecard_service.build_run_result(
            entity_ref=entity_ref,
            entity_scope=entity_scope,
            workbook_fingerprint=workbook_fingerprint,
            coverage_result=coverage_result,
            assembly_result=assembly_result,
            category_results=category_results,
            source_set=source_set,
        )
        return QualitativeAnalysisRunArtifacts(
            signals=signals,
            coverage_result=coverage_result,
            assembly_result=assembly_result,
            category_results=category_results,
            run_result=run_result,
        )

    def write_smoke_audit(
        self,
        output_path: str | Path,
        insights: Iterable[Insight | Mapping[str, Any]],
        *,
        entity_ref: str,
        workbook_fingerprint: str,
        entity_scope: str = "company",
        source_set: tuple[SourceSnapshot, ...] | None = None,
        section_confidence_by_page: Mapping[int, float] | None = None,
    ) -> QualitativeAnalysisRunArtifacts:
        """Run QAE and write the Phase 7 smoke-audit payload."""

        artifacts = self.run_with_artifacts(
            insights,
            entity_ref=entity_ref,
            workbook_fingerprint=workbook_fingerprint,
            entity_scope=entity_scope,
            source_set=source_set,
            section_confidence_by_page=section_confidence_by_page,
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                self.to_smoke_audit_payload(artifacts),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return artifacts

    def to_smoke_audit_payload(
        self,
        artifacts: QualitativeAnalysisRunArtifacts,
    ) -> dict[str, Any]:
        """Build the required real-bundle smoke audit payload."""

        run_result = artifacts.run_result
        return {
            "taxonomy_version": run_result.versions.taxonomy_version,
            "authority_matrix_version": run_result.versions.authority_matrix_version,
            "insight_count": artifacts.coverage_result.total_signal_count,
            "signal_count": len(artifacts.signals),
            "theme_count": len(artifacts.assembly_result.themes),
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
            "coverage_summary": run_result.coverage_summary.model_dump(mode="json"),
            "divergence_summary": run_result.divergence_summary.model_dump(
                mode="json"
            ),
            "unmapped_summary": run_result.unmapped_summary.model_dump(mode="json"),
            "run_status": run_result.run_status.value,
            "run_metadata": artifacts.run_metadata,
            "constraints_observed": {
                "multi_source_logic": False,
                "announcements": False,
                "analyst_reports": False,
                "news": False,
                "llm_logic": False,
            },
        }


__all__ = [
    "QualitativeAnalysisOrchestrator",
    "QualitativeAnalysisRunArtifacts",
]
