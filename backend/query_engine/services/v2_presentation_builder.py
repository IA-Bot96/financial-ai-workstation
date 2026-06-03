"""Deterministic Query Engine v2 divergence and authority presentation.

Phase P6 decorates a cited QueryResponse with MSIL-authored authority display
and surfaced divergence presentation. It does not generate answers, retrieve
evidence, alter ranking, alter citations, recompute authority, or resolve
divergence.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.v2_contracts import (
    AuthorityPresentationContract,
    CitationContract,
    DivergencePresentationContract,
    DivergenceSidePresentationContract,
    EvidenceBundleContract,
    EvidenceItemContract,
    QueryResponseContract,
    QueryV2AuthorityRole,
    QueryV2ClaimContract,
    QueryV2DivergenceResolution,
    QueryV2PresentationStatus,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
)


class AuthorityPresentationResult(BaseModel):
    """Authority presentation output for one response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    presentations: tuple[AuthorityPresentationContract, ...] = Field(
        default_factory=tuple
    )
    claims_evaluated: int = Field(..., ge=0)
    claims_with_authority_displayed: int = Field(..., ge=0)
    authority_recomputation_attempts: int = Field(default=0, ge=0)
    authority_override_attempts: int = Field(default=0, ge=0)
    attribution_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class DivergencePresentationResult(BaseModel):
    """Divergence presentation output for one response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    presentations: tuple[DivergencePresentationContract, ...] = Field(
        default_factory=tuple
    )
    divergence_refs_seen: int = Field(..., ge=0)
    divergences_surfaced: int = Field(..., ge=0)
    divergence_resolution_attempts: int = Field(default=0, ge=0)
    divergence_winner_selections: int = Field(default=0, ge=0)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryPresentationResult(BaseModel):
    """Decorated QueryResponse plus P6 presentation artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_response: QueryResponseContract
    decorated_response: QueryResponseContract
    authority_presentations: tuple[AuthorityPresentationContract, ...] = Field(
        default_factory=tuple
    )
    divergence_presentations: tuple[DivergencePresentationContract, ...] = Field(
        default_factory=tuple
    )
    claims_with_authority_displayed: int = Field(..., ge=0)
    authority_recomputation_attempts: int = Field(default=0, ge=0)
    authority_override_attempts: int = Field(default=0, ge=0)
    divergences_surfaced: int = Field(..., ge=0)
    divergence_resolution_attempts: int = Field(default=0, ge=0)
    divergence_winner_selections: int = Field(default=0, ge=0)
    attribution_coverage: float = Field(..., ge=0, le=100)
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    llm_used: bool = False


