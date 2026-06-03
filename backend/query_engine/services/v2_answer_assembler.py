"""Deterministic Query Engine v2 answer assembly.

Phase P4 consumes ranked evidence and authored evidence bundles to build
grounded AnswerAssemblyContext and QueryResponse contracts. It does not render
user-facing citations, present divergence, present authority, or use LLM logic.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.v2_contracts import (
    AnswerAssemblyContextContract,
    CitationContract,
    EvidenceBundleContract,
    EvidenceItemContract,
    QueryIntentContract,
    QueryResponseContract,
    QueryV2CitationType,
    QueryV2ClaimContract,
    QueryV2IntentType,
    QueryV2PrecisionLevel,
    QueryV2RankingSignal,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
    RankedEvidenceContract,
    RankedEvidenceItemContract,
)


class QueryV2AssemblyStatus(str, Enum):
    """Phase P4 assembly statuses requested by the implementation scope."""

    SUCCESS = "SUCCESS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSUPPORTED_INTENT = "UNSUPPORTED_INTENT"


class GroundedEvidence(BaseModel):
    """Evidence item joined to its ranked-evidence metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str
    ranked_item: RankedEvidenceItemContract
    evidence_item: EvidenceItemContract
    evidence_confidence: float = Field(..., ge=0, le=1)
    authority_ceiling: float = Field(..., ge=0, le=1)
    claim_confidence: float = Field(..., ge=0, le=1)
    integrity_status: str | None = None
    validation_status: str | None = None


class AnswerAssemblyContextBuildResult(BaseModel):
    """Context-building result with audit details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context: AnswerAssemblyContextContract
    grounded_evidence: tuple[GroundedEvidence, ...] = Field(default_factory=tuple)
    ungrounded_evidence_refs: tuple[str, ...] = Field(default_factory=tuple)
    weakest_supporting_evidence: float = Field(..., ge=0, le=1)
    authority_ceiling: float = Field(..., ge=0, le=1)
    confidence_ceiling_applied: bool


class AnswerAssemblyResult(BaseModel):
    """Final P4 assembly output for one query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_intent: QueryIntentContract
    ranked_evidence: RankedEvidenceContract
    assembly_context: AnswerAssemblyContextContract
    query_response: QueryResponseContract
    assembly_status: QueryV2AssemblyStatus
    answer_type: str
    grounded_claim_count: int = Field(..., ge=0)
    ungrounded_claim_count: int = Field(..., ge=0)
    confidence_ceiling_applied: bool
    weakest_supporting_evidence: float = Field(..., ge=0, le=1)
    authority_ceiling: float = Field(..., ge=0, le=1)
    integrity_statuses: tuple[str, ...] = Field(default_factory=tuple)
    validation_statuses: tuple[str, ...] = Field(default_factory=tuple)
    divergence_refs_consumed: tuple[str, ...] = Field(default_factory=tuple)
    authority_metadata_consumed: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    evidence_modified: bool = False
    llm_used: bool = False


