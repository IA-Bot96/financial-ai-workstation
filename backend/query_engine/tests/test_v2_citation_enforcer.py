"""Tests for Query Engine v2 Phase P5 citation enforcement."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from query_engine.models import (  # noqa: E402
    AnswerAssemblyContextContract,
    CitationContract,
    EvidenceBundleContract,
    EvidenceItemContract,
    QueryResponseContract,
    QueryV2CitationType,
    QueryV2ClaimContract,
    QueryV2PrecisionLevel,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
)
from query_engine.services import (  # noqa: E402
    CitationEnforcementStatus,
    CitationEnforcer,
    CitationValidator,
)
from query_engine.services.v2_citation_enforcer import (  # noqa: E402
    EXCLUSION_NONE_PROVENANCE,
    EXCLUSION_UNSUPPORTED_PROVENANCE,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _item(
    evidence_ref: str = "ev_1",
    *,
    provenance: dict | None = None,
    summary: str = "Revenue increased.",
    integrity_status: str | None = None,
) -> EvidenceItemContract:
    return EvidenceItemContract(
        evidence_ref=evidence_ref,
        content_class="narrative_claim",
        claim_or_value_or_theme_summary=summary,
        authority_class="audited_issuer",
        source_type="annual_report",
        provenance=provenance
        or {
            "provenance_type": "PDF_PAGE",
            "workbook_fingerprint": "fp_123",
            "report_reference": "lucky_2025",
            "page_number": 84,
        },
        entity_ref="lucky_cement",
        integrity_status=integrity_status,
    )


def _response(items: tuple[EvidenceItemContract, ...]) -> QueryResponseContract:
    claims = tuple(_claim(item) for item in items)
    return QueryResponseContract(
        response_id="resp_1",
        query_id="q1",
        status=QueryV2ResponseStatus.ANSWERED,
        answer_text=" ".join(claim.statement for claim in claims),
        claims=claims,
        overall_confidence=0.8,
        numeric_integrity_status="integrity_status=clean;validation_status=PASS",
    )


def _claim(item: EvidenceItemContract) -> QueryV2ClaimContract:
    evidence_ref = str(getattr(item, "evidence_ref", "ev_missing"))
    return QueryV2ClaimContract(
        statement=str(
            getattr(item, "claim_or_value_or_theme_summary", "Missing provenance claim.")
        ),
        supporting_evidence_refs=(evidence_ref,),
        authority_class=str(getattr(item, "authority_class", "audited_issuer")),
        citations=(
            CitationContract(
                citation_id=f"pre_p5_{evidence_ref}",
                citation_type=QueryV2CitationType.PDF_PAGE,
                source_ref=f"pre_p5:{evidence_ref}",
                entity_ref=str(getattr(item, "entity_ref", "lucky_cement")),
                evidence_ref=evidence_ref,
                rendered_text=f"Pre-P5 trace {evidence_ref}",
                precision_level=QueryV2PrecisionLevel.PAGE,
            ),
        ),
        confidence=0.8,
        numeric_integrity_status=getattr(item, "integrity_status", None),
    )


def _context(items: tuple[EvidenceItemContract, ...]) -> AnswerAssemblyContextContract:
    return AnswerAssemblyContextContract(
        context_id="context_1",
        intent_ref="q1",
        ranked_evidence_refs=tuple(str(getattr(item, "evidence_ref")) for item in items),
        authority_set=tuple(
            {
                "evidence_ref": str(getattr(item, "evidence_ref")),
                "authority_class": str(getattr(item, "authority_class", "audited_issuer")),
                "source_type": str(getattr(item, "source_type", "annual_report")),
            }
            for item in items
        ),
        confidence_ceiling=0.8,
        insufficiency_flag=False,
    )


def _bundle(items: tuple[EvidenceItemContract, ...]) -> EvidenceBundleContract:
    return EvidenceBundleContract.model_construct(
        bundle_id="bundle_1",
        request_ref="request_1",
        source_domain=QueryV2TargetDomain.MSIL,
        items=items,
        coverage_note="Citation test evidence.",
    )


def test_enforcer_keeps_claim_with_pdf_page_provenance_and_renders_page_precision() -> None:
    item = _item()

    result = CitationEnforcer().enforce(
        query_response=_response((item,)),
        assembly_context=_context((item,)),
        evidence_bundles=(_bundle((item,)),),
    )

    citation = result.enforced_response.claims[0].citations[0]
    assert result.status == CitationEnforcementStatus.SUCCESS
    assert result.claims_cited == 1
    assert result.claims_dropped == 0
    assert citation.citation_type == QueryV2CitationType.PDF_PAGE
    assert citation.precision_level == QueryV2PrecisionLevel.PAGE
    assert citation.source_ref == "lucky_2025:page:84"


def test_report_level_pdf_provenance_remains_ref_precision() -> None:
    item = _item(
        provenance={
            "provenance_type": "PDF_PAGE",
            "report_reference": "lucky_2025",
        }
    )

    result = CitationEnforcer().enforce(
        query_response=_response((item,)),
        assembly_context=_context((item,)),
        evidence_bundles=(_bundle((item,)),),
    )

    citation = result.enforced_response.claims[0].citations[0]
    assert result.status == CitationEnforcementStatus.SUCCESS
    assert citation.citation_type == QueryV2CitationType.PDF_PAGE
    assert citation.precision_level == QueryV2PrecisionLevel.REF
    assert citation.source_ref == "lucky_2025"


def test_enforcer_drops_none_and_unsupported_provenance_claims() -> None:
    valid = _item("valid")
    none = EvidenceItemContract.model_construct(
        evidence_ref="none",
        content_class="narrative_claim",
        claim_or_value_or_theme_summary="NONE provenance claim.",
        authority_class="audited_issuer",
        source_type="annual_report",
        provenance={"provenance_type": "NONE"},
        entity_ref="lucky_cement",
        observation_time=None,
        subject_period=None,
        supersession_state=None,
        divergence_refs=(),
        integrity_status=None,
    )
    unsupported = _item(
        "unsupported",
        provenance={"provenance_type": "INTERNAL_NOTE", "source_ref": "internal"},
    )
    items = (valid, none, unsupported)

    result = CitationEnforcer().enforce(
        query_response=_response(items),
        assembly_context=_context(items),
        evidence_bundles=(_bundle(items),),
    )

    assert result.status == CitationEnforcementStatus.SUCCESS_WITH_DROPPED_CLAIMS
    assert result.enforced_response.status == QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS
    assert result.claims_cited == 1
    assert result.claims_dropped == 2
    assert result.none_provenance_exclusions == 1
    assert result.unsupported_provenance_exclusions == 1
    assert result.decisions[1].exclusion_reason == EXCLUSION_NONE_PROVENANCE
    assert result.decisions[2].exclusion_reason == EXCLUSION_UNSUPPORTED_PROVENANCE


def test_all_dropped_claims_route_to_insufficient_evidence() -> None:
    missing = EvidenceItemContract.model_construct(
        evidence_ref="missing",
        content_class="narrative_claim",
        claim_or_value_or_theme_summary="Missing provenance claim.",
        authority_class="audited_issuer",
        source_type="annual_report",
        entity_ref="lucky_cement",
        observation_time=None,
        subject_period=None,
        supersession_state=None,
        divergence_refs=(),
        integrity_status=None,
    )

    result = CitationEnforcer().enforce(
        query_response=_response((missing,)),
        assembly_context=_context((missing,)),
        evidence_bundles=(_bundle((missing,)),),
    )

    assert result.status == CitationEnforcementStatus.INSUFFICIENT_EVIDENCE
    assert result.enforced_response.status == QueryV2ResponseStatus.INSUFFICIENT_EVIDENCE
    assert result.claims_cited == 0
    assert result.claims_dropped == 1
    assert result.missing_provenance_exclusions == 1


def test_workbook_cell_precision_requires_cell_locator() -> None:
    item = _item(
        provenance={
            "provenance_type": "WORKBOOK_CELL",
            "workbook_fingerprint": "fp_123",
        }
    )

    result = CitationEnforcer().enforce(
        query_response=_response((item,)),
        assembly_context=_context((item,)),
        evidence_bundles=(_bundle((item,)),),
    )

    assert result.status == CitationEnforcementStatus.INSUFFICIENT_EVIDENCE
    assert result.unsupported_provenance_exclusions == 1


def test_validator_rejects_false_precision() -> None:
    citation = CitationContract(
        citation_id="bad_precision",
        citation_type=QueryV2CitationType.PDF_PAGE,
        source_ref="lucky_2025",
        entity_ref="lucky_cement",
        evidence_ref="ev_1",
        rendered_text="Annual report reference lucky_2025",
        precision_level=QueryV2PrecisionLevel.PAGE,
    )

    assert CitationValidator.precision_violation(
        citation,
        {"provenance_type": "PDF_PAGE", "report_reference": "lucky_2025"},
    )


def test_enforcer_writes_citation_audit_and_phase5_report() -> None:
    tmp_path = _workspace_tmp("v2_citation_audit")
    audit_path = tmp_path / "query_v2_citation_audit.json"
    report_path = tmp_path / "query_v2_phase5_report.json"

    report = CitationEnforcer().write_phase5_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["validation_passed"] is True
    assert audit["claims_evaluated"] >= 8
    assert audit["claims_cited"] >= 4
    assert audit["claims_dropped"] >= 4
    assert audit["missing_provenance_exclusions"] >= 1
    assert audit["none_provenance_exclusions"] >= 1
    assert audit["unsupported_provenance_exclusions"] >= 1
    assert audit["citation_precision_violations"] == 0
    assert audit["integrity_violations"] == []
    assert report.validation_passed is True
    assert report_path.exists()
