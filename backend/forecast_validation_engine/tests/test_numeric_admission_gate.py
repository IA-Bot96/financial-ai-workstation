"""Tests for FVE Phase 11 numeric admission governance."""

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    NumericEvidenceStatus,
    NumericRole,
)
from forecast_validation_engine.services import (  # noqa: E402
    NumericAdmissionGate,
    build_numeric_admission_audit,
)
from multi_source_intelligence.models import (  # noqa: E402
    AnnouncementProvenance,
    AuthorityClass,
    ClaimType,
    ContentClass,
    EntityResolutionResult,
    EntityScope,
    EntityType,
    Horizon,
    IntelligenceSignal,
    IntelligenceSignalClassification,
    IntelligenceSignalContent,
    IntelligenceSignalMetadata,
    PDFPageProvenance,
    PayoutProvenance,
    RegulatoryProvenance,
    ResolutionMethod,
    ReviewStatus,
    SourceSnapshotReference,
    SourceType,
    TimeBasis,
    URLSnapshotProvenance,
)
from shared.models.historical_series_integrity import (  # noqa: E402
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityResult,
    ScaleConsistencyResult,
    SeriesValueCandidateEvidence,
)


NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def test_annual_report_baseline_delegates_to_hsig_clean_status() -> None:
    signal = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        claim_type=ClaimType.AUDITED_FACT,
        metric_ref="revenue",
        value=1000,
        payload={"value_year": 2025, "source_report_year": 2025},
    )

    result = NumericAdmissionGate().evaluate(
        (signal,),
        historical_gate_result=_gate_result(_series_result("revenue", "clean")),
    )

    evidence = result.evidence[0]
    assert evidence.role == NumericRole.BASELINE
    assert evidence.status == NumericEvidenceStatus.ADMITTED
    assert evidence.can_be_baseline is True
    assert evidence.admission_decision.hsig_delegated is True
    assert evidence.integrity_verdict == "hsig_clean"


def test_annual_report_blocked_by_hsig_cannot_become_baseline() -> None:
    signal = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        claim_type=ClaimType.AUDITED_FACT,
        metric_ref="revenue",
        value=1000,
        payload={"value_year": 2025, "source_report_year": 2025},
    )

    result = NumericAdmissionGate().evaluate(
        (signal,),
        historical_gate_result=_gate_result(
            _series_result("revenue", "baseline_not_validatable")
        ),
    )

    evidence = result.evidence[0]
    assert evidence.role == NumericRole.BASELINE
    assert evidence.status == NumericEvidenceStatus.SKIPPED_BASELINE_NOT_VALIDATABLE
    assert evidence.can_be_baseline is False
    assert evidence.admitted is False


def test_reference_only_numeric_is_excluded_as_non_authoritative() -> None:
    signal = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        claim_type=ClaimType.DESCRIPTIVE,
        metric_ref="annual_report_numeric_reference:capacity",
        value="50 MW",
        creation_eligible=False,
        payload={
            "value_year": 2025,
            "source_report_year": 2025,
            "numeric_reference_only": True,
            "not_authoritative_value": True,
        },
    )

    result = NumericAdmissionGate().evaluate((signal,))

    evidence = result.evidence[0]
    assert evidence.role == NumericRole.NON_AUTHORITATIVE
    assert evidence.status == NumericEvidenceStatus.EXCLUDED_NON_AUTHORITATIVE
    assert evidence.can_be_baseline is False
    assert result.diagnostics["non_authoritative_exclusions"] == 1
    assert result.diagnostics["reference_only_exclusions"] == 1


def test_company_payout_is_event_fact_not_baseline() -> None:
    signal = _numeric_signal(
        source_type=SourceType.COMPANY_PAYOUTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        claim_type=ClaimType.CORPORATE_ACTION_FACT,
        metric_ref="payout_amount",
        value="15.00",
        payload={"numeric_reference_only": False, "fve_candidate": True},
    )

    result = NumericAdmissionGate().evaluate((signal,))

    evidence = result.evidence[0]
    assert evidence.role == NumericRole.EVENT_FACT
    assert evidence.status == NumericEvidenceStatus.ADMITTED
    assert evidence.can_be_baseline is False
    assert result.diagnostics["event_fact_counts"] == 1


