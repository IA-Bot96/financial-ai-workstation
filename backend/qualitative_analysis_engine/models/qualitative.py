"""Frozen QAE Phase 1 model contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityScope(str, Enum):
    """Entity scope attached to qualitative evidence."""

    COMPANY = "company"
    SECTOR = "sector"
    MARKET = "market"


class SourceType(str, Enum):
    """Source systems that can produce qualitative signals."""

    ANNUAL_REPORT = "annual_report"
    COMPANY_ANNOUNCEMENTS = "company_announcements"
    SECP_NOTICES = "secp_notices"
    COMPANY_OVERVIEW = "company_overview"
    ANALYSIS_REPORTS = "analysis_reports"
    SECTOR_SUMMARY = "sector_summary"
    DAILY_MARKET_SUMMARY = "daily_market_summary"


class Specificity(str, Enum):
    """Whether a claim is named/specific or generic."""

    NAMED = "named"
    GENERIC = "generic"


class MappingMethod(str, Enum):
    """Taxonomy mapping tier used for a signal."""

    EXACT = "exact"
    ALIAS = "alias"
    KEYWORD = "keyword"
    SECTION_ONLY = "section_only"
    UNMAPPED = "unmapped"


class RoutingBasis(str, Enum):
    """Routing basis used to identify a category prior."""

    SECTION_PRIOR = "section_prior"
    ADAPTER_SIGNAL = "adapter_signal"
    NONE = "none"


class ClaimType(str, Enum):
    """Claim type used for claim-scoped authority weighting."""

    REGULATORY_COMPLIANCE = "regulatory_compliance"
    AUDITED_FACT = "audited_fact"
    OFFICIAL_UNAUDITED_FACT = "official_unaudited_fact"
    FORWARD_EXPECTATION = "forward_expectation"
    DESCRIPTIVE = "descriptive"
    SENTIMENT = "sentiment"
    SECTOR_CONTEXT = "sector_context"


class AuthorityClass(str, Enum):
    """Source-derived authority class for a qualitative signal."""

    REGULATORY_INDEPENDENT = "regulatory_independent"
    AUDITED_ISSUER = "audited_issuer"
    OFFICIAL_ISSUER_UNAUDITED = "official_issuer_unaudited"
    ISSUER_DESCRIPTIVE = "issuer_descriptive"
    INDEPENDENT_OPINION = "independent_opinion"
    SECTOR_AGGREGATE = "sector_aggregate"
    MARKET_REVEALED = "market_revealed"


class TimeBasis(str, Enum):
    """Temporal basis used by a qualitative signal."""

    FISCAL = "fiscal"
    CALENDAR = "calendar"
    CONTINUOUS = "continuous"
    STATIC = "static"


class Horizon(str, Enum):
    """Time horizon represented by a qualitative signal."""

    HISTORICAL = "historical"
    CURRENT = "current"
    FORWARD = "forward"


class ProvenanceType(str, Enum):
    """Citation/provenance variants supported by QAE."""

    PDF_PAGE = "PDF_PAGE"
    ANNOUNCEMENT_REF = "ANNOUNCEMENT_REF"
    REGULATORY_REF = "REGULATORY_REF"
    URL_SNAPSHOT = "URL_SNAPSHOT"
    MARKET_DATA_REF = "MARKET_DATA_REF"
    SECTOR_REF = "SECTOR_REF"
    NONE = "NONE"


class ThemeRole(str, Enum):
    """A signal's role relative to an assembled theme."""

    CREATES = "creates"
    STRENGTHENS = "strengthens"
    CONTRADICTS = "contradicts"
    CONTEXTUALIZES = "contextualizes"


class ThemeSalience(str, Enum):
    """Salience tier for a theme or category count."""

    FULL_SALIENCE = "full_salience"
    LOW_SALIENCE = "low_salience"


class CategoryStatus(str, Enum):
    """Deterministic category status for QAE scorecard output."""

    SKIPPED_NO_ELIGIBLE_SIGNALS = "SKIPPED_NO_ELIGIBLE_SIGNALS"
    SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY = (
        "SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY"
    )
    SKIPPED_INSUFFICIENT_COVERAGE = "SKIPPED_INSUFFICIENT_COVERAGE"
    ANALYZED_WITH_WARNING = "ANALYZED_WITH_WARNING"
    ANALYZED = "ANALYZED"


class RunStatus(str, Enum):
    """Coverage-framed run status for QAE."""

    ANALYZED_WITH_COVERAGE = "ANALYZED_WITH_COVERAGE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


class DivergenceType(str, Enum):
    """Narrative divergence type surfaced by QAE."""

    NARRATIVE_VS_NARRATIVE = "narrative_vs_narrative"
    MANAGEMENT_VS_ANALYST = "management_vs_analyst"
    MANAGEMENT_VS_MARKET_SENTIMENT = "management_vs_market_sentiment"
    COMPANY_VS_SECTOR = "company_vs_sector"
    NARRATIVE_VS_NUMBERS_CANDIDATE = "narrative_vs_numbers_candidate"


