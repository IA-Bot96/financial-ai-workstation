"""OCR V2 Phase P3 statement governance.

This module classifies candidate eligibility from captured statement metadata
only. It does not implement canonical selection, entity governance, scale
normalization, workbook generation, OCR-to-MSIL export, ranking, candidate
scoring, or LLM behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_candidate_capture import CandidateCapture, CandidateFact
from .ocr_v2_contracts import OCRV2Basis, OCRV2StatementType
from .ocr_v2_governance_models import (
    GovernedCandidate,
    StatementGovernanceOutcome,
    StatementGovernanceReason,
)
from .ocr_v2_regression_fixture import (
    REGRESSION_CASES_PATH,
    candidate_rows_from_regression_cases,
    load_ocr_v2_regression_fixture,
)


class StatementGovernanceResult(BaseModel):
    """Statement-governance result for a batch of candidates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    governed_candidates: tuple[GovernedCandidate, ...] = Field(default_factory=tuple)
    candidates_evaluated: int = Field(..., ge=0)
    eligible_candidates: int = Field(..., ge=0)
    ineligible_candidates: int = Field(..., ge=0)
    review_required_candidates: int = Field(..., ge=0)
    candidate_removals: int = Field(default=0, ge=0)
    winner_selection_attempts: int = Field(default=0, ge=0)
    canonical_values_produced: int = Field(default=0, ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_statement_result(self) -> "StatementGovernanceResult":
        if self.candidates_evaluated != len(self.governed_candidates):
            raise ValueError("candidates_evaluated must equal governed candidate count.")
        if (
            self.eligible_candidates
            + self.ineligible_candidates
            + self.review_required_candidates
            != self.candidates_evaluated
        ):
            raise ValueError("statement governance counts must reconcile.")
        if self.candidate_removals:
            raise ValueError("StatementGovernance cannot remove candidates.")
        if self.winner_selection_attempts:
            raise ValueError("StatementGovernance cannot select winners.")
        if self.canonical_values_produced:
            raise ValueError("StatementGovernance cannot produce canonical values.")
        return self


class OCRV2StatementGovernanceAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P3 statement governance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates_evaluated: int = Field(..., ge=0)
    eligible_candidates: int = Field(..., ge=0)
    ineligible_candidates: int = Field(..., ge=0)
    review_required_candidates: int = Field(..., ge=0)
    candidate_removals: int = Field(..., ge=0)
    winner_selection_attempts: int = Field(..., ge=0)
    regression_fixture_executed: bool
    regression_cases_executed: int = Field(..., ge=0)
    canonical_values_produced: int = Field(..., ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase3Report(BaseModel):
    """OCR V2 Phase P3 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    statement_audit_path: str
    scale_audit_path: str
    regression_fixture_path: str
    regression_fixture_executed: bool
    regression_cases_executed: int = Field(..., ge=0)
    candidates_evaluated: int = Field(..., ge=0)
    candidate_removals: int = Field(..., ge=0)
    winner_selection_attempts: int = Field(..., ge=0)
    normalization_attempts: int = Field(..., ge=0)
    scale_inference_attempts: int = Field(..., ge=0)
    canonical_values_produced: int = Field(..., ge=0)
    selection_logic_added: bool
    entity_governance_added: bool
    ranking_logic_added: bool
    llm_logic_added: bool
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class StatementGovernance:
    """Deterministic statement eligibility classifier."""

    def __init__(self, declared_basis: str | OCRV2Basis = OCRV2Basis.UNCONSOLIDATED) -> None:
        self.declared_basis = _enum_value(declared_basis)

    def evaluate_candidate(self, candidate: CandidateFact) -> GovernedCandidate:
        """Classify one candidate without looking at its numeric value."""

        outcome, reason = self._classify(candidate)
        return GovernedCandidate(
            candidate=candidate,
            governance_outcome=outcome,
            governance_reason=reason,
            candidate_removal_attempted=False,
            winner_selection_attempted=False,
        )

    def govern(self, candidates: Iterable[CandidateFact]) -> StatementGovernanceResult:
        """Classify every candidate and retain every candidate."""

        governed = tuple(self.evaluate_candidate(candidate) for candidate in candidates)
        return StatementGovernanceResult(
            governed_candidates=governed,
            candidates_evaluated=len(governed),
            eligible_candidates=sum(
                1
                for item in governed
                if item.governance_outcome == StatementGovernanceOutcome.ELIGIBLE
            ),
            ineligible_candidates=sum(
                1
                for item in governed
                if item.governance_outcome == StatementGovernanceOutcome.INELIGIBLE
            ),
            review_required_candidates=sum(
                1
                for item in governed
                if item.governance_outcome
                == StatementGovernanceOutcome.REVIEW_REQUIRED
            ),
            candidate_removals=0,
            winner_selection_attempts=0,
            canonical_values_produced=0,
            integrity_violations=(),
        )

    def build_audit(
        self,
        candidates: Iterable[CandidateFact] | None = None,
    ) -> OCRV2StatementGovernanceAudit:
        """Build the required statement-governance audit."""

        if candidates is None:
            regression_cases = load_ocr_v2_regression_cases()
            candidates = candidates_from_regression_cases(regression_cases)
            regression_count = len(regression_cases["cases"])
        else:
            regression_count = 0
        result = self.govern(candidates)
        violations = _statement_integrity_violations(result)
        return OCRV2StatementGovernanceAudit(
            candidates_evaluated=result.candidates_evaluated,
            eligible_candidates=result.eligible_candidates,
            ineligible_candidates=result.ineligible_candidates,
            review_required_candidates=result.review_required_candidates,
            candidate_removals=result.candidate_removals,
            winner_selection_attempts=result.winner_selection_attempts,
            regression_fixture_executed=regression_count > 0,
            regression_cases_executed=regression_count,
            canonical_values_produced=result.canonical_values_produced,
            integrity_violations=violations,
        )

    def write_statement_governance_audit(
        self,
        output_path: str | Path = "output/ocr_v2_statement_governance_audit.json",
    ) -> OCRV2StatementGovernanceAudit:
        """Persist the P3 statement-governance audit."""

        audit = self.build_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def _classify(
        self,
        candidate: CandidateFact,
    ) -> tuple[StatementGovernanceOutcome, StatementGovernanceReason]:
        statement_type = candidate.statement_type
        basis = candidate.basis

        if statement_type == OCRV2StatementType.ANALYSIS_TABLE.value:
            return (
                StatementGovernanceOutcome.INELIGIBLE,
                StatementGovernanceReason.ANALYSIS_TABLE,
            )
        if statement_type == OCRV2StatementType.SUMMARY_TABLE.value:
            return (
                StatementGovernanceOutcome.REVIEW_REQUIRED,
                StatementGovernanceReason.SUMMARY_TABLE,
            )
        if statement_type == OCRV2StatementType.NOTE.value:
            return (
                StatementGovernanceOutcome.REVIEW_REQUIRED,
                StatementGovernanceReason.NOTE_ONLY,
            )
        if statement_type not in {
            OCRV2StatementType.PRIMARY_STATEMENT.value,
            OCRV2StatementType.SUPPORTING_SCHEDULE.value,
        }:
            return (
                StatementGovernanceOutcome.REVIEW_REQUIRED,
                StatementGovernanceReason.UNSUPPORTED_STATEMENT,
            )
        if basis == OCRV2Basis.UNKNOWN.value or self.declared_basis == OCRV2Basis.UNKNOWN.value:
            return (
                StatementGovernanceOutcome.REVIEW_REQUIRED,
                StatementGovernanceReason.AMBIGUOUS_BASIS,
            )
        if basis != self.declared_basis:
            return (
                StatementGovernanceOutcome.INELIGIBLE,
                StatementGovernanceReason.AMBIGUOUS_BASIS,
            )
        return (
            StatementGovernanceOutcome.ELIGIBLE,
            StatementGovernanceReason.PRIMARY_STATEMENT,
        )


def write_phase3_report(
    *,
    statement_audit_path: str | Path = "output/ocr_v2_statement_governance_audit.json",
    scale_audit_path: str | Path = "output/ocr_v2_scale_governance_audit.json",
    report_path: str | Path = "output/ocr_v2_phase3_report.json",
) -> OCRV2Phase3Report:
    """Write all required OCR V2 Phase P3 artifacts."""

    from .ocr_v2_scale_governance import ScaleGovernance

    statement_audit = StatementGovernance().write_statement_governance_audit(
        statement_audit_path
    )
    scale_audit = ScaleGovernance().write_scale_governance_audit(scale_audit_path)
    violations = tuple(
        (*statement_audit.integrity_violations, *scale_audit.integrity_violations)
    )
    report = OCRV2Phase3Report(
        phase="P3",
        scope="statement_governance_and_scale_governance_only",
        statement_audit_path=str(statement_audit_path),
        scale_audit_path=str(scale_audit_path),
        regression_fixture_path=str(REGRESSION_CASES_PATH),
        regression_fixture_executed=(
            statement_audit.regression_fixture_executed
            and scale_audit.regression_fixture_executed
        ),
        regression_cases_executed=statement_audit.regression_cases_executed,
        candidates_evaluated=statement_audit.candidates_evaluated,
        candidate_removals=statement_audit.candidate_removals,
        winner_selection_attempts=statement_audit.winner_selection_attempts,
        normalization_attempts=scale_audit.normalization_attempts,
        scale_inference_attempts=scale_audit.scale_inference_attempts,
        canonical_values_produced=statement_audit.canonical_values_produced,
        selection_logic_added=False,
        entity_governance_added=False,
        ranking_logic_added=False,
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


def load_ocr_v2_regression_cases(
    path: str | Path = REGRESSION_CASES_PATH,
) -> dict[str, Any]:
    """Load the permanent OCR V2 regression fixture."""

    return load_ocr_v2_regression_fixture(path).model_dump(mode="python")


def candidates_from_regression_cases(regression_cases: dict[str, Any]) -> tuple[CandidateFact, ...]:
    """Create captured candidates from the regression fixture without selection."""

    rows = candidate_rows_from_regression_cases(regression_cases)
    return CandidateCapture().capture(rows).candidates


def _statement_integrity_violations(
    result: StatementGovernanceResult,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if result.candidate_removals:
        violations.append(
            _violation(
                "candidate_removals",
                "StatementGovernance",
                "Statement governance removed candidates.",
            )
        )
    if result.winner_selection_attempts:
        violations.append(
            _violation(
                "winner_selection_attempts",
                "StatementGovernance",
                "Statement governance attempted winner selection.",
            )
        )
    if result.canonical_values_produced:
        violations.append(
            _violation(
                "canonical_values_produced",
                "StatementGovernance",
                "Statement governance produced canonical values.",
            )
        )
    return tuple(violations)


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _violation(check_id: str, subject: str, message: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": "critical",
        "subject": subject,
        "message": message,
    }


__all__ = [
    "OCRV2Phase3Report",
    "OCRV2StatementGovernanceAudit",
    "REGRESSION_CASES_PATH",
    "StatementGovernance",
    "StatementGovernanceResult",
    "candidates_from_regression_cases",
    "load_ocr_v2_regression_cases",
    "write_phase3_report",
]
