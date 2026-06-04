"""Tests for OCR V2 Phase P2 candidate registry only."""

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
    CandidateFact,
    CandidateRegistry,
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
            "raw_value": "52,530,000",
            "raw_label": "Revenue",
            "value_year": 2025,
            "page_number": 292,
            "table_reference": "table_292_consolidated_statement",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:3:col:2025",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.CONSOLIDATED.value,
            "entity_scope": OCRV2EntityScope.ISSUER.value,
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
        {
            "raw_value": "49,250,000",
            "raw_label": "Revenue",
            "value_year": 2025,
            "page_number": 293,
            "table_reference": "table_293_unconsolidated_statement",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:3:col:2025",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": OCRV2EntityScope.ISSUER.value,
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
        {
            "raw_value": "52,530,000",
            "raw_label": "Revenue",
            "value_year": 2025,
            "page_number": 166,
            "table_reference": "table_166_financial_highlights",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:5:col:2025",
            "statement_type": OCRV2StatementType.SUMMARY_TABLE.value,
            "basis": OCRV2Basis.CONSOLIDATED.value,
            "entity_scope": OCRV2EntityScope.ISSUER.value,
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
        {
            "raw_value": "52.53",
            "raw_label": "Earnings per share",
            "value_year": 2025,
            "page_number": 162,
            "table_reference": "table_162_analysis",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:19:col:2025",
            "statement_type": OCRV2StatementType.ANALYSIS_TABLE.value,
            "basis": OCRV2Basis.UNKNOWN.value,
            "entity_scope": OCRV2EntityScope.ISSUER.value,
            "source_scale": "source_header:percent",
            "source_unit": "%",
        },
        {
            "raw_value": "12,300,000",
            "raw_label": "Current assets",
            "value_year": 2025,
            "page_number": 341,
            "table_reference": "table_341_note_current_assets",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:9:col:2025",
            "statement_type": OCRV2StatementType.NOTE.value,
            "basis": OCRV2Basis.CONSOLIDATED.value,
            "entity_scope": OCRV2EntityScope.ISSUER.value,
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
        {
            "raw_value": "1,120,000",
            "raw_label": "Share of profit of investee",
            "value_year": 2025,
            "page_number": 350,
            "table_reference": "table_350_investee_note",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:7:col:2025",
            "statement_type": OCRV2StatementType.NOTE.value,
            "basis": OCRV2Basis.UNKNOWN.value,
            "entity_scope": OCRV2EntityScope.INVESTEE.value,
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
    )


def _candidates() -> tuple[CandidateFact, ...]:
    return CandidateCapture().capture(_candidate_rows()).candidates


def test_registry_appends_and_returns_candidates_in_append_order() -> None:
    candidates = _candidates()
    registry = CandidateRegistry()

    result = registry.append(candidates[:3])

    assert result.candidates_registered == 3
    assert registry.all_candidates() == candidates[:3]
    assert registry.snapshot().candidates == candidates[:3]
    assert result.candidate_removals == 0
    assert result.canonical_selection_attempts == 0
    assert result.governance_logic_added is False
    assert result.selection_logic_added is False


def test_registry_retrieval_preserves_original_capture_metadata() -> None:
    candidates = _candidates()
    registry = CandidateRegistry(candidates)

    selected = registry.get_candidate(candidates[0].candidate_id)
    assert selected == candidates[0]
    assert selected is not None
    assert selected.raw_label == "Revenue"
    assert selected.basis == OCRV2Basis.CONSOLIDATED.value
    assert selected.entity_scope == OCRV2EntityScope.ISSUER.value
    assert selected.provenance.locator == "row:3:col:2025"

    page_candidates = registry.candidates_for_page(292)
    assert page_candidates == (candidates[0],)


def test_exact_duplicates_are_suppressed_without_counting_as_removals() -> None:
    candidate = _candidates()[0]
    registry = CandidateRegistry()

    result = registry.append((candidate, candidate))

    assert result.candidates_registered == 1
    assert result.exact_duplicates_removed == 1
    assert result.candidate_removals == 0
    assert registry.all_candidates() == (candidate,)


def test_competing_candidates_are_retained_even_for_same_metric_year_and_value() -> None:
    candidates = _candidates()
    registry = CandidateRegistry(candidates)

    revenue_candidates = registry.candidates_for_label_year(
        raw_label="Revenue",
        value_year=2025,
    )

    assert len(revenue_candidates) == 3
    assert {candidate.table_reference for candidate in revenue_candidates} == {
        "table_292_consolidated_statement",
        "table_293_unconsolidated_statement",
        "table_166_financial_highlights",
    }
    assert len({candidate.candidate_id for candidate in revenue_candidates}) == 3
    assert registry.snapshot().candidates_registered == len(candidates)


def test_losing_candidate_classes_are_retained_without_governance_filtering() -> None:
    candidates = _candidates()
    registry = CandidateRegistry(candidates)
    retained = registry.all_candidates()

    assert {candidate.basis for candidate in retained} >= {
        OCRV2Basis.CONSOLIDATED.value,
        OCRV2Basis.UNCONSOLIDATED.value,
        OCRV2Basis.UNKNOWN.value,
    }
    assert {candidate.statement_type for candidate in retained} >= {
        OCRV2StatementType.PRIMARY_STATEMENT.value,
        OCRV2StatementType.NOTE.value,
        OCRV2StatementType.SUMMARY_TABLE.value,
        OCRV2StatementType.ANALYSIS_TABLE.value,
    }
    assert {candidate.entity_scope for candidate in retained} >= {
        OCRV2EntityScope.ISSUER.value,
        OCRV2EntityScope.INVESTEE.value,
    }


def test_provenance_is_complete_and_preserved() -> None:
    candidates = _candidates()
    registry = CandidateRegistry(candidates)

    assert all(candidate.provenance for candidate in registry.all_candidates())
    assert [
        candidate.provenance.model_dump(mode="json")
        for candidate in registry.all_candidates()
    ] == [candidate.provenance.model_dump(mode="json") for candidate in candidates]


def test_registry_is_deterministically_repeatable() -> None:
    candidates = _candidates()

    first = CandidateRegistry(candidates)
    second = CandidateRegistry(candidates)

    assert first.snapshot().deterministic_signature == (
        second.snapshot().deterministic_signature
    )
    assert first.snapshot().model_dump(mode="json") == (
        second.snapshot().model_dump(mode="json")
    )


def test_registry_audit_uses_current_registry_state_when_available() -> None:
    candidates = _candidates()[:2]
    registry = CandidateRegistry(candidates)

    audit = registry.build_audit()

    assert audit.candidates_registered == 2
    assert audit.exact_duplicates_removed == 0
    assert audit.provenance_coverage_percent == 100.0
    assert audit.candidate_removals == 0
    assert audit.canonical_selection_attempts == 0
    assert audit.integrity_violations == ()


def test_candidate_registry_audit_and_report_have_required_success_values() -> None:
    tmp_path = _workspace_tmp("candidate_registry")
    audit_path = tmp_path / "ocr_v2_candidate_registry_audit.json"
    report_path = tmp_path / "ocr_v2_phase2_report.json"

    report = CandidateRegistry().write_phase2_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["candidates_registered"] > 0
    assert audit["exact_duplicates_removed"] > 0
    assert audit["competing_candidates_retained"] > 0
    assert audit["provenance_coverage_percent"] == 100.0
    assert audit["candidate_removals"] == 0
    assert audit["canonical_selection_attempts"] == 0
    assert audit["integrity_violations"] == []
    assert report.phase == "P2"
    assert report.scope == "candidate_registry_only"
    assert report.candidates_registered == audit["candidates_registered"]
    assert report.governance_logic_added is False
    assert report.selection_logic_added is False
    assert report.integrity_audit_passed is True
