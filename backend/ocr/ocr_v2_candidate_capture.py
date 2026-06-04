"""OCR V2 Phase P1 candidate capture.

This module captures observed financial fact candidates only. It does not
implement a candidate registry, statement governance, entity governance, scale
governance, canonical selection, workbook export, ranking, or LLM behavior.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_contracts import (
    CandidateProvenanceContract,
    OCRV2Basis,
    OCRV2EntityScope,
    OCRV2StatementType,
    OCRV2VersionPins,
    default_ocr_v2_version_pins,
)


UNKNOWN_CLASSIFICATION = "unknown"


class CandidateFact(BaseModel):
    """One raw observed OCR V2 candidate fact.

    A CandidateFact is a captured observation. It is not normalized, selected,
    ranked, or canonical.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(..., min_length=1)
    raw_value: float | int | str
    raw_label: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    page_number: int = Field(..., gt=0)
    table_reference: str = Field(..., min_length=1)
    statement_type: str = Field(default=UNKNOWN_CLASSIFICATION, min_length=1)
    basis: str = Field(default=OCRV2Basis.UNKNOWN.value, min_length=1)
    entity_scope: str = Field(default=UNKNOWN_CLASSIFICATION, min_length=1)
    source_scale: str = Field(default=UNKNOWN_CLASSIFICATION, min_length=1)
    source_unit: str = Field(default=UNKNOWN_CLASSIFICATION, min_length=1)
    provenance: CandidateProvenanceContract
    version_pins: OCRV2VersionPins = Field(
        default_factory=default_ocr_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_capture_observation(self) -> "CandidateFact":
        if self.provenance.page != self.page_number:
            raise ValueError("candidate provenance page must match page_number.")
        if self.provenance.table_ref != self.table_reference:
            raise ValueError(
                "candidate provenance table_ref must match table_reference."
            )
        if self.statement_type not in _allowed_statement_types():
            raise ValueError("statement_type must be frozen enum value or unknown.")
        if self.basis not in _allowed_basis_values():
            raise ValueError("basis must be frozen enum value or unknown.")
        if self.entity_scope not in _allowed_entity_scopes():
            raise ValueError("entity_scope must be frozen enum value or unknown.")
        return self


class CandidateCaptureInput(BaseModel):
    """Input shape consumed by the capture-only component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_value: float | int | str
    raw_label: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    page_number: int = Field(..., gt=0)
    table_reference: str = Field(..., min_length=1)
    document_fingerprint: str = Field(..., min_length=1)
    locator: str = Field(..., min_length=1)
    statement_type: str | None = None
    basis: str | None = None
    entity_scope: str | None = None
    source_scale: str | None = None
    source_unit: str | None = None


class CandidateCaptureResult(BaseModel):
    """Result of capture-only candidate creation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[CandidateFact, ...] = Field(default_factory=tuple)
    candidates_captured: int = Field(..., ge=0)
    canonical_selection_attempts: int = Field(default=0, ge=0)
    discarded_candidates: int = Field(default=0, ge=0)
    selection_logic_added: bool = False
    governance_logic_added: bool = False
    deterministic_signature: str = Field(..., min_length=1)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_capture_result(self) -> "CandidateCaptureResult":
        if self.candidates_captured != len(self.candidates):
            raise ValueError("candidates_captured must equal len(candidates).")
        if self.canonical_selection_attempts != 0:
            raise ValueError("candidate capture cannot attempt canonical selection.")
        if self.discarded_candidates != 0:
            raise ValueError("candidate capture cannot discard competing candidates.")
        if self.selection_logic_added:
            raise ValueError("selection logic is forbidden in P1.")
        if self.governance_logic_added:
            raise ValueError("governance logic is forbidden in P1.")
        return self


class OCRV2CandidateCaptureAudit(BaseModel):
    """Audit payload required by OCR V2 Phase P1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates_captured: int = Field(..., ge=0)
    provenance_coverage_percent: float = Field(..., ge=0, le=100)
    candidates_with_unknown_basis: int = Field(..., ge=0)
    candidates_with_unknown_entity_scope: int = Field(..., ge=0)
    canonical_selection_attempts: int = Field(..., ge=0)
    discarded_candidates: int = Field(..., ge=0)
    deterministic_signature: str = Field(..., min_length=1)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase1Report(BaseModel):
    """OCR V2 Phase P1 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    candidates_created: int = Field(..., ge=0)
    selection_logic_added: bool
    governance_logic_added: bool
    audit_path: str
    integrity_audit_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class CandidateCapture:
    """Capture-only component for OCR V2 candidate facts."""

    def create_candidate(
        self,
        *,
        raw_value: float | int | str,
        raw_label: str,
        value_year: int,
        page_number: int,
        table_reference: str,
        document_fingerprint: str,
        locator: str,
        statement_type: str | OCRV2StatementType | None = None,
        basis: str | OCRV2Basis | None = None,
        entity_scope: str | OCRV2EntityScope | None = None,
        source_scale: str | None = None,
        source_unit: str | None = None,
    ) -> CandidateFact:
        """Create one raw candidate observation without inference or selection."""

        payload = {
            "raw_value": raw_value,
            "raw_label": raw_label,
            "value_year": value_year,
            "page_number": page_number,
            "table_reference": table_reference,
            "document_fingerprint": document_fingerprint,
            "locator": locator,
            "statement_type": _unknown_if_blank(_enum_value(statement_type)),
            "basis": _unknown_if_blank(_enum_value(basis), default=OCRV2Basis.UNKNOWN.value),
            "entity_scope": _unknown_if_blank(_enum_value(entity_scope)),
            "source_scale": _unknown_if_blank(source_scale),
            "source_unit": _unknown_if_blank(source_unit),
        }
        provenance = CandidateProvenanceContract(
            document_fingerprint=document_fingerprint,
            page=page_number,
            table_ref=table_reference,
            locator=locator,
        )
        return CandidateFact(
            candidate_id=_candidate_id(payload),
            raw_value=raw_value,
            raw_label=raw_label,
            value_year=value_year,
            page_number=page_number,
            table_reference=table_reference,
            statement_type=payload["statement_type"],
            basis=payload["basis"],
            entity_scope=payload["entity_scope"],
            source_scale=payload["source_scale"],
            source_unit=payload["source_unit"],
            provenance=provenance,
        )

    def capture(
        self,
        rows: Iterable[CandidateCaptureInput | Mapping[str, Any]],
    ) -> CandidateCaptureResult:
        """Capture every supplied row as a candidate observation."""

        candidates = tuple(self.create_candidate(**_input_payload(row)) for row in rows)
        return CandidateCaptureResult(
            candidates=candidates,
            candidates_captured=len(candidates),
            canonical_selection_attempts=0,
            discarded_candidates=0,
            selection_logic_added=False,
            governance_logic_added=False,
            deterministic_signature=_result_signature(candidates),
            integrity_violations=_integrity_violations(candidates),
        )

    def build_audit(
        self,
        rows: Iterable[CandidateCaptureInput | Mapping[str, Any]] | None = None,
    ) -> OCRV2CandidateCaptureAudit:
        """Build the required P1 capture audit."""

        result = self.capture(rows or _audit_fixture_rows())
        provenance_count = sum(1 for candidate in result.candidates if candidate.provenance)
        violations = tuple(
            (
                *result.integrity_violations,
                *_audit_integrity_violations(result),
            )
        )
        return OCRV2CandidateCaptureAudit(
            candidates_captured=result.candidates_captured,
            provenance_coverage_percent=_percent(
                provenance_count,
                result.candidates_captured,
            ),
            candidates_with_unknown_basis=sum(
                1 for candidate in result.candidates if candidate.basis == OCRV2Basis.UNKNOWN.value
            ),
            candidates_with_unknown_entity_scope=sum(
                1
                for candidate in result.candidates
                if candidate.entity_scope == UNKNOWN_CLASSIFICATION
            ),
            canonical_selection_attempts=result.canonical_selection_attempts,
            discarded_candidates=result.discarded_candidates,
            deterministic_signature=result.deterministic_signature,
            integrity_violations=violations,
        )

    def write_candidate_capture_audit(
        self,
        output_path: str | Path = "output/ocr_v2_candidate_capture_audit.json",
    ) -> OCRV2CandidateCaptureAudit:
        """Persist the P1 candidate-capture audit."""

        audit = self.build_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase1_report(
        self,
        *,
        audit_path: str | Path = "output/ocr_v2_candidate_capture_audit.json",
        report_path: str | Path = "output/ocr_v2_phase1_report.json",
    ) -> OCRV2Phase1Report:
        """Write both required OCR V2 Phase P1 artifacts."""

        audit = self.write_candidate_capture_audit(audit_path)
        report = OCRV2Phase1Report(
            phase="P1",
            scope="candidate_capture_only",
            candidates_created=audit.candidates_captured,
            selection_logic_added=False,
            governance_logic_added=False,
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


def _input_payload(row: CandidateCaptureInput | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(row, CandidateCaptureInput):
        return row.model_dump(mode="python")
    return CandidateCaptureInput.model_validate(dict(row)).model_dump(mode="python")


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _unknown_if_blank(value: Any, *, default: str = UNKNOWN_CLASSIFICATION) -> str:
    if value in (None, ""):
        return default
    return str(value)


def _allowed_statement_types() -> set[str]:
    return {item.value for item in OCRV2StatementType} | {UNKNOWN_CLASSIFICATION}


def _allowed_basis_values() -> set[str]:
    return {item.value for item in OCRV2Basis}


def _allowed_entity_scopes() -> set[str]:
    return {item.value for item in OCRV2EntityScope} | {UNKNOWN_CLASSIFICATION}


def _candidate_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"ocr_v2_candidate_{digest[:24]}"


def _result_signature(candidates: tuple[CandidateFact, ...]) -> str:
    encoded = json.dumps(
        [candidate.model_dump(mode="json") for candidate in candidates],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 100.0
    return round(numerator / denominator * 100, 2)


def _integrity_violations(candidates: tuple[CandidateFact, ...]) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate.provenance:
            violations.append(
                _violation(
                    "provenance_required",
                    candidate.candidate_id,
                    "Candidate is missing provenance.",
                )
            )
        if not candidate.raw_label:
            violations.append(
                _violation(
                    "raw_label_required",
                    candidate.candidate_id,
                    "Candidate is missing original label.",
                )
            )
    return tuple(violations)


def _audit_integrity_violations(
    result: CandidateCaptureResult,
) -> tuple[dict[str, Any], ...]:
    violations: list[dict[str, Any]] = []
    if result.canonical_selection_attempts:
        violations.append(
            _violation(
                "canonical_selection_attempts",
                "CandidateCapture",
                "Candidate capture attempted canonical selection.",
            )
        )
    if result.discarded_candidates:
        violations.append(
            _violation(
                "discarded_candidates",
                "CandidateCapture",
                "Candidate capture discarded candidates.",
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


def _audit_fixture_rows() -> tuple[dict[str, Any], ...]:
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
            "raw_value": "44.10",
            "raw_label": "Earnings per share",
            "value_year": 2024,
            "page_number": 292,
            "table_reference": "table_292_income_statement",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:38:col:2024",
            "statement_type": OCRV2StatementType.PRIMARY_STATEMENT.value,
            "basis": OCRV2Basis.UNCONSOLIDATED.value,
            "entity_scope": OCRV2EntityScope.ISSUER.value,
            "source_scale": "source_header:PKR",
            "source_unit": "PKR",
        },
        {
            "raw_value": "52.53",
            "raw_label": "EPS ratio summary",
            "value_year": 2025,
            "page_number": 166,
            "table_reference": "table_166_financial_ratios",
            "document_fingerprint": "fixture_lucky_2025",
            "locator": "row:12:col:2025",
            "statement_type": OCRV2StatementType.SUMMARY_TABLE.value,
            "basis": OCRV2Basis.UNKNOWN.value,
            "entity_scope": UNKNOWN_CLASSIFICATION,
            "source_scale": UNKNOWN_CLASSIFICATION,
            "source_unit": UNKNOWN_CLASSIFICATION,
        },
    )


__all__ = [
    "UNKNOWN_CLASSIFICATION",
    "CandidateCapture",
    "CandidateCaptureInput",
    "CandidateCaptureResult",
    "CandidateFact",
    "OCRV2CandidateCaptureAudit",
    "OCRV2Phase1Report",
]