class PDFPageProvenance(BaseModel):
    """PDF page-level provenance for annual-report signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: Literal[ProvenanceType.PDF_PAGE] = Field(
        default=ProvenanceType.PDF_PAGE,
        description="Discriminator for PDF page provenance.",
    )
    page_number: int = Field(..., gt=0, description="One-based PDF page number.")
    source_section: str = Field(
        ..., min_length=1, description="Source report section name."
    )
    workbook_fingerprint: str = Field(
        ..., min_length=1, description="Immutable workbook or bundle fingerprint."
    )


class AnnouncementRefProvenance(BaseModel):
    """Exchange announcement provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: Literal[ProvenanceType.ANNOUNCEMENT_REF] = Field(
        default=ProvenanceType.ANNOUNCEMENT_REF
    )
    exchange: str = Field(..., min_length=1, description="Exchange identifier.")
    announcement_id: str = Field(
        ..., min_length=1, description="Exchange announcement id."
    )
    announcement_date: str = Field(
        ..., min_length=1, description="Announcement publication date."
    )
    url: str = Field(..., min_length=1, description="Announcement URL.")


class RegulatoryRefProvenance(BaseModel):
    """Regulatory notice provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: Literal[ProvenanceType.REGULATORY_REF] = Field(
        default=ProvenanceType.REGULATORY_REF
    )
    regulator: str = Field(..., min_length=1, description="Regulator name.")
    notice_id: str = Field(..., min_length=1, description="Notice id.")
    notice_date: str = Field(..., min_length=1, description="Notice date.")
    url: str = Field(..., min_length=1, description="Notice URL.")


class URLSnapshotProvenance(BaseModel):
    """URL snapshot provenance for overview or analyst sources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: Literal[ProvenanceType.URL_SNAPSHOT] = Field(
        default=ProvenanceType.URL_SNAPSHOT
    )
    url: str = Field(..., min_length=1, description="Source URL.")
    publisher: str = Field(..., min_length=1, description="Publisher name.")
    document_date: str = Field(..., min_length=1, description="Document date.")


class MarketDataRefProvenance(BaseModel):
    """Market-data provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: Literal[ProvenanceType.MARKET_DATA_REF] = Field(
        default=ProvenanceType.MARKET_DATA_REF
    )
    market_date: str = Field(..., min_length=1, description="Market date.")
    series_or_ticker: str = Field(
        ..., min_length=1, description="Market series or ticker."
    )
    dataset: str = Field(..., min_length=1, description="Market dataset name.")


class SectorRefProvenance(BaseModel):
    """Sector-summary provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: Literal[ProvenanceType.SECTOR_REF] = Field(
        default=ProvenanceType.SECTOR_REF
    )
    sector_id: str = Field(..., min_length=1, description="Sector identifier.")
    provider: str = Field(..., min_length=1, description="Provider name.")
    summary_date: str = Field(..., min_length=1, description="Summary date.")


