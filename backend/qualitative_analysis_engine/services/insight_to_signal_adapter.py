"""Annual-report OCR Insight to QualitativeSignal adapter."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from ocr_engine.models.insights_extraction import Insight
from qualitative_analysis_engine.models import (
    AuthorityClass,
    ClaimType,
    EntityScope,
    Horizon,
    MappingMethod,
    PDFPageProvenance,
    QualitativeSignal,
    SourceType,
    Specificity,
    TimeBasis,
)

from .mapping_confidence import MappingConfidenceComposer
from .section_router import SourceSectionRouter
from .taxonomy_loader import TaxonomyDefinition, TaxonomyLoader
from .text_normalization import normalize_text
from .theme_canonicalizer import ThemeCanonicalizer


AUTHORITY_MATRIX_VERSION = "1.0.0"
SIGNAL_VERSION = "1.0.0"
REVIEW_REJECT_THRESHOLD = 0.50
REVIEW_THRESHOLD = 0.70


class InsightToSignalAdapter:
    """Convert annual-report OCR insights into QAE qualitative signals."""

    def __init__(
        self,
        *,
        entity_ref: str,
        workbook_fingerprint: str,
        taxonomy: TaxonomyDefinition | None = None,
        taxonomy_loader: TaxonomyLoader | None = None,
        canonicalizer: ThemeCanonicalizer | None = None,
        section_router: SourceSectionRouter | None = None,
        confidence_composer: MappingConfidenceComposer | None = None,
        authority_matrix_version: str = AUTHORITY_MATRIX_VERSION,
        signal_version: str = SIGNAL_VERSION,
    ) -> None:
        if not entity_ref.strip():
            raise ValueError("entity_ref is required.")
        if not workbook_fingerprint.strip():
            raise ValueError("workbook_fingerprint is required.")

        self._entity_ref = entity_ref
        self._workbook_fingerprint = workbook_fingerprint
        self._taxonomy = taxonomy or (taxonomy_loader or TaxonomyLoader()).load()
        self._section_router = section_router or SourceSectionRouter()
        self._confidence_composer = (
            confidence_composer or MappingConfidenceComposer()
        )
        self._canonicalizer = canonicalizer or ThemeCanonicalizer(
            self._taxonomy,
            section_router=self._section_router,
            confidence_composer=self._confidence_composer,
        )
        self._authority_matrix_version = authority_matrix_version
        self._signal_version = signal_version

    def adapt_insight(
        self,
        insight: Insight | Mapping[str, Any],
        *,
        sequence_index: int = 0,
        section_confidence: float | None = None,
        review_status: str | None = None,
    ) -> QualitativeSignal:
        """Convert one annual-report OCR insight into a QualitativeSignal."""

        insight_data = _insight_to_dict(insight)
        extraction_confidence = float(insight_data["confidence"])
        source_section = str(insight_data["source_section"])
        takeaway = str(insight_data["takeaway"])
        area = str(insight_data["area"])
        normalized_claim_text = normalize_text(takeaway)
        section_route = self._section_router.route(source_section)
        effective_section_confidence = (
            section_confidence
            if section_confidence is not None
            else section_route.route_confidence
            if section_route.recognized
            else None
        )
        canonicalization = self._canonicalizer.canonicalize(
            area,
            takeaway=takeaway,
            source_section=source_section,
            extraction_confidence=extraction_confidence,
            section_confidence=effective_section_confidence,
        )
        signal_confidence = self._confidence_composer.compose(
            mapping_confidence=canonicalization.mapping_confidence,
            extraction_confidence=extraction_confidence,
            section_confidence=effective_section_confidence,
            section_theme_conflict=False,
        )

        claim_type = _derive_claim_type(source_section)
        horizon = _derive_horizon(source_section, canonicalization.category_ref)
        signal_id = _build_signal_id(
            entity_ref=self._entity_ref,
            source_report_year=int(insight_data["source_report_year"]),
            page_number=int(insight_data["page_number"]),
            source_section=source_section,
            theme_ref=canonicalization.theme_ref,
            category_ref=canonicalization.category_ref,
            value_year=int(insight_data["value_year"]),
            sequence_index=sequence_index,
            signal_version=self._signal_version,
        )
        resolved_review_status = (
            review_status
            or insight_data.get("review_status")
            or _derive_review_status(extraction_confidence)
        )

        return QualitativeSignal(
            signal_id=signal_id,
            signal_version=self._signal_version,
            entity_ref=self._entity_ref,
            entity_scope=EntityScope.COMPANY,
            source_type=SourceType.ANNUAL_REPORT,
            taxonomy_version=self._taxonomy.taxonomy_version,
            authority_matrix_version=self._authority_matrix_version,
            claim=takeaway.strip(),
            normalized_claim_text=normalized_claim_text,
            raw_excerpt=takeaway.strip(),
            is_quantified=_has_quantitative_evidence(takeaway),
            specificity=_derive_specificity(takeaway),
            category_ref=canonicalization.category_ref,
            theme_ref=canonicalization.theme_ref,
            subtheme_ref=None,
            mapping_method=canonicalization.mapping_method,
            mapping_confidence=canonicalization.mapping_confidence,
            routing_basis=canonicalization.routing_basis,
            unmapped=canonicalization.unmapped,
            claim_type=claim_type,
            authority_class=AuthorityClass.AUDITED_ISSUER,
            source_independent_of_issuer=False,
            verified=True,
            trust_prior=0.9,
            observation_time=int(insight_data["source_report_year"]),
            source_report_year=int(insight_data["source_report_year"]),
            subject_period=int(insight_data["value_year"]),
            value_year=int(insight_data["value_year"]),
            time_basis=TimeBasis.FISCAL,
            horizon=horizon,
            provenance=PDFPageProvenance(
                page_number=int(insight_data["page_number"]),
                source_section=source_section,
                workbook_fingerprint=self._workbook_fingerprint,
            ),
            page_number=int(insight_data["page_number"]),
            source_section=source_section,
            extraction_confidence=extraction_confidence,
            structure_confidence=effective_section_confidence,
            signal_confidence=signal_confidence,
            creation_eligible=not canonicalization.unmapped,
            review_status=resolved_review_status,
            source_metadata={
                "area": area,
                "source_section": source_section,
                "page_number": int(insight_data["page_number"]),
                "source_report_year": int(insight_data["source_report_year"]),
                "value_year": int(insight_data["value_year"]),
                "ocr_confidence": extraction_confidence,
                "review_status": resolved_review_status,
                "section_confidence": effective_section_confidence,
                "section_theme_conflict": canonicalization.section_theme_conflict,
                "canonicalization_evidence": list(canonicalization.evidence),
                "matched_text": canonicalization.matched_text,
                "secondary_categories": list(canonicalization.secondary_categories),
            },
        )

    def adapt_insights(
        self,
        insights: Iterable[Insight | Mapping[str, Any]],
        *,
        section_confidence_by_page: Mapping[int, float] | None = None,
    ) -> tuple[QualitativeSignal, ...]:
        """Convert multiple annual-report insights into qualitative signals."""

        signals: list[QualitativeSignal] = []
        for sequence_index, insight in enumerate(insights):
            insight_data = _insight_to_dict(insight)
            page_number = int(insight_data["page_number"])
            signals.append(
                self.adapt_insight(
                    insight_data,
                    sequence_index=sequence_index,
                    section_confidence=section_confidence_by_page.get(page_number)
                    if section_confidence_by_page
                    else None,
                )
            )
        return tuple(signals)

    def audit_signals(
        self,
        insights: Iterable[Insight | Mapping[str, Any]],
        *,
        section_confidence_by_page: Mapping[int, float] | None = None,
    ) -> dict[str, Any]:
        """Generate a deterministic signal-generation audit for insights."""

        signals = self.adapt_insights(
            insights,
            section_confidence_by_page=section_confidence_by_page,
        )
        return build_signal_generation_audit(signals)

    def audit_bundle(
        self,
        bundle_path: str | Path,
    ) -> dict[str, Any]:
        """Load a Query Engine bundle and audit generated annual-report signals."""

        path = Path(bundle_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        insights = _extract_bundle_insights(payload)
        audit = self.audit_signals(insights)
        audit["bundle_path"] = str(path)
        audit["company_name"] = payload.get("company_name")
        audit["workbook_fingerprint"] = payload.get("workbook_fingerprint")
        audit["report_years"] = list(
            payload.get("insights_results_by_report_year", {}).keys()
        )
        return audit

    def write_audit(
        self,
        output_path: str | Path,
        *,
        bundle_path: str | Path | None = None,
        insights: Iterable[Insight | Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate and persist a signal-generation audit."""

        if bundle_path is not None:
            audit = self.audit_bundle(bundle_path)
        elif insights is not None:
            audit = self.audit_signals(insights)
        else:
            audit = self.audit_signals(())

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return audit


