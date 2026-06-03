"""Frozen Query Engine v2 contract substrate.

These models materialize Query v2 Phase P0 only. They define immutable contract
shapes, enum registries, version pins, and contract-level invariants without
implementing intent classification, retrieval planning, ranking, citations, or
answer assembly behavior.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


QUERY_V2_CONTRACT_VERSION = "2.0.0"
QUERY_V2_RANKING_POLICY_VERSION = "2.0.0"
MSIL_SCHEMA_VERSION_CONSUMED = "1.0.0"
AUTHORITY_MATRIX_VERSION_CONSUMED = "1.0.0"
ENTITY_REGISTRY_VERSION_CONSUMED = "1.0.0"
QAE_CONSUMPTION_CONTRACT_VERSION_CONSUMED = "1.0.0"
FVE_CONSUMPTION_CONTRACT_VERSION_CONSUMED = "1.0.0"
TAXONOMY_VERSION_CONSUMED = "1.0.0"

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class QueryV2IntentType(str, Enum):
    """Frozen Query v2 intent type enum."""

    FACTUAL_LOOKUP = "factual_lookup"
    METRIC_LOOKUP = "metric_lookup"
    QUALITATIVE_ANALYSIS = "qualitative_analysis"
    FORECAST_VALIDATION = "forecast_validation"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    RISK_ANALYSIS = "risk_analysis"
    SOURCE_EXPLORATION = "source_exploration"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class QueryV2TargetDomain(str, Enum):
    """Frozen target domains for Query v2 evidence requests."""

    MSIL = "msil"
    OCR_VIA_MSIL = "ocr_via_msil"
    QAE = "qae"
    FVE = "fve"


class QueryV2ResponseStatus(str, Enum):
    """Frozen user-facing Query v2 response states."""

    ANSWERED = "ANSWERED"
    ANSWERED_WITH_WARNINGS = "ANSWERED_WITH_WARNINGS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSUPPORTED_INTENT = "UNSUPPORTED_INTENT"


class QueryV2CitationType(str, Enum):
    """Frozen citation types mirrored from MSIL provenance, excluding NONE."""

    WORKBOOK_CELL = "WORKBOOK_CELL"
    PDF_PAGE = "PDF_PAGE"
    ANNOUNCEMENT_REF = "ANNOUNCEMENT_REF"
    REGULATORY_REF = "REGULATORY_REF"
    PAYOUT_REF = "PAYOUT_REF"
    MARKET_DATA_REF = "MARKET_DATA_REF"
    FUTURES_REF = "FUTURES_REF"
    SECTOR_REF = "SECTOR_REF"
    URL_SNAPSHOT = "URL_SNAPSHOT"
    NEWS_REF = "NEWS_REF"


class QueryV2RankingSignal(str, Enum):
    """Frozen deterministic evidence-ranking signal names."""

    AUTHORITY_WEIGHT = "authority_weight"
    RECENCY = "recency"
    PROVENANCE_COMPLETENESS = "provenance_completeness"
    CORROBORATION_STRENGTH = "corroboration_strength"


class QueryV2PrecisionLevel(str, Enum):
    """Citation precision values allowed by the frozen contract."""

    PAGE = "page"
    DATE = "date"
    CELL = "cell"
    REF = "ref"


class QueryV2EntityResolutionStatus(str, Enum):
    """Entity-resolution states consumed from MSIL by Query v2."""

    RESOLVED = "resolved"
    REVIEW = "review"
    QUARANTINED = "quarantined"
    UNRESOLVED = "unresolved"


class QueryV2AuthorityRole(str, Enum):
    """Authority presentation roles allowed in Query v2 responses."""

    FACT = "fact"
    SUPPORTING = "supporting"
    OPINION = "opinion"
    FORWARD_CONTEXT = "forward_context"


class QueryV2PresentationStatus(str, Enum):
    """Divergence presentation status controlled by Query v2."""

    SURFACED = "surfaced"


class QueryV2DivergenceResolution(str, Enum):
    """Query v2 never resolves divergence."""

    NOT_DETERMINED_BY_QUERY = "not_determined_by_query"


class QueryV2VersionPins(BaseModel):
    """Complete version pin set required by Query v2 contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_contract_version: str = Field(
        default=QUERY_V2_CONTRACT_VERSION,
        min_length=1,
    )
    ranking_policy_version: str = Field(
        default=QUERY_V2_RANKING_POLICY_VERSION,
        min_length=1,
    )
    msil_schema_version: str = Field(
        default=MSIL_SCHEMA_VERSION_CONSUMED,
        min_length=1,
    )
    authority_matrix_version: str = Field(
        default=AUTHORITY_MATRIX_VERSION_CONSUMED,
        min_length=1,
    )
    entity_registry_version: str = Field(
        default=ENTITY_REGISTRY_VERSION_CONSUMED,
        min_length=1,
    )
    qae_consumption_contract_version: str = Field(
        default=QAE_CONSUMPTION_CONTRACT_VERSION_CONSUMED,
        min_length=1,
    )
    fve_consumption_contract_version: str = Field(
        default=FVE_CONSUMPTION_CONTRACT_VERSION_CONSUMED,
        min_length=1,
    )
    taxonomy_version: str = Field(
        default=TAXONOMY_VERSION_CONSUMED,
        min_length=1,
    )

    @field_validator("*")
    @classmethod
    def _validate_semver(cls, value: str) -> str:
        """Require semantic-version-looking pins."""

        if not _SEMVER_PATTERN.match(value):
            raise ValueError("version pins must use MAJOR.MINOR.PATCH format.")
        return value