class NoneProvenance(BaseModel):
    """Forbidden no-provenance marker used only for validation failures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_type: Literal[ProvenanceType.NONE] = Field(
        default=ProvenanceType.NONE
    )


SignalProvenance: TypeAlias = Annotated[
    PDFPageProvenance
    | AnnouncementRefProvenance
    | RegulatoryRefProvenance
    | URLSnapshotProvenance
    | MarketDataRefProvenance
    | SectorRefProvenance
    | NoneProvenance,
    Field(discriminator="provenance_type"),
]


class QualitativeSignal(BaseModel):
    """Atomic narrative evidence unit consumed by QAE theme assembly."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "signal_id": "lucky:annual_report:225:energy_transition:2025",
                    "entity_ref": "lucky_cement",
                    "entity_scope": "company",
                    "source_type": "annual_report",
                    "taxonomy_version": "1.0.0",
                    "authority_matrix_version": "1.0.0",
                    "claim": "The company expanded solar generation capacity.",
                    "is_quantified": False,
                    "specificity": "named",
                    "category_ref": "esg",
                    "theme_ref": "energy_transition",
                    "mapping_method": "alias",
                    "mapping_confidence": 0.9,
                    "routing_basis": "section_prior",
                    "unmapped": False,
                    "claim_type": "audited_fact",
                    "authority_class": "audited_issuer",
                    "source_independent_of_issuer": False,
                    "verified": True,
                    "trust_prior": 0.9,
                    "observation_time": 2025,
                    "subject_period": 2025,
                    "time_basis": "fiscal",
                    "horizon": "historical",
                    "provenance": {
                        "provenance_type": "PDF_PAGE",
                        "page_number": 84,
                        "source_section": "Sustainability",
                        "workbook_fingerprint": "abc123",
                    },
                    "extraction_confidence": 0.86,
                    "mapping_confidence": 0.9,
                    "signal_confidence": 0.86,
                    "creation_eligible": True,
                }
            ]
        },
    )

    signal_id: str = Field(
        ..., min_length=1, description="Stable text-independent signal id."
    )
    signal_version: str = Field(
        default="1.0.0", min_length=1, description="Signal contract version."
    )
    entity_ref: str = Field(..., min_length=1, description="Canonical entity id.")
    entity_scope: EntityScope = Field(..., description="Entity scope.")
    source_type: SourceType = Field(..., description="Source type.")
    taxonomy_version: str = Field(
        ..., min_length=1, description="Pinned taxonomy version."
    )
    authority_matrix_version: str = Field(
        ..., min_length=1, description="Pinned authority matrix version."
    )

    claim: str = Field(..., min_length=1, description="Normalized narrative claim.")
    normalized_claim_text: str | None = Field(
        default=None,
        description="Normalized claim text retained for adapter diagnostics.",
    )
    raw_excerpt: str | None = Field(default=None, description="Source excerpt.")
    is_quantified: bool = Field(
        ..., description="Whether the claim references a quantity."
    )
    specificity: Specificity = Field(..., description="Claim specificity.")

    category_ref: str | None = Field(
        default=None, description="Canonical category or category prior."
    )
    theme_ref: str | None = Field(default=None, description="Canonical theme.")
    subtheme_ref: str | None = Field(default=None, description="Canonical sub-theme.")
    mapping_method: MappingMethod = Field(..., description="Mapping method.")
    mapping_confidence: float = Field(
        ..., ge=0, le=1, description="Taxonomy mapping confidence."
    )
    routing_basis: RoutingBasis = Field(..., description="Routing basis.")
    unmapped: bool = Field(..., description="Whether the signal is unmapped.")

    claim_type: ClaimType = Field(..., description="Claim type.")
    authority_class: AuthorityClass = Field(..., description="Authority class.")
    source_independent_of_issuer: bool = Field(
        ..., description="Whether the source is independent from the issuer."
    )
    verified: bool = Field(..., description="Whether source origin is verified.")
    trust_prior: float = Field(..., ge=0, le=1, description="Source trust prior.")
    source_lineage: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Known source lineage ids used to prevent circular corroboration.",
    )
    derived_from: tuple[str, ...] = Field(
        default_factory=tuple, description="Upstream source ids."
    )

    observation_time: int | str = Field(
        ..., description="When the claim was made or published."
    )
    source_report_year: int | None = Field(
        default=None,
        ge=1900,
        description="Annual report year for annual-report signals.",
    )
    subject_period: int | str | None = Field(
        default=None, description="Period the claim is about, if any."
    )
    value_year: int | None = Field(
        default=None,
        ge=1900,
        description="Financial year discussed by annual-report OCR insight.",
    )
    time_basis: TimeBasis = Field(..., description="Temporal basis.")
    horizon: Horizon = Field(..., description="Claim horizon.")
    supersedes: tuple[str, ...] = Field(
        default_factory=tuple, description="Signals superseded by this signal."
    )
    superseded_by: tuple[str, ...] = Field(
        default_factory=tuple, description="Signals that supersede this signal."
    )

    provenance: SignalProvenance = Field(..., description="Source provenance.")
    page_number: int | None = Field(
        default=None,
        gt=0,
        description="One-based PDF page number retained for annual-report signals.",
    )
    source_section: str | None = Field(
        default=None,
        description="Annual-report source section retained from OCR insight.",
    )
    snapshot_ref: str | None = Field(
        default=None, description="Immutable snapshot or content hash."
    )
    retrieved_at: datetime | None = Field(
        default=None, description="Retrieval timestamp for external sources."
    )

    extraction_confidence: float = Field(
        ..., ge=0, le=1, description="Claim extraction confidence."
    )
    structure_confidence: float | None = Field(
        default=None, ge=0, le=1, description="Section or structure confidence."
    )
    signal_confidence: float = Field(
        ..., ge=0, le=1, description="Final signal reliability confidence."
    )
    review_status: str | None = Field(
        default=None,
        description="OCR insight governance status retained for diagnostics.",
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-preserved OCR metadata not used for classification.",
    )

    creation_eligible: bool = Field(
        ..., description="Whether the signal may instantiate a theme."
    )
    theme_role: ThemeRole | None = Field(
        default=None, description="Assembly-time role relative to a theme."
    )

    @model_validator(mode="after")
    def _validate_signal_contract(self) -> "QualitativeSignal":
        """Enforce source, mapping, provenance, and confidence invariants."""

        if isinstance(self.provenance, NoneProvenance):
            raise ValueError("signals with NONE provenance may not be emitted.")

        if self.unmapped:
            if self.mapping_method != MappingMethod.UNMAPPED:
                raise ValueError("unmapped signals must use unmapped mapping_method.")
            if self.theme_ref is not None:
                raise ValueError("unmapped signals must not carry theme_ref.")
        else:
            if self.mapping_method == MappingMethod.UNMAPPED:
                raise ValueError("mapped signals cannot use unmapped mapping_method.")
            if not self.category_ref or not self.theme_ref:
                raise ValueError("mapped signals require category_ref and theme_ref.")

        expected_confidence = min(
            self.extraction_confidence,
            self.mapping_confidence,
            self.structure_confidence
            if self.structure_confidence is not None
            else 1.0,
        )
        if abs(self.signal_confidence - expected_confidence) > 1e-9:
            raise ValueError(
                "signal_confidence must equal min(extraction, mapping, structure)."
            )

        if self.source_type == SourceType.ANNUAL_REPORT and not isinstance(
            self.provenance, PDFPageProvenance
        ):
            raise ValueError("annual_report signals require PDF_PAGE provenance.")

        external_source = self.source_type != SourceType.ANNUAL_REPORT
        if external_source and not self.snapshot_ref:
            raise ValueError("external sources require snapshot_ref.")
        if external_source and self.retrieved_at is None:
            raise ValueError("external sources require retrieved_at.")

        if self.source_type in {
            SourceType.COMPANY_OVERVIEW,
            SourceType.DAILY_MARKET_SUMMARY,
        } and self.creation_eligible:
            raise ValueError(
                "company_overview and daily_market_summary are attach-only sources."
            )

        if self.source_type == SourceType.SECTOR_SUMMARY and (
            self.entity_scope != EntityScope.SECTOR
        ):
            raise ValueError("sector_summary signals must use entity_scope=sector.")

        if self.time_basis == TimeBasis.STATIC and self.subject_period is not None:
            raise ValueError("static signals must not carry subject_period.")

        return self


