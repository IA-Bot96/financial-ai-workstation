"""Integrity validation for the frozen OCR V2 Phase P0 foundation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .ocr_v2_contracts import (
    FROZEN_OCR_V2_CONTRACTS,
    FROZEN_OCR_V2_ENUM_VALUES,
    FROZEN_OCR_V2_OWNERSHIP_TABLE,
    FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS,
    FROZEN_OCR_V2_REQUIRED_FIELDS,
    FROZEN_OCR_V2_VERSION_PIN_FIELDS,
    OCR_V2_CONTRACT_MODEL_REGISTRY,
    OCRV2VersionPins,
    default_ocr_v2_version_pins,
)


EXPECTED_OCR_V2_CONTRACTS: tuple[str, ...] = (
    "CandidateFactContract",
    "CandidateRegistryContract",
    "StatementGovernanceContract",
    "EntityGovernanceContract",
    "ScaleGovernanceContract",
    "CanonicalSelectionContract",
    "OCRExportContract",
)

EXPECTED_OCR_V2_ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "statement_type": (
        "PRIMARY_STATEMENT",
        "SUPPORTING_SCHEDULE",
        "NOTE",
        "SUMMARY_TABLE",
        "ANALYSIS_TABLE",
    ),
    "basis": ("consolidated", "unconsolidated", "standalone", "unknown"),
    "entity_scope": (
        "ISSUER",
        "SUBSIDIARY",
        "ASSOCIATE",
        "JOINT_VENTURE",
        "INVESTEE",
    ),
    "scale_role": ("SOURCE_SCALE", "TARGET_SCALE", "NORMALIZED_SCALE"),
}

EXPECTED_OCR_V2_OWNERSHIP_TABLE: dict[str, str] = {
    "entity_identity": "MSIL",
    "candidate_capture": "OCR",
    "candidate_retention": "Candidate Registry",
    "canonical_choice": "Canonical Selection",
}


class OCRV2ContractIntegrityAudit(BaseModel):
    """Audit payload required for OCR V2 Phase P0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    contract_count: int = Field(..., ge=0)
    expected_contract_count: int = Field(..., ge=0)
    all_contracts_present: bool
    all_enums_present: bool
    all_version_pins_present: bool
    ownership_consistent: bool
    prohibited_behaviors_absent: bool
    contract_checks: dict[str, Any]
    enum_checks: dict[str, Any]
    version_pin_fields: tuple[str, ...]
    ownership_checks: dict[str, Any]
    prohibited_behavior_checks: dict[str, bool]
    required_field_integrity: dict[str, Any]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2Phase0Report(BaseModel):
    """OCR V2 Phase P0 implementation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    contracts_frozen: bool
    implementation_logic_added: bool
    integrity_audit_passed: bool
    audit_path: str
    contracts_materialized: tuple[str, ...]
    governance_config_materialized: bool
    version_pins: dict[str, str]
    prohibited_implementations: tuple[str, ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class OCRV2ContractIntegrityValidator:
    """Validate the OCR V2 P0 contract-only foundation."""

    def validate(
        self,
        *,
        version_pins: OCRV2VersionPins | None = None,
    ) -> OCRV2ContractIntegrityAudit:
        """Run deterministic integrity checks."""

        pins = version_pins or default_ocr_v2_version_pins()
        violations: list[dict[str, Any]] = []

        contract_checks = _contract_checks()
        if not contract_checks["passed"]:
            violations.append(
                _violation(
                    "contracts_present",
                    "FROZEN_OCR_V2_CONTRACTS",
                    "Frozen OCR V2 contract list does not match the required set.",
                    contract_checks["differences"],
                )
            )

        enum_checks = _enum_checks()
        for enum_name, check in enum_checks.items():
            if not check["passed"]:
                violations.append(
                    _violation(
                        "enums_present",
                        enum_name,
                        "Frozen enum values differ from OCR V2 contracts.",
                        check["differences"],
                    )
                )

        missing_pins = tuple(
            field
            for field in FROZEN_OCR_V2_VERSION_PIN_FIELDS
            if not getattr(pins, field, None)
        )
        if missing_pins:
            violations.append(
                _violation(
                    "version_pins_present",
                    "OCRV2VersionPins",
                    "Missing required OCR V2 version pins.",
                    missing_pins,
                )
            )

        ownership_checks = _ownership_checks()
        if not ownership_checks["passed"]:
            violations.append(
                _violation(
                    "ownership_consistency",
                    "FROZEN_OCR_V2_OWNERSHIP_TABLE",
                    "OCR V2 ownership table is inconsistent.",
                    ownership_checks["differences"],
                )
            )

        prohibited_absent = not any(FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS.values())
        if not prohibited_absent:
            violations.append(
                _violation(
                    "prohibited_behaviors_absent",
                    "FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS",
                    "A prohibited OCR V2 P0 implementation flag is enabled.",
                    FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS,
                )
            )

        required_field_checks = _required_field_checks()
        for contract_name, check in required_field_checks.items():
            if not check["passed"]:
                violations.append(
                    _violation(
                        "required_field_integrity",
                        contract_name,
                        "Contract is missing required frozen fields.",
                        check["missing_fields"],
                    )
                )

        return OCRV2ContractIntegrityAudit(
            validation_passed=not violations,
            contract_count=len(FROZEN_OCR_V2_CONTRACTS),
            expected_contract_count=len(EXPECTED_OCR_V2_CONTRACTS),
            all_contracts_present=contract_checks["passed"],
            all_enums_present=all(check["passed"] for check in enum_checks.values()),
            all_version_pins_present=not missing_pins,
            ownership_consistent=ownership_checks["passed"],
            prohibited_behaviors_absent=prohibited_absent,
            contract_checks=contract_checks,
            enum_checks=enum_checks,
            version_pin_fields=FROZEN_OCR_V2_VERSION_PIN_FIELDS,
            ownership_checks=ownership_checks,
            prohibited_behavior_checks=FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS,
            required_field_integrity=required_field_checks,
            integrity_violations=tuple(violations),
        )

    def write_audit(
        self,
        output_path: str | Path = "output/ocr_v2_contract_integrity_audit.json",
    ) -> OCRV2ContractIntegrityAudit:
        """Validate and persist the OCR V2 contract integrity audit."""

        audit = self.validate()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase0_report(
        self,
        *,
        audit_path: str | Path = "output/ocr_v2_contract_integrity_audit.json",
        report_path: str | Path = "output/ocr_v2_phase0_report.json",
    ) -> OCRV2Phase0Report:
        """Write both required OCR V2 Phase P0 artifacts."""

        audit = self.write_audit(audit_path)
        report = OCRV2Phase0Report(
            phase="P0",
            scope="foundations_only",
            contracts_frozen=True,
            implementation_logic_added=False,
            integrity_audit_passed=audit.validation_passed,
            audit_path=str(audit_path),
            contracts_materialized=FROZEN_OCR_V2_CONTRACTS,
            governance_config_materialized=True,
            version_pins=default_ocr_v2_version_pins().model_dump(mode="json"),
            prohibited_implementations=tuple(
                key.removesuffix("_implemented")
                for key in FROZEN_OCR_V2_PROHIBITED_BEHAVIOR_FLAGS
            ),
            integrity_violations=audit.integrity_violations,
        )
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report


def _contract_checks() -> dict[str, Any]:
    actual = FROZEN_OCR_V2_CONTRACTS
    expected = EXPECTED_OCR_V2_CONTRACTS
    missing = tuple(value for value in expected if value not in actual)
    unexpected = tuple(value for value in actual if value not in expected)
    return {
        "passed": actual == expected,
        "expected": expected,
        "actual": actual,
        "differences": {"missing": missing, "unexpected": unexpected},
    }


def _enum_checks() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for enum_name, expected in EXPECTED_OCR_V2_ENUM_VALUES.items():
        actual = FROZEN_OCR_V2_ENUM_VALUES.get(enum_name, ())
        missing = tuple(value for value in expected if value not in actual)
        unexpected = tuple(value for value in actual if value not in expected)
        checks[enum_name] = {
            "passed": actual == expected,
            "expected": expected,
            "actual": actual,
            "differences": {"missing": missing, "unexpected": unexpected},
        }
    return checks


def _ownership_checks() -> dict[str, Any]:
    actual = FROZEN_OCR_V2_OWNERSHIP_TABLE
    expected = EXPECTED_OCR_V2_OWNERSHIP_TABLE
    missing = tuple(key for key in expected if key not in actual)
    unexpected = tuple(key for key in actual if key not in expected)
    mismatched = {
        key: {"expected": expected[key], "actual": actual.get(key)}
        for key in expected
        if key in actual and actual[key] != expected[key]
    }
    return {
        "passed": not missing and not unexpected and not mismatched,
        "expected": expected,
        "actual": actual,
        "differences": {
            "missing": missing,
            "unexpected": unexpected,
            "mismatched": mismatched,
        },
    }


def _required_field_checks() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for contract_name, required_fields in FROZEN_OCR_V2_REQUIRED_FIELDS.items():
        model = OCR_V2_CONTRACT_MODEL_REGISTRY[contract_name]
        actual_fields = set(model.model_fields)
        missing = tuple(field for field in required_fields if field not in actual_fields)
        checks[contract_name] = {
            "passed": not missing,
            "required_fields": required_fields,
            "model_fields": tuple(sorted(actual_fields)),
            "missing_fields": missing,
        }
    return checks


def _violation(
    check_id: str,
    affected_contract: str,
    message: str,
    details: Any,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": "critical",
        "affected_contract": affected_contract,
        "message": message,
        "details": details,
    }


__all__ = [
    "EXPECTED_OCR_V2_CONTRACTS",
    "EXPECTED_OCR_V2_ENUM_VALUES",
    "EXPECTED_OCR_V2_OWNERSHIP_TABLE",
    "OCRV2ContractIntegrityAudit",
    "OCRV2ContractIntegrityValidator",
    "OCRV2Phase0Report",
]
