"""Authority assignment and matrix application for MSIL Phase 4."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from multi_source_intelligence.models import (
    AuthorityClass,
    AuthorityMatrix,
    ClaimType,
    ContentClass,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    SourceType,
    default_authority_matrix,
)


SOURCE_TYPE_ALIASES = {
    "annual_report": SourceType.ANNUAL_REPORT,
    "psx_announcement": SourceType.PSX_ANNOUNCEMENTS,
    "psx_announcements": SourceType.PSX_ANNOUNCEMENTS,
    "company_payout": SourceType.COMPANY_PAYOUTS,
    "company_payouts": SourceType.COMPANY_PAYOUTS,
    "secp_notice": SourceType.SECP_NOTICES,
    "secp_notices": SourceType.SECP_NOTICES,
    "sector_source": SourceType.SECTOR_SUMMARY,
    "sector_summary": SourceType.SECTOR_SUMMARY,
    "analyst_source": SourceType.ANALYSIS_REPORTS,
    "analysis_reports": SourceType.ANALYSIS_REPORTS,
    "news_source": SourceType.NEWS_SOURCES,
    "news_sources": SourceType.NEWS_SOURCES,
    "market_source": SourceType.MARKET_WATCH,
    "market_watch": SourceType.MARKET_WATCH,
    "futures_market_watch": SourceType.FUTURES_MARKET_WATCH,
}

SOURCE_AUTHORITY_CLASS = {
    SourceType.ANNUAL_REPORT: AuthorityClass.AUDITED_ISSUER,
    SourceType.PSX_ANNOUNCEMENTS: AuthorityClass.EXCHANGE_OFFICIAL,
    SourceType.COMPANY_PAYOUTS: AuthorityClass.EXCHANGE_OFFICIAL,
    SourceType.SECP_NOTICES: AuthorityClass.REGULATORY_INDEPENDENT,
    SourceType.MARKET_WATCH: AuthorityClass.MARKET_REVEALED,
    SourceType.FUTURES_MARKET_WATCH: AuthorityClass.MARKET_REVEALED,
    SourceType.SECTOR_SUMMARY: AuthorityClass.SECTOR_AGGREGATE,
    SourceType.COMPANY_OVERVIEW: AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
    SourceType.ANALYSIS_REPORTS: AuthorityClass.INDEPENDENT_OPINION,
    SourceType.NEWS_SOURCES: AuthorityClass.NEWS_MEDIA,
}


class AuthorityAssignmentRequest(BaseModel):
    """Request to assign source/content authority metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: SourceType
    content_class: ContentClass
    claim_type: ClaimType | None = Field(
        default=None,
        description="Optional caller-supplied claim type; still matrix-validated.",
    )
    verified: bool = Field(default=True)
    numeric_reference_only: bool = Field(default=False)
    source_independent_of_issuer: bool | None = Field(default=None)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_type", mode="before")
    @classmethod
    def _coerce_source_type(cls, value: SourceType | str) -> SourceType | str:
        """Accept frozen source names and common future-facing aliases."""

        if isinstance(value, SourceType):
            return value
        normalized = str(value).strip().lower()
        return SOURCE_TYPE_ALIASES.get(normalized, value)