class ThemeReference(BaseModel):
    """Stable QAE theme identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_ref: str = Field(..., min_length=1, description="Canonical entity id.")
    entity_scope: EntityScope = Field(..., description="Entity scope.")
    theme_ref: str = Field(..., min_length=1, description="Canonical theme ref.")
    taxonomy_version: str = Field(
        ..., min_length=1, description="Pinned taxonomy version."
    )


class DivergenceReference(BaseModel):
    """Authority-weighted narrative divergence reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    divergence_id: str = Field(
        ..., min_length=1, description="Stable divergence id."
    )
    divergence_type: DivergenceType = Field(..., description="Divergence type.")
    theme_ref: str = Field(..., min_length=1, description="Affected theme.")
    category_ref: str = Field(..., min_length=1, description="Affected category.")
    signal_ids: tuple[str, ...] = Field(
        ..., min_length=2, description="Signals participating in divergence."
    )
    side_a_signal_id: str = Field(
        ..., min_length=1, description="First side signal id."
    )
    side_b_signal_id: str = Field(
        ..., min_length=1, description="Second side signal id."
    )
    side_a_authority_class: AuthorityClass = Field(
        ..., description="Authority class for first side."
    )
    side_b_authority_class: AuthorityClass = Field(
        ..., description="Authority class for second side."
    )
    summary: str = Field(..., min_length=1, description="Divergence summary.")
    confidence_impact: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Confidence penalty attributable to the divergence.",
    )
    materiality_impact: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Materiality lift attributable to the divergence.",
    )
    auto_resolved: bool = Field(
        default=False, description="Divergences must not be auto-resolved by QAE."
    )

    @model_validator(mode="after")
    def _validate_divergence(self) -> "DivergenceReference":
        """Ensure both sides are included and unresolved."""

        if self.auto_resolved:
            raise ValueError("QAE divergences must never be auto-resolved.")
        if self.side_a_signal_id not in self.signal_ids:
            raise ValueError("side_a_signal_id must be present in signal_ids.")
        if self.side_b_signal_id not in self.signal_ids:
            raise ValueError("side_b_signal_id must be present in signal_ids.")
        return self