def default_query_v2_version_pins() -> QueryV2VersionPins:
    """Return the frozen Query v2 default version pins."""

    return QueryV2VersionPins()


class QueryV2EntityMention(BaseModel):
    """Entity mention referenced by Query v2 intent contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_mention: str = Field(..., min_length=1)
    entity_ref: str | None = Field(default=None)
    entity_resolution_status: QueryV2EntityResolutionStatus

    @model_validator(mode="after")
    def _validate_entity_resolution(self) -> "QueryV2EntityMention":
        """Require MSIL-resolved refs only for resolved mentions."""

        if (
            self.entity_resolution_status == QueryV2EntityResolutionStatus.RESOLVED
            and not self.entity_ref
        ):
            raise ValueError("resolved entity mentions require entity_ref.")
        if (
            self.entity_resolution_status
            in {
                QueryV2EntityResolutionStatus.QUARANTINED,
                QueryV2EntityResolutionStatus.UNRESOLVED,
            }
            and self.entity_ref
        ):
            raise ValueError(
                "unresolved or quarantined entity mentions cannot carry entity_ref."
            )
        return self


class QueryIntentContract(BaseModel):
    """Frozen QueryIntent contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(..., min_length=1)
    raw_query: str = Field(..., min_length=1)
    intent_type: QueryV2IntentType
    secondary_intents: tuple[QueryV2IntentType, ...] = Field(default_factory=tuple)
    entity_mentions: tuple[QueryV2EntityMention, ...] = Field(default_factory=tuple)
    requested_metrics_or_topics: tuple[str, ...] = Field(default_factory=tuple)
    forecast_target: dict[str, Any] | None = Field(default=None)
    time_scope: dict[str, Any] | None = Field(default=None)
    classification_confidence: float = Field(..., ge=0, le=1)
    needs_clarification: bool
    clarification_prompt: str | None = Field(default=None)
    query_contract_version: str = Field(default=QUERY_V2_CONTRACT_VERSION)
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_intent_offramps(self) -> "QueryIntentContract":
        """Enforce clarification and version-pin invariants."""

        if self.needs_clarification and not self.clarification_prompt:
            raise ValueError("clarification_prompt is required when clarification is needed.")
        if self.intent_type == QueryV2IntentType.AMBIGUOUS and not self.needs_clarification:
            raise ValueError("ambiguous intent requires needs_clarification=True.")
        if self.query_contract_version != self.version_pins.query_contract_version:
            raise ValueError("query_contract_version must match version_pins.")
        return self


