"""Deterministic Query Engine v2 citation enforcement.

Phase P5 consumes an assembled QueryResponse and original evidence bundles,
then ships only claims that can be cited from MSIL-backed provenance. It renders
citations at the precision actually supported by provenance and drops claims
that would otherwise be uncited or over-precise.
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
    QueryResponseContract,
    QueryV2CitationType,
    QueryV2ClaimContract,
    QueryV2PrecisionLevel,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
)


EXCLUSION_MISSING_PROVENANCE = "missing_provenance"
EXCLUSION_NONE_PROVENANCE = "none_provenance"
EXCLUSION_UNSUPPORTED_PROVENANCE = "unsupported_provenance"
EXCLUSION_MISSING_EVIDENCE = "missing_evidence"
EXCLUSION_PRECISION_VIOLATION = "precision_violation"


class CitationEnforcementStatus(str, Enum):
    """Outcome state after citation enforcement."""

    SUCCESS = "SUCCESS"
    SUCCESS_WITH_DROPPED_CLAIMS = "SUCCESS_WITH_DROPPED_CLAIMS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSUPPORTED_INTENT = "UNSUPPORTED_INTENT"


class CitationValidationResult(BaseModel):
    """Validation and rendering result for one evidence citation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str
    valid: bool
    citation: CitationContract | None = None
    exclusion_reason: str | None = None
    provenance_origin: str | None = None
    provenance_type: str | None = None
    precision_level: QueryV2PrecisionLevel | None = None
    precision_violation: bool = False