class ThemeEvidence(BaseModel):
    """Evidence bundle attached to one grounded theme instance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(..., min_length=1, description="Stable evidence id.")
    theme_ref: str = Field(..., min_length=1, description="Canonical theme ref.")
    signal_ids: tuple[str, ...] = Field(
        ..., min_length=1, description="Supporting signal ids."
    )
    signal_claims: dict[str, str] = Field(
        default_factory=dict, description="Claim text by signal id."
    )
    signal_roles: dict[str, ThemeRole] = Field(
        default_factory=dict, description="Theme role by signal id."
    )
    provenance_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Provenance or citation references."
    )
    observation_times: dict[str, int | str] = Field(
        default_factory=dict, description="Observation time by signal id."
    )
    subject_periods: dict[str, int | str | None] = Field(
        default_factory=dict, description="Subject period by signal id."
    )
    time_basis_by_signal: dict[str, TimeBasis] = Field(
        default_factory=dict, description="Time basis by signal id."
    )
    horizon_by_signal: dict[str, Horizon] = Field(
        default_factory=dict, description="Horizon by signal id."
    )
    authority_class_by_signal: dict[str, AuthorityClass] = Field(
        default_factory=dict, description="Authority class by signal id."
    )
    claim_type_by_signal: dict[str, ClaimType] = Field(
        default_factory=dict, description="Claim type by signal id."
    )
    mapping_method_by_signal: dict[str, MappingMethod] = Field(
        default_factory=dict, description="Mapping method by signal id."
    )
    source_mix: dict[SourceType, int] = Field(
        default_factory=dict, description="Signal count by source type."
    )
    independent_origins: tuple[str, ...] = Field(
        default_factory=tuple, description="Independent origin group identifiers."
    )
    divergence_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Divergence ids touching this evidence."
    )
    duplicate_count: int = Field(
        default=1, ge=1, description="Number of duplicate artifacts collapsed."
    )
    salience: ThemeSalience = Field(..., description="Evidence salience tier.")
    low_salience: bool = Field(
        ..., description="Whether evidence is single-origin or otherwise thin."
    )

    @model_validator(mode="after")
    def _validate_evidence(self) -> "ThemeEvidence":
        """Validate signal grounding and single-signal salience labels."""

        signal_id_set = set(self.signal_ids)
        if len(signal_id_set) != len(self.signal_ids):
            raise ValueError("signal_ids must be unique within ThemeEvidence.")
        if len(self.signal_ids) == 1 and not self.low_salience:
            raise ValueError("single-signal evidence must be marked low_salience.")
        if self.low_salience and self.salience != ThemeSalience.LOW_SALIENCE:
            raise ValueError("low_salience evidence must use low_salience tier.")
        for mapping in (
            self.signal_claims,
            self.signal_roles,
            self.observation_times,
            self.subject_periods,
            self.time_basis_by_signal,
            self.horizon_by_signal,
            self.authority_class_by_signal,
            self.claim_type_by_signal,
            self.mapping_method_by_signal,
        ):
            extra_keys = set(mapping) - signal_id_set
            if extra_keys:
                raise ValueError(
                    "signal metadata contains ids not present in signal_ids: "
                    + ", ".join(sorted(extra_keys))
                )
        return self


class QualitativeTheme(BaseModel):
    """Grounded qualitative theme instance assembled from admitted signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    theme_reference: ThemeReference = Field(..., description="Stable theme identity.")
    category_ref: str = Field(..., min_length=1, description="Primary category.")
    secondary_categories: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=2,
        description="Bounded secondary category cross-references.",
    )
    subtheme_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Sub-theme facets."
    )
    signal_ids: tuple[str, ...] = Field(
        ..., min_length=1, description="Signals attached to this theme."
    )
    created_by_signal_ids: tuple[str, ...] = Field(
        ..., min_length=1, description="Mapped creation-eligible signal ids."
    )
    evidence: ThemeEvidence = Field(..., description="Evidence bundle.")
    divergence_refs: tuple[DivergenceReference, ...] = Field(
        default_factory=tuple, description="Narrative divergences touching theme."
    )
    source_mix: dict[SourceType, int] = Field(
        default_factory=dict, description="Source mix for the theme."
    )
    salience: ThemeSalience = Field(..., description="Theme salience.")
    theme_confidence: float = Field(
        ..., ge=0, le=1, description="Theme trust confidence."
    )
    evidence_weight: float = Field(
        ..., ge=0, le=1, description="Evidence influence weight."
    )
    materiality: float = Field(
        ..., ge=0, le=1, description="Business materiality."
    )
    low_salience: bool = Field(..., description="Whether theme has low salience.")
    taxonomy_version: str = Field(
        ..., min_length=1, description="Pinned taxonomy version."
    )
    authority_matrix_version: str = Field(
        ..., min_length=1, description="Pinned authority matrix version."
    )

    @model_validator(mode="after")
    def _validate_theme(self) -> "QualitativeTheme":
        """Validate theme grounding, identity, and version invariants."""

        signal_id_set = set(self.signal_ids)
        if len(signal_id_set) != len(self.signal_ids):
            raise ValueError("signal_ids must be unique within QualitativeTheme.")
        if set(self.created_by_signal_ids) - signal_id_set:
            raise ValueError("created_by_signal_ids must be present in signal_ids.")
        if set(self.evidence.signal_ids) - signal_id_set:
            raise ValueError("evidence signal_ids must be present in theme signal_ids.")
        if self.evidence.theme_ref != self.theme_reference.theme_ref:
            raise ValueError("evidence theme_ref must match theme_reference.")
        if self.theme_reference.taxonomy_version != self.taxonomy_version:
            raise ValueError("theme taxonomy version must match identity version.")
        if len(self.signal_ids) == 1 and not self.low_salience:
            raise ValueError("single-signal themes must be marked low_salience.")
        return self


