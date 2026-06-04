"""OCR V2 Phase P5 canonical selection.

This module selects one canonical candidate from already-governed candidates.
It consumes statement, scale, and entity governance verdicts. It does not
perform governance, modify values, modify provenance, rank candidates, score
candidates, write workbooks, export to MSIL, assign authority, or use LLM logic.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_entity_governance import (
    EntityGovernance,
    EntityGovernanceOutcome,
    EntityGovernedCandidate,
)
from .ocr_v2_governance_models import (
    ScaleGovernanceOutcome,
    StatementGovernanceOutcome,
)
from .ocr_v2_scale_governance import ScaleGovernance
from .ocr_v2_statement_governance import (
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
)


class CanonicalSelectionStatus(str, Enum):
    """Frozen Phase P5 canonical selection statuses."""

    SELECTED = "selected"
    AMBIGUOUS = "ambiguity"
    NO_SELECTION = "no_selection"


class CanonicalSelectionReason(str, Enum):
    """Deterministic Phase P5 selection reasons."""

    SINGLE_CANDIDATE_AFTER_FILTERING = "single_candidate_after_filtering"
    AMBIGUOUS_MULTIPLE_EQUIVALENT_CANDIDATES = (
        "ambiguous_multiple_equivalent_candidates"
    )
    NO_ELIGIBLE_CANDIDATES = "no_eligible_candidates"


class CanonicalSelectionDecision(BaseModel):
    """One canonical-selection decision for a candidate group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CanonicalSelectionStatus
    selected_candidate_id: str | None = None
    selection_reason: CanonicalSelectionReason
    losing_candidate_ids: tuple[str, ...] = Field(default_factory=tuple)
    losing_candidate_reasons: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    ambiguity_candidate_ids: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_selection_decision(self) -> "CanonicalSelectionDecision":
        if self.status == CanonicalSelectionStatus.SELECTED and not self.selected_candidate_id:
            raise ValueError("selected decisions require selected_candidate_id.")
        if self.status != CanonicalSelectionStatus.SELECTED and self.selected_candidate_id:
            raise ValueError("non-selected decisions cannot carry selected_candidate_id.")
        if self.status == CanonicalSelectionStatus.AMBIGUOUS and not self.ambiguity_candidate_ids:
            raise ValueError("ambiguous decisions require ambiguity_candidate_ids.")
        return self