class QueryV2DivergenceAuthorityAudit(BaseModel):
    """Audit payload for Query v2 Phase P6 presentation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_passed: bool
    responses_decorated: int = Field(..., ge=0)
    claims_evaluated: int = Field(..., ge=0)
    claims_with_authority_displayed: int = Field(..., ge=0)
    authority_recomputation_attempts: int = Field(..., ge=0)
    authority_override_attempts: int = Field(..., ge=0)
    divergences_surfaced: int = Field(..., ge=0)
    divergence_resolution_attempts: int = Field(..., ge=0)
    divergence_winner_selections: int = Field(..., ge=0)
    attribution_coverage_percent: float = Field(..., ge=0, le=100)
    authority_role_distribution: dict[str, int]
    divergence_status_distribution: dict[str, int]
    divergence_resolution_distribution: dict[str, int]
    sample_results: tuple[dict[str, Any], ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    llm_used: bool = False


class QueryV2Phase6Report(BaseModel):
    """Implementation report for Query v2 Phase P6."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    scope: str
    builder: str
    services: tuple[str, ...]
    audit_path: str
    validation_passed: bool
    claims_with_authority_displayed: int = Field(..., ge=0)
    authority_recomputation_attempts: int = Field(..., ge=0)
    authority_override_attempts: int = Field(..., ge=0)
    divergences_surfaced: int = Field(..., ge=0)
    divergence_resolution_attempts: int = Field(..., ge=0)
    divergence_winner_selections: int = Field(..., ge=0)
    attribution_coverage_percent: float = Field(..., ge=0, le=100)
    prohibited_implementations: tuple[str, ...]
    integrity_violations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class AuthorityPresenter:
    """Build display-only AuthorityPresentation contracts."""

    def present(
        self,
        *,
        query_response: QueryResponseContract,
        evidence_bundles: Iterable[EvidenceBundleContract],
    ) -> AuthorityPresentationResult:
        """Present MSIL-assigned authority for every shipped claim."""

        evidence_by_ref = _evidence_by_ref(evidence_bundles)
        presentations: list[AuthorityPresentationContract] = []
        violations: list[dict[str, Any]] = []
        for index, claim in enumerate(query_response.claims, start=1):
            evidence_item = _first_claim_evidence(claim, evidence_by_ref)
            if evidence_item is None:
                violations.append(
                    _violation(
                        "missing_evidence_for_authority",
                        "AuthorityPresenter",
                        "Claim could not be attributed because evidence was missing.",
                        {"claim": claim.statement},
                    )
                )
                continue
            if _evidence_authority_class(evidence_item) != claim.authority_class:
                violations.append(
                    _violation(
                        "authority_class_mismatch",
                        "AuthorityPresenter",
                        "Claim authority differs from evidence authority; Query did not override it.",
                        {
                            "claim_authority": claim.authority_class,
                            "evidence_authority": _evidence_authority_class(evidence_item),
                        },
                    )
                )
                continue
            presentations.append(
                self._presentation_for_claim(
                    response_id=query_response.response_id,
                    claim=claim,
                    claim_index=index,
                    evidence_item=evidence_item,
                )
            )

        return AuthorityPresentationResult(
            presentations=tuple(presentations),
            claims_evaluated=len(query_response.claims),
            claims_with_authority_displayed=len(presentations),
            attribution_violations=tuple(violations),
        )

    @staticmethod
    def _presentation_for_claim(
        *,
        response_id: str,
        claim: QueryV2ClaimContract,
        claim_index: int,
        evidence_item: EvidenceItemContract,
    ) -> AuthorityPresentationContract:
        provenance = _provenance(evidence_item)
        claim_ref = _claim_ref(response_id, claim_index)
        return AuthorityPresentationContract(
            presentation_id=_presentation_id("authority", claim_ref),
            claim_ref=claim_ref,
            authority_class=claim.authority_class,
            claim_type=_claim_type(evidence_item, provenance),
            effective_authority=_effective_authority(claim, provenance),
            attribution_label=_attribution_label(evidence_item, provenance),
            authority_role=_authority_role(claim, evidence_item, provenance),
        )


class DivergencePresenter:
    """Build surfaced-never-resolved divergence presentations."""

    def present(
        self,
        *,
        query_response: QueryResponseContract,
        evidence_bundles: Iterable[EvidenceBundleContract],
    ) -> DivergencePresentationResult:
        """Surface divergences using response claims and MSIL-authored refs."""

        evidence_by_ref = _evidence_by_ref(evidence_bundles)
        sides_by_ref: dict[str, list[DivergenceSidePresentationContract]] = {}
        raw_refs: set[str] = set()
        violations: list[dict[str, Any]] = []
        for claim in query_response.claims:
            for evidence_ref in claim.supporting_evidence_refs:
                evidence_item = evidence_by_ref.get(evidence_ref)
                if evidence_item is None:
                    continue
                for divergence_ref in _divergence_refs(evidence_item):
                    raw_refs.add(divergence_ref)
                    citation = _citation_for_evidence(claim, evidence_ref)
                    if citation is None:
                        violations.append(
                            _violation(
                                "missing_divergence_side_citation",
                                "DivergencePresenter",
                                "Divergence side was missing citation support.",
                                {"divergence_ref": divergence_ref},
                            )
                        )
                        continue
                    sides_by_ref.setdefault(divergence_ref, []).append(
                        DivergenceSidePresentationContract(
                            claim_summary=claim.statement,
                            authority_class=claim.authority_class,
                            source_type=_evidence_source_type(evidence_item),
                            citation=citation,
                        )
                    )

        presentations: list[DivergencePresentationContract] = []
        for divergence_ref, sides in sorted(sides_by_ref.items()):
            unique_sides = _unique_sides(tuple(sides))
            if len(unique_sides) < 2:
                continue
            authority_weighting = _authority_weighting(
                divergence_ref,
                unique_sides,
                evidence_by_ref,
            )
            if _contains_winner_selection(authority_weighting):
                violations.append(
                    _violation(
                        "divergence_winner_selection",
                        "DivergencePresenter",
                        "Winner-selection metadata is not surfaced by Query.",
                        {"divergence_ref": divergence_ref},
                    )
                )
                continue
            presentations.append(
                DivergencePresentationContract(
                    presentation_id=_presentation_id("divergence", divergence_ref),
                    divergence_ref=divergence_ref,
                    entity_ref=unique_sides[0].citation.entity_ref,
                    subject=_divergence_subject(divergence_ref, evidence_by_ref),
                    sides=unique_sides,
                    authority_weighting=authority_weighting,
                    presentation_status=QueryV2PresentationStatus.SURFACED,
                    resolution=QueryV2DivergenceResolution.NOT_DETERMINED_BY_QUERY,
                    detected_by=_divergence_detected_by(divergence_ref, evidence_by_ref),
                )
            )

        resolution_attempts = sum(
            1
            for presentation in presentations
            if presentation.resolution != QueryV2DivergenceResolution.NOT_DETERMINED_BY_QUERY
        )
        winner_selections = sum(
            1
            for presentation in presentations
            if _contains_winner_selection(presentation.authority_weighting)
        )
        return DivergencePresentationResult(
            presentations=tuple(presentations),
            divergence_refs_seen=len(raw_refs),
            divergences_surfaced=len(presentations),
            divergence_resolution_attempts=resolution_attempts,
            divergence_winner_selections=winner_selections,
            integrity_violations=tuple(violations),
        )


