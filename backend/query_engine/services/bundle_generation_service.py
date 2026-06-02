"""Generate Query Engine input bundles after workbook population."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.input_bundle import (
    QUERY_ENGINE_INPUT_SCHEMA_VERSION,
    QueryEngineInputBundle,
)
from query_engine.services.bundle_serializer import QueryEngineBundleSerializer
from query_engine.services.fingerprint_service import QueryEngineFingerprintService
from shared.models.company_context import CompanyContext
from workbook_population.models.workbook_cell_mapping import (
    WorkbookCellMappingDraft,
)

logger = logging.getLogger(__name__)


class QueryEnginePhase0Report(BaseModel):
    """Operational report for Query Engine bundle generation."""

    model_config = ConfigDict(extra="forbid")

    bundle_path: str = Field(..., description="Generated sidecar path.")
    bundle_size_bytes: int = Field(..., ge=0, description="Serialized JSON size.")
    mappings_persisted: int = Field(..., ge=0, description="Persisted cell mappings.")
    fingerprint_generated: bool = Field(..., description="Whether fingerprint exists.")
    workbook_fingerprint: str = Field(..., description="Generated bundle fingerprint.")
    serialization_time_seconds: float = Field(
        ..., ge=0, description="Sidecar serialization duration."
    )
    validation_results: dict[str, Any] = Field(
        ..., description="Bundle validation result serialized as JSON."
    )


class QueryEngineBundleGenerationService:
    """Build and persist Query Engine input bundles from completed OCR context."""

    def __init__(
        self,
        *,
        cell_mapping_provider: Any | None = None,
        serializer: QueryEngineBundleSerializer | None = None,
        fingerprint_service: QueryEngineFingerprintService | None = None,
        report_path: str | Path = "output/query_engine_phase0_report.json",
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize bundle generation with injectable dependencies."""

        self._cell_mapping_provider = cell_mapping_provider
        self._serializer = serializer or QueryEngineBundleSerializer()
        self._fingerprint_service = fingerprint_service or QueryEngineFingerprintService()
        self._report_path = Path(report_path)
        self._logger = log or logger
        self._last_bundle: QueryEngineInputBundle | None = None
        self._last_report: QueryEnginePhase0Report | None = None

    @property
    def last_bundle(self) -> QueryEngineInputBundle | None:
        """Return the most recently generated bundle."""

        return self._last_bundle

    @property
    def last_report(self) -> QueryEnginePhase0Report | None:
        """Return the most recent Phase 0 generation report."""

        return self._last_report

    def process(self, context: CompanyContext) -> CompanyContext:
        """Generate a Query Engine bundle and attach its path to context."""

        if context.generated_workbook is None:
            raise ValueError("generated_workbook is required before bundle generation")
        if context.financial_year_consolidation_result is None:
            raise ValueError(
                "financial_year_consolidation_result is required before bundle generation"
            )

        mapping_drafts = self._mapping_drafts()
        payload = self._fingerprint_payload(context, mapping_drafts)
        workbook_path = context.generated_workbook.output_file_path
        workbook_fingerprint = self._fingerprint_service.workbook_fingerprint(
            workbook_path=workbook_path,
            structured_payload=payload,
        )
        mappings = [
            draft.to_record(workbook_fingerprint) for draft in mapping_drafts
        ]
        bundle = QueryEngineInputBundle(
            schema_version=QUERY_ENGINE_INPUT_SCHEMA_VERSION,
            workbook_id=f"wb_{workbook_fingerprint[:12]}",
            workbook_fingerprint=workbook_fingerprint,
            company_name=context.company_name,
            report_years=[report.year for report in context.reports],
            workbook_result=context.generated_workbook,
            financial_year_consolidation_result=(
                context.financial_year_consolidation_result
            ),
            insights_results_by_report_year=context.insights_results,
            workbook_cell_mappings=mappings,
        )
        validation = bundle.validate_contract()

        start_time = time.perf_counter()
        sidecar_path = self._serializer.serialize(bundle)
        serialization_time_seconds = time.perf_counter() - start_time

        report = QueryEnginePhase0Report(
            bundle_path=str(sidecar_path),
            bundle_size_bytes=sidecar_path.stat().st_size,
            mappings_persisted=len(mappings),
            fingerprint_generated=bool(bundle.workbook_fingerprint),
            workbook_fingerprint=bundle.workbook_fingerprint,
            serialization_time_seconds=serialization_time_seconds,
            validation_results=validation.model_dump(mode="json"),
        )
        self._write_report(report)

        context.query_engine_bundle_path = str(sidecar_path)
        context.query_engine_bundle_validation = validation.model_dump(mode="json")
        self._last_bundle = bundle
        self._last_report = report

        self._logger.info(
            "Query Engine input bundle generated",
            extra={
                "bundle_path": str(sidecar_path),
                "mappings_persisted": len(mappings),
                "workbook_fingerprint": bundle.workbook_fingerprint,
            },
        )
        return context

    def _mapping_drafts(self) -> list[WorkbookCellMappingDraft]:
        provider = self._cell_mapping_provider
        if provider is None:
            return []
        drafts = getattr(provider, "last_cell_mapping_drafts", [])
        return list(drafts)

    @staticmethod
    def _fingerprint_payload(
        context: CompanyContext,
        mapping_drafts: list[WorkbookCellMappingDraft],
    ) -> dict[str, Any]:
        if context.generated_workbook is None:
            raise ValueError("generated_workbook is required")
        if context.financial_year_consolidation_result is None:
            raise ValueError("financial_year_consolidation_result is required")

        return {
            "schema_version": QUERY_ENGINE_INPUT_SCHEMA_VERSION,
            "workbook_id": "",
            "workbook_fingerprint": "",
            "company_name": context.company_name,
            "report_years": sorted(report.year for report in context.reports),
            "workbook_result": context.generated_workbook.model_dump(mode="json"),
            "financial_year_consolidation_result": (
                context.financial_year_consolidation_result.model_dump(mode="json")
            ),
            "insights_results_by_report_year": {
                str(year): result.model_dump(mode="json")
                for year, result in sorted(context.insights_results.items())
            },
            "workbook_cell_mappings": [
                {
                    "workbook_fingerprint": "",
                    **draft.model_dump(mode="json"),
                }
                for draft in mapping_drafts
            ],
        }

    def _write_report(self, report: QueryEnginePhase0Report) -> None:
        self._report_path.parent.mkdir(parents=True, exist_ok=True)
        self._report_path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )


__all__ = ["QueryEngineBundleGenerationService", "QueryEnginePhase0Report"]
