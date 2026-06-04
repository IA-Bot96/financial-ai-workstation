"""OCR V2 Phase P4 entity governance.

This module classifies candidate eligibility from captured entity-scope
metadata only. It does not implement canonical selection, workbook generation,
OCR-to-MSIL export, ranking, candidate scoring, authority assignment, or LLM
behavior.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_candidate_capture import UNKNOWN_CLASSIFICATION, CandidateFact
from .ocr_v2_candidate_registry import CandidateRegistry, CandidateRegistrySnapshot
from .ocr_v2_contracts import OCRV2EntityScope
from .ocr_v2_governance_models import GovernedCandidate
from .ocr_v2_scale_governance import ScaleGovernance
from .ocr_v2_statement_governance import (
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
)


class EntityGovernanceOutcome(str, Enum):
    """Frozen Phase P4 entity-governance outcomes."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class EntityGovernanceReason(str, Enum):
    """Frozen Phase P4 entity-governance reasons."""

    ISSUER_CANDIDATE = "issuer_candidate"
    SUBSIDIARY_CANDIDATE = "subsidiary_candidate"
    ASSOCIATE_CANDIDATE = "associate_candidate"
    JOINT_VENTURE_CANDIDATE = "joint_venture_candidate"
    INVESTEE_CANDIDATE = "investee_candidate"
    UNKNOWN_ENTITY_SCOPE = "unknown_entity_scope"
    AMBIGUOUS_ENTITY_SCOPE = "ambiguous_entity_scope"
    POLICY_REVIEW_REQUIRED = "policy_review_required"