def build_signal_generation_audit(
    signals: Iterable[QualitativeSignal],
) -> dict[str, Any]:
    """Build a deterministic audit summary for generated signals."""

    signal_list = list(signals)
    mapped = [signal for signal in signal_list if not signal.unmapped]
    unmapped = [signal for signal in signal_list if signal.unmapped]
    return {
        "total_insights_processed": len(signal_list),
        "total_signals_generated": len(signal_list),
        "mapped_signals": len(mapped),
        "unmapped_signals": len(unmapped),
        "unmapped_rate": round(len(unmapped) / len(signal_list), 6)
        if signal_list
        else 0.0,
        "signal_confidence_distribution": _confidence_distribution(
            [signal.signal_confidence for signal in signal_list]
        ),
        "category_distribution": dict(
            sorted(
                Counter(
                    signal.category_ref
                    for signal in signal_list
                    if signal.category_ref
                ).items()
            )
        ),
        "theme_distribution": dict(
            sorted(
                Counter(
                    signal.theme_ref for signal in signal_list if signal.theme_ref
                ).items()
            )
        ),
        "mapping_method_distribution": dict(
            sorted(Counter(signal.mapping_method.value for signal in signal_list).items())
        ),
        "authority_class_distribution": dict(
            sorted(
                Counter(
                    signal.authority_class.value for signal in signal_list
                ).items()
            )
        ),
        "claim_type_distribution": dict(
            sorted(Counter(signal.claim_type.value for signal in signal_list).items())
        ),
        "review_status_distribution": dict(
            sorted(
                Counter(
                    signal.review_status for signal in signal_list if signal.review_status
                ).items()
            )
        ),
        "unmapped_samples": [
            {
                "signal_id": signal.signal_id,
                "area": signal.source_metadata.get("area"),
                "source_section": signal.source_section,
                "page_number": signal.page_number,
                "category_ref": signal.category_ref,
            }
            for signal in unmapped[:25]
        ],
    }


