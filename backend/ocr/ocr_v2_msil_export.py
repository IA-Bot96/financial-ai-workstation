"""OCR V2 Phase P7 OCR-to-MSIL export.

This module adapts OCR V2 canonical workbook output into the existing MSIL
IntelligenceSignal input contract. It does not perform OCR extraction,
governance, canonical selection, workbook generation changes, ranking,
candidate scoring, authority assignment, MSIL schema changes, or LLM behavior.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from multi_source_intelligence.models import (
    AuthorityClass,
    ClaimType,
    ContentClass,
    EntityResolutionResult,
    EntityScope,
    Horizon,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    PDFPageProvenance,
    ResolutionMethod,
    ReviewStatus,
    SourceType,
    TimeBasis,
)

from .ocr_v2_workbook_generator import (
    OCRV2WorkbookGenerator,
    OCRV2WorkbookOutput,
    OCRV2WorkbookRow,
    _execute_regression_selections,
)
from .ocr_v2_statement_governance import load_ocr_v2_regression_cases


DEFAULT_REGRESSION_WORKBOOK_FINGERPRINT = "ocr_v2_regression_workbook_fingerprint"
DEFAULT_REGRESSION_REPORT_REFERENCE = "annual_report:lucky_cement:2025"
DEFAULT_REGRESSION_SOURCE_REPORT_YEAR = 2025


class OCRV2MSILExportBundle(BaseModel):
    """MSIL-compatible OCR V2 export bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_ref: str = Field(..., min_length=1)
    report_reference: str = Field(..., min_length=1)
    workbook_fingerprint: str = Field(..., min_length=1)
    rows_exported: int = Field(..., ge=0)
    signals: tuple[IntelligenceSignal, ...] = Field(default_factory=tuple)
    contract_preserved: bool

    @model_validator(mode="after")
    def _validate_bundle(self) -> "OCRV2MSILExportBundle":
        if self.rows_exported != len(self.signals):
            raise ValueError("rows_exported must equal len(signals).")
        if not self.contract_preserved:
            raise ValueError("MSIL export contract must be preserved.")
        return self


