"""OCR V2 Phase P2 candidate registry.

This module persists and returns captured CandidateFact observations. It is
registry-only: it does not implement statement governance, entity governance,
scale governance, canonical selection, workbook export, ranking, or LLM logic.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_candidate_capture import CandidateCapture, CandidateFact
from .ocr_v2_contracts import OCRV2Basis, OCRV2EntityScope, OCRV2StatementType


class CandidateRegistryAppendResult(BaseModel):
    """Result of appending candidates into the registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates_registered: int = Field(..., ge=0)
    exact_duplicates_removed: int = Field(..., ge=0)
    competing_candidates_retained: int = Field(..., ge=0)
    candidate_removals: int = Field(default=0, ge=0)
    canonical_selection_attempts: int = Field(default=0, ge=0)
    governance_logic_added: bool = False
    selection_logic_added: bool = False
    deterministic_signature: str = Field(..., min_length=1)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_registry_append_result(self) -> "CandidateRegistryAppendResult":
        if self.candidate_removals != 0:
            raise ValueError("CandidateRegistry cannot remove candidates.")
        if self.canonical_selection_attempts != 0:
            raise ValueError("CandidateRegistry cannot attempt canonical selection.")
        if self.governance_logic_added:
            raise ValueError("governance logic is forbidden in P2.")
        if self.selection_logic_added:
            raise ValueError("selection logic is forbidden in P2.")
        return self


