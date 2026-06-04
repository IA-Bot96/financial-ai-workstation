"""OCR V2 Bridge Phase B3 real Lucky end-to-end run.

This module executes the already-built OCR V2 pipeline over real Lucky raw table
CSV artifacts from the B0-B2 bridge. It does not modify or implement OCR
extraction, governance, selection, workbook generation, MSIL export, ranking,
scoring, or LLM behavior.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_candidate_adapter import OCRV2CandidateAdapter
from .ocr_v2_candidate_capture import CandidateCapture, CandidateCaptureResult
from .ocr_v2_candidate_registry import CandidateRegistry, CandidateRegistryAppendResult
from .ocr_v2_canonical_selection import (
    CanonicalSelection,
    CanonicalSelectionResult,
    CanonicalSelectionStatus,
)
from .ocr_v2_entity_governance import EntityGovernance, EntityGovernanceResult
from .ocr_v2_preselection import (
    CandidatePreselectionResult,
    prepare_candidates_for_canonical_selection,
)
from .ocr_v2_scale_governance import ScaleGovernance, ScaleGovernanceResult
from .ocr_v2_statement_governance import StatementGovernance, StatementGovernanceResult
from .ocr_v2_table_adapter import DEFAULT_BBOX_TABLES_DIR
from .ocr_v2_workbook_generator import OCRV2WorkbookGenerator, OCRV2WorkbookOutput


DEFAULT_LUCKY_WORKBOOK_PATH = Path("output/ocr_v2_lucky_workbook.xlsx")
DEFAULT_LUCKY_CANDIDATES_PATH = Path("output/ocr_v2_lucky_candidates.json")
DEFAULT_LUCKY_REGISTRY_PATH = Path("output/ocr_v2_lucky_registry.json")
DEFAULT_LUCKY_AUDIT_PATH = Path("output/ocr_v2_lucky_run_audit.json")
DEFAULT_LUCKY_B3_REPORT_PATH = Path("output/ocr_v2_b3_report.json")
DEFAULT_LUCKY_ENTITY_REF = "lucky_cement"


class OCRV2LuckyRunAudit(BaseModel):
    """Audit payload required by OCR V2 Bridge Phase B3."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tables_processed: int = Field(..., ge=0)
    candidate_rows_generated: int = Field(..., ge=0)
    registry_candidates: int = Field(..., ge=0)
    metric_year_groups: int = Field(..., ge=0)
    canonical_values_selected: int = Field(..., ge=0)
    ambiguous_groups: int = Field(..., ge=0)
    no_selection_groups: int = Field(..., ge=0)
    source_insufficient_groups: int = Field(..., ge=0)
    multi_candidate_metric_year_groups: int = Field(..., ge=0)
    governance_executed: bool
    selection_executed: bool
    workbook_generated: bool
    provenance_preserved: bool
    real_extraction_run: bool
    oracle_injected_values: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2B3Report(BaseModel):
    """OCR V2 Bridge B3 phase report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    workbook_path: str
    candidates_path: str
    registry_path: str
    audit_path: str
    tables_processed: int = Field(..., ge=0)
    candidate_rows_generated: int = Field(..., ge=0)
    registry_candidates: int = Field(..., ge=0)
    metric_year_groups: int = Field(..., ge=0)
    canonical_values_selected: int = Field(..., ge=0)
    ambiguous_groups: int = Field(..., ge=0)
    no_selection_groups: int = Field(..., ge=0)
    source_insufficient_groups: int = Field(..., ge=0)
    real_extraction_run: bool
    oracle_injected_values: bool
    extraction_engine_changes_added: bool
    governance_changes_added: bool
    selection_changes_added: bool
    workbook_generation_changes_added: bool
    msil_export_changes_added: bool
    ranking_logic_added: bool
    scoring_logic_added: bool
    llm_logic_added: bool
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2TimingBreakdown(BaseModel):
    """Timing breakdown for OCR V2 shadow observability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    extraction_time_seconds: float = Field(..., ge=0)
    capture_time_seconds: float = Field(..., ge=0)
    registry_time_seconds: float = Field(..., ge=0)
    governance_time_seconds: float = Field(..., ge=0)
    statement_governance_time_seconds: float = Field(..., ge=0)
    scale_governance_time_seconds: float = Field(..., ge=0)
    entity_governance_time_seconds: float = Field(..., ge=0)
    selection_time_seconds: float = Field(..., ge=0)
    workbook_time_seconds: float = Field(..., ge=0)
    export_time_seconds: float = Field(..., ge=0)