class CanonicalSelectionResult(BaseModel):
    """Canonical-selection result for a single metric/year candidate group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[EntityGovernedCandidate, ...] = Field(default_factory=tuple)
    decision: CanonicalSelectionDecision
    candidates_evaluated: int = Field(..., ge=0)
    candidate_removals: int = Field(default=0, ge=0)
    value_modification_attempts: int = Field(default=0, ge=0)
    provenance_modification_attempts: int = Field(default=0, ge=0)
    ranking_logic_used: bool = False
    candidate_scoring_used: bool = False
    llm_logic_used: bool = False
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_selection_result(self) -> "CanonicalSelectionResult":
        if self.candidates_evaluated != len(self.candidates):
            raise ValueError("candidates_evaluated must equal candidate count.")
        if self.candidate_removals:
            raise ValueError("CanonicalSelection cannot remove candidates.")
        if self.value_modification_attempts:
            raise ValueError("CanonicalSelection cannot modify values.")
        if self.provenance_modification_attempts:
            raise ValueError("CanonicalSelection cannot modify provenance.")
        if self.ranking_logic_used:
            raise ValueError("ranking logic is forbidden in P5.")
        if self.candidate_scoring_used:
            raise ValueError("candidate scoring is forbidden in P5.")
        if self.llm_logic_used:
            raise ValueError("LLM logic is forbidden in P5.")
        return self

    @property
    def selected_candidate(self) -> EntityGovernedCandidate | None:
        if not self.decision.selected_candidate_id:
            return None
        for candidate in self.candidates:
            if candidate.candidate_id == self.decision.selected_candidate_id:
                return candidate
        return None


class OCRV2CanonicalSelectionAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P5 canonical selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates_evaluated: int = Field(..., ge=0)
    canonical_values_selected: int = Field(..., ge=0)
    ambiguity_results: int = Field(..., ge=0)
    no_selection_results: int = Field(..., ge=0)
    regression_fixture_executed: bool
    regression_cases_executed: int = Field(..., ge=0)
    regression_cases_passed: int = Field(..., ge=0)
    regression_cases_failed: int = Field(..., ge=0)
    incorrect_candidates_selected: int = Field(..., ge=0)
    candidate_removals: int = Field(..., ge=0)
    value_modification_attempts: int = Field(..., ge=0)
    provenance_modification_attempts: int = Field(..., ge=0)
    ranking_logic_used: bool
    candidate_scoring_used: bool
    llm_logic_used: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase5Report(BaseModel):
    """OCR V2 Phase P5 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    audit_path: str
    candidates_evaluated: int = Field(..., ge=0)
    canonical_values_selected: int = Field(..., ge=0)
    ambiguity_results: int = Field(..., ge=0)
    no_selection_results: int = Field(..., ge=0)
    regression_cases_passed: int = Field(..., ge=0)
    regression_cases_failed: int = Field(..., ge=0)
    incorrect_candidates_selected: int = Field(..., ge=0)
    selection_logic_added: bool
    workbook_generation_added: bool
    ocr_to_msil_export_added: bool
    ranking_logic_added: bool
    candidate_scoring_added: bool
    authority_assignment_added: bool
    llm_logic_added: bool
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class CanonicalSelection:
    """Deterministic canonical selection over already-governed candidates."""

    def select(
        self,
        candidates: Iterable[EntityGovernedCandidate],
    ) -> CanonicalSelectionResult:
        """Select one candidate, return ambiguity, or return no selection."""

        candidate_tuple = tuple(candidates)
        decision = _selection_decision(candidate_tuple)
        result = CanonicalSelectionResult(
            candidates=candidate_tuple,
            decision=decision,
            candidates_evaluated=len(candidate_tuple),
            candidate_removals=0,
            value_modification_attempts=0,
            provenance_modification_attempts=0,
            ranking_logic_used=False,
            candidate_scoring_used=False,
            llm_logic_used=False,
            integrity_violations=(),
        )
        return result.model_copy(
            update={"integrity_violations": _selection_integrity_violations(result)}
        )

    def build_audit(
        self,
        selection_results: Iterable[CanonicalSelectionResult] | None = None,
    ) -> OCRV2CanonicalSelectionAudit:
        """Build the required canonical-selection audit."""

        regression_cases_executed = 0
        regression_cases_passed = 0
        regression_cases_failed = 0
        incorrect_candidates_selected = 0
        if selection_results is None:
            fixture = load_ocr_v2_regression_cases()
            regression_results = _execute_regression_oracle(self, fixture)
            selection_results = tuple(result for _, result in regression_results)
            regression_cases_executed = len(regression_results)
            for case, result in regression_results:
                correct_id = _case_candidate_id(result, f"{case['case_id']}_correct")
                incorrect_id = _case_candidate_id(result, f"{case['case_id']}_incorrect")
                selected_id = result.decision.selected_candidate_id
                if selected_id == correct_id:
                    regression_cases_passed += 1
                else:
                    regression_cases_failed += 1
                if selected_id and selected_id == incorrect_id:
                    incorrect_candidates_selected += 1
        results = tuple(selection_results)
        violations = tuple(
            violation
            for result in results
            for violation in result.integrity_violations
        )
        return OCRV2CanonicalSelectionAudit(
            candidates_evaluated=sum(result.candidates_evaluated for result in results),
            canonical_values_selected=sum(
                1
                for result in results
                if result.decision.status == CanonicalSelectionStatus.SELECTED
            ),
            ambiguity_results=sum(
                1
                for result in results
                if result.decision.status == CanonicalSelectionStatus.AMBIGUOUS
            ),
            no_selection_results=sum(
                1
                for result in results
                if result.decision.status == CanonicalSelectionStatus.NO_SELECTION
            ),
            regression_fixture_executed=regression_cases_executed > 0,
            regression_cases_executed=regression_cases_executed,
            regression_cases_passed=regression_cases_passed,
            regression_cases_failed=regression_cases_failed,
            incorrect_candidates_selected=incorrect_candidates_selected,
            candidate_removals=sum(result.candidate_removals for result in results),
            value_modification_attempts=sum(
                result.value_modification_attempts for result in results
            ),
            provenance_modification_attempts=sum(
                result.provenance_modification_attempts for result in results
            ),
            ranking_logic_used=any(result.ranking_logic_used for result in results),
            candidate_scoring_used=any(
                result.candidate_scoring_used for result in results
            ),
            llm_logic_used=any(result.llm_logic_used for result in results),
            integrity_violations=violations,
        )

    def write_canonical_selection_audit(
        self,
        output_path: str | Path = "output/ocr_v2_canonical_selection_audit.json",
    ) -> OCRV2CanonicalSelectionAudit:
        """Persist the P5 canonical-selection audit."""

        audit = self.build_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase5_report(
        self,
        *,
        audit_path: str | Path = "output/ocr_v2_canonical_selection_audit.json",
        report_path: str | Path = "output/ocr_v2_phase5_report.json",
    ) -> OCRV2Phase5Report:
        """Write all required OCR V2 Phase P5 artifacts."""

        audit = self.write_canonical_selection_audit(audit_path)
        violations = tuple(
            (
                *audit.integrity_violations,
                *_audit_integrity_violations(audit),
            )
        )
        report = OCRV2Phase5Report(
            phase="P5",
            scope="canonical_selection_only",
            audit_path=str(audit_path),
            candidates_evaluated=audit.candidates_evaluated,
            canonical_values_selected=audit.canonical_values_selected,
            ambiguity_results=audit.ambiguity_results,
            no_selection_results=audit.no_selection_results,
            regression_cases_passed=audit.regression_cases_passed,
            regression_cases_failed=audit.regression_cases_failed,
            incorrect_candidates_selected=audit.incorrect_candidates_selected,
            selection_logic_added=True,
            workbook_generation_added=False,
            ocr_to_msil_export_added=False,
            ranking_logic_added=False,
            candidate_scoring_added=False,
            authority_assignment_added=False,
            llm_logic_added=False,
            integrity_audit_passed=not violations,
            integrity_violations=violations,
        )
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report


