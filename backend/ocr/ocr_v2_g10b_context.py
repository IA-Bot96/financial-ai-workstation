"""OCR V2 G1.0b context enrichment audit.

This module measures page-level context enrichment only. It does not modify or
implement governance, selection, workbook generation, source precedence, alias
handling, MSIL export, OCR extraction, ranking, scoring, or LLM behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ocr_v2_lucky_run import OCRV2LuckyRun
from .ocr_v2_remediation_r1 import (
    DEFAULT_TRUTH_SET_PATH,
    _load_truth_rows,
    _load_workbook_rows,
    _r1_comparison_audit,
)
from .ocr_v2_table_adapter import OCRV2TableAdapter


DEFAULT_G10B_TABLES_DIR = Path("output/ocr_v2_final_validation_tables")
DEFAULT_G10B_WORKBOOK_PATH = Path("output/ocr_v2_g10b_workbook.xlsx")
DEFAULT_G10B_AUDIT_PATH = Path("ocr_v2_g10b_context_audit.json")
DEFAULT_G10B_REPORT_PATH = Path("ocr_v2_g10b_context_report.md")


def write_ocr_v2_g10b_context_artifacts(
    *,
    tables_dir: str | Path = DEFAULT_G10B_TABLES_DIR,
    truth_set_path: str | Path = DEFAULT_TRUTH_SET_PATH,
    workbook_path: str | Path = DEFAULT_G10B_WORKBOOK_PATH,
    audit_path: str | Path = DEFAULT_G10B_AUDIT_PATH,
    report_path: str | Path = DEFAULT_G10B_REPORT_PATH,
) -> dict[str, Any]:
    """Write the G1.0b context enrichment audit and Markdown report."""

    before_cells = OCRV2TableAdapter(enable_page_context=False).ingest_directory(
        tables_dir
    ).cells
    after_cells = OCRV2TableAdapter().ingest_directory(tables_dir).cells
    before = _context_presence(before_cells)
    after = _context_presence(after_cells)

    run_result = OCRV2LuckyRun().run(tables_dir=tables_dir, workbook_path=workbook_path)
    workbook_rows = _load_workbook_rows(workbook_path)
    truth_rows = _load_truth_rows(truth_set_path)
    validation = _r1_comparison_audit(
        truth_rows=truth_rows,
        workbook_rows=workbook_rows,
        run_audit=run_result.audit.model_dump(mode="json"),
        workbook_path=workbook_path,
    )
    coverage = validation["coverage"]
    lucky_still_66 = (
        coverage["covered_cells"] == validation["truth_set_cells"] == 66
        and coverage["value_mismatches"] == 0
        and coverage["scale_mismatches"] == 0
        and coverage["missing_cells"] == 0
    )
    audit = {
        "audit": "ocr_v2_g10b_context_audit",
        "phase": "G1.0b",
        "scope": "context_enrichment_only",
        "tables_dir": str(tables_dir),
        "workbook_path": str(workbook_path),
        "total_candidates_before": len(before_cells),
        "total_candidates_after": len(after_cells),
        "statement_title_presence_before": before["statement_title"],
        "statement_title_presence_after": after["statement_title"],
        "notes_to_marker_before": before["notes_to_marker"],
        "notes_to_marker_after": after["notes_to_marker"],
        "entity_context_before": before["entity_context"],
        "entity_context_after": after["entity_context"],
        "context_presence_before": before,
        "context_presence_after": after,
        "lucky_validation": {
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
        "success_criteria": {
            "statement_title_coverage_materially_increased": (
                after["statement_title"]["count"] > before["statement_title"]["count"]
            ),
            "notes_markers_populated": after["notes_to_marker"]["count"] > 0,
            "entity_context_populated": after["entity_context"]["count"] > 0,
            "lucky_still_66_of_66": lucky_still_66,
        },
        "constraints_observed": {
            "governance_modified": False,
            "selection_modified": False,
            "workbook_generation_modified": False,
            "source_precedence_modified": False,
            "alias_handling_modified": False,
            "msil_export_modified": False,
            "production_integration_performed": False,
            "fallback_removed": False,
        },
        "final_determination": (
            "G10B_CONTEXT_ENRICHMENT_PASSED"
            if (
                after["statement_title"]["count"] > before["statement_title"]["count"]
                and after["notes_to_marker"]["count"] > 0
                and after["entity_context"]["count"] > 0
                and lucky_still_66
            )
            else "G10B_CONTEXT_ENRICHMENT_FAILED"
        ),
    }
    _write_json(audit_path, audit)
    _write_report(report_path, audit)
    return audit


def _context_presence(cells: tuple[Any, ...]) -> dict[str, Any]:
    total = len(cells)
    statement_title_count = sum(
        1 for cell in cells if cell.document_context.statement_title
    )
    notes_marker_count = sum(
        1 for cell in cells if cell.document_context.notes_to_marker
    )
    entity_context_count = sum(
        1 for cell in cells if cell.document_context.entity_context
    )
    section_heading_count = sum(
        1 for cell in cells if cell.document_context.section_heading
    )
    named_entities_count = sum(
        1 for cell in cells if cell.document_context.named_entities
    )
    units_scale_count = sum(
        1 for cell in cells if cell.document_context.units_scale_text
    )
    return {
        "total_candidates": total,
        "statement_title": _presence(statement_title_count, total),
        "notes_to_marker": _presence(notes_marker_count, total),
        "entity_context": _presence(entity_context_count, total),
        "section_heading": _presence(section_heading_count, total),
        "named_entities": _presence(named_entities_count, total),
        "units_scale_text": _presence(units_scale_count, total),
    }


def _presence(count: int, total: int) -> dict[str, Any]:
    return {
        "count": count,
        "total": total,
        "percent": round(count / total * 100, 2) if total else 0.0,
    }


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_report(path: str | Path, audit: dict[str, Any]) -> None:
    validation = audit["lucky_validation"]
    lines = [
        "# OCR V2 G1.0b Context Enrichment Report",
        "",
        f"Final determination: **{audit['final_determination']}**",
        "",
        "## Context Coverage",
        "",
        f"- Statement title before: {audit['statement_title_presence_before']['count']} / {audit['statement_title_presence_before']['total']} ({audit['statement_title_presence_before']['percent']}%)",
        f"- Statement title after: {audit['statement_title_presence_after']['count']} / {audit['statement_title_presence_after']['total']} ({audit['statement_title_presence_after']['percent']}%)",
        f"- Notes marker before: {audit['notes_to_marker_before']['count']} / {audit['notes_to_marker_before']['total']} ({audit['notes_to_marker_before']['percent']}%)",
        f"- Notes marker after: {audit['notes_to_marker_after']['count']} / {audit['notes_to_marker_after']['total']} ({audit['notes_to_marker_after']['percent']}%)",
        f"- Entity context before: {audit['entity_context_before']['count']} / {audit['entity_context_before']['total']} ({audit['entity_context_before']['percent']}%)",
        f"- Entity context after: {audit['entity_context_after']['count']} / {audit['entity_context_after']['total']} ({audit['entity_context_after']['percent']}%)",
        "",
        "## Lucky Validation",
        "",
        f"- Coverage: {validation['covered_cells']} / {validation['total_cells']} ({validation['coverage_percent']}%)",
        f"- Exact matches: {validation['exact_matches']}",
        f"- Source-insufficient abstentions: {validation['source_insufficient_correct_abstentions']}",
        f"- Value mismatches: {validation['value_mismatches']}",
        f"- Scale mismatches: {validation['scale_mismatches']}",
        f"- Missing cells: {validation['missing_cells']}",
        "",
        "## Constraints",
        "",
        "- Governance, selection, workbook generation, source precedence, aliases, and MSIL export were not modified.",
        "- Deprecated fallback remains available.",
        "- No production integration was performed.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "DEFAULT_G10B_AUDIT_PATH",
    "DEFAULT_G10B_REPORT_PATH",
    "DEFAULT_G10B_TABLES_DIR",
    "DEFAULT_G10B_WORKBOOK_PATH",
    "write_ocr_v2_g10b_context_artifacts",
]