class CategoryCoverage(BaseModel):
    """Mapped-vs-raw coverage data for a category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mapped: int = Field(..., ge=0, description="Mapped signal count.")
    raw: int = Field(..., ge=0, description="Raw signal count.")
    unmapped_rate: float = Field(
        ..., ge=0, le=1, description="Unmapped signals divided by raw signals."
    )
    source_mix: dict[SourceType, int] = Field(
        default_factory=dict, description="Signal source mix."
    )
    expected_sections_present: tuple[str, ...] = Field(
        default_factory=tuple, description="Expected sections observed."
    )
    expected_sections_absent: tuple[str, ...] = Field(
        default_factory=tuple, description="Expected sections missing."
    )

    @model_validator(mode="after")
    def _validate_coverage(self) -> "CategoryCoverage":
        """Validate coverage count consistency."""

        if self.mapped > self.raw:
            raise ValueError("mapped coverage cannot exceed raw coverage.")
        if self.raw == 0 and self.unmapped_rate != 0:
            raise ValueError("unmapped_rate must be 0 when raw coverage is 0.")
        return self


class ConfidenceDistribution(BaseModel):
    """Confidence bucket distribution with ceiling provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket_0: int = Field(default=0, ge=0, description="Confidence exactly 0.")
    bucket_0_1_to_0_5: int = Field(
        default=0, ge=0, description="Confidence from 0.1 to 0.5."
    )
    bucket_0_5_to_0_7: int = Field(
        default=0, ge=0, description="Confidence from 0.5 to 0.7."
    )
    bucket_0_7_to_0_9: int = Field(
        default=0, ge=0, description="Confidence from 0.7 to 0.9."
    )
    bucket_0_9_plus: int = Field(default=0, ge=0, description="Confidence 0.9+.")
    ceiling_reasons: tuple[str, ...] = Field(
        default_factory=tuple, description="Reasons confidence was capped."
    )

    @property
    def total(self) -> int:
        """Return total observations across buckets."""

        return (
            self.bucket_0
            + self.bucket_0_1_to_0_5
            + self.bucket_0_5_to_0_7
            + self.bucket_0_7_to_0_9
            + self.bucket_0_9_plus
        )


class CategoryMateriality(BaseModel):
    """Category-level materiality roll-up."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_materiality: float | None = Field(
        default=None, ge=0, le=1, description="Maximum owned-theme materiality."
    )
    weighted_materiality: float | None = Field(
        default=None, ge=0, le=1, description="Weighted materiality if computed."
    )
    aggregation_method: str = Field(
        ..., min_length=1, description="Non-dilutive aggregation method."
    )
    top_theme_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Most material theme refs."
    )


class QualitativeCategoryResult(BaseModel):
    """Coverage-first result for one qualitative category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category_ref: str = Field(..., min_length=1, description="Canonical category.")
    status: CategoryStatus = Field(..., description="Category status.")
    owned_themes: tuple[QualitativeTheme, ...] = Field(
        default_factory=tuple,
        description="Themes owned by this category's primary category.",
    )
    theme_count_by_salience: dict[ThemeSalience, int] = Field(
        default_factory=dict, description="Theme counts by salience tier."
    )
    coverage: CategoryCoverage = Field(..., description="Category coverage.")
    category_confidence: ConfidenceDistribution = Field(
        ..., description="Confidence distribution for analyzed content."
    )
    category_materiality: CategoryMateriality = Field(
        ..., description="Non-dilutive category materiality."
    )
    divergence_refs: tuple[DivergenceReference, ...] = Field(
        default_factory=tuple, description="Divergences touching the category."
    )
    unmapped_pool_ref: str | None = Field(
        default=None, description="Unmapped pool reference for review backlog."
    )
    skip_reason: str | None = Field(
        default=None, description="Required reason for skipped categories."
    )
    evidence_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Evidence refs for themes or skips."
    )
    taxonomy_version: str = Field(
        ..., min_length=1, description="Pinned taxonomy version."
    )
    authority_matrix_version: str = Field(
        ..., min_length=1, description="Pinned authority matrix version."
    )

    @model_validator(mode="after")
    def _validate_category_result(self) -> "QualitativeCategoryResult":
        """Validate skip evidence and primary category ownership."""

        skipped = self.status.value.startswith("SKIPPED")
        if skipped:
            if not self.skip_reason:
                raise ValueError("skipped categories require skip_reason.")
            if not self.evidence_refs:
                raise ValueError("skipped categories require coverage-gap evidence.")
        if not skipped and self.skip_reason:
            raise ValueError("non-skipped categories must not carry skip_reason.")

        for theme in self.owned_themes:
            if theme.category_ref != self.category_ref:
                raise ValueError("owned theme category_ref must match category_ref.")
            if theme.taxonomy_version != self.taxonomy_version:
                raise ValueError("owned theme taxonomy version must match category.")

        if self.theme_count_by_salience:
            if sum(self.theme_count_by_salience.values()) != len(self.owned_themes):
                raise ValueError("salience counts must equal owned theme count.")
        return self


