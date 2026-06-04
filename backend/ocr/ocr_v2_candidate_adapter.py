"""OCR V2 Bridge Phase B2 candidate adapter.

This module transforms raw extracted table cells into CandidateCaptureInput
rows. It does not invoke CandidateCapture, governance, canonical selection,
ranking, scoring, workbook generation, OCR-to-MSIL export, or LLM behavior.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_bridge_config import (
    OCRV2BridgeConfig,
    default_ocr_v2_bridge_config,
)
from .ocr_v2_candidate_capture import CandidateCaptureInput
from .ocr_v2_context_derivers import (
    UNKNOWN_DERIVED_TAG,
    BasisDeriver,
    EntityScopeDeriver,
    StatementTypeDeriver,
)
from .ocr_v2_table_adapter import (
    DEFAULT_BBOX_TABLES_DIR,
    ExtractedTableCell,
    OCRV2TableAdapter,
)


class OCRV2BridgeCandidateStream(BaseModel):
    """CandidateCaptureInput stream produced by the extraction bridge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tables_processed: int = Field(..., ge=0)
    candidate_inputs: tuple[CandidateCaptureInput, ...] = Field(default_factory=tuple)
    candidate_rows_generated: int = Field(..., ge=0)
    candidate_removals: int = Field(default=0, ge=0)
    governance_invocations: int = Field(default=0, ge=0)
    canonical_selection_attempts: int = Field(default=0, ge=0)
    table_files: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_stream(self) -> "OCRV2BridgeCandidateStream":
        if self.candidate_rows_generated != len(self.candidate_inputs):
            raise ValueError("candidate_rows_generated must equal len(candidate_inputs).")
        if self.candidate_removals != 0:
            raise ValueError("bridge must not remove candidates.")
        if self.governance_invocations != 0:
            raise ValueError("bridge must not invoke governance.")
        if self.canonical_selection_attempts != 0:
            raise ValueError("bridge must not attempt canonical selection.")
        return self


