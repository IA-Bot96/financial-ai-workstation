"""Tests for the OCR V2 permanent regression oracle fixture.

These tests validate fixture integrity only. They do not execute governance,
selection, OCR extraction, workbook generation, ranking, or LLM behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    OCRV2RegressionFailureClass,
    REGRESSION_CASES_PATH,
    REQUIRED_CASE_IDS,
    build_ocr_v2_regression_fixture_audit,
    load_ocr_v2_regression_fixture,
    write_ocr_v2_regression_fixture_audit,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_regression_fixture_loads_and_contains_required_cases() -> None:
    fixture = load_ocr_v2_regression_fixture()
    case_ids = {case.case_id for case in fixture.cases}

    assert Path(REGRESSION_CASES_PATH).exists()
    assert len(fixture.cases) >= 15
    assert case_ids >= set(REQUIRED_CASE_IDS)
    assert fixture.entity_ref == "lucky_cement"
    assert fixture.declared_basis == "unconsolidated"


def test_regression_fixture_schema_and_allowed_enums() -> None:
    fixture = load_ocr_v2_regression_fixture()
    allowed_failure_classes = {item.value for item in OCRV2RegressionFailureClass}
    allowed_correct = {"ELIGIBLE", "SCALE_VALID"}
    allowed_incorrect = {
        "INELIGIBLE",
        "REVIEW_REQUIRED",
        "SCALE_REVIEW_REQUIRED",
    }

    for case in fixture.cases:
        assert case.failure_class.value in allowed_failure_classes
        assert case.expected_governance_result.correct_candidate_expected in allowed_correct
        assert (
            case.expected_governance_result.incorrect_candidate_expected
            in allowed_incorrect
        )
        assert case.verified_by
        assert case.verification_source
        for candidate in (case.correct_candidate, case.incorrect_candidate):
            assert candidate.value not in (None, "")
            assert candidate.basis
            assert candidate.statement_type
            assert candidate.entity_scope
            assert candidate.source_scale
            assert candidate.source_unit
            assert candidate.page_number > 0
            assert candidate.provenance_reference


def test_regression_fixture_loading_is_deterministic() -> None:
    first = load_ocr_v2_regression_fixture()
    second = load_ocr_v2_regression_fixture()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_regression_fixture_has_no_duplicate_case_ids() -> None:
    fixture = load_ocr_v2_regression_fixture()
    case_ids = [case.case_id for case in fixture.cases]

    assert len(case_ids) == len(set(case_ids))


def test_regression_fixture_audit_has_success_values() -> None:
    audit = build_ocr_v2_regression_fixture_audit()

    assert audit.regression_case_count >= 15
    assert audit.verified_case_count == audit.regression_case_count
    assert audit.missing_fields == ()
    assert audit.missing_required_cases == ()
    assert audit.duplicate_case_ids == ()
    assert audit.integrity_violations == ()


def test_regression_fixture_audit_can_be_written() -> None:
    tmp_path = _workspace_tmp("regression_fixture")
    audit_path = tmp_path / "ocr_v2_regression_fixture_audit.json"

    audit = write_ocr_v2_regression_fixture_audit(audit_path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["regression_case_count"] >= 15
    assert payload["verified_case_count"] == payload["regression_case_count"]
    assert payload["missing_fields"] == []
    assert payload["integrity_violations"] == []
    assert payload["deterministic_signature"] == audit.deterministic_signature
