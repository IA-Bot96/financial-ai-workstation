"""Deterministic Query Engine v2 intent classification.

This Phase P1 service emits the frozen QueryIntent contract only. It does not
perform entity resolution, retrieval planning, ranking, answer assembly,
citations, divergence handling, authority handling, or LLM work.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.v2_contracts import (
    QueryIntentContract,
    QueryV2EntityMention,
    QueryV2EntityResolutionStatus,
    QueryV2IntentType,
)


_INTENT_THRESHOLD = 2

_METRIC_TERMS: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "sales", "turnover", "net sales"),
    "gross_profit": ("gross profit",),
    "operating_profit": ("operating profit", "operating income"),
    "profit_after_tax": ("net income", "profit after tax", "net profit", "pat"),
    "earnings_per_share": ("eps", "earnings per share", "earning per share"),
    "cash_and_cash_equivalents": (
        "cash",
        "cash and cash equivalents",
        "cash equivalents",
        "bank balances",
    ),
    "total_debt": ("debt", "borrowings", "finance", "loans"),
    "total_equity": ("equity", "net assets", "shareholders equity"),
    "capital_expenditure": ("capex", "capital expenditure"),
    "operating_cash_flow": (
        "operating cash flow",
        "cash flow from operations",
        "cash generated from operations",
    ),
}

_INTENT_RULES: dict[QueryV2IntentType, tuple[tuple[str, int, tuple[str, ...]], ...]] = {
    QueryV2IntentType.FACTUAL_LOOKUP: (
        ("factual_lookup:who", 2, ("who is", "who was")),
        ("factual_lookup:where", 2, ("where is", "where was")),
        ("factual_lookup:company_identity", 3, ("registered office", "address", "ticker", "sector", "ceo", "chairman")),
        ("factual_lookup:what_is", 2, ("what is", "what are")),
    ),
    QueryV2IntentType.METRIC_LOOKUP: (
        ("metric_lookup:direct_value", 3, ("what was", "what is", "show", "value of")),
        ("metric_lookup:history", 3, ("trend", "history", "historical", "over years")),
        ("metric_lookup:growth", 3, ("growth", "cagr", "compound annual growth rate")),
    ),
    QueryV2IntentType.QUALITATIVE_ANALYSIS: (
        ("qualitative_analysis:why_explain", 4, ("why", "explain", "what drove", "drivers", "drove")),
        ("qualitative_analysis:narrative_sections", 3, ("business review", "management discussion", "outlook", "strategy", "sustainability", "governance")),
        ("qualitative_analysis:change_reasons", 3, ("decline", "increase", "decrease", "reasons")),
    ),
    QueryV2IntentType.FORECAST_VALIDATION: (
        ("forecast_validation:forecast", 5, ("forecast", "projection", "projected", "budget", "target")),
        ("forecast_validation:reasonableness", 3, ("reasonable", "validate", "plausible")),
    ),
    QueryV2IntentType.COMPARISON: (
        ("comparison:explicit_compare", 5, ("compare", "comparison", "versus", " vs ", "relative to")),
        ("comparison:between", 4, ("between", "against")),
    ),
    QueryV2IntentType.TIMELINE: (
        ("timeline:timeline", 5, ("timeline", "chronology")),
        ("timeline:events", 4, ("events", "announcements", "corporate actions", "what happened", "when did")),
        ("timeline:actions", 3, ("dividend", "board change", "rights issue", "bonus issue")),
    ),
    QueryV2IntentType.RISK_ANALYSIS: (
        ("risk_analysis:explicit", 5, ("risk analysis", "risk profile", "risk exposure")),
        ("risk_analysis:risk_terms", 3, ("major risks", "principal risks", "uncertainties", "regulatory risk")),
    ),
    QueryV2IntentType.SOURCE_EXPLORATION: (
        ("source_exploration:source", 5, ("source", "sources", "citation", "citations", "evidence", "provenance")),
        ("source_exploration:selection", 5, ("why was", "why were", "selected", "chosen")),
        ("source_exploration:where_from", 4, ("where did this come from", "which report", "show me the reference")),
    ),
}

_AMBIGUOUS_PATTERNS = (
    "tell me about",
    "what about",
    "analyze the company",
    "company performance",
)

_UNSUPPORTED_PATTERNS = (
    "write a poem",
    "draft an email",
    "translate",
    "make an image",
    "book a meeting",
)


class QueryIntentCandidate(BaseModel):
    """One scored deterministic intent candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_type: QueryV2IntentType
    score: int = Field(..., ge=0)
    matched_rules: tuple[str, ...] = Field(default_factory=tuple)
    matched_terms: tuple[str, ...] = Field(default_factory=tuple)