class RetrievalPlanStepContract(BaseModel):
    """One auditable deterministic retrieval plan step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(..., min_length=1)
    target_domain: QueryV2TargetDomain
    source_types: tuple[str, ...] = Field(default_factory=tuple)
    content_classes: tuple[str, ...] = Field(default_factory=tuple)
    purpose: str = Field(..., min_length=1)
    required_authority_floor: str | None = Field(default=None)
    recency_requirement: dict[str, Any] | None = Field(default=None)
    rule_id: str = Field(..., min_length=1)


class RetrievalPlanContract(BaseModel):
    """Frozen RetrievalPlan contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(..., min_length=1)
    intent_ref: str = Field(..., min_length=1)
    entity_refs: tuple[str, ...] = Field(default_factory=tuple)
    plan_steps: tuple[RetrievalPlanStepContract, ...] = Field(default_factory=tuple)
    is_multi_source: bool
    unsupported_reason: str | None = Field(default=None)
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_plan_shape(self) -> "RetrievalPlanContract":
        """Require steps and resolved entities unless the plan is unsupported."""

        if self.plan_steps and not self.entity_refs:
            raise ValueError("supported retrieval plans require resolved entity_refs.")
        if not self.plan_steps and not self.unsupported_reason:
            raise ValueError("unsupported_reason is required when plan_steps is empty.")
        if self.is_multi_source:
            domains = {step.target_domain for step in self.plan_steps}
            sources = {source for step in self.plan_steps for source in step.source_types}
            if len(domains) <= 1 and len(sources) <= 1:
                raise ValueError("is_multi_source=True requires multiple domains or sources.")
        return self


class EvidenceRequestContract(BaseModel):
    """Frozen EvidenceRequest contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(..., min_length=1)
    plan_step_ref: str = Field(..., min_length=1)
    target_domain: QueryV2TargetDomain
    entity_ref: str = Field(..., min_length=1)
    selectors: dict[str, Any] = Field(default_factory=dict)
    authority_floor: str | None = Field(default=None)
    recency_window: dict[str, Any] | None = Field(default=None)
    max_results: int | None = Field(default=None, gt=0)
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )


class EvidenceItemContract(BaseModel):
    """Evidence item carried as authored by MSIL, QAE, or FVE."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str = Field(..., min_length=1)
    content_class: str = Field(..., min_length=1)
    claim_or_value_or_theme_summary: str = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    provenance: dict[str, Any] = Field(..., min_length=1)
    observation_time: str | None = Field(default=None)
    subject_period: str | None = Field(default=None)
    supersession_state: str | None = Field(default=None)
    divergence_refs: tuple[str, ...] = Field(default_factory=tuple)
    entity_ref: str = Field(..., min_length=1)
    integrity_status: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_provenance(self) -> "EvidenceItemContract":
        """Forbid unprovenanced evidence from entering a bundle."""

        provenance = getattr(self, "provenance", None)
        if provenance is None:
            return self
        if not isinstance(provenance, dict):
            raise ValueError("provenance must be an object.")
        provenance_type = str(provenance.get("provenance_type", "")).upper()
        if provenance_type == "NONE":
            raise ValueError("NONE provenance is forbidden in Query v2 evidence.")
        return self


class EvidenceBundleContract(BaseModel):
    """Frozen EvidenceBundle contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str = Field(..., min_length=1)
    request_ref: str = Field(..., min_length=1)
    source_domain: QueryV2TargetDomain
    items: tuple[EvidenceItemContract, ...] = Field(default_factory=tuple)
    coverage_note: str = Field(..., min_length=1)
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )


class RankedEvidenceItemContract(BaseModel):
    """One ranked evidence reference with audit signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str = Field(..., min_length=1)
    rank: int = Field(..., ge=1)
    ranking_signals: dict[QueryV2RankingSignal, float] = Field(..., min_length=1)
    included: bool
    exclusion_reason: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_exclusion_reason(self) -> "RankedEvidenceItemContract":
        """Excluded evidence must explain why it was excluded."""

        if not self.included and not self.exclusion_reason:
            raise ValueError("excluded ranked evidence requires exclusion_reason.")
        return self