class OCRV2MSILExportAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P7 export."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows_exported: int = Field(..., ge=0)
    provenance_preserved_count: int = Field(..., ge=0)
    value_mutations: int = Field(..., ge=0)
    scale_mutations: int = Field(..., ge=0)
    regression_cases_verified: int = Field(..., ge=0)
    msil_contract_compatible: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase7Report(BaseModel):
    """OCR V2 Phase P7 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    audit_path: str
    rows_exported: int = Field(..., ge=0)
    contract_preserved: bool
    value_mutations: int = Field(..., ge=0)
    scale_mutations: int = Field(..., ge=0)
    regression_cases_verified: int = Field(..., ge=0)
    msil_contract_compatible: bool
    ocr_extraction_changes_added: bool
    governance_changes_added: bool
    selection_changes_added: bool
    workbook_changes_added: bool
    ranking_logic_added: bool
    scoring_logic_added: bool
    authority_assignment_added: bool
    llm_logic_added: bool
    msil_schema_changes_added: bool
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2MSILExporter:
    """Adapt canonical OCR V2 workbook rows into MSIL IntelligenceSignals."""

    def __init__(
        self,
        *,
        entity_resolution: EntityResolutionResult,
        workbook_fingerprint: str,
        report_reference: str,
        entity_scope: EntityScope = EntityScope.COMPANY,
        source_report_year: int | None = None,
        source_independent_of_issuer: bool = False,
        verified: bool = True,
        trust_prior: float = 0.95,
    ) -> None:
        if entity_resolution.review_status != ReviewStatus.RESOLVED:
            raise ValueError("OCRV2MSILExporter requires a resolved entity_resolution.")
        if not entity_resolution.resolved_entity_ref:
            raise ValueError("entity_resolution must include resolved_entity_ref.")
        if not workbook_fingerprint.strip():
            raise ValueError("workbook_fingerprint is required.")
        if not report_reference.strip():
            raise ValueError("report_reference is required.")

        self._entity_resolution = entity_resolution
        self._entity_ref = entity_resolution.resolved_entity_ref
        self._entity_scope = entity_scope
        self._workbook_fingerprint = workbook_fingerprint
        self._report_reference = report_reference
        self._source_report_year = source_report_year
        self._source_independent_of_issuer = source_independent_of_issuer
        self._verified = verified
        self._trust_prior = trust_prior

    def export(self, workbook_output: OCRV2WorkbookOutput) -> OCRV2MSILExportBundle:
        """Export workbook-compatible canonical rows into MSIL signals."""

        signals = tuple(self._signal_from_row(row) for row in workbook_output.rows)
        return OCRV2MSILExportBundle(
            entity_ref=self._entity_ref,
            report_reference=self._report_reference,
            workbook_fingerprint=self._workbook_fingerprint,
            rows_exported=len(signals),
            signals=signals,
            contract_preserved=True,
        )

    def build_audit(
        self,
        workbook_output: OCRV2WorkbookOutput,
        *,
        fixture: dict[str, Any] | None = None,
    ) -> OCRV2MSILExportAudit:
        """Build the required OCR-to-MSIL export audit."""

        bundle = self.export(workbook_output)
        row_by_candidate_id = {row.selected_candidate_id: row for row in workbook_output.rows}
        value_mutations = _value_mutation_count(bundle, row_by_candidate_id)
        scale_mutations = _scale_mutation_count(bundle, row_by_candidate_id)
        provenance_preserved_count = _provenance_preserved_count(bundle, row_by_candidate_id)
        regression_cases_verified = (
            _regression_cases_verified(bundle, fixture) if fixture else 0
        )
        msil_contract_compatible = _msil_contract_compatible(bundle)
        violations = _audit_integrity_violations(
            bundle=bundle,
            workbook_output=workbook_output,
            provenance_preserved_count=provenance_preserved_count,
            value_mutations=value_mutations,
            scale_mutations=scale_mutations,
            regression_cases_verified=regression_cases_verified,
            expected_regression_cases=len(fixture["cases"]) if fixture else 0,
            msil_contract_compatible=msil_contract_compatible,
        )
        return OCRV2MSILExportAudit(
            rows_exported=bundle.rows_exported,
            provenance_preserved_count=provenance_preserved_count,
            value_mutations=value_mutations,
            scale_mutations=scale_mutations,
            regression_cases_verified=regression_cases_verified,
            msil_contract_compatible=msil_contract_compatible,
            integrity_violations=violations,
        )

    def write_msil_export_audit(
        self,
        workbook_output: OCRV2WorkbookOutput,
        output_path: str | Path = "output/ocr_v2_msil_export_audit.json",
        *,
        fixture: dict[str, Any] | None = None,
    ) -> OCRV2MSILExportAudit:
        """Persist the P7 OCR-to-MSIL export audit."""

        audit = self.build_audit(workbook_output, fixture=fixture)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def _signal_from_row(self, row: OCRV2WorkbookRow) -> IntelligenceSignal:
        if row.entity_ref != self._entity_ref:
            raise ValueError(
                "Workbook row entity_ref must match supplied resolved entity. "
                "OCR V2 export does not perform entity resolution."
            )
        identity_key = _identity_key(
            report_reference=self._report_reference,
            row=row,
        )
        content = IntelligenceSignalContent(
            content_class=ContentClass.NUMERIC_CLAIM,
            identity_key=identity_key,
            metric_ref=row.metric_id,
            value=row.canonical_value,
            unit=row.source_unit,
            payload=_row_payload(row),
        )
        return IntelligenceSignal(
            entity_ref=self._entity_ref,
            entity_scope=self._entity_scope,
            entity_resolution=self._entity_resolution,
            content=content,
            classification=IntelligenceSignalClassification(
                content_class=ContentClass.NUMERIC_CLAIM,
                source_type=SourceType.ANNUAL_REPORT,
                claim_type=ClaimType.AUDITED_FACT,
                authority_class=AuthorityClass.AUDITED_ISSUER,
                creation_eligible=True,
                mapping_confidence=1.0,
                authority_confidence=1.0,
                independence_metadata={
                    "source_independent_of_issuer": self._source_independent_of_issuer,
                    "authority_basis": "annual_report_canonical_workbook_output",
                    "authority_assignment_service_invoked": False,
                },
            ),
            metadata=IntelligenceSignalMetadata(
                observation_time=datetime(
                    self._source_report_year or row.value_year,
                    1,
                    1,
                    tzinfo=timezone.utc,
                ),
                subject_period=f"FY{row.value_year}",
                time_basis=TimeBasis.FISCAL,
                horizon=Horizon.HISTORICAL,
                source_independent_of_issuer=self._source_independent_of_issuer,
                verified=self._verified,
                trust_prior=self._trust_prior,
                source_record_id=identity_key,
                source_lineage_hooks=(row.source_reference, row.provenance_reference),
            ),
            provenance=PDFPageProvenance(
                workbook_fingerprint=self._workbook_fingerprint,
                page_number=row.page_number,
                report_reference=self._report_reference,
                source_report_year=self._source_report_year,
                source_section=row.statement_type,
                cell_reference=row.provenance_reference,
                verified=self._verified,
                source_lineage=(row.source_reference,),
            ),
        )


def write_phase7_report(
    *,
    audit_path: str | Path = "output/ocr_v2_msil_export_audit.json",
    report_path: str | Path = "output/ocr_v2_phase7_report.json",
) -> OCRV2Phase7Report:
    """Write all required OCR V2 Phase P7 artifacts."""

    fixture = load_ocr_v2_regression_cases()
    selection_results = _execute_regression_selections(fixture)
    workbook_output = OCRV2WorkbookGenerator().generate(
        selection_results,
        entity_ref=fixture["entity_ref"],
    )
    exporter = _regression_exporter(fixture["entity_ref"])
    audit = exporter.write_msil_export_audit(
        workbook_output,
        audit_path,
        fixture=fixture,
    )
    report = OCRV2Phase7Report(
        phase="P7",
        scope="ocr_to_msil_export_only",
        audit_path=str(audit_path),
        rows_exported=audit.rows_exported,
        contract_preserved=not audit.integrity_violations,
        value_mutations=audit.value_mutations,
        scale_mutations=audit.scale_mutations,
        regression_cases_verified=audit.regression_cases_verified,
        msil_contract_compatible=audit.msil_contract_compatible,
        ocr_extraction_changes_added=False,
        governance_changes_added=False,
        selection_changes_added=False,
        workbook_changes_added=False,
        ranking_logic_added=False,
        scoring_logic_added=False,
        authority_assignment_added=False,
        llm_logic_added=False,
        msil_schema_changes_added=False,
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


def _regression_exporter(entity_ref: str) -> OCRV2MSILExporter:
    return OCRV2MSILExporter(
        entity_resolution=_resolved_entity(entity_ref),
        workbook_fingerprint=DEFAULT_REGRESSION_WORKBOOK_FINGERPRINT,
        report_reference=DEFAULT_REGRESSION_REPORT_REFERENCE,
        source_report_year=DEFAULT_REGRESSION_SOURCE_REPORT_YEAR,
    )


def _resolved_entity(entity_ref: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        raw_identifier=entity_ref,
        normalized_identifier=entity_ref,
        method=ResolutionMethod.EXACT,
        confidence=1.0,
        review_status=ReviewStatus.RESOLVED,
        resolved_entity_ref=entity_ref,
        resolved_entity_type="company",
        candidates=(),
        review_required=False,
        evidence={"resolution_reason": "supplied_to_ocr_v2_msil_export"},
    )


def _identity_key(*, report_reference: str, row: OCRV2WorkbookRow) -> str:
    return (
        f"ocr_v2:{report_reference}:metric:{row.metric_id}:"
        f"value_year:{row.value_year}:table:{row.table_reference}:"
        f"candidate:{row.selected_candidate_id}"
    )


def _row_payload(row: OCRV2WorkbookRow) -> dict[str, Any]:
    return {
        "ocr_v2_export": True,
        "metric_id": row.metric_id,
        "value_year": row.value_year,
        "entity_ref": row.entity_ref,
        "basis": row.basis,
        "statement_type": row.statement_type,
        "entity_scope": row.entity_scope,
        "source_scale": row.source_scale,
        "source_unit": row.source_unit,
        "page_number": row.page_number,
        "table_reference": row.table_reference,
        "source_reference": row.source_reference,
        "provenance_reference": row.provenance_reference,
        "selected_candidate_id": row.selected_candidate_id,
    }


def _value_mutation_count(
    bundle: OCRV2MSILExportBundle,
    row_by_candidate_id: dict[str, OCRV2WorkbookRow],
) -> int:
    mutations = 0
    for signal in bundle.signals:
        candidate_id = signal.content.payload["selected_candidate_id"]
        row = row_by_candidate_id[candidate_id]
        if signal.content.value != row.canonical_value:
            mutations += 1
    return mutations


def _scale_mutation_count(
    bundle: OCRV2MSILExportBundle,
    row_by_candidate_id: dict[str, OCRV2WorkbookRow],
) -> int:
    mutations = 0
    for signal in bundle.signals:
        candidate_id = signal.content.payload["selected_candidate_id"]
        row = row_by_candidate_id[candidate_id]
        if signal.content.payload["source_scale"] != row.source_scale:
            mutations += 1
    return mutations


def _provenance_preserved_count(
    bundle: OCRV2MSILExportBundle,
    row_by_candidate_id: dict[str, OCRV2WorkbookRow],
) -> int:
    preserved = 0
    for signal in bundle.signals:
        payload = signal.content.payload
        row = row_by_candidate_id[payload["selected_candidate_id"]]
        provenance = signal.provenance
        if (
            signal.content.metric_ref == row.metric_id
            and signal.content.value == row.canonical_value
            and payload["source_reference"] == row.source_reference
            and payload["provenance_reference"] == row.provenance_reference
            and provenance.page_number == row.page_number
            and provenance.cell_reference == row.provenance_reference
            and provenance.source_lineage == (row.source_reference,)
            and provenance.report_reference == bundle.report_reference
            and provenance.workbook_fingerprint == bundle.workbook_fingerprint
        ):
            preserved += 1
    return preserved


def _regression_cases_verified(
    bundle: OCRV2MSILExportBundle,
    fixture: dict[str, Any] | None,
) -> int:
    if not fixture:
        return 0
    signals_by_table_ref = {
        signal.content.payload["table_reference"]: signal for signal in bundle.signals
    }
    verified = 0
    for case in fixture["cases"]:
        correct_ref = f"{case['case_id']}_correct"
        incorrect_ref = f"{case['case_id']}_incorrect"
        signal = signals_by_table_ref.get(correct_ref)
        if signal is None:
            continue
        if incorrect_ref in signals_by_table_ref:
            continue
        if (
            signal.content.value == case["correct_candidate"]["value"]
            and signal.provenance.cell_reference
            == case["correct_candidate"]["provenance_reference"]
            and signal.content.payload["provenance_reference"]
            == case["correct_candidate"]["provenance_reference"]
        ):
            verified += 1
    return verified


def _msil_contract_compatible(bundle: OCRV2MSILExportBundle) -> bool:
    try:
        restored_bundle = OCRV2MSILExportBundle.model_validate_json(
            bundle.model_dump_json()
        )
        for signal in restored_bundle.signals:
            IntelligenceSignal.model_validate_json(signal.model_dump_json())
            if signal.content.content_class != ContentClass.NUMERIC_CLAIM:
                return False
            if signal.classification.source_type != SourceType.ANNUAL_REPORT:
                return False
            if signal.provenance.source_type != SourceType.ANNUAL_REPORT:
                return False
    except Exception:  # noqa: BLE001 - compatibility is summarized in the audit.
        return False
    return True


def _audit_integrity_violations(
    *,
    bundle: OCRV2MSILExportBundle,
    workbook_output: OCRV2WorkbookOutput,
    provenance_preserved_count: int,
    value_mutations: int,
    scale_mutations: int,
    regression_cases_verified: int,
    expected_regression_cases: int,
    msil_contract_compatible: bool,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if bundle.rows_exported != workbook_output.workbook_rows_generated:
        violations.append(
            _violation(
                "row_count_mismatch",
                "OCRV2MSILExporter",
                "MSIL export count does not match workbook row count.",
            )
        )
    if provenance_preserved_count != bundle.rows_exported:
        violations.append(
            _violation(
                "provenance_loss",
                "OCRV2MSILExporter",
                "One or more exported signals lost canonical provenance.",
            )
        )
    if value_mutations:
        violations.append(
            _violation(
                "value_mutations",
                "OCRV2MSILExporter",
                "One or more canonical values were mutated during export.",
            )
        )
    if scale_mutations:
        violations.append(
            _violation(
                "scale_mutations",
                "OCRV2MSILExporter",
                "One or more scale metadata values were mutated during export.",
            )
        )
    if expected_regression_cases and regression_cases_verified != expected_regression_cases:
        violations.append(
            _violation(
                "regression_cases_not_verified",
                "OCRV2MSILExporter",
                "Regression oracle rows did not all preserve selected correct values.",
            )
        )
    if not msil_contract_compatible:
        violations.append(
            _violation(
                "msil_contract_incompatible",
                "OCRV2MSILExporter",
                "Exported bundle failed existing MSIL signal contract validation.",
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
    "DEFAULT_REGRESSION_REPORT_REFERENCE",
    "DEFAULT_REGRESSION_SOURCE_REPORT_YEAR",
    "DEFAULT_REGRESSION_WORKBOOK_FINGERPRINT",
    "OCRV2MSILExportAudit",
    "OCRV2MSILExportBundle",
    "OCRV2MSILExporter",
    "OCRV2Phase7Report",
    "write_phase7_report",
]
