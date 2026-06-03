"""Claim-type-scoped authority matrix models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import AuthorityClass, ClaimType, ContentClass
from .versioning import CURRENT_AUTHORITY_MATRIX_VERSION


class AuthorityMatrixEntry(BaseModel):
    """Effective authority ordering for one claim type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_type: ClaimType = Field(..., description="Claim type governed.")
    authority_order: tuple[AuthorityClass, ...] = Field(
        ..., min_length=1, description="Highest-to-lowest authority classes."
    )
    rationale: str = Field(
        ..., min_length=1, description="Governance rationale for the ordering."
    )

    @model_validator(mode="after")
    def _validate_unique_authorities(self) -> "AuthorityMatrixEntry":
        """Prevent duplicate authority classes inside one ranking."""

        if len(set(self.authority_order)) != len(self.authority_order):
            raise ValueError("authority_order cannot contain duplicates.")
        return self


class AuthoritySpecialRule(BaseModel):
    """Special authority governance rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(..., min_length=1)
    authority_class: AuthorityClass = Field(..., description="Authority class scoped.")
    applies_to_content_classes: tuple[ContentClass, ...] = Field(
        default_factory=tuple,
        description="Content classes where this rule is relevant.",
    )
    description: str = Field(..., min_length=1)
    standalone_fact_authority_allowed: bool = Field(
        ..., description="Whether this authority can create standalone facts."
    )


class AuthorityMatrix(BaseModel):
    """Versioned authority matrix keyed by claim type."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "authority_matrix_version": "1.0.0",
                    "entries": [
                        {
                            "claim_type": "audited_fact",
                            "authority_order": [
                                "audited_issuer",
                                "official_issuer_unaudited",
                                "independent_opinion",
                            ],
                            "rationale": "Audited reports dominate financial facts.",
                        }
                    ],
                    "special_rules": [
                        {
                            "rule_id": "news_media_corroboration_only",
                            "authority_class": "news_media",
                            "applies_to_content_classes": ["narrative_claim"],
                            "description": "News is corroboration-only.",
                            "standalone_fact_authority_allowed": False,
                        }
                    ],
                }
            ]
        },
    )

    authority_matrix_version: str = Field(..., min_length=1)
    entries: tuple[AuthorityMatrixEntry, ...] = Field(..., min_length=1)
    special_rules: tuple[AuthoritySpecialRule, ...] = Field(
        ..., min_length=1, description="Frozen news/market special rules."
    )

    @model_validator(mode="after")
    def _validate_matrix_totality(self) -> "AuthorityMatrix":
        """Require exactly one entry for every claim type."""

        claim_types = [entry.claim_type for entry in self.entries]
        duplicates = {claim_type for claim_type in claim_types if claim_types.count(claim_type) > 1}
        if duplicates:
            raise ValueError(
                "authority matrix contains duplicate claim_type entries: "
                + ", ".join(sorted(item.value for item in duplicates))
            )
        missing = set(ClaimType) - set(claim_types)
        if missing:
            raise ValueError(
                "authority matrix missing claim_type entries: "
                + ", ".join(sorted(item.value for item in missing))
            )
        if self._special_rule("news_media_corroboration_only") is None:
            raise ValueError("authority matrix must include news corroboration rule.")
        if self._special_rule("market_revealed_observation_only") is None:
            raise ValueError("authority matrix must include market observation rule.")
        return self

    def ranking_for(self, claim_type: ClaimType) -> tuple[AuthorityClass, ...]:
        """Return the authority ordering for a claim type."""

        for entry in self.entries:
            if entry.claim_type == claim_type:
                return entry.authority_order
        raise KeyError(f"Claim type is not present in matrix: {claim_type.value}")

    def effective_rank(
        self,
        *,
        claim_type: ClaimType,
        authority_class: AuthorityClass,
    ) -> int | None:
        """Return zero-based authority rank, or None if the class is not ranked."""

        ranking = self.ranking_for(claim_type)
        if authority_class not in ranking:
            return None
        return ranking.index(authority_class)

    def _special_rule(self, rule_id: str) -> AuthoritySpecialRule | None:
        return next(
            (rule for rule in self.special_rules if rule.rule_id == rule_id),
            None,
        )


