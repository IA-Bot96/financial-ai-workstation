"""Coverage measurement for QAE taxonomy mapping."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from qualitative_analysis_engine.models import MappingMethod

from .theme_canonicalizer import ThemeCanonicalizationResult, ThemeCanonicalizer


class TaxonomyMappingAuditService:
    """Measure taxonomy coverage for a collection of OCR insights."""

    def __init__(self, canonicalizer: ThemeCanonicalizer | None = None) -> None:
        self._canonicalizer = canonicalizer or ThemeCanonicalizer()

    def audit_insights(
        self,
        insights: Iterable[Mapping[str, Any]],
        *,
        bundle_path: str | None = None,
        report_year: str | int | None = None,
    ) -> dict[str, Any]:
        """Canonicalize insights and return a deterministic coverage audit."""

        results: list[ThemeCanonicalizationResult] = []
        for insight in insights:
            result = self._canonicalizer.canonicalize(
                str(insight.get("area") or ""),
                takeaway=str(insight.get("takeaway") or ""),
                source_section=str(insight.get("source_section") or ""),
                extraction_confidence=float(insight.get("confidence") or 1.0),
            )
            results.append(result)

        method_counts = Counter(result.mapping_method.value for result in results)
        theme_counts = Counter(
            result.theme_ref for result in results if result.theme_ref
        )
        category_counts = Counter(
            result.category_ref for result in results if result.category_ref
        )
        section_counts = Counter(
            result.section_route.source_section
            for result in results
            if result.section_route and result.section_route.source_section
        )
        confidence_distribution = _confidence_distribution(
            [result.confidence for result in results]
        )
        unmapped_results = [result for result in results if result.unmapped]
        conflicts = [result for result in results if result.section_theme_conflict]

        return {
            "bundle_path": bundle_path,
            "report_year": str(report_year) if report_year is not None else None,
            "insight_count": len(results),
            "theme_match_counts": dict(sorted(theme_counts.items())),
            "mapping_method_counts": dict(sorted(method_counts.items())),
            "unmapped_count": len(unmapped_results),
            "unmapped_rate": round(
                len(unmapped_results) / len(results), 6
            )
            if results
            else 0.0,
            "unmapped_samples": [
                {
                    "area": result.original_text,
                    "source_section": result.section_route.source_section
                    if result.section_route
                    else None,
                    "routed_category": result.category_ref,
                }
                for result in unmapped_results[:25]
            ],
            "confidence_distribution": confidence_distribution,
            "category_distribution": dict(sorted(category_counts.items())),
            "source_section_distribution": dict(sorted(section_counts.items())),
            "section_theme_conflict_count": len(conflicts),
            "section_theme_conflict_samples": [
                {
                    "area": result.original_text,
                    "theme_ref": result.theme_ref,
                    "theme_category": result.category_ref,
                    "source_section": result.section_route.source_section
                    if result.section_route
                    else None,
                    "section_categories": result.section_route.category_refs
                    if result.section_route
                    else (),
                }
                for result in conflicts[:25]
            ],
        }

    def audit_bundle(
        self,
        bundle_path: str | Path,
    ) -> dict[str, Any]:
        """Load a QueryEngineInputBundle sidecar and audit OCR insights."""

        path = Path(bundle_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        insights_by_year = payload.get("insights_results_by_report_year", {})
        all_insights: list[Mapping[str, Any]] = []
        for year, result in sorted(insights_by_year.items()):
            insights = result.get("insights", []) if isinstance(result, dict) else []
            for insight in insights:
                enriched = dict(insight)
                enriched["_report_year"] = year
                all_insights.append(enriched)

        audit = self.audit_insights(all_insights, bundle_path=str(path))
        audit["company_name"] = payload.get("company_name")
        audit["workbook_fingerprint"] = payload.get("workbook_fingerprint")
        audit["report_years"] = list(insights_by_year.keys())
        return audit

    def write_audit(
        self,
        output_path: str | Path,
        *,
        bundle_path: str | Path | None = None,
        insights: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate and persist a mapping audit."""

        if bundle_path is not None:
            audit = self.audit_bundle(bundle_path)
        elif insights is not None:
            audit = self.audit_insights(insights)
        else:
            audit = self.audit_insights(())

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_json_ready(audit), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit


def _confidence_distribution(values: list[float]) -> dict[str, int]:
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


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, MappingMethod):
        return value.value
    return value


__all__ = ["TaxonomyMappingAuditService"]

