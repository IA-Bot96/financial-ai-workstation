"""Tests for Query Engine v2 Phase P1 deterministic intent classification."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from query_engine.models import (  # noqa: E402
    QueryV2EntityMention,
    QueryV2EntityResolutionStatus,
    QueryV2IntentType,
)
from query_engine.services import QueryIntentClassifier  # noqa: E402


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


def test_classifier_covers_all_frozen_intent_types() -> None:
    classifier = QueryIntentClassifier()
    cases = {
        "What is Lucky Cement's sector?": QueryV2IntentType.FACTUAL_LOOKUP,
        "What was revenue in 2025?": QueryV2IntentType.METRIC_LOOKUP,
        "Why did operating profit decline?": QueryV2IntentType.QUALITATIVE_ANALYSIS,
        "Is my 2026 revenue forecast reasonable?": QueryV2IntentType.FORECAST_VALIDATION,
        "Compare debt and cash.": QueryV2IntentType.COMPARISON,
        "Show the corporate events timeline.": QueryV2IntentType.TIMELINE,
        "Provide a risk analysis of the company.": QueryV2IntentType.RISK_ANALYSIS,
        "Show the source for EPS.": QueryV2IntentType.SOURCE_EXPLORATION,
        "Tell me about Lucky.": QueryV2IntentType.AMBIGUOUS,
        "Write a poem about cement.": QueryV2IntentType.UNSUPPORTED,
    }

    actual = {
        query: classifier.classify(
            query,
            entity_mentions=(_resolved_entity(),)
            if expected
            not in {QueryV2IntentType.AMBIGUOUS, QueryV2IntentType.UNSUPPORTED}
            else (),
        ).query_intent.intent_type
        for query, expected in cases.items()
    }

    assert actual == cases
    assert set(actual.values()) == set(QueryV2IntentType)


def test_classifier_is_deterministic_and_uses_stable_query_id() -> None:
    classifier = QueryIntentClassifier()
    first = classifier.classify(
        "What was revenue in 2025?",
        entity_mentions=(_resolved_entity(),),
    )
    second = classifier.classify(
        "What was revenue in 2025?",
        entity_mentions=(_resolved_entity(),),
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.query_intent.query_id.startswith("query_v2_")
    assert first.deterministic_signature == second.deterministic_signature


def test_classifier_consumes_supplied_entity_refs_without_resolving() -> None:
    classifier = QueryIntentClassifier()

    result = classifier.classify(
        "What was revenue in 2025?",
        entity_mentions=(_resolved_entity(),),
    )

    assert result.query_intent.entity_mentions[0].entity_ref == "lucky_cement"
    assert result.entity_mentions_consumed == 1
    assert result.supplied_entity_refs == ("lucky_cement",)
    assert result.msil_called is False
    assert result.entity_resolution_performed is False
    assert result.entities_created is False


def test_unresolved_supplied_entity_routes_to_clarification() -> None:
    classifier = QueryIntentClassifier()
    unresolved = QueryV2EntityMention(
        raw_mention="Lucky",
        entity_ref=None,
        entity_resolution_status=QueryV2EntityResolutionStatus.UNRESOLVED,
    )

    result = classifier.classify(
        "What was revenue in 2025?",
        entity_mentions=(unresolved,),
    )

    assert result.query_intent.intent_type == QueryV2IntentType.AMBIGUOUS
    assert result.query_intent.needs_clarification is True
    assert result.ambiguity_routed_to_clarification is True
    assert result.entity_resolution_performed is False


def test_unsupported_query_routes_to_unsupported_without_clarification() -> None:
    result = QueryIntentClassifier().classify("Draft an email about cement.")

    assert result.query_intent.intent_type == QueryV2IntentType.UNSUPPORTED
    assert result.query_intent.needs_clarification is False
    assert result.unsupported_routed_to_unsupported is True


def test_multi_signal_query_records_secondary_intents() -> None:
    result = QueryIntentClassifier().classify(
        "Compare revenue and operating profit and explain the decline.",
        entity_mentions=(_resolved_entity(),),
    )

    assert result.query_intent.intent_type == QueryV2IntentType.COMPARISON
    assert QueryV2IntentType.QUALITATIVE_ANALYSIS in result.query_intent.secondary_intents
    assert QueryV2IntentType.METRIC_LOOKUP in result.query_intent.secondary_intents


def test_classifier_writes_intent_audit_and_phase1_report() -> None:
    tmp_path = _workspace_tmp("v2_intent_audit")
    audit_path = tmp_path / "query_v2_intent_audit.json"
    report_path = tmp_path / "query_v2_phase1_report.json"

    report = QueryIntentClassifier().write_phase1_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["validation_passed"] is True
    assert audit["missing_frozen_intents"] == []
    assert audit["ambiguity_routing_passed"] is True
    assert audit["unsupported_routing_passed"] is True
    assert audit["deterministic_repeatability_passed"] is True
    assert audit["entity_handling"]["msil_called"] is False
    assert report.validation_passed is True
    assert report_path.exists()
