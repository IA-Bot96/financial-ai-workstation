"""Tests for Query Engine v2 Phase P3 deterministic evidence ranking."""

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
    QueryV2RankingSignal,
    QueryV2TargetDomain,
    RetrievalPlanContract,
    RetrievalPlanStepContract,
)
from query_engine.services import EvidenceRanker  # noqa: E402


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/query_engine_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _plan(
    *,
    plan_id: str = "plan_msil",
    target_domain: QueryV2TargetDomain = QueryV2TargetDomain.MSIL,
    content_classes: tuple[str, ...] = ("narrative_claim",),
    source_types: tuple[str, ...] = ("annual_report",),
) -> RetrievalPlanContract:
    return RetrievalPlanContract(
        plan_id=plan_id,
        intent_ref=f"intent_{plan_id}",
        entity_refs=("lucky_cement",),
        plan_steps=(
            RetrievalPlanStepContract(
                step_id=f"step_{plan_id}",
                target_domain=target_domain,
                source_types=source_types,
                content_classes=content_classes,
                purpose="Test plan step.",
                required_authority_floor="audited_issuer",
                recency_requirement={"mode": "all_available"},
                rule_id=f"p2.test.{plan_id}",
            ),
        ),
        is_multi_source=False,
    )


def _item(
    evidence_ref: str,
    *,
    provenance: dict | None = None,
    content_class: str = "narrative_claim",
    entity_ref: str = "lucky_cement",
    authority_class: str = "audited_issuer",
    source_type: str = "annual_report",
    observation_time: str = "2025-06-30",
    integrity_status: str | None = None,
    divergence_refs: tuple[str, ...] = (),
) -> EvidenceItemContract:
    if provenance is None:
        return EvidenceItemContract.model_construct(
            evidence_ref=evidence_ref,
            content_class=content_class,
            claim_or_value_or_theme_summary=f"Evidence {evidence_ref}.",
            authority_class=authority_class,
            source_type=source_type,
            observation_time=observation_time,
            subject_period=None,
            supersession_state=None,
            divergence_refs=divergence_refs,
            entity_ref=entity_ref,
            integrity_status=integrity_status,
        )
    return EvidenceItemContract(
        evidence_ref=evidence_ref,
        content_class=content_class,
        claim_or_value_or_theme_summary=f"Evidence {evidence_ref}.",
        authority_class=authority_class,
        source_type=source_type,
        provenance=provenance,
        observation_time=observation_time,
        divergence_refs=divergence_refs,
        entity_ref=entity_ref,
        integrity_status=integrity_status,
    )


def _bundle(
    *items: EvidenceItemContract,
    source_domain: QueryV2TargetDomain = QueryV2TargetDomain.MSIL,
) -> EvidenceBundleContract:
    return EvidenceBundleContract(
        bundle_id="bundle_test",
        request_ref="req_test",
        source_domain=source_domain,
        items=items,
        coverage_note="Test bundle.",
    )


def test_provenance_complete_evidence_ranks_above_incomplete_evidence() -> None:
    bundle = _bundle(
        _item(
            "incomplete",
            provenance={"provenance_type": "PDF_PAGE"},
        ),
        _item(
            "complete",
            provenance={
                "provenance_type": "PDF_PAGE",
                "page_number": 84,
                "authority_weight": 0.95,
                "corroboration_count": 2,
            },
        ),
    )

    result = EvidenceRanker().rank(bundle, _plan())

    ranked = result.ranked_evidence.ranked_items
    assert ranked[0].evidence_ref == "complete"
    assert ranked[0].ranking_signals[QueryV2RankingSignal.PROVENANCE_COMPLETENESS] == 1.0
    assert ranked[1].evidence_ref == "incomplete"
    assert ranked[1].ranking_signals[QueryV2RankingSignal.PROVENANCE_COMPLETENESS] == 0.6
    assert all(item.included for item in ranked)


def test_missing_provenance_is_excluded_with_reason() -> None:
    bundle = _bundle(
        _item("valid", provenance={"provenance_type": "PDF_PAGE", "page_number": 84}),
        _item("missing_provenance", provenance=None),
    )

    result = EvidenceRanker().rank(bundle, _plan())
    excluded = [
        item for item in result.ranked_evidence.ranked_items if not item.included
    ]

    assert len(excluded) == 1
    assert excluded[0].evidence_ref == "missing_provenance"
    assert excluded[0].exclusion_reason == "missing_provenance"
    assert result.validation.exclusion_counts["missing_provenance"] == 1


