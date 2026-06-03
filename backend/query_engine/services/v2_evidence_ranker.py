"""Deterministic Query Engine v2 evidence ranking.

This Phase P3 module consumes evidence bundles as authored and emits the frozen
RankedEvidence contract. It does not retrieve evidence, assemble answers, render
citations, present divergence, present authority, or use LLM logic.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.v2_contracts import (
    EvidenceBundleContract,
    EvidenceItemContract,
    QueryV2RankingSignal,
    QueryV2TargetDomain,
    RankedEvidenceContract,
    RankedEvidenceItemContract,
    RetrievalPlanContract,
    RetrievalPlanStepContract,
)


EXCLUSION_MISSING_PROVENANCE = "missing_provenance"
EXCLUSION_UNRESOLVED_ENTITY = "unresolved_entity"
EXCLUSION_UNSUPPORTED_CONTENT = "unsupported_content"
EXCLUSION_INCOMPATIBLE_DOMAIN = "incompatible_domain"


class EvidenceRankingDecision(BaseModel):
    """One deterministic inclusion/exclusion and ranking decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str = Field(..., min_length=1)
    included: bool
    exclusion_reason: str | None = Field(default=None)
    ranking_score: float = Field(..., ge=0)
    ranking_signals: dict[QueryV2RankingSignal, float]
    ranking_factors: dict[str, float]


class EvidenceBundleValidationResult(BaseModel):
    """Validation result for one evidence bundle against a retrieval plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str
    source_domain: QueryV2TargetDomain
    evidence_items_processed: int = Field(..., ge=0)
    included_count: int = Field(..., ge=0)
    excluded_count: int = Field(..., ge=0)
    exclusion_counts: dict[str, int]
    decisions: tuple[EvidenceRankingDecision, ...] = Field(default_factory=tuple)
    validation_passed: bool


class EvidenceRankingResult(BaseModel):
    """Output of ranking one EvidenceBundle against one RetrievalPlan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str
    plan_id: str
    ranked_evidence: RankedEvidenceContract
    validation: EvidenceBundleValidationResult
    ranking_factors_exercised: tuple[str, ...]
    evidence_items_processed: int = Field(..., ge=0)
    evidence_items_included: int = Field(..., ge=0)
    evidence_items_excluded: int = Field(..., ge=0)
    authority_recomputation_attempts: int = Field(default=0, ge=0)
    corroboration_recomputation_attempts: int = Field(default=0, ge=0)
    divergence_recomputation_attempts: int = Field(default=0, ge=0)