class SourceSnapshot(BaseModel):
    """Source fingerprint included in the QAE run source set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: SourceType = Field(..., description="Source type.")
    snapshot_ref: str = Field(
        ..., min_length=1, description="Source snapshot or fingerprint."
    )
    retrieved_at: datetime | None = Field(
        default=None, description="Retrieval timestamp when applicable."
    )


class RunCoverageSummary(BaseModel):
    """Run-level coverage summary, reported before confidence/materiality."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analyzable_categories: int = Field(
        ..., ge=0, description="Analyzed or warning categories."
    )
    total_categories: int = Field(
        ..., ge=1, description="Total configured content categories."
    )
    analyzable_percentage: float = Field(
        ..., ge=0, le=100, description="Analyzable category percentage."
    )
    category_status_counts: dict[CategoryStatus, int] = Field(
        default_factory=dict, description="Count by category status."
    )
    per_source_coverage_matrix: dict[SourceType, dict[str, int]] = Field(
        default_factory=dict, description="Source contribution by category."
    )
    section_presence_map: dict[str, bool] = Field(
        default_factory=dict, description="Annual-report section presence map."
    )
    mapped: int = Field(default=0, ge=0, description="Run-wide mapped count.")
    raw: int = Field(default=0, ge=0, description="Run-wide raw count.")
    unmapped_rate: float = Field(
        default=0.0, ge=0, le=1, description="Run-wide unmapped rate."
    )

    @model_validator(mode="after")
    def _validate_run_coverage(self) -> "RunCoverageSummary":
        """Validate run coverage counts."""

        if self.analyzable_categories > self.total_categories:
            raise ValueError("analyzable_categories cannot exceed total_categories.")
        if self.mapped > self.raw:
            raise ValueError("mapped count cannot exceed raw count.")
        return self


class RunMaterialitySummary(BaseModel):
    """Run-level materiality summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    top_theme_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Top material theme refs."
    )
    top_risk_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Top material risk theme refs."
    )
    ranking_basis: str = Field(
        ..., min_length=1, description="Materiality ranking basis."
    )


class DivergenceSummary(BaseModel):
    """Run-level divergence summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_divergences: int = Field(default=0, ge=0)
    count_by_category: dict[str, int] = Field(default_factory=dict)
    count_by_type: dict[DivergenceType, int] = Field(default_factory=dict)
    cross_engine_candidates: tuple[str, ...] = Field(default_factory=tuple)


class UnmappedSummary(BaseModel):
    """Run-level unmapped review backlog summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_unmapped: int = Field(default=0, ge=0)
    unmapped_by_category_prior: dict[str, int] = Field(default_factory=dict)
    sample_claims: tuple[str, ...] = Field(default_factory=tuple)
    suggested_terms: tuple[str, ...] = Field(default_factory=tuple)


class FVEHandoffTheme(BaseModel):
    """One narrative-only theme row exported to Forecast Validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    theme_ref: str = Field(..., min_length=1, description="Theme ref.")
    category_ref: str = Field(..., min_length=1, description="Category ref.")
    horizon: Horizon = Field(..., description="Theme horizon.")
    materiality: float = Field(..., ge=0, le=1, description="Theme materiality.")
    confidence: float = Field(..., ge=0, le=1, description="Theme confidence.")
    authority_classes: tuple[AuthorityClass, ...] = Field(
        default_factory=tuple, description="Authority classes represented."
    )
    claim_types: tuple[ClaimType, ...] = Field(
        default_factory=tuple, description="Claim types represented."
    )
    evidence_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Evidence references."
    )
    narrative_only: bool = Field(
        default=True, description="Hard safety tag for FVE."
    )
    references_quantity: bool = Field(
        default=False,
        description="Whether narrative references a number for FVE gate routing.",
    )
    coverage_caveat: str | None = Field(
        default=None, description="Coverage caveat from source category."
    )
    divergence_refs: tuple[str, ...] = Field(
        default_factory=tuple, description="Divergence references for FVE."
    )
    entity_ref: str = Field(..., min_length=1, description="Entity id.")
    taxonomy_version: str = Field(
        ..., min_length=1, description="Taxonomy version."
    )
    workbook_fingerprint: str | None = Field(
        default=None, description="Workbook or bundle fingerprint."
    )

    @model_validator(mode="after")
    def _validate_handoff_theme(self) -> "FVEHandoffTheme":
        """Guarantee FVE handoff remains narrative-only."""

        if not self.narrative_only:
            raise ValueError("FVE handoff themes must be narrative_only.")
        return self


