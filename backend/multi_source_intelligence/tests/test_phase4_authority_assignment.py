"""Tests for MSIL Phase 4 authority assignment and matrix application."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from multi_source_intelligence.models import (  # noqa: E402
    AuthorityClass,
    ClaimType,
    ContentClass,
    SourceType,
)
from multi_source_intelligence.services import (  # noqa: E402
    AuthorityAssignmentRequest,
    AuthorityAssignmentService,
)


def test_annual_report_narrative_assignment_uses_audited_issuer_authority() -> None:
    result = AuthorityAssignmentService().assign(
        {
            "source_type": "annual_report",
            "content_class": ContentClass.NARRATIVE_CLAIM,
        }
    )

    assert result.is_valid is True
    assert result.source_type == SourceType.ANNUAL_REPORT
    assert result.claim_type == ClaimType.DESCRIPTIVE
    assert result.authority_class == AuthorityClass.AUDITED_ISSUER
    assert result.creation_eligible is True


def test_annual_report_numeric_reference_can_disable_creation_rights() -> None:
    result = AuthorityAssignmentService().assign(
        AuthorityAssignmentRequest(
            source_type=SourceType.ANNUAL_REPORT,
            content_class=ContentClass.NUMERIC_CLAIM,
            numeric_reference_only=True,
        )
    )

    assert result.is_valid is True
    assert result.claim_type == ClaimType.AUDITED_FACT
    assert result.creation_eligible is False
    assert "numeric_reference_only" in result.applied_rules


@pytest.mark.parametrize(
    ("source_type", "expected_authority", "expected_claim_type"),
    (
        ("annual_report", AuthorityClass.AUDITED_ISSUER, ClaimType.DESCRIPTIVE),
        ("psx_announcement", AuthorityClass.EXCHANGE_OFFICIAL, ClaimType.CORPORATE_ACTION_FACT),
        ("company_payout", AuthorityClass.EXCHANGE_OFFICIAL, ClaimType.CORPORATE_ACTION_FACT),
        ("secp_notice", AuthorityClass.REGULATORY_INDEPENDENT, ClaimType.REGULATORY_COMPLIANCE),
        ("sector_source", AuthorityClass.SECTOR_AGGREGATE, ClaimType.SECTOR_CONTEXT),
        ("analyst_source", AuthorityClass.INDEPENDENT_OPINION, ClaimType.FORWARD_EXPECTATION),
        ("news_source", AuthorityClass.NEWS_MEDIA, ClaimType.DESCRIPTIVE),
        ("market_source", AuthorityClass.MARKET_REVEALED, ClaimType.SENTIMENT),
    ),
)
def test_future_ready_source_aliases_are_supported(
    source_type: str,
    expected_authority: AuthorityClass,
    expected_claim_type: ClaimType,
) -> None:
    content_class = (
        ContentClass.MARKET_OBSERVATION
        if source_type == "market_source"
        else ContentClass.NARRATIVE_CLAIM
    )

    result = AuthorityAssignmentService().assign(
        {"source_type": source_type, "content_class": content_class}
    )

    assert result.is_valid is True
    assert result.authority_class == expected_authority
    assert result.claim_type == expected_claim_type


def test_claim_type_scoped_rank_is_not_global() -> None:
    service = AuthorityAssignmentService()
    audited_fact = service.assign(
        {
            "source_type": "annual_report",
            "content_class": ContentClass.NUMERIC_CLAIM,
            "claim_type": ClaimType.AUDITED_FACT,
        }
    )
    forward_expectation = service.assign(
        {
            "source_type": "annual_report",
            "content_class": ContentClass.NARRATIVE_CLAIM,
            "claim_type": ClaimType.FORWARD_EXPECTATION,
        }
    )

    assert audited_fact.effective_rank == 0
    assert forward_expectation.effective_rank == 3


def test_news_and_market_sources_cannot_create_standalone_facts() -> None:
    service = AuthorityAssignmentService()
    news = service.assign(
        {"source_type": "news_source", "content_class": ContentClass.NARRATIVE_CLAIM}
    )
    market = service.assign(
        {"source_type": "market_source", "content_class": ContentClass.MARKET_OBSERVATION}
    )

    assert news.creation_eligible is False
    assert market.creation_eligible is False
    assert "standalone_fact_authority_disallowed" in news.applied_rules
    assert "standalone_fact_authority_disallowed" in market.applied_rules


def test_validation_rejects_invalid_creation_rights() -> None:
    result = AuthorityAssignmentService().validate_classification(
        source_type="news_source",
        content_class=ContentClass.NARRATIVE_CLAIM,
        claim_type=ClaimType.DESCRIPTIVE,
        authority_class=AuthorityClass.NEWS_MEDIA,
        creation_eligible=True,
    )

    assert result.is_valid is False
    assert any("creation_eligible" in item for item in result.invalid_mappings)


def test_validation_rejects_wrong_source_authority_mapping() -> None:
    result = AuthorityAssignmentService().validate_classification(
        source_type="annual_report",
        content_class=ContentClass.NARRATIVE_CLAIM,
        claim_type=ClaimType.DESCRIPTIVE,
        authority_class=AuthorityClass.NEWS_MEDIA,
        creation_eligible=False,
    )

    assert result.is_valid is False
    assert any("source_type default" in item for item in result.invalid_mappings)


def test_unsupported_source_type_is_rejected_by_request_model() -> None:
    with pytest.raises(ValidationError):
        AuthorityAssignmentRequest(
            source_type="unsupported_source",
            content_class=ContentClass.NARRATIVE_CLAIM,
        )


def test_to_classification_exports_signal_classification_model() -> None:
    result = AuthorityAssignmentService().assign(
        {
            "source_type": "psx_announcement",
            "content_class": ContentClass.CORPORATE_EVENT,
        }
    )
    classification = result.to_classification()

    assert classification.source_type == SourceType.PSX_ANNOUNCEMENTS
    assert classification.content_class == ContentClass.CORPORATE_EVENT
    assert classification.claim_type == ClaimType.CORPORATE_ACTION_FACT
    assert classification.authority_class == AuthorityClass.EXCHANGE_OFFICIAL


def test_authority_audit_reports_distributions_and_coverage() -> None:
    audit = AuthorityAssignmentService().audit_assignments(
        [
            {"source_type": "annual_report", "content_class": ContentClass.NARRATIVE_CLAIM},
            {"source_type": "market_source", "content_class": ContentClass.MARKET_OBSERVATION},
            {"source_type": "news_source", "content_class": ContentClass.NARRATIVE_CLAIM},
        ]
    )

    assert audit["signals_evaluated"] == 3
    assert audit["authority_distribution"]["audited_issuer"] == 1
    assert audit["authority_distribution"]["market_revealed"] == 1
    assert audit["authority_distribution"]["news_media"] == 1
    assert audit["creation_eligible_distribution"] == {"true": 1, "false": 2}
    assert audit["authority_coverage"]["source_type_coverage_percent"] == 100.0