class AuthorityAssignmentResult(BaseModel):
    """Authority assignment plus matrix validation details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: SourceType
    content_class: ContentClass
    claim_type: ClaimType
    authority_class: AuthorityClass
    creation_eligible: bool
    effective_rank: int | None = Field(
        default=None,
        description="Zero-based rank within the claim-type-specific matrix.",
    )
    standalone_fact_authority_allowed: bool
    applied_rules: tuple[str, ...] = Field(default_factory=tuple)
    invalid_mappings: tuple[str, ...] = Field(default_factory=tuple)
    is_valid: bool = Field(default=True)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "AuthorityAssignmentResult":
        if self.invalid_mappings and self.is_valid:
            raise ValueError("invalid_mappings require is_valid=False.")
        if not self.invalid_mappings and not self.is_valid:
            raise ValueError("is_valid=False requires invalid_mappings.")
        return self

    def to_classification(self) -> IntelligenceSignalClassification:
        """Return a signal classification from a valid assignment."""

        if not self.is_valid:
            raise ValueError("Cannot convert invalid authority assignment.")
        return IntelligenceSignalClassification(
            content_class=self.content_class,
            source_type=self.source_type,
            claim_type=self.claim_type,
            authority_class=self.authority_class,
            creation_eligible=self.creation_eligible,
            mapping_confidence=1.0,
            authority_confidence=1.0,
            independence_metadata={
                "authority_assignment_rules": list(self.applied_rules),
                "effective_authority_rank": self.effective_rank,
            },
        )


class AuthorityAssignmentService:
    """Apply the frozen claim-type-scoped authority matrix."""

    def __init__(self, authority_matrix: AuthorityMatrix | None = None) -> None:
        self._authority_matrix = authority_matrix or default_authority_matrix()

    @property
    def authority_matrix(self) -> AuthorityMatrix:
        return self._authority_matrix

    def assign(
        self,
        request: AuthorityAssignmentRequest | Mapping[str, Any],
    ) -> AuthorityAssignmentResult:
        """Assign and validate authority metadata for one source/content pair."""

        if not isinstance(request, AuthorityAssignmentRequest):
            request = AuthorityAssignmentRequest.model_validate(request)

        authority_class = SOURCE_AUTHORITY_CLASS.get(request.source_type)
        if authority_class is None:
            return _invalid_result(
                request=request,
                claim_type=request.claim_type or ClaimType.DESCRIPTIVE,
                authority_class=AuthorityClass.NEWS_MEDIA,
                reason=f"unsupported source_type: {request.source_type.value}",
            )

        claim_type = request.claim_type or self._default_claim_type(
            source_type=request.source_type,
            content_class=request.content_class,
        )
        applied_rules = [f"source_authority:{request.source_type.value}"]
        applied_rules.append(f"claim_type:{claim_type.value}")

        standalone_allowed = self._standalone_allowed(
            authority_class=authority_class,
            content_class=request.content_class,
        )
        creation_eligible = standalone_allowed and request.verified
        if request.numeric_reference_only:
            creation_eligible = False
            applied_rules.append("numeric_reference_only")
        if not request.verified:
            applied_rules.append("unverified_origin_creation_disabled")
        if not standalone_allowed:
            applied_rules.append("standalone_fact_authority_disallowed")

        effective_rank = self._authority_matrix.effective_rank(
            claim_type=claim_type,
            authority_class=authority_class,
        )
        invalid_mappings = self._validation_errors(
            source_type=request.source_type,
            content_class=request.content_class,
            claim_type=claim_type,
            authority_class=authority_class,
            creation_eligible=creation_eligible,
            standalone_allowed=standalone_allowed,
            effective_rank=effective_rank,
        )

        return AuthorityAssignmentResult(
            source_type=request.source_type,
            content_class=request.content_class,
            claim_type=claim_type,
            authority_class=authority_class,
            creation_eligible=creation_eligible,
            effective_rank=effective_rank,
            standalone_fact_authority_allowed=standalone_allowed,
            applied_rules=tuple(applied_rules),
            invalid_mappings=tuple(invalid_mappings),
            is_valid=not invalid_mappings,
        )

    def validate_classification(
        self,
        *,
        source_type: SourceType | str,
        content_class: ContentClass,
        claim_type: ClaimType,
        authority_class: AuthorityClass,
        creation_eligible: bool,
    ) -> AuthorityAssignmentResult:
        """Validate externally supplied authority metadata against the matrix."""

        request = AuthorityAssignmentRequest(
            source_type=source_type,
            content_class=content_class,
            claim_type=claim_type,
        )
        standalone_allowed = self._standalone_allowed(
            authority_class=authority_class,
            content_class=content_class,
        )
        effective_rank = self._authority_matrix.effective_rank(
            claim_type=claim_type,
            authority_class=authority_class,
        )
        invalid_mappings = self._validation_errors(
            source_type=request.source_type,
            content_class=content_class,
            claim_type=claim_type,
            authority_class=authority_class,
            creation_eligible=creation_eligible,
            standalone_allowed=standalone_allowed,
            effective_rank=effective_rank,
        )
        expected_authority = SOURCE_AUTHORITY_CLASS.get(request.source_type)
        if expected_authority != authority_class:
            invalid_mappings.append(
                "authority_class does not match source_type default authority."
            )

        return AuthorityAssignmentResult(
            source_type=request.source_type,
            content_class=content_class,
            claim_type=claim_type,
            authority_class=authority_class,
            creation_eligible=creation_eligible,
            effective_rank=effective_rank,
            standalone_fact_authority_allowed=standalone_allowed,
            applied_rules=("external_classification_validation",),
            invalid_mappings=tuple(invalid_mappings),
            is_valid=not invalid_mappings,
        )

    def assign_for_signal(self, signal: IntelligenceSignal) -> AuthorityAssignmentResult:
        """Assign authority metadata for an existing MSIL signal."""

        return self.assign(
            AuthorityAssignmentRequest(
                source_type=signal.classification.source_type,
                content_class=signal.content.content_class,
                claim_type=signal.classification.claim_type,
                verified=signal.metadata.verified,
                numeric_reference_only=bool(
                    signal.content.payload.get("numeric_reference_only", False)
                ),
                source_independent_of_issuer=(
                    signal.metadata.source_independent_of_issuer
                ),
            )
        )

    def audit_assignments(
        self,
        requests: Iterable[AuthorityAssignmentRequest | Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Evaluate assignments and return deterministic audit metrics."""

        results = [self.assign(request) for request in requests]
        invalid = [result for result in results if not result.is_valid]
        return {
            "audit_name": "authority_audit",
            "phase": "MSIL Phase 4",
            "signals_evaluated": len(results),
            "authority_distribution": dict(
                Counter(result.authority_class.value for result in results)
            ),
            "claim_type_distribution": dict(
                Counter(result.claim_type.value for result in results)
            ),
            "creation_eligible_distribution": dict(
                Counter(str(result.creation_eligible).lower() for result in results)
            ),
            "invalid_mappings": [
                result.model_dump(mode="json") for result in invalid
            ],
            "authority_coverage": {
                "source_types_supported": len(SOURCE_AUTHORITY_CLASS),
                "source_types_total": len(SourceType),
                "source_type_coverage_percent": round(
                    (len(SOURCE_AUTHORITY_CLASS) / len(SourceType)) * 100,
                    2,
                ),
                "claim_types_in_matrix": len(self._authority_matrix.entries),
                "claim_types_total": len(ClaimType),
            },
        }

    def audit_signals(self, signals: Iterable[IntelligenceSignal]) -> dict[str, Any]:
        """Audit authority assignment for existing signals."""

        return self.audit_assignments(
            [
                AuthorityAssignmentRequest(
                    source_type=signal.classification.source_type,
                    content_class=signal.content.content_class,
                    claim_type=signal.classification.claim_type,
                    verified=signal.metadata.verified,
                    numeric_reference_only=bool(
                        signal.content.payload.get("numeric_reference_only", False)
                    ),
                    source_independent_of_issuer=(
                        signal.metadata.source_independent_of_issuer
                    ),
                )
                for signal in signals
            ]
        )

    def _default_claim_type(
        self,
        *,
        source_type: SourceType,
        content_class: ContentClass,
    ) -> ClaimType:
        if source_type == SourceType.SECP_NOTICES:
            return ClaimType.REGULATORY_COMPLIANCE
        if source_type in {SourceType.PSX_ANNOUNCEMENTS, SourceType.COMPANY_PAYOUTS}:
            return ClaimType.CORPORATE_ACTION_FACT
        if source_type == SourceType.ANNUAL_REPORT:
            if content_class == ContentClass.NUMERIC_CLAIM:
                return ClaimType.AUDITED_FACT
            if content_class == ContentClass.CORPORATE_EVENT:
                return ClaimType.CORPORATE_ACTION_FACT
            return ClaimType.DESCRIPTIVE
        if source_type in {SourceType.MARKET_WATCH, SourceType.FUTURES_MARKET_WATCH}:
            return ClaimType.SENTIMENT
        if source_type == SourceType.SECTOR_SUMMARY:
            return ClaimType.SECTOR_CONTEXT
        if source_type == SourceType.ANALYSIS_REPORTS:
            return ClaimType.FORWARD_EXPECTATION
        if source_type == SourceType.NEWS_SOURCES:
            return ClaimType.DESCRIPTIVE
        return ClaimType.DESCRIPTIVE

    def _standalone_allowed(
        self,
        *,
        authority_class: AuthorityClass,
        content_class: ContentClass,
    ) -> bool:
        for rule in self._authority_matrix.special_rules:
            if rule.authority_class != authority_class:
                continue
            if content_class not in rule.applies_to_content_classes:
                continue
            if not rule.standalone_fact_authority_allowed:
                return False
        return True

    def _validation_errors(
        self,
        *,
        source_type: SourceType,
        content_class: ContentClass,
        claim_type: ClaimType,
        authority_class: AuthorityClass,
        creation_eligible: bool,
        standalone_allowed: bool,
        effective_rank: int | None,
    ) -> list[str]:
        errors: list[str] = []
        if source_type not in SOURCE_AUTHORITY_CLASS:
            errors.append(f"unsupported source_type: {source_type.value}")
        if effective_rank is None:
            errors.append(
                f"authority_class {authority_class.value} is not ranked for "
                f"claim_type {claim_type.value}"
            )
        if creation_eligible and not standalone_allowed:
            errors.append(
                "creation_eligible cannot be true when authority special rules "
                "disallow standalone fact creation"
            )
        if (
            content_class == ContentClass.MARKET_OBSERVATION
            and source_type
            not in {SourceType.MARKET_WATCH, SourceType.FUTURES_MARKET_WATCH}
        ):
            errors.append("market_observation requires a market source type")
        return errors


def _invalid_result(
    *,
    request: AuthorityAssignmentRequest,
    claim_type: ClaimType,
    authority_class: AuthorityClass,
    reason: str,
) -> AuthorityAssignmentResult:
    return AuthorityAssignmentResult(
        source_type=request.source_type,
        content_class=request.content_class,
        claim_type=claim_type,
        authority_class=authority_class,
        creation_eligible=False,
        effective_rank=None,
        standalone_fact_authority_allowed=False,
        applied_rules=("invalid_source_type",),
        invalid_mappings=(reason,),
        is_valid=False,
    )


__all__ = [
    "AuthorityAssignmentRequest",
    "AuthorityAssignmentResult",
    "AuthorityAssignmentService",
]