def test_unresolved_entity_unsupported_content_and_incompatible_domain_exclusions() -> None:
    ranker = EvidenceRanker()

    unresolved = ranker.rank(
        _bundle(
            _item(
                "wrong_entity",
                provenance={"provenance_type": "PDF_PAGE", "page_number": 84},
                entity_ref="unknown_entity",
            )
        ),
        _plan(),
    )
    unsupported = ranker.rank(
        _bundle(
            _item(
                "unsupported_content",
                provenance={"provenance_type": "MARKET_DATA_REF", "date": "2025-06-30"},
                content_class="market_observation",
                source_type="market_watch",
            )
        ),
        _plan(),
    )
    incompatible = ranker.rank(
        _bundle(
            _item(
                "incompatible_domain",
                provenance={"provenance_type": "PDF_PAGE", "page_number": 84},
            ),
            source_domain=QueryV2TargetDomain.MSIL,
        ),
        _plan(
            plan_id="plan_qae",
            target_domain=QueryV2TargetDomain.QAE,
            content_classes=("qualitative_theme",),
        ),
    )

    assert unresolved.ranked_evidence.ranked_items[0].exclusion_reason == "unresolved_entity"
    assert unsupported.ranked_evidence.ranked_items[0].exclusion_reason == "unsupported_content"
    assert incompatible.ranked_evidence.ranked_items[0].exclusion_reason == "incompatible_domain"


def test_ranker_preserves_evidence_as_authored_metadata() -> None:
    item = _item(
        "fve_integrity",
        provenance={"provenance_type": "WORKBOOK_CELL", "cell": "Revenue!B4"},
        content_class="numeric_integrity_status",
        authority_class="fve_validated",
        source_type="forecast_validation_engine",
        integrity_status="clean_with_warning",
        divergence_refs=("div_1",),
    )
    bundle = _bundle(item, source_domain=QueryV2TargetDomain.FVE)
    before = bundle.model_dump(mode="json")

    result = EvidenceRanker().rank(
        bundle,
        _plan(
            plan_id="plan_fve",
            target_domain=QueryV2TargetDomain.FVE,
            content_classes=("numeric_integrity_status",),
            source_types=("forecast_validation_engine",),
        ),
    )
    after = bundle.model_dump(mode="json")

    assert before == after
    assert result.authority_recomputation_attempts == 0
    assert result.corroboration_recomputation_attempts == 0
    assert result.divergence_recomputation_attempts == 0
    assert bundle.items[0].authority_class == "fve_validated"
    assert bundle.items[0].integrity_status == "clean_with_warning"
    assert bundle.items[0].divergence_refs == ("div_1",)


def test_ranker_supports_msil_qae_and_fve_bundles() -> None:
    msil = EvidenceRanker().rank(
        _bundle(
            _item("msil", provenance={"provenance_type": "PDF_PAGE", "page_number": 1}),
            source_domain=QueryV2TargetDomain.MSIL,
        ),
        _plan(),
    )
    qae = EvidenceRanker().rank(
        _bundle(
            _item(
                "qae",
                provenance={"provenance_type": "PDF_PAGE", "page_number": 2},
                content_class="qualitative_theme",
                authority_class="qae_analyzed",
            ),
            source_domain=QueryV2TargetDomain.QAE,
        ),
        _plan(
            plan_id="plan_qae",
            target_domain=QueryV2TargetDomain.QAE,
            content_classes=("qualitative_theme",),
        ),
    )
    fve = EvidenceRanker().rank(
        _bundle(
            _item(
                "fve",
                provenance={"provenance_type": "WORKBOOK_CELL", "cell": "A1"},
                content_class="numeric_integrity_status",
                authority_class="fve_validated",
                source_type="forecast_validation_engine",
            ),
            source_domain=QueryV2TargetDomain.FVE,
        ),
        _plan(
            plan_id="plan_fve",
            target_domain=QueryV2TargetDomain.FVE,
            content_classes=("numeric_integrity_status",),
            source_types=("forecast_validation_engine",),
        ),
    )

    assert msil.evidence_items_included == 1
    assert qae.evidence_items_included == 1
    assert fve.evidence_items_included == 1


def test_ranker_writes_ranking_audit_and_phase3_report() -> None:
    tmp_path = _workspace_tmp("v2_ranking_audit")
    audit_path = tmp_path / "query_v2_ranking_audit.json"
    report_path = tmp_path / "query_v2_phase3_report.json"

    report = EvidenceRanker().write_phase3_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["validation_passed"] is True
    assert audit["bundles_processed"] >= 3
    assert audit["evidence_items_processed"] >= 8
    assert audit["provenance_exclusions"] >= 1
    assert audit["authority_recomputation_attempts"] == 0
    assert audit["corroboration_recomputation_attempts"] == 0
    assert audit["divergence_recomputation_attempts"] == 0
    assert audit["as_authored_preservation_passed"] is True
    assert audit["integrity_violations"] == []
    assert "provenance_completeness" in audit["ranking_factors_exercised"]
    assert report.validation_passed is True
    assert report_path.exists()