class RankedEvidenceContract(BaseModel):
    """Frozen RankedEvidence contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ranked_id: str = Field(..., min_length=1)
    bundle_ref: str = Field(..., min_length=1)
    ranked_items: tuple[RankedEvidenceItemContract, ...] = Field(default_factory=tuple)
    ranking_policy_version: str = Field(default=QUERY_V2_RANKING_POLICY_VERSION)
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_ranking_policy_pin(self) -> "RankedEvidenceContract":
        """Keep the explicit ranking pin aligned with version pins."""

        if self.ranking_policy_version != self.version_pins.ranking_policy_version:
            raise ValueError("ranking_policy_version must match version_pins.")
        return self


class AnswerAssemblyContextContract(BaseModel):
    """Frozen AnswerAssemblyContext contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context_id: str = Field(..., min_length=1)
    intent_ref: str = Field(..., min_length=1)
    ranked_evidence_refs: tuple[str, ...] = Field(default_factory=tuple)
    domain_conclusions: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    divergence_set: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    authority_set: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    confidence_ceiling: float = Field(..., ge=0, le=1)
    insufficiency_flag: bool
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_grounding(self) -> "AnswerAssemblyContextContract":
        """Require grounding and authority for answerable assembly contexts."""

        if not self.insufficiency_flag and not self.ranked_evidence_refs:
            raise ValueError("answerable contexts require ranked_evidence_refs.")
        if not self.insufficiency_flag and not self.authority_set:
            raise ValueError("answerable contexts require authority_set.")
        return self


class CitationContract(BaseModel):
    """Frozen CitationContract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(..., min_length=1)
    citation_type: QueryV2CitationType
    source_ref: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    evidence_ref: str = Field(..., min_length=1)
    rendered_text: str = Field(..., min_length=1)
    precision_level: QueryV2PrecisionLevel
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )


class QueryV2ClaimContract(BaseModel):
    """One claim inside a Query v2 response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(..., min_length=1)
    supporting_evidence_refs: tuple[str, ...] = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    citations: tuple[CitationContract, ...] = Field(..., min_length=1)
    confidence: float = Field(..., ge=0, le=1)
    numeric_integrity_status: str | None = Field(default=None)


class DivergenceSidePresentationContract(BaseModel):
    """One side of an MSIL-authored divergence presented by Query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_summary: str = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    citation: CitationContract


class DivergencePresentationContract(BaseModel):
    """Frozen DivergencePresentationContract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    presentation_id: str = Field(..., min_length=1)
    divergence_ref: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    sides: tuple[DivergenceSidePresentationContract, ...] = Field(..., min_length=2)
    authority_weighting: dict[str, Any] = Field(..., min_length=1)
    presentation_status: QueryV2PresentationStatus = QueryV2PresentationStatus.SURFACED
    resolution: QueryV2DivergenceResolution = (
        QueryV2DivergenceResolution.NOT_DETERMINED_BY_QUERY
    )
    detected_by: str = Field(..., min_length=1)
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_divergence_presentation(self) -> "DivergencePresentationContract":
        """Enforce surfaced-never-resolved divergence presentation."""

        if self.presentation_status != QueryV2PresentationStatus.SURFACED:
            raise ValueError("divergence presentation_status must be surfaced.")
        if self.resolution != QueryV2DivergenceResolution.NOT_DETERMINED_BY_QUERY:
            raise ValueError("Query must not resolve divergence.")
        weighting_mode = str(self.authority_weighting.get("weighting", "")).lower()
        if weighting_mode == "equal":
            raise ValueError("equal-weighting is forbidden for divergence presentation.")
        return self


