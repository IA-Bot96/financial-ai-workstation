"""Tests for OCR V2 Phase P5 canonical selection only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    CandidateCapture,
    CanonicalSelection,
    CanonicalSelectionReason,
    CanonicalSelectionStatus,
    EntityGovernance,
    OCRV2Basis,
    OCRV2EntityScope,
    OCRV2StatementType,
    ScaleGovernance,
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
    write_phase5_report,
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


def _entity_governed_from_rows(*rows: dict[str, object]):
    candidates = CandidateCapture().capture(rows).candidates
    statement_governed = StatementGovernance().govern(candidates).governed_candidates
    scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
    return EntityGovernance().govern(scale_governed).entity_governed_candidates


def test_canonical_selection_prefers_eligible_and_scale_valid_candidate() -> None:
    governed = _entity_governed_from_rows(
        _row(raw_value="100", table_reference="correct"),
        _row(
            raw_value="100000",
            table_reference="scale_bad",
            source_scale="magnitude_inferred_full_rupees",
        ),
        _row(
            raw_value="99",
            table_reference="note_review",
            statement_type=OCRV2StatementType.NOTE.value,
        ),
    )

    result = CanonicalSelection().select(governed)
    selected = result.selected_candidate

    assert result.decision.status == CanonicalSelectionStatus.SELECTED
    assert result.decision.selection_reason == (
        CanonicalSelectionReason.SINGLE_CANDIDATE_AFTER_FILTERING
    )
    assert selected is not None
    assert selected.table_reference == "correct"
    assert len(result.candidates) == 3
    assert set(result.decision.losing_candidate_ids) == {
        candidate.candidate_id
        for candidate in governed
        if candidate.table_reference in {"scale_bad", "note_review"}
    }
    assert result.decision.losing_candidate_reasons


def test_canonical_selection_returns_ambiguity_without_tie_break_guessing() -> None:
    governed = _entity_governed_from_rows(
        _row(raw_value="100", table_reference="candidate_a"),
        _row(raw_value="101", table_reference="candidate_b"),
    )

    result = CanonicalSelection().select(governed)

    assert result.decision.status == CanonicalSelectionStatus.AMBIGUOUS
    assert result.decision.selected_candidate_id is None
    assert result.decision.selection_reason == (
        CanonicalSelectionReason.AMBIGUOUS_MULTIPLE_EQUIVALENT_CANDIDATES
    )
    assert set(result.decision.ambiguity_candidate_ids) == {
        candidate.candidate_id for candidate in governed
    }


def test_canonical_selection_returns_no_selection_when_all_candidates_ineligible() -> None:
    governed = _entity_governed_from_rows(
        _row(
            raw_value="100",
            table_reference="investee_a",
            entity_scope=OCRV2EntityScope.INVESTEE.value,
        ),
        _row(
            raw_value="101",
            table_reference="investee_b",
            entity_scope=OCRV2EntityScope.INVESTEE.value,
        ),
    )

    result = CanonicalSelection().select(governed)

    assert result.decision.status == CanonicalSelectionStatus.NO_SELECTION
    assert result.decision.selected_candidate_id is None
    assert result.decision.selection_reason == (
        CanonicalSelectionReason.NO_ELIGIBLE_CANDIDATES
    )
    assert set(result.decision.losing_candidate_ids) == {
        candidate.candidate_id for candidate in governed
    }


def test_canonical_selection_preserves_losing_candidates_values_and_provenance() -> None:
    governed = _entity_governed_from_rows(
        _row(raw_value="100", table_reference="correct"),
        _row(
            raw_value="99",
            table_reference="analysis_table",
            statement_type=OCRV2StatementType.ANALYSIS_TABLE.value,
            source_scale="source_header:percentage_ingested_as_value",
            source_unit="%",
        ),
    )

    result = CanonicalSelection().select(governed)

    assert result.candidates == governed
    assert [candidate.original_value for candidate in result.candidates] == [
        candidate.original_value for candidate in governed
    ]
    assert [candidate.provenance for candidate in result.candidates] == [
        candidate.provenance for candidate in governed
    ]
    assert result.candidate_removals == 0
    assert result.value_modification_attempts == 0
    assert result.provenance_modification_attempts == 0
    assert not result.ranking_logic_used
    assert not result.candidate_scoring_used
    assert not result.llm_logic_used


def test_canonical_selection_is_deterministic() -> None:
    governed = _entity_governed_from_rows(
        _row(raw_value="100", table_reference="correct"),
        _row(
            raw_value="100000",
            table_reference="scale_bad",
            source_scale="magnitude_inferred_full_rupees",
        ),
    )
    selector = CanonicalSelection()

    first = selector.select(governed)
    second = selector.select(governed)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_canonical_selection_executes_regression_oracle_successfully() -> None:
    fixture = load_ocr_v2_regression_cases()
    selector = CanonicalSelection()

    for case in fixture["cases"]:
        candidates = candidates_from_regression_cases({**fixture, "cases": [case]})
        statement_governed = StatementGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(candidates).governed_candidates
        scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
        entity_governed = EntityGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(scale_governed).entity_governed_candidates

        result = selector.select(entity_governed)
        selected = result.selected_candidate

        assert result.decision.status == CanonicalSelectionStatus.SELECTED
        assert selected is not None
        assert selected.table_reference == f"{case['case_id']}_correct"
        assert selected.original_value == case["correct_candidate"]["value"]
        assert selected.table_reference != f"{case['case_id']}_incorrect"
        assert len(result.candidates) == 2


def test_canonical_selection_audit_has_required_success_values() -> None:
    tmp_path = _workspace_tmp("canonical_selection")
    audit_path = tmp_path / "ocr_v2_canonical_selection_audit.json"

    audit = CanonicalSelection().write_canonical_selection_audit(audit_path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["candidates_evaluated"] == 30
    assert payload["canonical_values_selected"] == 15
    assert payload["ambiguity_results"] == 0
    assert payload["no_selection_results"] == 0
    assert payload["regression_fixture_executed"] is True
    assert payload["regression_cases_executed"] == 15
    assert payload["regression_cases_passed"] == 15
    assert payload["regression_cases_failed"] == 0
    assert payload["incorrect_candidates_selected"] == 0
    assert payload["candidate_removals"] == 0
    assert payload["value_modification_attempts"] == 0
    assert payload["provenance_modification_attempts"] == 0
    assert payload["ranking_logic_used"] is False
    assert payload["candidate_scoring_used"] is False
    assert payload["llm_logic_used"] is False
    assert payload["integrity_violations"] == []
    assert audit.integrity_violations == ()


def test_phase5_report_writes_required_artifacts() -> None:
    tmp_path = _workspace_tmp("phase5")
    audit_path = tmp_path / "ocr_v2_canonical_selection_audit.json"
    report_path = tmp_path / "ocr_v2_phase5_report.json"

    report = write_phase5_report(audit_path=audit_path, report_path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert audit_path.exists()
    assert payload["phase"] == "P5"
    assert payload["scope"] == "canonical_selection_only"
    assert payload["regression_cases_passed"] == 15
    assert payload["regression_cases_failed"] == 0
    assert payload["incorrect_candidates_selected"] == 0
    assert payload["selection_logic_added"] is True
    assert payload["workbook_generation_added"] is False
    assert payload["ocr_to_msil_export_added"] is False
    assert payload["ranking_logic_added"] is False
    assert payload["candidate_scoring_added"] is False
    assert payload["authority_assignment_added"] is False
    assert payload["llm_logic_added"] is False
    assert payload["integrity_audit_passed"] is True
    assert report.integrity_violations == ()