def test_psx_disclosure_is_supporting_unless_guidance() -> None:
    supporting = _numeric_signal(
        source_type=SourceType.PSX_ANNOUNCEMENTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        claim_type=ClaimType.OFFICIAL_UNAUDITED_FACT,
        metric_ref="revenue",
        value=1000,
        payload={"numeric_reference_only": False},
    )
    guidance = _numeric_signal(
        source_type=SourceType.PSX_ANNOUNCEMENTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        claim_type=ClaimType.FORWARD_EXPECTATION,
        metric_ref="revenue_guidance",
        value=1200,
        payload={"guidance": True, "numeric_reference_only": False},
    )

    result = NumericAdmissionGate().evaluate((supporting, guidance))

    roles = {item.metric: item.role for item in result.evidence}
    assert roles["revenue"] == NumericRole.SUPPORTING
    assert roles["revenue_guidance"] == NumericRole.FORECAST_CONTEXT
    assert all(item.can_be_baseline is False for item in result.evidence)


def test_secp_numeric_is_revalidation_trigger_supporting_evidence() -> None:
    signal = _numeric_signal(
        source_type=SourceType.SECP_NOTICES,
        authority_class=AuthorityClass.REGULATORY_INDEPENDENT,
        claim_type=ClaimType.REGULATORY_COMPLIANCE,
        metric_ref="penalty_amount",
        value=100,
        payload={"numeric_reference_only": False},
    )

    result = NumericAdmissionGate().evaluate((signal,))

    evidence = result.evidence[0]
    assert evidence.role == NumericRole.SUPPORTING
    assert evidence.status == NumericEvidenceStatus.REVALIDATION_TRIGGER
    assert result.diagnostics["revalidation_trigger_counts"] == 1


def test_analyst_number_is_forecast_context_never_baseline() -> None:
    signal = _numeric_signal(
        source_type=SourceType.ANALYSIS_REPORTS,
        authority_class=AuthorityClass.INDEPENDENT_OPINION,
        claim_type=ClaimType.FORWARD_EXPECTATION,
        metric_ref="target_eps",
        value=60,
        payload={"analyst_expectation": True, "numeric_reference_only": False},
    )

    result = NumericAdmissionGate().evaluate((signal,))

    evidence = result.evidence[0]
    assert evidence.role == NumericRole.FORECAST_CONTEXT
    assert evidence.can_be_baseline is False
    assert result.diagnostics["analyst_baseline_admissions"] == 0


def test_numeric_admission_audit_reports_governance_counts() -> None:
    reference = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        claim_type=ClaimType.DESCRIPTIVE,
        metric_ref="annual_report_numeric_reference:capacity",
        value=50,
        creation_eligible=False,
        payload={"numeric_reference_only": True, "not_authoritative_value": True},
    )
    payout = _numeric_signal(
        source_type=SourceType.COMPANY_PAYOUTS,
        authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
        claim_type=ClaimType.CORPORATE_ACTION_FACT,
        metric_ref="payout_amount",
        value=15,
        payload={"numeric_reference_only": False},
    )

    result = NumericAdmissionGate().evaluate((reference, payout))
    audit = build_numeric_admission_audit(result)

    assert audit["numeric_claims_processed"] == 2
    assert audit["role_distribution"]["non_authoritative"] == 1
    assert audit["role_distribution"]["event_fact"] == 1
    assert audit["non_authoritative_exclusions"] == 1
    assert audit["external_baseline_admissions"] == 0


def _series_result(metric: str, status: str) -> HistoricalSeriesIntegrityResult:
    return HistoricalSeriesIntegrityResult(
        metric=metric,
        status=status,  # type: ignore[arg-type]
        value_years=[2025] if status != "missing" else [],
        selected_series=[_candidate(metric)] if status != "missing" else [],
        blocking_issues=[],
        warning_issues=[],
        candidate_spread_by_year=[],
        yoy_scale_issues=[],
        source_policy_violations=[],
        scale_result=ScaleConsistencyResult(
            status="fail" if status == "baseline_not_validatable" else "pass",
            max_candidate_spread=None,
            max_yoy_magnitude_ratio=None,
            blocking_reasons=[],
            warning_reasons=[],
        ),
        evidence=[],
        confidence=0.95,
        validation_readiness=status in {"clean", "clean_with_warning"},
    )


def _candidate(metric: str) -> SeriesValueCandidateEvidence:
    return SeriesValueCandidateEvidence(
        metric=metric,
        value_year=2025,
        value=1000,
        source_report_year=2025,
        page_number=10,
        table_type="income_statement",
        source_class="primary_statement",
        statement_scope="unknown",
        normalization_confidence=0.95,
        source_confidence=0.95,
        original_metric=metric,
        requires_review=False,
        is_currently_selected=True,
    )


