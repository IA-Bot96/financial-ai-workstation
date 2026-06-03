"""Integrity validation for the frozen Query Engine v2 contract substrate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.v2_contracts import (
    FROZEN_QUERY_V2_CONTRACTS,
    FROZEN_QUERY_V2_ENUM_VALUES,
    FROZEN_QUERY_V2_OWNERSHIP_TABLE,
    FROZEN_QUERY_V2_REQUIRED_FIELDS,
    FROZEN_QUERY_V2_VERSION_PIN_FIELDS,
    QUERY_V2_CONTRACT_MODEL_REGISTRY,
    QUERY_V2_CONTRACT_VERSION,
    QUERY_V2_RANKING_POLICY_VERSION,
    QueryV2CitationType,
    QueryV2IntentType,
    QueryV2RankingSignal,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
    QueryV2VersionPins,
    default_query_v2_version_pins,
)


EXPECTED_QUERY_V2_ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "intent_type": (
        "factual_lookup",
        "metric_lookup",
        "qualitative_analysis",
        "forecast_validation",
        "comparison",
        "timeline",
        "risk_analysis",
        "source_exploration",
        "ambiguous",
        "unsupported",
    ),
    "target_domain": ("msil", "ocr_via_msil", "qae", "fve"),
    "status": (
        "ANSWERED",
        "ANSWERED_WITH_WARNINGS",
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_CLARIFICATION",
        "UNSUPPORTED_INTENT",
    ),
    "citation_type": (
        "WORKBOOK_CELL",
        "PDF_PAGE",
        "ANNOUNCEMENT_REF",
        "REGULATORY_REF",
        "PAYOUT_REF",
        "MARKET_DATA_REF",
        "FUTURES_REF",
        "SECTOR_REF",
        "URL_SNAPSHOT",
        "NEWS_REF",
    ),
    "ranking_signals": (
        "authority_weight",
        "recency",
        "provenance_completeness",
        "corroboration_strength",
    ),
}

EXPECTED_QUERY_V2_OWNERSHIP_TABLE: dict[str, str] = {
    "intent_classification": "Query",
    "retrieval_planning": "Query",
    "source_selection": "Query",
    "ranking": "Query",
    "answer_assembly": "Query",
    "citation_rendering": "Query",
    "entity_resolution": "MSIL",
    "authority_assignment": "MSIL",
    "provenance": "MSIL",
    "corroboration": "MSIL",
    "divergence_detection": "MSIL",
    "theme_generation": "QAE",
    "numeric_validation": "FVE",
    "forecast_plausibility": "FVE",
    "numeric_integrity_status": "FVE",
    "divergence_interpretation": "OwningDomainEngine_QueryPresentsOnly",
}


class QueryV2ContractIntegrityAudit(BaseModel):
    """Audit payload for Query v2 Phase P0 contract integrity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    query_contract_version: str
    ranking_policy_version: str
    frozen_contract_count: int = Field(..., ge=0)
    expected_frozen_contract_count: int = Field(..., ge=0)
    all_frozen_enums_present: bool
    enum_checks: dict[str, dict[str, Any]]
    all_version_pins_present: bool
    version_pin_fields: tuple[str, ...]
    ownership_table_consistent: bool
    ownership_checks: dict[str, Any]
    required_field_integrity: dict[str, dict[str, Any]]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    checks_executed: tuple[str, ...] = Field(default_factory=tuple)


