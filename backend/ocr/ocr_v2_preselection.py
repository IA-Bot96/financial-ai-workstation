"""OCR V2 governed-candidate preparation before canonical selection.

This module prepares already-governed candidates for the frozen canonical
selector. It does not perform governance, change values, change provenance,
write workbooks, export to MSIL, rank by confidence, score candidates, or use
LLM logic.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from .ocr_v2_contracts import OCRV2StatementType


SOURCE_PRECEDENCE_ORDER: tuple[str, ...] = (
    OCRV2StatementType.PRIMARY_STATEMENT.value,
    OCRV2StatementType.NOTE.value,
    OCRV2StatementType.SUPPORTING_SCHEDULE.value,
    OCRV2StatementType.SUMMARY_TABLE.value,
    OCRV2StatementType.ANALYSIS_TABLE.value,
)


class SourcePrecedenceConflict(BaseModel):
    """One metric/year group where lower-precedence sources were excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    value_year: int
    preferred_statement_type: str
    excluded_candidate_ids: tuple[str, ...] = Field(default_factory=tuple)
    excluded_statement_types: tuple[str, ...] = Field(default_factory=tuple)


class CandidateDuplicateGroup(BaseModel):
    """One exact duplicate group collapsed before canonical selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    value_year: int
    duplicate_count: int = Field(..., ge=2)
    retained_candidate_id: str
    duplicate_candidate_ids: tuple[str, ...] = Field(default_factory=tuple)
    retained_provenance: str
    duplicate_provenance_refs: tuple[str, ...] = Field(default_factory=tuple)


class CandidatePreselectionResult(BaseModel):
    """Prepared governed candidates plus diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    candidates: tuple[Any, ...] = Field(default_factory=tuple)
    input_candidates: int = Field(..., ge=0)
    output_candidates: int = Field(..., ge=0)
    source_precedence_conflicts: tuple[SourcePrecedenceConflict, ...] = Field(
        default_factory=tuple
    )
    duplicate_groups: tuple[CandidateDuplicateGroup, ...] = Field(default_factory=tuple)
    duplicates_detected: int = Field(..., ge=0)
    duplicates_collapsed: int = Field(..., ge=0)
    provenance_preserved: bool


def prepare_candidates_for_canonical_selection(
    candidates: Iterable[Any],
) -> CandidatePreselectionResult:
    """Apply deterministic source precedence and exact duplicate collapse."""

    candidate_tuple = tuple(candidates)
    deduped_candidates, duplicate_groups = _collapse_exact_duplicates(candidate_tuple)
    precedence_candidates, conflicts = _apply_source_precedence(deduped_candidates)
    duplicates_collapsed = sum(group.duplicate_count - 1 for group in duplicate_groups)
    return CandidatePreselectionResult(
        candidates=precedence_candidates,
        input_candidates=len(candidate_tuple),
        output_candidates=len(precedence_candidates),
        source_precedence_conflicts=conflicts,
        duplicate_groups=duplicate_groups,
        duplicates_detected=sum(group.duplicate_count for group in duplicate_groups),
        duplicates_collapsed=duplicates_collapsed,
        provenance_preserved=all(
            bool(group.retained_provenance) and bool(group.duplicate_provenance_refs)
            for group in duplicate_groups
        )
        if duplicate_groups
        else True,
    )


def _apply_source_precedence(
    candidates: tuple[Any, ...],
) -> tuple[tuple[Any, ...], tuple[SourcePrecedenceConflict, ...]]:
    grouped: dict[tuple[str, int], list[Any]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.candidate.raw_label, candidate.candidate.value_year)].append(
            candidate
        )

    retained: list[Any] = []
    conflicts: list[SourcePrecedenceConflict] = []
    for key in sorted(grouped, key=lambda item: (item[0], item[1])):
        group = grouped[key]
        precedence_group = [
            candidate for candidate in group if _candidate_can_enter_selection(candidate)
        ]
        if not precedence_group:
            precedence_group = group
        preferred = _preferred_statement_type(precedence_group)
        preferred_candidates = [
            candidate
            for candidate in group
            if candidate.candidate.statement_type == preferred
        ]
        excluded = [
            candidate
            for candidate in group
            if candidate.candidate.statement_type != preferred
        ]
        retained.extend(_sort_candidates(preferred_candidates))
        if excluded:
            conflicts.append(
                SourcePrecedenceConflict(
                    metric=key[0],
                    value_year=key[1],
                    preferred_statement_type=preferred,
                    excluded_candidate_ids=tuple(
                        candidate.candidate_id for candidate in _sort_candidates(excluded)
                    ),
                    excluded_statement_types=tuple(
                        sorted({candidate.candidate.statement_type for candidate in excluded})
                    ),
                )
            )
    return tuple(retained), tuple(conflicts)


def _collapse_exact_duplicates(
    candidates: tuple[Any, ...],
) -> tuple[tuple[Any, ...], tuple[CandidateDuplicateGroup, ...]]:
    grouped: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for candidate in candidates:
        grouped[_duplicate_key(candidate)].append(candidate)

    retained: list[Any] = []
    duplicate_groups: list[CandidateDuplicateGroup] = []
    for key in sorted(grouped, key=lambda item: tuple(str(part) for part in item)):
        group = _sort_candidates(grouped[key])
        retained.append(group[0])
        if len(group) <= 1:
            continue
        duplicate_groups.append(
            CandidateDuplicateGroup(
                metric=group[0].candidate.raw_label,
                value_year=group[0].candidate.value_year,
                duplicate_count=len(group),
                retained_candidate_id=group[0].candidate_id,
                duplicate_candidate_ids=tuple(
                    candidate.candidate_id for candidate in group[1:]
                ),
                retained_provenance=group[0].candidate.provenance.locator,
                duplicate_provenance_refs=tuple(
                    candidate.candidate.provenance.locator for candidate in group[1:]
                ),
            )
        )
    return tuple(retained), tuple(duplicate_groups)


def _preferred_statement_type(candidates: list[Any]) -> str:
    present = {candidate.candidate.statement_type for candidate in candidates}
    for statement_type in SOURCE_PRECEDENCE_ORDER:
        if statement_type in present:
            return statement_type
    return sorted(present)[0]


def _candidate_can_enter_selection(candidate: Any) -> bool:
    statement_outcome = getattr(
        candidate.governed_candidate.governance_outcome,
        "value",
        candidate.governed_candidate.governance_outcome,
    )
    entity_outcome = getattr(
        candidate.entity_governance_outcome,
        "value",
        candidate.entity_governance_outcome,
    )
    return statement_outcome != "INELIGIBLE" and entity_outcome != "INELIGIBLE"


def _duplicate_key(candidate: Any) -> tuple[Any, ...]:
    observed = candidate.candidate
    return (
        observed.raw_label,
        observed.value_year,
        _normalize_value(observed.raw_value),
        observed.page_number,
        observed.basis,
        observed.entity_scope,
        observed.source_scale,
        observed.source_unit,
    )


def _sort_candidates(candidates: Iterable[Any]) -> list[Any]:
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.candidate.table_reference,
            candidate.candidate.provenance.locator,
            candidate.candidate_id,
        ),
    )


def _normalize_value(value: Any) -> str:
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[, ]+", "", text)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"-{text}" if negative else text


__all__ = [
    "CandidateDuplicateGroup",
    "CandidatePreselectionResult",
    "SOURCE_PRECEDENCE_ORDER",
    "SourcePrecedenceConflict",
    "prepare_candidates_for_canonical_selection",
]
