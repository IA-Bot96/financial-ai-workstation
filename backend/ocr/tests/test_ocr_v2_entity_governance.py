"""Tests for OCR V2 Phase P4 entity governance only."""

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
    CandidateRegistry,
    EntityGovernance,
    EntityGovernanceOutcome,
    EntityGovernanceReason,
    OCRV2Basis,
    OCRV2EntityScope,
    OCRV2StatementType,
    ScaleGovernance,
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
    write_phase4_report,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _rows_for_entity_scopes(*scopes: str) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "raw_value": str(index + 1),
            "raw_label": f"Entity scope {scope}",
            "value_year": 2025,
            "page_number": 200 + index,
            "table_reference": f"entity_scope_{index}",
            "document_fingerprint": "fixture",
            "locator": f"row:{index}:col:1",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": scope,
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        }
        for index, scope in enumerate(scopes)
    )


def _scale_governed_from_rows(*rows: dict[str, object]):
    candidates = CandidateCapture().capture(rows).candidates
    statement_governed = StatementGovernance().govern(candidates).governed_candidates
    return ScaleGovernance().govern(statement_governed).governed_candidates


def test_entity_governance_classifies_issuer_and_non_issuer_scopes() -> None:
    governed = _scale_governed_from_rows(
        *_rows_for_entity_scopes(
            OCRV2EntityScope.ISSUER.value,
            OCRV2EntityScope.SUBSIDIARY.value,
            OCRV2EntityScope.ASSOCIATE.value,
            OCRV2EntityScope.JOINT_VENTURE.value,
            OCRV2EntityScope.INVESTEE.value,
        )
    )

    result = EntityGovernance().govern(governed)

    assert [item.entity_governance_outcome for item in result.entity_governed_candidates] == [
        EntityGovernanceOutcome.ELIGIBLE,
        EntityGovernanceOutcome.INELIGIBLE,
        EntityGovernanceOutcome.INELIGIBLE,
        EntityGovernanceOutcome.INELIGIBLE,
        EntityGovernanceOutcome.INELIGIBLE,
    ]
    assert [item.entity_governance_reason for item in result.entity_governed_candidates] == [
        EntityGovernanceReason.ISSUER_CANDIDATE,
        EntityGovernanceReason.SUBSIDIARY_CANDIDATE,
        EntityGovernanceReason.ASSOCIATE_CANDIDATE,
        EntityGovernanceReason.JOINT_VENTURE_CANDIDATE,
        EntityGovernanceReason.INVESTEE_CANDIDATE,
    ]
    assert result.issuer_candidates_detected == 1
    assert result.investee_candidates_detected == 1


def test_entity_governance_unknown_scope_requires_review() -> None:
    governed = _scale_governed_from_rows(
        *_rows_for_entity_scopes("unknown"),
    )

    result = EntityGovernance().govern(governed)
    candidate = result.entity_governed_candidates[0]

    assert candidate.entity_governance_outcome == (
        EntityGovernanceOutcome.REVIEW_REQUIRED
    )
    assert candidate.entity_governance_reason == (
        EntityGovernanceReason.UNKNOWN_ENTITY_SCOPE
    )


def test_entity_governance_preserves_candidates_and_prior_governance_metadata() -> None:
    governed = _scale_governed_from_rows(
        *_rows_for_entity_scopes(
            OCRV2EntityScope.ISSUER.value,
            OCRV2EntityScope.INVESTEE.value,
        )
    )

    result = EntityGovernance().govern(governed)

    assert result.candidates_evaluated == len(governed)
    assert [item.governed_candidate for item in result.entity_governed_candidates] == list(
        governed
    )
    assert [item.original_value for item in result.entity_governed_candidates] == [
        item.original_value for item in governed
    ]
    assert all(item.provenance for item in result.entity_governed_candidates)
    assert result.candidate_removals == 0
    assert result.winner_selection_attempts == 0
    assert result.value_modification_attempts == 0
    assert result.canonical_values_produced == 0
    assert not any(hasattr(item, "canonical_value") for item in result.entity_governed_candidates)


