"""QAE-side consumption adapter for MSIL evidence.

MSIL owns entity resolution, authority assignment, provenance, corroboration, and
divergence detection. This adapter only consumes those outputs and maps
eligible narrative evidence into the existing QAE signal/theme flow.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from multi_source_intelligence.models import (
    ContentClass as MSILContentClass,
    CorroborationGroup,
    CorroborationResult,
    Divergence as MSILDivergence,
    DivergenceResult,
    DivergenceType as MSILDivergenceType,
    IntelligenceSignal,
    ProvenanceType as MSILProvenanceType,
    ReviewStatus,
    SourceType as MSILSourceType,
)
from qualitative_analysis_engine.models import (
    AnnouncementRefProvenance,
    AuthorityClass,
    ClaimType,
    DivergenceReference,
    DivergenceType,
    EntityScope,
    Horizon,
    MappingMethod,
    MarketDataRefProvenance,
    PDFPageProvenance,
    QualitativeSignal,
    RegulatoryRefProvenance,
    RoutingBasis,
    SectorRefProvenance,
    SourceType,
    Specificity,
    TimeBasis,
    URLSnapshotProvenance,
)

from .mapping_confidence import MappingConfidenceComposer
from .section_router import SourceSectionRouter
from .taxonomy_loader import TaxonomyDefinition, TaxonomyLoader
from .text_normalization import normalize_text
from .theme_assembly import ThemeAssemblyResult
from .theme_canonicalizer import ThemeCanonicalizer


AUTHORITY_MATRIX_VERSION = "1.0.0"
SIGNAL_VERSION = "1.0.0"


class QAEMSILEvidenceReference(BaseModel):
    """MSIL non-theme evidence retained as QAE reference/context only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_ref: str = Field(..., min_length=1)
    entity_ref: str = Field(..., min_length=1)
    content_class: str = Field(..., min_length=1)
    reference_role: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    authority_class: str = Field(..., min_length=1)
    claim_type: str = Field(..., min_length=1)
    provenance_type: str = Field(..., min_length=1)
    creation_eligible: bool
    reason: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class QAEMSILCorroborationApplication(BaseModel):
    """MSIL corroboration group consumed by QAE after theme creation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    corroboration_group_id: str = Field(..., min_length=1)
    member_signal_refs: tuple[str, ...] = Field(..., min_length=2)
    independent_origin_count: int = Field(..., ge=2)
    authority_classes_present: tuple[str, ...] = Field(..., min_length=2)
    strength: float = Field(..., ge=0, le=1)
    applied_theme_refs: tuple[str, ...] = Field(default_factory=tuple)


class QAEMSILConsumptionResult(BaseModel):
    """Result of consuming MSIL records for QAE."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signals_consumed: int = Field(..., ge=0)
    narrative_claims_consumed: int = Field(..., ge=0)
    qae_signals: tuple[QualitativeSignal, ...] = Field(default_factory=tuple)
    numeric_claim_references: tuple[QAEMSILEvidenceReference, ...] = Field(
        default_factory=tuple
    )
    corporate_event_references: tuple[QAEMSILEvidenceReference, ...] = Field(
        default_factory=tuple
    )
    market_observation_references: tuple[QAEMSILEvidenceReference, ...] = Field(
        default_factory=tuple
    )
    unsupported_references: tuple[QAEMSILEvidenceReference, ...] = Field(
        default_factory=tuple
    )
    corroboration_references: tuple[QAEMSILCorroborationApplication, ...] = Field(
        default_factory=tuple
    )
    divergence_references: tuple[DivergenceReference, ...] = Field(default_factory=tuple)
    authority_metadata_attached: int = Field(..., ge=0)
    provenance_metadata_attached: int = Field(..., ge=0)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    ownership_boundaries: dict[str, bool] = Field(default_factory=dict)