class QueryV2AssemblyAudit(BaseModel):
    """Audit payload for Query v2 Phase P4 answer assembly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    responses_assembled: int = Field(..., ge=0)
    grounded_claims: int = Field(..., ge=0)
    ungrounded_claims: int = Field(..., ge=0)
    confidence_ceiling_applications: int = Field(..., ge=0)
    insufficient_evidence_responses: int = Field(..., ge=0)
    clarification_responses: int = Field(..., ge=0)
    unsupported_responses: int = Field(..., ge=0)
    answer_type_coverage: dict[str, int]
    response_status_counts: dict[str, int]
    integrity_statuses_preserved: tuple[str, ...]
    validation_statuses_preserved: tuple[str, ...]
    authority_metadata_consumed: int = Field(..., ge=0)
    divergence_refs_consumed: int = Field(..., ge=0)
    confidence_rule: str
    llm_used: bool
    sample_results: tuple[dict[str, Any], ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryV2Phase4Report(BaseModel):
    """Implementation report for Query v2 Phase P4."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    assembler: str
    builders: tuple[str, ...]
    audit_path: str
    validation_passed: bool
    responses_assembled: int = Field(..., ge=0)
    grounded_claims: int = Field(..., ge=0)
    ungrounded_claims: int = Field(..., ge=0)
    confidence_ceiling_applications: int = Field(..., ge=0)
    insufficient_evidence_responses: int = Field(..., ge=0)
    clarification_responses: int = Field(..., ge=0)
    unsupported_responses: int = Field(..., ge=0)
    prohibited_implementations: tuple[str, ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class AnswerAssemblyContextBuilder:
    """Build AnswerAssemblyContext from ranked evidence and authored bundles."""

    def build(
        self,
        *,
        query_intent: QueryIntentContract,
        ranked_evidence: RankedEvidenceContract,
        evidence_bundles: Iterable[EvidenceBundleContract],
    ) -> AnswerAssemblyContextBuildResult:
        """Join ranked refs to evidence items and build the frozen context."""

        evidence_by_ref = _evidence_by_ref(evidence_bundles)
        grounded: list[GroundedEvidence] = []
        ungrounded_refs: list[str] = []
        for ranked_item in sorted(ranked_evidence.ranked_items, key=lambda item: item.rank):
            if not ranked_item.included:
                continue
            evidence_item = evidence_by_ref.get(ranked_item.evidence_ref)
            if evidence_item is None:
                ungrounded_refs.append(ranked_item.evidence_ref)
                continue
            evidence_confidence = _evidence_confidence(evidence_item, ranked_item)
            authority_ceiling = _authority_ceiling(evidence_item, ranked_item)
            grounded.append(
                GroundedEvidence(
                    evidence_ref=ranked_item.evidence_ref,
                    ranked_item=ranked_item,
                    evidence_item=evidence_item,
                    evidence_confidence=evidence_confidence,
                    authority_ceiling=authority_ceiling,
                    claim_confidence=min(evidence_confidence, authority_ceiling),
                    integrity_status=_integrity_status(evidence_item),
                    validation_status=_validation_status(evidence_item),
                )
            )

        weakest_supporting_evidence = (
            min(item.evidence_confidence for item in grounded) if grounded else 0.0
        )
        authority_ceiling = min(item.authority_ceiling for item in grounded) if grounded else 0.0
        confidence_ceiling = min(weakest_supporting_evidence, authority_ceiling)
        context = AnswerAssemblyContextContract(
            context_id=_context_id(query_intent.query_id, ranked_evidence.ranked_id),
            intent_ref=query_intent.query_id,
            ranked_evidence_refs=tuple(item.evidence_ref for item in grounded),
            domain_conclusions=_domain_conclusions(grounded),
            divergence_set=_divergence_set(grounded),
            authority_set=_authority_set(grounded),
            confidence_ceiling=confidence_ceiling,
            insufficiency_flag=not grounded,
        )
        return AnswerAssemblyContextBuildResult(
            context=context,
            grounded_evidence=tuple(grounded),
            ungrounded_evidence_refs=tuple(ungrounded_refs),
            weakest_supporting_evidence=weakest_supporting_evidence,
            authority_ceiling=authority_ceiling,
            confidence_ceiling_applied=bool(grounded),
        )


class QueryResponseBuilder:
    """Build QueryResponse contracts from assembly contexts."""

    def build(
        self,
        *,
        query_intent: QueryIntentContract,
        ranked_evidence: RankedEvidenceContract,
        context_result: AnswerAssemblyContextBuildResult,
    ) -> tuple[QueryResponseContract, QueryV2AssemblyStatus]:
        """Build the frozen response and return the P4 assembly status."""

        if query_intent.intent_type == QueryV2IntentType.UNSUPPORTED:
            return (
                QueryResponseContract(
                    response_id=_response_id(query_intent.query_id, ranked_evidence.ranked_id),
                    query_id=query_intent.query_id,
                    status=QueryV2ResponseStatus.UNSUPPORTED_INTENT,
                    overall_confidence=0.0,
                ),
                QueryV2AssemblyStatus.UNSUPPORTED_INTENT,
            )
        if query_intent.needs_clarification or query_intent.intent_type == QueryV2IntentType.AMBIGUOUS:
            return (
                QueryResponseContract(
                    response_id=_response_id(query_intent.query_id, ranked_evidence.ranked_id),
                    query_id=query_intent.query_id,
                    status=QueryV2ResponseStatus.NEEDS_CLARIFICATION,
                    overall_confidence=0.0,
                    clarification_prompt=query_intent.clarification_prompt
                    or "Please clarify the intended query.",
                ),
                QueryV2AssemblyStatus.NEEDS_CLARIFICATION,
            )
        if context_result.context.insufficiency_flag:
            return (
                QueryResponseContract(
                    response_id=_response_id(query_intent.query_id, ranked_evidence.ranked_id),
                    query_id=query_intent.query_id,
                    status=QueryV2ResponseStatus.INSUFFICIENT_EVIDENCE,
                    overall_confidence=0.0,
                    warnings=("No groundable ranked evidence was available.",),
                ),
                QueryV2AssemblyStatus.INSUFFICIENT_EVIDENCE,
            )

        claims = tuple(_claim_for_evidence(item) for item in context_result.grounded_evidence)
        warnings = _warnings_for_grounded_evidence(context_result.grounded_evidence)
        response = QueryResponseContract(
            response_id=_response_id(query_intent.query_id, ranked_evidence.ranked_id),
            query_id=query_intent.query_id,
            status=QueryV2ResponseStatus.ANSWERED,
            answer_text=_answer_text(query_intent.intent_type, claims),
            claims=claims,
            warnings=warnings,
            overall_confidence=context_result.context.confidence_ceiling,
            numeric_integrity_status=_response_integrity_status(
                query_intent,
                context_result.grounded_evidence,
            ),
        )
        return response, QueryV2AssemblyStatus.SUCCESS


class AnswerAssembler:
    """Deterministic P4 answer assembly orchestrator."""

    def __init__(
        self,
        *,
        context_builder: AnswerAssemblyContextBuilder | None = None,
        response_builder: QueryResponseBuilder | None = None,
    ) -> None:
        self._context_builder = context_builder or AnswerAssemblyContextBuilder()
        self._response_builder = response_builder or QueryResponseBuilder()

    def assemble(
        self,
        *,
        query_intent: QueryIntentContract,
        ranked_evidence: RankedEvidenceContract,
        evidence_bundles: Iterable[EvidenceBundleContract],
    ) -> AnswerAssemblyResult:
        """Assemble a deterministic response from ranked evidence."""

        bundle_tuple = tuple(evidence_bundles)
        before_hash = _bundles_content_hash(bundle_tuple)
        context_result = self._context_builder.build(
            query_intent=query_intent,
            ranked_evidence=ranked_evidence,
            evidence_bundles=bundle_tuple,
        )
        response, assembly_status = self._response_builder.build(
            query_intent=query_intent,
            ranked_evidence=ranked_evidence,
            context_result=context_result,
        )
        after_hash = _bundles_content_hash(bundle_tuple)
        divergence_refs = tuple(
            dict.fromkeys(
                ref
                for item in context_result.grounded_evidence
                for ref in item.evidence_item.divergence_refs
            )
        )
        authority_metadata = _authority_set(context_result.grounded_evidence)
        integrity_statuses = tuple(
            dict.fromkeys(
                status for status in (item.integrity_status for item in context_result.grounded_evidence) if status
            )
        )
        validation_statuses = tuple(
            dict.fromkeys(
                status for status in (item.validation_status for item in context_result.grounded_evidence) if status
            )
        )
        return AnswerAssemblyResult(
            query_intent=query_intent,
            ranked_evidence=ranked_evidence,
            assembly_context=context_result.context,
            query_response=response,
            assembly_status=assembly_status,
            answer_type=_answer_type(query_intent.intent_type),
            grounded_claim_count=len(response.claims),
            ungrounded_claim_count=len(context_result.ungrounded_evidence_refs),
            confidence_ceiling_applied=context_result.confidence_ceiling_applied,
            weakest_supporting_evidence=context_result.weakest_supporting_evidence,
            authority_ceiling=context_result.authority_ceiling,
            integrity_statuses=integrity_statuses,
            validation_statuses=validation_statuses,
            divergence_refs_consumed=divergence_refs,
            authority_metadata_consumed=authority_metadata,
            evidence_modified=before_hash != after_hash,
        )

    def write_assembly_audit(
        self,
        output_path: str | Path = "output/query_v2_assembly_audit.json",
    ) -> QueryV2AssemblyAudit:
        """Run and persist the deterministic P4 assembly audit."""

        audit = self.build_assembly_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase4_report(
        self,
        *,
        audit_path: str | Path = "output/query_v2_assembly_audit.json",
        report_path: str | Path = "output/query_v2_phase4_report.json",
    ) -> QueryV2Phase4Report:
        """Write the P4 assembly audit and implementation report."""

        audit = self.write_assembly_audit(audit_path)
        report = QueryV2Phase4Report(
            phase="P4",
            scope="Deterministic answer assembly only",
            assembler="AnswerAssembler",
            builders=("AnswerAssemblyContextBuilder", "QueryResponseBuilder"),
            audit_path=str(audit_path),
            validation_passed=audit.validation_passed,
            responses_assembled=audit.responses_assembled,
            grounded_claims=audit.grounded_claims,
            ungrounded_claims=audit.ungrounded_claims,
            confidence_ceiling_applications=audit.confidence_ceiling_applications,
            insufficient_evidence_responses=audit.insufficient_evidence_responses,
            clarification_responses=audit.clarification_responses,
            unsupported_responses=audit.unsupported_responses,
            prohibited_implementations=(
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

    def build_assembly_audit(self) -> QueryV2AssemblyAudit:
        """Build the deterministic P4 assembly audit payload."""

        results = [
            self.assemble(
                query_intent=query_intent,
                ranked_evidence=ranked_evidence,
                evidence_bundles=evidence_bundles,
            )
            for query_intent, ranked_evidence, evidence_bundles in _audit_samples()
        ]
        status_counts = Counter(result.assembly_status.value for result in results)
        answer_type_counts = Counter(result.answer_type for result in results)
        grounded_claims = sum(result.grounded_claim_count for result in results)
        ungrounded_claims = sum(result.ungrounded_claim_count for result in results)
        confidence_applications = sum(
            1 for result in results if result.confidence_ceiling_applied
        )
        integrity_statuses = tuple(
            sorted(
                {
                    status
                    for result in results
                    for status in result.integrity_statuses
                }
            )
        )
        validation_statuses = tuple(
            sorted(
                {
                    status
                    for result in results
                    for status in result.validation_statuses
                }
            )
        )
        sample_results = tuple(_sample_payload(result) for result in results)
        violations: list[dict[str, Any]] = []
        expected_answer_types = {
            "factual_lookup",
            "metric_lookup",
            "qualitative_analysis",
            "forecast_validation",
            "comparison",
            "timeline",
            "risk_analysis",
            "source_exploration",
        }
        missing_answer_types = expected_answer_types - set(answer_type_counts)
        if missing_answer_types:
            violations.append(
                _violation(
                    "answer_type_coverage",
                    "AnswerAssembler",
                    "Not every supported answer type was assembled in the audit.",
                    tuple(sorted(missing_answer_types)),
                )
            )
        if grounded_claims <= 0:
            violations.append(
                _violation(
                    "claim_grounding",
                    "AnswerAssembler",
                    "No grounded claims were assembled.",
                    {},
                )
            )
        if confidence_applications <= 0:
            violations.append(
                _violation(
                    "confidence_ceiling",
                    "AnswerAssemblyContextBuilder",
                    "No confidence ceiling applications were observed.",
                    {},
                )
            )
        if status_counts[QueryV2AssemblyStatus.INSUFFICIENT_EVIDENCE.value] <= 0:
            violations.append(
                _violation(
                    "insufficient_evidence_response",
                    "QueryResponseBuilder",
                    "No insufficient-evidence response was observed.",
                    {},
                )
            )
        if status_counts[QueryV2AssemblyStatus.NEEDS_CLARIFICATION.value] <= 0:
            violations.append(
                _violation(
                    "clarification_response",
                    "QueryResponseBuilder",
                    "No clarification response was observed.",
                    {},
                )
            )
        if status_counts[QueryV2AssemblyStatus.UNSUPPORTED_INTENT.value] <= 0:
            violations.append(
                _violation(
                    "unsupported_response",
                    "QueryResponseBuilder",
                    "No unsupported response was observed.",
                    {},
                )
            )
        if any(result.evidence_modified for result in results):
            violations.append(
                _violation(
                    "as_authored_preservation",
                    "AnswerAssembler",
                    "Evidence bundle content was modified during assembly.",
                    {},
                )
            )
        if any(result.llm_used for result in results):
            violations.append(
                _violation(
                    "llm_usage",
                    "AnswerAssembler",
                    "LLM usage is forbidden in P4.",
                    {},
                )
            )
        if "clean_with_warning" not in integrity_statuses:
            violations.append(
                _violation(
                    "metric_integrity_preservation",
                    "QueryResponseBuilder",
                    "Metric integrity status was not preserved in audit samples.",
                    integrity_statuses,
                )
            )
        if "PASS" not in validation_statuses:
            violations.append(
                _violation(
                    "metric_validation_preservation",
                    "QueryResponseBuilder",
                    "Metric validation status was not preserved in audit samples.",
                    validation_statuses,
                )
            )

        return QueryV2AssemblyAudit(
            validation_passed=not violations,
            responses_assembled=len(results),
            grounded_claims=grounded_claims,
            ungrounded_claims=ungrounded_claims,
            confidence_ceiling_applications=confidence_applications,
            insufficient_evidence_responses=status_counts[
                QueryV2AssemblyStatus.INSUFFICIENT_EVIDENCE.value
            ],
            clarification_responses=status_counts[
                QueryV2AssemblyStatus.NEEDS_CLARIFICATION.value
            ],
            unsupported_responses=status_counts[
                QueryV2AssemblyStatus.UNSUPPORTED_INTENT.value
            ],
            answer_type_coverage=dict(sorted(answer_type_counts.items())),
            response_status_counts=dict(sorted(status_counts.items())),
            integrity_statuses_preserved=integrity_statuses,
            validation_statuses_preserved=validation_statuses,
            authority_metadata_consumed=sum(
                len(result.authority_metadata_consumed) for result in results
            ),
            divergence_refs_consumed=sum(
                len(result.divergence_refs_consumed) for result in results
            ),
            confidence_rule="min(weakest_supporting_evidence, authority_ceiling)",
            llm_used=False,
            sample_results=sample_results,
            integrity_violations=tuple(violations),
        )


def _claim_for_evidence(grounded: GroundedEvidence) -> QueryV2ClaimContract:
    item = grounded.evidence_item
    return QueryV2ClaimContract(
        statement=item.claim_or_value_or_theme_summary,
        supporting_evidence_refs=(grounded.evidence_ref,),
        authority_class=item.authority_class,
        citations=(_provenance_trace(item),),
        confidence=grounded.claim_confidence,
        numeric_integrity_status=grounded.integrity_status,
    )


def _provenance_trace(item: EvidenceItemContract) -> CitationContract:
    provenance = _provenance(item)
    citation_type = _citation_type(provenance)
    source_ref = _source_ref(provenance, item.evidence_ref)
    return CitationContract(
        citation_id=f"trace_{item.evidence_ref}",
        citation_type=citation_type,
        source_ref=source_ref,
        entity_ref=item.entity_ref,
        evidence_ref=item.evidence_ref,
        rendered_text=source_ref,
        precision_level=_precision_level(citation_type),
    )


def _citation_type(provenance: dict[str, Any]) -> QueryV2CitationType:
    provenance_type = str(provenance.get("provenance_type", "PDF_PAGE")).upper()
    try:
        return QueryV2CitationType(provenance_type)
    except ValueError:
        return QueryV2CitationType.PDF_PAGE


def _precision_level(citation_type: QueryV2CitationType) -> QueryV2PrecisionLevel:
    if citation_type == QueryV2CitationType.WORKBOOK_CELL:
        return QueryV2PrecisionLevel.CELL
    if citation_type == QueryV2CitationType.PDF_PAGE:
        return QueryV2PrecisionLevel.PAGE
    if citation_type in {
        QueryV2CitationType.MARKET_DATA_REF,
        QueryV2CitationType.FUTURES_REF,
    }:
        return QueryV2PrecisionLevel.DATE
    return QueryV2PrecisionLevel.REF


def _source_ref(provenance: dict[str, Any], evidence_ref: str) -> str:
    for key in (
        "source_ref",
        "cell",
        "announcement_id",
        "notice_id",
        "payout_id",
        "url",
        "snapshot_id",
        "date",
    ):
        value = provenance.get(key)
        if value not in (None, ""):
            return str(value)
    if provenance.get("page_number") not in (None, ""):
        return f"page:{provenance['page_number']}"
    return f"evidence:{evidence_ref}"


def _warnings_for_grounded_evidence(
    grounded_evidence: tuple[GroundedEvidence, ...],
) -> tuple[str, ...]:
    warnings: list[str] = []
    divergence_refs = tuple(
        dict.fromkeys(
            ref
            for grounded in grounded_evidence
            for ref in grounded.evidence_item.divergence_refs
        )
    )
    if divergence_refs:
        warnings.append("divergence_refs_consumed:" + ",".join(divergence_refs))
    validation_statuses = tuple(
        dict.fromkeys(
            grounded.validation_status
            for grounded in grounded_evidence
            if grounded.validation_status
        )
    )
    for status in validation_statuses:
        warnings.append(f"validation_status:{status}")
    return tuple(warnings)


def _answer_text(
    intent_type: QueryV2IntentType,
    claims: tuple[QueryV2ClaimContract, ...],
) -> str:
    if not claims:
        return ""
    prefix = {
        QueryV2IntentType.FACTUAL_LOOKUP: "Factual lookup",
        QueryV2IntentType.METRIC_LOOKUP: "Metric lookup",
        QueryV2IntentType.QUALITATIVE_ANALYSIS: "Qualitative analysis",
        QueryV2IntentType.FORECAST_VALIDATION: "Forecast validation",
        QueryV2IntentType.COMPARISON: "Comparison",
        QueryV2IntentType.TIMELINE: "Timeline",
        QueryV2IntentType.RISK_ANALYSIS: "Risk analysis",
        QueryV2IntentType.SOURCE_EXPLORATION: "Source exploration",
    }.get(intent_type, "Answer")
    return f"{prefix}: " + " ".join(claim.statement for claim in claims)


def _response_integrity_status(
    query_intent: QueryIntentContract,
    grounded_evidence: tuple[GroundedEvidence, ...],
) -> str | None:
    if query_intent.intent_type not in {
        QueryV2IntentType.METRIC_LOOKUP,
        QueryV2IntentType.COMPARISON,
        QueryV2IntentType.FORECAST_VALIDATION,
    }:
        return None
    statuses = tuple(
        dict.fromkeys(
            grounded.integrity_status
            for grounded in grounded_evidence
            if grounded.integrity_status
        )
    )
    validation_statuses = tuple(
        dict.fromkeys(
            grounded.validation_status
            for grounded in grounded_evidence
            if grounded.validation_status
        )
    )
    parts: list[str] = []
    if statuses:
        parts.append("integrity_status=" + ",".join(statuses))
    if validation_statuses:
        parts.append("validation_status=" + ",".join(validation_statuses))
    return ";".join(parts) if parts else "not_provided"


def _evidence_by_ref(
    evidence_bundles: Iterable[EvidenceBundleContract],
) -> dict[str, EvidenceItemContract]:
    evidence: dict[str, EvidenceItemContract] = {}
    for bundle in evidence_bundles:
        for item in bundle.items:
            evidence[item.evidence_ref] = item
    return evidence


def _domain_conclusions(grounded: Iterable[GroundedEvidence]) -> tuple[dict[str, Any], ...]:
    conclusions: list[dict[str, Any]] = []
    for item in grounded:
        if item.evidence_item.content_class in {
            "qualitative_theme",
            "forecast_validation_result",
            "numeric_integrity_status",
        }:
            conclusions.append(
                {
                    "evidence_ref": item.evidence_ref,
                    "content_class": item.evidence_item.content_class,
                    "summary": item.evidence_item.claim_or_value_or_theme_summary,
                    "integrity_status": item.integrity_status,
                    "validation_status": item.validation_status,
                }
            )
    return tuple(conclusions)


def _divergence_set(grounded: Iterable[GroundedEvidence]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "evidence_ref": item.evidence_ref,
            "divergence_refs": item.evidence_item.divergence_refs,
        }
        for item in grounded
        if item.evidence_item.divergence_refs
    )


def _authority_set(grounded: Iterable[GroundedEvidence]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "evidence_ref": item.evidence_ref,
            "authority_class": item.evidence_item.authority_class,
            "source_type": item.evidence_item.source_type,
            "authority_ceiling": item.authority_ceiling,
        }
        for item in grounded
    )


def _evidence_confidence(
    evidence_item: EvidenceItemContract,
    ranked_item: RankedEvidenceItemContract,
) -> float:
    provenance = _provenance(evidence_item)
    for key in ("evidence_confidence", "confidence", "source_confidence"):
        value = provenance.get(key)
        if isinstance(value, int | float):
            return _clamp(float(value))
    return _clamp(
        ranked_item.ranking_signals.get(
            QueryV2RankingSignal.PROVENANCE_COMPLETENESS,
            0.5,
        )
    )


def _authority_ceiling(
    evidence_item: EvidenceItemContract,
    ranked_item: RankedEvidenceItemContract,
) -> float:
    provenance = _provenance(evidence_item)
    for key in ("authority_ceiling", "authority_weight"):
        value = provenance.get(key)
        if isinstance(value, int | float):
            return _clamp(float(value))
    return _clamp(
        ranked_item.ranking_signals.get(
            QueryV2RankingSignal.AUTHORITY_WEIGHT,
            0.5,
        )
    )


def _integrity_status(evidence_item: EvidenceItemContract) -> str | None:
    if evidence_item.integrity_status:
        return evidence_item.integrity_status
    value = _provenance(evidence_item).get("integrity_status")
    return str(value) if value not in (None, "") else None


def _validation_status(evidence_item: EvidenceItemContract) -> str | None:
    value = _provenance(evidence_item).get("validation_status")
    return str(value) if value not in (None, "") else None


def _provenance(evidence_item: EvidenceItemContract) -> dict[str, Any]:
    provenance = getattr(evidence_item, "provenance", None)
    return provenance if isinstance(provenance, dict) else {}


def _answer_type(intent_type: QueryV2IntentType) -> str:
    return intent_type.value


def _context_id(query_id: str, ranked_id: str) -> str:
    return "query_v2_context_" + _digest(f"{query_id}:{ranked_id}")


def _response_id(query_id: str, ranked_id: str) -> str:
    return "query_v2_response_" + _digest(f"{query_id}:{ranked_id}")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def _bundles_content_hash(evidence_bundles: tuple[EvidenceBundleContract, ...]) -> str:
    payload = [bundle.model_dump(mode="json", exclude={"version_pins"}) for bundle in evidence_bundles]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _audit_samples() -> tuple[
    tuple[QueryIntentContract, RankedEvidenceContract, tuple[EvidenceBundleContract, ...]],
    ...,
]:
    return (
        *(
            _success_sample(intent_type)
            for intent_type in (
                QueryV2IntentType.FACTUAL_LOOKUP,
                QueryV2IntentType.METRIC_LOOKUP,
                QueryV2IntentType.QUALITATIVE_ANALYSIS,
                QueryV2IntentType.FORECAST_VALIDATION,
                QueryV2IntentType.COMPARISON,
                QueryV2IntentType.TIMELINE,
                QueryV2IntentType.RISK_ANALYSIS,
                QueryV2IntentType.SOURCE_EXPLORATION,
            )
        ),
        _insufficient_sample(),
        _clarification_sample(),
        _unsupported_sample(),
        _ungrounded_sample(),
    )


def _success_sample(
    intent_type: QueryV2IntentType,
) -> tuple[QueryIntentContract, RankedEvidenceContract, tuple[EvidenceBundleContract, ...]]:
    evidence_ref = f"ev_{intent_type.value}"
    content_class = {
        QueryV2IntentType.METRIC_LOOKUP: "numeric_integrity_status",
        QueryV2IntentType.FORECAST_VALIDATION: "forecast_validation_result",
        QueryV2IntentType.QUALITATIVE_ANALYSIS: "qualitative_theme",
        QueryV2IntentType.RISK_ANALYSIS: "qualitative_theme",
    }.get(intent_type, "narrative_claim")
    integrity_status = "clean_with_warning" if intent_type in {
        QueryV2IntentType.METRIC_LOOKUP,
        QueryV2IntentType.COMPARISON,
        QueryV2IntentType.FORECAST_VALIDATION,
    } else None
    provenance = {
        "provenance_type": "WORKBOOK_CELL" if integrity_status else "PDF_PAGE",
        "page_number": 84,
        "cell": "Revenue!B4" if integrity_status else None,
        "confidence": 0.82,
        "authority_weight": 0.74,
        "validation_status": "PASS" if integrity_status else None,
    }
    item = EvidenceItemContract(
        evidence_ref=evidence_ref,
        content_class=content_class,
        claim_or_value_or_theme_summary=f"{intent_type.value} grounded claim.",
        authority_class="fve_validated" if integrity_status else "audited_issuer",
        source_type="forecast_validation_engine" if integrity_status else "annual_report",
        provenance={key: value for key, value in provenance.items() if value is not None},
        observation_time="2025-06-30",
        divergence_refs=("div_1",) if intent_type == QueryV2IntentType.RISK_ANALYSIS else (),
        entity_ref="lucky_cement",
        integrity_status=integrity_status,
    )
    return (
        _intent(
            query_id=f"q_{intent_type.value}",
            intent_type=intent_type,
            requested_metrics_or_topics=("revenue",) if integrity_status else (),
        ),
        _ranked("ranked_" + intent_type.value, evidence_ref),
        (
            EvidenceBundleContract(
                bundle_id="bundle_" + intent_type.value,
                request_ref="request_" + intent_type.value,
                source_domain=QueryV2TargetDomain.FVE
                if integrity_status
                else QueryV2TargetDomain.MSIL,
                items=(item,),
                coverage_note="Audit evidence.",
            ),
        ),
    )


def _insufficient_sample() -> tuple[
    QueryIntentContract,
    RankedEvidenceContract,
    tuple[EvidenceBundleContract, ...],
]:
    return (
        _intent("q_insufficient", QueryV2IntentType.METRIC_LOOKUP, ("revenue",)),
        RankedEvidenceContract(ranked_id="ranked_insufficient", bundle_ref="bundle_empty"),
        (
            EvidenceBundleContract(
                bundle_id="bundle_empty",
                request_ref="request_empty",
                source_domain=QueryV2TargetDomain.MSIL,
                items=(),
                coverage_note="No evidence.",
            ),
        ),
    )


def _clarification_sample() -> tuple[
    QueryIntentContract,
    RankedEvidenceContract,
    tuple[EvidenceBundleContract, ...],
]:
    return (
        QueryIntentContract(
            query_id="q_clarify",
            raw_query="Tell me about Lucky.",
            intent_type=QueryV2IntentType.AMBIGUOUS,
            classification_confidence=0.5,
            needs_clarification=True,
            clarification_prompt="Please clarify the requested analysis.",
        ),
        RankedEvidenceContract(ranked_id="ranked_clarify", bundle_ref="bundle_empty"),
        (),
    )


def _unsupported_sample() -> tuple[
    QueryIntentContract,
    RankedEvidenceContract,
    tuple[EvidenceBundleContract, ...],
]:
    return (
        _intent("q_unsupported", QueryV2IntentType.UNSUPPORTED),
        RankedEvidenceContract(ranked_id="ranked_unsupported", bundle_ref="bundle_empty"),
        (),
    )


def _ungrounded_sample() -> tuple[
    QueryIntentContract,
    RankedEvidenceContract,
    tuple[EvidenceBundleContract, ...],
]:
    return (
        _intent("q_ungrounded", QueryV2IntentType.FACTUAL_LOOKUP),
        _ranked("ranked_ungrounded", "missing_ref"),
        (
            EvidenceBundleContract(
                bundle_id="bundle_ungrounded",
                request_ref="request_ungrounded",
                source_domain=QueryV2TargetDomain.MSIL,
                items=(),
                coverage_note="Missing ranked evidence item.",
            ),
        ),
    )


def _intent(
    query_id: str,
    intent_type: QueryV2IntentType,
    requested_metrics_or_topics: tuple[str, ...] = (),
) -> QueryIntentContract:
    return QueryIntentContract(
        query_id=query_id,
        raw_query=query_id.replace("_", " "),
        intent_type=intent_type,
        requested_metrics_or_topics=requested_metrics_or_topics,
        classification_confidence=0.9,
        needs_clarification=False,
    )


def _ranked(ranked_id: str, evidence_ref: str) -> RankedEvidenceContract:
    return RankedEvidenceContract(
        ranked_id=ranked_id,
        bundle_ref="bundle_" + ranked_id,
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


def _sample_payload(result: AnswerAssemblyResult) -> dict[str, Any]:
    return {
        "query_id": result.query_intent.query_id,
        "intent_type": result.query_intent.intent_type.value,
        "answer_type": result.answer_type,
        "assembly_status": result.assembly_status.value,
        "query_response_status": result.query_response.status.value,
        "grounded_claim_count": result.grounded_claim_count,
        "ungrounded_claim_count": result.ungrounded_claim_count,
        "confidence_ceiling": result.assembly_context.confidence_ceiling,
        "weakest_supporting_evidence": result.weakest_supporting_evidence,
        "authority_ceiling": result.authority_ceiling,
        "integrity_statuses": result.integrity_statuses,
        "validation_statuses": result.validation_statuses,
        "divergence_refs_consumed": result.divergence_refs_consumed,
    }


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
    "AnswerAssembler",
    "AnswerAssemblyContextBuildResult",
    "AnswerAssemblyContextBuilder",
    "AnswerAssemblyResult",
    "GroundedEvidence",
    "QueryResponseBuilder",
    "QueryV2AssemblyAudit",
    "QueryV2AssemblyStatus",
    "QueryV2Phase4Report",
]