class OCRV2BridgeAudit(BaseModel):
    """Audit payload required by OCR V2 Bridge B0-B2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tables_processed: int = Field(..., ge=0)
    candidate_rows_generated: int = Field(..., ge=0)
    candidate_rows_with_basis: int = Field(..., ge=0)
    candidate_rows_with_statement_type: int = Field(..., ge=0)
    candidate_rows_with_entity_scope: int = Field(..., ge=0)
    candidate_rows_with_scale: int = Field(..., ge=0)
    candidate_rows_missing_required_metadata: int = Field(..., ge=0)
    multi_candidate_metric_year_groups: int = Field(..., ge=0)
    candidate_removals: int = Field(..., ge=0)
    governance_invocations: int = Field(..., ge=0)
    canonical_selection_attempts: int = Field(..., ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2BridgePhaseReport(BaseModel):
    """OCR V2 Bridge B0-B2 phase report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    audit_path: str
    tables_processed: int = Field(..., ge=0)
    candidate_rows_generated: int = Field(..., ge=0)
    candidate_rows_missing_required_metadata: int = Field(..., ge=0)
    multi_candidate_metric_year_groups: int = Field(..., ge=0)
    candidate_capture_ready: bool
    governance_changes_added: bool
    selection_changes_added: bool
    workbook_changes_added: bool
    export_changes_added: bool
    new_ocr_extraction_engine_added: bool
    llm_logic_added: bool
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2CandidateAdapter:
    """Transform extracted cells into CandidateCaptureInput rows."""

    def __init__(self, config: OCRV2BridgeConfig | None = None) -> None:
        self._config = config or default_ocr_v2_bridge_config()
        self._basis_deriver = BasisDeriver()
        self._statement_type_deriver = StatementTypeDeriver()
        self._entity_scope_deriver = EntityScopeDeriver()

    @property
    def config(self) -> OCRV2BridgeConfig:
        return self._config

    def adapt_cells(
        self,
        cells: Iterable[ExtractedTableCell],
    ) -> tuple[CandidateCaptureInput, ...]:
        """Convert every extracted cell to a CandidateCaptureInput row."""

        return tuple(self._input_from_cell(cell) for cell in cells)

    def build_stream(
        self,
        tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
    ) -> OCRV2BridgeCandidateStream:
        """Build the B0-B2 candidate stream from real raw table artifacts."""

        ingestion = OCRV2TableAdapter().ingest_directory(tables_dir)
        candidate_inputs = self.adapt_cells(ingestion.cells)
        return OCRV2BridgeCandidateStream(
            tables_processed=ingestion.tables_processed,
            candidate_inputs=candidate_inputs,
            candidate_rows_generated=len(candidate_inputs),
            candidate_removals=0,
            governance_invocations=0,
            canonical_selection_attempts=0,
            table_files=ingestion.table_files,
        )

    def build_audit(
        self,
        tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
    ) -> OCRV2BridgeAudit:
        """Build the bridge audit over the real raw table artifacts."""

        stream = self.build_stream(tables_dir)
        missing_metadata = sum(
            1 for row in stream.candidate_inputs if _has_missing_required_metadata(row)
        )
        metric_year_counts = Counter(
            (row.raw_label, row.value_year) for row in stream.candidate_inputs
        )
        multi_candidate_groups = sum(
            1 for count in metric_year_counts.values() if count > 1
        )
        violations = _audit_integrity_violations(
            stream,
            missing_metadata=missing_metadata,
            multi_candidate_groups=multi_candidate_groups,
        )
        return OCRV2BridgeAudit(
            tables_processed=stream.tables_processed,
            candidate_rows_generated=stream.candidate_rows_generated,
            candidate_rows_with_basis=sum(
                1 for row in stream.candidate_inputs if _present(row.basis)
            ),
            candidate_rows_with_statement_type=sum(
                1 for row in stream.candidate_inputs if _present(row.statement_type)
            ),
            candidate_rows_with_entity_scope=sum(
                1 for row in stream.candidate_inputs if _present(row.entity_scope)
            ),
            candidate_rows_with_scale=sum(
                1 for row in stream.candidate_inputs if _present(row.source_scale)
            ),
            candidate_rows_missing_required_metadata=missing_metadata,
            multi_candidate_metric_year_groups=multi_candidate_groups,
            candidate_removals=stream.candidate_removals,
            governance_invocations=stream.governance_invocations,
            canonical_selection_attempts=stream.canonical_selection_attempts,
            integrity_violations=violations,
        )

    def write_bridge_audit(
        self,
        output_path: str | Path = "output/ocr_v2_bridge_audit.json",
        *,
        tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
    ) -> OCRV2BridgeAudit:
        """Persist the B0-B2 bridge audit."""

        audit = self.build_audit(tables_dir)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_bridge_phase_report(
        self,
        *,
        audit_path: str | Path = "output/ocr_v2_bridge_audit.json",
        report_path: str | Path = "output/ocr_v2_bridge_phase_report.json",
        tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
    ) -> OCRV2BridgePhaseReport:
        """Write both required OCR V2 Bridge B0-B2 artifacts."""

        audit = self.write_bridge_audit(audit_path, tables_dir=tables_dir)
        report = OCRV2BridgePhaseReport(
            phase="B0-B2",
            scope="extraction_bridge_only",
            audit_path=str(audit_path),
            tables_processed=audit.tables_processed,
            candidate_rows_generated=audit.candidate_rows_generated,
            candidate_rows_missing_required_metadata=(
                audit.candidate_rows_missing_required_metadata
            ),
            multi_candidate_metric_year_groups=audit.multi_candidate_metric_year_groups,
            candidate_capture_ready=not audit.integrity_violations,
            governance_changes_added=False,
            selection_changes_added=False,
            workbook_changes_added=False,
            export_changes_added=False,
            new_ocr_extraction_engine_added=False,
            llm_logic_added=False,
            integrity_audit_passed=not audit.integrity_violations,
            integrity_violations=audit.integrity_violations,
        )
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report

    def _input_from_cell(self, cell: ExtractedTableCell) -> CandidateCaptureInput:
        statement_type = self._statement_type_for_cell(cell)
        basis = self._basis_for_cell(cell)
        entity_scope = self._entity_scope_for_cell(cell)
        return CandidateCaptureInput(
            raw_value=cell.raw_value,
            raw_label=self._config.canonical_metric_for_cell(
                cell.raw_label,
                page_number=cell.page_number,
                value_year=cell.value_year,
            ),
            value_year=cell.value_year,
            page_number=cell.page_number,
            table_reference=cell.table_reference,
            document_fingerprint=self._config.document_fingerprint,
            locator=cell.locator,
            statement_type=statement_type,
            basis=basis,
            entity_scope=entity_scope,
            source_scale=cell.source_scale,
            source_unit=cell.source_unit,
        )

    def _statement_type_for_cell(self, cell: ExtractedTableCell) -> str:
        legacy_statement_type = self._config.statement_type_for_cell(
            cell.page_number,
            section_label=cell.section_label,
            table_reference=cell.table_reference,
        )
        derived = self._statement_type_deriver.derive(cell.document_context)
        if legacy_statement_type == "ANALYSIS_TABLE" and derived.value != "ANALYSIS_TABLE":
            return legacy_statement_type
        if not _is_unknown_tag(derived.value):
            return derived.value
        return legacy_statement_type

    def _basis_for_cell(self, cell: ExtractedTableCell) -> str:
        derived = self._basis_deriver.derive(cell.document_context)
        if not _is_unknown_tag(derived.value):
            return derived.value
        return self._config.basis_for_page(cell.page_number)

    def _entity_scope_for_cell(self, cell: ExtractedTableCell) -> str:
        derived = self._entity_scope_deriver.derive(cell.document_context)
        if not _is_unknown_tag(derived.value):
            return derived.value
        return self._config.entity_scope_for_page(cell.page_number)