class FVEHandoffPayload(BaseModel):
    """Narrative-only QAE payload exported to Forecast Validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handoff_id: str = Field(..., min_length=1, description="Stable handoff id.")
    entity_ref: str = Field(..., min_length=1, description="Entity id.")
    taxonomy_version: str = Field(
        ..., min_length=1, description="Taxonomy version."
    )
    authority_matrix_version: str = Field(
        ..., min_length=1, description="Authority matrix version."
    )
    workbook_fingerprint: str | None = Field(default=None)
    themes: tuple[FVEHandoffTheme, ...] = Field(
        default_factory=tuple, description="Narrative-only theme exports."
    )
    coverage_caveats: tuple[str, ...] = Field(
        default_factory=tuple, description="Run/category coverage caveats."
    )
    divergence_refs: tuple[str, ...] = Field(default_factory=tuple)
    narrative_only: bool = Field(
        default=True, description="Hard payload-level safety tag."
    )

    @model_validator(mode="after")
    def _validate_handoff_payload(self) -> "FVEHandoffPayload":
        """Validate narrative-only and version invariants."""

        if not self.narrative_only:
            raise ValueError("FVE handoff payload must be narrative_only.")
        for theme in self.themes:
            if theme.entity_ref != self.entity_ref:
                raise ValueError("handoff theme entity_ref must match payload.")
            if theme.taxonomy_version != self.taxonomy_version:
                raise ValueError("handoff theme taxonomy_version must match payload.")
        return self


class RunVersions(BaseModel):
    """Version pins for a QAE run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str = Field(..., min_length=1)
    authority_matrix_version: str = Field(..., min_length=1)
    assembly_contract_version: str = Field(..., min_length=1)
    scorecard_contract_version: str = Field(..., min_length=1)


class QualitativeRunResult(BaseModel):
    """Root QAE scorecard/run output contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_ref: str = Field(..., min_length=1, description="Entity id.")
    entity_scope: EntityScope = Field(..., description="Entity scope.")
    source_set: tuple[SourceSnapshot, ...] = Field(
        default_factory=tuple, description="Sources ingested for this run."
    )
    observation_window: dict[str, int | str | None] = Field(
        default_factory=dict,
        description="Min/max observation time and time-basis mix.",
    )
    category_results: tuple[QualitativeCategoryResult, ...] = Field(
        ..., min_length=1, description="Category-level results."
    )
    coverage_summary: RunCoverageSummary = Field(
        ..., description="Run-level coverage headline."
    )
    confidence_summary: ConfidenceDistribution = Field(
        ..., description="Run-level confidence distribution."
    )
    materiality_summary: RunMaterialitySummary = Field(
        ..., description="Run-level materiality summary."
    )
    divergence_summary: DivergenceSummary = Field(
        ..., description="Run-level divergence summary."
    )
    unmapped_summary: UnmappedSummary = Field(
        ..., description="Run-level unmapped backlog summary."
    )
    recurring_analysis: dict[str, Any] = Field(
        default_factory=dict, description="Within-report recurring analysis."
    )
    yoy_analysis: dict[str, Any] = Field(
        default_factory=dict,
        description="YoY analysis, usually skipped until sufficient history.",
    )
    fve_handoff: FVEHandoffPayload = Field(
        ..., description="Narrative-only FVE handoff payload."
    )
    run_status: RunStatus = Field(..., description="Coverage-framed run status.")
    versions: RunVersions = Field(..., description="Version pins.")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC generation timestamp.",
    )

    @model_validator(mode="after")
    def _validate_run_result(self) -> "QualitativeRunResult":
        """Validate category, version, and handoff consistency."""

        category_refs = [result.category_ref for result in self.category_results]
        if len(set(category_refs)) != len(category_refs):
            raise ValueError("category_results must have unique category_ref values.")
        if self.coverage_summary.total_categories != len(self.category_results):
            raise ValueError("coverage total_categories must match category_results.")
        for result in self.category_results:
            if result.taxonomy_version != self.versions.taxonomy_version:
                raise ValueError("category taxonomy_version must match run versions.")
            if (
                result.authority_matrix_version
                != self.versions.authority_matrix_version
            ):
                raise ValueError(
                    "category authority_matrix_version must match run versions."
                )
        if self.fve_handoff.entity_ref != self.entity_ref:
            raise ValueError("FVE handoff entity_ref must match run entity_ref.")
        if self.fve_handoff.taxonomy_version != self.versions.taxonomy_version:
            raise ValueError("FVE handoff taxonomy_version must match run versions.")
        return self


__all__ = [
    "AnnouncementRefProvenance",
    "AuthorityClass",
    "CategoryCoverage",
    "CategoryMateriality",
    "CategoryStatus",
    "ClaimType",
    "ConfidenceDistribution",
    "DivergenceReference",
    "DivergenceSummary",
    "DivergenceType",
    "EntityScope",
    "FVEHandoffPayload",
    "FVEHandoffTheme",
    "Horizon",
    "MarketDataRefProvenance",
    "MappingMethod",
    "NoneProvenance",
    "PDFPageProvenance",
    "ProvenanceType",
    "QualitativeCategoryResult",
    "QualitativeRunResult",
    "QualitativeSignal",
    "QualitativeTheme",
    "RegulatoryRefProvenance",
    "RoutingBasis",
    "RunCoverageSummary",
    "RunMaterialitySummary",
    "RunStatus",
    "RunVersions",
    "SectorRefProvenance",
    "SignalProvenance",
    "SourceSnapshot",
    "SourceType",
    "Specificity",
    "ThemeEvidence",
    "ThemeReference",
    "ThemeRole",
    "ThemeSalience",
    "TimeBasis",
    "UnmappedSummary",
    "URLSnapshotProvenance",
]
