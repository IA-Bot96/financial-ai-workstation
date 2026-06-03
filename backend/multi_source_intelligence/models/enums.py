"""Frozen MSIL Phase 0 enum registry."""

from __future__ import annotations

from enum import Enum


class EntityType(str, Enum):
    """Canonical entity registry record type."""

    COMPANY = "company"
    SECURITY = "security"
    FUTURES_INSTRUMENT = "futures_instrument"
    SECTOR = "sector"
    PERSON = "person"
    SOURCE = "source"
    PERIOD = "period"


class EntityScope(str, Enum):
    """Scope attached to an intelligence signal."""

    COMPANY = "company"
    SECURITY = "security"
    SECTOR = "sector"
    MARKET = "market"
    PERSON = "person"


class AliasType(str, Enum):
    """Entity alias variants allowed in the registry."""

    TICKER = "ticker"
    SECP_REG_NO = "secp_reg_no"
    LEGAL_NAME = "legal_name"
    NAME_VARIANT = "name_variant"
    ISIN = "isin"


class RelationshipType(str, Enum):
    """Registry entity relationship type."""

    SECURITY_OF = "security_of"
    FUTURES_ON = "futures_on"
    PERSON_OF = "person_of"
    MEMBER_OF_SECTOR = "member_of_sector"
    PARENT_OF = "parent_of"
    SUBSIDIARY_OF = "subsidiary_of"


class EntityStatus(str, Enum):
    """Lifecycle status for canonical entity records."""

    ACTIVE = "active"
    MERGED = "merged"
    DEPRECATED = "deprecated"


class ResolutionMethod(str, Enum):
    """Deterministic entity-resolution tier."""

    EXACT = "exact"
    ALIAS = "alias"
    FUZZY = "fuzzy"
    UNRESOLVED = "unresolved"


class ReviewStatus(str, Enum):
    """Entity-resolution review state."""

    RESOLVED = "resolved"
    REVIEW = "review"
    QUARANTINED = "quarantined"


class ContentClass(str, Enum):
    """MSIL routing class for incoming evidence."""

    NUMERIC_CLAIM = "numeric_claim"
    NARRATIVE_CLAIM = "narrative_claim"
    CORPORATE_EVENT = "corporate_event"
    MARKET_OBSERVATION = "market_observation"


class SourceType(str, Enum):
    """All frozen MSIL source families."""

    ANNUAL_REPORT = "annual_report"
    PSX_ANNOUNCEMENTS = "psx_announcements"
    SECP_NOTICES = "secp_notices"
    COMPANY_PAYOUTS = "company_payouts"
    MARKET_WATCH = "market_watch"
    FUTURES_MARKET_WATCH = "futures_market_watch"
    SECTOR_SUMMARY = "sector_summary"
    COMPANY_OVERVIEW = "company_overview"
    ANALYSIS_REPORTS = "analysis_reports"
    NEWS_SOURCES = "news_sources"


class AuthorityClass(str, Enum):
    """Source authority class in the claim-type-scoped matrix."""

    REGULATORY_INDEPENDENT = "regulatory_independent"
    EXCHANGE_OFFICIAL = "exchange_official"
    AUDITED_ISSUER = "audited_issuer"
    OFFICIAL_ISSUER_UNAUDITED = "official_issuer_unaudited"
    INDEPENDENT_OPINION = "independent_opinion"
    SECTOR_AGGREGATE = "sector_aggregate"
    MARKET_REVEALED = "market_revealed"
    NEWS_MEDIA = "news_media"


class ClaimType(str, Enum):
    """Claim type used to determine effective authority."""

    REGULATORY_COMPLIANCE = "regulatory_compliance"
    CORPORATE_ACTION_FACT = "corporate_action_fact"
    AUDITED_FACT = "audited_fact"
    OFFICIAL_UNAUDITED_FACT = "official_unaudited_fact"
    FORWARD_EXPECTATION = "forward_expectation"
    DESCRIPTIVE = "descriptive"
    SENTIMENT = "sentiment"
    SECTOR_CONTEXT = "sector_context"


class TimeBasis(str, Enum):
    """Time basis used by evidence records."""

    FISCAL = "fiscal"
    CALENDAR = "calendar"
    CONTINUOUS = "continuous"
    STATIC = "static"


class Horizon(str, Enum):
    """Temporal horizon represented by a claim."""

    HISTORICAL = "historical"
    CURRENT = "current"
    FORWARD = "forward"


class ProvenanceType(str, Enum):
    """Frozen provenance discriminator values."""

    PDF_PAGE = "PDF_PAGE"
    ANNOUNCEMENT_REF = "ANNOUNCEMENT_REF"
    REGULATORY_REF = "REGULATORY_REF"
    PAYOUT_REF = "PAYOUT_REF"
    MARKET_DATA_REF = "MARKET_DATA_REF"
    FUTURES_REF = "FUTURES_REF"
    SECTOR_REF = "SECTOR_REF"
    URL_SNAPSHOT = "URL_SNAPSHOT"
    NEWS_REF = "NEWS_REF"
    NONE = "NONE"


class EventType(str, Enum):
    """Timeline corporate event type."""

    DIVIDEND_DECLARED = "dividend_declared"
    DIVIDEND_PAID = "dividend_paid"
    RESULTS_ANNOUNCED = "results_announced"
    BOARD_CHANGE = "board_change"
    CAPACITY_COMMISSIONED = "capacity_commissioned"
    RIGHTS_ISSUE = "rights_issue"
    BONUS_ISSUE = "bonus_issue"
    SECP_ACTION = "secp_action"
    RATING_CHANGE = "rating_change"


class DivergenceType(str, Enum):
    """MSIL divergence category."""

    NARRATIVE_VS_NARRATIVE = "narrative_vs_narrative"
    NARRATIVE_VS_NUMBERS = "narrative_vs_numbers"
    FACT_VS_FACT = "fact_vs_fact"
    SENTIMENT_VS_FUNDAMENTALS = "sentiment_vs_fundamentals"


class DivergenceStatus(str, Enum):
    """MSIL may surface divergences, never resolve them."""

    SURFACED = "surfaced"


__all__ = [
    "AliasType",
    "AuthorityClass",
    "ClaimType",
    "ContentClass",
    "DivergenceStatus",
    "DivergenceType",
    "EntityScope",
    "EntityStatus",
    "EntityType",
    "EventType",
    "Horizon",
    "ProvenanceType",
    "RelationshipType",
    "ResolutionMethod",
    "ReviewStatus",
    "SourceType",
    "TimeBasis",
]
