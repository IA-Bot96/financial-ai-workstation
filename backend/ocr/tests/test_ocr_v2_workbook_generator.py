"""Tests for OCR V2 Phase P6 workbook generation only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from openpyxl import load_workbook

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    CandidateCapture,
    CanonicalSelection,
    CanonicalSelectionStatus,
    EntityGovernance,
    OCRV2Basis,
    OCRV2EntityScope,
    OCRV2StatementType,
    OCRV2WorkbookGenerator,
    ScaleGovernance,
    StatementGovernance,
    WORKBOOK_HEADERS,
    WORKBOOK_SHEET_NAME,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
    write_phase6_report,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _row(
    *,
    raw_value: str,
    table_reference: str,
    statement_type: str = OCRV2StatementType.PRIMARY_STATEMENT.value,
    basis: str = OCRV2Basis.UNCONSOLIDATED.value,
    entity_scope: str = OCRV2EntityScope.ISSUER.value,
    source_scale: str = "source_header:PKR thousands",
    source_unit: str = "PKR",
) -> dict[str, object]:
    return {
        "raw_value": raw_value,
        "raw_label": "revenue",
        "value_year": 2025,
        "page_number": 241,
        "table_reference": table_reference,
        "document_fingerprint": "fixture",
        "locator": f"{table_reference}:row:1:col:1",
        "statement_type": statement_type,
        "basis": basis,
        "entity_scope": entity_scope,
        "source_scale": source_scale,
        "source_unit": source_unit,
    }


def _selection_result(*rows: dict[str, object]):
    candidates = CandidateCapture().capture(rows).candidates
    statement_governed = StatementGovernance().govern(candidates).governed_candidates
    scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
    entity_governed = EntityGovernance().govern(scale_governed).entity_governed_candidates
    return CanonicalSelection().select(entity_governed)


def _regression_selection_results():
    fixture = load_ocr_v2_regression_cases()
    results = []
    for case in fixture["cases"]:
        candidates = candidates_from_regression_cases({**fixture, "cases": [case]})
        statement_governed = StatementGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(candidates).governed_candidates
        scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
        entity_governed = EntityGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(scale_governed).entity_governed_candidates
        results.append(CanonicalSelection().select(entity_governed))
    return fixture, tuple(results)


def test_workbook_generation_projects_selected_canonical_rows_only() -> None:
    selected_result = _selection_result(
        _row(raw_value="100", table_reference="correct"),
        _row(
            raw_value="100000",
            table_reference="scale_bad",
            source_scale="magnitude_inferred_full_rupees",
        ),
    )
    ambiguous_result = _selection_result(
        _row(raw_value="100", table_reference="candidate_a"),
        _row(raw_value="101", table_reference="candidate_b"),
    )

    output = OCRV2WorkbookGenerator().generate(
        (selected_result, ambiguous_result),
        entity_ref="lucky_cement",
    )

    assert selected_result.decision.status == CanonicalSelectionStatus.SELECTED
    assert ambiguous_result.decision.status == CanonicalSelectionStatus.AMBIGUOUS
    assert output.workbook_rows_generated == 1
    assert output.rows[0].canonical_value == selected_result.selected_candidate.original_value
    assert output.rows[0].table_reference == "correct"


def test_workbook_generation_preserves_provenance_and_source_metadata() -> None:
    result = _selection_result(
        _row(raw_value="100", table_reference="correct"),
        _row(
            raw_value="99",
            table_reference="note",
            statement_type=OCRV2StatementType.NOTE.value,
        ),
    )

    output = OCRV2WorkbookGenerator().generate((result,), entity_ref="lucky_cement")
    workbook_row = output.rows[0]
    selected = result.selected_candidate
    candidate = selected.candidate

    assert workbook_row.metric_id == candidate.raw_label
    assert workbook_row.value_year == candidate.value_year
    assert workbook_row.canonical_value == candidate.raw_value
    assert workbook_row.entity_ref == "lucky_cement"
    assert workbook_row.basis == candidate.basis
    assert workbook_row.statement_type == candidate.statement_type
    assert workbook_row.entity_scope == candidate.entity_scope
    assert workbook_row.source_scale == candidate.source_scale
    assert workbook_row.source_unit == candidate.source_unit
    assert workbook_row.page_number == candidate.page_number
    assert workbook_row.table_reference == candidate.table_reference
    assert workbook_row.source_reference == candidate.provenance.table_ref
    assert workbook_row.provenance_reference == candidate.provenance.locator
    assert workbook_row.selected_candidate_id == candidate.candidate_id


def test_workbook_generation_is_deterministic() -> None:
    result = _selection_result(
        _row(raw_value="100", table_reference="correct"),
        _row(
            raw_value="100000",
            table_reference="scale_bad",
            source_scale="magnitude_inferred_full_rupees",
        ),
    )
    generator = OCRV2WorkbookGenerator()

    first = generator.generate((result,), entity_ref="lucky_cement")
    second = generator.generate((result,), entity_ref="lucky_cement")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_workbook_generation_writes_xlsx_with_canonical_rows() -> None:
    tmp_path = _workspace_tmp("workbook_generation")
    workbook_path = tmp_path / "ocr_v2_workbook.xlsx"
    result = _selection_result(
        _row(raw_value="100", table_reference="correct"),
        _row(
            raw_value="99",
            table_reference="analysis",
            statement_type=OCRV2StatementType.ANALYSIS_TABLE.value,
            source_scale="source_header:percentage_ingested_as_value",
            source_unit="%",
        ),
    )

    output = OCRV2WorkbookGenerator().write_xlsx(
        (result,),
        workbook_path,
        entity_ref="lucky_cement",
    )
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    worksheet = workbook[WORKBOOK_SHEET_NAME]

    assert workbook_path.exists()
    assert output.workbook_rows_generated == 1
    assert [cell.value for cell in worksheet[1]] == list(WORKBOOK_HEADERS)
    first_row = [cell.value for cell in worksheet[2]]
    assert first_row[WORKBOOK_HEADERS.index("canonical_value")] == "100"
    assert first_row[WORKBOOK_HEADERS.index("table_reference")] == "correct"
    assert first_row[WORKBOOK_HEADERS.index("provenance_reference")] == (
        "correct:row:1:col:1"
    )


def test_workbook_generation_regression_oracle_compatibility() -> None:
    fixture, results = _regression_selection_results()

    output = OCRV2WorkbookGenerator().generate(
        results,
        entity_ref=fixture["entity_ref"],
    )
    rows_by_table_ref = {row.table_reference: row for row in output.rows}

    assert output.workbook_rows_generated == 15
    for case in fixture["cases"]:
        correct_ref = f"{case['case_id']}_correct"
        incorrect_ref = f"{case['case_id']}_incorrect"
        assert correct_ref in rows_by_table_ref
        assert incorrect_ref not in rows_by_table_ref
        row = rows_by_table_ref[correct_ref]
        assert row.canonical_value == case["correct_candidate"]["value"]
        assert row.provenance_reference == (
            case["correct_candidate"]["provenance_reference"]
        )


def test_workbook_generation_audit_has_required_success_values() -> None:
    tmp_path = _workspace_tmp("workbook_generation_audit")
    audit_path = tmp_path / "ocr_v2_workbook_generation_audit.json"

    audit = OCRV2WorkbookGenerator().write_workbook_generation_audit(audit_path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["workbook_rows_generated"] == 15
    assert payload["provenance_preserved_count"] == 15
    assert payload["value_mutations"] == 0
    assert payload["scale_mutations"] == 0
    assert payload["regression_cases_verified"] == 15
    assert payload["contract_preserved"] is True
    assert payload["integrity_violations"] == []
    assert audit.integrity_violations == ()


def test_phase6_report_writes_required_artifacts() -> None:
    tmp_path = _workspace_tmp("phase6")
    audit_path = tmp_path / "ocr_v2_workbook_generation_audit.json"
    workbook_path = tmp_path / "ocr_v2_workbook_generation.xlsx"
    report_path = tmp_path / "ocr_v2_phase6_report.json"

    report = write_phase6_report(
        audit_path=audit_path,
        workbook_output_path=workbook_path,
        report_path=report_path,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert audit_path.exists()
    assert workbook_path.exists()
    assert payload["phase"] == "P6"
    assert payload["scope"] == "workbook_generation_only"
    assert payload["workbook_rows_generated"] == 15
    assert payload["contract_preserved"] is True
    assert payload["value_mutations"] == 0
    assert payload["scale_mutations"] == 0
    assert payload["regression_cases_verified"] == 15
    assert payload["ocr_to_msil_export_added"] is False
    assert payload["new_governance_rules_added"] is False
    assert payload["new_selection_rules_added"] is False
    assert payload["ranking_logic_added"] is False
    assert payload["candidate_scoring_added"] is False
    assert payload["llm_logic_added"] is False
    assert payload["ocr_extraction_changes_added"] is False
    assert payload["integrity_audit_passed"] is True
    assert report.integrity_violations == ()