def _insight_to_dict(insight: Insight | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(insight, Insight):
        return insight.model_dump(mode="json")
    return dict(insight)


def _extract_bundle_insights(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    insights: list[Mapping[str, Any]] = []
    for _, result in sorted(payload.get("insights_results_by_report_year", {}).items()):
        if not isinstance(result, Mapping):
            continue
        for insight in result.get("insights", []):
            if isinstance(insight, Mapping):
                insights.append(insight)
    return insights


def _build_signal_id(
    *,
    entity_ref: str,
    source_report_year: int,
    page_number: int,
    source_section: str,
    theme_ref: str | None,
    category_ref: str | None,
    value_year: int,
    sequence_index: int,
    signal_version: str,
) -> str:
    theme_or_category = theme_ref or category_ref or "unmapped"
    return ":".join(
        (
            "qae",
            f"v{normalize_text(signal_version).replace(' ', '_')}",
            normalize_text(entity_ref).replace(" ", "_"),
            "annual_report",
            str(source_report_year),
            f"p{page_number}",
            normalize_text(source_section).replace(" ", "_") or "unknown_section",
            normalize_text(theme_or_category).replace(" ", "_") or "unmapped",
            str(value_year),
            f"i{sequence_index}",
        )
    )


def _derive_claim_type(source_section: str) -> ClaimType:
    section = normalize_text(source_section)
    if section in {
        "chairman review",
        "ceo review",
        "outlook",
        "opportunities",
        "strategy",
    }:
        return ClaimType.FORWARD_EXPECTATION
    if section in {"directors report"}:
        return ClaimType.REGULATORY_COMPLIANCE
    return ClaimType.AUDITED_FACT


def _derive_horizon(source_section: str, category_ref: str | None) -> Horizon:
    section = normalize_text(source_section)
    if section in {
        "chairman review",
        "ceo review",
        "outlook",
        "opportunities",
        "strategy",
    } or category_ref == "outlook":
        return Horizon.FORWARD
    return Horizon.HISTORICAL


def _derive_review_status(confidence: float) -> str:
    if confidence < REVIEW_REJECT_THRESHOLD:
        return "rejected_low_confidence"
    if confidence < REVIEW_THRESHOLD:
        return "review"
    return "accepted"


def _derive_specificity(claim: str) -> Specificity:
    normalized_claim = normalize_text(claim)
    generic_terms = (
        "adequate internal controls",
        "going concern",
        "corporate governance",
        "code of conduct",
        "no significant doubts",
    )
    if any(term in normalized_claim for term in generic_terms):
        return Specificity.GENERIC
    return Specificity.NAMED


def _has_quantitative_evidence(claim: str) -> bool:
    return bool(
        re.search(r"\d", claim)
        or any(
            token in claim.lower()
            for token in (
                "%",
                "pkr",
                "rs",
                "usd",
                "million",
                "billion",
                "tons",
                "units",
            )
        )
    )


def _confidence_distribution(values: list[float]) -> dict[str, int]:
    distribution = {
        "0.0": 0,
        "0.1-0.5": 0,
        "0.5-0.7": 0,
        "0.7-0.9": 0,
        "0.9+": 0,
    }
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
    "AUTHORITY_MATRIX_VERSION",
    "SIGNAL_VERSION",
    "InsightToSignalAdapter",
    "build_signal_generation_audit",
]
