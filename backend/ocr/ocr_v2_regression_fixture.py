"""OCR V2 permanent regression fixture foundation.

This module loads and validates the machine-readable CV1-derived regression
oracle. It intentionally contains no governance logic, selection logic, OCR
extraction behavior, workbook behavior, ranking, or LLM behavior.
"""

from __future__ import annotations

import json
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


REGRESSION_CASES_PATH = Path(__file__).with_name("ocr_v2_regression_cases.json")

REQUIRED_CASE_IDS: tuple[str, ...] = (
    "revenue_2021_scale",
    "revenue_2024",
    "revenue_2025",
    "gross_profit_2024",
    "gross_profit_2025",
    "net_profit_2024",
    "net_profit_2025",
    "ocf_2025",
    "total_assets_2025",
    "total_equity_2025",
    "long_term_debt_2024",
    "revenue_note_vs_statement",
    "investee_contamination_case",
    "analysis_table_case",
    "summary_table_case",
)


class OCRV2RegressionFailureClass(str, Enum):
    """Allowed permanent OCR V2 regression fixture failure classes."""

    STATEMENT_BASIS = "statement_basis"
    STATEMENT_PRECEDENCE = "statement_precedence"
    SCALE_GOVERNANCE = "scale_governance"
    ANALYSIS_TABLE_CONTAMINATION = "analysis_table_contamination"
    NOTE_CONTAMINATION = "note_contamination"
    INVESTEE_CONTAMINATION = "investee_contamination"
    SUMMARY_TABLE_CONTAMINATION = "summary_table_contamination"
    SOURCE_SELECTION = "source_selection"


class OCRV2RegressionCandidate(BaseModel):
    """One candidate entry inside a regression case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str | int | float
    basis: str = Field(..., min_length=1)
    statement_type: str = Field(..., min_length=1)
    entity_scope: str = Field(..., min_length=1)
    source_scale: str = Field(..., min_length=1)
    source_unit: str = Field(..., min_length=1)
    page_number: int = Field(..., gt=0)
    provenance_reference: str = Field(..., min_length=1)


class OCRV2ExpectedGovernanceResult(BaseModel):
    """Fixture-level expected governance result.

    This is declarative oracle metadata only. It does not execute governance.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    correct_candidate_expected: str = Field(..., min_length=1)
    incorrect_candidate_expected: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_expected_values(self) -> "OCRV2ExpectedGovernanceResult":
        if self.correct_candidate_expected not in {"ELIGIBLE", "SCALE_VALID"}:
            raise ValueError("correct_candidate_expected is not an allowed oracle value.")
        if self.incorrect_candidate_expected not in {
            "INELIGIBLE",
            "REVIEW_REQUIRED",
            "SCALE_REVIEW_REQUIRED",
        }:
            raise ValueError("incorrect_candidate_expected is not an allowed oracle value.")
        return self


