"""Tests for MSIL Phase 8C Stage 1 FVE evidence consumption."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    ForecastContextPlausibilityStatus,
    ForecastInput,
    MSILNumericInfluence,
    NumericRole,
    ValidationOutcome,
)
from forecast_validation_engine.services import (  # noqa: E402
    ForecastValidationOrchestrator,
    MSILNumericEvidenceConsumer,
    NumericAdmissionGate,
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
    ResolutionMethod,
    ReviewStatus,
    SourceSnapshotReference,
    SourceType,
    TimeBasis,
    URLSnapshotProvenance,
)
from shared.models.financial_year_consolidation import (  # noqa: E402
    FinancialYearConsolidationResult,
)
from shared.models.historical_series_integrity import (  # noqa: E402
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityResult,
    ScaleConsistencyResult,
    SeriesValueCandidateEvidence,
)
from shared.models.metric_value import MetricValue  # noqa: E402


NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def test_stage1_consumes_supporting_and_event_fact_as_report_only() -> None:
    gate_result = NumericAdmissionGate().evaluate(
        (
            _numeric_signal(
                source_type=SourceType.PSX_ANNOUNCEMENTS,
                authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
                claim_type=ClaimType.OFFICIAL_UNAUDITED_FACT,
                metric_ref="revenue",
                value=1200,
                payload={"numeric_reference_only": False},
            ),
            _numeric_signal(
                source_type=SourceType.COMPANY_PAYOUTS,
                authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
                claim_type=ClaimType.CORPORATE_ACTION_FACT,
                metric_ref="payout_amount",
                value=15,
                payload={"numeric_reference_only": False},
            ),
        )
    )

    result = MSILNumericEvidenceConsumer().consume(gate_result)

    assert result.supporting_evidence_consumed == 1
    assert result.event_facts_consumed == 1
    assert len(result.validation_evidence) == 2
    assert result.baseline_modifications == 0
    assert result.calculations_modified == 0
    assert result.hsig_bypass_attempts == 0
    assert all(
        evidence.provenance["baseline_usage"] == "forbidden"
        and evidence.provenance["calculation_usage"] == "forbidden"
        for evidence in result.validation_evidence
    )


def test_stage1_surfaces_divergence_without_resolution_or_winning_source() -> None:
    gate_result = NumericAdmissionGate().evaluate(
        (
            _numeric_signal(
                source_type=SourceType.PSX_ANNOUNCEMENTS,
                authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
                claim_type=ClaimType.OFFICIAL_UNAUDITED_FACT,
                metric_ref="cash_dividend",
                value=15,
                payload={"numeric_reference_only": False},
            ),
        )
    )
    divergent = gate_result.evidence[0].model_copy(
        update={"divergence_refs": ("div_payout_conflict",)}
    )

    result = MSILNumericEvidenceConsumer().consume((divergent,))

    assert result.divergences_surfaced == 1
    assert result.confidence_adjustments[0].influence == (
        MSILNumericInfluence.DECREASE_CONFIDENCE
    )
    assert result.confidence_adjustments[0].adjustment < 0
    assert "div_payout_conflict" in result.confidence_adjustments[0].divergence_refs
    assert result.ownership_boundaries["fve_resolves_divergence"] is False
    assert result.ownership_boundaries["fve_selects_winning_source"] is False
    assert any("did not resolve" in warning for warning in result.warnings)


def test_stage1_corroborated_supporting_evidence_adjusts_confidence_only() -> None:
    gate_result = NumericAdmissionGate().evaluate(
        (
            _numeric_signal(
                source_type=SourceType.PSX_ANNOUNCEMENTS,
                authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
                claim_type=ClaimType.OFFICIAL_UNAUDITED_FACT,
                metric_ref="revenue",
                value=1200,
                payload={"numeric_reference_only": False},
            ),
        )
    )
    evidence = gate_result.evidence[0]
    corroborated = evidence.model_copy(
        update={
            "metadata": {
                **evidence.metadata,
                "corroboration_refs": ("cor_revenue_2025",),
            }
        }
    )

    result = MSILNumericEvidenceConsumer().consume((corroborated,))

    assert result.confidence_adjustments[0].influence == (
        MSILNumericInfluence.INCREASE_CONFIDENCE
    )
    assert result.confidence_adjustments[0].adjustment > 0
    assert result.validation_evidence[0].calculations["calculation_usage"] == "forbidden"
    assert result.baseline_modifications == 0


def test_stage2_consumes_forecast_context_for_plausibility_only() -> None:
    analyst = _numeric_signal(
        source_type=SourceType.ANALYSIS_REPORTS,
        authority_class=AuthorityClass.INDEPENDENT_OPINION,
        claim_type=ClaimType.FORWARD_EXPECTATION,
        metric_ref="revenue",
        value=1300,
        payload={
            "numeric_reference_only": False,
            "analyst_expectation": True,
            "value_year": 2026,
        },
    )
    annual_baseline = _numeric_signal(
        source_type=SourceType.ANNUAL_REPORT,
        authority_class=AuthorityClass.AUDITED_ISSUER,
        claim_type=ClaimType.AUDITED_FACT,
        metric_ref="earnings_per_share",
        value=52.5,
        payload={"value_year": 2025, "source_report_year": 2025},
    )
    gate_result = NumericAdmissionGate().evaluate(
        (analyst, annual_baseline),
        historical_gate_result=_gate_result(
            _series_result("earnings_per_share", "clean")
        ),
    )

    result = MSILNumericEvidenceConsumer().consume(
        gate_result,
        forecast_inputs=(
            ForecastInput(metric="revenue", forecast_year=2026, value=1325),
        ),
    )

    assert result.forecast_context_consumed == 1
    assert result.forecast_context_ignored == 0
    assert result.baseline_evidence_ignored == 1
    assert result.supporting_evidence_consumed == 0
    assert result.event_facts_consumed == 0
    assert len(result.plausibility_assessments) == 1
    assert result.plausibility_assessments[0].status == (
        ForecastContextPlausibilityStatus.PLAUSIBLE
    )
    assert result.plausibility_assessments[0].governance_boundary == (
        "plausibility_only"
    )
    assert result.confidence_adjustments[0].applies_to == (
        "plausibility_confidence_only"
    )
    assert result.validation_evidence[0].provenance["historical_validation_usage"] == (
        "forbidden"
    )
    assert result.hsig_bypass_attempts == 0


def test_stage2_forecast_context_divergence_is_surfaced_not_resolved() -> None:
    gate_result = NumericAdmissionGate().evaluate(
        (
            _numeric_signal(
                source_type=SourceType.PSX_ANNOUNCEMENTS,
                authority_class=AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                claim_type=ClaimType.FORWARD_EXPECTATION,
                metric_ref="revenue",
                value=1600,
                payload={
                    "numeric_reference_only": False,
                    "guidance": True,
                    "value_year": 2026,
                },
            ),
        )
    )
    evidence = gate_result.evidence[0]
    divergent = evidence.model_copy(
        update={"divergence_refs": ("div_guidance_vs_consensus",)}
    )

    result = MSILNumericEvidenceConsumer().consume(
        (divergent,),
        forecast_inputs=(
            ForecastInput(metric="revenue", forecast_year=2026, value=700),
        ),
    )

    assessment = result.plausibility_assessments[0]
    assert result.forecast_context_consumed == 1
    assert result.divergences_surfaced == 1
    assert assessment.status == (
        ForecastContextPlausibilityStatus.IMPLAUSIBLE_REQUIRES_REVIEW
    )
    assert assessment.authority_ceiling == 0.85
    assert assessment.benchmark_values[0].authority_label == "management_guidance"
    assert result.confidence_adjustments[0].influence == (
        MSILNumericInfluence.DECREASE_CONFIDENCE
    )
    assert result.ownership_boundaries["fve_resolves_divergence"] is False
    assert result.ownership_boundaries["forecast_context_influences_hsig"] is False
    assert any("did not resolve" in warning for warning in result.warnings)


def test_orchestrator_attaches_msil_reporting_without_modifying_gate() -> None:
    numeric_gate_result = NumericAdmissionGate().evaluate(
        (
            _numeric_signal(
                source_type=SourceType.PSX_ANNOUNCEMENTS,
                authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
                claim_type=ClaimType.OFFICIAL_UNAUDITED_FACT,
                metric_ref="revenue",
                value=1200,
                payload={"numeric_reference_only": False},
            ),
            _numeric_signal(
                source_type=SourceType.COMPANY_PAYOUTS,
                authority_class=AuthorityClass.EXCHANGE_OFFICIAL,
                claim_type=ClaimType.CORPORATE_ACTION_FACT,
                metric_ref="payout_amount",
                value=15,
                payload={"numeric_reference_only": False},
            ),
        )
    )

    result = ForecastValidationOrchestrator().run(
        consolidation_result=FinancialYearConsolidationResult(
            metric_values=[
                _metric_value("earnings_per_share", 2024, 48.0),
                _metric_value("earnings_per_share", 2025, 52.5),
            ]
        ),
        forecast_inputs=(
            ForecastInput(
                metric="earnings_per_share",
                forecast_year=2026,
                value=55.0,
            ),
        ),
        validation_id="fv_msil_stage1_test",
        metrics=("earnings_per_share",),
        numeric_admission_result=numeric_gate_result,
    )

    assert result.historical_gate_result.status_counts["clean"] == 1
    assert result.scorecard.overall_outcome == ValidationOutcome.PASS
    assert any(
        evidence.evidence_id.startswith("msil_numeric:")
        for evidence in result.evidence
    )
    assert result.provenance["msil_phase8c_stage1"]["supporting_evidence_consumed"] == 1
    assert result.provenance["msil_phase8c_stage1"]["event_facts_consumed"] == 1
    assert result.provenance["msil_phase8c_stage1"]["baseline_modifications"] == 0
    assert result.provenance["msil_phase8c_stage1"]["calculations_modified"] == 0
    assert "RevenueValidationService" in result.scorecard.deferred_categories


def test_orchestrator_attaches_forecast_context_plausibility_without_rule_redesign() -> None:
    numeric_gate_result = NumericAdmissionGate().evaluate(
        (
            _numeric_signal(
                source_type=SourceType.PSX_ANNOUNCEMENTS,
                authority_class=AuthorityClass.OFFICIAL_ISSUER_UNAUDITED,
                claim_type=ClaimType.FORWARD_EXPECTATION,
                metric_ref="revenue",
                value=1200,
                payload={
                    "numeric_reference_only": False,
                    "guidance": True,
                    "value_year": 2026,
                },
            ),
        )
    )

    result = ForecastValidationOrchestrator().run(
        consolidation_result=FinancialYearConsolidationResult(
            metric_values=[
                _metric_value("earnings_per_share", 2024, 48.0),
                _metric_value("earnings_per_share", 2025, 52.5),
            ]
        ),
        forecast_inputs=(
            ForecastInput(metric="revenue", forecast_year=2026, value=1250),
        ),
        validation_id="fv_msil_stage2_test",
        metrics=("earnings_per_share",),
        numeric_admission_result=numeric_gate_result,
    )

    stage2 = result.provenance["msil_phase8c_stage2"]
    assert stage2["forecast_context_consumed"] == 1
    assert stage2["baseline_modifications"] == 0
    assert stage2["calculations_modified"] == 0
    assert stage2["plausibility_assessments"][0]["status"] == "plausible"
    assert result.scorecard.overall_outcome == ValidationOutcome.PASS


def _metric_value(metric: str, year: int, value: float) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=10,
        table_type="income_statement",
    )


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
            status="pass",
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
        overall_status="clean",
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
            creation_eligible=True,
            mapping_confidence=1.0,
            authority_confidence=1.0,
        ),
        metadata=IntelligenceSignalMetadata(
            observation_time=NOW,
            subject_period="FY2025",
            time_basis=TimeBasis.CALENDAR,
            horizon=Horizon.CURRENT,
            source_independent_of_issuer=source_type == SourceType.ANALYSIS_REPORTS,
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
    if source_type == SourceType.ANALYSIS_REPORTS:
        return URLSnapshotProvenance(
            source_type=source_type,
            url=f"https://analyst.example.test/{record_id}",
            snapshot_ref=_snapshot(source_type, record_id),
            retrieved_at=NOW,
        )
    raise AssertionError(f"Unsupported test source_type: {source_type}")
