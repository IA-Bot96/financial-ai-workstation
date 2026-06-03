"""Tests for Query Engine v2 Phase P4 deterministic answer assembly."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from query_engine.models import (  # noqa: E402
    EvidenceBundleContract,
    EvidenceItemContract,
    QueryIntentContract,
    QueryV2IntentType,
    QueryV2RankingSignal,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
    RankedEvidenceContract,
    RankedEvidenceItemContract,
)
from query_engine.services import AnswerAssembler, QueryV2AssemblyStatus  # noqa: E402


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _intent(
    intent_type: QueryV2IntentType,
    *,
    query_id: str | None = None,
    requested_metrics_or_topics: tuple[str, ...] = (),
    needs_clarification: bool = False,
) -> QueryIntentContract:
    return QueryIntentContract(
        query_id=query_id or f"q_{intent_type.value}",
        raw_query=f"test {intent_type.value}",
        intent_type=intent_type,
        requested_metrics_or_topics=requested_metrics_or_topics,
        classification_confidence=0.9,
        needs_clarification=needs_clarification,
        clarification_prompt="Please clarify." if needs_clarification else None,
    )


def _item(
    evidence_ref: str = "ev_1",
    *,
    content_class: str = "narrative_claim",
    summary: str = "Revenue increased due to higher dispatches.",
    authority_class: str = "audited_issuer",
    source_type: str = "annual_report",
    provenance: dict | None = None,
    integrity_status: str | None = None,
    divergence_refs: tuple[str, ...] = (),
) -> EvidenceItemContract:
    return EvidenceItemContract(
        evidence_ref=evidence_ref,
        content_class=content_class,
        claim_or_value_or_theme_summary=summary,
        authority_class=authority_class,
        source_type=source_type,
        provenance=provenance
        or {
            "provenance_type": "PDF_PAGE",
            "page_number": 84,
            "confidence": 0.82,
            "authority_weight": 0.74,
        },
        observation_time="2025-06-30",
        divergence_refs=divergence_refs,
        entity_ref="lucky_cement",
        integrity_status=integrity_status,
    )


def _bundle(item: EvidenceItemContract) -> EvidenceBundleContract:
    return EvidenceBundleContract(
        bundle_id="bundle_1",
        request_ref="request_1",
        source_domain=QueryV2TargetDomain.MSIL,
        items=(item,),
        coverage_note="Test evidence.",
    )


def _ranked(evidence_ref: str = "ev_1") -> RankedEvidenceContract:
    return RankedEvidenceContract(
        ranked_id="ranked_1",
        bundle_ref="bundle_1",
        ranked_items=(
            RankedEvidenceItemContract(
                evidence_ref=evidence_ref,
                rank=1,
                ranking_signals={
                    QueryV2RankingSignal.AUTHORITY_WEIGHT: 0.74,
                    QueryV2RankingSignal.RECENCY: 0.8,
                    QueryV2RankingSignal.PROVENANCE_COMPLETENESS: 1.0,
                    QueryV2RankingSignal.CORROBORATION_STRENGTH: 0.0,
                },
                included=True,
            ),
        ),
    )


def test_assembler_builds_grounded_success_response_with_confidence_ceiling() -> None:
    item = _item()

    result = AnswerAssembler().assemble(
        query_intent=_intent(QueryV2IntentType.FACTUAL_LOOKUP),
        ranked_evidence=_ranked(),
        evidence_bundles=(_bundle(item),),
    )

    assert result.assembly_status == QueryV2AssemblyStatus.SUCCESS
    assert result.query_response.status == QueryV2ResponseStatus.ANSWERED
    assert result.grounded_claim_count == 1
    assert result.ungrounded_claim_count == 0
    assert result.assembly_context.ranked_evidence_refs == ("ev_1",)
    assert result.assembly_context.confidence_ceiling == 0.74
    assert result.weakest_supporting_evidence == 0.82
    assert result.authority_ceiling == 0.74
    assert result.query_response.overall_confidence == 0.74
    assert result.query_response.claims[0].supporting_evidence_refs == ("ev_1",)
    assert result.query_response.claims[0].authority_class == item.authority_class
    assert item.claim_or_value_or_theme_summary in result.query_response.answer_text


def test_metric_answer_preserves_integrity_and_validation_status() -> None:
    item = _item(
        "metric_ev",
        content_class="numeric_integrity_status",
        summary="Revenue passed historical integrity checks.",
        authority_class="fve_validated",
        source_type="forecast_validation_engine",
        provenance={
            "provenance_type": "WORKBOOK_CELL",
            "cell": "Revenue!B4",
            "confidence": 0.88,
            "authority_weight": 0.81,
            "validation_status": "PASS",
        },
        integrity_status="clean_with_warning",
    )
    bundle = _bundle(item)

    result = AnswerAssembler().assemble(
        query_intent=_intent(
            QueryV2IntentType.METRIC_LOOKUP,
            requested_metrics_or_topics=("revenue",),
        ),
        ranked_evidence=_ranked("metric_ev"),
        evidence_bundles=(bundle,),
    )

    assert result.assembly_status == QueryV2AssemblyStatus.SUCCESS
    assert result.integrity_statuses == ("clean_with_warning",)
    assert result.validation_statuses == ("PASS",)
    assert result.query_response.numeric_integrity_status == (
        "integrity_status=clean_with_warning;validation_status=PASS"
    )
    assert result.query_response.claims[0].numeric_integrity_status == "clean_with_warning"
    assert "validation_status:PASS" in result.query_response.warnings


def test_divergence_refs_are_consumed_but_not_presented() -> None:
    item = _item(divergence_refs=("div_1",))

    result = AnswerAssembler().assemble(
        query_intent=_intent(QueryV2IntentType.RISK_ANALYSIS),
        ranked_evidence=_ranked(),
        evidence_bundles=(_bundle(item),),
    )

    assert result.divergence_refs_consumed == ("div_1",)
    assert result.query_response.divergences == ()
    assert "divergence_refs_consumed:div_1" in result.query_response.warnings


def test_insufficient_evidence_and_ungrounded_refs_route_to_insufficient() -> None:
    result = AnswerAssembler().assemble(
        query_intent=_intent(QueryV2IntentType.FACTUAL_LOOKUP),
        ranked_evidence=_ranked("missing_ev"),
        evidence_bundles=(
            EvidenceBundleContract(
                bundle_id="bundle_1",
                request_ref="request_1",
                source_domain=QueryV2TargetDomain.MSIL,
                items=(),
                coverage_note="No evidence item for ranked ref.",
            ),
        ),
    )

    assert result.assembly_status == QueryV2AssemblyStatus.INSUFFICIENT_EVIDENCE
    assert result.query_response.status == QueryV2ResponseStatus.INSUFFICIENT_EVIDENCE
    assert result.grounded_claim_count == 0
    assert result.ungrounded_claim_count == 1
    assert result.assembly_context.insufficiency_flag is True


def test_clarification_and_unsupported_status_offramps() -> None:
    clarify = AnswerAssembler().assemble(
        query_intent=_intent(QueryV2IntentType.AMBIGUOUS, needs_clarification=True),
        ranked_evidence=RankedEvidenceContract(
            ranked_id="ranked_clarify",
            bundle_ref="bundle_empty",
        ),
        evidence_bundles=(),
    )
    unsupported = AnswerAssembler().assemble(
        query_intent=_intent(QueryV2IntentType.UNSUPPORTED),
        ranked_evidence=RankedEvidenceContract(
            ranked_id="ranked_unsupported",
            bundle_ref="bundle_empty",
        ),
        evidence_bundles=(),
    )

    assert clarify.assembly_status == QueryV2AssemblyStatus.NEEDS_CLARIFICATION
    assert clarify.query_response.status == QueryV2ResponseStatus.NEEDS_CLARIFICATION
    assert clarify.query_response.clarification_prompt == "Please clarify."
    assert unsupported.assembly_status == QueryV2AssemblyStatus.UNSUPPORTED_INTENT
    assert unsupported.query_response.status == QueryV2ResponseStatus.UNSUPPORTED_INTENT


def test_assembler_writes_assembly_audit_and_phase4_report() -> None:
    tmp_path = _workspace_tmp("v2_assembly_audit")
    audit_path = tmp_path / "query_v2_assembly_audit.json"
    report_path = tmp_path / "query_v2_phase4_report.json"

    report = AnswerAssembler().write_phase4_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["validation_passed"] is True
    assert audit["responses_assembled"] >= 12
    assert audit["grounded_claims"] >= 8
    assert audit["ungrounded_claims"] >= 1
    assert audit["confidence_ceiling_applications"] >= 8
    assert audit["insufficient_evidence_responses"] >= 1
    assert audit["clarification_responses"] >= 1
    assert audit["unsupported_responses"] >= 1
    assert audit["integrity_statuses_preserved"] == ["clean_with_warning"]
    assert "PASS" in audit["validation_statuses_preserved"]
    assert audit["llm_used"] is False
    assert audit["integrity_violations"] == []
    assert report.validation_passed is True
    assert report_path.exists()
