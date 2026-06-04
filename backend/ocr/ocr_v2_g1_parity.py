"""OCR V2 G1 Lucky parity audit.

This module validates the G1.0-G1.2 bridge rewiring. It compares deriver-first
adapter tags against the deprecated page-range fallback tags, then re-runs the
existing Lucky OCR V2 path against the complete extraction table set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ocr_v2_bridge_config import OCRV2BridgeConfig, default_ocr_v2_bridge_config
from .ocr_v2_candidate_adapter import OCRV2CandidateAdapter
from .ocr_v2_context_derivers import (
    UNKNOWN_DERIVED_TAG,
    BasisDeriver,
    EntityScopeDeriver,
    StatementTypeDeriver,
)
from .ocr_v2_lucky_run import OCRV2LuckyRun
from .ocr_v2_remediation_r1 import (
    DEFAULT_TRUTH_SET_PATH,
    _load_truth_rows,
    _load_workbook_rows,
    _r1_comparison_audit,
)
from .ocr_v2_table_adapter import OCRV2TableAdapter


DEFAULT_G1_TABLES_DIR = Path("output/ocr_v2_final_validation_tables")
DEFAULT_G1_WORKBOOK_PATH = Path("output/ocr_v2_g1_workbook.xlsx")
DEFAULT_G1_AUDIT_PATH = Path("ocr_v2_g1_parity_audit.json")
DEFAULT_G1_REPORT_PATH = Path("ocr_v2_g1_parity_report.md")


def write_ocr_v2_g1_parity_artifacts(
    *,
    tables_dir: str | Path = DEFAULT_G1_TABLES_DIR,
    truth_set_path: str | Path = DEFAULT_TRUTH_SET_PATH,
    workbook_path: str | Path = DEFAULT_G1_WORKBOOK_PATH,
    audit_path: str | Path = DEFAULT_G1_AUDIT_PATH,
    report_path: str | Path = DEFAULT_G1_REPORT_PATH,
) -> dict[str, Any]:
    """Write the G1 Lucky parity audit and Markdown report."""

    config = default_ocr_v2_bridge_config()
    table_adapter = OCRV2TableAdapter()
    candidate_adapter = OCRV2CandidateAdapter(config)
    ingestion = table_adapter.ingest_directory(tables_dir)
    stream = candidate_adapter.build_stream(tables_dir)
    context_coverage = _context_coverage_audit(ingestion.cells)
    tag_parity = _tag_parity_audit(
        cells=ingestion.cells,
        candidate_inputs=stream.candidate_inputs,
        config=config,
    )

    run_result = OCRV2LuckyRun(candidate_adapter=candidate_adapter).run(
        tables_dir=tables_dir,
        workbook_path=workbook_path,
    )
    workbook_rows = _load_workbook_rows(workbook_path)
    truth_rows = _load_truth_rows(truth_set_path)
    validation = _r1_comparison_audit(
        truth_rows=truth_rows,
        workbook_rows=workbook_rows,
        run_audit=run_result.audit.model_dump(mode="json"),
        workbook_path=workbook_path,
    )
    coverage = validation["coverage"]
    success = (
        coverage["covered_cells"] == coverage["exact_matches"]
        + coverage["source_insufficient_correct_abstentions"]
        and coverage["covered_cells"] == validation["truth_set_cells"]
        and coverage["value_mismatches"] == 0
        and coverage["scale_mismatches"] == 0
        and coverage["missing_cells"] == 0
        and tag_parity["total_tag_mismatches"] == 0
    )
    audit = {
        "audit": "ocr_v2_g1_parity_audit",
        "phase": "G1.0-G1.2",
        "scope": "document_context_derivation_with_deprecated_page_range_fallback",
        "tables_dir": str(tables_dir),
        "workbook_path": str(workbook_path),
        "total_candidates": tag_parity["total_candidates"],
        "document_context": context_coverage,
        "basis_matches": tag_parity["basis_matches"],
        "statement_type_matches": tag_parity["statement_type_matches"],
        "entity_scope_matches": tag_parity["entity_scope_matches"],
        "total_tag_mismatches": tag_parity["total_tag_mismatches"],
        "candidate_rows_with_tag_mismatch": tag_parity[
            "candidate_rows_with_tag_mismatch"
        ],
        "derived_non_unknown": tag_parity["derived_non_unknown"],
        "fallback_applied": tag_parity["fallback_applied"],
        "mismatch_examples": tag_parity["mismatch_examples"],
        "lucky_coverage": {
            "total_cells": validation["truth_set_cells"],
            "covered_cells": coverage["covered_cells"],
            "coverage_percent": coverage["coverage_percent"],
            "exact_matches": coverage["exact_matches"],
            "source_insufficient_correct_abstentions": coverage[
                "source_insufficient_correct_abstentions"
            ],
            "value_mismatches": coverage["value_mismatches"],
            "scale_mismatches": coverage["scale_mismatches"],
            "missing_cells": coverage["missing_cells"],
        },
        "integrity_violations": list(run_result.audit.integrity_violations),
        "success_criteria": {
            "lucky_remains_66_of_66": coverage["covered_cells"] == 66,
            "coverage_remains_100_percent": coverage["coverage_percent"] == 100.0,
            "value_mismatches_zero": coverage["value_mismatches"] == 0,
            "scale_mismatches_zero": coverage["scale_mismatches"] == 0,
            "total_tag_mismatches_zero": tag_parity["total_tag_mismatches"] == 0,
        },
        "final_determination": "G1_PARITY_PASSED" if success else "G1_PARITY_FAILED",
    }
    _write_json(audit_path, audit)
    _write_report(report_path, audit)
    return audit


def _tag_parity_audit(
    *,
    cells: tuple[Any, ...],
    candidate_inputs: tuple[Any, ...],
    config: OCRV2BridgeConfig,
) -> dict[str, Any]:
    basis_deriver = BasisDeriver()
    statement_deriver = StatementTypeDeriver()
    entity_deriver = EntityScopeDeriver()
    basis_matches = 0
    statement_matches = 0
    entity_matches = 0
    tag_mismatches = 0
    rows_with_mismatch = 0
    mismatch_examples: list[dict[str, Any]] = []
    derived_non_unknown = {"basis": 0, "statement_type": 0, "entity_scope": 0}
    fallback_applied = {"basis": 0, "statement_type": 0, "entity_scope": 0}

    for cell, row in zip(cells, candidate_inputs, strict=True):
        legacy = {
            "basis": config.basis_for_page(cell.page_number),
            "statement_type": config.statement_type_for_cell(
                cell.page_number,
                section_label=cell.section_label,
                table_reference=cell.table_reference,
            ),
            "entity_scope": config.entity_scope_for_page(cell.page_number),
        }
        emitted = {
            "basis": row.basis,
            "statement_type": row.statement_type,
            "entity_scope": row.entity_scope,
        }
        derived = {
            "basis": basis_deriver.derive(cell.document_context).value,
            "statement_type": statement_deriver.derive(cell.document_context).value,
            "entity_scope": entity_deriver.derive(cell.document_context).value,
        }
        for key, value in derived.items():
            if value == UNKNOWN_DERIVED_TAG:
                fallback_applied[key] += 1
            else:
                derived_non_unknown[key] += 1

        row_mismatches: dict[str, dict[str, str]] = {}
        if emitted["basis"] == legacy["basis"]:
            basis_matches += 1
        else:
            row_mismatches["basis"] = {
                "legacy": legacy["basis"],
                "emitted": emitted["basis"],
            }
        if emitted["statement_type"] == legacy["statement_type"]:
            statement_matches += 1
        else:
            row_mismatches["statement_type"] = {
                "legacy": legacy["statement_type"],
                "emitted": emitted["statement_type"],
            }
        if emitted["entity_scope"] == legacy["entity_scope"]:
            entity_matches += 1
        else:
            row_mismatches["entity_scope"] = {
                "legacy": legacy["entity_scope"],
                "emitted": emitted["entity_scope"],
            }
        if row_mismatches:
            tag_mismatches += len(row_mismatches)
            rows_with_mismatch += 1
            if len(mismatch_examples) < 25:
                mismatch_examples.append(
                    {
                        "raw_label": cell.raw_label,
                        "raw_value": cell.raw_value,
                        "value_year": cell.value_year,
                        "page_number": cell.page_number,
                        "table_reference": cell.table_reference,
                        "section_label": cell.section_label,
                        "document_context": cell.document_context.model_dump(
                            mode="json"
                        ),
                        "mismatches": row_mismatches,
                    }
                )
    return {
        "total_candidates": len(candidate_inputs),
        "basis_matches": basis_matches,
        "statement_type_matches": statement_matches,
        "entity_scope_matches": entity_matches,
        "total_tag_mismatches": tag_mismatches,
        "candidate_rows_with_tag_mismatch": rows_with_mismatch,
        "derived_non_unknown": derived_non_unknown,
        "fallback_applied": fallback_applied,
        "mismatch_examples": mismatch_examples,
    }


def _context_coverage_audit(cells: tuple[Any, ...]) -> dict[str, Any]:
    context_objects = [cell.document_context for cell in cells]
    context_count = sum(1 for context in context_objects if context)
    return {
        "context_objects_present": context_count,
        "statement_title_present": sum(
            1 for context in context_objects if context.statement_title
        ),
        "section_heading_present": sum(
            1 for context in context_objects if context.section_heading
        ),
        "notes_to_marker_true": sum(
            1 for context in context_objects if context.notes_to_marker
        ),
        "named_entities_present": sum(
            1 for context in context_objects if context.named_entities
        ),
        "units_scale_text_present": sum(
            1 for context in context_objects if context.units_scale_text
        ),
        "context_present_for_all_candidates": context_count == len(cells),
    }


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_report(path: str | Path, audit: dict[str, Any]) -> None:
    coverage = audit["lucky_coverage"]
    lines = [
        "# OCR V2 G1 Parity Report",
        "",
        f"Final determination: **{audit['final_determination']}**",
        "",
        "## Tag Parity",
        "",
        f"- Total candidates: {audit['total_candidates']}",
        f"- Basis matches: {audit['basis_matches']}",
        f"- Statement type matches: {audit['statement_type_matches']}",
        f"- Entity scope matches: {audit['entity_scope_matches']}",
        f"- Total tag mismatches: {audit['total_tag_mismatches']}",
        "",
        "## Document Context",
        "",
        f"- Context present for all candidates: {audit['document_context']['context_present_for_all_candidates']}",
        f"- Statement title present: {audit['document_context']['statement_title_present']}",
        f"- Section heading present: {audit['document_context']['section_heading_present']}",
        f"- Units/scale text present: {audit['document_context']['units_scale_text_present']}",
        "",
        "## Lucky Validation",
        "",
        f"- Coverage: {coverage['covered_cells']} / {coverage['total_cells']} ({coverage['coverage_percent']}%)",
        f"- Exact matches: {coverage['exact_matches']}",
        f"- Source-insufficient abstentions: {coverage['source_insufficient_correct_abstentions']}",
        f"- Value mismatches: {coverage['value_mismatches']}",
        f"- Scale mismatches: {coverage['scale_mismatches']}",
        f"- Missing cells: {coverage['missing_cells']}",
        "",
        "## Context-Derived Tags",
        "",
        f"- Derived non-unknown: {json.dumps(audit['derived_non_unknown'], sort_keys=True)}",
        f"- Deprecated fallback applied: {json.dumps(audit['fallback_applied'], sort_keys=True)}",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "DEFAULT_G1_AUDIT_PATH",
    "DEFAULT_G1_REPORT_PATH",
    "DEFAULT_G1_TABLES_DIR",
    "DEFAULT_G1_WORKBOOK_PATH",
    "write_ocr_v2_g1_parity_artifacts",
]