class EntityGovernedCandidate(BaseModel):
    """A statement/scale-governed candidate plus entity governance metadata.

    The underlying candidate and earlier governance metadata are preserved
    exactly. This model is not a selected value and does not carry a canonical
    value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    governed_candidate: GovernedCandidate
    entity_governance_outcome: EntityGovernanceOutcome
    entity_governance_reason: EntityGovernanceReason
    candidate_removal_attempted: bool = False
    winner_selection_attempted: bool = False
    value_modification_attempted: bool = False
    canonical_values_produced: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_no_prohibited_behavior(self) -> "EntityGovernedCandidate":
        if self.candidate_removal_attempted:
            raise ValueError("Phase P4 entity governance cannot remove candidates.")
        if self.winner_selection_attempted:
            raise ValueError("Phase P4 entity governance cannot select winners.")
        if self.value_modification_attempted:
            raise ValueError("Phase P4 entity governance cannot modify values.")
        if self.canonical_values_produced:
            raise ValueError("Phase P4 entity governance cannot produce canonical values.")
        return self

    @property
    def candidate(self) -> CandidateFact:
        return self.governed_candidate.candidate

    @property
    def candidate_id(self) -> str:
        return self.governed_candidate.candidate_id

    @property
    def original_value(self) -> float | int | str:
        return self.governed_candidate.original_value

    @property
    def provenance(self) -> Any:
        return self.governed_candidate.provenance

    @property
    def page_number(self) -> int:
        return self.candidate.page_number

    @property
    def table_reference(self) -> str:
        return self.candidate.table_reference


class EntityGovernanceResult(BaseModel):
    """Entity-governance result for a batch of candidates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_governed_candidates: tuple[EntityGovernedCandidate, ...] = Field(
        default_factory=tuple
    )
    candidates_evaluated: int = Field(..., ge=0)
    eligible_candidates: int = Field(..., ge=0)
    ineligible_candidates: int = Field(..., ge=0)
    review_required_candidates: int = Field(..., ge=0)
    investee_candidates_detected: int = Field(..., ge=0)
    issuer_candidates_detected: int = Field(..., ge=0)
    candidate_removals: int = Field(default=0, ge=0)
    winner_selection_attempts: int = Field(default=0, ge=0)
    value_modification_attempts: int = Field(default=0, ge=0)
    canonical_values_produced: int = Field(default=0, ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_entity_result(self) -> "EntityGovernanceResult":
        if self.candidates_evaluated != len(self.entity_governed_candidates):
            raise ValueError(
                "candidates_evaluated must equal entity-governed candidate count."
            )
        if (
            self.eligible_candidates
            + self.ineligible_candidates
            + self.review_required_candidates
            != self.candidates_evaluated
        ):
            raise ValueError("entity governance counts must reconcile.")
        if self.candidate_removals:
            raise ValueError("EntityGovernance cannot remove candidates.")
        if self.winner_selection_attempts:
            raise ValueError("EntityGovernance cannot select winners.")
        if self.value_modification_attempts:
            raise ValueError("EntityGovernance cannot modify values.")
        if self.canonical_values_produced:
            raise ValueError("EntityGovernance cannot produce canonical values.")
        return self


class OCRV2EntityGovernanceAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P4 entity governance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates_evaluated: int = Field(..., ge=0)
    eligible_candidates: int = Field(..., ge=0)
    ineligible_candidates: int = Field(..., ge=0)
    review_required_candidates: int = Field(..., ge=0)
    investee_candidates_detected: int = Field(..., ge=0)
    issuer_candidates_detected: int = Field(..., ge=0)
    candidate_removals: int = Field(..., ge=0)
    winner_selection_attempts: int = Field(..., ge=0)
    value_modification_attempts: int = Field(..., ge=0)
    canonical_values_produced: int = Field(..., ge=0)
    regression_fixture_executed: bool
    regression_cases_executed: int = Field(..., ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase4Report(BaseModel):
    """OCR V2 Phase P4 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    audit_path: str
    candidates_evaluated: int = Field(..., ge=0)
    eligible_candidates: int = Field(..., ge=0)
    ineligible_candidates: int = Field(..., ge=0)
    review_required_candidates: int = Field(..., ge=0)
    investee_candidates_detected: int = Field(..., ge=0)
    issuer_candidates_detected: int = Field(..., ge=0)
    candidate_removals: int = Field(..., ge=0)
    winner_selection_attempts: int = Field(..., ge=0)
    value_modification_attempts: int = Field(..., ge=0)
    canonical_values_produced: int = Field(..., ge=0)
    regression_fixture_executed: bool
    regression_cases_executed: int = Field(..., ge=0)
    governance_logic_added: bool
    selection_logic_added: bool
    workbook_changes_added: bool
    ocr_to_msil_export_added: bool
    ranking_logic_added: bool
    candidate_scoring_added: bool
    authority_assignment_added: bool
    llm_logic_added: bool
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class EntityGovernance:
    """Deterministic issuer-only entity eligibility classifier."""

    def __init__(self, *, declared_basis: str = "unconsolidated") -> None:
        self.declared_basis = declared_basis

    def evaluate_candidate(
        self,
        candidate: CandidateFact | GovernedCandidate,
    ) -> EntityGovernedCandidate:
        """Classify one candidate without changing prior governance metadata."""

        governed_candidate = _as_governed_candidate(candidate, self.declared_basis)
        outcome, reason = _classify_entity_scope(governed_candidate.candidate.entity_scope)
        return EntityGovernedCandidate(
            governed_candidate=governed_candidate,
            entity_governance_outcome=outcome,
            entity_governance_reason=reason,
            candidate_removal_attempted=False,
            winner_selection_attempted=False,
            value_modification_attempted=False,
            canonical_values_produced=0,
        )

    def govern(
        self,
        candidates: (
            CandidateRegistry
            | CandidateRegistrySnapshot
            | Iterable[CandidateFact | GovernedCandidate]
        ),
    ) -> EntityGovernanceResult:
        """Entity-govern candidates while retaining every candidate."""

        entity_governed = tuple(
            self.evaluate_candidate(candidate)
            for candidate in _candidate_iterable(candidates, self.declared_basis)
        )
        result = EntityGovernanceResult(
            entity_governed_candidates=entity_governed,
            candidates_evaluated=len(entity_governed),
            eligible_candidates=sum(
                1
                for item in entity_governed
                if item.entity_governance_outcome == EntityGovernanceOutcome.ELIGIBLE
            ),
            ineligible_candidates=sum(
                1
                for item in entity_governed
                if item.entity_governance_outcome == EntityGovernanceOutcome.INELIGIBLE
            ),
            review_required_candidates=sum(
                1
                for item in entity_governed
                if item.entity_governance_outcome
                == EntityGovernanceOutcome.REVIEW_REQUIRED
            ),
            investee_candidates_detected=sum(
                1
                for item in entity_governed
                if item.candidate.entity_scope == OCRV2EntityScope.INVESTEE.value
            ),
            issuer_candidates_detected=sum(
                1
                for item in entity_governed
                if item.candidate.entity_scope == OCRV2EntityScope.ISSUER.value
            ),
            candidate_removals=0,
            winner_selection_attempts=0,
            value_modification_attempts=0,
            canonical_values_produced=0,
            integrity_violations=(),
        )
        return result.model_copy(update={"integrity_violations": _entity_violations(result)})

    def build_audit(
        self,
        candidates: (
            CandidateRegistry
            | CandidateRegistrySnapshot
            | Iterable[CandidateFact | GovernedCandidate]
            | None
        ) = None,
    ) -> OCRV2EntityGovernanceAudit:
        """Build the required entity-governance audit."""

        regression_count = 0
        if candidates is None:
            fixture = load_ocr_v2_regression_cases()
            raw_candidates = candidates_from_regression_cases(fixture)
            statement_governed = StatementGovernance(
                declared_basis=fixture["declared_basis"]
            ).govern(raw_candidates).governed_candidates
            candidates = ScaleGovernance().govern(statement_governed).governed_candidates
            regression_count = len(fixture["cases"])
        result = self.govern(candidates)
        return OCRV2EntityGovernanceAudit(
            candidates_evaluated=result.candidates_evaluated,
            eligible_candidates=result.eligible_candidates,
            ineligible_candidates=result.ineligible_candidates,
            review_required_candidates=result.review_required_candidates,
            investee_candidates_detected=result.investee_candidates_detected,
            issuer_candidates_detected=result.issuer_candidates_detected,
            candidate_removals=result.candidate_removals,
            winner_selection_attempts=result.winner_selection_attempts,
            value_modification_attempts=result.value_modification_attempts,
            canonical_values_produced=result.canonical_values_produced,
            regression_fixture_executed=regression_count > 0,
            regression_cases_executed=regression_count,
            integrity_violations=result.integrity_violations,
        )

    def write_entity_governance_audit(
        self,
        output_path: str | Path = "output/ocr_v2_entity_governance_audit.json",
    ) -> OCRV2EntityGovernanceAudit:
        """Persist the P4 entity-governance audit."""

        audit = self.build_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase4_report(
        self,
        *,
        audit_path: str | Path = "output/ocr_v2_entity_governance_audit.json",
        report_path: str | Path = "output/ocr_v2_phase4_report.json",
    ) -> OCRV2Phase4Report:
        """Write all required OCR V2 Phase P4 artifacts."""

        audit = self.write_entity_governance_audit(audit_path)
        report = OCRV2Phase4Report(
            phase="P4",
            scope="entity_governance_only",
            audit_path=str(audit_path),
            candidates_evaluated=audit.candidates_evaluated,
            eligible_candidates=audit.eligible_candidates,
            ineligible_candidates=audit.ineligible_candidates,
            review_required_candidates=audit.review_required_candidates,
            investee_candidates_detected=audit.investee_candidates_detected,
            issuer_candidates_detected=audit.issuer_candidates_detected,
            candidate_removals=audit.candidate_removals,
            winner_selection_attempts=audit.winner_selection_attempts,
            value_modification_attempts=audit.value_modification_attempts,
            canonical_values_produced=audit.canonical_values_produced,
            regression_fixture_executed=audit.regression_fixture_executed,
            regression_cases_executed=audit.regression_cases_executed,
            governance_logic_added=True,
            selection_logic_added=False,
            workbook_changes_added=False,
            ocr_to_msil_export_added=False,
            ranking_logic_added=False,
            candidate_scoring_added=False,
            authority_assignment_added=False,
            llm_logic_added=False,
            integrity_audit_passed=not audit.integrity_violations,
            integrity_violations=audit.integrity_violations,
        )
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report


def write_phase4_report(
    *,
    audit_path: str | Path = "output/ocr_v2_entity_governance_audit.json",
    report_path: str | Path = "output/ocr_v2_phase4_report.json",
) -> OCRV2Phase4Report:
    """Convenience wrapper for writing the P4 report."""

    return EntityGovernance().write_phase4_report(
        audit_path=audit_path,
        report_path=report_path,
    )


def _candidate_iterable(
    candidates: (
        CandidateRegistry
        | CandidateRegistrySnapshot
        | Iterable[CandidateFact | GovernedCandidate]
    ),
    declared_basis: str,
) -> tuple[CandidateFact | GovernedCandidate, ...]:
    if isinstance(candidates, CandidateRegistry):
        return candidates.all_candidates()
    if isinstance(candidates, CandidateRegistrySnapshot):
        return candidates.candidates
    return tuple(candidates)


def _as_governed_candidate(
    candidate: CandidateFact | GovernedCandidate,
    declared_basis: str,
) -> GovernedCandidate:
    if isinstance(candidate, GovernedCandidate):
        return candidate
    statement_governed = StatementGovernance(declared_basis=declared_basis).evaluate_candidate(
        candidate
    )
    return ScaleGovernance().evaluate_candidate(statement_governed)


def _classify_entity_scope(
    entity_scope: str,
) -> tuple[EntityGovernanceOutcome, EntityGovernanceReason]:
    scope = (entity_scope or "").strip()
    if scope == OCRV2EntityScope.ISSUER.value:
        return (
            EntityGovernanceOutcome.ELIGIBLE,
            EntityGovernanceReason.ISSUER_CANDIDATE,
        )
    if scope in {UNKNOWN_CLASSIFICATION, "UNKNOWN", ""}:
        return (
            EntityGovernanceOutcome.REVIEW_REQUIRED,
            EntityGovernanceReason.UNKNOWN_ENTITY_SCOPE,
        )
    if "ambiguous" in scope.lower():
        return (
            EntityGovernanceOutcome.REVIEW_REQUIRED,
            EntityGovernanceReason.AMBIGUOUS_ENTITY_SCOPE,
        )
    if scope == OCRV2EntityScope.SUBSIDIARY.value:
        return (
            EntityGovernanceOutcome.INELIGIBLE,
            EntityGovernanceReason.SUBSIDIARY_CANDIDATE,
        )
    if scope == OCRV2EntityScope.ASSOCIATE.value:
        return (
            EntityGovernanceOutcome.INELIGIBLE,
            EntityGovernanceReason.ASSOCIATE_CANDIDATE,
        )
    if scope == OCRV2EntityScope.JOINT_VENTURE.value:
        return (
            EntityGovernanceOutcome.INELIGIBLE,
            EntityGovernanceReason.JOINT_VENTURE_CANDIDATE,
        )
    if scope == OCRV2EntityScope.INVESTEE.value:
        return (
            EntityGovernanceOutcome.INELIGIBLE,
            EntityGovernanceReason.INVESTEE_CANDIDATE,
        )
    return (
        EntityGovernanceOutcome.REVIEW_REQUIRED,
        EntityGovernanceReason.POLICY_REVIEW_REQUIRED,
    )


def _entity_violations(
    result: EntityGovernanceResult,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if result.candidate_removals:
        violations.append(
            _violation(
                "candidate_removals",
                "EntityGovernance",
                "Entity governance removed candidates.",
            )
        )
    if result.winner_selection_attempts:
        violations.append(
            _violation(
                "winner_selection_attempts",
                "EntityGovernance",
                "Entity governance attempted winner selection.",
            )
        )
    if result.value_modification_attempts:
        violations.append(
            _violation(
                "value_modification_attempts",
                "EntityGovernance",
                "Entity governance attempted to modify values.",
            )
        )
    if result.canonical_values_produced:
        violations.append(
            _violation(
                "canonical_values_produced",
                "EntityGovernance",
                "Entity governance produced canonical values.",
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
    "EntityGovernance",
    "EntityGovernanceOutcome",
    "EntityGovernanceReason",
    "EntityGovernanceResult",
    "EntityGovernedCandidate",
    "OCRV2EntityGovernanceAudit",
    "OCRV2Phase4Report",
    "write_phase4_report",
]