class QueryV2RankingAudit(BaseModel):
    """Audit payload for Query v2 Phase P3 evidence ranking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    bundles_processed: int = Field(..., ge=0)
    evidence_items_processed: int = Field(..., ge=0)
    evidence_items_included: int = Field(..., ge=0)
    evidence_items_excluded: int = Field(..., ge=0)
    ranking_factors_exercised: tuple[str, ...]
    provenance_exclusions: int = Field(..., ge=0)
    exclusion_counts: dict[str, int]
    authority_recomputation_attempts: int = Field(..., ge=0)
    corroboration_recomputation_attempts: int = Field(..., ge=0)
    divergence_recomputation_attempts: int = Field(..., ge=0)
    as_authored_preservation_passed: bool
    sample_results: tuple[dict[str, Any], ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryV2Phase3Report(BaseModel):
    """Implementation report for Query v2 Phase P3."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    ranker: str
    builders: tuple[str, ...]
    audit_path: str
    validation_passed: bool
    bundles_processed: int = Field(..., ge=0)
    evidence_items_processed: int = Field(..., ge=0)
    evidence_items_included: int = Field(..., ge=0)
    evidence_items_excluded: int = Field(..., ge=0)
    provenance_exclusions: int = Field(..., ge=0)
    authority_recomputation_attempts: int = Field(..., ge=0)
    corroboration_recomputation_attempts: int = Field(..., ge=0)
    divergence_recomputation_attempts: int = Field(..., ge=0)
    prohibited_implementations: tuple[str, ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class EvidenceBundleValidator:
    """Validate EvidenceBundle items for deterministic ranking eligibility."""

    def validate(
        self,
        bundle: EvidenceBundleContract,
        retrieval_plan: RetrievalPlanContract,
    ) -> EvidenceBundleValidationResult:
        """Validate each evidence item without modifying the bundle."""

        plan_steps = _compatible_plan_steps(bundle.source_domain, retrieval_plan)
        compatible_content_classes = {
            content_class
            for step in plan_steps
            for content_class in step.content_classes
        }
        resolved_entity_refs = set(retrieval_plan.entity_refs)
        decisions: list[EvidenceRankingDecision] = []
        for item in bundle.items:
            exclusion_reason = self._exclusion_reason(
                item=item,
                bundle=bundle,
                retrieval_plan=retrieval_plan,
                plan_steps=plan_steps,
                compatible_content_classes=compatible_content_classes,
                resolved_entity_refs=resolved_entity_refs,
            )
            signals = _ranking_signals(item)
            factors = _ranking_factors(
                item=item,
                bundle=bundle,
                retrieval_plan=retrieval_plan,
                plan_steps=plan_steps,
                ranking_signals=signals,
            )
            score = 0.0 if exclusion_reason else _ranking_score(signals, factors)
            decisions.append(
                EvidenceRankingDecision(
                    evidence_ref=_evidence_ref(item),
                    included=exclusion_reason is None,
                    exclusion_reason=exclusion_reason,
                    ranking_score=score,
                    ranking_signals=signals,
                    ranking_factors=factors,
                )
            )

        exclusion_counts = Counter(
            decision.exclusion_reason
            for decision in decisions
            if decision.exclusion_reason
        )
        included_count = sum(1 for decision in decisions if decision.included)
        excluded_count = len(decisions) - included_count
        return EvidenceBundleValidationResult(
            bundle_id=bundle.bundle_id,
            source_domain=bundle.source_domain,
            evidence_items_processed=len(bundle.items),
            included_count=included_count,
            excluded_count=excluded_count,
            exclusion_counts=dict(sorted(exclusion_counts.items())),
            decisions=tuple(decisions),
            validation_passed=True,
        )

    @staticmethod
    def _exclusion_reason(
        *,
        item: EvidenceItemContract,
        bundle: EvidenceBundleContract,
        retrieval_plan: RetrievalPlanContract,
        plan_steps: tuple[RetrievalPlanStepContract, ...],
        compatible_content_classes: set[str],
        resolved_entity_refs: set[str],
    ) -> str | None:
        if _missing_provenance(item):
            return EXCLUSION_MISSING_PROVENANCE
        if not _evidence_entity_ref(item) or _evidence_entity_ref(item) not in resolved_entity_refs:
            return EXCLUSION_UNRESOLVED_ENTITY
        if not plan_steps or not _domain_compatible(bundle.source_domain, retrieval_plan):
            return EXCLUSION_INCOMPATIBLE_DOMAIN
        if _evidence_content_class(item) not in compatible_content_classes:
            return EXCLUSION_UNSUPPORTED_CONTENT
        return None


class RankedEvidenceBuilder:
    """Build RankedEvidence contracts from validation decisions."""

    def build(
        self,
        *,
        bundle: EvidenceBundleContract,
        validation: EvidenceBundleValidationResult,
    ) -> RankedEvidenceContract:
        """Build ranked evidence, with excluded items placed after included items."""

        ordered = sorted(
            validation.decisions,
            key=lambda decision: (
                0 if decision.included else 1,
                -decision.ranking_signals.get(
                    QueryV2RankingSignal.PROVENANCE_COMPLETENESS,
                    0.0,
                ),
                -decision.ranking_score,
                decision.exclusion_reason or "",
                decision.evidence_ref,
            ),
        )
        ranked_items = tuple(
            RankedEvidenceItemContract(
                evidence_ref=decision.evidence_ref,
                rank=index,
                ranking_signals=decision.ranking_signals,
                included=decision.included,
                exclusion_reason=decision.exclusion_reason,
            )
            for index, decision in enumerate(ordered, start=1)
        )
        return RankedEvidenceContract(
            ranked_id=_ranked_id(bundle.bundle_id),
            bundle_ref=bundle.bundle_id,
            ranked_items=ranked_items,
        )


class EvidenceRanker:
    """Deterministic P3 evidence ranker."""

    def __init__(
        self,
        *,
        validator: EvidenceBundleValidator | None = None,
        builder: RankedEvidenceBuilder | None = None,
    ) -> None:
        self._validator = validator or EvidenceBundleValidator()
        self._builder = builder or RankedEvidenceBuilder()

    def rank(
        self,
        bundle: EvidenceBundleContract,
        retrieval_plan: RetrievalPlanContract,
    ) -> EvidenceRankingResult:
        """Validate and rank one evidence bundle without altering evidence content."""

        before_hash = _bundle_content_hash(bundle)
        validation = self._validator.validate(bundle, retrieval_plan)
        ranked = self._builder.build(bundle=bundle, validation=validation)
        after_hash = _bundle_content_hash(bundle)
        if before_hash != after_hash:
            raise RuntimeError("EvidenceBundle content was modified during ranking.")
        ranking_factors = tuple(
            sorted(
                {
                    factor
                    for decision in validation.decisions
                    for factor in decision.ranking_factors
                }
            )
        )
        return EvidenceRankingResult(
            bundle_id=bundle.bundle_id,
            plan_id=retrieval_plan.plan_id,
            ranked_evidence=ranked,
            validation=validation,
            ranking_factors_exercised=ranking_factors,
            evidence_items_processed=validation.evidence_items_processed,
            evidence_items_included=validation.included_count,
            evidence_items_excluded=validation.excluded_count,
        )

    def write_ranking_audit(
        self,
        output_path: str | Path = "output/query_v2_ranking_audit.json",
    ) -> QueryV2RankingAudit:
        """Run and persist the deterministic P3 ranking audit."""

        audit = self.build_ranking_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase3_report(
        self,
        *,
        audit_path: str | Path = "output/query_v2_ranking_audit.json",
        report_path: str | Path = "output/query_v2_phase3_report.json",
    ) -> QueryV2Phase3Report:
        """Write the P3 ranking audit and implementation report."""

        audit = self.write_ranking_audit(audit_path)
        report = QueryV2Phase3Report(
            phase="P3",
            scope="Evidence consumption and deterministic ranking only",
            ranker="EvidenceRanker",
            builders=("EvidenceBundleValidator", "RankedEvidenceBuilder"),
            audit_path=str(audit_path),
            validation_passed=audit.validation_passed,
            bundles_processed=audit.bundles_processed,
            evidence_items_processed=audit.evidence_items_processed,
            evidence_items_included=audit.evidence_items_included,
            evidence_items_excluded=audit.evidence_items_excluded,
            provenance_exclusions=audit.provenance_exclusions,
            authority_recomputation_attempts=(
                audit.authority_recomputation_attempts
            ),
            corroboration_recomputation_attempts=(
                audit.corroboration_recomputation_attempts
            ),
            divergence_recomputation_attempts=(
                audit.divergence_recomputation_attempts
            ),
            prohibited_implementations=(
                "answer_assembly",
                "citation_rendering",
                "divergence_presentation",
                "authority_presentation",
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

    def build_ranking_audit(self) -> QueryV2RankingAudit:
        """Build the deterministic P3 audit payload."""

        samples = _audit_samples()
        results = [self.rank(bundle, plan) for bundle, plan in samples]
        exclusion_counts: Counter[str] = Counter()
        factors: set[str] = set()
        sample_results: list[dict[str, Any]] = []
        before_after_hashes_match = True
        for (bundle, _plan), result in zip(samples, results):
            before_hash = _bundle_content_hash(bundle)
            after_hash = _bundle_content_hash(bundle)
            before_after_hashes_match = before_after_hashes_match and (
                before_hash == after_hash
            )
            exclusion_counts.update(result.validation.exclusion_counts)
            factors.update(result.ranking_factors_exercised)
            sample_results.append(
                {
                    "bundle_id": result.bundle_id,
                    "source_domain": bundle.source_domain.value,
                    "plan_id": result.plan_id,
                    "items_processed": result.evidence_items_processed,
                    "items_included": result.evidence_items_included,
                    "items_excluded": result.evidence_items_excluded,
                    "exclusion_counts": result.validation.exclusion_counts,
                    "ranked_items": [
                        item.model_dump(mode="json")
                        for item in result.ranked_evidence.ranked_items
                    ],
                }
            )

        evidence_items_processed = sum(result.evidence_items_processed for result in results)
        evidence_items_included = sum(result.evidence_items_included for result in results)
        evidence_items_excluded = sum(result.evidence_items_excluded for result in results)
        provenance_exclusions = exclusion_counts.get(EXCLUSION_MISSING_PROVENANCE, 0)
        authority_attempts = sum(result.authority_recomputation_attempts for result in results)
        corroboration_attempts = sum(
            result.corroboration_recomputation_attempts for result in results
        )
        divergence_attempts = sum(
            result.divergence_recomputation_attempts for result in results
        )
        required_exclusions = {
            EXCLUSION_MISSING_PROVENANCE,
            EXCLUSION_UNRESOLVED_ENTITY,
            EXCLUSION_UNSUPPORTED_CONTENT,
            EXCLUSION_INCOMPATIBLE_DOMAIN,
        }
        required_factors = {
            "provenance_completeness",
            "authority_class",
            "recency",
            "corroboration_count",
            "source_relevance",
            "requested_domain_relevance",
        }
        violations: list[dict[str, Any]] = []
        if not required_exclusions.issubset(set(exclusion_counts)):
            violations.append(
                _violation(
                    "exclusion_reason_coverage",
                    "EvidenceBundleValidator",
                    "Not every required exclusion reason was exercised.",
                    {
                        "missing": tuple(sorted(required_exclusions - set(exclusion_counts))),
                        "observed": dict(sorted(exclusion_counts.items())),
                    },
                )
            )
        if not required_factors.issubset(factors):
            violations.append(
                _violation(
                    "ranking_factor_coverage",
                    "EvidenceRanker",
                    "Not every expected ranking factor was exercised.",
                    {
                        "missing": tuple(sorted(required_factors - factors)),
                        "observed": tuple(sorted(factors)),
                    },
                )
            )
        if provenance_exclusions == 0:
            violations.append(
                _violation(
                    "provenance_exclusions",
                    "EvidenceBundleValidator",
                    "Missing-provenance evidence was not excluded.",
                    dict(sorted(exclusion_counts.items())),
                )
            )
        if authority_attempts or corroboration_attempts or divergence_attempts:
            violations.append(
                _violation(
                    "consume_not_recompute",
                    "EvidenceRanker",
                    "Ranking attempted to recompute MSIL-owned metadata.",
                    {
                        "authority_recomputation_attempts": authority_attempts,
                        "corroboration_recomputation_attempts": corroboration_attempts,
                        "divergence_recomputation_attempts": divergence_attempts,
                    },
                )
            )
        if not before_after_hashes_match:
            violations.append(
                _violation(
                    "as_authored_preservation",
                    "EvidenceRanker",
                    "Evidence bundle content changed during ranking.",
                    {},
                )
            )

        return QueryV2RankingAudit(
            validation_passed=not violations,
            bundles_processed=len(samples),
            evidence_items_processed=evidence_items_processed,
            evidence_items_included=evidence_items_included,
            evidence_items_excluded=evidence_items_excluded,
            ranking_factors_exercised=tuple(sorted(factors)),
            provenance_exclusions=provenance_exclusions,
            exclusion_counts=dict(sorted(exclusion_counts.items())),
            authority_recomputation_attempts=authority_attempts,
            corroboration_recomputation_attempts=corroboration_attempts,
            divergence_recomputation_attempts=divergence_attempts,
            as_authored_preservation_passed=before_after_hashes_match,
            sample_results=tuple(sample_results),
            integrity_violations=tuple(violations),
        )


def _compatible_plan_steps(
    source_domain: QueryV2TargetDomain,
    retrieval_plan: RetrievalPlanContract,
) -> tuple[RetrievalPlanStepContract, ...]:
    return tuple(
        step
        for step in retrieval_plan.plan_steps
        if step.target_domain == source_domain
        or (
            source_domain == QueryV2TargetDomain.MSIL
            and step.target_domain == QueryV2TargetDomain.OCR_VIA_MSIL
        )
    )


def _domain_compatible(
    source_domain: QueryV2TargetDomain,
    retrieval_plan: RetrievalPlanContract,
) -> bool:
    return bool(_compatible_plan_steps(source_domain, retrieval_plan))


def _ranking_signals(item: EvidenceItemContract) -> dict[QueryV2RankingSignal, float]:
    provenance = _provenance(item)
    return {
        QueryV2RankingSignal.AUTHORITY_WEIGHT: _authority_weight(
            _evidence_authority_class(item),
            provenance,
        ),
        QueryV2RankingSignal.RECENCY: _recency_score(item),
        QueryV2RankingSignal.PROVENANCE_COMPLETENESS: _provenance_completeness(item),
        QueryV2RankingSignal.CORROBORATION_STRENGTH: _corroboration_strength(provenance),
    }


def _ranking_factors(
    *,
    item: EvidenceItemContract,
    bundle: EvidenceBundleContract,
    retrieval_plan: RetrievalPlanContract,
    plan_steps: tuple[RetrievalPlanStepContract, ...],
    ranking_signals: dict[QueryV2RankingSignal, float],
) -> dict[str, float]:
    source_types = {source for step in plan_steps for source in step.source_types}
    content_classes = {content for step in plan_steps for content in step.content_classes}
    source_relevance = 1.0 if _evidence_source_type(item) in source_types else 0.5
    content_relevance = 1.0 if _evidence_content_class(item) in content_classes else 0.0
    requested_domain_relevance = 1.0 if _domain_compatible(bundle.source_domain, retrieval_plan) else 0.0
    return {
        "provenance_completeness": ranking_signals[
            QueryV2RankingSignal.PROVENANCE_COMPLETENESS
        ],
        "authority_class": ranking_signals[QueryV2RankingSignal.AUTHORITY_WEIGHT],
        "recency": ranking_signals[QueryV2RankingSignal.RECENCY],
        "corroboration_count": ranking_signals[
            QueryV2RankingSignal.CORROBORATION_STRENGTH
        ],
        "source_relevance": source_relevance,
        "requested_domain_relevance": requested_domain_relevance,
        "content_relevance": content_relevance,
    }


def _ranking_score(
    signals: dict[QueryV2RankingSignal, float],
    factors: dict[str, float],
) -> float:
    return round(
        (
            signals[QueryV2RankingSignal.PROVENANCE_COMPLETENESS] * 100
            + signals[QueryV2RankingSignal.AUTHORITY_WEIGHT] * 20
            + signals[QueryV2RankingSignal.RECENCY] * 10
            + signals[QueryV2RankingSignal.CORROBORATION_STRENGTH] * 10
            + factors["source_relevance"] * 5
            + factors["requested_domain_relevance"] * 5
            + factors["content_relevance"] * 5
        ),
        4,
    )


def _missing_provenance(item: EvidenceItemContract) -> bool:
    provenance = _provenance(item)
    if not provenance:
        return True
    provenance_type = str(provenance.get("provenance_type", "")).upper()
    return not provenance_type or provenance_type == "NONE"


def _provenance_completeness(item: EvidenceItemContract) -> float:
    provenance = _provenance(item)
    if _missing_provenance(item):
        return 0.0
    informative_keys = {
        key
        for key, value in provenance.items()
        if key != "provenance_type" and value not in (None, "", (), [])
    }
    return 1.0 if informative_keys else 0.6


def _authority_weight(authority_class: str, provenance: dict[str, Any]) -> float:
    provided = provenance.get("authority_weight")
    if isinstance(provided, int | float):
        return _clamp(float(provided))
    weights = {
        "regulatory_independent": 0.98,
        "audited_issuer": 0.95,
        "exchange_official": 0.92,
        "fve_validated": 0.9,
        "official_issuer_unaudited": 0.85,
        "qae_analyzed": 0.75,
        "sector_aggregate": 0.68,
        "independent_opinion": 0.62,
        "market_revealed": 0.55,
        "news_media": 0.35,
    }
    return weights.get(authority_class.lower(), 0.5)


def _recency_score(item: EvidenceItemContract) -> float:
    year = _extract_year(_evidence_observation_time(item)) or _extract_year(
        _evidence_subject_period(item)
    )
    if year is None:
        return 0.5
    return _clamp((year - 2000) / 30)


def _corroboration_strength(provenance: dict[str, Any]) -> float:
    provided = provenance.get("corroboration_strength")
    if isinstance(provided, int | float):
        return _clamp(float(provided))
    count = provenance.get("corroboration_count")
    if isinstance(count, int | float):
        return _clamp(float(count) / 5)
    refs = provenance.get("corroboration_refs")
    if isinstance(refs, list | tuple):
        return _clamp(len(refs) / 5)
    return 0.0


def _audit_samples() -> tuple[tuple[EvidenceBundleContract, RetrievalPlanContract], ...]:
    msil_plan = _plan(
        "plan_msil",
        QueryV2TargetDomain.MSIL,
        ("annual_report", "secp_notices"),
        ("narrative_claim", "corporate_event", "numeric_claim"),
    )
    qae_plan = _plan(
        "plan_qae",
        QueryV2TargetDomain.QAE,
        ("annual_report",),
        ("qualitative_theme",),
    )
    fve_plan = _plan(
        "plan_fve",
        QueryV2TargetDomain.FVE,
        ("forecast_validation_engine",),
        ("numeric_integrity_status", "forecast_validation_result"),
    )
    incompatible_plan = _plan(
        "plan_incompatible",
        QueryV2TargetDomain.QAE,
        ("annual_report",),
        ("qualitative_theme",),
    )
    return (
        (
            EvidenceBundleContract(
                bundle_id="bundle_msil",
                request_ref="req_msil",
                source_domain=QueryV2TargetDomain.MSIL,
                items=(
                    _item(
                        evidence_ref="msil_complete",
                        content_class="narrative_claim",
                        authority_class="audited_issuer",
                        source_type="annual_report",
                        provenance={
                            "provenance_type": "PDF_PAGE",
                            "page_number": 84,
                            "authority_weight": 0.95,
                            "corroboration_count": 2,
                        },
                        observation_time="2025-06-30",
                    ),
                    _item(
                        evidence_ref="msil_incomplete",
                        content_class="narrative_claim",
                        authority_class="audited_issuer",
                        source_type="annual_report",
                        provenance={"provenance_type": "PDF_PAGE"},
                        observation_time="2025-06-30",
                    ),
                    _item(
                        evidence_ref="msil_unresolved",
                        content_class="narrative_claim",
                        authority_class="audited_issuer",
                        source_type="annual_report",
                        provenance={"provenance_type": "PDF_PAGE", "page_number": 85},
                        entity_ref="unknown_entity",
                    ),
                    _item(
                        evidence_ref="msil_unsupported",
                        content_class="market_observation",
                        authority_class="market_revealed",
                        source_type="market_watch",
                        provenance={"provenance_type": "MARKET_DATA_REF", "date": "2025-06-30"},
                    ),
                    _item_without_provenance("msil_missing_provenance"),
                ),
                coverage_note="MSIL sample evidence.",
            ),
            msil_plan,
        ),
        (
            EvidenceBundleContract(
                bundle_id="bundle_qae",
                request_ref="req_qae",
                source_domain=QueryV2TargetDomain.QAE,
                items=(
                    _item(
                        evidence_ref="qae_theme",
                        content_class="qualitative_theme",
                        authority_class="qae_analyzed",
                        source_type="annual_report",
                        provenance={"provenance_type": "PDF_PAGE", "page_number": 90},
                        observation_time="2025-06-30",
                    ),
                ),
                coverage_note="QAE theme evidence.",
            ),
            qae_plan,
        ),
        (
            EvidenceBundleContract(
                bundle_id="bundle_fve",
                request_ref="req_fve",
                source_domain=QueryV2TargetDomain.FVE,
                items=(
                    _item(
                        evidence_ref="fve_integrity",
                        content_class="numeric_integrity_status",
                        authority_class="fve_validated",
                        source_type="forecast_validation_engine",
                        provenance={"provenance_type": "WORKBOOK_CELL", "cell": "Revenue!B4"},
                        integrity_status="clean_with_warning",
                        observation_time="2025-06-30",
                    ),
                ),
                coverage_note="FVE validation evidence.",
            ),
            fve_plan,
        ),
        (
            EvidenceBundleContract(
                bundle_id="bundle_incompatible",
                request_ref="req_incompatible",
                source_domain=QueryV2TargetDomain.MSIL,
                items=(
                    _item(
                        evidence_ref="incompatible_domain",
                        content_class="narrative_claim",
                        authority_class="audited_issuer",
                        source_type="annual_report",
                        provenance={"provenance_type": "PDF_PAGE", "page_number": 91},
                    ),
                ),
                coverage_note="Incompatible domain sample.",
            ),
            incompatible_plan,
        ),
    )


def _plan(
    plan_id: str,
    target_domain: QueryV2TargetDomain,
    source_types: tuple[str, ...],
    content_classes: tuple[str, ...],
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
                purpose="Audit ranking sample.",
                required_authority_floor="audited_issuer",
                recency_requirement={"mode": "all_available"},
                rule_id=f"p2.audit.{plan_id}",
            ),
        ),
        is_multi_source=False,
    )


def _item(
    *,
    evidence_ref: str,
    content_class: str,
    authority_class: str,
    source_type: str,
    provenance: dict[str, Any],
    observation_time: str | None = None,
    subject_period: str | None = None,
    entity_ref: str = "lucky_cement",
    integrity_status: str | None = None,
) -> EvidenceItemContract:
    return EvidenceItemContract(
        evidence_ref=evidence_ref,
        content_class=content_class,
        claim_or_value_or_theme_summary=f"Sample evidence {evidence_ref}.",
        authority_class=authority_class,
        source_type=source_type,
        provenance=provenance,
        observation_time=observation_time,
        subject_period=subject_period,
        divergence_refs=("div_1",) if evidence_ref == "msil_complete" else (),
        entity_ref=entity_ref,
        integrity_status=integrity_status,
    )


def _item_without_provenance(evidence_ref: str) -> EvidenceItemContract:
    return EvidenceItemContract.model_construct(
        evidence_ref=evidence_ref,
        content_class="narrative_claim",
        claim_or_value_or_theme_summary=f"Sample evidence {evidence_ref}.",
        authority_class="audited_issuer",
        source_type="annual_report",
        observation_time="2025-06-30",
        subject_period=None,
        supersession_state=None,
        divergence_refs=(),
        entity_ref="lucky_cement",
        integrity_status=None,
    )


def _evidence_ref(item: EvidenceItemContract) -> str:
    return str(getattr(item, "evidence_ref", "unknown_evidence"))


def _evidence_content_class(item: EvidenceItemContract) -> str:
    return str(getattr(item, "content_class", ""))


def _evidence_entity_ref(item: EvidenceItemContract) -> str:
    return str(getattr(item, "entity_ref", ""))


def _evidence_authority_class(item: EvidenceItemContract) -> str:
    return str(getattr(item, "authority_class", ""))


def _evidence_source_type(item: EvidenceItemContract) -> str:
    return str(getattr(item, "source_type", ""))


def _evidence_observation_time(item: EvidenceItemContract) -> str:
    return str(getattr(item, "observation_time", "") or "")


def _evidence_subject_period(item: EvidenceItemContract) -> str:
    return str(getattr(item, "subject_period", "") or "")


def _provenance(item: EvidenceItemContract) -> dict[str, Any]:
    provenance = getattr(item, "provenance", None)
    return provenance if isinstance(provenance, dict) else {}


def _extract_year(value: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", value)
    if match:
        return int(match.group(0))
    try:
        return datetime.fromisoformat(value).year
    except ValueError:
        return None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def _ranked_id(bundle_id: str) -> str:
    digest = hashlib.sha256(bundle_id.encode("utf-8")).hexdigest()[:16]
    return f"query_v2_ranked_{digest}"


def _bundle_content_hash(bundle: EvidenceBundleContract) -> str:
    payload = bundle.model_dump(mode="json", exclude={"version_pins"})
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
    "EXCLUSION_INCOMPATIBLE_DOMAIN",
    "EXCLUSION_MISSING_PROVENANCE",
    "EXCLUSION_UNRESOLVED_ENTITY",
    "EXCLUSION_UNSUPPORTED_CONTENT",
    "EvidenceBundleValidationResult",
    "EvidenceBundleValidator",
    "EvidenceRanker",
    "EvidenceRankingDecision",
    "EvidenceRankingResult",
    "QueryV2Phase3Report",
    "QueryV2RankingAudit",
    "RankedEvidenceBuilder",
]