class QAEMSILThemeApplicationResult(BaseModel):
    """Theme assembly output after applying MSIL-owned evidence references."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assembly_result: ThemeAssemblyResult
    corroboration_references_applied: int = Field(..., ge=0)
    divergence_references_applied: int = Field(..., ge=0)
    themes_updated: int = Field(..., ge=0)
    confidence_adjustments: dict[str, dict[str, float]] = Field(default_factory=dict)
    materiality_adjustments: dict[str, dict[str, float]] = Field(default_factory=dict)


class QAEMSILEvidenceAdapter:
    """Consume MSIL evidence for QAE without recomputing MSIL-owned concepts."""

    _OWNERSHIP_BOUNDARIES = {
        "qae_resolves_entities": False,
        "qae_assigns_authority": False,
        "qae_recomputes_corroboration": False,
        "qae_recomputes_divergence": False,
        "qae_resolves_divergence": False,
        "qae_changes_taxonomy": False,
        "qae_changes_creation_gate": False,
        "qae_creates_themes_from_numeric_claims": False,
        "qae_creates_themes_from_corporate_events": False,
        "qae_creates_themes_from_market_observations": False,
    }

    def __init__(
        self,
        *,
        taxonomy: TaxonomyDefinition | None = None,
        taxonomy_loader: TaxonomyLoader | None = None,
        canonicalizer: ThemeCanonicalizer | None = None,
        section_router: SourceSectionRouter | None = None,
        confidence_composer: MappingConfidenceComposer | None = None,
        authority_matrix_version: str = AUTHORITY_MATRIX_VERSION,
        signal_version: str = SIGNAL_VERSION,
    ) -> None:
        self._taxonomy = taxonomy or (taxonomy_loader or TaxonomyLoader()).load()
        self._section_router = section_router or SourceSectionRouter()
        self._confidence_composer = confidence_composer or MappingConfidenceComposer()
        self._canonicalizer = canonicalizer or ThemeCanonicalizer(
            self._taxonomy,
            section_router=self._section_router,
            confidence_composer=self._confidence_composer,
        )
        self._authority_matrix_version = authority_matrix_version
        self._signal_version = signal_version

    def adapt(
        self,
        signals: Iterable[IntelligenceSignal],
        *,
        corroboration_result: CorroborationResult | None = None,
        divergence_result: DivergenceResult | None = None,
    ) -> QAEMSILConsumptionResult:
        """Map MSIL signals into QAE signals and reference-only evidence."""

        signal_list = tuple(signals)
        qae_signals: list[QualitativeSignal] = []
        numeric_refs: list[QAEMSILEvidenceReference] = []
        event_refs: list[QAEMSILEvidenceReference] = []
        market_refs: list[QAEMSILEvidenceReference] = []
        unsupported_refs: list[QAEMSILEvidenceReference] = []
        warnings: list[str] = []

        for signal in signal_list:
            content_class = signal.content.content_class
            try:
                if content_class == MSILContentClass.NARRATIVE_CLAIM:
                    qae_signals.append(self._adapt_narrative_signal(signal))
                elif content_class == MSILContentClass.NUMERIC_CLAIM:
                    numeric_refs.append(
                        _reference(
                            signal,
                            reference_role="numeric_context_only",
                            reason="numeric_claims_may_reference_themes_but_never_create_them",
                        )
                    )
                elif content_class == MSILContentClass.CORPORATE_EVENT:
                    event_refs.append(
                        _reference(
                            signal,
                            reference_role="corporate_event_anchor_only",
                            reason="corporate_events_are_context_anchors_not_theme_sources",
                        )
                    )
                elif content_class == MSILContentClass.MARKET_OBSERVATION:
                    market_refs.append(
                        _reference(
                            signal,
                            reference_role="market_divergence_context_only",
                            reason="market_observations_reach_qae_only_through_divergence",
                        )
                    )
                else:
                    unsupported_refs.append(
                        _reference(
                            signal,
                            reference_role="unsupported_content_class",
                            reason="content_class_not_supported_by_qae_msil_adapter",
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - surfaced as warning.
                unsupported_refs.append(
                    _reference(
                        signal,
                        reference_role="adapter_failure",
                        reason=str(exc),
                    )
                )
                warnings.append(
                    f"MSIL signal {signal.signal_id or '<missing>'} could not be consumed by QAE: {exc}"
                )

        signal_by_ref = {signal.signal_id: signal for signal in qae_signals}
        corroboration_refs = tuple(
            self._corroboration_application(group, signal_by_ref)
            for group in (corroboration_result.groups if corroboration_result else ())
        )
        divergence_refs = tuple(
            divergence_ref
            for divergence in (divergence_result.divergences if divergence_result else ())
            for divergence_ref in self._divergence_references(divergence, signal_by_ref)
        )

        authority_attached = len(qae_signals) + len(numeric_refs) + len(event_refs) + len(market_refs)
        provenance_attached = authority_attached
        return QAEMSILConsumptionResult(
            signals_consumed=len(signal_list),
            narrative_claims_consumed=len(qae_signals),
            qae_signals=tuple(qae_signals),
            numeric_claim_references=tuple(numeric_refs),
            corporate_event_references=tuple(event_refs),
            market_observation_references=tuple(market_refs),
            unsupported_references=tuple(unsupported_refs),
            corroboration_references=corroboration_refs,
            divergence_references=divergence_refs,
            authority_metadata_attached=authority_attached,
            provenance_metadata_attached=provenance_attached,
            warnings=tuple(warnings),
            ownership_boundaries=dict(self._OWNERSHIP_BOUNDARIES),
        )

    def apply_msil_references(
        self,
        *,
        assembly_result: ThemeAssemblyResult,
        consumption_result: QAEMSILConsumptionResult,
    ) -> QAEMSILThemeApplicationResult:
        """Apply MSIL-owned corroboration/divergence to assembled QAE themes."""

        corroboration_by_theme = _corroboration_by_theme(
            consumption_result.corroboration_references,
            assembly_result,
        )
        divergence_by_theme = _divergence_by_theme(
            consumption_result.divergence_references,
            assembly_result,
        )
        updated_themes = []
        confidence_adjustments: dict[str, dict[str, float]] = {}
        materiality_adjustments: dict[str, dict[str, float]] = {}
        corroboration_applied = 0
        divergence_applied = 0

        for theme in assembly_result.themes:
            theme_ref = theme.theme_reference.theme_ref
            cor_refs = corroboration_by_theme.get(theme_ref, ())
            div_refs = divergence_by_theme.get(theme_ref, ())
            if not cor_refs and not div_refs:
                updated_themes.append(theme)
                continue

            corroboration_lift = min(0.15, sum(ref.strength * 0.08 for ref in cor_refs))
            divergence_penalty = min(0.30, sum(ref.confidence_impact for ref in div_refs))
            materiality_lift = min(
                0.30,
                sum(ref.strength * 0.08 for ref in cor_refs)
                + sum(ref.materiality_impact for ref in div_refs),
            )
            ceiling = _authority_ceiling(theme)
            new_confidence = round(
                max(0.0, min(ceiling, theme.theme_confidence + corroboration_lift - divergence_penalty)),
                6,
            )
            new_materiality = round(min(1.0, theme.materiality + materiality_lift), 6)
            divergence_refs = _dedupe_divergences((*theme.divergence_refs, *div_refs))
            evidence = theme.evidence.model_copy(
                update={
                    "divergence_refs": tuple(
                        divergence.divergence_id for divergence in divergence_refs
                    ),
                    "independent_origins": tuple(
                        sorted(
                            set(theme.evidence.independent_origins)
                            | {f"msil:{ref.corroboration_group_id}" for ref in cor_refs}
                        )
                    ),
                }
            )
            updated_theme = theme.model_copy(
                update={
                    "theme_confidence": new_confidence,
                    "materiality": new_materiality,
                    "divergence_refs": divergence_refs,
                    "evidence": evidence,
                }
            )
            updated_themes.append(updated_theme)
            confidence_adjustments[theme_ref] = {
                "before": theme.theme_confidence,
                "after": new_confidence,
                "corroboration_lift": round(corroboration_lift, 6),
                "divergence_penalty": round(divergence_penalty, 6),
                "authority_ceiling": ceiling,
            }
            materiality_adjustments[theme_ref] = {
                "before": theme.materiality,
                "after": new_materiality,
                "msil_materiality_lift": round(materiality_lift, 6),
            }
            corroboration_applied += len(cor_refs)
            divergence_applied += len(div_refs)

        updated_divergences = _dedupe_divergences(
            (*assembly_result.divergences, *consumption_result.divergence_references)
        )
        updated_assembly = assembly_result.model_copy(
            update={
                "themes": tuple(updated_themes),
                "divergences": updated_divergences,
                "confidence_distribution": _distribution(
                    [theme.theme_confidence for theme in updated_themes]
                ),
                "materiality_distribution": _distribution(
                    [theme.materiality for theme in updated_themes]
                ),
            }
        )
        return QAEMSILThemeApplicationResult(
            assembly_result=updated_assembly,
            corroboration_references_applied=corroboration_applied,
            divergence_references_applied=divergence_applied,
            themes_updated=len(confidence_adjustments),
            confidence_adjustments=confidence_adjustments,
            materiality_adjustments=materiality_adjustments,
        )

    def audit(
        self,
        consumption_result: QAEMSILConsumptionResult,
        *,
        application_result: QAEMSILThemeApplicationResult | None = None,
    ) -> dict[str, Any]:
        """Build the QAE MSIL integration audit payload."""

        qae_signals = consumption_result.qae_signals
        references = (
            *consumption_result.numeric_claim_references,
            *consumption_result.corporate_event_references,
            *consumption_result.market_observation_references,
        )
        return {
            "audit_name": "qae_msil_integration_audit",
            "integration_phase": "MSIL Phase 8B: QAE Integration",
            "signals_consumed": consumption_result.signals_consumed,
            "narrative_claims_consumed": consumption_result.narrative_claims_consumed,
            "qae_signals_generated": len(qae_signals),
            "numeric_claims_referenced": len(consumption_result.numeric_claim_references),
            "corporate_events_referenced": len(consumption_result.corporate_event_references),
            "market_observations_referenced": len(consumption_result.market_observation_references),
            "unsupported_references": len(consumption_result.unsupported_references),
            "authority_metadata_attached": consumption_result.authority_metadata_attached,
            "provenance_metadata_attached": consumption_result.provenance_metadata_attached,
            "corroboration_references_consumed": len(consumption_result.corroboration_references),
            "corroboration_references_applied": application_result.corroboration_references_applied
            if application_result
            else 0,
            "divergence_references_consumed": len(consumption_result.divergence_references),
            "divergence_references_applied": application_result.divergence_references_applied
            if application_result
            else 0,
            "content_class_boundary": {
                "narrative_claim_theme_source": True,
                "numeric_claim_theme_source": False,
                "corporate_event_theme_source": False,
                "market_observation_theme_source": False,
            },
            "source_type_distribution": dict(
                Counter(signal.source_type.value for signal in qae_signals)
            ),
            "authority_class_distribution": dict(
                Counter(
                    signal.source_metadata.get("msil_authority_class", signal.authority_class.value)
                    for signal in qae_signals
                )
            ),
            "claim_type_distribution": dict(
                Counter(signal.claim_type.value for signal in qae_signals)
            ),
            "provenance_type_distribution": dict(
                Counter(signal.provenance.provenance_type.value for signal in qae_signals)
            ),
            "reference_role_distribution": dict(
                Counter(reference.reference_role for reference in references)
            ),
            "theme_application": application_result.model_dump(mode="json", exclude={"assembly_result"})
            if application_result
            else None,
            "ownership_boundary_validation": consumption_result.ownership_boundaries,
            "warnings": list(consumption_result.warnings),
        }

    def write_audit(
        self,
        output_path: str | Path,
        consumption_result: QAEMSILConsumptionResult,
        *,
        application_result: QAEMSILThemeApplicationResult | None = None,
    ) -> dict[str, Any]:
        """Write the integration audit to disk."""

        audit = self.audit(consumption_result, application_result=application_result)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        return audit

    def _adapt_narrative_signal(self, signal: IntelligenceSignal) -> QualitativeSignal:
        if signal.entity_resolution.review_status != ReviewStatus.RESOLVED:
            raise ValueError("QAE cannot consume unresolved MSIL entity signals.")
        source_type = _qae_source_type(signal)
        if source_type == SourceType.DAILY_MARKET_SUMMARY:
            raise ValueError("market source narrative may not create QAE themes.")

        claim = signal.content.claim_text or signal.content.normalized_claim_text or ""
        if not claim.strip():
            raise ValueError("narrative_claim signal is missing claim text.")
        payload = dict(signal.content.payload)
        area = str(
            payload.get("area")
            or payload.get("title")
            or payload.get("source_section")
            or signal.content.metric_ref
            or claim
        )
        source_section = payload.get("source_section") or getattr(
            signal.provenance,
            "source_section",
            None,
        )
        extraction_confidence = _bounded_float(
            payload.get("confidence"),
            default=min(signal.metadata.trust_prior, signal.classification.mapping_confidence),
        )
        section_route = self._section_router.route(source_section)
        section_confidence = section_route.route_confidence if section_route.recognized else None
        canonicalization = self._canonicalizer.canonicalize(
            area,
            takeaway=claim,
            source_section=source_section,
            extraction_confidence=extraction_confidence,
            section_confidence=section_confidence,
        )
        routing_basis = (
            canonicalization.routing_basis
            if source_type == SourceType.ANNUAL_REPORT
            else RoutingBasis.ADAPTER_SIGNAL
        )
        signal_confidence = self._confidence_composer.compose(
            mapping_confidence=canonicalization.mapping_confidence,
            extraction_confidence=extraction_confidence,
            section_confidence=section_confidence,
            section_theme_conflict=False,
        )

        qae_authority = _qae_authority_class(signal)
        return QualitativeSignal(
            signal_id=signal.signal_id or "",
            signal_version=self._signal_version,
            entity_ref=signal.entity_ref,
            entity_scope=_qae_entity_scope(signal),
            source_type=source_type,
            taxonomy_version=self._taxonomy.taxonomy_version,
            authority_matrix_version=self._authority_matrix_version,
            claim=claim.strip(),
            normalized_claim_text=signal.content.normalized_claim_text
            or normalize_text(claim),
            raw_excerpt=claim.strip(),
            is_quantified=_has_quantitative_evidence(claim),
            specificity=_derive_specificity(claim),
            category_ref=canonicalization.category_ref,
            theme_ref=canonicalization.theme_ref,
            subtheme_ref=None,
            mapping_method=canonicalization.mapping_method,
            mapping_confidence=canonicalization.mapping_confidence,
            routing_basis=routing_basis,
            unmapped=canonicalization.unmapped,
            claim_type=_qae_claim_type(signal),
            authority_class=qae_authority,
            source_independent_of_issuer=signal.metadata.source_independent_of_issuer,
            verified=signal.metadata.verified,
            trust_prior=signal.metadata.trust_prior,
            source_lineage=signal.metadata.source_lineage,
            derived_from=tuple(payload.get("derived_from") or ()),
            observation_time=_qae_observation_time(signal),
            source_report_year=_optional_int(payload.get("source_report_year")),
            subject_period=_qae_subject_period(signal),
            value_year=_optional_int(payload.get("value_year")),
            time_basis=_qae_time_basis(signal),
            horizon=_qae_horizon(signal),
            supersedes=(signal.supersedes,) if signal.supersedes else (),
            superseded_by=(signal.superseded_by,) if signal.superseded_by else (),
            provenance=_qae_provenance(signal),
            page_number=getattr(signal.provenance, "page_number", None),
            source_section=source_section,
            snapshot_ref=_snapshot_id(signal),
            retrieved_at=getattr(signal.provenance, "retrieved_at", None),
            extraction_confidence=extraction_confidence,
            structure_confidence=section_confidence,
            signal_confidence=signal_confidence,
            review_status=payload.get("review_status"),
            source_metadata={
                "msil_signal_id": signal.signal_id,
                "msil_content_class": signal.content.content_class.value,
                "msil_source_type": signal.classification.source_type.value,
                "msil_authority_class": signal.classification.authority_class.value,
                "msil_claim_type": signal.classification.claim_type.value,
                "msil_creation_eligible": signal.classification.creation_eligible,
                "msil_mapping_confidence": signal.classification.mapping_confidence,
                "msil_authority_confidence": signal.classification.authority_confidence,
                "msil_provenance": signal.provenance.model_dump(mode="json"),
                "msil_version_pins": signal.version_pins.model_dump(mode="json"),
                "authority_class_compatibility_mapping": (
                    signal.classification.authority_class.value
                    if signal.classification.authority_class.value == qae_authority.value
                    else f"{signal.classification.authority_class.value}->{qae_authority.value}"
                ),
                "source_payload": payload,
                "area": area,
                "canonicalization_evidence": list(canonicalization.evidence),
                "matched_text": canonicalization.matched_text,
                "secondary_categories": list(canonicalization.secondary_categories),
                "section_theme_conflict": canonicalization.section_theme_conflict,
            },
            creation_eligible=(
                signal.classification.creation_eligible
                and not canonicalization.unmapped
                and source_type != SourceType.DAILY_MARKET_SUMMARY
            ),
        )

    def _corroboration_application(
        self,
        group: CorroborationGroup,
        signal_by_ref: Mapping[str, QualitativeSignal],
    ) -> QAEMSILCorroborationApplication:
        applied_theme_refs = tuple(
            sorted(
                {
                    signal_by_ref[signal_ref].theme_ref
                    for signal_ref in group.member_signal_refs
                    if signal_ref in signal_by_ref
                    and signal_by_ref[signal_ref].theme_ref is not None
                }
            )
        )
        return QAEMSILCorroborationApplication(
            corroboration_group_id=group.corroboration_group_id or "",
            member_signal_refs=group.member_signal_refs,
            independent_origin_count=group.independent_origin_count,
            authority_classes_present=tuple(
                authority.value for authority in group.authority_classes_present
            ),
            strength=group.strength,
            applied_theme_refs=applied_theme_refs,
        )

    def _divergence_references(
        self,
        divergence: MSILDivergence,
        signal_by_ref: Mapping[str, QualitativeSignal],
    ) -> tuple[DivergenceReference, ...]:
        if divergence.divergence_type != MSILDivergenceType.NARRATIVE_VS_NARRATIVE:
            return ()
        side_refs = (divergence.side_a.signal_ref, divergence.side_b.signal_ref)
        qae_sides = [signal_by_ref[signal_ref] for signal_ref in side_refs if signal_ref in signal_by_ref]
        if not qae_sides:
            return ()
        anchor = next((signal for signal in qae_sides if signal.theme_ref), None)
        if anchor is None:
            return ()
        confidence_impact, materiality_impact = _divergence_impacts(divergence)
        return (
            DivergenceReference(
                divergence_id=divergence.divergence_id or "",
                divergence_type=_qae_divergence_type(divergence),
                theme_ref=anchor.theme_ref or "unknown_theme",
                category_ref=anchor.category_ref or "unknown_category",
                signal_ids=side_refs,
                side_a_signal_id=divergence.side_a.signal_ref,
                side_b_signal_id=divergence.side_b.signal_ref,
                side_a_authority_class=_qae_authority_from_value(
                    divergence.side_a.authority_class.value
                ),
                side_b_authority_class=_qae_authority_from_value(
                    divergence.side_b.authority_class.value
                ),
                summary=(
                    "MSIL surfaced narrative divergence; QAE displays both sides "
                    "without resolving."
                ),
                confidence_impact=confidence_impact,
                materiality_impact=materiality_impact,
                auto_resolved=False,
            ),
        )


def _reference(
    signal: IntelligenceSignal,
    *,
    reference_role: str,
    reason: str,
) -> QAEMSILEvidenceReference:
    return QAEMSILEvidenceReference(
        signal_ref=signal.signal_id or "",
        entity_ref=signal.entity_ref,
        content_class=signal.content.content_class.value,
        reference_role=reference_role,
        source_type=signal.classification.source_type.value,
        authority_class=signal.classification.authority_class.value,
        claim_type=signal.classification.claim_type.value,
        provenance_type=signal.provenance.provenance_type.value,
        creation_eligible=signal.classification.creation_eligible,
        reason=reason,
        payload={
            "content": signal.content.model_dump(mode="json"),
            "metadata": signal.metadata.model_dump(mode="json"),
            "provenance": signal.provenance.model_dump(mode="json"),
        },
    )


def _qae_source_type(signal: IntelligenceSignal) -> SourceType:
    mapping = {
        MSILSourceType.ANNUAL_REPORT: SourceType.ANNUAL_REPORT,
        MSILSourceType.PSX_ANNOUNCEMENTS: SourceType.COMPANY_ANNOUNCEMENTS,
        MSILSourceType.SECP_NOTICES: SourceType.SECP_NOTICES,
        MSILSourceType.COMPANY_OVERVIEW: SourceType.COMPANY_OVERVIEW,
        MSILSourceType.ANALYSIS_REPORTS: SourceType.ANALYSIS_REPORTS,
        MSILSourceType.SECTOR_SUMMARY: SourceType.SECTOR_SUMMARY,
        MSILSourceType.MARKET_WATCH: SourceType.DAILY_MARKET_SUMMARY,
        MSILSourceType.FUTURES_MARKET_WATCH: SourceType.DAILY_MARKET_SUMMARY,
    }
    source_type = mapping.get(signal.classification.source_type)
    if source_type is None:
        raise ValueError(
            f"MSIL source_type is not supported by QAE: {signal.classification.source_type.value}"
        )
    return source_type


def _qae_authority_class(signal: IntelligenceSignal) -> AuthorityClass:
    return _qae_authority_from_value(signal.classification.authority_class.value)


def _qae_authority_from_value(value: str) -> AuthorityClass:
    mapping = {
        "regulatory_independent": AuthorityClass.REGULATORY_INDEPENDENT,
        "audited_issuer": AuthorityClass.AUDITED_ISSUER,
        "official_issuer_unaudited": AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
        "exchange_official": AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
        "independent_opinion": AuthorityClass.INDEPENDENT_OPINION,
        "sector_aggregate": AuthorityClass.SECTOR_AGGREGATE,
        "market_revealed": AuthorityClass.MARKET_REVEALED,
        "news_media": AuthorityClass.INDEPENDENT_OPINION,
    }
    authority = mapping.get(value)
    if authority is None:
        raise ValueError(f"MSIL authority_class is not supported by QAE: {value}")
    return authority


def _qae_claim_type(signal: IntelligenceSignal) -> ClaimType:
    return ClaimType(signal.classification.claim_type.value)


def _qae_entity_scope(signal: IntelligenceSignal) -> EntityScope:
    return EntityScope(signal.entity_scope.value)


def _qae_time_basis(signal: IntelligenceSignal) -> TimeBasis:
    return TimeBasis(signal.metadata.time_basis.value)


def _qae_horizon(signal: IntelligenceSignal) -> Horizon:
    return Horizon(signal.metadata.horizon.value)


def _qae_subject_period(signal: IntelligenceSignal) -> int | str | None:
    payload = signal.content.payload
    value_year = _optional_int(payload.get("value_year"))
    if value_year is not None:
        return value_year
    return signal.metadata.subject_period


def _qae_observation_time(signal: IntelligenceSignal) -> int | str:
    payload = signal.content.payload
    source_report_year = _optional_int(payload.get("source_report_year"))
    if source_report_year is not None:
        return source_report_year
    return signal.metadata.observation_time.isoformat()


def _qae_provenance(signal: IntelligenceSignal):
    provenance = signal.provenance
    if provenance.provenance_type == MSILProvenanceType.PDF_PAGE:
        return PDFPageProvenance(
            page_number=provenance.page_number,
            source_section=provenance.source_section or "UNKNOWN",
            workbook_fingerprint=provenance.workbook_fingerprint,
        )
    if provenance.provenance_type == MSILProvenanceType.ANNOUNCEMENT_REF:
        return AnnouncementRefProvenance(
            exchange="PSX",
            announcement_id=provenance.announcement_id,
            announcement_date=_date_string(provenance.retrieved_at),
            url=_snapshot_url(provenance),
        )
    if provenance.provenance_type == MSILProvenanceType.REGULATORY_REF:
        return RegulatoryRefProvenance(
            regulator="SECP",
            notice_id=provenance.notice_id,
            notice_date=_date_string(provenance.retrieved_at),
            url=_snapshot_url(provenance),
        )
    if provenance.provenance_type == MSILProvenanceType.URL_SNAPSHOT:
        return URLSnapshotProvenance(
            url=provenance.url,
            publisher=provenance.source_type.value,
            document_date=_date_string(provenance.retrieved_at),
        )
    if provenance.provenance_type == MSILProvenanceType.MARKET_DATA_REF:
        return MarketDataRefProvenance(
            market_date=str(provenance.trade_date),
            series_or_ticker=provenance.series_id,
            dataset=provenance.source_type.value,
        )
    if provenance.provenance_type == MSILProvenanceType.SECTOR_REF:
        return SectorRefProvenance(
            sector_id=provenance.sector_ref,
            provider=provenance.source_type.value,
            summary_date=_date_string(provenance.retrieved_at),
        )
    raise ValueError(
        f"MSIL provenance_type is not supported as QAE narrative provenance: {provenance.provenance_type.value}"
    )


def _snapshot_id(signal: IntelligenceSignal) -> str | None:
    snapshot_ref = getattr(signal.provenance, "snapshot_ref", None)
    if snapshot_ref is None:
        return None
    return snapshot_ref.snapshot_id


def _snapshot_url(provenance: Any) -> str:
    snapshot_ref = getattr(provenance, "snapshot_ref", None)
    if snapshot_ref is None:
        return "snapshot://missing"
    return snapshot_ref.snapshot_uri or f"snapshot://{snapshot_ref.snapshot_id}"


def _date_string(value: Any) -> str:
    if value is None:
        return "unknown"
    return value.date().isoformat() if hasattr(value, "date") else str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace("FY", ""))
    except (TypeError, ValueError):
        return None


def _bounded_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    return max(0.0, min(1.0, parsed))


def _has_quantitative_evidence(text: str) -> bool:
    return any(character.isdigit() for character in text)


def _derive_specificity(claim: str) -> Specificity:
    normalized = normalize_text(claim)
    generic_terms = {
        "corporate governance",
        "code of conduct",
        "going concern",
        "adequate internal controls",
    }
    if any(term in normalized for term in generic_terms):
        return Specificity.GENERIC
    return Specificity.NAMED


def _qae_divergence_type(divergence: MSILDivergence) -> DivergenceType:
    source_types = {divergence.side_a.source_type.value, divergence.side_b.source_type.value}
    if "market_watch" in source_types or "futures_market_watch" in source_types:
        return DivergenceType.MANAGEMENT_VS_MARKET_SENTIMENT
    return DivergenceType.NARRATIVE_VS_NARRATIVE


def _divergence_impacts(divergence: MSILDivergence) -> tuple[float, float]:
    authorities = {
        divergence.side_a.authority_class.value,
        divergence.side_b.authority_class.value,
    }
    if "regulatory_independent" in authorities:
        return 0.20, 0.25
    if len(authorities) > 1:
        return 0.15, 0.20
    return 0.10, 0.15


def _authority_ceiling(theme) -> float:
    authorities = set(theme.evidence.authority_class_by_signal.values())
    if not authorities:
        return 1.0
    if authorities == {AuthorityClass.INDEPENDENT_OPINION}:
        return 0.75
    if authorities == {AuthorityClass.MARKET_REVEALED}:
        return 0.60
    if authorities == {AuthorityClass.SECTOR_AGGREGATE}:
        return 0.65
    return 1.0


def _corroboration_by_theme(
    references: tuple[QAEMSILCorroborationApplication, ...],
    assembly_result: ThemeAssemblyResult,
) -> dict[str, tuple[QAEMSILCorroborationApplication, ...]]:
    theme_signal_ids = {
        theme.theme_reference.theme_ref: set(theme.signal_ids)
        for theme in assembly_result.themes
    }
    grouped: dict[str, list[QAEMSILCorroborationApplication]] = defaultdict(list)
    for reference in references:
        member_refs = set(reference.member_signal_refs)
        for theme_ref, signal_ids in theme_signal_ids.items():
            if len(member_refs & signal_ids) >= 2:
                grouped[theme_ref].append(reference)
    return {theme_ref: tuple(values) for theme_ref, values in grouped.items()}


def _divergence_by_theme(
    references: tuple[DivergenceReference, ...],
    assembly_result: ThemeAssemblyResult,
) -> dict[str, tuple[DivergenceReference, ...]]:
    existing_theme_refs = {theme.theme_reference.theme_ref for theme in assembly_result.themes}
    grouped: dict[str, list[DivergenceReference]] = defaultdict(list)
    for reference in references:
        if reference.theme_ref in existing_theme_refs:
            grouped[reference.theme_ref].append(reference)
    return {theme_ref: tuple(values) for theme_ref, values in grouped.items()}


def _dedupe_divergences(
    divergences: tuple[DivergenceReference, ...],
) -> tuple[DivergenceReference, ...]:
    by_id: dict[str, DivergenceReference] = {}
    for divergence in divergences:
        by_id[divergence.divergence_id] = divergence
    return tuple(by_id[key] for key in sorted(by_id))


def _distribution(values: Iterable[float]) -> dict[str, int]:
    distribution = {"0.0": 0, "0.1-0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, "0.9+": 0}
    for value in values:
        if value == 0:
            distribution["0.0"] += 1
        elif value < 0.5:
            distribution["0.1-0.5"] += 1
        elif value < 0.7:
            distribution["0.5-0.7"] += 1
        elif value < 0.9:
            distribution["0.7-0.9"] += 1
        else:
            distribution["0.9+"] += 1
    return distribution


__all__ = [
    "QAEMSILConsumptionResult",
    "QAEMSILCorroborationApplication",
    "QAEMSILEvidenceAdapter",
    "QAEMSILEvidenceReference",
    "QAEMSILThemeApplicationResult",
]