class CandidateRegistrySnapshot(BaseModel):
    """Immutable snapshot of registry contents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[CandidateFact, ...] = Field(default_factory=tuple)
    candidates_registered: int = Field(..., ge=0)
    deterministic_signature: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_snapshot_count(self) -> "CandidateRegistrySnapshot":
        if self.candidates_registered != len(self.candidates):
            raise ValueError("candidates_registered must equal len(candidates).")
        return self


class OCRV2CandidateRegistryAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates_registered: int = Field(..., ge=0)
    exact_duplicates_removed: int = Field(..., ge=0)
    competing_candidates_retained: int = Field(..., ge=0)
    provenance_coverage_percent: float = Field(..., ge=0, le=100)
    candidate_removals: int = Field(..., ge=0)
    canonical_selection_attempts: int = Field(..., ge=0)
    deterministic_signature: str = Field(..., min_length=1)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase2Report(BaseModel):
    """OCR V2 Phase P2 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    candidates_registered: int = Field(..., ge=0)
    governance_logic_added: bool
    selection_logic_added: bool
    audit_path: str
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class CandidateRegistry:
    """Append-only candidate registry with exact-duplicate suppression."""

    def __init__(self, candidates: Iterable[CandidateFact] | None = None) -> None:
        self._candidates: list[CandidateFact] = []
        self._exact_duplicate_keys: set[str] = set()
        self._exact_duplicates_removed = 0
        if candidates:
            self.append(candidates)

    def append(
        self,
        candidates: CandidateFact | Iterable[CandidateFact],
    ) -> CandidateRegistryAppendResult:
        """Append candidates, preserving all non-exact competing observations."""

        candidate_tuple = _candidate_tuple(candidates)
        for candidate in candidate_tuple:
            key = _exact_duplicate_key(candidate)
            if key in self._exact_duplicate_keys:
                self._exact_duplicates_removed += 1
                continue
            self._exact_duplicate_keys.add(key)
            self._candidates.append(candidate)
        return self._append_result()

    def all_candidates(self) -> tuple[CandidateFact, ...]:
        """Return all retained candidates in append order."""

        return tuple(self._candidates)

    def snapshot(self) -> CandidateRegistrySnapshot:
        """Return an immutable deterministic registry snapshot."""

        candidates = self.all_candidates()
        return CandidateRegistrySnapshot(
            candidates=candidates,
            candidates_registered=len(candidates),
            deterministic_signature=_registry_signature(candidates),
        )

    def get_candidate(self, candidate_id: str) -> CandidateFact | None:
        """Return the first candidate with the supplied id, if present."""

        for candidate in self._candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        return None

    def candidates_for_label_year(
        self,
        *,
        raw_label: str,
        value_year: int,
    ) -> tuple[CandidateFact, ...]:
        """Return candidates by original label and represented year."""

        return tuple(
            candidate
            for candidate in self._candidates
            if candidate.raw_label == raw_label and candidate.value_year == value_year
        )

    def candidates_for_page(self, page_number: int) -> tuple[CandidateFact, ...]:
        """Return candidates captured on one page."""

        return tuple(
            candidate
            for candidate in self._candidates
            if candidate.page_number == page_number
        )

    def build_audit(
        self,
        candidates: Iterable[CandidateFact] | None = None,
    ) -> OCRV2CandidateRegistryAudit:
        """Build the required registry audit."""

        if candidates is None and self._candidates:
            registry = self
        else:
            registry = CandidateRegistry()
            registry.append(candidates or _audit_fixture_candidates())
        snapshot = registry.snapshot()
        provenance_count = sum(
            1 for candidate in snapshot.candidates if candidate.provenance
        )
        competing_count = _competing_candidates_retained(snapshot.candidates)
        violations = _audit_integrity_violations(
            candidates=snapshot.candidates,
            candidate_removals=0,
            canonical_selection_attempts=0,
        )
        return OCRV2CandidateRegistryAudit(
            candidates_registered=snapshot.candidates_registered,
            exact_duplicates_removed=registry._exact_duplicates_removed,
            competing_candidates_retained=competing_count,
            provenance_coverage_percent=_percent(
                provenance_count,
                snapshot.candidates_registered,
            ),
            candidate_removals=0,
            canonical_selection_attempts=0,
            deterministic_signature=snapshot.deterministic_signature,
            integrity_violations=violations,
        )

    def write_candidate_registry_audit(
        self,
        output_path: str | Path = "output/ocr_v2_candidate_registry_audit.json",
    ) -> OCRV2CandidateRegistryAudit:
        """Persist the P2 candidate-registry audit."""

        audit = self.build_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase2_report(
        self,
        *,
        audit_path: str | Path = "output/ocr_v2_candidate_registry_audit.json",
        report_path: str | Path = "output/ocr_v2_phase2_report.json",
    ) -> OCRV2Phase2Report:
        """Write both required OCR V2 Phase P2 artifacts."""

        audit = self.write_candidate_registry_audit(audit_path)
        report = OCRV2Phase2Report(
            phase="P2",
            scope="candidate_registry_only",
            candidates_registered=audit.candidates_registered,
            governance_logic_added=False,
            selection_logic_added=False,
            audit_path=str(audit_path),
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

    def _append_result(self) -> CandidateRegistryAppendResult:
        candidates = self.all_candidates()
        return CandidateRegistryAppendResult(
            candidates_registered=len(candidates),
            exact_duplicates_removed=self._exact_duplicates_removed,
            competing_candidates_retained=_competing_candidates_retained(candidates),
            candidate_removals=0,
            canonical_selection_attempts=0,
            governance_logic_added=False,
            selection_logic_added=False,
            deterministic_signature=_registry_signature(candidates),
            integrity_violations=_audit_integrity_violations(
                candidates=candidates,
                candidate_removals=0,
                canonical_selection_attempts=0,
            ),
        )


def _candidate_tuple(
    candidates: CandidateFact | Iterable[CandidateFact],
) -> tuple[CandidateFact, ...]:
    if isinstance(candidates, CandidateFact):
        return (candidates,)
    return tuple(candidates)


def _exact_duplicate_key(candidate: CandidateFact) -> str:
    payload = {
        "candidate_id": candidate.candidate_id,
        "raw_value": candidate.raw_value,
        "page_number": candidate.page_number,
        "table_reference": candidate.table_reference,
        "provenance": candidate.provenance.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _registry_signature(candidates: tuple[CandidateFact, ...]) -> str:
    encoded = json.dumps(
        [candidate.model_dump(mode="json") for candidate in candidates],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _competing_candidates_retained(candidates: tuple[CandidateFact, ...]) -> int:
    grouped: dict[tuple[str, int], list[CandidateFact]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.raw_label, candidate.value_year)].append(candidate)
    return sum(len(group) for group in grouped.values() if len(group) > 1)


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 100.0
    return round(numerator / denominator * 100, 2)


def _audit_integrity_violations(
    *,
    candidates: tuple[CandidateFact, ...],
    candidate_removals: int,
    canonical_selection_attempts: int,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if candidate_removals:
        violations.append(
            _violation(
                "candidate_removals",
                "CandidateRegistry",
                "CandidateRegistry removed candidates.",
            )
        )
    if canonical_selection_attempts:
        violations.append(
            _violation(
                "canonical_selection_attempts",
                "CandidateRegistry",
                "CandidateRegistry attempted canonical selection.",
            )
        )
    for candidate in candidates:
        if not candidate.provenance:
            violations.append(
                _violation(
                    "provenance_required",
                    candidate.candidate_id,
                    "Candidate is missing provenance.",
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


def _audit_fixture_candidates() -> tuple[CandidateFact, ...]:
    capture = CandidateCapture()
    rows = (
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
            "raw_value": "52.53",
            "raw_label": "Earnings per share",
            "value_year": 2025,
            "page_number": 350,
            "table_reference": "table_350_investee_note",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:7:col:2025",
            "statement_type": OCRV2StatementType.NOTE.value,
            "basis": OCRV2Basis.UNKNOWN.value,
            "entity_scope": OCRV2EntityScope.INVESTEE.value,
            "source_scale": "source_header:PKR",
            "source_unit": "PKR",
        },
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
            "raw_value": "2,500,000",
            "raw_label": "Capital expenditure",
            "value_year": 2025,
            "page_number": 168,
            "table_reference": "table_168_capex_schedule",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:11:col:2025",
            "statement_type": OCRV2StatementType.SUPPORTING_SCHEDULE.value,
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
    )
    return tuple(capture.capture(rows).candidates)


__all__ = [
    "CandidateRegistry",
    "CandidateRegistryAppendResult",
    "CandidateRegistrySnapshot",
    "OCRV2CandidateRegistryAudit",
    "OCRV2Phase2Report",
]