class QueryIntentClassificationResult(BaseModel):
    """Result of deterministic Query v2 intent classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_intent: QueryIntentContract
    candidates: tuple[QueryIntentCandidate, ...] = Field(default_factory=tuple)
    matched_rules: tuple[str, ...] = Field(default_factory=tuple)
    matched_terms: tuple[str, ...] = Field(default_factory=tuple)
    ambiguity_routed_to_clarification: bool = False
    unsupported_routed_to_unsupported: bool = False
    deterministic_signature: str = Field(..., min_length=1)
    entity_mentions_consumed: int = Field(..., ge=0)
    supplied_entity_refs: tuple[str, ...] = Field(default_factory=tuple)
    msil_called: bool = False
    entity_resolution_performed: bool = False
    entities_created: bool = False


class QueryV2IntentAudit(BaseModel):
    """Audit payload for Query v2 Phase P1 intent classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    classification_coverage: dict[str, int]
    frozen_intents_covered: tuple[str, ...]
    missing_frozen_intents: tuple[str, ...]
    ambiguity_routing_passed: bool
    unsupported_routing_passed: bool
    deterministic_repeatability_passed: bool
    entity_handling: dict[str, Any]
    sample_results: tuple[dict[str, Any], ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryV2Phase1Report(BaseModel):
    """Implementation report for Query v2 Phase P1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    classifier: str
    frozen_intents_supported: tuple[str, ...]
    audit_path: str
    validation_passed: bool
    deterministic_repeatability_passed: bool
    ambiguity_routing_passed: bool
    unsupported_routing_passed: bool
    entity_resolution_boundary: dict[str, Any]
    prohibited_implementations: tuple[str, ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryIntentClassifier:
    """Rule-based deterministic classifier for the frozen QueryIntent contract."""

    def classify(
        self,
        raw_query: str,
        *,
        query_id: str | None = None,
        entity_mentions: Iterable[QueryV2EntityMention | Mapping[str, Any]] = (),
        forecast_target: dict[str, Any] | None = None,
        time_scope: dict[str, Any] | None = None,
    ) -> QueryIntentClassificationResult:
        """Classify a raw query into a frozen QueryIntentContract."""

        query_text = raw_query.strip()
        mentions = self._coerce_entity_mentions(entity_mentions)
        normalized = _normalize_query(query_text)
        deterministic_signature = _deterministic_signature(
            raw_query=query_text,
            entity_mentions=mentions,
            forecast_target=forecast_target,
            time_scope=time_scope,
        )
        query_id = query_id or f"query_v2_{deterministic_signature[:16]}"

        entity_ambiguity = [
            mention
            for mention in mentions
            if mention.entity_resolution_status
            != QueryV2EntityResolutionStatus.RESOLVED
        ]
        if entity_ambiguity:
            return self._build_ambiguous_result(
                query_id=query_id,
                raw_query=query_text,
                mentions=mentions,
                deterministic_signature=deterministic_signature,
                reason="Supplied MSIL entity reference requires clarification.",
                candidates=(),
                forecast_target=forecast_target,
                time_scope=time_scope,
            )

        if not normalized or _contains_any(normalized, _UNSUPPORTED_PATTERNS):
            return self._build_unsupported_result(
                query_id=query_id,
                raw_query=query_text or raw_query,
                mentions=mentions,
                deterministic_signature=deterministic_signature,
                forecast_target=forecast_target,
                time_scope=time_scope,
            )

        candidates = self._score_candidates(normalized)
        if self._is_intrinsically_ambiguous(normalized, candidates):
            return self._build_ambiguous_result(
                query_id=query_id,
                raw_query=query_text,
                mentions=mentions,
                deterministic_signature=deterministic_signature,
                reason="The query is too broad to classify deterministically.",
                candidates=candidates,
                forecast_target=forecast_target,
                time_scope=time_scope,
            )

        if not candidates or candidates[0].score < _INTENT_THRESHOLD:
            return self._build_unsupported_result(
                query_id=query_id,
                raw_query=query_text,
                mentions=mentions,
                deterministic_signature=deterministic_signature,
                forecast_target=forecast_target,
                time_scope=time_scope,
            )

        top_score = candidates[0].score
        tied = tuple(candidate for candidate in candidates if candidate.score == top_score)
        if len(tied) > 1:
            return self._build_ambiguous_result(
                query_id=query_id,
                raw_query=query_text,
                mentions=mentions,
                deterministic_signature=deterministic_signature,
                reason=(
                    "Multiple intent rules matched with equal confidence: "
                    + ", ".join(candidate.intent_type.value for candidate in tied)
                ),
                candidates=candidates,
                forecast_target=forecast_target,
                time_scope=time_scope,
            )

        top = candidates[0]
        secondary_intents = tuple(
            candidate.intent_type
            for candidate in candidates[1:]
            if candidate.score >= _INTENT_THRESHOLD
        )
        confidence = _confidence_for_score(top.score)
        requested = _requested_metrics_or_topics(normalized)
        query_intent = QueryIntentContract(
            query_id=query_id,
            raw_query=query_text,
            intent_type=top.intent_type,
            secondary_intents=secondary_intents,
            entity_mentions=mentions,
            requested_metrics_or_topics=requested,
            forecast_target=forecast_target,
            time_scope=time_scope,
            classification_confidence=confidence,
            needs_clarification=False,
        )
        return QueryIntentClassificationResult(
            query_intent=query_intent,
            candidates=candidates,
            matched_rules=top.matched_rules,
            matched_terms=top.matched_terms,
            deterministic_signature=deterministic_signature,
            entity_mentions_consumed=len(mentions),
            supplied_entity_refs=tuple(
                mention.entity_ref for mention in mentions if mention.entity_ref
            ),
        )

    def write_intent_audit(
        self,
        output_path: str | Path = "output/query_v2_intent_audit.json",
    ) -> QueryV2IntentAudit:
        """Run a deterministic coverage audit and persist it."""

        audit = self.build_intent_audit()
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
        audit_path: str | Path = "output/query_v2_intent_audit.json",
        report_path: str | Path = "output/query_v2_phase1_report.json",
    ) -> QueryV2Phase1Report:
        """Write the P1 intent audit and implementation report."""

        audit = self.write_intent_audit(audit_path)
        report = QueryV2Phase1Report(
            phase="P1",
            scope="Deterministic QueryIntent classification only",
            classifier="QueryIntentClassifier",
            frozen_intents_supported=tuple(intent.value for intent in QueryV2IntentType),
            audit_path=str(audit_path),
            validation_passed=audit.validation_passed,
            deterministic_repeatability_passed=(
                audit.deterministic_repeatability_passed
            ),
            ambiguity_routing_passed=audit.ambiguity_routing_passed,
            unsupported_routing_passed=audit.unsupported_routing_passed,
            entity_resolution_boundary=audit.entity_handling,
            prohibited_implementations=(
                "retrieval_planning",
                "ranking",
                "answer_assembly",
                "citation_logic",
                "divergence_handling",
                "authority_handling",
                "llm_logic",
                "entity_resolution",
                "entity_creation",
                "msil_calls",
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

    def build_intent_audit(self) -> QueryV2IntentAudit:
        """Build the deterministic P1 audit payload."""

        sample_results: list[dict[str, Any]] = []
        coverage: Counter[str] = Counter()
        repeatability_failures: list[dict[str, str]] = []
        for sample in _audit_samples():
            first = self.classify(sample["query"], entity_mentions=sample.get("entities", ()))
            second = self.classify(sample["query"], entity_mentions=sample.get("entities", ()))
            first_payload = first.model_dump(mode="json")
            second_payload = second.model_dump(mode="json")
            repeated = first_payload == second_payload
            if not repeated:
                repeatability_failures.append(
                    {
                        "query": sample["query"],
                        "first_signature": first.deterministic_signature,
                        "second_signature": second.deterministic_signature,
                    }
                )
            actual = first.query_intent.intent_type.value
            coverage[actual] += 1
            sample_results.append(
                {
                    "query": sample["query"],
                    "expected_intent": sample["expected"],
                    "actual_intent": actual,
                    "matched_rules": first.matched_rules,
                    "matched_terms": first.matched_terms,
                    "needs_clarification": first.query_intent.needs_clarification,
                    "unsupported_routed_to_unsupported": (
                        first.unsupported_routed_to_unsupported
                    ),
                    "repeatable": repeated,
                }
            )

        covered = tuple(
            intent.value
            for intent in QueryV2IntentType
            if coverage.get(intent.value, 0) > 0
        )
        missing = tuple(
            intent.value
            for intent in QueryV2IntentType
            if coverage.get(intent.value, 0) == 0
        )
        ambiguity_routing_passed = any(
            item["expected_intent"] == QueryV2IntentType.AMBIGUOUS.value
            and item["actual_intent"] == QueryV2IntentType.AMBIGUOUS.value
            and item["needs_clarification"]
            for item in sample_results
        )
        unsupported_routing_passed = any(
            item["expected_intent"] == QueryV2IntentType.UNSUPPORTED.value
            and item["actual_intent"] == QueryV2IntentType.UNSUPPORTED.value
            and item["unsupported_routed_to_unsupported"]
            for item in sample_results
        )
        deterministic_repeatability_passed = not repeatability_failures
        coverage_passed = not missing and all(
            item["expected_intent"] == item["actual_intent"]
            for item in sample_results
        )
        entity_handling = {
            "msil_called": False,
            "entity_resolution_performed": False,
            "entities_created": False,
            "supplied_entity_mentions_consumed": sum(
                len(sample.get("entities", ())) for sample in _audit_samples()
            ),
            "query_does_not_resolve_entities": True,
        }
        violations: list[dict[str, Any]] = []
        if not coverage_passed:
            violations.append(
                _violation(
                    "classification_coverage",
                    "QueryIntentClassifier",
                    "Not every frozen intent was covered by the deterministic audit.",
                    {"missing_frozen_intents": missing, "sample_results": sample_results},
                )
            )
        if not ambiguity_routing_passed:
            violations.append(
                _violation(
                    "ambiguity_routing",
                    "QueryIntentClassifier",
                    "Ambiguous audit sample did not route to clarification.",
                    sample_results,
                )
            )
        if not unsupported_routing_passed:
            violations.append(
                _violation(
                    "unsupported_routing",
                    "QueryIntentClassifier",
                    "Unsupported audit sample did not route to unsupported.",
                    sample_results,
                )
            )
        if not deterministic_repeatability_passed:
            violations.append(
                _violation(
                    "deterministic_repeatability",
                    "QueryIntentClassifier",
                    "Repeated classifications produced different results.",
                    repeatability_failures,
                )
            )

        return QueryV2IntentAudit(
            validation_passed=not violations,
            classification_coverage=dict(sorted(coverage.items())),
            frozen_intents_covered=covered,
            missing_frozen_intents=missing,
            ambiguity_routing_passed=ambiguity_routing_passed,
            unsupported_routing_passed=unsupported_routing_passed,
            deterministic_repeatability_passed=deterministic_repeatability_passed,
            entity_handling=entity_handling,
            sample_results=tuple(sample_results),
            integrity_violations=tuple(violations),
        )

    @staticmethod
    def _coerce_entity_mentions(
        entity_mentions: Iterable[QueryV2EntityMention | Mapping[str, Any]],
    ) -> tuple[QueryV2EntityMention, ...]:
        return tuple(
            mention
            if isinstance(mention, QueryV2EntityMention)
            else QueryV2EntityMention.model_validate(dict(mention))
            for mention in entity_mentions
        )

    def _score_candidates(self, normalized: str) -> tuple[QueryIntentCandidate, ...]:
        metric_matches = _metric_matches(normalized)
        candidates: list[QueryIntentCandidate] = []
        for intent_type, rules in _INTENT_RULES.items():
            score = 0
            matched_rules: list[str] = []
            matched_terms: list[str] = []
            for rule_id, weight, phrases in rules:
                matches = tuple(phrase for phrase in phrases if _phrase_matches(normalized, phrase))
                if matches:
                    score += weight * len(matches)
                    matched_rules.append(rule_id)
                    matched_terms.extend(matches)
            if intent_type == QueryV2IntentType.METRIC_LOOKUP and metric_matches:
                score += 4
                matched_rules.append("metric_lookup:metric_terms")
                matched_terms.extend(metric_matches)
            if (
                intent_type == QueryV2IntentType.COMPARISON
                and len(metric_matches) >= 2
                and _contains_any(normalized, ("compare", "versus", " vs ", "between", "against"))
            ):
                score += 3
                matched_rules.append("comparison:multiple_metric_terms")
                matched_terms.extend(metric_matches)
            if (
                intent_type == QueryV2IntentType.SOURCE_EXPLORATION
                and metric_matches
                and _contains_any(normalized, ("source", "citation", "evidence", "provenance", "selected", "chosen"))
            ):
                score += 3
                matched_rules.append("source_exploration:metric_provenance")
                matched_terms.extend(metric_matches)
            if score:
                candidates.append(
                    QueryIntentCandidate(
                        intent_type=intent_type,
                        score=score,
                        matched_rules=tuple(dict.fromkeys(matched_rules)),
                        matched_terms=tuple(dict.fromkeys(matched_terms)),
                    )
                )
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    -candidate.score,
                    _intent_priority(candidate.intent_type),
                    candidate.intent_type.value,
                ),
            )
        )

    @staticmethod
    def _is_intrinsically_ambiguous(
        normalized: str,
        candidates: tuple[QueryIntentCandidate, ...],
    ) -> bool:
        if not _contains_any(normalized, _AMBIGUOUS_PATTERNS):
            return False
        if not candidates:
            return True
        return candidates[0].score < 5

    def _build_ambiguous_result(
        self,
        *,
        query_id: str,
        raw_query: str,
        mentions: tuple[QueryV2EntityMention, ...],
        deterministic_signature: str,
        reason: str,
        candidates: tuple[QueryIntentCandidate, ...],
        forecast_target: dict[str, Any] | None,
        time_scope: dict[str, Any] | None,
    ) -> QueryIntentClassificationResult:
        prompt = (
            reason
            + " Please clarify whether you want financial metrics, qualitative analysis, "
            "timeline/source evidence, or forecast validation."
        )
        query_intent = QueryIntentContract(
            query_id=query_id,
            raw_query=raw_query,
            intent_type=QueryV2IntentType.AMBIGUOUS,
            secondary_intents=tuple(candidate.intent_type for candidate in candidates),
            entity_mentions=mentions,
            requested_metrics_or_topics=_requested_metrics_or_topics(_normalize_query(raw_query)),
            forecast_target=forecast_target,
            time_scope=time_scope,
            classification_confidence=0.5,
            needs_clarification=True,
            clarification_prompt=prompt,
        )
        return QueryIntentClassificationResult(
            query_intent=query_intent,
            candidates=candidates,
            ambiguity_routed_to_clarification=True,
            deterministic_signature=deterministic_signature,
            entity_mentions_consumed=len(mentions),
            supplied_entity_refs=tuple(
                mention.entity_ref for mention in mentions if mention.entity_ref
            ),
        )

    def _build_unsupported_result(
        self,
        *,
        query_id: str,
        raw_query: str,
        mentions: tuple[QueryV2EntityMention, ...],
        deterministic_signature: str,
        forecast_target: dict[str, Any] | None,
        time_scope: dict[str, Any] | None,
    ) -> QueryIntentClassificationResult:
        query_intent = QueryIntentContract(
            query_id=query_id,
            raw_query=raw_query,
            intent_type=QueryV2IntentType.UNSUPPORTED,
            entity_mentions=mentions,
            forecast_target=forecast_target,
            time_scope=time_scope,
            classification_confidence=0.4,
            needs_clarification=False,
        )
        return QueryIntentClassificationResult(
            query_intent=query_intent,
            unsupported_routed_to_unsupported=True,
            deterministic_signature=deterministic_signature,
            entity_mentions_consumed=len(mentions),
            supplied_entity_refs=tuple(
                mention.entity_ref for mention in mentions if mention.entity_ref
            ),
        )


def _audit_samples() -> tuple[dict[str, Any], ...]:
    resolved_entity = QueryV2EntityMention(
        raw_mention="Lucky Cement",
        entity_ref="lucky_cement",
        entity_resolution_status=QueryV2EntityResolutionStatus.RESOLVED,
    )
    return (
        {
            "query": "What is Lucky Cement's sector?",
            "expected": QueryV2IntentType.FACTUAL_LOOKUP.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "What was revenue in 2025?",
            "expected": QueryV2IntentType.METRIC_LOOKUP.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "Why did operating profit decline?",
            "expected": QueryV2IntentType.QUALITATIVE_ANALYSIS.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "Is my 2026 revenue forecast reasonable?",
            "expected": QueryV2IntentType.FORECAST_VALIDATION.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "Compare debt and cash.",
            "expected": QueryV2IntentType.COMPARISON.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "Show the corporate events timeline.",
            "expected": QueryV2IntentType.TIMELINE.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "Provide a risk analysis of the company.",
            "expected": QueryV2IntentType.RISK_ANALYSIS.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "Show the source for EPS.",
            "expected": QueryV2IntentType.SOURCE_EXPLORATION.value,
            "entities": (resolved_entity,),
        },
        {
            "query": "Tell me about Lucky.",
            "expected": QueryV2IntentType.AMBIGUOUS.value,
            "entities": (),
        },
        {
            "query": "Write a poem about cement.",
            "expected": QueryV2IntentType.UNSUPPORTED.value,
            "entities": (),
        },
    )


def _normalize_query(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9%]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_any(value: str, phrases: Iterable[str]) -> bool:
    return any(_phrase_matches(value, phrase) for phrase in phrases)


def _phrase_matches(value: str, phrase: str) -> bool:
    normalized_phrase = _normalize_query(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {value} "


def _metric_matches(normalized: str) -> tuple[str, ...]:
    matches: list[str] = []
    for canonical, aliases in _METRIC_TERMS.items():
        if any(_phrase_matches(normalized, alias) for alias in aliases):
            matches.append(canonical)
    return tuple(dict.fromkeys(matches))


def _requested_metrics_or_topics(normalized: str) -> tuple[str, ...]:
    metrics = list(_metric_matches(normalized))
    topic_terms = (
        "risk",
        "strategy",
        "outlook",
        "governance",
        "sustainability",
        "source",
        "timeline",
        "forecast",
    )
    for topic in topic_terms:
        if _phrase_matches(normalized, topic):
            metrics.append(topic)
    return tuple(dict.fromkeys(metrics))


def _confidence_for_score(score: int) -> float:
    return min(0.95, round(0.55 + (score * 0.05), 2))


def _intent_priority(intent_type: QueryV2IntentType) -> int:
    priority = {
        QueryV2IntentType.FORECAST_VALIDATION: 0,
        QueryV2IntentType.COMPARISON: 1,
        QueryV2IntentType.SOURCE_EXPLORATION: 2,
        QueryV2IntentType.RISK_ANALYSIS: 3,
        QueryV2IntentType.QUALITATIVE_ANALYSIS: 4,
        QueryV2IntentType.TIMELINE: 5,
        QueryV2IntentType.METRIC_LOOKUP: 6,
        QueryV2IntentType.FACTUAL_LOOKUP: 7,
    }
    return priority.get(intent_type, 99)


def _deterministic_signature(
    *,
    raw_query: str,
    entity_mentions: tuple[QueryV2EntityMention, ...],
    forecast_target: dict[str, Any] | None,
    time_scope: dict[str, Any] | None,
) -> str:
    payload = {
        "raw_query": raw_query,
        "entity_mentions": [
            mention.model_dump(mode="json") for mention in entity_mentions
        ],
        "forecast_target": forecast_target,
        "time_scope": time_scope,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
    "QueryIntentCandidate",
    "QueryIntentClassificationResult",
    "QueryIntentClassifier",
    "QueryV2IntentAudit",
    "QueryV2Phase1Report",
]