class ClaimCitationDecision(BaseModel):
    """Claim-level citation enforcement decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_statement: str
    shipped: bool
    supporting_evidence_refs: tuple[str, ...]
    citations: tuple[CitationContract, ...] = Field(default_factory=tuple)
    exclusion_reason: str | None = None
    validation_results: tuple[CitationValidationResult, ...] = Field(
        default_factory=tuple
    )


class CitationEnforcementResult(BaseModel):
    """Final P5 result for one assembled response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_response: QueryResponseContract
    enforced_response: QueryResponseContract
    assembly_context: AnswerAssemblyContextContract
    status: CitationEnforcementStatus
    claims_evaluated: int = Field(..., ge=0)
    claims_cited: int = Field(..., ge=0)
    claims_dropped: int = Field(..., ge=0)
    missing_provenance_exclusions: int = Field(..., ge=0)
    none_provenance_exclusions: int = Field(..., ge=0)
    unsupported_provenance_exclusions: int = Field(..., ge=0)
    citation_precision_violations: int = Field(..., ge=0)
    decisions: tuple[ClaimCitationDecision, ...] = Field(default_factory=tuple)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryV2CitationAudit(BaseModel):
    """Audit payload for Query v2 Phase P5 citation enforcement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    claims_evaluated: int = Field(..., ge=0)
    claims_cited: int = Field(..., ge=0)
    claims_dropped: int = Field(..., ge=0)
    missing_provenance_exclusions: int = Field(..., ge=0)
    none_provenance_exclusions: int = Field(..., ge=0)
    unsupported_provenance_exclusions: int = Field(..., ge=0)
    citation_precision_violations: int = Field(..., ge=0)
    response_status_counts: dict[str, int]
    provenance_origin_counts: dict[str, int]
    citation_type_counts: dict[str, int]
    precision_level_counts: dict[str, int]
    sample_results: tuple[dict[str, Any], ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryV2Phase5Report(BaseModel):
    """Implementation report for Query v2 Phase P5."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    enforcer: str
    services: tuple[str, ...]
    audit_path: str
    validation_passed: bool
    claims_evaluated: int = Field(..., ge=0)
    claims_cited: int = Field(..., ge=0)
    claims_dropped: int = Field(..., ge=0)
    missing_provenance_exclusions: int = Field(..., ge=0)
    none_provenance_exclusions: int = Field(..., ge=0)
    unsupported_provenance_exclusions: int = Field(..., ge=0)
    citation_precision_violations: int = Field(..., ge=0)
    prohibited_implementations: tuple[str, ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class CitationValidator:
    """Validate whether evidence provenance can support a Query v2 citation."""

    def validate(self, evidence_item: EvidenceItemContract) -> CitationValidationResult:
        """Return the citation eligibility for an evidence item."""

        evidence_ref = _evidence_ref(evidence_item)
        provenance = _provenance(evidence_item)
        if not provenance:
            return CitationValidationResult(
                evidence_ref=evidence_ref,
                valid=False,
                exclusion_reason=EXCLUSION_MISSING_PROVENANCE,
            )

        provenance_type = _provenance_type(provenance)
        if provenance_type == "NONE":
            return CitationValidationResult(
                evidence_ref=evidence_ref,
                valid=False,
                exclusion_reason=EXCLUSION_NONE_PROVENANCE,
                provenance_type=provenance_type,
            )
        if provenance_type not in _SUPPORTED_PROVENANCE_TYPES:
            return CitationValidationResult(
                evidence_ref=evidence_ref,
                valid=False,
                exclusion_reason=EXCLUSION_UNSUPPORTED_PROVENANCE,
                provenance_type=provenance_type or None,
            )

        locator_valid, precision = _locator_and_precision(provenance_type, provenance)
        if not locator_valid:
            return CitationValidationResult(
                evidence_ref=evidence_ref,
                valid=False,
                exclusion_reason=EXCLUSION_UNSUPPORTED_PROVENANCE,
                provenance_type=provenance_type,
            )

        citation_type = QueryV2CitationType(provenance_type)
        citation = CitationRenderer().render(
            evidence_item=evidence_item,
            citation_type=citation_type,
            precision_level=precision,
        )
        precision_violation = self.precision_violation(citation, provenance)
        return CitationValidationResult(
            evidence_ref=evidence_ref,
            valid=not precision_violation,
            citation=None if precision_violation else citation,
            exclusion_reason=(
                EXCLUSION_PRECISION_VIOLATION if precision_violation else None
            ),
            provenance_origin=_provenance_origin(provenance),
            provenance_type=provenance_type,
            precision_level=precision,
            precision_violation=precision_violation,
        )

    @staticmethod
    def precision_violation(
        citation: CitationContract,
        provenance: dict[str, Any],
    ) -> bool:
        """Detect whether a rendered citation exceeds provenance precision."""

        provenance_type = _provenance_type(provenance)
        _, allowed_precision = _locator_and_precision(provenance_type, provenance)
        if allowed_precision is None:
            return True
        return _precision_rank(citation.precision_level) > _precision_rank(
            allowed_precision
        )


class CitationRenderer:
    """Render CitationContract objects from validated MSIL-backed provenance."""

    def render(
        self,
        *,
        evidence_item: EvidenceItemContract,
        citation_type: QueryV2CitationType,
        precision_level: QueryV2PrecisionLevel,
    ) -> CitationContract:
        """Render a citation without increasing provenance precision."""

        provenance = _provenance(evidence_item)
        source_ref = _source_ref(citation_type.value, provenance)
        return CitationContract(
            citation_id=_citation_id(_evidence_ref(evidence_item), source_ref),
            citation_type=citation_type,
            source_ref=source_ref,
            entity_ref=_entity_ref(evidence_item),
            evidence_ref=_evidence_ref(evidence_item),
            rendered_text=_rendered_text(citation_type.value, provenance, source_ref),
            precision_level=precision_level,
        )


class CitationEnforcer:
    """Drop uncitable assembled claims and attach validated citations."""

    def __init__(
        self,
        *,
        validator: CitationValidator | None = None,
        renderer: CitationRenderer | None = None,
    ) -> None:
        self._validator = validator or CitationValidator()
        self._renderer = renderer or CitationRenderer()

    def enforce(
        self,
        *,
        query_response: QueryResponseContract,
        assembly_context: AnswerAssemblyContextContract,
        evidence_bundles: Iterable[EvidenceBundleContract],
    ) -> CitationEnforcementResult:
        """Enforce citation support for every shipped claim."""

        if query_response.status == QueryV2ResponseStatus.NEEDS_CLARIFICATION:
            return _offramp_result(
                query_response=query_response,
                assembly_context=assembly_context,
                status=CitationEnforcementStatus.NEEDS_CLARIFICATION,
            )
        if query_response.status == QueryV2ResponseStatus.UNSUPPORTED_INTENT:
            return _offramp_result(
                query_response=query_response,
                assembly_context=assembly_context,
                status=CitationEnforcementStatus.UNSUPPORTED_INTENT,
            )
        if query_response.status == QueryV2ResponseStatus.INSUFFICIENT_EVIDENCE:
            return _offramp_result(
                query_response=query_response,
                assembly_context=assembly_context,
                status=CitationEnforcementStatus.INSUFFICIENT_EVIDENCE,
            )

        evidence_by_ref = _evidence_by_ref(evidence_bundles)
        context_refs = set(assembly_context.ranked_evidence_refs)
        kept_claims: list[QueryV2ClaimContract] = []
        decisions: list[ClaimCitationDecision] = []
        integrity_violations: list[dict[str, Any]] = []

        for claim in query_response.claims:
            decision = self._evaluate_claim(
                claim=claim,
                evidence_by_ref=evidence_by_ref,
                context_refs=context_refs,
                integrity_violations=integrity_violations,
            )
            decisions.append(decision)
            if decision.shipped:
                kept_claims.append(
                    QueryV2ClaimContract(
                        statement=claim.statement,
                        supporting_evidence_refs=claim.supporting_evidence_refs,
                        authority_class=claim.authority_class,
                        citations=decision.citations,
                        confidence=claim.confidence,
                        numeric_integrity_status=claim.numeric_integrity_status,
                    )
                )

        claims_dropped = len(query_response.claims) - len(kept_claims)
        if not kept_claims:
            enforced = QueryResponseContract(
                response_id=query_response.response_id,
                query_id=query_response.query_id,
                status=QueryV2ResponseStatus.INSUFFICIENT_EVIDENCE,
                warnings=tuple(
                    dict.fromkeys(
                        (
                            *query_response.warnings,
                            "All assembled claims were excluded by citation enforcement.",
                        )
                    )
                ),
                overall_confidence=0.0,
                numeric_integrity_status=query_response.numeric_integrity_status,
                generated_at=query_response.generated_at,
            )
            status = CitationEnforcementStatus.INSUFFICIENT_EVIDENCE
        else:
            enforced_status = (
                QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS
                if claims_dropped
                else query_response.status
            )
            warnings = list(query_response.warnings)
            if claims_dropped:
                warnings.append(f"citation_claims_dropped:{claims_dropped}")
            enforced = QueryResponseContract(
                response_id=query_response.response_id,
                query_id=query_response.query_id,
                status=enforced_status,
                answer_text=_answer_text(kept_claims),
                claims=tuple(kept_claims),
                divergences=query_response.divergences,
                warnings=tuple(dict.fromkeys(warnings)),
                overall_confidence=min(
                    query_response.overall_confidence,
                    min(claim.confidence for claim in kept_claims),
                ),
                numeric_integrity_status=query_response.numeric_integrity_status,
                generated_at=query_response.generated_at,
            )
            status = (
                CitationEnforcementStatus.SUCCESS_WITH_DROPPED_CLAIMS
                if claims_dropped
                else CitationEnforcementStatus.SUCCESS
            )

        counts = _decision_exclusion_counts(decisions)
        precision_violations = sum(
            1
            for decision in decisions
            for result in decision.validation_results
            if result.precision_violation
        )
        return CitationEnforcementResult(
            original_response=query_response,
            enforced_response=enforced,
            assembly_context=assembly_context,
            status=status,
            claims_evaluated=len(query_response.claims),
            claims_cited=len(kept_claims),
            claims_dropped=claims_dropped,
            missing_provenance_exclusions=counts.get(
                EXCLUSION_MISSING_PROVENANCE,
                0,
            )
            + counts.get(EXCLUSION_MISSING_EVIDENCE, 0),
            none_provenance_exclusions=counts.get(EXCLUSION_NONE_PROVENANCE, 0),
            unsupported_provenance_exclusions=counts.get(
                EXCLUSION_UNSUPPORTED_PROVENANCE,
                0,
            ),
            citation_precision_violations=precision_violations,
            decisions=tuple(decisions),
            integrity_violations=tuple(integrity_violations),
        )

    def _evaluate_claim(
        self,
        *,
        claim: QueryV2ClaimContract,
        evidence_by_ref: dict[str, EvidenceItemContract],
        context_refs: set[str],
        integrity_violations: list[dict[str, Any]],
    ) -> ClaimCitationDecision:
        validation_results: list[CitationValidationResult] = []
        citations: list[CitationContract] = []
        for evidence_ref in claim.supporting_evidence_refs:
            if evidence_ref not in context_refs:
                integrity_violations.append(
                    _violation(
                        "claim_not_grounded_in_assembly_context",
                        "CitationEnforcer",
                        "Claim supporting evidence is not present in the assembly context.",
                        {"evidence_ref": evidence_ref, "statement": claim.statement},
                    )
                )
            evidence_item = evidence_by_ref.get(evidence_ref)
            if evidence_item is None:
                validation_results.append(
                    CitationValidationResult(
                        evidence_ref=evidence_ref,
                        valid=False,
                        exclusion_reason=EXCLUSION_MISSING_EVIDENCE,
                    )
                )
                continue
            result = self._validator.validate(evidence_item)
            validation_results.append(result)
            if result.valid and result.citation is not None:
                citations.append(result.citation)

        invalid_results = tuple(result for result in validation_results if not result.valid)
        if invalid_results or not citations:
            reason = (
                invalid_results[0].exclusion_reason
                if invalid_results
                else EXCLUSION_MISSING_PROVENANCE
            )
            return ClaimCitationDecision(
                claim_statement=claim.statement,
                shipped=False,
                supporting_evidence_refs=claim.supporting_evidence_refs,
                exclusion_reason=reason,
                validation_results=tuple(validation_results),
            )
        return ClaimCitationDecision(
            claim_statement=claim.statement,
            shipped=True,
            supporting_evidence_refs=claim.supporting_evidence_refs,
            citations=tuple(citations),
            validation_results=tuple(validation_results),
        )

    def write_citation_audit(
        self,
        output_path: str | Path = "output/query_v2_citation_audit.json",
    ) -> QueryV2CitationAudit:
        """Run and persist the deterministic P5 citation audit."""

        audit = self.build_citation_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase5_report(
        self,
        *,
        audit_path: str | Path = "output/query_v2_citation_audit.json",
        report_path: str | Path = "output/query_v2_phase5_report.json",
    ) -> QueryV2Phase5Report:
        """Write the P5 citation audit and implementation report."""

        audit = self.write_citation_audit(audit_path)
        report = QueryV2Phase5Report(
            phase="P5",
            scope="Citation enforcement only",
            enforcer="CitationEnforcer",
            services=("CitationValidator", "CitationRenderer"),
            audit_path=str(audit_path),
            validation_passed=audit.validation_passed,
            claims_evaluated=audit.claims_evaluated,
            claims_cited=audit.claims_cited,
            claims_dropped=audit.claims_dropped,
            missing_provenance_exclusions=audit.missing_provenance_exclusions,
            none_provenance_exclusions=audit.none_provenance_exclusions,
            unsupported_provenance_exclusions=(
                audit.unsupported_provenance_exclusions
            ),
            citation_precision_violations=audit.citation_precision_violations,
            prohibited_implementations=(
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

    def build_citation_audit(self) -> QueryV2CitationAudit:
        """Build the deterministic P5 citation audit payload."""

        results = [
            self.enforce(
                query_response=response,
                assembly_context=context,
                evidence_bundles=bundles,
            )
            for response, context, bundles in _audit_samples()
        ]
        status_counts = Counter(result.status.value for result in results)
        origin_counts: Counter[str] = Counter()
        citation_type_counts: Counter[str] = Counter()
        precision_counts: Counter[str] = Counter()
        sample_results: list[dict[str, Any]] = []
        integrity_violations: list[dict[str, Any]] = []

        for result in results:
            integrity_violations.extend(result.integrity_violations)
            for decision in result.decisions:
                for validation in decision.validation_results:
                    if validation.provenance_origin:
                        origin_counts[validation.provenance_origin] += 1
                    if validation.citation:
                        citation_type_counts[validation.citation.citation_type.value] += 1
                        precision_counts[validation.citation.precision_level.value] += 1
            sample_results.append(_sample_payload(result))

        claims_evaluated = sum(result.claims_evaluated for result in results)
        claims_cited = sum(result.claims_cited for result in results)
        claims_dropped = sum(result.claims_dropped for result in results)
        missing = sum(result.missing_provenance_exclusions for result in results)
        none = sum(result.none_provenance_exclusions for result in results)
        unsupported = sum(result.unsupported_provenance_exclusions for result in results)
        precision_violations = sum(
            result.citation_precision_violations for result in results
        )
        shipped_claims_have_citations = all(
            all(claim.citations for claim in result.enforced_response.claims)
            for result in results
        )
        if not shipped_claims_have_citations:
            integrity_violations.append(
                _violation(
                    "uncited_shipped_claim",
                    "CitationEnforcer",
                    "A shipped claim did not carry a citation.",
                    {},
                )
            )
        if claims_dropped < 3:
            integrity_violations.append(
                _violation(
                    "drop_rule_coverage",
                    "CitationEnforcer",
                    "Citation audit did not exercise all required drop rules.",
                    {
                        "missing": missing,
                        "none": none,
                        "unsupported": unsupported,
                    },
                )
            )
        if missing <= 0 or none <= 0 or unsupported <= 0:
            integrity_violations.append(
                _violation(
                    "exclusion_reason_coverage",
                    "CitationValidator",
                    "Missing/NONE/unsupported provenance exclusions were not all exercised.",
                    {
                        "missing": missing,
                        "none": none,
                        "unsupported": unsupported,
                    },
                )
            )
        if precision_violations != 0:
            integrity_violations.append(
                _violation(
                    "citation_precision",
                    "CitationRenderer",
                    "A shipped citation exceeded provenance precision.",
                    {"precision_violations": precision_violations},
                )
            )

        return QueryV2CitationAudit(
            validation_passed=not integrity_violations,
            claims_evaluated=claims_evaluated,
            claims_cited=claims_cited,
            claims_dropped=claims_dropped,
            missing_provenance_exclusions=missing,
            none_provenance_exclusions=none,
            unsupported_provenance_exclusions=unsupported,
            citation_precision_violations=precision_violations,
            response_status_counts=dict(sorted(status_counts.items())),
            provenance_origin_counts=dict(sorted(origin_counts.items())),
            citation_type_counts=dict(sorted(citation_type_counts.items())),
            precision_level_counts=dict(sorted(precision_counts.items())),
            sample_results=tuple(sample_results),
            integrity_violations=tuple(integrity_violations),
        )


def _offramp_result(
    *,
    query_response: QueryResponseContract,
    assembly_context: AnswerAssemblyContextContract,
    status: CitationEnforcementStatus,
) -> CitationEnforcementResult:
    return CitationEnforcementResult(
        original_response=query_response,
        enforced_response=query_response,
        assembly_context=assembly_context,
        status=status,
        claims_evaluated=0,
        claims_cited=0,
        claims_dropped=0,
        missing_provenance_exclusions=0,
        none_provenance_exclusions=0,
        unsupported_provenance_exclusions=0,
        citation_precision_violations=0,
    )


def _evidence_by_ref(
    evidence_bundles: Iterable[EvidenceBundleContract],
) -> dict[str, EvidenceItemContract]:
    evidence: dict[str, EvidenceItemContract] = {}
    for bundle in evidence_bundles:
        for item in bundle.items:
            evidence[_evidence_ref(item)] = item
    return evidence


def _decision_exclusion_counts(
    decisions: Iterable[ClaimCitationDecision],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for decision in decisions:
        if decision.exclusion_reason:
            counts[decision.exclusion_reason] += 1
    return counts


def _provenance(item: EvidenceItemContract) -> dict[str, Any]:
    provenance = getattr(item, "provenance", None)
    return provenance if isinstance(provenance, dict) else {}


def _provenance_type(provenance: dict[str, Any]) -> str:
    explicit = provenance.get("provenance_type")
    if explicit not in (None, ""):
        return _enum_value(explicit).upper()
    citation_ref = provenance.get("msil_citation_ref")
    if isinstance(citation_ref, dict):
        citation_type = citation_ref.get("citation_type") or citation_ref.get(
            "provenance_type"
        )
        if citation_type not in (None, ""):
            return _enum_value(citation_type).upper()
    citation_type = provenance.get("citation_type")
    if citation_type not in (None, "") and "msil_citation_ref" in provenance:
        return _enum_value(citation_type).upper()
    return ""


def _provenance_origin(provenance: dict[str, Any]) -> str:
    if "msil_citation_ref" in provenance or "citation_ref" in provenance:
        return "msil_citation_reference"
    if _snapshot_id(provenance):
        return "msil_snapshot"
    return "msil_provenance"


def _locator_and_precision(
    provenance_type: str,
    provenance: dict[str, Any],
) -> tuple[bool, QueryV2PrecisionLevel | None]:
    if provenance_type == QueryV2CitationType.WORKBOOK_CELL.value:
        if _first(provenance, "cell_reference", "cell", "workbook_cell"):
            return True, QueryV2PrecisionLevel.CELL
        return False, None
    if provenance_type == QueryV2CitationType.PDF_PAGE.value:
        if _first(provenance, "page_number"):
            return True, QueryV2PrecisionLevel.PAGE
        if _first(provenance, "report_reference", "workbook_fingerprint", "source_ref"):
            return True, QueryV2PrecisionLevel.REF
        return False, None
    if provenance_type == QueryV2CitationType.ANNOUNCEMENT_REF.value:
        return (
            bool(_first(provenance, "announcement_id") and _snapshot_id(provenance)),
            QueryV2PrecisionLevel.REF,
        )
    if provenance_type == QueryV2CitationType.REGULATORY_REF.value:
        return (
            bool(_first(provenance, "notice_id") and _snapshot_id(provenance)),
            QueryV2PrecisionLevel.REF,
        )
    if provenance_type == QueryV2CitationType.PAYOUT_REF.value:
        return (
            bool(_first(provenance, "payout_id") and _snapshot_id(provenance)),
            QueryV2PrecisionLevel.REF,
        )
    if provenance_type == QueryV2CitationType.MARKET_DATA_REF.value:
        return (
            bool(
                _first(provenance, "series_id")
                and _first(provenance, "trade_date", "date")
                and _snapshot_id(provenance)
            ),
            QueryV2PrecisionLevel.DATE,
        )
    if provenance_type == QueryV2CitationType.FUTURES_REF.value:
        return (
            bool(
                _first(provenance, "series_id")
                and _first(provenance, "contract")
                and _first(provenance, "trade_date", "date")
                and _snapshot_id(provenance)
            ),
            QueryV2PrecisionLevel.DATE,
        )
    if provenance_type == QueryV2CitationType.SECTOR_REF.value:
        return (
            bool(_first(provenance, "sector_ref") and _snapshot_id(provenance)),
            QueryV2PrecisionLevel.REF,
        )
    if provenance_type == QueryV2CitationType.URL_SNAPSHOT.value:
        return (
            bool(_first(provenance, "url") and _snapshot_id(provenance)),
            QueryV2PrecisionLevel.REF,
        )
    if provenance_type == QueryV2CitationType.NEWS_REF.value:
        return (
            bool(
                _first(provenance, "publisher")
                and _first(provenance, "url")
                and _snapshot_id(provenance)
            ),
            QueryV2PrecisionLevel.REF,
        )
    return False, None


def _source_ref(provenance_type: str, provenance: dict[str, Any]) -> str:
    if provenance_type == QueryV2CitationType.WORKBOOK_CELL.value:
        return str(_first(provenance, "cell_reference", "cell", "workbook_cell"))
    if provenance_type == QueryV2CitationType.PDF_PAGE.value:
        page_number = _first(provenance, "page_number")
        report_ref = _first(
            provenance,
            "report_reference",
            "workbook_fingerprint",
            "source_ref",
        )
        if page_number not in (None, ""):
            prefix = str(report_ref) if report_ref not in (None, "") else "pdf"
            return f"{prefix}:page:{page_number}"
        return str(report_ref)
    if provenance_type == QueryV2CitationType.ANNOUNCEMENT_REF.value:
        return f"announcement:{_first(provenance, 'announcement_id')}"
    if provenance_type == QueryV2CitationType.REGULATORY_REF.value:
        return f"regulatory:{_first(provenance, 'notice_id')}"
    if provenance_type == QueryV2CitationType.PAYOUT_REF.value:
        return f"payout:{_first(provenance, 'payout_id')}"
    if provenance_type == QueryV2CitationType.MARKET_DATA_REF.value:
        return (
            f"market:{_first(provenance, 'series_id')}:"
            f"{_first(provenance, 'trade_date', 'date')}"
        )
    if provenance_type == QueryV2CitationType.FUTURES_REF.value:
        return (
            f"futures:{_first(provenance, 'series_id')}:"
            f"{_first(provenance, 'contract')}:"
            f"{_first(provenance, 'trade_date', 'date')}"
        )
    if provenance_type == QueryV2CitationType.SECTOR_REF.value:
        return f"sector:{_first(provenance, 'sector_ref')}"
    if provenance_type == QueryV2CitationType.URL_SNAPSHOT.value:
        return str(_first(provenance, "url"))
    if provenance_type == QueryV2CitationType.NEWS_REF.value:
        return f"news:{_first(provenance, 'publisher')}:{_first(provenance, 'url')}"
    citation_ref = provenance.get("msil_citation_ref")
    if isinstance(citation_ref, dict) and citation_ref.get("source_ref"):
        return str(citation_ref["source_ref"])
    return str(_first(provenance, "source_ref", "citation_ref") or "unknown_source")


def _rendered_text(
    provenance_type: str,
    provenance: dict[str, Any],
    source_ref: str,
) -> str:
    if provenance_type == QueryV2CitationType.PDF_PAGE.value:
        page_number = _first(provenance, "page_number")
        if page_number not in (None, ""):
            return f"Annual report page {page_number}"
        return f"Annual report reference {source_ref}"
    if provenance_type == QueryV2CitationType.WORKBOOK_CELL.value:
        return f"Workbook cell {source_ref}"
    if provenance_type in {
        QueryV2CitationType.MARKET_DATA_REF.value,
        QueryV2CitationType.FUTURES_REF.value,
    }:
        return source_ref
    snapshot_id = _snapshot_id(provenance)
    if snapshot_id:
        return f"{source_ref} (snapshot {snapshot_id})"
    return source_ref


def _snapshot_id(provenance: dict[str, Any]) -> str | None:
    value = provenance.get("snapshot_id")
    if value not in (None, ""):
        return str(value)
    snapshot_ref = provenance.get("snapshot_ref")
    if isinstance(snapshot_ref, dict):
        nested = snapshot_ref.get("snapshot_id")
        return str(nested) if nested not in (None, "") else None
    if snapshot_ref not in (None, ""):
        return str(snapshot_ref)
    return None


def _first(provenance: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = provenance.get(key)
        if value not in (None, "", (), []):
            return _enum_value(value)
    citation_ref = provenance.get("msil_citation_ref")
    if isinstance(citation_ref, dict):
        for key in keys:
            value = citation_ref.get(key)
            if value not in (None, "", (), []):
                return _enum_value(value)
    return None


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _evidence_ref(item: EvidenceItemContract) -> str:
    return str(getattr(item, "evidence_ref", "unknown_evidence"))


def _entity_ref(item: EvidenceItemContract) -> str:
    return str(getattr(item, "entity_ref", "unknown_entity"))


def _answer_text(claims: list[QueryV2ClaimContract]) -> str:
    return " ".join(claim.statement for claim in claims)


def _citation_id(evidence_ref: str, source_ref: str) -> str:
    digest = hashlib.sha256(f"{evidence_ref}:{source_ref}".encode("utf-8")).hexdigest()
    return f"query_v2_citation_{digest[:16]}"


def _precision_rank(precision: QueryV2PrecisionLevel) -> int:
    ranks = {
        QueryV2PrecisionLevel.REF: 0,
        QueryV2PrecisionLevel.DATE: 1,
        QueryV2PrecisionLevel.PAGE: 2,
        QueryV2PrecisionLevel.CELL: 3,
    }
    return ranks[precision]


def _sample_payload(result: CitationEnforcementResult) -> dict[str, Any]:
    return {
        "response_id": result.original_response.response_id,
        "status": result.status.value,
        "query_response_status": result.enforced_response.status.value,
        "claims_evaluated": result.claims_evaluated,
        "claims_cited": result.claims_cited,
        "claims_dropped": result.claims_dropped,
        "exclusion_reasons": [
            decision.exclusion_reason
            for decision in result.decisions
            if decision.exclusion_reason
        ],
        "shipped_citations": [
            citation.model_dump(mode="json")
            for claim in result.enforced_response.claims
            for citation in claim.citations
        ],
    }


def _audit_samples() -> tuple[
    tuple[
        QueryResponseContract,
        AnswerAssemblyContextContract,
        tuple[EvidenceBundleContract, ...],
    ],
    ...,
]:
    valid_pdf = _item(
        "ev_pdf",
        {
            "provenance_type": "PDF_PAGE",
            "workbook_fingerprint": "fp_123",
            "report_reference": "lucky_2025",
            "page_number": 84,
        },
    )
    valid_report = _item(
        "ev_report",
        {
            "provenance_type": "PDF_PAGE",
            "report_reference": "lucky_2025",
        },
    )
    valid_cell = _item(
        "ev_cell",
        {
            "provenance_type": "WORKBOOK_CELL",
            "cell_reference": "Revenue!B4",
            "workbook_fingerprint": "fp_123",
        },
    )
    valid_announcement = _item(
        "ev_announcement",
        {
            "provenance_type": "ANNOUNCEMENT_REF",
            "announcement_id": "psx_1",
            "snapshot_ref": {"snapshot_id": "snap_1"},
        },
    )
    missing = EvidenceItemContract.model_construct(
        evidence_ref="ev_missing",
        content_class="narrative_claim",
        claim_or_value_or_theme_summary="Missing provenance claim.",
        authority_class="audited_issuer",
        source_type="annual_report",
        observation_time=None,
        subject_period=None,
        supersession_state=None,
        divergence_refs=(),
        entity_ref="lucky_cement",
        integrity_status=None,
    )
    none = EvidenceItemContract.model_construct(
        evidence_ref="ev_none",
        content_class="narrative_claim",
        claim_or_value_or_theme_summary="NONE provenance claim.",
        authority_class="audited_issuer",
        source_type="annual_report",
        provenance={"provenance_type": "NONE"},
        observation_time=None,
        subject_period=None,
        supersession_state=None,
        divergence_refs=(),
        entity_ref="lucky_cement",
        integrity_status=None,
    )
    unsupported = _item(
        "ev_unsupported",
        {"provenance_type": "INTERNAL_NOTE", "source_ref": "internal"},
    )
    invalid_cell = _item(
        "ev_invalid_cell",
        {
            "provenance_type": "WORKBOOK_CELL",
            "workbook_fingerprint": "fp_123",
        },
    )
    return (
        _sample("resp_valid_pdf", (valid_pdf,)),
        _sample("resp_valid_report", (valid_report,)),
        _sample("resp_valid_cell", (valid_cell,)),
        _sample("resp_valid_announcement", (valid_announcement,)),
        _sample("resp_missing", (missing,)),
        _sample("resp_none", (none,)),
        _sample("resp_unsupported", (unsupported,)),
        _sample("resp_invalid_cell", (invalid_cell,)),
    )


def _sample(
    response_id: str,
    items: tuple[EvidenceItemContract, ...],
) -> tuple[
    QueryResponseContract,
    AnswerAssemblyContextContract,
    tuple[EvidenceBundleContract, ...],
]:
    claims = tuple(_claim(item) for item in items)
    refs = tuple(_evidence_ref(item) for item in items)
    response = QueryResponseContract(
        response_id=response_id,
        query_id=f"q_{response_id}",
        status=QueryV2ResponseStatus.ANSWERED,
        answer_text=" ".join(claim.statement for claim in claims),
        claims=claims,
        overall_confidence=0.8,
    )
    context = AnswerAssemblyContextContract(
        context_id=f"context_{response_id}",
        intent_ref=f"q_{response_id}",
        ranked_evidence_refs=refs,
        authority_set=tuple(
            {
                "evidence_ref": _evidence_ref(item),
                "authority_class": getattr(item, "authority_class", "unknown"),
                "source_type": getattr(item, "source_type", "unknown"),
            }
            for item in items
        ),
        confidence_ceiling=0.8,
        insufficiency_flag=False,
    )
    bundle = EvidenceBundleContract.model_construct(
        bundle_id=f"bundle_{response_id}",
        request_ref=f"request_{response_id}",
        source_domain=QueryV2TargetDomain.MSIL,
        items=items,
        coverage_note="Citation audit sample.",
    )
    return response, context, (bundle,)


def _item(evidence_ref: str, provenance: dict[str, Any]) -> EvidenceItemContract:
    return EvidenceItemContract(
        evidence_ref=evidence_ref,
        content_class="narrative_claim",
        claim_or_value_or_theme_summary=f"Claim supported by {evidence_ref}.",
        authority_class="audited_issuer",
        source_type="annual_report",
        provenance=provenance,
        entity_ref="lucky_cement",
    )


def _claim(item: EvidenceItemContract) -> QueryV2ClaimContract:
    evidence_ref = _evidence_ref(item)
    return QueryV2ClaimContract(
        statement=str(
            getattr(
                item,
                "claim_or_value_or_theme_summary",
                f"Claim supported by {evidence_ref}.",
            )
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


_SUPPORTED_PROVENANCE_TYPES = {item.value for item in QueryV2CitationType}


__all__ = [
    "CitationEnforcementResult",
    "CitationEnforcementStatus",
    "CitationEnforcer",
    "CitationRenderer",
    "CitationValidationResult",
    "CitationValidator",
    "ClaimCitationDecision",
    "EXCLUSION_MISSING_EVIDENCE",
    "EXCLUSION_MISSING_PROVENANCE",
    "EXCLUSION_NONE_PROVENANCE",
    "EXCLUSION_PRECISION_VIOLATION",
    "EXCLUSION_UNSUPPORTED_PROVENANCE",
    "QueryV2CitationAudit",
    "QueryV2Phase5Report",
]
