"""Tests for OCR V2 Phase P1 candidate capture only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    UNKNOWN_CLASSIFICATION,
    CandidateCapture,
    CandidateCaptureInput,
    CandidateFact,
    CandidateProvenanceContract,
    OCRV2Basis,
    OCRV2EntityScope,
    OCRV2StatementType,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _candidate_rows() -> tuple[dict, ...]:
    return (
        {
            "raw_value": "52.53",
            "raw_label": "Earnings per share",
            "value_year": 2025,
            "page_number": 292,
            "table_reference": "table_292_income_statement",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:38:col:2025",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": OCRV2EntityScope.ISSUER.value,
            "source_scale": "source_header:PKR",
            "source_unit": "PKR",
        },
        {
            "raw_value": "52.53",
            "raw_label": "Earnings per share",
            "value_year": 2025,
            "page_number": 166,
            "table_reference": "table_166_ratio_summary",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:12:col:2025",
            "statement_type": OCRV2StatementType.SUMMARY_TABLE.value,
            "basis": OCRV2Basis.UNKNOWN.value,
            "entity_scope": UNKNOWN_CLASSIFICATION,
            "source_scale": UNKNOWN_CLASSIFICATION,
            "source_unit": UNKNOWN_CLASSIFICATION,
        },
    )


def test_candidate_creation_preserves_raw_observation_and_provenance() -> None:
    candidate = CandidateCapture().create_candidate(
        raw_value="52.53",
        raw_label="Earnings per share",
        value_year=2025,
        page_number=292,
        table_reference="table_292_income_statement",
        document_fingerprint="fixture_lucky_2025",
        locator="row:38:col:2025",
        statement_type=OCRV2StatementType.PRIMARY_STATEMENT,
        basis=OCRV2Basis.UNCONSOLIDATED,
        entity_scope=OCRV2EntityScope.ISSUER,
        source_scale="source_header:PKR",
        source_unit="PKR",
    )

    assert isinstance(candidate, CandidateFact)
    assert candidate.raw_value == "52.53"
    assert candidate.raw_label == "Earnings per share"
    assert candidate.value_year == 2025
    assert candidate.page_number == 292
    assert candidate.table_reference == "table_292_income_statement"
    assert candidate.statement_type == "PRIMARY_STATEMENT"
    assert candidate.basis == "unconsolidated"
    assert candidate.entity_scope == "ISSUER"
    assert candidate.source_scale == "source_header:PKR"
    assert candidate.source_unit == "PKR"
    assert candidate.provenance.document_fingerprint == "fixture_lucky_2025"
    assert candidate.provenance.locator == "row:38:col:2025"


def test_competing_candidates_are_preserved_without_selection() -> None:
    result = CandidateCapture().capture(_candidate_rows())

    assert result.candidates_captured == 2
    assert len(result.candidates) == 2
    assert {candidate.table_reference for candidate in result.candidates} == {
        "table_292_income_statement",
        "table_166_ratio_summary",
    }
    assert result.canonical_selection_attempts == 0
    assert result.discarded_candidates == 0
    assert result.selection_logic_added is False
    assert result.governance_logic_added is False
    assert result.integrity_violations == ()


def test_unknown_classifications_are_allowed_and_not_inferred() -> None:
    candidate = CandidateCapture().create_candidate(
        raw_value="123",
        raw_label="Unclassified row",
        value_year=2025,
        page_number=10,
        table_reference="table_10_unknown",
        document_fingerprint="fixture_lucky_2025",
        locator="row:1:col:1",
    )

    assert candidate.statement_type == UNKNOWN_CLASSIFICATION
    assert candidate.basis == OCRV2Basis.UNKNOWN.value
    assert candidate.entity_scope == UNKNOWN_CLASSIFICATION
    assert candidate.source_scale == UNKNOWN_CLASSIFICATION
    assert candidate.source_unit == UNKNOWN_CLASSIFICATION


def test_candidate_capture_input_roundtrips_to_candidate() -> None:
    row = CandidateCaptureInput(**_candidate_rows()[0])

    result = CandidateCapture().capture((row,))

    assert result.candidates_captured == 1
    assert result.candidates[0].raw_label == row.raw_label
    assert result.candidates[0].provenance.page == row.page_number


def test_provenance_alignment_is_required_for_candidate_fact() -> None:
    with pytest.raises(ValidationError):
        CandidateFact(
            candidate_id="candidate_bad",
            raw_value="1",
            raw_label="Bad row",
            value_year=2025,
            page_number=11,
            table_reference="table_11",
            statement_type=UNKNOWN_CLASSIFICATION,
            basis=OCRV2Basis.UNKNOWN.value,
            entity_scope=UNKNOWN_CLASSIFICATION,
            source_scale=UNKNOWN_CLASSIFICATION,
            source_unit=UNKNOWN_CLASSIFICATION,
            provenance=CandidateProvenanceContract(
                document_fingerprint="fixture",
                page=10,
                table_ref="table_11",
                locator="row:1:col:1",
            ),
        )


def test_capture_is_deterministically_repeatable() -> None:
    capture = CandidateCapture()

    first = capture.capture(_candidate_rows())
    second = capture.capture(_candidate_rows())

    assert first.deterministic_signature == second.deterministic_signature
    assert [candidate.candidate_id for candidate in first.candidates] == [
        candidate.candidate_id for candidate in second.candidates
    ]
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_candidate_capture_audit_and_report_have_required_success_values() -> None:
    tmp_path = _workspace_tmp("candidate_capture")
    audit_path = tmp_path / "ocr_v2_candidate_capture_audit.json"
    report_path = tmp_path / "ocr_v2_phase1_report.json"

    report = CandidateCapture().write_phase1_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["candidates_captured"] > 0
    assert audit["provenance_coverage_percent"] == 100.0
    assert audit["canonical_selection_attempts"] == 0
    assert audit["discarded_candidates"] == 0
    assert audit["integrity_violations"] == []
    assert report.phase == "P1"
    assert report.scope == "candidate_capture_only"
    assert report.candidates_created == audit["candidates_captured"]
    assert report.selection_logic_added is False
    assert report.governance_logic_added is False
    assert report.integrity_audit_passed is True