def write_ocr_v2_bridge_phase_report(
    *,
    audit_path: str | Path = "output/ocr_v2_bridge_audit.json",
    report_path: str | Path = "output/ocr_v2_bridge_phase_report.json",
    tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
) -> OCRV2BridgePhaseReport:
    """Convenience wrapper for writing B0-B2 bridge artifacts."""

    return OCRV2CandidateAdapter().write_bridge_phase_report(
        audit_path=audit_path,
        report_path=report_path,
        tables_dir=tables_dir,
    )


def _has_missing_required_metadata(row: CandidateCaptureInput) -> bool:
    fields = (
        "raw_value",
        "raw_label",
        "value_year",
        "page_number",
        "table_reference",
        "document_fingerprint",
        "locator",
        "statement_type",
        "basis",
        "entity_scope",
        "source_scale",
        "source_unit",
    )
    payload = row.model_dump(mode="python")
    return any(payload.get(field) in (None, "") for field in fields)


def _present(value: str | None) -> bool:
    return value not in (None, "")


def _is_unknown_tag(value: str | None) -> bool:
    return value in (None, "", UNKNOWN_DERIVED_TAG, "UNKNOWN")


def _audit_integrity_violations(
    stream: OCRV2BridgeCandidateStream,
    *,
    missing_metadata: int,
    multi_candidate_groups: int,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if stream.candidate_rows_generated <= 0:
        violations.append(
            _violation(
                "candidate_rows_required",
                "OCRV2CandidateAdapter",
                "Bridge did not generate any CandidateCaptureInput rows.",
            )
        )
    if missing_metadata:
        violations.append(
            _violation(
                "missing_required_metadata",
                "OCRV2CandidateAdapter",
                "One or more candidate rows are missing bridge-required metadata.",
            )
        )
    if stream.candidate_removals:
        violations.append(
            _violation(
                "candidate_removal",
                "OCRV2CandidateAdapter",
                "Bridge removed candidates.",
            )
        )
    if stream.governance_invocations:
        violations.append(
            _violation(
                "governance_invocation",
                "OCRV2CandidateAdapter",
                "Bridge invoked OCR V2 governance.",
            )
        )
    if stream.canonical_selection_attempts:
        violations.append(
            _violation(
                "selection_attempt",
                "OCRV2CandidateAdapter",
                "Bridge attempted canonical selection.",
            )
        )
    if multi_candidate_groups <= 0:
        violations.append(
            _violation(
                "candidate_multiplicity_required",
                "OCRV2CandidateAdapter",
                "Bridge did not preserve any multiple-candidate metric/year groups.",
            )
        )
    return tuple(violations)


def _violation(check_id: str, subject: str, message: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": "critical",
        "subject": subject,
        "message": message,
    }


__all__ = [
    "OCRV2BridgeAudit",
    "OCRV2BridgeCandidateStream",
    "OCRV2BridgePhaseReport",
    "OCRV2CandidateAdapter",
    "write_ocr_v2_bridge_phase_report",
]