def write_phase5_report(
    *,
    audit_path: str | Path = "output/ocr_v2_canonical_selection_audit.json",
    report_path: str | Path = "output/ocr_v2_phase5_report.json",
) -> OCRV2Phase5Report:
    """Convenience wrapper for writing the P5 report."""

    return CanonicalSelection().write_phase5_report(
        audit_path=audit_path,
        report_path=report_path,
    )


def _selection_decision(
    candidates: tuple[EntityGovernedCandidate, ...],
) -> CanonicalSelectionDecision:
    losing_reasons: dict[str, list[str]] = {candidate.candidate_id: [] for candidate in candidates}

    eligible_candidates: list[EntityGovernedCandidate] = []
    for candidate in candidates:
        statement_outcome = candidate.governed_candidate.governance_outcome
        entity_outcome = candidate.entity_governance_outcome
        if statement_outcome == StatementGovernanceOutcome.INELIGIBLE:
            losing_reasons[candidate.candidate_id].append(
                f"statement_ineligible:{candidate.governed_candidate.governance_reason.value}"
            )
            continue
        if entity_outcome == EntityGovernanceOutcome.INELIGIBLE:
            losing_reasons[candidate.candidate_id].append(
                f"entity_ineligible:{candidate.entity_governance_reason.value}"
            )
            continue
        eligible_candidates.append(candidate)

    if not eligible_candidates:
        return _decision(
            status=CanonicalSelectionStatus.NO_SELECTION,
            reason=CanonicalSelectionReason.NO_ELIGIBLE_CANDIDATES,
            selected_candidate_id=None,
            losing_reasons=losing_reasons,
            losing_candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
            ambiguity_candidate_ids=(),
        )

    fully_eligible = [
        candidate
        for candidate in eligible_candidates
        if candidate.governed_candidate.governance_outcome
        == StatementGovernanceOutcome.ELIGIBLE
        and candidate.entity_governance_outcome == EntityGovernanceOutcome.ELIGIBLE
    ]
    if fully_eligible:
        for candidate in eligible_candidates:
            if candidate not in fully_eligible:
                losing_reasons[candidate.candidate_id].append(
                    "lower_governance_eligibility:review_required"
                )
        eligible_candidates = fully_eligible

    scale_valid = [
        candidate
        for candidate in eligible_candidates
        if candidate.governed_candidate.scale_outcome == ScaleGovernanceOutcome.SCALE_VALID
    ]
    if scale_valid:
        for candidate in eligible_candidates:
            if candidate not in scale_valid:
                losing_reasons[candidate.candidate_id].append(
                    f"lower_scale_governance:{candidate.governed_candidate.scale_reason.value}"
                )
        eligible_candidates = scale_valid

    if len(eligible_candidates) == 1:
        selected = eligible_candidates[0]
        losing_candidate_ids = tuple(
            candidate.candidate_id
            for candidate in candidates
            if candidate.candidate_id != selected.candidate_id
        )
        return _decision(
            status=CanonicalSelectionStatus.SELECTED,
            reason=CanonicalSelectionReason.SINGLE_CANDIDATE_AFTER_FILTERING,
            selected_candidate_id=selected.candidate_id,
            losing_reasons=losing_reasons,
            losing_candidate_ids=losing_candidate_ids,
            ambiguity_candidate_ids=(),
        )

    return _decision(
        status=CanonicalSelectionStatus.AMBIGUOUS,
        reason=CanonicalSelectionReason.AMBIGUOUS_MULTIPLE_EQUIVALENT_CANDIDATES,
        selected_candidate_id=None,
        losing_reasons=losing_reasons,
        losing_candidate_ids=tuple(
            candidate_id for candidate_id, reasons in losing_reasons.items() if reasons
        ),
        ambiguity_candidate_ids=tuple(candidate.candidate_id for candidate in eligible_candidates),
    )


