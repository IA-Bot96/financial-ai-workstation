"""Tests for Query Engine v2 Phase P6 presentation layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from query_engine.models import (  # noqa: E402
    CitationContract,
    EvidenceBundleContract,
    EvidenceItemContract,
    QueryResponseContract,
    QueryV2AuthorityRole,
    QueryV2CitationType,
    QueryV2DivergenceResolution,
    QueryV2PrecisionLevel,
    QueryV2PresentationStatus,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
    QueryV2ClaimContract,
)
from query_engine.services import QueryPresentationBuilder  # noqa: E402


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _item(
    evidence_ref: str,
    summary: str,
    authority_class: str,
    source_type: str,
    provenance: dict,
    *,
    divergence_refs: tuple[str, ...] = (),
) -> EvidenceItemContract:
    return EvidenceItemContract(
        evidence_ref=evidence_ref,
        content_class="narrative_claim",
        claim_or_value_or_theme_summary=summary,
        authority_class=authority_class,
        source_type=source_type,
        provenance=provenance,
        divergence_refs=divergence_refs,
        entity_ref="lucky_cement",
    )


def _claim(item: EvidenceItemContract) -> QueryV2ClaimContract:
    citation_type = (
        QueryV2CitationType.WORKBOOK_CELL
        if item.provenance["provenance_type"] == "WORKBOOK_CELL"
        else QueryV2CitationType.PDF_PAGE
    )
    source_ref = (
        item.provenance.get("cell")
        or item.provenance.get("url")
        or f"page:{item.provenance.get('page_number', 1)}"
    )
    return QueryV2ClaimContract(
        statement=item.claim_or_value_or_theme_summary,
        supporting_evidence_refs=(item.evidence_ref,),
        authority_class=item.authority_class,
        citations=(
            CitationContract(
                citation_id=f"cit_{item.evidence_ref}",
                citation_type=citation_type,
                source_ref=str(source_ref),
                entity_ref=item.entity_ref,
                evidence_ref=item.evidence_ref,
                rendered_text=str(source_ref),
                precision_level=(
                    QueryV2PrecisionLevel.CELL
                    if citation_type == QueryV2CitationType.WORKBOOK_CELL
                    else QueryV2PrecisionLevel.PAGE
                ),
            ),
        ),
        confidence=0.75,
    )


def _response(items: tuple[EvidenceItemContract, ...]) -> QueryResponseContract:
    claims = tuple(_claim(item) for item in items)
    return QueryResponseContract(
        response_id="resp_1",
        query_id="q1",
        status=QueryV2ResponseStatus.ANSWERED,
        answer_text=" ".join(claim.statement for claim in claims),
        claims=claims,
        overall_confidence=0.75,
    )


def _bundle(items: tuple[EvidenceItemContract, ...]) -> EvidenceBundleContract:
    return EvidenceBundleContract(
        bundle_id="bundle_1",
        request_ref="request_1",
        source_domain=QueryV2TargetDomain.MSIL,
        items=items,
        coverage_note="Presentation test evidence.",
    )


def test_authority_presenter_attributes_every_claim_without_recompute() -> None:
    audited = _item(
        "ev_audited",
        "Revenue increased.",
        "audited_issuer",
        "annual_report",
        {
            "provenance_type": "PDF_PAGE",
            "page_number": 84,
            "claim_type": "audited_fact",
            "effective_authority": "audited_issuer",
            "authority_role": "fact",
            "attribution_label": "per the audited report",
        },
    )
    analyst = _item(
        "ev_analyst",
        "Analyst expects slower growth.",
        "independent_opinion",
        "analysis_reports",
        {
            "provenance_type": "URL_SNAPSHOT",
            "url": "https://example.test/research",
            "snapshot_ref": {"snapshot_id": "snap_1"},
            "claim_type": "forward_context",
            "effective_authority": "independent_opinion",
            "authority_role": "opinion",
            "attribution_label": "per the analyst report",
        },
    )

    result = QueryPresentationBuilder().decorate(
        query_response=_response((audited, analyst)),
        evidence_bundles=(_bundle((audited, analyst)),),
    )

    assert result.claims_with_authority_displayed == 2
    assert result.authority_recomputation_attempts == 0
    assert result.authority_override_attempts == 0
    assert result.attribution_coverage == 100.0
    assert result.authority_presentations[0].authority_class == "audited_issuer"
    assert result.authority_presentations[0].authority_role == QueryV2AuthorityRole.FACT
    assert result.authority_presentations[1].authority_class == "independent_opinion"
    assert result.authority_presentations[1].authority_role == QueryV2AuthorityRole.OPINION


def test_divergence_presenter_surfaces_both_sides_without_resolution() -> None:
    issuer = _item(
        "ev_issuer",
        "Issuer says demand increased.",
        "audited_issuer",
        "annual_report",
        {
            "provenance_type": "PDF_PAGE",
            "page_number": 84,
            "claim_type": "audited_fact",
            "effective_authority": "audited_issuer",
            "authority_role": "fact",
            "divergence_subject": "revenue outlook",
            "authority_weighting": {"weighting": "msil_authority_metadata"},
        },
        divergence_refs=("div_1",),
    )
    analyst = _item(
        "ev_analyst",
        "Analyst says demand weakened.",
        "independent_opinion",
        "analysis_reports",
        {
            "provenance_type": "URL_SNAPSHOT",
            "url": "https://example.test/research",
            "snapshot_ref": {"snapshot_id": "snap_1"},
            "claim_type": "forward_context",
            "effective_authority": "independent_opinion",
            "authority_role": "opinion",
            "divergence_subject": "revenue outlook",
            "authority_weighting": {"weighting": "msil_authority_metadata"},
        },
        divergence_refs=("div_1",),
    )

    result = QueryPresentationBuilder().decorate(
        query_response=_response((issuer, analyst)),
        evidence_bundles=(_bundle((issuer, analyst)),),
    )

    assert result.divergences_surfaced == 1
    assert result.divergence_resolution_attempts == 0
    assert result.divergence_winner_selections == 0
    assert result.decorated_response.status == QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS
    presentation = result.decorated_response.divergences[0]
    assert presentation.presentation_status == QueryV2PresentationStatus.SURFACED
    assert presentation.resolution == QueryV2DivergenceResolution.NOT_DETERMINED_BY_QUERY
    assert presentation.subject == "revenue outlook"
    assert len(presentation.sides) == 2
    assert {side.authority_class for side in presentation.sides} == {
        "audited_issuer",
        "independent_opinion",
    }


def test_single_sided_divergence_reference_is_not_presented() -> None:
    issuer = _item(
        "ev_issuer",
        "Issuer says demand increased.",
        "audited_issuer",
        "annual_report",
        {
            "provenance_type": "PDF_PAGE",
            "page_number": 84,
            "claim_type": "audited_fact",
            "effective_authority": "audited_issuer",
            "authority_role": "fact",
        },
        divergence_refs=("div_1",),
    )

    result = QueryPresentationBuilder().decorate(
        query_response=_response((issuer,)),
        evidence_bundles=(_bundle((issuer,)),),
    )

    assert result.divergences_surfaced == 0
    assert result.decorated_response.divergences == ()
    assert result.decorated_response.status == QueryV2ResponseStatus.ANSWERED


def test_missing_evidence_blocks_full_attribution_coverage() -> None:
    item = _item(
        "ev_audited",
        "Revenue increased.",
        "audited_issuer",
        "annual_report",
        {
            "provenance_type": "PDF_PAGE",
            "page_number": 84,
            "claim_type": "audited_fact",
            "effective_authority": "audited_issuer",
            "authority_role": "fact",
        },
    )

    result = QueryPresentationBuilder().decorate(
        query_response=_response((item,)),
        evidence_bundles=(
            EvidenceBundleContract(
                bundle_id="empty",
                request_ref="request_1",
                source_domain=QueryV2TargetDomain.MSIL,
                items=(),
                coverage_note="No evidence.",
            ),
        ),
    )

    assert result.claims_with_authority_displayed == 0
    assert result.attribution_coverage == 0.0
    assert result.integrity_violations


def test_presentation_builder_writes_divergence_authority_audit_and_phase6_report() -> None:
    tmp_path = _workspace_tmp("v2_presentation_audit")
    audit_path = tmp_path / "query_v2_divergence_authority_audit.json"
    report_path = tmp_path / "query_v2_phase6_report.json"

    report = QueryPresentationBuilder().write_phase6_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["validation_passed"] is True
    assert audit["claims_with_authority_displayed"] >= 3
    assert audit["authority_recomputation_attempts"] == 0
    assert audit["authority_override_attempts"] == 0
    assert audit["divergences_surfaced"] >= 1
    assert audit["divergence_resolution_attempts"] == 0
    assert audit["divergence_winner_selections"] == 0
    assert audit["attribution_coverage_percent"] == 100.0
    assert audit["integrity_violations"] == []
    assert report.validation_passed is True
    assert report_path.exists()