def default_authority_matrix() -> AuthorityMatrix:
    """Return the frozen Phase 0 authority matrix."""

    return AuthorityMatrix(
        authority_matrix_version=CURRENT_AUTHORITY_MATRIX_VERSION,
        entries=(
            AuthorityMatrixEntry(
                claim_type=ClaimType.REGULATORY_COMPLIANCE,
                authority_order=(
                    AuthorityClass.REGULATORY_INDEPENDENT,
                    AuthorityClass.AUDITED_ISSUER,
                    AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                    AuthorityClass.NEWS_MEDIA,
                ),
                rationale="Regulators dominate compliance; issuer sources are secondary.",
            ),
            AuthorityMatrixEntry(
                claim_type=ClaimType.CORPORATE_ACTION_FACT,
                authority_order=(
                    AuthorityClass.EXCHANGE_OFFICIAL,
                    AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                    AuthorityClass.REGULATORY_INDEPENDENT,
                    AuthorityClass.NEWS_MEDIA,
                ),
                rationale="Exchange-published action data dominates issuer and media reports.",
            ),
            AuthorityMatrixEntry(
                claim_type=ClaimType.AUDITED_FACT,
                authority_order=(
                    AuthorityClass.AUDITED_ISSUER,
                    AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                    AuthorityClass.INDEPENDENT_OPINION,
                    AuthorityClass.NEWS_MEDIA,
                ),
                rationale="Audited issuer reports dominate financial facts.",
            ),
            AuthorityMatrixEntry(
                claim_type=ClaimType.OFFICIAL_UNAUDITED_FACT,
                authority_order=(
                    AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                    AuthorityClass.EXCHANGE_OFFICIAL,
                    AuthorityClass.INDEPENDENT_OPINION,
                    AuthorityClass.NEWS_MEDIA,
                ),
                rationale="Issuer official unaudited records dominate unaudited facts.",
            ),
            AuthorityMatrixEntry(
                claim_type=ClaimType.FORWARD_EXPECTATION,
                authority_order=(
                    AuthorityClass.INDEPENDENT_OPINION,
                    AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                    AuthorityClass.MARKET_REVEALED,
                    AuthorityClass.AUDITED_ISSUER,
                    AuthorityClass.NEWS_MEDIA,
                ),
                rationale="Independent opinion and explicit guidance outrank annual-report optimism.",
            ),
            AuthorityMatrixEntry(
                claim_type=ClaimType.DESCRIPTIVE,
                authority_order=(
                    AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                    AuthorityClass.AUDITED_ISSUER,
                    AuthorityClass.SECTOR_AGGREGATE,
                    AuthorityClass.INDEPENDENT_OPINION,
                    AuthorityClass.NEWS_MEDIA,
                ),
                rationale="Issuer descriptions dominate descriptive company context.",
            ),
            AuthorityMatrixEntry(
                claim_type=ClaimType.SENTIMENT,
                authority_order=(
                    AuthorityClass.MARKET_REVEALED,
                    AuthorityClass.INDEPENDENT_OPINION,
                    AuthorityClass.NEWS_MEDIA,
                    AuthorityClass.SECTOR_AGGREGATE,
                ),
                rationale="Market observations dominate sentiment, with media corroboration only.",
            ),
            AuthorityMatrixEntry(
                claim_type=ClaimType.SECTOR_CONTEXT,
                authority_order=(
                    AuthorityClass.SECTOR_AGGREGATE,
                    AuthorityClass.INDEPENDENT_OPINION,
                    AuthorityClass.MARKET_REVEALED,
                    AuthorityClass.NEWS_MEDIA,
                ),
                rationale="Sector aggregates dominate sector context.",
            ),
        ),
        special_rules=(
            AuthoritySpecialRule(
                rule_id="news_media_corroboration_only",
                authority_class=AuthorityClass.NEWS_MEDIA,
                applies_to_content_classes=(
                    ContentClass.NARRATIVE_CLAIM,
                    ContentClass.CORPORATE_EVENT,
                ),
                description=(
                    "News media may corroborate or surface contradictions, but may not "
                    "create standalone facts without independent verification."
                ),
                standalone_fact_authority_allowed=False,
            ),
            AuthoritySpecialRule(
                rule_id="market_revealed_observation_only",
                authority_class=AuthorityClass.MARKET_REVEALED,
                applies_to_content_classes=(ContentClass.MARKET_OBSERVATION,),
                description=(
                    "Market and futures data are observations/context, not standalone "
                    "fact creators for financial statement values."
                ),
                standalone_fact_authority_allowed=False,
            ),
        ),
    )


__all__ = [
    "AuthorityMatrix",
    "AuthorityMatrixEntry",
    "AuthoritySpecialRule",
    "default_authority_matrix",
]