class AuthorityPresentationContract(BaseModel):
    """Frozen AuthorityPresentationContract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    presentation_id: str = Field(..., min_length=1)
    claim_ref: str = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    claim_type: str = Field(..., min_length=1)
    effective_authority: str = Field(..., min_length=1)
    attribution_label: str = Field(..., min_length=1)
    authority_role: QueryV2AuthorityRole
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )

    @model_validator(mode="after")
    def _validate_low_authority_role(self) -> "AuthorityPresentationContract":
        """Prevent explicit opinion or market authority from being presented as fact."""

        low_authority_tokens = ("news", "analyst", "market", "opinion")
        authority_text = f"{self.authority_class} {self.effective_authority}".lower()
        if (
            self.authority_role == QueryV2AuthorityRole.FACT
            and any(token in authority_text for token in low_authority_tokens)
        ):
            raise ValueError("low-authority evidence cannot be presented as fact.")
        return self


class QueryResponseContract(BaseModel):
    """Frozen QueryResponse contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response_id: str = Field(..., min_length=1)
    query_id: str = Field(..., min_length=1)
    status: QueryV2ResponseStatus
    answer_text: str | None = Field(default=None)
    claims: tuple[QueryV2ClaimContract, ...] = Field(default_factory=tuple)
    divergences: tuple[DivergencePresentationContract, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    overall_confidence: float = Field(..., ge=0, le=1)
    numeric_integrity_status: str | None = Field(default=None)
    clarification_prompt: str | None = Field(default=None)
    version_pins: QueryV2VersionPins = Field(
        default_factory=default_query_v2_version_pins
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="after")
    def _validate_response_contract(self) -> "QueryResponseContract":
        """Enforce cited-answer and off-ramp invariants."""

        if self.status in {
            QueryV2ResponseStatus.ANSWERED,
            QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS,
        }:
            if not self.claims:
                raise ValueError("answered QueryResponse requires at least one claim.")
            if not self.answer_text:
                raise ValueError("answered QueryResponse requires answer_text.")
            for claim in self.claims:
                if not claim.citations:
                    raise ValueError("every answered claim requires at least one citation.")
        if (
            self.status == QueryV2ResponseStatus.NEEDS_CLARIFICATION
            and not self.clarification_prompt
        ):
            raise ValueError(
                "clarification_prompt is required for NEEDS_CLARIFICATION."
            )
        return self


FROZEN_QUERY_V2_CONTRACTS: tuple[str, ...] = (
    "QueryIntent",
    "RetrievalPlan",
    "EvidenceRequest",
    "EvidenceBundle",
    "RankedEvidence",
    "AnswerAssemblyContext",
    "QueryResponse",
    "CitationContract",
    "DivergencePresentationContract",
    "AuthorityPresentationContract",
)

FROZEN_QUERY_V2_ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "intent_type": tuple(item.value for item in QueryV2IntentType),
    "target_domain": tuple(item.value for item in QueryV2TargetDomain),
    "status": tuple(item.value for item in QueryV2ResponseStatus),
    "citation_type": tuple(item.value for item in QueryV2CitationType),
    "ranking_signals": tuple(item.value for item in QueryV2RankingSignal),
}

FROZEN_QUERY_V2_VERSION_PIN_FIELDS: tuple[str, ...] = (
    "query_contract_version",
    "ranking_policy_version",
    "msil_schema_version",
    "authority_matrix_version",
    "entity_registry_version",
    "qae_consumption_contract_version",
    "fve_consumption_contract_version",
    "taxonomy_version",
)