class OCRV2LuckyRunResult(BaseModel):
    """In-memory result for the real Lucky OCR V2 B3 run."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    bridge_stream: Any
    capture_result: CandidateCaptureResult
    registry_append_result: CandidateRegistryAppendResult
    statement_result: StatementGovernanceResult
    scale_result: ScaleGovernanceResult
    entity_result: EntityGovernanceResult
    preselection_result: CandidatePreselectionResult
    selection_results: tuple[CanonicalSelectionResult, ...]
    workbook_output: OCRV2WorkbookOutput
    audit: OCRV2LuckyRunAudit
    timing_breakdown: OCRV2TimingBreakdown

    @model_validator(mode="after")
    def _validate_run_result(self) -> "OCRV2LuckyRunResult":
        if self.audit.candidate_rows_generated != self.capture_result.candidates_captured:
            raise ValueError("audit candidate count must match capture count.")
        if self.audit.registry_candidates != self.registry_append_result.candidates_registered:
            raise ValueError("audit registry count must match registry append count.")
        return self


class OCRV2LuckyRun:
    """Execute B3 using real Lucky extraction-table artifacts."""

    def __init__(self, *, candidate_adapter: OCRV2CandidateAdapter | None = None) -> None:
        self._candidate_adapter = candidate_adapter or OCRV2CandidateAdapter()

    def run(
        self,
        *,
        tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
        workbook_path: str | Path = DEFAULT_LUCKY_WORKBOOK_PATH,
    ) -> OCRV2LuckyRunResult:
        """Run raw tables through bridge, capture, registry, governance, selection, workbook."""

        phase_start = time.perf_counter()
        bridge_stream = self._candidate_adapter.build_stream(tables_dir)
        extraction_time_seconds = time.perf_counter() - phase_start

        phase_start = time.perf_counter()
        capture_result = CandidateCapture().capture(bridge_stream.candidate_inputs)
        capture_time_seconds = time.perf_counter() - phase_start

        phase_start = time.perf_counter()
        registry = CandidateRegistry()
        registry_append_result = registry.append(capture_result.candidates)
        registry_snapshot = registry.snapshot()
        registry_time_seconds = time.perf_counter() - phase_start

        governance_start = time.perf_counter()
        phase_start = time.perf_counter()
        statement_result = StatementGovernance().govern(registry_snapshot.candidates)
        statement_governance_time_seconds = time.perf_counter() - phase_start

        phase_start = time.perf_counter()
        scale_result = ScaleGovernance().govern(statement_result.governed_candidates)
        scale_governance_time_seconds = time.perf_counter() - phase_start

        phase_start = time.perf_counter()
        entity_result = EntityGovernance().govern(scale_result.governed_candidates)
        entity_governance_time_seconds = time.perf_counter() - phase_start
        governance_time_seconds = time.perf_counter() - governance_start

        phase_start = time.perf_counter()
        preselection_result = prepare_candidates_for_canonical_selection(
            entity_result.entity_governed_candidates
        )
        selection_results = _select_metric_year_groups(
            preselection_result.candidates
        )
        selection_time_seconds = time.perf_counter() - phase_start

        phase_start = time.perf_counter()
        workbook_output = OCRV2WorkbookGenerator().write_xlsx(
            selection_results,
            workbook_path,
            entity_ref=DEFAULT_LUCKY_ENTITY_REF,
        )
        workbook_time_seconds = time.perf_counter() - phase_start
        timing_breakdown = OCRV2TimingBreakdown(
            extraction_time_seconds=extraction_time_seconds,
            capture_time_seconds=capture_time_seconds,
            registry_time_seconds=registry_time_seconds,
            governance_time_seconds=governance_time_seconds,
            statement_governance_time_seconds=statement_governance_time_seconds,
            scale_governance_time_seconds=scale_governance_time_seconds,
            entity_governance_time_seconds=entity_governance_time_seconds,
            selection_time_seconds=selection_time_seconds,
            workbook_time_seconds=workbook_time_seconds,
            export_time_seconds=0.0,
        )
        audit = _build_lucky_run_audit(
            bridge_stream=bridge_stream,
            capture_result=capture_result,
            registry_append_result=registry_append_result,
            statement_result=statement_result,
            scale_result=scale_result,
            entity_result=entity_result,
            selection_results=selection_results,
            workbook_output=workbook_output,
            workbook_path=Path(workbook_path),
        )
        return OCRV2LuckyRunResult(
            bridge_stream=bridge_stream,
            capture_result=capture_result,
            registry_append_result=registry_append_result,
            statement_result=statement_result,
            scale_result=scale_result,
            entity_result=entity_result,
            preselection_result=preselection_result,
            selection_results=selection_results,
            workbook_output=workbook_output,
            audit=audit,
            timing_breakdown=timing_breakdown,
        )

    def write_artifacts(
        self,
        *,
        tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
        workbook_path: str | Path = DEFAULT_LUCKY_WORKBOOK_PATH,
        candidates_path: str | Path = DEFAULT_LUCKY_CANDIDATES_PATH,
        registry_path: str | Path = DEFAULT_LUCKY_REGISTRY_PATH,
        audit_path: str | Path = DEFAULT_LUCKY_AUDIT_PATH,
        report_path: str | Path = DEFAULT_LUCKY_B3_REPORT_PATH,
    ) -> OCRV2B3Report:
        """Run B3 and write all required artifacts."""

        result = self.run(tables_dir=tables_dir, workbook_path=workbook_path)
        _write_json(candidates_path, _candidate_artifact(result))
        _write_json(registry_path, _registry_artifact(result))
        _write_json(audit_path, result.audit.model_dump(mode="json"))

        report = OCRV2B3Report(
            phase="B3",
            scope="real_lucky_end_to_end_run",
            workbook_path=str(workbook_path),
            candidates_path=str(candidates_path),
            registry_path=str(registry_path),
            audit_path=str(audit_path),
            tables_processed=result.audit.tables_processed,
            candidate_rows_generated=result.audit.candidate_rows_generated,
            registry_candidates=result.audit.registry_candidates,
            metric_year_groups=result.audit.metric_year_groups,
            canonical_values_selected=result.audit.canonical_values_selected,
            ambiguous_groups=result.audit.ambiguous_groups,
            no_selection_groups=result.audit.no_selection_groups,
            source_insufficient_groups=result.audit.source_insufficient_groups,
            real_extraction_run=True,
            oracle_injected_values=False,
            extraction_engine_changes_added=False,
            governance_changes_added=False,
            selection_changes_added=False,
            workbook_generation_changes_added=False,
            msil_export_changes_added=False,
            ranking_logic_added=False,
            scoring_logic_added=False,
            llm_logic_added=False,
            integrity_audit_passed=not result.audit.integrity_violations,
            integrity_violations=result.audit.integrity_violations,
        )
        _write_json(report_path, report.model_dump(mode="json"))
        return report


def write_ocr_v2_b3_report(
    *,
    tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
    workbook_path: str | Path = DEFAULT_LUCKY_WORKBOOK_PATH,
    candidates_path: str | Path = DEFAULT_LUCKY_CANDIDATES_PATH,
    registry_path: str | Path = DEFAULT_LUCKY_REGISTRY_PATH,
    audit_path: str | Path = DEFAULT_LUCKY_AUDIT_PATH,
    report_path: str | Path = DEFAULT_LUCKY_B3_REPORT_PATH,
) -> OCRV2B3Report:
    """Convenience wrapper for writing OCR V2 B3 Lucky artifacts."""

    return OCRV2LuckyRun().write_artifacts(
        tables_dir=tables_dir,
        workbook_path=workbook_path,
        candidates_path=candidates_path,
        registry_path=registry_path,
        audit_path=audit_path,
        report_path=report_path,
    )


def _select_metric_year_groups(
    candidates: tuple[Any, ...],
) -> tuple[CanonicalSelectionResult, ...]:
    grouped: dict[tuple[str, int], list[Any]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.candidate.raw_label, candidate.candidate.value_year)].append(
            candidate
        )
    selector = CanonicalSelection()
    return tuple(
        selector.select(grouped[key])
        for key in sorted(grouped, key=lambda item: (item[0], item[1]))
    )


def _build_lucky_run_audit(
    *,
    bridge_stream: Any,
    capture_result: CandidateCaptureResult,
    registry_append_result: CandidateRegistryAppendResult,
    statement_result: StatementGovernanceResult,
    scale_result: ScaleGovernanceResult,
    entity_result: EntityGovernanceResult,
    selection_results: tuple[CanonicalSelectionResult, ...],
    workbook_output: OCRV2WorkbookOutput,
    workbook_path: Path,
) -> OCRV2LuckyRunAudit:
    selected_count = sum(
        1
        for result in selection_results
        if result.decision.status == CanonicalSelectionStatus.SELECTED
    )
    ambiguous_count = sum(
        1
        for result in selection_results
        if result.decision.status == CanonicalSelectionStatus.AMBIGUOUS
    )
    no_selection_count = sum(
        1
        for result in selection_results
        if result.decision.status == CanonicalSelectionStatus.NO_SELECTION
    )
    multi_candidate_groups = sum(
        1 for result in selection_results if result.candidates_evaluated > 1
    )
    provenance_preserved = _workbook_provenance_preserved(
        workbook_output,
        selection_results,
    )
    violations = _audit_integrity_violations(
        bridge_stream=bridge_stream,
        capture_result=capture_result,
        registry_append_result=registry_append_result,
        statement_result=statement_result,
        scale_result=scale_result,
        entity_result=entity_result,
        selection_results=selection_results,
        workbook_output=workbook_output,
        workbook_path=workbook_path,
        provenance_preserved=provenance_preserved,
        selected_count=selected_count,
    )
    return OCRV2LuckyRunAudit(
        tables_processed=bridge_stream.tables_processed,
        candidate_rows_generated=bridge_stream.candidate_rows_generated,
        registry_candidates=registry_append_result.candidates_registered,
        metric_year_groups=len(selection_results),
        canonical_values_selected=selected_count,
        ambiguous_groups=ambiguous_count,
        no_selection_groups=no_selection_count,
        source_insufficient_groups=no_selection_count,
        multi_candidate_metric_year_groups=multi_candidate_groups,
        governance_executed=(
            statement_result.candidates_evaluated > 0
            and scale_result.candidates_evaluated > 0
            and entity_result.candidates_evaluated > 0
        ),
        selection_executed=len(selection_results) > 0,
        workbook_generated=workbook_path.exists(),
        provenance_preserved=provenance_preserved,
        real_extraction_run=True,
        oracle_injected_values=False,
        integrity_violations=violations,
    )


def _workbook_provenance_preserved(
    workbook_output: OCRV2WorkbookOutput,
    selection_results: tuple[CanonicalSelectionResult, ...],
) -> bool:
    selected_by_id = {
        selected.candidate_id: selected
        for result in selection_results
        if (selected := result.selected_candidate) is not None
    }
    if workbook_output.workbook_rows_generated != len(selected_by_id):
        return False
    for row in workbook_output.rows:
        selected = selected_by_id.get(row.selected_candidate_id)
        if selected is None:
            return False
        candidate = selected.candidate
        if (
            row.canonical_value != candidate.raw_value
            or row.page_number != candidate.page_number
            or row.table_reference != candidate.table_reference
            or row.provenance_reference != candidate.provenance.locator
            or row.source_reference != candidate.provenance.table_ref
        ):
            return False
    return True


def _audit_integrity_violations(
    *,
    bridge_stream: Any,
    capture_result: CandidateCaptureResult,
    registry_append_result: CandidateRegistryAppendResult,
    statement_result: StatementGovernanceResult,
    scale_result: ScaleGovernanceResult,
    entity_result: EntityGovernanceResult,
    selection_results: tuple[CanonicalSelectionResult, ...],
    workbook_output: OCRV2WorkbookOutput,
    workbook_path: Path,
    provenance_preserved: bool,
    selected_count: int,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if bridge_stream.candidate_rows_generated <= 0:
        violations.append(_violation("candidate_rows_required", "B3", "No bridge candidate rows generated."))
    if capture_result.candidates_captured <= 0:
        violations.append(_violation("capture_required", "B3", "No candidates captured."))
    if registry_append_result.candidates_registered <= 0:
        violations.append(_violation("registry_required", "B3", "No candidates registered."))
    if selected_count <= 0:
        violations.append(_violation("canonical_selection_required", "B3", "No canonical values selected."))
    if not selection_results:
        violations.append(_violation("selection_groups_required", "B3", "No metric/year groups were selected."))
    if not workbook_path.exists() or workbook_output.workbook_rows_generated <= 0:
        violations.append(_violation("workbook_required", "B3", "Workbook was not generated."))
    if not provenance_preserved:
        violations.append(_violation("provenance_loss", "B3", "Workbook output did not preserve selected candidate provenance."))
    for result in (
        capture_result,
        registry_append_result,
        statement_result,
        scale_result,
        entity_result,
        *selection_results,
    ):
        violations.extend(getattr(result, "integrity_violations", ()))
    return tuple(violations)


def _candidate_artifact(result: OCRV2LuckyRunResult) -> dict[str, Any]:
    return {
        "artifact": "ocr_v2_lucky_candidates",
        "real_extraction_run": True,
        "oracle_injected_values": False,
        "tables_processed": result.bridge_stream.tables_processed,
        "candidate_inputs": [
            row.model_dump(mode="json") for row in result.bridge_stream.candidate_inputs
        ],
        "capture_result": result.capture_result.model_dump(mode="json"),
        "preselection_result": result.preselection_result.model_dump(mode="json"),
        "timing_breakdown": result.timing_breakdown.model_dump(mode="json"),
    }


def _registry_artifact(result: OCRV2LuckyRunResult) -> dict[str, Any]:
    return {
        "artifact": "ocr_v2_lucky_registry",
        "real_extraction_run": True,
        "oracle_injected_values": False,
        "registry_append_result": result.registry_append_result.model_dump(mode="json"),
        "preselection_result": result.preselection_result.model_dump(mode="json"),
        "timing_breakdown": result.timing_breakdown.model_dump(mode="json"),
        "candidates": [
            candidate.model_dump(mode="json")
            for candidate in result.capture_result.candidates
        ],
    }


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _violation(check_id: str, subject: str, message: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": "critical",
        "subject": subject,
        "message": message,
    }


__all__ = [
    "DEFAULT_LUCKY_AUDIT_PATH",
    "DEFAULT_LUCKY_B3_REPORT_PATH",
    "DEFAULT_LUCKY_CANDIDATES_PATH",
    "DEFAULT_LUCKY_ENTITY_REF",
    "DEFAULT_LUCKY_REGISTRY_PATH",
    "DEFAULT_LUCKY_WORKBOOK_PATH",
    "OCRV2B3Report",
    "OCRV2LuckyRun",
    "OCRV2LuckyRunAudit",
    "OCRV2LuckyRunResult",
    "OCRV2TimingBreakdown",
    "write_ocr_v2_b3_report",
]
