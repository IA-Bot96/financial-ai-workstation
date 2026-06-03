"""Integrity checks for frozen MSIL Phase 0 contracts."""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from multi_source_intelligence.models import (
    AliasType,
    AuthorityClass,
    AuthorityMatrix,
    ClaimType,
    ContentClass,
    ContractIntegrityIssue,
    ContractIntegrityValidationResult,
    DivergenceStatus,
    DivergenceType,
    EntityScope,
    EntityStatus,
    EntityType,
    EventType,
    Horizon,
    MSILVersionPins,
    ProvenanceSchema,
    ProvenanceType,
    RelationshipType,
    ResolutionMethod,
    ReviewStatus,
    SourceType,
    TimeBasis,
    default_authority_matrix,
    default_provenance_schema,
    default_version_pins,
)


class ContractIntegrityValidator:
    """Validate Phase 0 enum, matrix, provenance, and version contracts."""

    def validate(
        self,
        *,
        authority_matrix: AuthorityMatrix | None = None,
        provenance_schema: ProvenanceSchema | None = None,
        version_pins: MSILVersionPins | None = None,
    ) -> ContractIntegrityValidationResult:
        """Run all deterministic Phase 0 integrity checks."""

        authority_matrix = authority_matrix or default_authority_matrix()
        provenance_schema = provenance_schema or default_provenance_schema()
        version_pins = version_pins or default_version_pins()

        checks_executed: list[str] = []
        issues: list[ContractIntegrityIssue] = []

        enum_counts = self._enum_counts()
        checks_executed.append("enum_values_unique")
        issues.extend(self._validate_enum_uniqueness())

        checks_executed.append("content_class_split_complete")
        issues.extend(self._validate_content_class_split())

        checks_executed.append("authority_matrix_total_per_claim_type")
        issues.extend(self._validate_authority_matrix(authority_matrix))

        checks_executed.append("provenance_schema_totality")
        issues.extend(self._validate_provenance_schema(provenance_schema))

        checks_executed.append("version_pins_present")
        issues.extend(self._validate_version_pins(version_pins))

        return ContractIntegrityValidationResult(
            is_valid=not issues,
            issues=tuple(issues),
            checks_executed=tuple(checks_executed),
            enum_counts=enum_counts,
            authority_matrix_claim_types=len(authority_matrix.entries),
            provenance_schema_entries=len(provenance_schema.requirements),
            version_pin_count=len(version_pins.model_dump(exclude_none=True)),
        )

    def _enum_counts(self) -> dict[str, int]:
        return {
            enum_cls.__name__: len(tuple(enum_cls))
            for enum_cls in _enum_registry()
        }

    def _validate_enum_uniqueness(self) -> tuple[ContractIntegrityIssue, ...]:
        issues: list[ContractIntegrityIssue] = []
        for enum_cls in _enum_registry():
            values = [item.value for item in enum_cls]
            duplicates = {value for value in values if values.count(value) > 1}
            if duplicates:
                issues.append(
                    _issue(
                        check_id="enum_values_unique",
                        affected_contract=enum_cls.__name__,
                        message="Duplicate enum values: "
                        + ", ".join(sorted(duplicates)),
                    )
                )
        return tuple(issues)

    def _validate_content_class_split(self) -> tuple[ContractIntegrityIssue, ...]:
        required = {
            ContentClass.NUMERIC_CLAIM,
            ContentClass.NARRATIVE_CLAIM,
            ContentClass.CORPORATE_EVENT,
            ContentClass.MARKET_OBSERVATION,
        }
        missing = required - set(ContentClass)
        if missing:
            return (
                _issue(
                    check_id="content_class_split_complete",
                    affected_contract="ContentClass",
                    message="Missing content classes: "
                    + ", ".join(sorted(item.value for item in missing)),
                ),
            )
        return ()

    def _validate_authority_matrix(
        self,
        authority_matrix: AuthorityMatrix,
    ) -> tuple[ContractIntegrityIssue, ...]:
        issues: list[ContractIntegrityIssue] = []
        claim_types = [entry.claim_type for entry in authority_matrix.entries]
        missing = set(ClaimType) - set(claim_types)
        duplicates = {claim_type for claim_type in claim_types if claim_types.count(claim_type) > 1}
        if missing:
            issues.append(
                _issue(
                    check_id="authority_matrix_total_per_claim_type",
                    affected_contract="AuthorityMatrix",
                    message="Missing claim types: "
                    + ", ".join(sorted(item.value for item in missing)),
                )
            )
        if duplicates:
            issues.append(
                _issue(
                    check_id="authority_matrix_total_per_claim_type",
                    affected_contract="AuthorityMatrix",
                    message="Duplicate claim types: "
                    + ", ".join(sorted(item.value for item in duplicates)),
                )
            )
        for entry in authority_matrix.entries:
            if len(set(entry.authority_order)) != len(entry.authority_order):
                issues.append(
                    _issue(
                        check_id="authority_order_unique",
                        affected_contract=f"AuthorityMatrix.{entry.claim_type.value}",
                        message="Duplicate authority classes in ranking.",
                    )
                )
        rule_ids = {rule.rule_id for rule in authority_matrix.special_rules}
        if "news_media_corroboration_only" not in rule_ids:
            issues.append(
                _issue(
                    check_id="news_special_rule_present",
                    affected_contract="AuthorityMatrix.special_rules",
                    message="Missing news_media_corroboration_only special rule.",
                )
            )
        if "market_revealed_observation_only" not in rule_ids:
            issues.append(
                _issue(
                    check_id="market_special_rule_present",
                    affected_contract="AuthorityMatrix.special_rules",
                    message="Missing market_revealed_observation_only special rule.",
                )
            )
        return tuple(issues)

    def _validate_provenance_schema(
        self,
        provenance_schema: ProvenanceSchema,
    ) -> tuple[ContractIntegrityIssue, ...]:
        issues: list[ContractIntegrityIssue] = []
        provenance_types = [
            requirement.provenance_type
            for requirement in provenance_schema.requirements
        ]
        missing = set(ProvenanceType) - set(provenance_types)
        duplicates = {
            provenance_type
            for provenance_type in provenance_types
            if provenance_types.count(provenance_type) > 1
        }
        if missing:
            issues.append(
                _issue(
                    check_id="provenance_schema_totality",
                    affected_contract="ProvenanceSchema",
                    message="Missing provenance types: "
                    + ", ".join(sorted(item.value for item in missing)),
                )
            )
        if duplicates:
            issues.append(
                _issue(
                    check_id="provenance_schema_totality",
                    affected_contract="ProvenanceSchema",
                    message="Duplicate provenance types: "
                    + ", ".join(sorted(item.value for item in duplicates)),
                )
            )
        for requirement in provenance_schema.requirements:
            if (
                requirement.provenance_type != ProvenanceType.PDF_PAGE
                and requirement.provenance_type != ProvenanceType.NONE
                and not requirement.snapshot_required
            ):
                issues.append(
                    _issue(
                        check_id="non_pdf_snapshot_required",
                        affected_contract=(
                            f"ProvenanceSchema.{requirement.provenance_type.value}"
                        ),
                        message="Non-PDF provenance must require snapshot_ref.",
                    )
                )
            if requirement.provenance_type == ProvenanceType.NONE:
                if not requirement.forbidden_to_emit:
                    issues.append(
                        _issue(
                            check_id="none_provenance_forbidden",
                            affected_contract="ProvenanceSchema.NONE",
                            message="NONE provenance must be forbidden to emit.",
                        )
                    )
        return tuple(issues)

    def _validate_version_pins(
        self,
        version_pins: MSILVersionPins,
    ) -> tuple[ContractIntegrityIssue, ...]:
        missing = [
            name
            for name, value in version_pins.model_dump().items()
            if name != "taxonomy_version" and not value
        ]
        if missing:
            return (
                _issue(
                    check_id="version_pins_present",
                    affected_contract="MSILVersionPins",
                    message="Missing version pins: " + ", ".join(sorted(missing)),
                ),
            )
        return ()


def _enum_registry() -> Iterable[type[Enum]]:
    return (
        EntityType,
        EntityScope,
        AliasType,
        RelationshipType,
        EntityStatus,
        ResolutionMethod,
        ReviewStatus,
        ContentClass,
        SourceType,
        AuthorityClass,
        ClaimType,
        TimeBasis,
        Horizon,
        ProvenanceType,
        EventType,
        DivergenceType,
        DivergenceStatus,
    )


def _issue(
    *,
    check_id: str,
    affected_contract: str,
    message: str,
) -> ContractIntegrityIssue:
    return ContractIntegrityIssue(
        check_id=check_id,
        severity="critical",
        affected_contract=affected_contract,
        message=message,
    )


__all__ = ["ContractIntegrityValidator"]
