"""OCR V2 Phase P6 workbook generation.

This module projects canonical-selection output into workbook-compatible rows
and an optional XLSX file. It does not perform OCR extraction, governance,
selection, ranking, candidate scoring, authority assignment, OCR-to-MSIL export,
or LLM behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_canonical_selection import (
    CanonicalSelection,
    CanonicalSelectionResult,
    CanonicalSelectionStatus,
)
from .ocr_v2_entity_governance import EntityGovernance
from .ocr_v2_scale_governance import ScaleGovernance
from .ocr_v2_statement_governance import (
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
)


WORKBOOK_SHEET_NAME = "OCR V2 Canonical Metrics"
WORKBOOK_HEADERS: tuple[str, ...] = (
    "metric_id",
    "value_year",
    "canonical_value",
    "entity_ref",
    "basis",
    "statement_type",
    "entity_scope",
    "source_scale",
    "source_unit",
    "page_number",
    "table_reference",
    "source_reference",
    "provenance_reference",
    "selected_candidate_id",
)


class OCRV2WorkbookRow(BaseModel):
    """One workbook-compatible canonical metric row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    canonical_value: float | int | str
    entity_ref: str = Field(..., min_length=1)
    basis: str = Field(..., min_length=1)
    statement_type: str = Field(..., min_length=1)
    entity_scope: str = Field(..., min_length=1)
    source_scale: str = Field(..., min_length=1)
    source_unit: str = Field(..., min_length=1)
    page_number: int = Field(..., gt=0)
    table_reference: str = Field(..., min_length=1)
    source_reference: str = Field(..., min_length=1)
    provenance_reference: str = Field(..., min_length=1)
    selected_candidate_id: str = Field(..., min_length=1)


