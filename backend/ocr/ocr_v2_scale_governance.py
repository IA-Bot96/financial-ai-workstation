"""OCR V2 Phase P3 scale governance.

This module evaluates captured source-scale metadata only. It does not infer
scale from magnitude, normalize values, modify values, select canonical values,
rank candidates, write workbooks, export to MSIL, or use LLM logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_governance_models import (
    GovernedCandidate,
    ScaleGovernanceOutcome,
    ScaleGovernanceReason,
)
from .ocr_v2_statement_governance import (
    StatementGovernance,
    candidates_from_regression_cases,
    load_ocr_v2_regression_cases,
)


class ScaleGovernanceResult(BaseModel):
    """Scale-governance result for a batch of governed candidates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    governed_candidates: tuple[GovernedCandidate, ...] = Field(default_factory=tuple)
    candidates_evaluated: int = Field(..., ge=0)
    scale_valid: int = Field(..., ge=0)
    scale_review_required: int = Field(..., ge=0)
    scale_unknown: int = Field(..., ge=0)
    normalization_attempts: int = Field(default=0, ge=0)
    scale_inference_attempts: int = Field(default=0, ge=0)
    candidate_removals: int = Field(default=0, ge=0)
    winner_selection_attempts: int = Field(default=0, ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_scale_result(self) -> "ScaleGovernanceResult":
        if self.candidates_evaluated != len(self.governed_candidates):
            raise ValueError("candidates_evaluated must equal governed candidate count.")
        if (
            self.scale_valid + self.scale_review_required + self.scale_unknown
            != self.candidates_evaluated
        ):
            raise ValueError("scale governance counts must reconcile.")
        if self.normalization_attempts:
            raise ValueError("ScaleGovernance cannot normalize values.")
        if self.scale_inference_attempts:
            raise ValueError("ScaleGovernance cannot infer scale.")
        if self.candidate_removals:
            raise ValueError("ScaleGovernance cannot remove candidates.")
        if self.winner_selection_attempts:
            raise ValueError("ScaleGovernance cannot select winners.")
        return self


class OCRV2ScaleGovernanceAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P3 scale governance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates_evaluated: int = Field(..., ge=0)
    scale_valid: int = Field(..., ge=0)
    scale_review_required: int = Field(..., ge=0)
    scale_unknown: int = Field(..., ge=0)
    normalization_attempts: int = Field(..., ge=0)
    scale_inference_attempts: int = Field(..., ge=0)
    candidate_removals: int = Field(..., ge=0)
    winner_selection_attempts: int = Field(..., ge=0)
    regression_fixture_executed: bool
    regression_cases_executed: int = Field(..., ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class ScaleGovernance:
    """Deterministic source-scale metadata classifier."""

    def evaluate_candidate(self, governed_candidate: GovernedCandidate) -> GovernedCandidate:
        """Classify one candidate's scale metadata without changing its value."""

        outcome, reason = _classify_scale(
            governed_candidate.candidate.source_scale,
            governed_candidate.candidate.source_unit,
        )
        return governed_candidate.model_copy(
            update={
                "scale_outcome": outcome,
                "scale_reason": reason,
                "normalization_attempted": False,
                "scale_inference_attempted": False,
            }
        )

    def govern(
        self,
        governed_candidates: Iterable[GovernedCandidate],
    ) -> ScaleGovernanceResult:
        """Evaluate scale metadata for every governed candidate."""

        governed = tuple(
            self.evaluate_candidate(candidate) for candidate in governed_candidates
        )
        return ScaleGovernanceResult(
            governed_candidates=governed,
            candidates_evaluated=len(governed),
            scale_valid=sum(
                1
                for item in governed
                if item.scale_outcome == ScaleGovernanceOutcome.SCALE_VALID
            ),
            scale_review_required=sum(
                1
                for item in governed
                if item.scale_outcome
                == ScaleGovernanceOutcome.SCALE_REVIEW_REQUIRED
            ),
            scale_unknown=sum(
                1
                for item in governed
                if item.scale_outcome == ScaleGovernanceOutcome.SCALE_UNKNOWN
            ),
            normalization_attempts=0,
            scale_inference_attempts=0,
            candidate_removals=0,
            winner_selection_attempts=0,
            integrity_violations=(),
        )

    def build_audit(
        self,
        governed_candidates: Iterable[GovernedCandidate] | None = None,
    ) -> OCRV2ScaleGovernanceAudit:
        """Build the required scale-governance audit."""

        if governed_candidates is None:
            regression_cases = load_ocr_v2_regression_cases()
            candidates = candidates_from_regression_cases(regression_cases)
            governed_candidates = StatementGovernance().govern(
                candidates
            ).governed_candidates
            regression_count = len(regression_cases["cases"])
        else:
            regression_count = 0
        result = self.govern(governed_candidates)
        violations = _scale_integrity_violations(result)
        return OCRV2ScaleGovernanceAudit(
            candidates_evaluated=result.candidates_evaluated,
            scale_valid=result.scale_valid,
            scale_review_required=result.scale_review_required,
            scale_unknown=result.scale_unknown,
            normalization_attempts=result.normalization_attempts,
            scale_inference_attempts=result.scale_inference_attempts,
            candidate_removals=result.candidate_removals,
            winner_selection_attempts=result.winner_selection_attempts,
            regression_fixture_executed=regression_count > 0,
            regression_cases_executed=regression_count,
            integrity_violations=violations,
        )

    def write_scale_governance_audit(
        self,
        output_path: str | Path = "output/ocr_v2_scale_governance_audit.json",
    ) -> OCRV2ScaleGovernanceAudit:
        """Persist the P3 scale-governance audit."""

        audit = self.build_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit


def _classify_scale(
    source_scale: str,
    source_unit: str,
) -> tuple[ScaleGovernanceOutcome, ScaleGovernanceReason]:
    scale = (source_scale or "").strip().lower()
    unit = (source_unit or "").strip().lower()
    if _is_missing_scale(scale) or _is_missing_scale(unit):
        return (
            ScaleGovernanceOutcome.SCALE_UNKNOWN,
            ScaleGovernanceReason.DECLARED_SCALE_MISSING,
        )
    if "conflict" in scale or "mixed" in scale:
        return (
            ScaleGovernanceOutcome.SCALE_REVIEW_REQUIRED,
            ScaleGovernanceReason.CONFLICTING_SCALE,
        )
    if any(token in scale for token in ("magnitude", "inferred", "estimated")):
        return (
            ScaleGovernanceOutcome.SCALE_REVIEW_REQUIRED,
            ScaleGovernanceReason.UNSUPPORTED_SCALE,
        )
    if _is_supported_scale(scale, unit):
        return (
            ScaleGovernanceOutcome.SCALE_VALID,
            ScaleGovernanceReason.DECLARED_SCALE_PRESENT,
        )
    return (
        ScaleGovernanceOutcome.SCALE_REVIEW_REQUIRED,
        ScaleGovernanceReason.UNSUPPORTED_SCALE,
    )


def _is_missing_scale(value: str) -> bool:
    return value in {"", "unknown", "none", "missing", "not_readable"}


def _is_supported_scale(scale: str, unit: str) -> bool:
    supported_scale_markers = {
        "source_header",
        "thousand",
        "thousands",
        "'000",
        "000",
        "million",
        "millions",
        "full",
        "percentage",
        "percent",
        "%",
        "per_share",
        "pkr",
    }
    supported_unit_markers = {"pkr", "rs", "rupee", "rupees", "%", "percent", "share"}
    return any(marker in scale for marker in supported_scale_markers) and any(
        marker in unit for marker in supported_unit_markers
    )


def _scale_integrity_violations(
    result: ScaleGovernanceResult,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if result.normalization_attempts:
        violations.append(
            _violation(
                "normalization_attempts",
                "ScaleGovernance",
                "Scale governance attempted normalization.",
            )
        )
    if result.scale_inference_attempts:
        violations.append(
            _violation(
                "scale_inference_attempts",
                "ScaleGovernance",
                "Scale governance attempted scale inference.",
            )
        )
    if result.candidate_removals:
        violations.append(
            _violation(
                "candidate_removals",
                "ScaleGovernance",
                "Scale governance removed candidates.",
            )
        )
    if result.winner_selection_attempts:
        violations.append(
            _violation(
                "winner_selection_attempts",
                "ScaleGovernance",
                "Scale governance attempted winner selection.",
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
    "OCRV2ScaleGovernanceAudit",
    "ScaleGovernance",
    "ScaleGovernanceResult",
]