class QueryPresentationBuilder:
    """Apply authority and divergence presentation to a cited response."""

    def __init__(
        self,
        *,
        authority_presenter: AuthorityPresenter | None = None,
        divergence_presenter: DivergencePresenter | None = None,
    ) -> None:
        self._authority_presenter = authority_presenter or AuthorityPresenter()
        self._divergence_presenter = divergence_presenter or DivergencePresenter()

    def decorate(
        self,
        *,
        query_response: QueryResponseContract,
        evidence_bundles: Iterable[EvidenceBundleContract],
    ) -> QueryPresentationResult:
        """Decorate a cited response with P6 presentation metadata."""

        bundle_tuple = tuple(evidence_bundles)
        if query_response.status not in {
            QueryV2ResponseStatus.ANSWERED,
            QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS,
        }:
            return QueryPresentationResult(
                original_response=query_response,
                decorated_response=query_response,
                claims_with_authority_displayed=0,
                divergences_surfaced=0,
                attribution_coverage=100.0,
            )

        authority = self._authority_presenter.present(
            query_response=query_response,
            evidence_bundles=bundle_tuple,
        )
        divergence = self._divergence_presenter.present(
            query_response=query_response,
            evidence_bundles=bundle_tuple,
        )
        warnings = list(query_response.warnings)
        warnings.append(
            f"authority_presentations_attached:{len(authority.presentations)}"
        )
        if divergence.presentations:
            warnings.append(f"divergences_surfaced:{len(divergence.presentations)}")
        status = (
            QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS
            if divergence.presentations
            and query_response.status == QueryV2ResponseStatus.ANSWERED
            else query_response.status
        )
        decorated = QueryResponseContract(
            response_id=query_response.response_id,
            query_id=query_response.query_id,
            status=status,
            answer_text=query_response.answer_text,
            claims=query_response.claims,
            divergences=_merge_divergences(
                query_response.divergences,
                divergence.presentations,
            ),
            warnings=tuple(dict.fromkeys(warnings)),
            overall_confidence=query_response.overall_confidence,
            numeric_integrity_status=query_response.numeric_integrity_status,
            clarification_prompt=query_response.clarification_prompt,
            generated_at=query_response.generated_at,
        )
        claims_evaluated = len(query_response.claims)
        attribution_coverage = (
            round(len(authority.presentations) / claims_evaluated * 100, 2)
            if claims_evaluated
            else 100.0
        )
        violations = [
            *authority.attribution_violations,
            *divergence.integrity_violations,
        ]
        if claims_evaluated and len(authority.presentations) != claims_evaluated:
            violations.append(
                _violation(
                    "attribution_coverage",
                    "QueryPresentationBuilder",
                    "Every shipped claim must have authority displayed.",
                    {
                        "claims": claims_evaluated,
                        "authority_presentations": len(authority.presentations),
                    },
                )
            )
        if any(
            presentation.resolution
            != QueryV2DivergenceResolution.NOT_DETERMINED_BY_QUERY
            for presentation in divergence.presentations
        ):
            violations.append(
                _violation(
                    "divergence_resolution",
                    "DivergencePresenter",
                    "Query must never resolve divergence.",
                    {},
                )
            )
        return QueryPresentationResult(
            original_response=query_response,
            decorated_response=decorated,
            authority_presentations=authority.presentations,
            divergence_presentations=divergence.presentations,
            claims_with_authority_displayed=len(authority.presentations),
            authority_recomputation_attempts=authority.authority_recomputation_attempts,
            authority_override_attempts=authority.authority_override_attempts,
            divergences_surfaced=len(divergence.presentations),
            divergence_resolution_attempts=divergence.divergence_resolution_attempts,
            divergence_winner_selections=divergence.divergence_winner_selections,
            attribution_coverage=attribution_coverage,
            integrity_violations=tuple(violations),
        )

    def write_divergence_authority_audit(
        self,
        output_path: str | Path = "output/query_v2_divergence_authority_audit.json",
    ) -> QueryV2DivergenceAuthorityAudit:
        """Run and persist the deterministic P6 presentation audit."""

        audit = self.build_divergence_authority_audit()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit

    def write_phase6_report(
        self,
        *,
        audit_path: str | Path = "output/query_v2_divergence_authority_audit.json",
        report_path: str | Path = "output/query_v2_phase6_report.json",
    ) -> QueryV2Phase6Report:
        """Write the P6 audit and implementation report."""

        audit = self.write_divergence_authority_audit(audit_path)
        report = QueryV2Phase6Report(
            phase="P6",
            scope="Divergence and authority presentation only",
            builder="QueryPresentationBuilder",
            services=("AuthorityPresenter", "DivergencePresenter"),
            audit_path=str(audit_path),
            validation_passed=audit.validation_passed,
            claims_with_authority_displayed=audit.claims_with_authority_displayed,
            authority_recomputation_attempts=audit.authority_recomputation_attempts,
            authority_override_attempts=audit.authority_override_attempts,
            divergences_surfaced=audit.divergences_surfaced,
            divergence_resolution_attempts=audit.divergence_resolution_attempts,
            divergence_winner_selections=audit.divergence_winner_selections,
            attribution_coverage_percent=audit.attribution_coverage_percent,
            prohibited_implementations=(
                "llm_logic",
                "answer_generation",
                "retrieval_changes",
                "ranking_changes",
                "citation_changes",
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

    def build_divergence_authority_audit(self) -> QueryV2DivergenceAuthorityAudit:
        """Build the deterministic P6 presentation audit."""

        samples = _audit_samples()
        results = [
            self.decorate(query_response=response, evidence_bundles=bundles)
            for response, bundles in samples
        ]
        authority_roles = Counter(
            presentation.authority_role.value
            for result in results
            for presentation in result.authority_presentations
        )
        divergence_statuses = Counter(
            presentation.presentation_status.value
            for result in results
            for presentation in result.divergence_presentations
        )
        divergence_resolutions = Counter(
            presentation.resolution.value
            for result in results
            for presentation in result.divergence_presentations
        )
        claims_evaluated = sum(len(result.original_response.claims) for result in results)
        claims_with_authority = sum(
            result.claims_with_authority_displayed for result in results
        )
        authority_recompute = sum(
            result.authority_recomputation_attempts for result in results
        )
        authority_override = sum(result.authority_override_attempts for result in results)
        divergences_surfaced = sum(result.divergences_surfaced for result in results)
        divergence_resolution_attempts = sum(
            result.divergence_resolution_attempts for result in results
        )
        divergence_winner_selections = sum(
            result.divergence_winner_selections for result in results
        )
        attribution_coverage = (
            round(claims_with_authority / claims_evaluated * 100, 2)
            if claims_evaluated
            else 100.0
        )
        violations = [
            violation
            for result in results
            for violation in result.integrity_violations
        ]
        if claims_evaluated and claims_with_authority != claims_evaluated:
            violations.append(
                _violation(
                    "audit_attribution_coverage",
                    "AuthorityPresenter",
                    "Not every audited claim was attributed.",
                    {
                        "claims_evaluated": claims_evaluated,
                        "claims_with_authority": claims_with_authority,
                    },
                )
            )
        if authority_recompute or authority_override:
            violations.append(
                _violation(
                    "authority_boundary",
                    "AuthorityPresenter",
                    "Authority was recomputed or overridden.",
                    {
                        "recompute": authority_recompute,
                        "override": authority_override,
                    },
                )
            )
        if divergences_surfaced <= 0:
            violations.append(
                _violation(
                    "divergence_coverage",
                    "DivergencePresenter",
                    "No divergence was surfaced in the audit.",
                    {},
                )
            )
        if divergence_resolution_attempts or divergence_winner_selections:
            violations.append(
                _violation(
                    "divergence_boundary",
                    "DivergencePresenter",
                    "Divergence was resolved or a winner was selected.",
                    {
                        "resolution_attempts": divergence_resolution_attempts,
                        "winner_selections": divergence_winner_selections,
                    },
                )
            )

        return QueryV2DivergenceAuthorityAudit(
            validation_passed=not violations,
            responses_decorated=len(results),
            claims_evaluated=claims_evaluated,
            claims_with_authority_displayed=claims_with_authority,
            authority_recomputation_attempts=authority_recompute,
            authority_override_attempts=authority_override,
            divergences_surfaced=divergences_surfaced,
            divergence_resolution_attempts=divergence_resolution_attempts,
            divergence_winner_selections=divergence_winner_selections,
            attribution_coverage_percent=attribution_coverage,
            authority_role_distribution=dict(sorted(authority_roles.items())),
            divergence_status_distribution=dict(sorted(divergence_statuses.items())),
            divergence_resolution_distribution=dict(
                sorted(divergence_resolutions.items())
            ),
            sample_results=tuple(_sample_payload(result) for result in results),
            integrity_violations=tuple(violations),
        )


def _evidence_by_ref(
    evidence_bundles: Iterable[EvidenceBundleContract],
) -> dict[str, EvidenceItemContract]:
    evidence: dict[str, EvidenceItemContract] = {}
    for bundle in evidence_bundles:
        for item in bundle.items:
            evidence[_evidence_ref(item)] = item
    return evidence


def _first_claim_evidence(
    claim: QueryV2ClaimContract,
    evidence_by_ref: dict[str, EvidenceItemContract],
) -> EvidenceItemContract | None:
    for evidence_ref in claim.supporting_evidence_refs:
        item = evidence_by_ref.get(evidence_ref)
        if item is not None:
            return item
    return None


def _claim_type(evidence_item: EvidenceItemContract, provenance: dict[str, Any]) -> str:
    value = _first(provenance, "claim_type")
    if value not in (None, ""):
        return str(value)
    return _evidence_content_class(evidence_item)


def _effective_authority(
    claim: QueryV2ClaimContract,
    provenance: dict[str, Any],
) -> str:
    value = _first(provenance, "effective_authority", "authority_class")
    return str(value) if value not in (None, "") else claim.authority_class


def _authority_role(
    claim: QueryV2ClaimContract,
    evidence_item: EvidenceItemContract,
    provenance: dict[str, Any],
) -> QueryV2AuthorityRole:
    value = _first(provenance, "authority_role")
    if value not in (None, ""):
        try:
            return QueryV2AuthorityRole(str(value))
        except ValueError:
            pass
    authority_text = f"{claim.authority_class} {_evidence_source_type(evidence_item)}".lower()
    claim_type = _claim_type(evidence_item, provenance).lower()
    if any(token in authority_text for token in ("analyst", "news", "market", "opinion")):
        return QueryV2AuthorityRole.OPINION
    if any(token in claim_type for token in ("forecast", "outlook", "guidance")):
        return QueryV2AuthorityRole.FORWARD_CONTEXT
    if any(token in authority_text for token in ("sector", "support")):
        return QueryV2AuthorityRole.SUPPORTING
    return QueryV2AuthorityRole.FACT


def _attribution_label(
    evidence_item: EvidenceItemContract,
    provenance: dict[str, Any],
) -> str:
    value = _first(provenance, "attribution_label")
    if value not in (None, ""):
        return str(value)
    source_type = _evidence_source_type(evidence_item).replace("_", " ")
    authority_class = _evidence_authority_class(evidence_item).replace("_", " ")
    return f"per {source_type} ({authority_class})"


def _divergence_refs(evidence_item: EvidenceItemContract) -> tuple[str, ...]:
    refs = tuple(str(ref) for ref in getattr(evidence_item, "divergence_refs", ()) if ref)
    provenance = _provenance(evidence_item)
    extra = _first(provenance, "divergence_refs")
    if isinstance(extra, list | tuple):
        refs = (*refs, *(str(ref) for ref in extra if ref))
    return tuple(dict.fromkeys(refs))


def _citation_for_evidence(
    claim: QueryV2ClaimContract,
    evidence_ref: str,
) -> CitationContract | None:
    for citation in claim.citations:
        if citation.evidence_ref == evidence_ref:
            return citation
    return claim.citations[0] if claim.citations else None


def _unique_sides(
    sides: tuple[DivergenceSidePresentationContract, ...],
) -> tuple[DivergenceSidePresentationContract, ...]:
    deduped: list[DivergenceSidePresentationContract] = []
    seen: set[tuple[str, str, str]] = set()
    for side in sides:
        key = (side.claim_summary, side.authority_class, side.citation.evidence_ref)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(side)
    return tuple(deduped)


def _authority_weighting(
    divergence_ref: str,
    sides: tuple[DivergenceSidePresentationContract, ...],
    evidence_by_ref: dict[str, EvidenceItemContract],
) -> dict[str, Any]:
    for item in evidence_by_ref.values():
        if divergence_ref not in _divergence_refs(item):
            continue
        weighting = _first(_provenance(item), "authority_weighting")
        if isinstance(weighting, dict) and not _contains_winner_selection(weighting):
            return dict(weighting)
    return {
        "weighting": "msil_authority_metadata",
        "authority_classes": tuple(side.authority_class for side in sides),
        "query_selects_winner": False,
    }


def _divergence_subject(
    divergence_ref: str,
    evidence_by_ref: dict[str, EvidenceItemContract],
) -> str:
    for item in evidence_by_ref.values():
        if divergence_ref in _divergence_refs(item):
            value = _first(_provenance(item), "divergence_subject", "subject")
            if value not in (None, ""):
                return str(value)
    return divergence_ref


def _divergence_detected_by(
    divergence_ref: str,
    evidence_by_ref: dict[str, EvidenceItemContract],
) -> str:
    for item in evidence_by_ref.values():
        if divergence_ref in _divergence_refs(item):
            value = _first(_provenance(item), "detected_by")
            if value not in (None, ""):
                return str(value)
    return "msil"


def _contains_winner_selection(weighting: dict[str, Any]) -> bool:
    winner_keys = {
        "winner",
        "winning_side",
        "selected_side",
        "selected_winner",
        "query_winner",
    }
    return any(key in weighting for key in winner_keys)


def _merge_divergences(
    existing: tuple[DivergencePresentationContract, ...],
    added: tuple[DivergencePresentationContract, ...],
) -> tuple[DivergencePresentationContract, ...]:
    merged: list[DivergencePresentationContract] = []
    seen: set[str] = set()
    for presentation in (*existing, *added):
        if presentation.divergence_ref in seen:
            continue
        seen.add(presentation.divergence_ref)
        merged.append(presentation)
    return tuple(merged)


def _provenance(item: EvidenceItemContract) -> dict[str, Any]:
    provenance = getattr(item, "provenance", None)
    return provenance if isinstance(provenance, dict) else {}


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", (), []):
            return _enum_value(value)
    authority = payload.get("authority")
    if isinstance(authority, dict):
        for key in keys:
            value = authority.get(key)
            if value not in (None, "", (), []):
                return _enum_value(value)
    return None


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _evidence_ref(item: EvidenceItemContract) -> str:
    return str(getattr(item, "evidence_ref", "unknown_evidence"))


def _evidence_content_class(item: EvidenceItemContract) -> str:
    return str(getattr(item, "content_class", "unknown_claim"))


def _evidence_authority_class(item: EvidenceItemContract) -> str:
    return str(getattr(item, "authority_class", "unknown_authority"))


def _evidence_source_type(item: EvidenceItemContract) -> str:
    return str(getattr(item, "source_type", "unknown_source"))


def _claim_ref(response_id: str, claim_index: int) -> str:
    return f"{response_id}:claim:{claim_index}"


def _presentation_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(f"{prefix}:{value}".encode("utf-8")).hexdigest()
    return f"query_v2_{prefix}_{digest[:16]}"


def _sample_payload(result: QueryPresentationResult) -> dict[str, Any]:
    return {
        "response_id": result.original_response.response_id,
        "claims": len(result.original_response.claims),
        "claims_with_authority_displayed": result.claims_with_authority_displayed,
        "divergences_surfaced": result.divergences_surfaced,
        "decorated_status": result.decorated_response.status.value,
        "authority_roles": [
            presentation.authority_role.value
            for presentation in result.authority_presentations
        ],
        "divergence_resolutions": [
            presentation.resolution.value
            for presentation in result.divergence_presentations
        ],
        "warnings": result.decorated_response.warnings,
    }


def _audit_samples() -> tuple[
    tuple[QueryResponseContract, tuple[EvidenceBundleContract, ...]],
    ...,
]:
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
            "attribution_label": "per the audited report",
            "divergence_subject": "revenue outlook",
            "authority_weighting": {"weighting": "msil_authority_metadata"},
        },
        divergence_refs=("div_revenue_outlook",),
    )
    analyst = _item(
        "ev_analyst",
        "Analyst says demand weakened.",
        "independent_opinion",
        "analysis_reports",
        {
            "provenance_type": "URL_SNAPSHOT",
            "url": "https://example.test/report",
            "snapshot_ref": {"snapshot_id": "snap_analyst"},
            "claim_type": "forward_context",
            "effective_authority": "independent_opinion",
            "authority_role": "opinion",
            "attribution_label": "per the analyst report",
            "divergence_subject": "revenue outlook",
            "authority_weighting": {"weighting": "msil_authority_metadata"},
        },
        divergence_refs=("div_revenue_outlook",),
    )
    metric = _item(
        "ev_metric",
        "Revenue passed integrity checks.",
        "fve_validated",
        "forecast_validation_engine",
        {
            "provenance_type": "WORKBOOK_CELL",
            "cell": "Revenue!B4",
            "claim_type": "numeric_validation",
            "effective_authority": "fve_validated",
            "authority_role": "fact",
            "attribution_label": "per FVE validation",
        },
    )
    return (
        _sample("resp_divergence", (issuer, analyst)),
        _sample("resp_metric", (metric,)),
    )