class OCRV2WorkbookOutput(BaseModel):
    """Workbook-compatible output generated from canonical selections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sheet_name: str = Field(default=WORKBOOK_SHEET_NAME, min_length=1, max_length=31)
    rows: tuple[OCRV2WorkbookRow, ...] = Field(default_factory=tuple)
    workbook_rows_generated: int = Field(..., ge=0)
    contract_preserved: bool
    workbook_output_path: str | None = None

    @model_validator(mode="after")
    def _validate_workbook_output(self) -> "OCRV2WorkbookOutput":
        if self.workbook_rows_generated != len(self.rows):
            raise ValueError("workbook_rows_generated must equal len(rows).")
        if not self.contract_preserved:
            raise ValueError("OCR V2 workbook contract must be preserved.")
        return self


class OCRV2WorkbookGenerationAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P6 workbook generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workbook_rows_generated: int = Field(..., ge=0)
    provenance_preserved_count: int = Field(..., ge=0)
    value_mutations: int = Field(..., ge=0)
    scale_mutations: int = Field(..., ge=0)
    regression_cases_verified: int = Field(..., ge=0)
    contract_preserved: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase6Report(BaseModel):
    """OCR V2 Phase P6 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    audit_path: str
    workbook_output_path: str
    workbook_rows_generated: int = Field(..., ge=0)
    contract_preserved: bool
    value_mutations: int = Field(..., ge=0)
    scale_mutations: int = Field(..., ge=0)
    regression_cases_verified: int = Field(..., ge=0)
    ocr_to_msil_export_added: bool
    new_governance_rules_added: bool
    new_selection_rules_added: bool
    ranking_logic_added: bool
    candidate_scoring_added: bool
    llm_logic_added: bool
    ocr_extraction_changes_added: bool
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2WorkbookGenerator:
    """Project canonical selections into workbook-compatible output."""

    def generate(
        self,
        selection_results: Iterable[CanonicalSelectionResult],
        *,
        entity_ref: str,
        workbook_output_path: str | Path | None = None,
    ) -> OCRV2WorkbookOutput:
        """Generate workbook-compatible rows from selected canonical values only."""

        rows = tuple(
            _row_from_selection_result(result, entity_ref)
            for result in selection_results
            if result.decision.status == CanonicalSelectionStatus.SELECTED
            and result.selected_candidate is not None
        )
        return OCRV2WorkbookOutput(
            rows=rows,
            workbook_rows_generated=len(rows),
            contract_preserved=True,
            workbook_output_path=str(workbook_output_path) if workbook_output_path else None,
        )

    def write_xlsx(
        self,
        selection_results: Iterable[CanonicalSelectionResult],
        output_path: str | Path,
        *,
        entity_ref: str,
    ) -> OCRV2WorkbookOutput:
        """Write selected canonical rows into a deterministic workbook sheet."""

        output = self.generate(
            selection_results,
            entity_ref=entity_ref,
            workbook_output_path=output_path,
        )
        _write_xlsx(output, output_path)
        return output

    def build_audit(
        self,
        selection_results: Iterable[CanonicalSelectionResult] | None = None,
        *,
        entity_ref: str | None = None,
    ) -> OCRV2WorkbookGenerationAudit:
        """Build the required workbook-generation audit."""

        fixture: dict[str, Any] | None = None
        if selection_results is None:
            fixture = load_ocr_v2_regression_cases()
            selection_results = _execute_regression_selections(fixture)
            entity_ref = fixture["entity_ref"]
        results = tuple(selection_results)
        output = self.generate(results, entity_ref=entity_ref or "unknown_entity")
        value_mutations = _value_mutation_count(output, results)
        scale_mutations = _scale_mutation_count(output, results)
        provenance_preserved_count = _provenance_preserved_count(output, results)
        regression_cases_verified = (
            _regression_cases_verified(output, fixture) if fixture else 0
        )
        violations = _audit_integrity_violations(
            output=output,
            results=results,
            provenance_preserved_count=provenance_preserved_count,
            value_mutations=value_mutations,
            scale_mutations=scale_mutations,
            regression_cases_verified=regression_cases_verified,
            expected_regression_cases=len(fixture["cases"]) if fixture else 0,
        )
        return OCRV2WorkbookGenerationAudit(
            workbook_rows_generated=output.workbook_rows_generated,
            provenance_preserved_count=provenance_preserved_count,
            value_mutations=value_mutations,
            scale_mutations=scale_mutations,
            regression_cases_verified=regression_cases_verified,
            contract_preserved=not violations,
            integrity_violations=violations,
        )

    def write_workbook_generation_audit(
        self,
        output_path: str | Path = "output/ocr_v2_workbook_generation_audit.json",
    ) -> OCRV2WorkbookGenerationAudit:
        """Persist the P6 workbook-generation audit."""

        audit = self.build_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase6_report(
        self,
        *,
        audit_path: str | Path = "output/ocr_v2_workbook_generation_audit.json",
        workbook_output_path: str | Path = "output/ocr_v2_workbook_generation.xlsx",
        report_path: str | Path = "output/ocr_v2_phase6_report.json",
    ) -> OCRV2Phase6Report:
        """Write all required OCR V2 Phase P6 artifacts."""

        fixture = load_ocr_v2_regression_cases()
        selection_results = _execute_regression_selections(fixture)
        self.write_xlsx(
            selection_results,
            workbook_output_path,
            entity_ref=fixture["entity_ref"],
        )
        audit = self.build_audit()
        audit_path = Path(audit_path)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        report = OCRV2Phase6Report(
            phase="P6",
            scope="workbook_generation_only",
            audit_path=str(audit_path),
            workbook_output_path=str(workbook_output_path),
            workbook_rows_generated=audit.workbook_rows_generated,
            contract_preserved=audit.contract_preserved,
            value_mutations=audit.value_mutations,
            scale_mutations=audit.scale_mutations,
            regression_cases_verified=audit.regression_cases_verified,
            ocr_to_msil_export_added=False,
            new_governance_rules_added=False,
            new_selection_rules_added=False,
            ranking_logic_added=False,
            candidate_scoring_added=False,
            llm_logic_added=False,
            ocr_extraction_changes_added=False,
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


def write_phase6_report(
    *,
    audit_path: str | Path = "output/ocr_v2_workbook_generation_audit.json",
    workbook_output_path: str | Path = "output/ocr_v2_workbook_generation.xlsx",
    report_path: str | Path = "output/ocr_v2_phase6_report.json",
) -> OCRV2Phase6Report:
    """Convenience wrapper for writing the P6 report."""

    return OCRV2WorkbookGenerator().write_phase6_report(
        audit_path=audit_path,
        workbook_output_path=workbook_output_path,
        report_path=report_path,
    )


def _row_from_selection_result(
    result: CanonicalSelectionResult,
    entity_ref: str,
) -> OCRV2WorkbookRow:
    selected = result.selected_candidate
    if selected is None:
        raise ValueError("Cannot build workbook row without selected candidate.")
    candidate = selected.candidate
    provenance = candidate.provenance
    return OCRV2WorkbookRow(
        metric_id=candidate.raw_label,
        value_year=candidate.value_year,
        canonical_value=candidate.raw_value,
        entity_ref=entity_ref,
        basis=candidate.basis,
        statement_type=candidate.statement_type,
        entity_scope=candidate.entity_scope,
        source_scale=candidate.source_scale,
        source_unit=candidate.source_unit,
        page_number=candidate.page_number,
        table_reference=candidate.table_reference,
        source_reference=provenance.table_ref,
        provenance_reference=provenance.locator,
        selected_candidate_id=candidate.candidate_id,
    )


def _write_xlsx(output: OCRV2WorkbookOutput, output_path: str | Path) -> None:
    from openpyxl import Workbook

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = output.sheet_name
    worksheet.append(WORKBOOK_HEADERS)
    for row in output.rows:
        row_payload = row.model_dump(mode="python")
        worksheet.append([row_payload[header] for header in WORKBOOK_HEADERS])
    workbook.save(path)


def _execute_regression_selections(
    fixture: dict[str, Any],
) -> tuple[CanonicalSelectionResult, ...]:
    selector = CanonicalSelection()
    results: list[CanonicalSelectionResult] = []
    for case in fixture["cases"]:
        case_fixture = {**fixture, "cases": [case]}
        raw_candidates = candidates_from_regression_cases(case_fixture)
        statement_governed = StatementGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(raw_candidates).governed_candidates
        scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
        entity_governed = EntityGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(scale_governed).entity_governed_candidates
        results.append(selector.select(entity_governed))
    return tuple(results)


def _selected_by_id(
    results: tuple[CanonicalSelectionResult, ...],
) -> dict[str, Any]:
    return {
        selected.candidate_id: selected
        for result in results
        if (selected := result.selected_candidate) is not None
    }


def _value_mutation_count(
    output: OCRV2WorkbookOutput,
    results: tuple[CanonicalSelectionResult, ...],
) -> int:
    selected_by_id = _selected_by_id(results)
    return sum(
        1
        for row in output.rows
        if row.canonical_value != selected_by_id[row.selected_candidate_id].original_value
    )


def _scale_mutation_count(
    output: OCRV2WorkbookOutput,
    results: tuple[CanonicalSelectionResult, ...],
) -> int:
    selected_by_id = _selected_by_id(results)
    return sum(
        1
        for row in output.rows
        if row.source_scale != selected_by_id[row.selected_candidate_id].candidate.source_scale
    )


def _provenance_preserved_count(
    output: OCRV2WorkbookOutput,
    results: tuple[CanonicalSelectionResult, ...],
) -> int:
    selected_by_id = _selected_by_id(results)
    preserved = 0
    for row in output.rows:
        selected = selected_by_id[row.selected_candidate_id]
        candidate = selected.candidate
        provenance = candidate.provenance
        if (
            row.page_number == candidate.page_number
            and row.provenance_reference == provenance.locator
            and row.source_reference == provenance.table_ref
            and row.statement_type == candidate.statement_type
            and row.basis == candidate.basis
            and row.entity_scope == candidate.entity_scope
        ):
            preserved += 1
    return preserved


def _regression_cases_verified(
    output: OCRV2WorkbookOutput,
    fixture: dict[str, Any] | None,
) -> int:
    if not fixture:
        return 0
    rows_by_table_ref = {row.table_reference: row for row in output.rows}
    verified = 0
    for case in fixture["cases"]:
        correct_ref = f"{case['case_id']}_correct"
        incorrect_ref = f"{case['case_id']}_incorrect"
        row = rows_by_table_ref.get(correct_ref)
        if row is None:
            continue
        if incorrect_ref in rows_by_table_ref:
            continue
        if (
            row.canonical_value == case["correct_candidate"]["value"]
            and row.provenance_reference
            == case["correct_candidate"]["provenance_reference"]
        ):
            verified += 1
    return verified


def _audit_integrity_violations(
    *,
    output: OCRV2WorkbookOutput,
    results: tuple[CanonicalSelectionResult, ...],
    provenance_preserved_count: int,
    value_mutations: int,
    scale_mutations: int,
    regression_cases_verified: int,
    expected_regression_cases: int,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if output.workbook_rows_generated != sum(
        1
        for result in results
        if result.decision.status == CanonicalSelectionStatus.SELECTED
    ):
        violations.append(
            _violation(
                "row_count_mismatch",
                "OCRV2WorkbookGenerator",
                "Workbook row count does not match selected canonical count.",
            )
        )
    if provenance_preserved_count != output.workbook_rows_generated:
        violations.append(
            _violation(
                "provenance_loss",
                "OCRV2WorkbookGenerator",
                "One or more workbook rows lost canonical provenance.",
            )
        )
    if value_mutations:
        violations.append(
            _violation(
                "value_mutations",
                "OCRV2WorkbookGenerator",
                "One or more canonical values were mutated during projection.",
            )
        )
    if scale_mutations:
        violations.append(
            _violation(
                "scale_mutations",
                "OCRV2WorkbookGenerator",
                "One or more scale metadata values were mutated during projection.",
            )
        )
    if expected_regression_cases and regression_cases_verified != expected_regression_cases:
        violations.append(
            _violation(
                "regression_cases_not_verified",
                "OCRV2WorkbookGenerator",
                "Regression oracle rows did not all preserve selected correct values.",
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
    "OCRV2Phase6Report",
    "OCRV2WorkbookGenerationAudit",
    "OCRV2WorkbookGenerator",
    "OCRV2WorkbookOutput",
    "OCRV2WorkbookRow",
    "WORKBOOK_HEADERS",
    "WORKBOOK_SHEET_NAME",
    "write_phase6_report",
]
