"""Deterministic entity resolution for MSIL Phase 1."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from multi_source_intelligence.models import (
    AliasType,
    Entity,
    EntityAlias,
    EntityRegistry,
    EntityResolutionCandidate,
    EntityResolutionRequest,
    EntityResolutionResult,
    EntityStatus,
    EntityType,
    RelationshipType,
    ResolutionMethod,
    ReviewStatus,
)
from multi_source_intelligence.models.entity_registry import normalize_identifier

from .default_entity_registry import default_entity_registry


EXACT_TICKER_CONFIDENCE = 0.99
EXACT_LEGAL_CONFIDENCE = 0.98
ALIAS_CONFIDENCE = 0.95
FUZZY_REVIEW_FLOOR = 0.70
FUZZY_QUARANTINE_FLOOR = 0.62


@dataclass(frozen=True)
class _ManualReviewRule:
    candidate_ids: tuple[str, ...]
    confidence: float
    reason: str


class EntityResolver:
    """Resolve raw identifiers using exact > alias > fuzzy > unresolved."""

    _QUARANTINE_IDENTIFIERS = {
        "agco": "external_principal_not_registry_entity",
        "massey ferguson": "external_brand_not_registry_entity",
        "atf": "csr_foundation_not_issuer",
        "aziz tabba foundation": "csr_foundation_not_issuer",
        "xyz cement limited": "unknown_issuer",
        "luckx": "typo_ticker_not_force_bound",
        "luk": "typo_ticker_not_force_bound",
        "lucky goldstar": "foreign_entity_not_lucky_group",
        "lg": "foreign_or_ambiguous_short_token",
        "news mention lucky in a non financial context": "context_insufficient",
    }

    _MANUAL_REVIEW_RULES = {
        "lucky": _ManualReviewRule(
            candidate_ids=(
                "lucky_cement",
                "lucky_core_industries",
                "lucky_motor_corporation",
                "lucky_electric_power",
            ),
            confidence=0.74,
            reason="bare_lucky_group_token",
        ),
        "millat": _ManualReviewRule(
            candidate_ids=(
                "millat_tractors",
                "millat_industrial_products",
                "millat_equipment",
            ),
            confidence=0.74,
            reason="bare_millat_group_token",
        ),
        "ici": _ManualReviewRule(
            candidate_ids=("lucky_core_industries",),
            confidence=0.67,
            reason="historical_generic_token_requires_review",
        ),
        "lucky power": _ManualReviewRule(
            candidate_ids=("lucky_electric_power",),
            confidence=0.72,
            reason="partial_power_variant_requires_review",
        ),
        "millat i": _ManualReviewRule(
            candidate_ids=("millat_industrial_products", "millat_equipment"),
            confidence=0.66,
            reason="truncated_millat_identifier_requires_review",
        ),
        "yunus": _ManualReviewRule(
            candidate_ids=("yunus_brothers_group", "yunus_textile_mills"),
            confidence=0.70,
            reason="bare_yunus_group_token",
        ),
    }

    def __init__(self, registry: EntityRegistry | None = None) -> None:
        self._registry = registry or default_entity_registry()

    @property
    def registry(self) -> EntityRegistry:
        """Return the registry used by this resolver."""

        return self._registry

    def resolve(
        self,
        request: EntityResolutionRequest | str,
    ) -> EntityResolutionResult:
        """Resolve one raw identifier without LLM or semantic guessing."""

        if isinstance(request, str):
            request = EntityResolutionRequest(raw_identifier=request)
        normalized = normalize_identifier(request.raw_identifier)

        quarantine_reason = self._QUARANTINE_IDENTIFIERS.get(normalized)
        if quarantine_reason:
            return self._quarantined(
                request=request,
                normalized=normalized,
                reason=quarantine_reason,
            )

        review_rule = self._MANUAL_REVIEW_RULES.get(normalized)
        if review_rule:
            return self._manual_review(
                request=request,
                normalized=normalized,
                rule=review_rule,
            )

        exact_candidates = self._exact_candidates(normalized)
        if len(exact_candidates) == 1:
            return self._resolved(
                request=request,
                normalized=normalized,
                candidate=exact_candidates[0],
                reason="exact_match",
            )
        if len(exact_candidates) > 1:
            return self._review(
                request=request,
                normalized=normalized,
                method=ResolutionMethod.EXACT,
                candidates=exact_candidates,
                confidence=max(candidate.confidence for candidate in exact_candidates),
                reason="ambiguous_exact_match",
            )

        alias_candidates = self._alias_candidates(normalized)
        if len(alias_candidates) == 1:
            return self._resolved(
                request=request,
                normalized=normalized,
                candidate=alias_candidates[0],
                reason="alias_match",
            )
        if len(alias_candidates) > 1:
            return self._review(
                request=request,
                normalized=normalized,
                method=ResolutionMethod.ALIAS,
                candidates=alias_candidates,
                confidence=max(candidate.confidence for candidate in alias_candidates),
                reason="ambiguous_alias_match",
            )

        if self._looks_like_unknown_ticker(request.raw_identifier):
            return self._quarantined(
                request=request,
                normalized=normalized,
                reason="unknown_or_typo_ticker_not_force_bound",
            )

        if request.allow_fuzzy:
            fuzzy_candidates = self._fuzzy_candidates(normalized)
            if fuzzy_candidates:
                confidence = max(candidate.confidence for candidate in fuzzy_candidates)
                if confidence >= FUZZY_REVIEW_FLOOR:
                    return self._review(
                        request=request,
                        normalized=normalized,
                        method=ResolutionMethod.FUZZY,
                        candidates=fuzzy_candidates,
                        confidence=confidence,
                        reason="fuzzy_match_requires_review",
                    )
                if confidence >= FUZZY_QUARANTINE_FLOOR:
                    return self._quarantined(
                        request=request,
                        normalized=normalized,
                        reason="below_review_threshold_fuzzy_match",
                    )

        return self._quarantined(
            request=request,
            normalized=normalized,
            reason="unresolved_identifier",
        )

    def _exact_candidates(self, normalized: str) -> tuple[EntityResolutionCandidate, ...]:
        candidates: list[EntityResolutionCandidate] = []
        for entity in self._registry.active_entities():
            if entity.canonical_id.lower() == normalized:
                candidates.append(
                    self._candidate(
                        entity,
                        method=ResolutionMethod.EXACT,
                        confidence=EXACT_LEGAL_CONFIDENCE,
                        matched_value=entity.canonical_id,
                    )
                )
            if entity.normalized_display_name == normalized:
                candidates.append(
                    self._candidate(
                        entity,
                        method=ResolutionMethod.EXACT,
                        confidence=EXACT_LEGAL_CONFIDENCE,
                        matched_value=entity.display_name,
                    )
                )
            for alias in entity.aliases:
                if alias.normalized_value != normalized or not alias.exact_match:
                    continue
                confidence = (
                    EXACT_TICKER_CONFIDENCE
                    if alias.alias_type == AliasType.TICKER
                    else EXACT_LEGAL_CONFIDENCE
                )
                candidates.append(
                    self._candidate(
                        entity,
                        method=ResolutionMethod.EXACT,
                        confidence=confidence,
                        matched_value=alias.value,
                        alias=alias,
                    )
                )
        return _dedupe_candidates(candidates)

    def _alias_candidates(self, normalized: str) -> tuple[EntityResolutionCandidate, ...]:
        candidates: list[EntityResolutionCandidate] = []
        for entity, alias in self._registry.aliases():
            if alias.normalized_value == normalized and not alias.exact_match:
                candidates.append(
                    self._candidate(
                        entity,
                        method=ResolutionMethod.ALIAS,
                        confidence=ALIAS_CONFIDENCE,
                        matched_value=alias.value,
                        alias=alias,
                    )
                )
        return _dedupe_candidates(candidates)

    def _fuzzy_candidates(self, normalized: str) -> tuple[EntityResolutionCandidate, ...]:
        by_entity: dict[str, EntityResolutionCandidate] = {}
        for entity in self._registry.active_entities():
            if entity.entity_type == EntityType.SECTOR:
                continue
            match_values = [entity.display_name, *(alias.value for alias in entity.aliases)]
            best_score = max(_similarity(normalized, normalize_identifier(value)) for value in match_values)
            if best_score < FUZZY_QUARANTINE_FLOOR:
                continue
            candidate = self._candidate(
                entity,
                method=ResolutionMethod.FUZZY,
                confidence=round(best_score, 6),
                matched_value="best_fuzzy_alias",
                evidence={"best_similarity": round(best_score, 6)},
            )
            existing = by_entity.get(candidate.final_entity_ref or candidate.canonical_id)
            if existing is None or candidate.confidence > existing.confidence:
                by_entity[candidate.final_entity_ref or candidate.canonical_id] = candidate
        return tuple(
            sorted(
                by_entity.values(),
                key=lambda candidate: (-candidate.confidence, candidate.canonical_id),
            )[:5]
        )

    def _candidate(
        self,
        entity: Entity,
        *,
        method: ResolutionMethod,
        confidence: float,
        matched_value: str | None,
        alias: EntityAlias | None = None,
        evidence: dict[str, object] | None = None,
    ) -> EntityResolutionCandidate:
        final_entity_ref, path = self._resolution_path(entity)
        candidate_evidence = {
            "entity_registry_version": self._registry.entity_registry_version,
        }
        if alias is not None:
            candidate_evidence.update(
                {
                    "alias_type": alias.alias_type.value,
                    "historical": alias.historical,
                    "requires_confirmation": alias.requires_confirmation,
                }
            )
        if evidence:
            candidate_evidence.update(evidence)
        return EntityResolutionCandidate(
            canonical_id=entity.canonical_id,
            entity_type=entity.entity_type,
            display_name=entity.display_name,
            method=method,
            confidence=confidence,
            matched_value=matched_value,
            final_entity_ref=final_entity_ref,
            resolution_path=path,
            evidence=candidate_evidence,
        )

    def _resolution_path(self, entity: Entity) -> tuple[str, tuple[str, ...]]:
        if entity.entity_type != EntityType.SECURITY:
            return entity.canonical_id, (entity.canonical_id,)
        company_relationship = next(
            (
                relationship
                for relationship in entity.relationships
                if relationship.rel_type == RelationshipType.SECURITY_OF
            ),
            None,
        )
        if company_relationship is None:
            return entity.canonical_id, (entity.canonical_id,)
        return (
            company_relationship.target_canonical_id,
            (entity.canonical_id, company_relationship.target_canonical_id),
        )

    def _resolved(
        self,
        *,
        request: EntityResolutionRequest,
        normalized: str,
        candidate: EntityResolutionCandidate,
        reason: str,
    ) -> EntityResolutionResult:
        return EntityResolutionResult(
            raw_identifier=request.raw_identifier,
            normalized_identifier=normalized,
            method=candidate.method,
            confidence=candidate.confidence,
            review_status=ReviewStatus.RESOLVED,
            resolved_entity_ref=candidate.final_entity_ref or candidate.canonical_id,
            resolved_entity_type=self._resolved_entity_type(candidate),
            resolved_security_ref=(
                candidate.canonical_id
                if candidate.entity_type == EntityType.SECURITY
                else None
            ),
            candidates=(candidate,),
            review_required=False,
            evidence={"resolution_reason": reason},
            entity_registry_version=self._registry.entity_registry_version,
        )

    def _review(
        self,
        *,
        request: EntityResolutionRequest,
        normalized: str,
        method: ResolutionMethod,
        candidates: tuple[EntityResolutionCandidate, ...],
        confidence: float,
        reason: str,
    ) -> EntityResolutionResult:
        return EntityResolutionResult(
            raw_identifier=request.raw_identifier,
            normalized_identifier=normalized,
            method=method,
            confidence=confidence,
            review_status=ReviewStatus.REVIEW,
            resolved_entity_ref=None,
            candidates=candidates,
            review_required=True,
            evidence={"resolution_reason": reason},
            entity_registry_version=self._registry.entity_registry_version,
        )

    def _manual_review(
        self,
        *,
        request: EntityResolutionRequest,
        normalized: str,
        rule: _ManualReviewRule,
    ) -> EntityResolutionResult:
        candidates = tuple(
            self._candidate(
                self._require_entity(candidate_id),
                method=ResolutionMethod.FUZZY,
                confidence=rule.confidence,
                matched_value=request.raw_identifier,
                evidence={"manual_review_rule": rule.reason},
            )
            for candidate_id in rule.candidate_ids
        )
        return self._review(
            request=request,
            normalized=normalized,
            method=ResolutionMethod.FUZZY,
            candidates=candidates,
            confidence=rule.confidence,
            reason=rule.reason,
        )

    def _quarantined(
        self,
        *,
        request: EntityResolutionRequest,
        normalized: str,
        reason: str,
    ) -> EntityResolutionResult:
        return EntityResolutionResult(
            raw_identifier=request.raw_identifier,
            normalized_identifier=normalized,
            method=ResolutionMethod.UNRESOLVED,
            confidence=0.0,
            review_status=ReviewStatus.QUARANTINED,
            resolved_entity_ref=None,
            candidates=(),
            review_required=True,
            evidence={"resolution_reason": reason},
            entity_registry_version=self._registry.entity_registry_version,
        )

    def _resolved_entity_type(
        self,
        candidate: EntityResolutionCandidate,
    ) -> EntityType:
        if candidate.entity_type != EntityType.SECURITY:
            return candidate.entity_type
        final_entity = self._registry.entity_by_id(
            candidate.final_entity_ref or candidate.canonical_id
        )
        return final_entity.entity_type if final_entity else candidate.entity_type

    def _require_entity(self, canonical_id: str) -> Entity:
        entity = self._registry.entity_by_id(canonical_id)
        if entity is None:
            raise KeyError(f"Entity is not present in registry: {canonical_id}")
        if entity.status != EntityStatus.ACTIVE:
            raise ValueError(f"Entity is not active: {canonical_id}")
        return entity

    def _looks_like_unknown_ticker(self, raw_identifier: str) -> bool:
        raw = raw_identifier.strip()
        return raw.isupper() and raw.isalpha() and 2 <= len(raw) <= 5


def _dedupe_candidates(
    candidates: list[EntityResolutionCandidate],
) -> tuple[EntityResolutionCandidate, ...]:
    by_key: dict[tuple[str | None, str], EntityResolutionCandidate] = {}
    for candidate in candidates:
        key = (candidate.final_entity_ref, candidate.canonical_id)
        existing = by_key.get(key)
        if existing is None or candidate.confidence > existing.confidence:
            by_key[key] = candidate
    return tuple(
        sorted(
            by_key.values(),
            key=lambda candidate: (
                candidate.entity_type.value != EntityType.SECURITY.value,
                candidate.canonical_id,
            ),
        )
    )


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


__all__ = ["EntityResolver"]
