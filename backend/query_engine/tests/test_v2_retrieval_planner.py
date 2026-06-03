"""Tests for Query Engine v2 Phase P2 deterministic retrieval planning."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from query_engine.models import (  # noqa: E402
    QueryIntentContract,
    QueryV2EntityMention,
    QueryV2EntityResolutionStatus,
    QueryV2IntentType,
    QueryV2TargetDomain,
)
from query_engine.services import RetrievalPlanner  # noqa: E402


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolved_entity() -> QueryV2EntityMention:
    return QueryV2EntityMention(
        raw_mention="Lucky Cement",
        entity_ref="lucky_cement",
        entity_resolution_status=QueryV2EntityResolutionStatus.RESOLVED,
    )


def _unresolved_entity() -> QueryV2EntityMention:
    return QueryV2EntityMention(
        raw_mention="Lucky",
        entity_ref=None,
        entity_resolution_status=QueryV2EntityResolutionStatus.UNRESOLVED,
    )


def _intent(
    intent_type: QueryV2IntentType,
    *,
    entity: QueryV2EntityMention | None = None,
    secondary_intents: tuple[QueryV2IntentType, ...] = (),
    requested_metrics_or_topics: tuple[str, ...] = (),
    needs_clarification: bool = False,
) -> QueryIntentContract:
    return QueryIntentContract(
        query_id=f"q_{intent_type.value}",
        raw_query=f"test {intent_type.value}",
        intent_type=intent_type,
        secondary_intents=secondary_intents,
        entity_mentions=(entity or _resolved_entity(),),
        requested_metrics_or_topics=requested_metrics_or_topics,
        classification_confidence=0.9,
        needs_clarification=needs_clarification,
        clarification_prompt="Please clarify." if needs_clarification else None,
    )


def test_supported_intents_generate_auditable_plan_steps_and_requests() -> None:
    planner = RetrievalPlanner()
    supported = (
        QueryV2IntentType.FACTUAL_LOOKUP,
        QueryV2IntentType.METRIC_LOOKUP,
        QueryV2IntentType.QUALITATIVE_ANALYSIS,
        QueryV2IntentType.FORECAST_VALIDATION,
        QueryV2IntentType.COMPARISON,
        QueryV2IntentType.TIMELINE,
        QueryV2IntentType.RISK_ANALYSIS,
        QueryV2IntentType.SOURCE_EXPLORATION,
    )

    for intent_type in supported:
        result = planner.plan(_intent(intent_type))

        assert result.retrieval_plan.unsupported_reason is None
        assert result.retrieval_plan.entity_refs == ("lucky_cement",)
        assert result.retrieval_plan.plan_steps
        assert len(result.evidence_requests) == len(result.retrieval_plan.plan_steps)
        for step in result.retrieval_plan.plan_steps:
            assert step.step_id
            assert step.target_domain
            assert step.source_types
            assert step.content_classes
            assert step.purpose
            assert step.required_authority_floor
            assert step.recency_requirement
            assert step.rule_id.startswith("p2.")
        for request in result.evidence_requests:
            assert request.entity_ref == "lucky_cement"
            assert request.plan_step_ref
            assert request.selectors["rule_id"].startswith("p2.")
            assert request.authority_floor
            assert request.recency_window


def test_metric_lookup_always_includes_fve_integrity_step_and_request() -> None:
    result = RetrievalPlanner().plan(
        _intent(
            QueryV2IntentType.METRIC_LOOKUP,
            requested_metrics_or_topics=("revenue",),
        )
    )

    fve_steps = [
        step
        for step in result.retrieval_plan.plan_steps
        if step.target_domain == QueryV2TargetDomain.FVE
    ]
    fve_requests = [
        request
        for request in result.evidence_requests
        if request.target_domain == QueryV2TargetDomain.FVE
    ]

    assert result.metric_plan_has_fve_step is True
    assert any(step.rule_id == "p2.metric_lookup.fve_integrity_required" for step in fve_steps)
    assert len(fve_requests) == len(fve_steps)
    assert fve_requests[0].selectors["requested_metrics_or_topics"] == ["revenue"]


def test_unresolved_entity_blocks_plan_and_requests() -> None:
    result = RetrievalPlanner().plan(
        _intent(QueryV2IntentType.METRIC_LOOKUP, entity=_unresolved_entity())
    )

    assert result.retrieval_plan.plan_steps == ()
    assert result.evidence_requests == ()
    assert "MSIL-resolved entity" in result.retrieval_plan.unsupported_reason
    assert result.resolved_entity_enforcement_passed is True
    assert result.msil_called is False
    assert result.qae_called is False
    assert result.fve_called is False


def test_unsupported_and_ambiguous_intents_route_to_unsupported_plan() -> None:
    unsupported = RetrievalPlanner().plan(_intent(QueryV2IntentType.UNSUPPORTED))
    ambiguous = RetrievalPlanner().plan(
        _intent(
            QueryV2IntentType.AMBIGUOUS,
            entity=_unresolved_entity(),
            needs_clarification=True,
        )
    )

    assert unsupported.retrieval_plan.plan_steps == ()
    assert unsupported.retrieval_plan.unsupported_reason
    assert unsupported.unsupported_routed_to_unsupported is True
    assert ambiguous.retrieval_plan.plan_steps == ()
    assert "Ambiguous" in ambiguous.retrieval_plan.unsupported_reason
    assert ambiguous.unsupported_routed_to_unsupported is True


def test_multi_intent_decomposition_adds_secondary_plan_steps() -> None:
    result = RetrievalPlanner().plan(
        _intent(
            QueryV2IntentType.COMPARISON,
            secondary_intents=(
                QueryV2IntentType.METRIC_LOOKUP,
                QueryV2IntentType.QUALITATIVE_ANALYSIS,
            ),
            requested_metrics_or_topics=("revenue", "operating_profit"),
        )
    )

    rule_ids = set(result.rule_ids)
    assert result.multi_intent_decomposition_applied is True
    assert QueryV2IntentType.COMPARISON in result.planned_intents
    assert QueryV2IntentType.METRIC_LOOKUP in result.planned_intents
    assert QueryV2IntentType.QUALITATIVE_ANALYSIS in result.planned_intents
    assert "p2.comparison.ocr_numeric_claims" in rule_ids
    assert "p2.metric_lookup.fve_integrity_required" in rule_ids
    assert "p2.qualitative_analysis.qae_themes" in rule_ids


def test_evidence_requests_are_resolved_entity_only_for_multiple_entities() -> None:
    second_entity = QueryV2EntityMention(
        raw_mention="Millat Tractors",
        entity_ref="millat_tractors",
        entity_resolution_status=QueryV2EntityResolutionStatus.RESOLVED,
    )
    query_intent = QueryIntentContract(
        query_id="q_compare_entities",
        raw_query="Compare revenue for Lucky and Millat.",
        intent_type=QueryV2IntentType.COMPARISON,
        entity_mentions=(_resolved_entity(), second_entity),
        requested_metrics_or_topics=("revenue",),
        classification_confidence=0.9,
        needs_clarification=False,
    )

    result = RetrievalPlanner().plan(query_intent)

    assert result.retrieval_plan.entity_refs == ("lucky_cement", "millat_tractors")
    assert {request.entity_ref for request in result.evidence_requests} == {
        "lucky_cement",
        "millat_tractors",
    }
    assert len(result.evidence_requests) == (
        len(result.retrieval_plan.plan_steps) * 2
    )


def test_planner_writes_planning_audit_and_phase2_report() -> None:
    tmp_path = _workspace_tmp("v2_planning_audit")
    audit_path = tmp_path / "query_v2_planning_audit.json"
    report_path = tmp_path / "query_v2_phase2_report.json"

    report = RetrievalPlanner().write_phase2_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["validation_passed"] is True
    assert audit["plans_generated"] >= 8
    assert audit["metric_plan_fve_requirement_passed"] is True
    assert audit["unsupported_routing_passed"] is True
    assert audit["resolved_entity_enforcement_passed"] is True
    assert audit["multi_intent_decomposition_coverage_passed"] is True
    assert audit["engine_call_boundaries"]["msil_called"] is False
    assert audit["engine_call_boundaries"]["qae_called"] is False
    assert audit["engine_call_boundaries"]["fve_called"] is False
    assert audit["integrity_violations"] == []
    assert report.validation_passed is True
    assert report_path.exists()