class OCRV2RegressionCase(BaseModel):
    """One permanent OCR V2 regression case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    failure_class: OCRV2RegressionFailureClass
    correct_candidate: OCRV2RegressionCandidate
    incorrect_candidate: OCRV2RegressionCandidate
    expected_governance_result: OCRV2ExpectedGovernanceResult
    verified_by: str = Field(..., min_length=1)
    verification_source: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_case_alignment(self) -> "OCRV2RegressionCase":
        if self.correct_candidate.provenance_reference == (
            self.incorrect_candidate.provenance_reference
        ):
            raise ValueError("correct and incorrect candidates need distinct provenance.")
        return self


class OCRV2RegressionFixture(BaseModel):
    """Permanent OCR V2 regression oracle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_version: str = Field(..., min_length=1)
    fixture_name: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    declared_basis: str = Field(..., min_length=1)
    evidence_sources: tuple[str, ...] = Field(..., min_length=1)
    cases: tuple[OCRV2RegressionCase, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_unique_case_ids(self) -> "OCRV2RegressionFixture":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("regression fixture contains duplicate case_id values.")
        return self


class OCRV2RegressionFixtureAudit(BaseModel):
    """Audit payload for the permanent OCR V2 regression fixture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    regression_case_count: int = Field(..., ge=0)
    verified_case_count: int = Field(..., ge=0)
    failure_class_breakdown: dict[str, int]
    missing_fields: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    missing_required_cases: tuple[str, ...] = Field(default_factory=tuple)
    duplicate_case_ids: tuple[str, ...] = Field(default_factory=tuple)
    deterministic_signature: str = Field(..., min_length=1)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


def load_ocr_v2_regression_fixture(
    path: str | Path = REGRESSION_CASES_PATH,
) -> OCRV2RegressionFixture:
    """Load and validate the permanent regression fixture deterministically."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return OCRV2RegressionFixture.model_validate(payload)


def build_ocr_v2_regression_fixture_audit(
    path: str | Path = REGRESSION_CASES_PATH,
) -> OCRV2RegressionFixtureAudit:
    """Validate the fixture and return a machine-readable audit."""

    raw_payload = json.loads(Path(path).read_text(encoding="utf-8"))
    missing_fields = tuple(_missing_field_records(raw_payload))
    duplicate_case_ids = _duplicate_case_ids(raw_payload)
    missing_required_cases = tuple(
        case_id
        for case_id in REQUIRED_CASE_IDS
        if case_id not in {case.get("case_id") for case in raw_payload.get("cases", [])}
    )
    violations: list[dict[str, Any]] = []
    fixture: OCRV2RegressionFixture | None = None
    try:
        fixture = OCRV2RegressionFixture.model_validate(raw_payload)
    except Exception as exc:  # pragma: no cover - exercised by audit payload.
        violations.append(
            _violation(
                "fixture_schema_validation",
                "ocr_v2_regression_cases.json",
                str(exc),
            )
        )
    if missing_fields:
        violations.append(
            _violation(
                "missing_fields",
                "ocr_v2_regression_cases.json",
                "Regression fixture has missing required fields.",
            )
        )
    if duplicate_case_ids:
        violations.append(
            _violation(
                "duplicate_case_ids",
                "ocr_v2_regression_cases.json",
                "Regression fixture has duplicate case_id values.",
            )
        )
    if missing_required_cases:
        violations.append(
            _violation(
                "missing_required_cases",
                "ocr_v2_regression_cases.json",
                "Regression fixture is missing required case IDs.",
            )
        )
    cases = fixture.cases if fixture else tuple()
    verified_case_count = sum(1 for case in cases if case.verified_by and case.verification_source)
    return OCRV2RegressionFixtureAudit(
        regression_case_count=len(cases),
        verified_case_count=verified_case_count,
        failure_class_breakdown=dict(
            sorted(Counter(case.failure_class.value for case in cases).items())
        ),
        missing_fields=missing_fields,
        missing_required_cases=missing_required_cases,
        duplicate_case_ids=duplicate_case_ids,
        deterministic_signature=_deterministic_signature(raw_payload),
        integrity_violations=tuple(violations),
    )


def write_ocr_v2_regression_fixture_audit(
    output_path: str | Path = "output/ocr_v2_regression_fixture_audit.json",
    fixture_path: str | Path = REGRESSION_CASES_PATH,
) -> OCRV2RegressionFixtureAudit:
    """Persist the permanent regression fixture audit."""

    audit = build_ocr_v2_regression_fixture_audit(fixture_path)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return audit


def candidate_rows_from_regression_cases(
    fixture: OCRV2RegressionFixture | dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Convert fixture candidates into P1 capture rows for downstream tests.

    This is adapter glue for tests and later phases; it does not classify,
    govern, select, normalize, or rank candidates.
    """

    if isinstance(fixture, dict):
        fixture = OCRV2RegressionFixture.model_validate(fixture)
    rows: list[dict[str, Any]] = []
    for case in fixture.cases:
        rows.append(_candidate_row(case, case.correct_candidate, "correct"))
        rows.append(_candidate_row(case, case.incorrect_candidate, "incorrect"))
    return tuple(rows)


def _candidate_row(
    case: OCRV2RegressionCase,
    candidate: OCRV2RegressionCandidate,
    role: str,
) -> dict[str, Any]:
    return {
        "raw_value": candidate.value,
        "raw_label": case.metric,
        "value_year": case.value_year,
        "page_number": candidate.page_number,
        "table_reference": f"{case.case_id}_{role}",
        "document_fingerprint": "fixture_lucky_cv1",
        "locator": candidate.provenance_reference,
        "statement_type": candidate.statement_type,
        "basis": candidate.basis,
        "entity_scope": candidate.entity_scope,
        "source_scale": candidate.source_scale,
        "source_unit": candidate.source_unit,
    }


def _missing_field_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    fixture_fields = (
        "fixture_version",
        "fixture_name",
        "entity_ref",
        "declared_basis",
        "evidence_sources",
        "cases",
    )
    for field in fixture_fields:
        if field not in payload:
            missing.append({"case_id": None, "field": field})
    case_fields = (
        "case_id",
        "metric",
        "value_year",
        "failure_class",
        "correct_candidate",
        "incorrect_candidate",
        "expected_governance_result",
        "verified_by",
        "verification_source",
    )
    candidate_fields = (
        "value",
        "basis",
        "statement_type",
        "entity_scope",
        "source_scale",
        "source_unit",
        "page_number",
        "provenance_reference",
    )
    expected_fields = ("correct_candidate_expected", "incorrect_candidate_expected")
    for index, case in enumerate(payload.get("cases", [])):
        case_id = case.get("case_id", f"index:{index}")
        for field in case_fields:
            if field not in case:
                missing.append({"case_id": case_id, "field": field})
        for candidate_name in ("correct_candidate", "incorrect_candidate"):
            candidate = case.get(candidate_name, {})
            for field in candidate_fields:
                if field not in candidate:
                    missing.append(
                        {
                            "case_id": case_id,
                            "field": f"{candidate_name}.{field}",
                        }
                    )
        expected = case.get("expected_governance_result", {})
        for field in expected_fields:
            if field not in expected:
                missing.append(
                    {
                        "case_id": case_id,
                        "field": f"expected_governance_result.{field}",
                    }
                )
    return missing


def _duplicate_case_ids(payload: dict[str, Any]) -> tuple[str, ...]:
    case_ids = [case.get("case_id") for case in payload.get("cases", [])]
    counts = Counter(case_ids)
    return tuple(sorted(case_id for case_id, count in counts.items() if count > 1))


def _deterministic_signature(payload: dict[str, Any]) -> str:
    import hashlib

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _violation(check_id: str, subject: str, message: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": "critical",
        "subject": subject,
        "message": message,
    }


__all__ = [
    "OCRV2ExpectedGovernanceResult",
    "OCRV2RegressionCandidate",
    "OCRV2RegressionCase",
    "OCRV2RegressionFailureClass",
    "OCRV2RegressionFixture",
    "OCRV2RegressionFixtureAudit",
    "REGRESSION_CASES_PATH",
    "REQUIRED_CASE_IDS",
    "build_ocr_v2_regression_fixture_audit",
    "candidate_rows_from_regression_cases",
    "load_ocr_v2_regression_fixture",
    "write_ocr_v2_regression_fixture_audit",
]