def _sample(
    response_id: str,
    items: tuple[EvidenceItemContract, ...],
) -> tuple[QueryResponseContract, tuple[EvidenceBundleContract, ...]]:
    claims = tuple(_claim(item) for item in items)
    response = QueryResponseContract(
        response_id=response_id,
        query_id=f"q_{response_id}",
        status=QueryV2ResponseStatus.ANSWERED,
        answer_text=" ".join(claim.statement for claim in claims),
        claims=claims,
        overall_confidence=0.75,
    )
    bundle = EvidenceBundleContract(
        bundle_id=f"bundle_{response_id}",
        request_ref=f"request_{response_id}",
        source_domain=QueryV2TargetDomain.MSIL,
        items=items,
        coverage_note="Presentation audit sample.",
    )
    return response, (bundle,)


def _item(
    evidence_ref: str,
    summary: str,
    authority_class: str,
    source_type: str,
    provenance: dict[str, Any],
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
    evidence_ref = _evidence_ref(item)
    citation_type = "WORKBOOK_CELL" if item.provenance["provenance_type"] == "WORKBOOK_CELL" else "PDF_PAGE"
    source_ref = item.provenance.get("cell") or item.provenance.get("url") or "page:84"
    return QueryV2ClaimContract(
        statement=item.claim_or_value_or_theme_summary,
        supporting_evidence_refs=(evidence_ref,),
        authority_class=item.authority_class,
        citations=(
            CitationContract(
                citation_id=f"cit_{evidence_ref}",
                citation_type=citation_type,
                source_ref=str(source_ref),
                entity_ref=item.entity_ref,
                evidence_ref=evidence_ref,
                rendered_text=str(source_ref),
                precision_level="cell" if citation_type == "WORKBOOK_CELL" else "page",
            ),
        ),
        confidence=0.75,
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


__all__ = [
    "AuthorityPresentationResult",
    "AuthorityPresenter",
    "DivergencePresentationResult",
    "DivergencePresenter",
    "QueryPresentationBuilder",
    "QueryPresentationResult",
    "QueryV2DivergenceAuthorityAudit",
    "QueryV2Phase6Report",
]
