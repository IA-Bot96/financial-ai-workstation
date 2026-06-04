"""OCR V2 Phase P3 governance models.

These models carry governance classifications only. They do not select
canonical values, rank candidates, normalize values, perform entity governance,
write workbooks, export to MSIL, or use LLM logic.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_candidate_capture import CandidateFact


class StatementGovernanceOutcome(str, Enum):
    """Frozen Phase P3 statement-governance outcomes."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class StatementGovernanceReason(str, Enum):
    """Frozen Phase P3 statement-governance reasons."""

    PRIMARY_STATEMENT = "primary_statement"
    NOTE_ONLY = "note_only"
    ANALYSIS_TABLE = "analysis_table"
    SUMMARY_TABLE = "summary_table"
    UNSUPPORTED_STATEMENT = "unsupported_statement"
    AMBIGUOUS_BASIS = "ambiguous_basis"


class ScaleGovernanceOutcome(str, Enum):
    """Frozen Phase P3 scale-governance outcomes."""

    SCALE_VALID = "SCALE_VALID"
    SCALE_REVIEW_REQUIRED = "SCALE_REVIEW_REQUIRED"
    SCALE_UNKNOWN = "SCALE_UNKNOWN"


class ScaleGovernanceReason(str, Enum):
    """Frozen Phase P3 scale-governance reasons."""

    DECLARED_SCALE_PRESENT = "declared_scale_present"
    DECLARED_SCALE_MISSING = "declared_scale_missing"
    UNSUPPORTED_SCALE = "unsupported_scale"
    CONFLICTING_SCALE = "conflicting_scale"


class GovernedCandidate(BaseModel):
    """A captured candidate plus governance metadata.

    The original CandidateFact is preserved exactly. This model is not a
    canonical value and does not carry a selected value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: CandidateFact
    governance_outcome: StatementGovernanceOutcome
    governance_reason: StatementGovernanceReason
    scale_outcome: ScaleGovernanceOutcome = ScaleGovernanceOutcome.SCALE_UNKNOWN
    scale_reason: ScaleGovernanceReason = ScaleGovernanceReason.DECLARED_SCALE_MISSING
    candidate_removal_attempted: bool = False
    winner_selection_attempted: bool = False
    normalization_attempted: bool = False
    scale_inference_attempted: bool = False

    @model_validator(mode="after")
    def _validate_no_prohibited_behavior(self) -> "GovernedCandidate":
        if self.candidate_removal_attempted:
            raise ValueError("Phase P3 governance cannot remove candidates.")
        if self.winner_selection_attempted:
            raise ValueError("Phase P3 governance cannot select winners.")
        if self.normalization_attempted:
            raise ValueError("Phase P3 governance cannot normalize values.")
        if self.scale_inference_attempted:
            raise ValueError("Phase P3 governance cannot infer scale.")
        return self

    @property
    def candidate_id(self) -> str:
        return self.candidate.candidate_id

    @property
    def original_value(self) -> float | int | str:
        return self.candidate.raw_value

    @property
    def provenance(self) -> Any:
        return self.candidate.provenance


__all__ = [
    "GovernedCandidate",
    "ScaleGovernanceOutcome",
    "ScaleGovernanceReason",
    "StatementGovernanceOutcome",
    "StatementGovernanceReason",
]
