"""Annual-report OCR Insight to MSIL IntelligenceSignal adapter."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ocr_engine.models.insights_extraction import Insight

from multi_source_intelligence.models import (
    AuthorityClass,
    ClaimType,
    ContentClass,
    EntityResolutionResult,
    EntityScope,
    Horizon,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    PDFPageProvenance,
    ReviewStatus,
    SourceType,
    TimeBasis,
)
from multi_source_intelligence.models.entity_registry import normalize_identifier


REVIEW_REJECT_THRESHOLD = 0.50
REVIEW_THRESHOLD = 0.70
NUMERIC_REFERENCE_PATTERN = re.compile(
    r"(?<![\w.])"
    r"(?P<prefix>PKR|Rs\.?|Rupees)?"
    r"\s*"
    r"(?P<number>\(?[-+]?\d[\d,]*(?:\.\d+)?\)?)"
    r"\s*"
    r"(?P<suffix>%|percent|times|x|days|thousand|million|billion)?",
    re.IGNORECASE,
)


class AnnualReportAdapterMappingFailure(BaseModel):
    """One failed OCR-insight mapping attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    insight_index: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    source_report_year: int | None = Field(default=None, ge=1900)
    source_section: str | None = Field(default=None)


class AnnualReportAdapterResult(BaseModel):
    """Result returned by the annual-report adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_ref: str = Field(..., min_length=1)
    report_reference: str = Field(..., min_length=1)
    workbook_fingerprint: str = Field(..., min_length=1)
    insights_processed: int = Field(..., ge=0)
    signals_generated: int = Field(..., ge=0)
    signals: tuple[IntelligenceSignal, ...] = Field(default_factory=tuple)
    mapping_failures: tuple[AnnualReportAdapterMappingFailure, ...] = Field(
        default_factory=tuple
    )
    content_class_distribution: dict[str, int] = Field(default_factory=dict)
    provenance_coverage: dict[str, int | bool] = Field(default_factory=dict)
    authority_distribution: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_counts(self) -> "AnnualReportAdapterResult":
        if self.signals_generated != len(self.signals):
            raise ValueError("signals_generated must equal len(signals).")
        if self.insights_processed < len(self.mapping_failures):
            raise ValueError("mapping_failures cannot exceed insights_processed.")
        return self


class AnnualReportAdapter:
    """Convert OCR Engine annual-report insights into MSIL signals."""

    def __init__(
        self,
        *,
        entity_resolution: EntityResolutionResult,
        workbook_fingerprint: str,
        report_reference: str,
        entity_scope: EntityScope = EntityScope.COMPANY,
        source_independent_of_issuer: bool = False,
        verified: bool = True,
        trust_prior: float = 0.9,
    ) -> None:
        if entity_resolution.review_status != ReviewStatus.RESOLVED:
            raise ValueError("AnnualReportAdapter requires a resolved entity_resolution.")
        if not entity_resolution.resolved_entity_ref:
            raise ValueError("entity_resolution must include resolved_entity_ref.")
        if not workbook_fingerprint.strip():
            raise ValueError("workbook_fingerprint is required.")
        if not report_reference.strip():
            raise ValueError("report_reference is required.")

        self._entity_resolution = entity_resolution
        self._entity_ref = entity_resolution.resolved_entity_ref
        self._entity_scope = entity_scope
        self._workbook_fingerprint = workbook_fingerprint
        self._report_reference = report_reference
        self._source_independent_of_issuer = source_independent_of_issuer
        self._verified = verified
        self._trust_prior = trust_prior

    def adapt_insight(
        self,
        insight: Insight | Mapping[str, Any],
        *,
        sequence_index: int = 0,
    ) -> tuple[IntelligenceSignal, ...]:
        """Convert one OCR insight into one narrative signal plus numeric references."""

        insight_data = _insight_to_dict(insight)
        narrative_signal = self._narrative_signal(insight_data, sequence_index)
        signals = [narrative_signal]
        for reference_index, numeric_reference in enumerate(
            _extract_numeric_references(insight_data["takeaway"])
        ):
            signals.append(
                self._numeric_reference_signal(
                    insight_data=insight_data,
                    sequence_index=sequence_index,
                    reference_index=reference_index,
                    numeric_reference=numeric_reference,
                    narrative_signal_id=narrative_signal.signal_id or "",
                )
            )
        return tuple(signals)

    def adapt_insights(
        self,
        insights: Iterable[Insight | Mapping[str, Any]],
    ) -> AnnualReportAdapterResult:
        """Convert OCR insights into an adapter result with audit distributions."""

        signals: list[IntelligenceSignal] = []
        failures: list[AnnualReportAdapterMappingFailure] = []
        insights_processed = 0
        for sequence_index, insight in enumerate(insights):
            insights_processed += 1
            try:
                signals.extend(
                    self.adapt_insight(insight, sequence_index=sequence_index)
                )
            except Exception as exc:  # noqa: BLE001 - failure is reported, not swallowed.
                failures.append(
                    _failure_from_insight(
                        insight,
                        insight_index=sequence_index,
                        reason=str(exc),
                    )
                )

        return AnnualReportAdapterResult(
            entity_ref=self._entity_ref,
            report_reference=self._report_reference,
            workbook_fingerprint=self._workbook_fingerprint,
            insights_processed=insights_processed,
            signals_generated=len(signals),
            signals=tuple(signals),
            mapping_failures=tuple(failures),
            content_class_distribution=dict(
                Counter(signal.content.content_class.value for signal in signals)
            ),
            provenance_coverage=_provenance_coverage(signals),
            authority_distribution=dict(
                Counter(signal.classification.authority_class.value for signal in signals)
            ),
        )

    def audit_result(self, result: AnnualReportAdapterResult) -> dict[str, Any]:
        """Build a JSON-serializable audit payload for one adapter result."""

        return {
            "audit_name": "msil_annual_report_adapter_audit",
            "phase": "MSIL Phase 3",
            "entity_ref": result.entity_ref,
            "report_reference": result.report_reference,
            "workbook_fingerprint": result.workbook_fingerprint,
            "insights_processed": result.insights_processed,
            "signals_generated": result.signals_generated,
            "content_class_distribution": result.content_class_distribution,
            "provenance_coverage": result.provenance_coverage,
            "authority_distribution": result.authority_distribution,
            "mapping_failures": [
                failure.model_dump(mode="json") for failure in result.mapping_failures
            ],
            "creation_eligible_distribution": dict(
                Counter(
                    str(signal.classification.creation_eligible).lower()
                    for signal in result.signals
                )
            ),
            "numeric_reference_only_signals": sum(
                1
                for signal in result.signals
                if signal.content.content_class == ContentClass.NUMERIC_CLAIM
                and signal.classification.creation_eligible is False
            ),
        }

    def _narrative_signal(
        self,
        insight_data: dict[str, Any],
        sequence_index: int,
    ) -> IntelligenceSignal:
        claim_type, horizon = _derive_claim_type_and_horizon(
            insight_data["source_section"]
        )
        content = IntelligenceSignalContent(
            content_class=ContentClass.NARRATIVE_CLAIM,
            identity_key=_identity_key(
                report_reference=self._report_reference,
                source_report_year=insight_data["source_report_year"],
                page_number=insight_data["page_number"],
                value_year=insight_data["value_year"],
                source_section=insight_data["source_section"],
                sequence_index=sequence_index,
                suffix="narrative",
            ),
            claim_text=insight_data["takeaway"],
            normalized_claim_text=normalize_identifier(insight_data["takeaway"]),
            payload=_source_payload(
                insight_data,
                review_status=_derive_review_status(insight_data["confidence"]),
                numeric_reference_only=False,
            ),
        )
        return IntelligenceSignal(
            entity_ref=self._entity_ref,
            entity_scope=self._entity_scope,
            entity_resolution=self._entity_resolution,
            content=content,
            classification=IntelligenceSignalClassification(
                content_class=ContentClass.NARRATIVE_CLAIM,
                source_type=SourceType.ANNUAL_REPORT,
                claim_type=claim_type,
                authority_class=AuthorityClass.AUDITED_ISSUER,
                creation_eligible=True,
                mapping_confidence=1.0,
                authority_confidence=1.0,
                independence_metadata={
                    "source_independent_of_issuer": self._source_independent_of_issuer,
                    "authority_basis": "annual_report",
                },
            ),
            metadata=_metadata(
                insight_data,
                horizon=horizon,
                report_reference=self._report_reference,
                source_independent_of_issuer=self._source_independent_of_issuer,
                verified=self._verified,
                trust_prior=self._trust_prior,
            ),
            provenance=_pdf_provenance(
                insight_data,
                workbook_fingerprint=self._workbook_fingerprint,
                report_reference=self._report_reference,
            ),
        )

    def _numeric_reference_signal(
        self,
        *,
        insight_data: dict[str, Any],
        sequence_index: int,
        reference_index: int,
        numeric_reference: dict[str, str],
        narrative_signal_id: str,
    ) -> IntelligenceSignal:
        content = IntelligenceSignalContent(
            content_class=ContentClass.NUMERIC_CLAIM,
            identity_key=_identity_key(
                report_reference=self._report_reference,
                source_report_year=insight_data["source_report_year"],
                page_number=insight_data["page_number"],
                value_year=insight_data["value_year"],
                source_section=insight_data["source_section"],
                sequence_index=sequence_index,
                suffix=f"numeric-reference-{reference_index}",
            ),
            metric_ref=f"annual_report_numeric_reference:{_slug(insight_data['area'])}",
            value=numeric_reference["raw_value"],
            unit=numeric_reference["unit"],
            payload={
                **_source_payload(
                    insight_data,
                    review_status=_derive_review_status(insight_data["confidence"]),
                    numeric_reference_only=True,
                ),
                "numeric_reference": numeric_reference,
                "originating_narrative_signal_id": narrative_signal_id,
                "not_authoritative_value": True,
            },
        )
        return IntelligenceSignal(
            entity_ref=self._entity_ref,
            entity_scope=self._entity_scope,
            entity_resolution=self._entity_resolution,
            content=content,
            classification=IntelligenceSignalClassification(
                content_class=ContentClass.NUMERIC_CLAIM,
                source_type=SourceType.ANNUAL_REPORT,
                claim_type=ClaimType.DESCRIPTIVE,
                authority_class=AuthorityClass.AUDITED_ISSUER,
                creation_eligible=False,
                mapping_confidence=1.0,
                authority_confidence=1.0,
                independence_metadata={
                    "source_independent_of_issuer": self._source_independent_of_issuer,
                    "authority_basis": "annual_report_numeric_reference_only",
                },
            ),
            metadata=_metadata(
                insight_data,
                horizon=Horizon.HISTORICAL,
                report_reference=self._report_reference,
                source_independent_of_issuer=self._source_independent_of_issuer,
                verified=self._verified,
                trust_prior=self._trust_prior,
                source_record_suffix=f"numeric-{reference_index}",
            ),
            provenance=_pdf_provenance(
                insight_data,
                workbook_fingerprint=self._workbook_fingerprint,
                report_reference=self._report_reference,
            ),
        )


def _insight_to_dict(insight: Insight | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(insight, Insight):
        data = insight.model_dump(mode="python")
    else:
        data = dict(insight)
    required = (
        "value_year",
        "source_report_year",
        "area",
        "takeaway",
        "source_section",
        "page_number",
        "confidence",
    )
    missing = [field for field in required if field not in data or data[field] is None]
    if missing:
        raise ValueError(f"insight missing required fields: {', '.join(missing)}")
    return {
        "value_year": int(data["value_year"]),
        "source_report_year": int(data["source_report_year"]),
        "area": str(data["area"]).strip(),
        "takeaway": str(data["takeaway"]).strip(),
        "source_section": str(data["source_section"]).strip(),
        "page_number": int(data["page_number"]),
        "confidence": float(data["confidence"]),
        "review_status": data.get("review_status"),
    }


def _failure_from_insight(
    insight: Insight | Mapping[str, Any],
    *,
    insight_index: int,
    reason: str,
) -> AnnualReportAdapterMappingFailure:
    try:
        data = insight.model_dump(mode="python") if isinstance(insight, Insight) else dict(insight)
    except Exception:  # noqa: BLE001
        data = {}
    return AnnualReportAdapterMappingFailure(
        insight_index=insight_index,
        reason=reason,
        page_number=data.get("page_number"),
        source_report_year=data.get("source_report_year"),
        source_section=data.get("source_section"),
    )


def _metadata(
    insight_data: dict[str, Any],
    *,
    horizon: Horizon,
    report_reference: str,
    source_independent_of_issuer: bool,
    verified: bool,
    trust_prior: float,
    source_record_suffix: str | None = None,
) -> IntelligenceSignalMetadata:
    source_record_id = _identity_key(
        report_reference=report_reference,
        source_report_year=insight_data["source_report_year"],
        page_number=insight_data["page_number"],
        value_year=insight_data["value_year"],
        source_section=insight_data["source_section"],
        sequence_index=0,
        suffix=source_record_suffix or "insight",
    )
    return IntelligenceSignalMetadata(
        observation_time=datetime(
            int(insight_data["source_report_year"]), 1, 1, tzinfo=timezone.utc
        ),
        subject_period=f"FY{insight_data['value_year']}",
        time_basis=TimeBasis.FISCAL,
        horizon=horizon,
        source_independent_of_issuer=source_independent_of_issuer,
        verified=verified,
        trust_prior=trust_prior,
        source_record_id=source_record_id,
        source_lineage_hooks=(report_reference,),
    )


def _pdf_provenance(
    insight_data: dict[str, Any],
    *,
    workbook_fingerprint: str,
    report_reference: str,
) -> PDFPageProvenance:
    return PDFPageProvenance(
        workbook_fingerprint=workbook_fingerprint,
        page_number=insight_data["page_number"],
        report_reference=report_reference,
        source_report_year=insight_data["source_report_year"],
        source_section=insight_data["source_section"],
    )


def _source_payload(
    insight_data: dict[str, Any],
    *,
    review_status: str,
    numeric_reference_only: bool,
) -> dict[str, Any]:
    return {
        "area": insight_data["area"],
        "source_section": insight_data["source_section"],
        "page_number": insight_data["page_number"],
        "source_report_year": insight_data["source_report_year"],
        "value_year": insight_data["value_year"],
        "confidence": insight_data["confidence"],
        "review_status": insight_data.get("review_status") or review_status,
        "numeric_reference_only": numeric_reference_only,
    }


def _derive_review_status(confidence: float) -> str:
    if confidence < REVIEW_REJECT_THRESHOLD:
        return "rejected_low_confidence"
    if confidence < REVIEW_THRESHOLD:
        return "review"
    return "accepted"


def _derive_claim_type_and_horizon(source_section: str) -> tuple[ClaimType, Horizon]:
    normalized = normalize_identifier(source_section)
    if any(token in normalized for token in ("outlook", "chairman", "ceo", "strategy", "opportunities")):
        return ClaimType.FORWARD_EXPECTATION, Horizon.FORWARD
    if any(token in normalized for token in ("directors", "governance", "regulatory", "compliance")):
        return ClaimType.REGULATORY_COMPLIANCE, Horizon.HISTORICAL
    if any(token in normalized for token in ("business review", "financial review", "management discussion", "mda", "md and a")):
        return ClaimType.AUDITED_FACT, Horizon.HISTORICAL
    if "risk" in normalized:
        return ClaimType.DESCRIPTIVE, Horizon.FORWARD
    return ClaimType.DESCRIPTIVE, Horizon.CURRENT


def _extract_numeric_references(text: str) -> tuple[dict[str, str], ...]:
    references: list[dict[str, str]] = []
    for match in NUMERIC_REFERENCE_PATTERN.finditer(text):
        raw = match.group(0).strip()
        number = match.group("number")
        if not raw or _looks_like_year_only(number):
            continue
        unit = _derive_unit(match.group("prefix"), match.group("suffix"))
        references.append(
            {
                "raw_value": raw,
                "number_text": number,
                "unit": unit,
            }
        )
    return tuple(references)


def _derive_unit(prefix: str | None, suffix: str | None) -> str:
    if suffix:
        normalized_suffix = suffix.lower().replace(".", "")
        if normalized_suffix == "percent":
            return "%"
        return normalized_suffix
    if prefix:
        return "PKR"
    return "unspecified"


def _looks_like_year_only(number: str) -> bool:
    cleaned = number.strip("()")
    return cleaned.isdigit() and 1900 <= int(cleaned) <= 2100


def _identity_key(
    *,
    report_reference: str,
    source_report_year: int,
    page_number: int,
    value_year: int,
    source_section: str,
    sequence_index: int,
    suffix: str,
) -> str:
    return (
        f"annual_report:{report_reference}:report_year:{source_report_year}:"
        f"page:{page_number}:value_year:{value_year}:"
        f"section:{_slug(source_section)}:index:{sequence_index}:{suffix}"
    )


def _slug(value: str) -> str:
    normalized = normalize_identifier(value)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "unknown"


def _provenance_coverage(signals: Iterable[IntelligenceSignal]) -> dict[str, int | bool]:
    signal_list = list(signals)
    with_pdf_page = [
        signal
        for signal in signal_list
        if signal.provenance.provenance_type.value == "PDF_PAGE"
    ]
    return {
        "signals_with_provenance": len([signal for signal in signal_list if signal.provenance]),
        "signals_with_pdf_page_provenance": len(with_pdf_page),
        "signals_with_page_number": len(
            [
                signal
                for signal in signal_list
                if getattr(signal.provenance, "page_number", None)
            ]
        ),
        "signals_with_report_reference": len(
            [
                signal
                for signal in signal_list
                if getattr(signal.provenance, "report_reference", None)
            ]
        ),
        "all_signals_provenance_backed": all(signal.provenance for signal in signal_list),
    }


__all__ = [
    "AnnualReportAdapter",
    "AnnualReportAdapterMappingFailure",
    "AnnualReportAdapterResult",
]
