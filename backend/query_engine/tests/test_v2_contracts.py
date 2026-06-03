"""Tests for Query Engine v2 Phase P0 contract substrate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from query_engine.models import (  # noqa: E402
    AuthorityPresentationContract,
    CitationContract,
    DivergencePresentationContract,
    DivergenceSidePresentationContract,
    EvidenceItemContract,
    QueryIntentContract,
    QueryResponseContract,
    QueryV2AuthorityRole,
    QueryV2CitationType,
    QueryV2ClaimContract,
    QueryV2EntityMention,
    QueryV2EntityResolutionStatus,
    QueryV2IntentType,
    QueryV2PrecisionLevel,
    QueryV2RankingSignal,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
    QueryV2VersionPins,
    RankedEvidenceContract,
    RankedEvidenceItemContract,
    default_query_v2_version_pins,
)
from query_engine.models.v2_contracts import (  # noqa: E402
    FROZEN_QUERY_V2_CONTRACTS,
    FROZEN_QUERY_V2_ENUM_VALUES,
)
from query_engine.services import QueryV2ContractIntegrityValidator  # noqa: E402


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _citation() -> CitationContract:
    return CitationContract(
        citation_id="cit_1",
        citation_type=QueryV2CitationType.PDF_PAGE,
        source_ref="annual_report:lucky:2025:p84",
        entity_ref="lucky_cement",
        evidence_ref="ev_1",
        rendered_text="Annual report 2025, p. 84",
        precision_level=QueryV2PrecisionLevel.PAGE,
    )


def test_frozen_query_v2_enums_are_materialized() -> None:
    assert FROZEN_QUERY_V2_ENUM_VALUES["intent_type"] == (
        "factual_lookup",
        "metric_lookup",
        "qualitative_analysis",
        "forecast_validation",
        "comparison",
        "timeline",
        "risk_analysis",
        "source_exploration",
        "ambiguous",
        "unsupported",
    )
    assert FROZEN_QUERY_V2_ENUM_VALUES["target_domain"] == (
        "msil",
        "ocr_via_msil",
        "qae",
        "fve",
    )
    assert "NONE" not in [item.value for item in QueryV2CitationType]
    assert [item.value for item in QueryV2RankingSignal] == [
        "authority_weight",
        "recency",
        "provenance_completeness",
        "corroboration_strength",
    ]
    assert len(FROZEN_QUERY_V2_CONTRACTS) == 10


def test_query_v2_version_pins_are_complete_and_serializable() -> None:
    pins = default_query_v2_version_pins()

    restored = QueryV2VersionPins.model_validate_json(pins.model_dump_json())

    assert restored == pins
    assert restored.query_contract_version == "2.0.0"
    assert restored.ranking_policy_version == "2.0.0"
    assert restored.msil_schema_version == "1.0.0"


def test_query_v2_version_pins_reject_non_semver_values() -> None:
    with pytest.raises(ValidationError):
        QueryV2VersionPins(query_contract_version="v2")


def test_query_intent_requires_clarification_for_ambiguous_intent() -> None:
    with pytest.raises(ValidationError):
        QueryIntentContract(
            query_id="q1",
            raw_query="What about Lucky?",
            intent_type=QueryV2IntentType.AMBIGUOUS,
            entity_mentions=(),
            classification_confidence=0.6,
            needs_clarification=False,
        )

    intent = QueryIntentContract(
        query_id="q1",
        raw_query="What about Lucky Cement revenue?",
        intent_type=QueryV2IntentType.METRIC_LOOKUP,
        entity_mentions=(
            QueryV2EntityMention(
                raw_mention="Lucky Cement",
                entity_ref="lucky_cement",
                entity_resolution_status=QueryV2EntityResolutionStatus.RESOLVED,
            ),
        ),
        requested_metrics_or_topics=("revenue",),
        classification_confidence=0.9,
        needs_clarification=False,
    )

    assert intent.entity_mentions[0].entity_ref == "lucky_cement"
    assert intent.query_contract_version == "2.0.0"


def test_evidence_item_rejects_none_provenance() -> None:
    with pytest.raises(ValidationError):
        EvidenceItemContract(
            evidence_ref="ev_1",
            content_class="narrative_claim",
            claim_or_value_or_theme_summary="Revenue increased.",
            authority_class="audited_issuer",
            source_type="annual_report",
            provenance={"provenance_type": "NONE"},
            entity_ref="lucky_cement",
        )


def test_ranked_evidence_exclusion_requires_reason_and_roundtrips() -> None:
    with pytest.raises(ValidationError):
        RankedEvidenceItemContract(
            evidence_ref="ev_1",
            rank=1,
            ranking_signals={QueryV2RankingSignal.AUTHORITY_WEIGHT: 1.0},
            included=False,
        )

    ranked = RankedEvidenceContract(
        ranked_id="ranked_1",
        bundle_ref="bundle_1",
        ranked_items=(
            RankedEvidenceItemContract(
                evidence_ref="ev_1",
                rank=1,
                ranking_signals={
                    QueryV2RankingSignal.AUTHORITY_WEIGHT: 1.0,
                    QueryV2RankingSignal.PROVENANCE_COMPLETENESS: 1.0,
                },
                included=True,
            ),
        ),
    )

    restored = RankedEvidenceContract.model_validate_json(ranked.model_dump_json())
    assert restored == ranked


def test_answered_response_requires_cited_claims() -> None:
    with pytest.raises(ValidationError):
        QueryResponseContract(
            response_id="resp_1",
            query_id="q1",
            status=QueryV2ResponseStatus.ANSWERED,
            answer_text="Revenue was 10.",
            overall_confidence=0.8,
        )

    response = QueryResponseContract(
        response_id="resp_1",
        query_id="q1",
        status=QueryV2ResponseStatus.ANSWERED,
        answer_text="Revenue was 10.",
        claims=(
            QueryV2ClaimContract(
                statement="Revenue was 10.",
                supporting_evidence_refs=("ev_1",),
                authority_class="audited_issuer",
                citations=(_citation(),),
                confidence=0.8,
                numeric_integrity_status="clean",
            ),
        ),
        overall_confidence=0.8,
        numeric_integrity_status="clean",
    )

    assert response.claims[0].citations[0].citation_type == QueryV2CitationType.PDF_PAGE


def test_divergence_presentation_is_surfaced_never_resolved() -> None:
    side = DivergenceSidePresentationContract(
        claim_summary="Issuer says revenue increased.",
        authority_class="audited_issuer",
        source_type="annual_report",
        citation=_citation(),
    )

    with pytest.raises(ValidationError):
        DivergencePresentationContract(
            presentation_id="div_pres_1",
            divergence_ref="div_1",
            entity_ref="lucky_cement",
            subject="revenue outlook",
            sides=(side, side),
            authority_weighting={"weighting": "equal"},
            detected_by="msil",
        )

    presentation = DivergencePresentationContract(
        presentation_id="div_pres_1",
        divergence_ref="div_1",
        entity_ref="lucky_cement",
        subject="revenue outlook",
        sides=(side, side),
        authority_weighting={"higher_authority_side": "audited_issuer"},
        detected_by="msil",
    )
    assert presentation.resolution.value == "not_determined_by_query"


def test_authority_presentation_rejects_low_authority_as_fact() -> None:
    with pytest.raises(ValidationError):
        AuthorityPresentationContract(
            presentation_id="auth_1",
            claim_ref="claim_1",
            authority_class="news_media",
            claim_type="descriptive",
            effective_authority="news_media",
            attribution_label="per media coverage",
            authority_role=QueryV2AuthorityRole.FACT,
        )

    presentation = AuthorityPresentationContract(
        presentation_id="auth_2",
        claim_ref="claim_2",
        authority_class="audited_issuer",
        claim_type="audited_fact",
        effective_authority="audited_issuer",
        attribution_label="per the audited report",
        authority_role=QueryV2AuthorityRole.FACT,
    )
    assert presentation.authority_role == QueryV2AuthorityRole.FACT


def test_contract_integrity_validator_writes_audit_and_report() -> None:
    tmp_path = _workspace_tmp("v2_contract_integrity")
    audit_path = tmp_path / "query_v2_contract_integrity_audit.json"
    report_path = tmp_path / "query_v2_phase0_report.json"

    report = QueryV2ContractIntegrityValidator().write_phase0_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["validation_passed"] is True
    assert audit["all_frozen_enums_present"] is True
    assert audit["all_version_pins_present"] is True
    assert audit["ownership_table_consistent"] is True
    assert audit["frozen_contract_count"] == 10
    assert audit["integrity_violations"] == []
    assert report.validation_passed is True
    assert report_path.exists()


def test_target_domain_enum_keeps_ocr_via_msil_boundary() -> None:
    assert QueryV2TargetDomain.OCR_VIA_MSIL.value == "ocr_via_msil"
