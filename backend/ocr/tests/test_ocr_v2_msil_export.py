"""Tests for OCR V2 Phase P7 OCR-to-MSIL export only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    ClaimType,
    ContentClass,
    EntityResolutionResult,
    ProvenanceType,
    ResolutionMethod,
    ReviewStatus,
    SourceType,
)
from ocr import (  # noqa: E402
    CandidateCapture,
    CanonicalSelection,
    EntityGovernance,
    OCRV2MSILExporter,
    OCRV2StatementType,
    OCRV2WorkbookGenerator,
    ScaleGovernance,
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
    write_phase7_report,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolution(entity_ref: str = "lucky_cement") -> EntityResolutionResult:
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
        evidence={"resolution_reason": "test_supplied_resolution"},
    )


def _exporter(entity_ref: str = "lucky_cement") -> OCRV2MSILExporter:
    return OCRV2MSILExporter(
        entity_resolution=_resolution(entity_ref),
        workbook_fingerprint="fp_lucky_2025",
        report_reference="annual_report:lucky:2025",
        source_report_year=2025,
    )


def _row(
    *,
    raw_value: str,
    table_reference: str,
    statement_type: str = OCRV2StatementType.PRIMARY_STATEMENT.value,
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
        "basis": "unconsolidated",
        "entity_scope": "ISSUER",
        "source_scale": "source_header:PKR thousands",
        "source_unit": "PKR",
    }


def _selection_result(*rows: dict[str, object]):
    candidates = CandidateCapture().capture(rows).candidates
    statement_governed = StatementGovernance().govern(candidates).governed_candidates
    scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
    entity_governed = EntityGovernance().govern(scale_governed).entity_governed_candidates
    return CanonicalSelection().select(entity_governed)


def _regression_workbook_output():
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
    return fixture, OCRV2WorkbookGenerator().generate(
        tuple(results),
        entity_ref=fixture["entity_ref"],
    )


def test_msil_export_projects_workbook_rows_to_numeric_intelligence_signals() -> None:
    result = _selection_result(
        _row(raw_value="100", table_reference="correct"),
        _row(raw_value="99", table_reference="note", statement_type="NOTE"),
    )
    workbook_output = OCRV2WorkbookGenerator().generate(
        (result,),
        entity_ref="lucky_cement",
    )

    bundle = _exporter().export(workbook_output)
    signal = bundle.signals[0]

    assert bundle.rows_exported == 1
    assert bundle.contract_preserved is True
    assert signal.content.content_class == ContentClass.NUMERIC_CLAIM
    assert signal.content.metric_ref == "revenue"
    assert signal.content.value == "100"
    assert signal.content.unit == "PKR"
    assert signal.classification.source_type == SourceType.ANNUAL_REPORT
    assert signal.classification.claim_type == ClaimType.AUDITED_FACT
    assert signal.classification.creation_eligible is True


def test_msil_export_preserves_value_scale_and_provenance() -> None:
    result = _selection_result(
        _row(raw_value="100", table_reference="correct"),
        _row(raw_value="99", table_reference="note", statement_type="NOTE"),
    )
    workbook_output = OCRV2WorkbookGenerator().generate(
        (result,),
        entity_ref="lucky_cement",
    )
    row = workbook_output.rows[0]

    signal = _exporter().export(workbook_output).signals[0]

    assert signal.content.value == row.canonical_value
    assert signal.content.payload["source_scale"] == row.source_scale
    assert signal.content.payload["source_reference"] == row.source_reference
    assert signal.content.payload["provenance_reference"] == row.provenance_reference
    assert signal.provenance.provenance_type == ProvenanceType.PDF_PAGE
    assert signal.provenance.page_number == row.page_number
    assert signal.provenance.cell_reference == row.provenance_reference
    assert signal.provenance.source_lineage == (row.source_reference,)
    assert signal.provenance.workbook_fingerprint == "fp_lucky_2025"
    assert signal.provenance.report_reference == "annual_report:lucky:2025"


def test_msil_export_is_deterministic() -> None:
    result = _selection_result(
        _row(raw_value="100", table_reference="correct"),
        _row(raw_value="99", table_reference="note", statement_type="NOTE"),
    )
    workbook_output = OCRV2WorkbookGenerator().generate(
        (result,),
        entity_ref="lucky_cement",
    )
    exporter = _exporter()

    first = exporter.export(workbook_output)
    second = exporter.export(workbook_output)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_msil_export_requires_supplied_resolved_entity_resolution() -> None:
    unresolved = EntityResolutionResult(
        raw_identifier="Lucky",
        normalized_identifier="lucky",
        method=ResolutionMethod.FUZZY,
        confidence=0.7,
        review_status=ReviewStatus.REVIEW,
        candidates=(),
        review_required=True,
    )

    with pytest.raises(ValueError, match="resolved entity_resolution"):
        OCRV2MSILExporter(
            entity_resolution=unresolved,
            workbook_fingerprint="fp_lucky_2025",
            report_reference="annual_report:lucky:2025",
        )


def test_msil_export_rejects_entity_mismatch_instead_of_resolving() -> None:
    result = _selection_result(_row(raw_value="100", table_reference="correct"))
    workbook_output = OCRV2WorkbookGenerator().generate(
        (result,),
        entity_ref="lucky_cement",
    )

    with pytest.raises(ValueError, match="does not perform entity resolution"):
        _exporter(entity_ref="millat_tractors").export(workbook_output)


def test_msil_export_regression_oracle_compatibility() -> None:
    fixture, workbook_output = _regression_workbook_output()

    bundle = _exporter(fixture["entity_ref"]).export(workbook_output)
    signals_by_table_ref = {
        signal.content.payload["table_reference"]: signal for signal in bundle.signals
    }

    assert bundle.rows_exported == 15
    for case in fixture["cases"]:
        correct_ref = f"{case['case_id']}_correct"
        incorrect_ref = f"{case['case_id']}_incorrect"
        assert correct_ref in signals_by_table_ref
        assert incorrect_ref not in signals_by_table_ref
        signal = signals_by_table_ref[correct_ref]
        assert signal.content.value == case["correct_candidate"]["value"]
        assert signal.provenance.cell_reference == (
            case["correct_candidate"]["provenance_reference"]
        )
        assert signal.content.payload["provenance_reference"] == (
            case["correct_candidate"]["provenance_reference"]
        )


def test_msil_export_audit_has_required_success_values() -> None:
    tmp_path = _workspace_tmp("msil_export_audit")
    audit_path = tmp_path / "ocr_v2_msil_export_audit.json"
    fixture, workbook_output = _regression_workbook_output()

    audit = _exporter(fixture["entity_ref"]).write_msil_export_audit(
        workbook_output,
        audit_path,
        fixture=fixture,
    )
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["rows_exported"] == 15
    assert payload["provenance_preserved_count"] == 15
    assert payload["value_mutations"] == 0
    assert payload["scale_mutations"] == 0
    assert payload["regression_cases_verified"] == 15
    assert payload["msil_contract_compatible"] is True
    assert payload["integrity_violations"] == []
    assert audit.integrity_violations == ()


def test_phase7_report_writes_required_artifacts() -> None:
    tmp_path = _workspace_tmp("phase7")
    audit_path = tmp_path / "ocr_v2_msil_export_audit.json"
    report_path = tmp_path / "ocr_v2_phase7_report.json"

    report = write_phase7_report(audit_path=audit_path, report_path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert audit_path.exists()
    assert payload["phase"] == "P7"
    assert payload["scope"] == "ocr_to_msil_export_only"
    assert payload["rows_exported"] == 15
    assert payload["contract_preserved"] is True
    assert payload["value_mutations"] == 0
    assert payload["scale_mutations"] == 0
    assert payload["regression_cases_verified"] == 15
    assert payload["msil_contract_compatible"] is True
    assert payload["ocr_extraction_changes_added"] is False
    assert payload["governance_changes_added"] is False
    assert payload["selection_changes_added"] is False
    assert payload["workbook_changes_added"] is False
    assert payload["ranking_logic_added"] is False
    assert payload["scoring_logic_added"] is False
    assert payload["authority_assignment_added"] is False
    assert payload["llm_logic_added"] is False
    assert payload["msil_schema_changes_added"] is False
    assert payload["integrity_audit_passed"] is True
    assert report.integrity_violations == ()