def _gate_result(
    *series_results: HistoricalSeriesIntegrityResult,
) -> HistoricalSeriesIntegrityGateResult:
    counts = {
        "clean": 0,
        "clean_with_warning": 0,
        "baseline_not_validatable": 0,
        "missing": 0,
    }
    metrics_by_status = {
        "clean": [],
        "clean_with_warning": [],
        "baseline_not_validatable": [],
        "missing": [],
    }
    for result in series_results:
        counts[result.status] += 1
        metrics_by_status[result.status].append(result.metric)
    return HistoricalSeriesIntegrityGateResult(
        metrics_evaluated=[result.metric for result in series_results],
        series_results=list(series_results),
        overall_status=(
            "baseline_not_validatable"
            if counts["baseline_not_validatable"]
            else "clean_with_warning"
            if counts["clean_with_warning"]
            else "missing"
            if counts["missing"]
            else "clean"
        ),
        status_counts=counts,
        metrics_by_status=metrics_by_status,
        clean_metrics=metrics_by_status["clean"],
        warning_metrics=metrics_by_status["clean_with_warning"],
        blocked_metrics=metrics_by_status["baseline_not_validatable"],
        missing_metrics=metrics_by_status["missing"],
        critical_issue_count=0,
        warning_count=0,
    )


def _numeric_signal(
    *,
    source_type: SourceType,
    authority_class: AuthorityClass,
    claim_type: ClaimType,
    metric_ref: str,
    value: float | int | str,
    payload: dict[str, object],
    creation_eligible: bool = True,
) -> IntelligenceSignal:
    record_id = f"{source_type.value}:{metric_ref}"
    return IntelligenceSignal(
        entity_ref="lucky_cement",
        entity_scope=EntityScope.COMPANY,
        entity_resolution=_resolution(),
        content=IntelligenceSignalContent(
            content_class=ContentClass.NUMERIC_CLAIM,
            identity_key=f"{record_id}:numeric",
            metric_ref=metric_ref,
            value=value,
            unit="PKR",
            payload={"record_id": record_id, **payload},
        ),
        classification=IntelligenceSignalClassification(
            content_class=ContentClass.NUMERIC_CLAIM,
            source_type=source_type,
            claim_type=claim_type,
            authority_class=authority_class,
            creation_eligible=creation_eligible,
            mapping_confidence=1.0,
            authority_confidence=1.0,
        ),
        metadata=IntelligenceSignalMetadata(
            observation_time=NOW,
            subject_period="FY2025",
            time_basis=TimeBasis.CALENDAR,
            horizon=Horizon.CURRENT,
            source_independent_of_issuer=source_type
            in {SourceType.SECP_NOTICES, SourceType.ANALYSIS_REPORTS},
            verified=True,
            source_record_id=record_id,
            source_lineage_hooks=(record_id,),
        ),
        provenance=_provenance(source_type, record_id),
    )


def _resolution() -> EntityResolutionResult:
    return EntityResolutionResult(
        raw_identifier="LUCK",
        normalized_identifier="luck",
        method=ResolutionMethod.EXACT,
        confidence=1.0,
        review_status=ReviewStatus.RESOLVED,
        resolved_entity_ref="lucky_cement",
        resolved_entity_type=EntityType.COMPANY,
        review_required=False,
    )


def _snapshot(source_type: SourceType, record_id: str) -> SourceSnapshotReference:
    return SourceSnapshotReference(
        snapshot_id=f"snap_{record_id}",
        source_type=source_type,
        capture_timestamp=NOW,
        source_hash=f"sha256:{record_id}",
        snapshot_uri=f"snapshot://{record_id}",
    )


def _provenance(source_type: SourceType, record_id: str):
    if source_type == SourceType.ANNUAL_REPORT:
        return PDFPageProvenance(
            workbook_fingerprint="wf_lucky_2025",
            page_number=10,
            report_reference="lucky-2025",
            source_report_year=2025,
            source_section="Financial Review",
        )
    if source_type == SourceType.PSX_ANNOUNCEMENTS:
        return AnnouncementProvenance(
            announcement_id=record_id,
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
        )
    if source_type == SourceType.COMPANY_PAYOUTS:
        return PayoutProvenance(
            payout_id=record_id,
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
        )
    if source_type == SourceType.SECP_NOTICES:
        return RegulatoryProvenance(
            notice_id=record_id,
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
        )
    if source_type == SourceType.ANALYSIS_REPORTS:
        return URLSnapshotProvenance(
            source_type=source_type,
            url=f"https://analyst.example.test/{record_id}",
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
        )
    raise AssertionError(f"Unsupported test source_type: {source_type}")
