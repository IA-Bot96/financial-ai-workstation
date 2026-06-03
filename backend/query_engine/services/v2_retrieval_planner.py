"""Deterministic Query Engine v2 retrieval planning.

This Phase P2 module consumes only the frozen QueryIntent contract and emits
RetrievalPlan/EvidenceRequest contracts. It does not retrieve evidence or call
MSIL, QAE, FVE, or any LLM.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.v2_contracts import (
    EvidenceRequestContract,
    QueryIntentContract,
    QueryV2EntityMention,
    QueryV2EntityResolutionStatus,
    QueryV2IntentType,
    QueryV2TargetDomain,
    RetrievalPlanContract,
    RetrievalPlanStepContract,
)


_SUPPORTED_PLANNING_INTENTS: tuple[QueryV2IntentType, ...] = (
    QueryV2IntentType.FACTUAL_LOOKUP,
    QueryV2IntentType.METRIC_LOOKUP,
    QueryV2IntentType.QUALITATIVE_ANALYSIS,
    QueryV2IntentType.FORECAST_VALIDATION,
    QueryV2IntentType.COMPARISON,
    QueryV2IntentType.TIMELINE,
    QueryV2IntentType.RISK_ANALYSIS,
    QueryV2IntentType.SOURCE_EXPLORATION,
)


class RetrievalPlanningResult(BaseModel):
    """Plan and evidence-request output for one QueryIntent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_intent: QueryIntentContract
    retrieval_plan: RetrievalPlanContract
    evidence_requests: tuple[EvidenceRequestContract, ...] = Field(default_factory=tuple)
    planned_intents: tuple[QueryV2IntentType, ...] = Field(default_factory=tuple)
    rule_ids: tuple[str, ...] = Field(default_factory=tuple)
    unsupported_routed_to_unsupported: bool = False
    resolved_entity_enforcement_passed: bool = True
    metric_plan_has_fve_step: bool = False
    multi_intent_decomposition_applied: bool = False
    msil_called: bool = False
    qae_called: bool = False
    fve_called: bool = False


