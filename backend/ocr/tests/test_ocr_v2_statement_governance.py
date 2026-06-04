"""Tests for OCR V2 Phase P3 statement governance only."""

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
    OCRV2Basis,
    OCRV2StatementType,
    REGRESSION_CASES_PATH,
    REQUIRED_CASE_IDS,
    StatementGovernance,
    StatementGovernanceOutcome,
    StatementGovernanceReason,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_regression_fixture_is_present_and_covers_required_cases() -> None:
    fixture = load_ocr_v2_regression_cases()

    assert Path(REGRESSION_CASES_PATH).exists()
    assert len(fixture["cases"]) >= 15
    assert {case["case_id"] for case in fixture["cases"]} >= set(REQUIRED_CASE_IDS)
    assert {case["failure_class"] for case in fixture["cases"]} >= {
        "statement_basis",
        "scale_governance",
        "analysis_table_contamination",
        "note_contamination",
        "investee_contamination",
        "summary_table_contamination",
    }


def test_statement_governance_executes_verified_cv1_regression_cases() -> None:
    fixture = load_ocr_v2_regression_cases()
    governance = StatementGovernance(declared_basis=fixture["declared_basis"])

    for case in fixture["cases"]:
        candidates = candidates_from_regression_cases({**fixture, "cases": [case]})
        result = governance.govern(candidates)
        correct, incorrect = result.governed_candidates
        expected = case["expected_governance_result"]

        if expected["correct_candidate_expected"] == "ELIGIBLE":
            assert correct.governance_outcome == StatementGovernanceOutcome.ELIGIBLE
        if (
            expected["incorrect_candidate_expected"] == "INELIGIBLE"
            and case["failure_class"] != "investee_contamination"
        ):
            assert incorrect.governance_outcome == StatementGovernanceOutcome.INELIGIBLE
        if expected["incorrect_candidate_expected"] == "REVIEW_REQUIRED":
            assert incorrect.governance_outcome == (
                StatementGovernanceOutcome.REVIEW_REQUIRED
            )
        assert correct.candidate.raw_value == case["correct_candidate"]["value"]
        assert incorrect.candidate.raw_value == case["incorrect_candidate"]["value"]
        assert correct.provenance
        assert incorrect.provenance


def test_statement_governance_preserves_candidates_without_selection() -> None:
    fixture = load_ocr_v2_regression_cases()
    candidates = candidates_from_regression_cases(fixture)

    result = StatementGovernance().govern(candidates)

    assert result.candidates_evaluated == len(candidates)
    assert len(result.governed_candidates) == len(candidates)
    assert [item.candidate for item in result.governed_candidates] == list(candidates)
    assert [item.original_value for item in result.governed_candidates] == [
        candidate.raw_value for candidate in candidates
    ]
    assert result.candidate_removals == 0
    assert result.winner_selection_attempts == 0
    assert result.canonical_values_produced == 0
    assert not any(hasattr(item, "canonical_value") for item in result.governed_candidates)


def test_statement_governance_classifies_analysis_summary_note_and_basis() -> None:
    capture = CandidateCapture()
    rows = (
        {
            "raw_value": "1",
            "raw_label": "Analysis percentage",
            "value_year": 2025,
            "page_number": 10,
            "table_reference": "analysis_table",
            "document_fingerprint": "fixture",
            "locator": "row:1:col:1",
            "statement_type": OCRV2StatementType.ANALYSIS_TABLE.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": "ISSUER",
            "source_scale": "source_header:percentage",
            "source_unit": "%",
        },
        {
            "raw_value": "2",
            "raw_label": "Summary value",
            "value_year": 2025,
            "page_number": 11,
            "table_reference": "summary_table",
            "document_fingerprint": "fixture",
            "locator": "row:1:col:1",
            "statement_type": OCRV2StatementType.SUMMARY_TABLE.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": "ISSUER",
            "source_scale": "source_header:PKR million",
            "source_unit": "PKR",
        },
        {
            "raw_value": "3",
            "raw_label": "Note value",
            "value_year": 2025,
            "page_number": 12,
            "table_reference": "note_table",
            "document_fingerprint": "fixture",
            "locator": "row:1:col:1",
            "statement_type": OCRV2StatementType.NOTE.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": "ISSUER",
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
        {
            "raw_value": "4",
            "raw_label": "Wrong basis value",
            "value_year": 2025,
            "page_number": 13,
            "table_reference": "wrong_basis_table",
            "document_fingerprint": "fixture",
            "locator": "row:1:col:1",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.CONSOLIDATED.value,
            "entity_scope": "ISSUER",
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
    )
    candidates = capture.capture(rows).candidates

    result = StatementGovernance().govern(candidates)

    assert [item.governance_outcome for item in result.governed_candidates] == [
        StatementGovernanceOutcome.INELIGIBLE,
        StatementGovernanceOutcome.REVIEW_REQUIRED,
        StatementGovernanceOutcome.REVIEW_REQUIRED,
        StatementGovernanceOutcome.INELIGIBLE,
    ]
    assert [item.governance_reason for item in result.governed_candidates] == [
        StatementGovernanceReason.ANALYSIS_TABLE,
        StatementGovernanceReason.SUMMARY_TABLE,
        StatementGovernanceReason.NOTE_ONLY,
        StatementGovernanceReason.AMBIGUOUS_BASIS,
    ]


def test_statement_governance_is_deterministic() -> None:
    fixture = load_ocr_v2_regression_cases()
    candidates = candidates_from_regression_cases(fixture)
    governance = StatementGovernance()

    first = governance.govern(candidates)
    second = governance.govern(candidates)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_statement_governance_audit_has_required_success_values() -> None:
    tmp_path = _workspace_tmp("statement_governance")
    audit_path = tmp_path / "ocr_v2_statement_governance_audit.json"

    audit = StatementGovernance().write_statement_governance_audit(audit_path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["candidates_evaluated"] > 0
    assert payload["eligible_candidates"] > 0
    assert payload["ineligible_candidates"] > 0
    assert payload["review_required_candidates"] > 0
    assert payload["candidate_removals"] == 0
    assert payload["winner_selection_attempts"] == 0
    assert payload["canonical_values_produced"] == 0
    assert payload["regression_fixture_executed"] is True
    assert payload["regression_cases_executed"] >= 15
    assert payload["integrity_violations"] == []
    assert audit.integrity_violations == ()