class QueryV2Phase0Report(BaseModel):
    """Implementation report for Query v2 Phase P0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    contracts_materialized: tuple[str, ...]
    frozen_contract_count: int = Field(..., ge=0)
    enums_materialized: dict[str, tuple[str, ...]]
    version_pins: dict[str, str]
    audit_path: str
    validation_passed: bool
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    prohibited_implementations: tuple[str, ...]


class QueryV2ContractIntegrityValidator:
    """Validate the frozen Query v2 P0 contract substrate."""

    def validate(
        self,
        *,
        version_pins: QueryV2VersionPins | None = None,
    ) -> QueryV2ContractIntegrityAudit:
        """Run deterministic contract integrity checks."""

        pins = version_pins or default_query_v2_version_pins()
        violations: list[dict[str, Any]] = []
        checks_executed: list[str] = []

        enum_checks = self._enum_checks()
        checks_executed.append("frozen_enum_values")
        for enum_name, check in enum_checks.items():
            if not check["passed"]:
                violations.append(
                    _violation(
                        "frozen_enum_values",
                        enum_name,
                        "Implemented enum values differ from frozen contract.",
                        check["differences"],
                    )
                )

        checks_executed.append("version_pins_present")
        missing_pins = [
            field
            for field in FROZEN_QUERY_V2_VERSION_PIN_FIELDS
            if not getattr(pins, field, None)
        ]
        if missing_pins:
            violations.append(
                _violation(
                    "version_pins_present",
                    "QueryV2VersionPins",
                    "Missing required version pins.",
                    missing_pins,
                )
            )

        checks_executed.append("ownership_table_consistency")
        ownership_checks = self._ownership_checks()
        if not ownership_checks["passed"]:
            violations.append(
                _violation(
                    "ownership_table_consistency",
                    "FROZEN_QUERY_V2_OWNERSHIP_TABLE",
                    "Ownership table does not match frozen contract.",
                    ownership_checks["differences"],
                )
            )

        checks_executed.append("required_field_integrity")
        required_field_checks = self._required_field_checks()
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

        checks_executed.append("frozen_contract_count")
        frozen_contract_count = len(FROZEN_QUERY_V2_CONTRACTS)
        expected_frozen_contract_count = 10
        if frozen_contract_count != expected_frozen_contract_count:
            violations.append(
                _violation(
                    "frozen_contract_count",
                    "FROZEN_QUERY_V2_CONTRACTS",
                    "Frozen contract count does not equal 10.",
                    {
                        "actual": frozen_contract_count,
                        "expected": expected_frozen_contract_count,
                    },
                )
            )

        return QueryV2ContractIntegrityAudit(
            validation_passed=not violations,
            query_contract_version=pins.query_contract_version,
            ranking_policy_version=pins.ranking_policy_version,
            frozen_contract_count=frozen_contract_count,
            expected_frozen_contract_count=expected_frozen_contract_count,
            all_frozen_enums_present=all(check["passed"] for check in enum_checks.values()),
            enum_checks=enum_checks,
            all_version_pins_present=not missing_pins,
            version_pin_fields=FROZEN_QUERY_V2_VERSION_PIN_FIELDS,
            ownership_table_consistent=ownership_checks["passed"],
            ownership_checks=ownership_checks,
            required_field_integrity=required_field_checks,
            integrity_violations=tuple(violations),
            checks_executed=tuple(checks_executed),
        )

    def write_audit(
        self,
        output_path: str | Path = "output/query_v2_contract_integrity_audit.json",
    ) -> QueryV2ContractIntegrityAudit:
        """Validate and persist the contract integrity audit."""

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
        audit_path: str | Path = "output/query_v2_contract_integrity_audit.json",
        report_path: str | Path = "output/query_v2_phase0_report.json",
    ) -> QueryV2Phase0Report:
        """Write both the P0 integrity audit and the P0 implementation report."""

        audit = self.write_audit(audit_path)
        report = QueryV2Phase0Report(
            phase="P0",
            scope="Contract substrate only",
            contracts_materialized=FROZEN_QUERY_V2_CONTRACTS,
            frozen_contract_count=len(FROZEN_QUERY_V2_CONTRACTS),
            enums_materialized=FROZEN_QUERY_V2_ENUM_VALUES,
            version_pins=default_query_v2_version_pins().model_dump(mode="json"),
            audit_path=str(audit_path),
            validation_passed=audit.validation_passed,
            integrity_violations=audit.integrity_violations,
            prohibited_implementations=(
                "intent_classification",
                "retrieval_planning",
                "ranking",
                "answer_assembly",
                "citation_rendering",
                "divergence_presentation_logic",
                "authority_presentation_logic",
                "llm_logic",
            ),
        )
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report

    @staticmethod
    def _enum_checks() -> dict[str, dict[str, Any]]:
        enum_sources = {
            "intent_type": tuple(item.value for item in QueryV2IntentType),
            "target_domain": tuple(item.value for item in QueryV2TargetDomain),
            "status": tuple(item.value for item in QueryV2ResponseStatus),
            "citation_type": tuple(item.value for item in QueryV2CitationType),
            "ranking_signals": tuple(item.value for item in QueryV2RankingSignal),
        }
        checks: dict[str, dict[str, Any]] = {}
        for enum_name, expected in EXPECTED_QUERY_V2_ENUM_VALUES.items():
            actual = enum_sources[enum_name]
            checks[enum_name] = {
                "passed": actual == expected,
                "expected": expected,
                "actual": actual,
                "differences": {
                    "missing": tuple(value for value in expected if value not in actual),
                    "unexpected": tuple(value for value in actual if value not in expected),
                },
            }
        checks["citation_type"]["none_forbidden"] = "NONE" not in enum_sources[
            "citation_type"
        ]
        if not checks["citation_type"]["none_forbidden"]:
            checks["citation_type"]["passed"] = False
        return checks

    @staticmethod
    def _ownership_checks() -> dict[str, Any]:
        missing = tuple(
            key
            for key in EXPECTED_QUERY_V2_OWNERSHIP_TABLE
            if key not in FROZEN_QUERY_V2_OWNERSHIP_TABLE
        )
        unexpected = tuple(
            key
            for key in FROZEN_QUERY_V2_OWNERSHIP_TABLE
            if key not in EXPECTED_QUERY_V2_OWNERSHIP_TABLE
        )
        mismatched = {
            key: {
                "expected": EXPECTED_QUERY_V2_OWNERSHIP_TABLE[key],
                "actual": FROZEN_QUERY_V2_OWNERSHIP_TABLE.get(key),
            }
            for key in EXPECTED_QUERY_V2_OWNERSHIP_TABLE
            if (
                key in FROZEN_QUERY_V2_OWNERSHIP_TABLE
                and FROZEN_QUERY_V2_OWNERSHIP_TABLE[key]
                != EXPECTED_QUERY_V2_OWNERSHIP_TABLE[key]
            )
        }
        return {
            "passed": not missing and not unexpected and not mismatched,
            "expected": EXPECTED_QUERY_V2_OWNERSHIP_TABLE,
            "actual": FROZEN_QUERY_V2_OWNERSHIP_TABLE,
            "differences": {
                "missing": missing,
                "unexpected": unexpected,
                "mismatched": mismatched,
            },
        }

    @staticmethod
    def _required_field_checks() -> dict[str, dict[str, Any]]:
        checks: dict[str, dict[str, Any]] = {}
        for contract_name, required_fields in FROZEN_QUERY_V2_REQUIRED_FIELDS.items():
            model = QUERY_V2_CONTRACT_MODEL_REGISTRY[contract_name]
            actual_fields = set(model.model_fields)
            missing_fields = tuple(
                field for field in required_fields if field not in actual_fields
            )
            checks[contract_name] = {
                "passed": not missing_fields,
                "required_fields": required_fields,
                "model_fields": tuple(sorted(actual_fields)),
                "missing_fields": missing_fields,
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
    "EXPECTED_QUERY_V2_ENUM_VALUES",
    "EXPECTED_QUERY_V2_OWNERSHIP_TABLE",
    "QueryV2ContractIntegrityAudit",
    "QueryV2ContractIntegrityValidator",
    "QueryV2Phase0Report",
]