def _decision(
    *,
    status: CanonicalSelectionStatus,
    reason: CanonicalSelectionReason,
    selected_candidate_id: str | None,
    losing_reasons: dict[str, list[str]],
    losing_candidate_ids: tuple[str, ...],
    ambiguity_candidate_ids: tuple[str, ...],
) -> CanonicalSelectionDecision:
    return CanonicalSelectionDecision(
        status=status,
        selected_candidate_id=selected_candidate_id,
        selection_reason=reason,
        losing_candidate_ids=losing_candidate_ids,
        losing_candidate_reasons={
            candidate_id: tuple(reasons)
            for candidate_id, reasons in sorted(losing_reasons.items())
            if reasons
        },
        ambiguity_candidate_ids=ambiguity_candidate_ids,
    )


def _execute_regression_oracle(
    selector: CanonicalSelection,
    fixture: dict[str, Any],
) -> tuple[tuple[dict[str, Any], CanonicalSelectionResult], ...]:
    results: list[tuple[dict[str, Any], CanonicalSelectionResult]] = []
    for case in fixture["cases"]:
        case_fixture = {**fixture, "cases": [case]}
        raw_candidates = candidates_from_regression_cases(case_fixture)
        statement_governed = StatementGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(raw_candidates).governed_candidates
        scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
        entity_governed = EntityGovernance(
            declared_basis=fixture["declared_basis"]
        ).govern(scale_governed).entity_governed_candidates
        results.append((case, selector.select(entity_governed)))
    return tuple(results)


def _case_candidate_id(result: CanonicalSelectionResult, table_reference: str) -> str | None:
    for candidate in result.candidates:
        if candidate.table_reference == table_reference:
            return candidate.candidate_id
    return None


def _selection_integrity_violations(
    result: CanonicalSelectionResult,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if result.candidate_removals:
        violations.append(
            _violation(
                "candidate_removals",
                "CanonicalSelection",
                "Canonical selection removed candidates.",
            )
        )
    if result.value_modification_attempts:
        violations.append(
            _violation(
                "value_modification_attempts",
                "CanonicalSelection",
                "Canonical selection modified candidate values.",
            )
        )
    if result.provenance_modification_attempts:
        violations.append(
            _violation(
                "provenance_modification_attempts",
                "CanonicalSelection",
                "Canonical selection modified provenance.",
            )
        )
    if result.ranking_logic_used:
        violations.append(
            _violation("ranking_logic_used", "CanonicalSelection", "Ranking was used.")
        )
    if result.candidate_scoring_used:
        violations.append(
            _violation(
                "candidate_scoring_used",
                "CanonicalSelection",
                "Candidate scoring was used.",
            )
        )
    if result.llm_logic_used:
        violations.append(
            _violation("llm_logic_used", "CanonicalSelection", "LLM logic was used.")
        )
    return tuple(violations)


def _audit_integrity_violations(
    audit: OCRV2CanonicalSelectionAudit,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if audit.regression_fixture_executed and audit.regression_cases_failed:
        violations.append(
            _violation(
                "regression_cases_failed",
                "CanonicalSelection",
                "Regression oracle cases failed canonical selection.",
            )
        )
    if audit.incorrect_candidates_selected:
        violations.append(
            _violation(
                "incorrect_candidates_selected",
                "CanonicalSelection",
                "Verified-incorrect candidates were selected.",
            )
        )
    if audit.candidate_removals:
        violations.append(
            _violation(
                "candidate_removals",
                "CanonicalSelection",
                "Canonical selection removed candidates.",
            )
        )
    if audit.value_modification_attempts:
        violations.append(
            _violation(
                "value_modification_attempts",
                "CanonicalSelection",
                "Canonical selection modified values.",
            )
        )
    if audit.provenance_modification_attempts:
        violations.append(
            _violation(
                "provenance_modification_attempts",
                "CanonicalSelection",
                "Canonical selection modified provenance.",
            )
        )
    if audit.ranking_logic_used or audit.candidate_scoring_used or audit.llm_logic_used:
        violations.append(
            _violation(
                "prohibited_logic",
                "CanonicalSelection",
                "Ranking, scoring, or LLM logic was used.",
            )
        )
    return tuple(violations)


def _violation(check_id: str, subject: str, message: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": "critical",
        "subject": subject,
        "message": message,
    }


__all__ = [
    "CanonicalSelection",
    "CanonicalSelectionDecision",
    "CanonicalSelectionReason",
    "CanonicalSelectionResult",
    "CanonicalSelectionStatus",
    "OCRV2CanonicalSelectionAudit",
    "OCRV2Phase5Report",
    "write_phase5_report",
]