FROZEN_QUERY_V2_OWNERSHIP_TABLE: dict[str, str] = {
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

FROZEN_QUERY_V2_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "QueryIntent": (
        "query_id",
        "raw_query",
        "intent_type",
        "entity_mentions",
        "classification_confidence",
        "needs_clarification",
        "query_contract_version",
    ),
    "RetrievalPlan": (
        "plan_id",
        "intent_ref",
        "entity_refs",
        "plan_steps",
        "is_multi_source",
        "version_pins",
    ),
    "EvidenceRequest": (
        "request_id",
        "plan_step_ref",
        "target_domain",
        "entity_ref",
        "selectors",
        "version_pins",
    ),
    "EvidenceBundle": (
        "bundle_id",
        "request_ref",
        "source_domain",
        "items",
        "coverage_note",
        "version_pins",
    ),
    "RankedEvidence": (
        "ranked_id",
        "bundle_ref",
        "ranked_items",
        "ranking_policy_version",
        "version_pins",
    ),
    "AnswerAssemblyContext": (
        "context_id",
        "intent_ref",
        "ranked_evidence_refs",
        "authority_set",
        "confidence_ceiling",
        "insufficiency_flag",
        "version_pins",
    ),
    "QueryResponse": (
        "response_id",
        "query_id",
        "status",
        "claims",
        "overall_confidence",
        "version_pins",
        "generated_at",
    ),
    "CitationContract": (
        "citation_id",
        "citation_type",
        "source_ref",
        "entity_ref",
        "evidence_ref",
        "rendered_text",
        "precision_level",
        "version_pins",
    ),
    "DivergencePresentationContract": (
        "presentation_id",
        "divergence_ref",
        "entity_ref",
        "subject",
        "sides",
        "authority_weighting",
        "presentation_status",
        "resolution",
        "detected_by",
        "version_pins",
    ),
    "AuthorityPresentationContract": (
        "presentation_id",
        "claim_ref",
        "authority_class",
        "claim_type",
        "effective_authority",
        "attribution_label",
        "authority_role",
        "version_pins",
    ),
}

QUERY_V2_CONTRACT_MODEL_REGISTRY: dict[str, type[BaseModel]] = {
    "QueryIntent": QueryIntentContract,
    "RetrievalPlan": RetrievalPlanContract,
    "EvidenceRequest": EvidenceRequestContract,
    "EvidenceBundle": EvidenceBundleContract,
    "RankedEvidence": RankedEvidenceContract,
    "AnswerAssemblyContext": AnswerAssemblyContextContract,
    "QueryResponse": QueryResponseContract,
    "CitationContract": CitationContract,
    "DivergencePresentationContract": DivergencePresentationContract,
    "AuthorityPresentationContract": AuthorityPresentationContract,
}


__all__ = [
    "AUTHORITY_MATRIX_VERSION_CONSUMED",
    "AnswerAssemblyContextContract",
    "AuthorityPresentationContract",
    "CitationContract",
    "DivergencePresentationContract",
    "DivergenceSidePresentationContract",
    "ENTITY_REGISTRY_VERSION_CONSUMED",
    "EvidenceBundleContract",
    "EvidenceItemContract",
    "EvidenceRequestContract",
    "FROZEN_QUERY_V2_CONTRACTS",
    "FROZEN_QUERY_V2_ENUM_VALUES",
    "FROZEN_QUERY_V2_OWNERSHIP_TABLE",
    "FROZEN_QUERY_V2_REQUIRED_FIELDS",
    "FROZEN_QUERY_V2_VERSION_PIN_FIELDS",
    "FVE_CONSUMPTION_CONTRACT_VERSION_CONSUMED",
    "MSIL_SCHEMA_VERSION_CONSUMED",
    "QAE_CONSUMPTION_CONTRACT_VERSION_CONSUMED",
    "QUERY_V2_CONTRACT_MODEL_REGISTRY",
    "QUERY_V2_CONTRACT_VERSION",
    "QUERY_V2_RANKING_POLICY_VERSION",
    "QueryIntentContract",
    "QueryResponseContract",
    "QueryV2AuthorityRole",
    "QueryV2CitationType",
    "QueryV2ClaimContract",
    "QueryV2DivergenceResolution",
    "QueryV2EntityMention",
    "QueryV2EntityResolutionStatus",
    "QueryV2IntentType",
    "QueryV2PrecisionLevel",
    "QueryV2PresentationStatus",
    "QueryV2RankingSignal",
    "QueryV2ResponseStatus",
    "QueryV2TargetDomain",
    "QueryV2VersionPins",
    "RankedEvidenceContract",
    "RankedEvidenceItemContract",
    "RetrievalPlanContract",
    "RetrievalPlanStepContract",
    "TAXONOMY_VERSION_CONSUMED",
    "default_query_v2_version_pins",
]