def test_entity_governance_consumes_registry_candidates_without_selection() -> None:
    candidates = CandidateCapture().capture(
        _rows_for_entity_scopes(
            OCRV2EntityScope.ISSUER.value,
            OCRV2EntityScope.INVESTEE.value,
        )
    ).candidates
    registry = CandidateRegistry(candidates)

    from_registry = EntityGovernance().govern(registry)
    from_snapshot = EntityGovernance().govern(registry.snapshot())

    assert from_registry.candidates_evaluated == 2
    assert from_snapshot.candidates_evaluated == 2
    assert from_registry.model_dump(mode="json") == from_snapshot.model_dump(mode="json")


def test_entity_governance_is_deterministic() -> None:
    governed = _scale_governed_from_rows(
        *_rows_for_entity_scopes(
            OCRV2EntityScope.ISSUER.value,
            OCRV2EntityScope.INVESTEE.value,
            "unknown",
        )
    )
    governance = EntityGovernance()

    first = governance.govern(governed)
    second = governance.govern(governed)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_entity_governance_executes_regression_oracle_entity_cases() -> None:
    fixture = load_ocr_v2_regression_cases()
    candidates = candidates_from_regression_cases(fixture)
    statement_governed = StatementGovernance(
        declared_basis=fixture["declared_basis"]
    ).govern(candidates).governed_candidates
    scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates

    result = EntityGovernance().govern(scale_governed)
    by_table_ref = {
        item.table_reference: item for item in result.entity_governed_candidates
    }

    for case in fixture["cases"]:
        correct = by_table_ref[f"{case['case_id']}_correct"]
        incorrect = by_table_ref[f"{case['case_id']}_incorrect"]
        if case["correct_candidate"]["entity_scope"] == OCRV2EntityScope.ISSUER.value:
            assert correct.entity_governance_outcome == EntityGovernanceOutcome.ELIGIBLE
        if case["failure_class"] == "investee_contamination":
            assert incorrect.entity_governance_outcome == (
                EntityGovernanceOutcome.INELIGIBLE
            )
            assert incorrect.entity_governance_reason == (
                EntityGovernanceReason.INVESTEE_CANDIDATE
            )

    assert result.investee_candidates_detected >= 2
    assert result.candidate_removals == 0
    assert result.winner_selection_attempts == 0


def test_entity_governance_audit_has_required_success_values() -> None:
    tmp_path = _workspace_tmp("entity_governance")
    audit_path = tmp_path / "ocr_v2_entity_governance_audit.json"

    audit = EntityGovernance().write_entity_governance_audit(audit_path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["candidates_evaluated"] > 0
    assert payload["eligible_candidates"] > 0
    assert payload["ineligible_candidates"] > 0
    assert payload["investee_candidates_detected"] >= 2
    assert payload["issuer_candidates_detected"] > 0
    assert payload["candidate_removals"] == 0
    assert payload["winner_selection_attempts"] == 0
    assert payload["value_modification_attempts"] == 0
    assert payload["canonical_values_produced"] == 0
    assert payload["regression_fixture_executed"] is True
    assert payload["regression_cases_executed"] >= 15
    assert payload["integrity_violations"] == []
    assert audit.integrity_violations == ()


def test_phase4_report_writes_required_artifacts() -> None:
    tmp_path = _workspace_tmp("phase4")
    audit_path = tmp_path / "ocr_v2_entity_governance_audit.json"
    report_path = tmp_path / "ocr_v2_phase4_report.json"

    report = write_phase4_report(audit_path=audit_path, report_path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert audit_path.exists()
    assert payload["phase"] == "P4"
    assert payload["scope"] == "entity_governance_only"
    assert payload["candidates_evaluated"] > 0
    assert payload["candidate_removals"] == 0
    assert payload["winner_selection_attempts"] == 0
    assert payload["value_modification_attempts"] == 0
    assert payload["canonical_values_produced"] == 0
    assert payload["governance_logic_added"] is True
    assert payload["selection_logic_added"] is False
    assert payload["workbook_changes_added"] is False
    assert payload["ocr_to_msil_export_added"] is False
    assert payload["ranking_logic_added"] is False
    assert payload["candidate_scoring_added"] is False
    assert payload["authority_assignment_added"] is False
    assert payload["llm_logic_added"] is False
    assert payload["integrity_audit_passed"] is True
    assert report.integrity_violations == ()
