"""Tests for OCR V2 Phase P3 scale governance only."""

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
    ScaleGovernance,
    ScaleGovernanceOutcome,
    ScaleGovernanceReason,
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
    write_phase3_report,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _governed_regression_candidates():
    fixture = load_ocr_v2_regression_cases()
    candidates = candidates_from_regression_cases(fixture)
    return StatementGovernance().govern(candidates).governed_candidates


def test_scale_governance_executes_verified_cv1_regression_cases() -> None:
    fixture = load_ocr_v2_regression_cases()
    statement_governance = StatementGovernance(declared_basis=fixture["declared_basis"])
    scale_governance = ScaleGovernance()

    for case in fixture["cases"]:
        candidates = candidates_from_regression_cases({**fixture, "cases": [case]})
        statement_result = statement_governance.govern(candidates)
        scale_result = scale_governance.govern(statement_result.governed_candidates)
        correct, incorrect = scale_result.governed_candidates
        expected = case["expected_governance_result"]

        if expected["correct_candidate_expected"] == "SCALE_VALID":
            assert correct.scale_outcome == ScaleGovernanceOutcome.SCALE_VALID
        if expected["incorrect_candidate_expected"] == "SCALE_REVIEW_REQUIRED":
            assert incorrect.scale_outcome == (
                ScaleGovernanceOutcome.SCALE_REVIEW_REQUIRED
            )
        assert correct.candidate.raw_value == case["correct_candidate"]["value"]
        assert incorrect.candidate.raw_value == case["incorrect_candidate"]["value"]


def test_scale_governance_preserves_candidates_without_normalization_or_selection() -> None:
    governed_candidates = _governed_regression_candidates()

    result = ScaleGovernance().govern(governed_candidates)

    assert result.candidates_evaluated == len(governed_candidates)
    assert len(result.governed_candidates) == len(governed_candidates)
    assert [item.candidate for item in result.governed_candidates] == [
        item.candidate for item in governed_candidates
    ]
    assert [item.original_value for item in result.governed_candidates] == [
        item.original_value for item in governed_candidates
    ]
    assert result.normalization_attempts == 0
    assert result.scale_inference_attempts == 0
    assert result.candidate_removals == 0
    assert result.winner_selection_attempts == 0
    assert not any(item.normalization_attempted for item in result.governed_candidates)
    assert not any(item.scale_inference_attempted for item in result.governed_candidates)


def test_scale_governance_classifies_missing_unsupported_and_conflicting_scale() -> None:
    rows = (
        {
            "raw_value": "1",
            "raw_label": "Missing scale",
            "value_year": 2025,
            "page_number": 10,
            "table_reference": "missing_scale",
            "document_fingerprint": "fixture",
            "locator": "row:1:col:1",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": "ISSUER",
            "source_scale": "unknown",
            "source_unit": "PKR",
        },
        {
            "raw_value": "2",
            "raw_label": "Unsupported scale",
            "value_year": 2025,
            "page_number": 11,
            "table_reference": "unsupported_scale",
            "document_fingerprint": "fixture",
            "locator": "row:1:col:1",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": "ISSUER",
            "source_scale": "magnitude_inferred_full_rupees",
            "source_unit": "PKR",
        },
        {
            "raw_value": "3",
            "raw_label": "Conflicting scale",
            "value_year": 2025,
            "page_number": 12,
            "table_reference": "conflicting_scale",
            "document_fingerprint": "fixture",
            "locator": "row:1:col:1",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": "ISSUER",
            "source_scale": "conflicting_scale:PKR thousands vs PKR millions",
            "source_unit": "PKR",
        },
    )
    candidates = CandidateCapture().capture(rows).candidates
    statement_result = StatementGovernance().govern(candidates)

    result = ScaleGovernance().govern(statement_result.governed_candidates)

    assert [item.scale_outcome for item in result.governed_candidates] == [
        ScaleGovernanceOutcome.SCALE_UNKNOWN,
        ScaleGovernanceOutcome.SCALE_REVIEW_REQUIRED,
        ScaleGovernanceOutcome.SCALE_REVIEW_REQUIRED,
    ]
    assert [item.scale_reason for item in result.governed_candidates] == [
        ScaleGovernanceReason.DECLARED_SCALE_MISSING,
        ScaleGovernanceReason.UNSUPPORTED_SCALE,
        ScaleGovernanceReason.CONFLICTING_SCALE,
    ]


def test_scale_governance_is_deterministic() -> None:
    governed_candidates = _governed_regression_candidates()
    governance = ScaleGovernance()

    first = governance.govern(governed_candidates)
    second = governance.govern(governed_candidates)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_scale_governance_audit_has_required_success_values() -> None:
    tmp_path = _workspace_tmp("scale_governance")
    audit_path = tmp_path / "ocr_v2_scale_governance_audit.json"

    audit = ScaleGovernance().write_scale_governance_audit(audit_path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["candidates_evaluated"] > 0
    assert payload["scale_valid"] > 0
    assert payload["scale_review_required"] > 0
    assert payload["normalization_attempts"] == 0
    assert payload["scale_inference_attempts"] == 0
    assert payload["candidate_removals"] == 0
    assert payload["winner_selection_attempts"] == 0
    assert payload["regression_fixture_executed"] is True
    assert payload["regression_cases_executed"] >= 15
    assert payload["integrity_violations"] == []
    assert audit.integrity_violations == ()


def test_phase3_report_writes_required_artifacts() -> None:
    tmp_path = _workspace_tmp("phase3")
    statement_audit_path = tmp_path / "ocr_v2_statement_governance_audit.json"
    scale_audit_path = tmp_path / "ocr_v2_scale_governance_audit.json"
    report_path = tmp_path / "ocr_v2_phase3_report.json"

    report = write_phase3_report(
        statement_audit_path=statement_audit_path,
        scale_audit_path=scale_audit_path,
        report_path=report_path,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert statement_audit_path.exists()
    assert scale_audit_path.exists()
    assert payload["phase"] == "P3"
    assert payload["scope"] == "statement_governance_and_scale_governance_only"
    assert payload["candidate_removals"] == 0
    assert payload["winner_selection_attempts"] == 0
    assert payload["normalization_attempts"] == 0
    assert payload["scale_inference_attempts"] == 0
    assert payload["canonical_values_produced"] == 0
    assert payload["selection_logic_added"] is False
    assert payload["entity_governance_added"] is False
    assert payload["ranking_logic_added"] is False
    assert payload["llm_logic_added"] is False
    assert payload["integrity_audit_passed"] is True
    assert report.integrity_violations == ()