class QueryV2PlanningAudit(BaseModel):
    """Audit payload for Query v2 Phase P2 retrieval planning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    plans_generated: int = Field(..., ge=0)
    evidence_requests_generated: int = Field(..., ge=0)
    rule_coverage: dict[str, int]
    metric_plans_total: int = Field(..., ge=0)
    metric_plans_with_fve_step: int = Field(..., ge=0)
    metric_plan_fve_requirement_passed: bool
    unsupported_routing_passed: bool
    resolved_entity_enforcement_passed: bool
    multi_intent_decomposition_coverage_passed: bool
    sample_results: tuple[dict[str, Any], ...]
    engine_call_boundaries: dict[str, bool]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryV2Phase2Report(BaseModel):
    """Implementation report for Query v2 Phase P2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    planner: str
    builders: tuple[str, ...]
    supported_intents: tuple[str, ...]
    audit_path: str
    validation_passed: bool
    plans_generated: int = Field(..., ge=0)
    evidence_requests_generated: int = Field(..., ge=0)
    metric_plan_fve_requirement_passed: bool
    unsupported_routing_passed: bool
    resolved_entity_enforcement_passed: bool
    multi_intent_decomposition_coverage_passed: bool
    prohibited_implementations: tuple[str, ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class RetrievalPlanBuilder:
    """Build deterministic RetrievalPlan contracts from QueryIntent contracts."""

    def build(self, query_intent: QueryIntentContract) -> RetrievalPlanContract:
        """Build one retrieval plan from a frozen QueryIntent contract."""

        plan_id = _plan_id(query_intent)
        resolved_entity_refs = _resolved_entity_refs(query_intent.entity_mentions)
        unsupported_reason = self._unsupported_reason(query_intent, resolved_entity_refs)
        if unsupported_reason:
            return RetrievalPlanContract(
                plan_id=plan_id,
                intent_ref=query_intent.query_id,
                entity_refs=resolved_entity_refs,
                plan_steps=(),
                is_multi_source=False,
                unsupported_reason=unsupported_reason,
            )

        planned_intents = _planned_intents(query_intent)
        steps: list[RetrievalPlanStepContract] = []
        seen_rule_ids: set[str] = set()
        for intent_index, intent_type in enumerate(planned_intents, start=1):
            for template in _plan_templates(intent_type):
                if template.rule_id in seen_rule_ids:
                    continue
                seen_rule_ids.add(template.rule_id)
                steps.append(
                    RetrievalPlanStepContract(
                        step_id=_step_id(
                            intent_index=intent_index,
                            step_index=len(steps) + 1,
                            rule_id=template.rule_id,
                        ),
                        target_domain=template.target_domain,
                        source_types=template.source_types,
                        content_classes=template.content_classes,
                        purpose=template.purpose,
                        required_authority_floor=template.required_authority_floor,
                        recency_requirement=template.recency_requirement,
                        rule_id=template.rule_id,
                    )
                )

        return RetrievalPlanContract(
            plan_id=plan_id,
            intent_ref=query_intent.query_id,
            entity_refs=resolved_entity_refs,
            plan_steps=tuple(steps),
            is_multi_source=_is_multi_source(steps),
            unsupported_reason=None,
        )

    @staticmethod
    def _unsupported_reason(
        query_intent: QueryIntentContract,
        resolved_entity_refs: tuple[str, ...],
    ) -> str | None:
        if query_intent.intent_type == QueryV2IntentType.UNSUPPORTED:
            return "Unsupported QueryIntent cannot be planned."
        if query_intent.intent_type == QueryV2IntentType.AMBIGUOUS:
            return "Ambiguous QueryIntent requires clarification before planning."
        if query_intent.needs_clarification:
            return "QueryIntent requires clarification before planning."
        if query_intent.intent_type not in _SUPPORTED_PLANNING_INTENTS:
            return f"Intent is not supported by P2 planning: {query_intent.intent_type.value}."
        if _has_unresolved_entity_mentions(query_intent.entity_mentions):
            return "Retrieval planning requires MSIL-resolved entity references."
        if not resolved_entity_refs:
            return "Retrieval planning requires at least one resolved entity_ref."
        return None


class EvidenceRequestBuilder:
    """Build inert EvidenceRequest contracts from deterministic plans."""

    def build(
        self,
        retrieval_plan: RetrievalPlanContract,
        query_intent: QueryIntentContract,
    ) -> tuple[EvidenceRequestContract, ...]:
        """Build one request per plan step and resolved entity."""

        if not retrieval_plan.plan_steps:
            return ()

        requests: list[EvidenceRequestContract] = []
        for step in retrieval_plan.plan_steps:
            for entity_index, entity_ref in enumerate(
                retrieval_plan.entity_refs,
                start=1,
            ):
                requests.append(
                    EvidenceRequestContract(
                        request_id=_request_id(
                            plan_id=retrieval_plan.plan_id,
                            step_id=step.step_id,
                            entity_index=entity_index,
                        ),
                        plan_step_ref=step.step_id,
                        target_domain=step.target_domain,
                        entity_ref=entity_ref,
                        selectors={
                            "primary_intent": query_intent.intent_type.value,
                            "secondary_intents": [
                                intent.value for intent in query_intent.secondary_intents
                            ],
                            "requested_metrics_or_topics": list(
                                query_intent.requested_metrics_or_topics
                            ),
                            "source_types": list(step.source_types),
                            "content_classes": list(step.content_classes),
                            "purpose": step.purpose,
                            "rule_id": step.rule_id,
                            "forecast_target": query_intent.forecast_target,
                            "time_scope": query_intent.time_scope,
                        },
                        authority_floor=step.required_authority_floor,
                        recency_window=step.recency_requirement,
                        max_results=25,
                    )
                )
        return tuple(requests)


class RetrievalPlanner:
    """Planning-only Query v2 P2 orchestrator."""

    def __init__(
        self,
        *,
        plan_builder: RetrievalPlanBuilder | None = None,
        request_builder: EvidenceRequestBuilder | None = None,
    ) -> None:
        self._plan_builder = plan_builder or RetrievalPlanBuilder()
        self._request_builder = request_builder or EvidenceRequestBuilder()

    def plan(self, query_intent: QueryIntentContract) -> RetrievalPlanningResult:
        """Build deterministic plan and inert evidence requests."""

        retrieval_plan = self._plan_builder.build(query_intent)
        evidence_requests = self._request_builder.build(retrieval_plan, query_intent)
        planned_intents = _planned_intents(query_intent) if retrieval_plan.plan_steps else ()
        rule_ids = tuple(step.rule_id for step in retrieval_plan.plan_steps)
        return RetrievalPlanningResult(
            query_intent=query_intent,
            retrieval_plan=retrieval_plan,
            evidence_requests=evidence_requests,
            planned_intents=planned_intents,
            rule_ids=rule_ids,
            unsupported_routed_to_unsupported=bool(
                retrieval_plan.unsupported_reason
                and query_intent.intent_type
                in {QueryV2IntentType.UNSUPPORTED, QueryV2IntentType.AMBIGUOUS}
            ),
            resolved_entity_enforcement_passed=(
                bool(retrieval_plan.unsupported_reason)
                if _has_unresolved_entity_mentions(query_intent.entity_mentions)
                or not _resolved_entity_refs(query_intent.entity_mentions)
                else all(request.entity_ref for request in evidence_requests)
            ),
            metric_plan_has_fve_step=_has_fve_integrity_step(retrieval_plan),
            multi_intent_decomposition_applied=(
                bool(query_intent.secondary_intents) and len(planned_intents) > 1
            ),
        )

    def write_planning_audit(
        self,
        output_path: str | Path = "output/query_v2_planning_audit.json",
    ) -> QueryV2PlanningAudit:
        """Run and persist the deterministic P2 planning audit."""

        audit = self.build_planning_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase2_report(
        self,
        *,
        audit_path: str | Path = "output/query_v2_planning_audit.json",
        report_path: str | Path = "output/query_v2_phase2_report.json",
    ) -> QueryV2Phase2Report:
        """Write the P2 planning audit and implementation report."""

        audit = self.write_planning_audit(audit_path)
        report = QueryV2Phase2Report(
            phase="P2",
            scope="Deterministic retrieval planning only",
            planner="RetrievalPlanner",
            builders=("RetrievalPlanBuilder", "EvidenceRequestBuilder"),
            supported_intents=tuple(intent.value for intent in _SUPPORTED_PLANNING_INTENTS),
            audit_path=str(audit_path),
            validation_passed=audit.validation_passed,
            plans_generated=audit.plans_generated,
            evidence_requests_generated=audit.evidence_requests_generated,
            metric_plan_fve_requirement_passed=(
                audit.metric_plan_fve_requirement_passed
            ),
            unsupported_routing_passed=audit.unsupported_routing_passed,
            resolved_entity_enforcement_passed=(
                audit.resolved_entity_enforcement_passed
            ),
            multi_intent_decomposition_coverage_passed=(
                audit.multi_intent_decomposition_coverage_passed
            ),
            prohibited_implementations=(
                "evidence_retrieval",
                "ranking",
                "answer_assembly",
                "citation_logic",
                "divergence_presentation",
                "authority_presentation",
                "msil_calls",
                "qae_calls",
                "fve_calls",
                "llm_logic",
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

    def build_planning_audit(self) -> QueryV2PlanningAudit:
        """Build the deterministic planning audit over representative intents."""

        sample_results: list[dict[str, Any]] = []
        rule_coverage: Counter[str] = Counter()
        plans_generated = 0
        evidence_requests_generated = 0
        metric_plans_total = 0
        metric_plans_with_fve_step = 0
        unsupported_routed = False
        resolved_entity_enforced = False
        multi_intent_covered = False

        for sample in _audit_intents():
            result = self.plan(sample)
            if result.retrieval_plan.plan_steps:
                plans_generated += 1
            evidence_requests_generated += len(result.evidence_requests)
            for rule_id in result.rule_ids:
                rule_coverage[rule_id] += 1
            if (
                sample.intent_type == QueryV2IntentType.METRIC_LOOKUP
                and result.retrieval_plan.plan_steps
            ):
                metric_plans_total += 1
                if result.metric_plan_has_fve_step:
                    metric_plans_with_fve_step += 1
            if sample.intent_type == QueryV2IntentType.UNSUPPORTED:
                unsupported_routed = (
                    unsupported_routed or result.unsupported_routed_to_unsupported
                )
            if _has_unresolved_entity_mentions(sample.entity_mentions):
                resolved_entity_enforced = (
                    resolved_entity_enforced
                    or bool(result.retrieval_plan.unsupported_reason)
                )
            if sample.secondary_intents:
                multi_intent_covered = (
                    multi_intent_covered
                    or result.multi_intent_decomposition_applied
                )
            sample_results.append(
                {
                    "query_id": sample.query_id,
                    "intent_type": sample.intent_type.value,
                    "secondary_intents": [
                        intent.value for intent in sample.secondary_intents
                    ],
                    "plan_id": result.retrieval_plan.plan_id,
                    "plan_step_count": len(result.retrieval_plan.plan_steps),
                    "evidence_request_count": len(result.evidence_requests),
                    "rule_ids": result.rule_ids,
                    "unsupported_reason": result.retrieval_plan.unsupported_reason,
                    "metric_plan_has_fve_step": result.metric_plan_has_fve_step,
                    "resolved_entity_enforcement_passed": (
                        result.resolved_entity_enforcement_passed
                    ),
                    "multi_intent_decomposition_applied": (
                        result.multi_intent_decomposition_applied
                    ),
                }
            )

        metric_fve_passed = (
            metric_plans_total > 0
            and metric_plans_total == metric_plans_with_fve_step
        )
        required_rules = _required_rule_ids()
        missing_rules = tuple(
            rule_id for rule_id in required_rules if rule_coverage.get(rule_id, 0) == 0
        )
        violations: list[dict[str, Any]] = []
        if missing_rules:
            violations.append(
                _violation(
                    "rule_coverage",
                    "RetrievalPlanner",
                    "Not every deterministic planning rule was covered by the audit.",
                    {"missing_rules": missing_rules},
                )
            )
        if not metric_fve_passed:
            violations.append(
                _violation(
                    "metric_lookup_fve_step",
                    "RetrievalPlanner",
                    "Metric lookup plans did not all include an FVE integrity step.",
                    {
                        "metric_plans_total": metric_plans_total,
                        "metric_plans_with_fve_step": metric_plans_with_fve_step,
                    },
                )
            )
        if not unsupported_routed:
            violations.append(
                _violation(
                    "unsupported_routing",
                    "RetrievalPlanner",
                    "Unsupported intent did not produce unsupported plan.",
                    sample_results,
                )
            )
        if not resolved_entity_enforced:
            violations.append(
                _violation(
                    "resolved_entity_enforcement",
                    "RetrievalPlanner",
                    "Unresolved entity audit sample did not block planning.",
                    sample_results,
                )
            )
        if not multi_intent_covered:
            violations.append(
                _violation(
                    "multi_intent_decomposition",
                    "RetrievalPlanner",
                    "Secondary intents were not decomposed into plan steps.",
                    sample_results,
                )
            )

        return QueryV2PlanningAudit(
            validation_passed=not violations,
            plans_generated=plans_generated,
            evidence_requests_generated=evidence_requests_generated,
            rule_coverage=dict(sorted(rule_coverage.items())),
            metric_plans_total=metric_plans_total,
            metric_plans_with_fve_step=metric_plans_with_fve_step,
            metric_plan_fve_requirement_passed=metric_fve_passed,
            unsupported_routing_passed=unsupported_routed,
            resolved_entity_enforcement_passed=resolved_entity_enforced,
            multi_intent_decomposition_coverage_passed=multi_intent_covered,
            sample_results=tuple(sample_results),
            engine_call_boundaries={
                "msil_called": False,
                "qae_called": False,
                "fve_called": False,
                "llm_called": False,
            },
            integrity_violations=tuple(violations),
        )


class _PlanStepTemplate(BaseModel):
    """Internal immutable plan-step template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    target_domain: QueryV2TargetDomain
    source_types: tuple[str, ...]
    content_classes: tuple[str, ...]
    purpose: str
    required_authority_floor: str
    recency_requirement: dict[str, Any]


def _plan_templates(intent_type: QueryV2IntentType) -> tuple[_PlanStepTemplate, ...]:
    templates = _PLAN_TEMPLATES.get(intent_type)
    if templates is None:
        return ()
    return templates


_PLAN_TEMPLATES: dict[QueryV2IntentType, tuple[_PlanStepTemplate, ...]] = {
    QueryV2IntentType.FACTUAL_LOOKUP: (
        _PlanStepTemplate(
            rule_id="p2.factual_lookup.msil_facts",
            target_domain=QueryV2TargetDomain.MSIL,
            source_types=(
                "annual_report",
                "psx_announcements",
                "secp_notices",
                "company_overview",
            ),
            content_classes=("narrative_claim", "corporate_event"),
            purpose="Retrieve entity-resolved factual evidence from MSIL.",
            required_authority_floor="official_issuer_unaudited",
            recency_requirement={"mode": "current_or_latest_available"},
        ),
    ),
    QueryV2IntentType.METRIC_LOOKUP: (
        _PlanStepTemplate(
            rule_id="p2.metric_lookup.ocr_numeric_claims",
            target_domain=QueryV2TargetDomain.OCR_VIA_MSIL,
            source_types=("annual_report",),
            content_classes=("numeric_claim",),
            purpose="Retrieve annual-report numeric metric evidence through MSIL.",
            required_authority_floor="audited_issuer",
            recency_requirement={"mode": "all_available_periods"},
        ),
        _PlanStepTemplate(
            rule_id="p2.metric_lookup.fve_integrity_required",
            target_domain=QueryV2TargetDomain.FVE,
            source_types=("forecast_validation_engine",),
            content_classes=("numeric_integrity_status",),
            purpose="Retrieve FVE metric integrity status required for every metric lookup.",
            required_authority_floor="fve_validated",
            recency_requirement={"mode": "matching_metric_periods"},
        ),
    ),
    QueryV2IntentType.QUALITATIVE_ANALYSIS: (
        _PlanStepTemplate(
            rule_id="p2.qualitative_analysis.qae_themes",
            target_domain=QueryV2TargetDomain.QAE,
            source_types=("annual_report",),
            content_classes=("qualitative_theme",),
            purpose="Retrieve QAE-authored themes for qualitative analysis.",
            required_authority_floor="qae_analyzed",
            recency_requirement={"mode": "report_period"},
        ),
        _PlanStepTemplate(
            rule_id="p2.qualitative_analysis.msil_narratives",
            target_domain=QueryV2TargetDomain.MSIL,
            source_types=("annual_report", "psx_announcements", "secp_notices"),
            content_classes=("narrative_claim",),
            purpose="Retrieve source narrative claims as authored by MSIL.",
            required_authority_floor="audited_issuer",
            recency_requirement={"mode": "report_period_or_later"},
        ),
    ),
    QueryV2IntentType.FORECAST_VALIDATION: (
        _PlanStepTemplate(
            rule_id="p2.forecast_validation.fve_validation",
            target_domain=QueryV2TargetDomain.FVE,
            source_types=("forecast_validation_engine",),
            content_classes=("forecast_validation_result",),
            purpose="Retrieve FVE-authored forecast validation result.",
            required_authority_floor="fve_validated",
            recency_requirement={"mode": "forecast_period"},
        ),
        _PlanStepTemplate(
            rule_id="p2.forecast_validation.ocr_baseline",
            target_domain=QueryV2TargetDomain.OCR_VIA_MSIL,
            source_types=("annual_report",),
            content_classes=("numeric_claim",),
            purpose="Retrieve historical numeric baseline evidence for forecast context.",
            required_authority_floor="audited_issuer",
            recency_requirement={"mode": "historical_baseline"},
        ),
    ),
    QueryV2IntentType.COMPARISON: (
        _PlanStepTemplate(
            rule_id="p2.comparison.ocr_numeric_claims",
            target_domain=QueryV2TargetDomain.OCR_VIA_MSIL,
            source_types=("annual_report",),
            content_classes=("numeric_claim",),
            purpose="Retrieve comparable metric values through MSIL.",
            required_authority_floor="audited_issuer",
            recency_requirement={"mode": "all_available_periods"},
        ),
        _PlanStepTemplate(
            rule_id="p2.comparison.fve_integrity",
            target_domain=QueryV2TargetDomain.FVE,
            source_types=("forecast_validation_engine",),
            content_classes=("numeric_integrity_status",),
            purpose="Retrieve integrity status for compared metrics.",
            required_authority_floor="fve_validated",
            recency_requirement={"mode": "matching_metric_periods"},
        ),
    ),
    QueryV2IntentType.TIMELINE: (
        _PlanStepTemplate(
            rule_id="p2.timeline.msil_events",
            target_domain=QueryV2TargetDomain.MSIL,
            source_types=(
                "annual_report",
                "psx_announcements",
                "secp_notices",
                "company_payouts",
            ),
            content_classes=("corporate_event", "narrative_claim"),
            purpose="Retrieve MSIL timeline and corporate-event evidence.",
            required_authority_floor="official_issuer_unaudited",
            recency_requirement={"mode": "chronological_all"},
        ),
    ),
    QueryV2IntentType.RISK_ANALYSIS: (
        _PlanStepTemplate(
            rule_id="p2.risk_analysis.qae_risk_themes",
            target_domain=QueryV2TargetDomain.QAE,
            source_types=("annual_report",),
            content_classes=("qualitative_theme",),
            purpose="Retrieve QAE-authored risk and governance themes.",
            required_authority_floor="qae_analyzed",
            recency_requirement={"mode": "report_period"},
        ),
        _PlanStepTemplate(
            rule_id="p2.risk_analysis.msil_risk_narratives",
            target_domain=QueryV2TargetDomain.MSIL,
            source_types=("annual_report", "secp_notices", "psx_announcements"),
            content_classes=("narrative_claim", "corporate_event"),
            purpose="Retrieve risk-related narrative and event evidence from MSIL.",
            required_authority_floor="audited_issuer",
            recency_requirement={"mode": "report_period_or_later"},
        ),
    ),
    QueryV2IntentType.SOURCE_EXPLORATION: (
        _PlanStepTemplate(
            rule_id="p2.source_exploration.msil_provenance",
            target_domain=QueryV2TargetDomain.MSIL,
            source_types=(
                "annual_report",
                "psx_announcements",
                "secp_notices",
                "company_payouts",
                "company_overview",
            ),
            content_classes=("numeric_claim", "narrative_claim", "corporate_event"),
            purpose="Retrieve provenance-backed evidence references for source exploration.",
            required_authority_floor="provenanced_source",
            recency_requirement={"mode": "all_available"},
        ),
    ),
}


def _audit_intents() -> tuple[QueryIntentContract, ...]:
    resolved = QueryV2EntityMention(
        raw_mention="Lucky Cement",
        entity_ref="lucky_cement",
        entity_resolution_status=QueryV2EntityResolutionStatus.RESOLVED,
    )
    unresolved = QueryV2EntityMention(
        raw_mention="Lucky",
        entity_ref=None,
        entity_resolution_status=QueryV2EntityResolutionStatus.UNRESOLVED,
    )
    return (
        _intent("q_factual", QueryV2IntentType.FACTUAL_LOOKUP, resolved),
        _intent("q_metric", QueryV2IntentType.METRIC_LOOKUP, resolved, ("revenue",)),
        _intent("q_qualitative", QueryV2IntentType.QUALITATIVE_ANALYSIS, resolved),
        _intent(
            "q_forecast",
            QueryV2IntentType.FORECAST_VALIDATION,
            resolved,
            ("revenue",),
            forecast_target={"metric": "revenue", "year": 2026, "value": 100.0},
        ),
        _intent(
            "q_comparison",
            QueryV2IntentType.COMPARISON,
            resolved,
            ("debt", "cash"),
        ),
        _intent("q_timeline", QueryV2IntentType.TIMELINE, resolved),
        _intent("q_risk", QueryV2IntentType.RISK_ANALYSIS, resolved),
        _intent("q_source", QueryV2IntentType.SOURCE_EXPLORATION, resolved),
        _intent("q_unsupported", QueryV2IntentType.UNSUPPORTED, resolved),
        _intent("q_unresolved_entity", QueryV2IntentType.METRIC_LOOKUP, unresolved),
        _intent(
            "q_multi_intent",
            QueryV2IntentType.COMPARISON,
            resolved,
            ("revenue", "operating_profit"),
            secondary_intents=(
                QueryV2IntentType.METRIC_LOOKUP,
                QueryV2IntentType.QUALITATIVE_ANALYSIS,
            ),
        ),
    )


def _intent(
    query_id: str,
    intent_type: QueryV2IntentType,
    entity: QueryV2EntityMention,
    requested_metrics_or_topics: tuple[str, ...] = (),
    *,
    secondary_intents: tuple[QueryV2IntentType, ...] = (),
    forecast_target: dict[str, Any] | None = None,
) -> QueryIntentContract:
    return QueryIntentContract(
        query_id=query_id,
        raw_query=query_id.replace("_", " "),
        intent_type=intent_type,
        secondary_intents=secondary_intents,
        entity_mentions=(entity,),
        requested_metrics_or_topics=requested_metrics_or_topics,
        forecast_target=forecast_target,
        classification_confidence=0.9,
        needs_clarification=False,
    )


def _planned_intents(query_intent: QueryIntentContract) -> tuple[QueryV2IntentType, ...]:
    planned: list[QueryV2IntentType] = []
    for intent in (query_intent.intent_type, *query_intent.secondary_intents):
        if intent in _SUPPORTED_PLANNING_INTENTS and intent not in planned:
            planned.append(intent)
    return tuple(planned)


def _resolved_entity_refs(
    entity_mentions: tuple[QueryV2EntityMention, ...],
) -> tuple[str, ...]:
    refs = [
        mention.entity_ref
        for mention in entity_mentions
        if (
            mention.entity_resolution_status == QueryV2EntityResolutionStatus.RESOLVED
            and mention.entity_ref
        )
    ]
    return tuple(dict.fromkeys(refs))


def _has_unresolved_entity_mentions(
    entity_mentions: tuple[QueryV2EntityMention, ...],
) -> bool:
    return any(
        mention.entity_resolution_status != QueryV2EntityResolutionStatus.RESOLVED
        for mention in entity_mentions
    )


def _has_fve_integrity_step(retrieval_plan: RetrievalPlanContract) -> bool:
    return any(
        step.target_domain == QueryV2TargetDomain.FVE
        and "integrity" in step.rule_id
        for step in retrieval_plan.plan_steps
    )


def _is_multi_source(steps: list[RetrievalPlanStepContract]) -> bool:
    domains = {step.target_domain for step in steps}
    sources = {source for step in steps for source in step.source_types}
    return len(domains) > 1 or len(sources) > 1


def _required_rule_ids() -> tuple[str, ...]:
    rule_ids = [
        template.rule_id
        for intent_type in _SUPPORTED_PLANNING_INTENTS
        for template in _plan_templates(intent_type)
    ]
    return tuple(dict.fromkeys(rule_ids))


def _plan_id(query_intent: QueryIntentContract) -> str:
    encoded = json.dumps(
        {
            "query_id": query_intent.query_id,
            "intent_type": query_intent.intent_type.value,
            "secondary_intents": [
                intent.value for intent in query_intent.secondary_intents
            ],
            "entity_refs": _resolved_entity_refs(query_intent.entity_mentions),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"query_v2_plan_{digest}"


def _step_id(*, intent_index: int, step_index: int, rule_id: str) -> str:
    return f"step_{intent_index}_{step_index}_{_slug(rule_id)}"


def _request_id(*, plan_id: str, step_id: str, entity_index: int) -> str:
    return f"request_{_slug(plan_id)}_{_slug(step_id)}_{entity_index}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


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
    "EvidenceRequestBuilder",
    "QueryV2Phase2Report",
    "QueryV2PlanningAudit",
    "RetrievalPlanBuilder",
    "RetrievalPlanner",
    "RetrievalPlanningResult",
]
