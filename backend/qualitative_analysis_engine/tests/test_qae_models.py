"""Tests for QAE Phase 1 model contracts."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from qualitative_analysis_engine.models import (  # noqa: E402
    CategoryCoverage,
    CategoryMateriality,
    CategoryStatus,
    ConfidenceDistribution,
    DivergenceReference,
    DivergenceSummary,
    FVEHandoffPayload,
    FVEHandoffTheme,
    QualitativeCategoryResult,
    QualitativeRunResult,
    QualitativeSignal,
    QualitativeTheme,
    RunCoverageSummary,
    RunMaterialitySummary,
    RunStatus,
    RunVersions,
    SourceSnapshot,
    ThemeEvidence,
    ThemeReference,
    ThemeSalience,
    UnmappedSummary,
)


def _signal_payload() -> dict:
    return {
        "signal_id": "lucky:annual_report:84:energy_transition:2025",
        "entity_ref": "lucky_cement",
        "entity_scope": "company",
        "source_type": "annual_report",
        "taxonomy_version": "1.0.0",
        "authority_matrix_version": "1.0.0",
        "claim": "The company expanded renewable energy generation.",
        "raw_excerpt": "Solar generation capacity increased during the year.",
        "is_quantified": False,
        "specificity": "named",
        "category_ref": "esg",
        "theme_ref": "energy_transition",
        "subtheme_ref": None,
        "mapping_method": "alias",
        "mapping_confidence": 0.9,
        "routing_basis": "section_prior",
        "unmapped": False,
        "claim_type": "audited_fact",
        "authority_class": "audited_issuer",
        "source_independent_of_issuer": False,
        "verified": True,
        "trust_prior": 0.9,
        "source_lineage": [],
        "derived_from": [],
        "observation_time": 2025,
        "subject_period": 2025,
        "time_basis": "fiscal",
        "horizon": "historical",
        "supersedes": [],
        "superseded_by": [],
        "provenance": {
            "provenance_type": "PDF_PAGE",
            "page_number": 84,
            "source_section": "Sustainability",
            "workbook_fingerprint": "fp_lucky_2025",
        },
        "snapshot_ref": None,
        "retrieved_at": None,
        "extraction_confidence": 0.86,
        "structure_confidence": 0.93,
        "signal_confidence": 0.86,
        "creation_eligible": True,
        "theme_role": None,
    }


def _signal() -> QualitativeSignal:
    return QualitativeSignal.model_validate(_signal_payload())


def _theme_evidence() -> ThemeEvidence:
    return ThemeEvidence(
        evidence_id="ev_energy_transition",
        theme_ref="energy_transition",
        signal_ids=("lucky:annual_report:84:energy_transition:2025",),
        signal_claims={
            "lucky:annual_report:84:energy_transition:2025": (
                "The company expanded renewable energy generation."
            )
        },
        signal_roles={"lucky:annual_report:84:energy_transition:2025": "creates"},
        provenance_refs=("pdf:84",),
        observation_times={"lucky:annual_report:84:energy_transition:2025": 2025},
        subject_periods={"lucky:annual_report:84:energy_transition:2025": 2025},
        time_basis_by_signal={
            "lucky:annual_report:84:energy_transition:2025": "fiscal"
        },
        horizon_by_signal={
            "lucky:annual_report:84:energy_transition:2025": "historical"
        },
        authority_class_by_signal={
            "lucky:annual_report:84:energy_transition:2025": "audited_issuer"
        },
        claim_type_by_signal={
            "lucky:annual_report:84:energy_transition:2025": "audited_fact"
        },
        mapping_method_by_signal={
            "lucky:annual_report:84:energy_transition:2025": "alias"
        },
        source_mix={"annual_report": 1},
        independent_origins=("annual_report",),
        duplicate_count=1,
        salience="low_salience",
        low_salience=True,
    )


def _theme() -> QualitativeTheme:
    signal_id = "lucky:annual_report:84:energy_transition:2025"
    return QualitativeTheme(
        theme_reference=ThemeReference(
            entity_ref="lucky_cement",
            entity_scope="company",
            theme_ref="energy_transition",
            taxonomy_version="1.0.0",
        ),
        category_ref="esg",
        secondary_categories=("strategy",),
        signal_ids=(signal_id,),
        created_by_signal_ids=(signal_id,),
        evidence=_theme_evidence(),
        source_mix={"annual_report": 1},
        salience="low_salience",
        theme_confidence=0.86,
        evidence_weight=0.55,
        materiality=0.7,
        low_salience=True,
        taxonomy_version="1.0.0",
        authority_matrix_version="1.0.0",
    )


def _category_result() -> QualitativeCategoryResult:
    return QualitativeCategoryResult(
        category_ref="esg",
        status="ANALYZED_WITH_WARNING",
        owned_themes=(_theme(),),
        theme_count_by_salience={ThemeSalience.LOW_SALIENCE: 1},
        coverage=CategoryCoverage(
            mapped=1,
            raw=1,
            unmapped_rate=0.0,
            source_mix={"annual_report": 1},
            expected_sections_present=("Sustainability",),
        ),
        category_confidence=ConfidenceDistribution(bucket_0_7_to_0_9=1),
        category_materiality=CategoryMateriality(
            max_materiality=0.7,
            aggregation_method="max",
            top_theme_refs=("energy_transition",),
        ),
        evidence_refs=("ev_energy_transition",),
        taxonomy_version="1.0.0",
        authority_matrix_version="1.0.0",
    )


def test_qualitative_signal_serializes_and_deserializes_pdf_provenance() -> None:
    signal = _signal()
    payload = signal.model_dump(mode="json")

    restored = QualitativeSignal.model_validate(payload)

    assert restored == signal
    assert payload["provenance"]["provenance_type"] == "PDF_PAGE"
    assert payload["signal_confidence"] == 0.86


def test_signal_confidence_must_match_contract_floor() -> None:
    payload = _signal_payload()
    payload["signal_confidence"] = 0.9

    with pytest.raises(ValidationError, match="signal_confidence"):
        QualitativeSignal.model_validate(payload)


def test_unmapped_signal_cannot_carry_theme_ref() -> None:
    payload = _signal_payload()
    payload["unmapped"] = True
    payload["mapping_method"] = "unmapped"

    with pytest.raises(ValidationError, match="theme_ref"):
        QualitativeSignal.model_validate(payload)


def test_external_signals_require_snapshot_and_retrieval_time() -> None:
    payload = _signal_payload()
    payload.update(
        {
            "signal_id": "analyst:energy_transition:2025",
            "source_type": "analysis_reports",
            "source_independent_of_issuer": True,
            "authority_class": "independent_opinion",
            "claim_type": "forward_expectation",
            "routing_basis": "adapter_signal",
            "observation_time": "2025-09-30",
            "subject_period": "2026",
            "time_basis": "calendar",
            "horizon": "forward",
            "provenance": {
                "provenance_type": "URL_SNAPSHOT",
                "url": "https://example.test/report",
                "publisher": "Example Research",
                "document_date": "2025-09-30",
            },
        }
    )

    with pytest.raises(ValidationError, match="snapshot_ref"):
        QualitativeSignal.model_validate(payload)

    payload["snapshot_ref"] = "sha256:abc"
    payload["retrieved_at"] = datetime(2026, 6, 3, tzinfo=timezone.utc)

    signal = QualitativeSignal.model_validate(payload)

    assert signal.snapshot_ref == "sha256:abc"


def test_attach_only_sources_cannot_create_themes() -> None:
    payload = _signal_payload()
    payload.update(
        {
            "signal_id": "overview:energy_transition",
            "source_type": "company_overview",
            "authority_class": "issuer_descriptive",
            "claim_type": "descriptive",
            "time_basis": "static",
            "subject_period": None,
            "provenance": {
                "provenance_type": "URL_SNAPSHOT",
                "url": "https://example.test/company",
                "publisher": "Company Website",
                "document_date": "2026-01-01",
            },
            "snapshot_ref": "sha256:def",
            "retrieved_at": datetime(2026, 6, 3, tzinfo=timezone.utc),
            "creation_eligible": True,
        }
    )

    with pytest.raises(ValidationError, match="attach-only"):
        QualitativeSignal.model_validate(payload)


def test_theme_evidence_and_theme_roundtrip() -> None:
    theme = _theme()
    restored = QualitativeTheme.model_validate(theme.model_dump(mode="json"))

    assert restored == theme
    assert restored.evidence.low_salience is True
    assert restored.created_by_signal_ids == restored.signal_ids


def test_single_signal_theme_must_be_low_salience() -> None:
    data = _theme().model_dump(mode="json")
    data["low_salience"] = False

    with pytest.raises(ValidationError, match="low_salience"):
        QualitativeTheme.model_validate(data)


def test_divergence_cannot_be_auto_resolved() -> None:
    with pytest.raises(ValidationError, match="auto-resolved"):
        DivergenceReference(
            divergence_id="div1",
            divergence_type="narrative_vs_narrative",
            theme_ref="demand_outlook",
            category_ref="outlook",
            signal_ids=("s1", "s2"),
            side_a_signal_id="s1",
            side_b_signal_id="s2",
            side_a_authority_class="audited_issuer",
            side_b_authority_class="independent_opinion",
            summary="Management expects demand growth while analyst expects decline.",
            auto_resolved=True,
        )


def test_skipped_category_requires_skip_reason_and_evidence() -> None:
    with pytest.raises(ValidationError, match="skip_reason"):
        QualitativeCategoryResult(
            category_ref="governance",
            status="SKIPPED_INSUFFICIENT_COVERAGE",
            coverage=CategoryCoverage(mapped=0, raw=0, unmapped_rate=0.0),
            category_confidence=ConfidenceDistribution(),
            category_materiality=CategoryMateriality(aggregation_method="max"),
            taxonomy_version="1.0.0",
            authority_matrix_version="1.0.0",
        )


def test_category_result_serialization_roundtrip() -> None:
    category = _category_result()
    restored = QualitativeCategoryResult.model_validate(
        category.model_dump(mode="json")
    )

    assert restored == category
    assert restored.theme_count_by_salience[ThemeSalience.LOW_SALIENCE] == 1


def test_fve_handoff_payload_is_narrative_only() -> None:
    with pytest.raises(ValidationError, match="narrative_only"):
        FVEHandoffTheme(
            theme_ref="energy_transition",
            category_ref="esg",
            horizon="forward",
            materiality=0.7,
            confidence=0.8,
            narrative_only=False,
            entity_ref="lucky_cement",
            taxonomy_version="1.0.0",
        )


def test_qualitative_run_result_roundtrip() -> None:
    category = _category_result()
    handoff_theme = FVEHandoffTheme(
        theme_ref="energy_transition",
        category_ref="esg",
        horizon="historical",
        materiality=0.7,
        confidence=0.86,
        authority_classes=("audited_issuer",),
        claim_types=("audited_fact",),
        evidence_refs=("ev_energy_transition",),
        entity_ref="lucky_cement",
        taxonomy_version="1.0.0",
        workbook_fingerprint="fp_lucky_2025",
    )
    run = QualitativeRunResult(
        entity_ref="lucky_cement",
        entity_scope="company",
        source_set=(
            SourceSnapshot(
                source_type="annual_report",
                snapshot_ref="fp_lucky_2025",
            ),
        ),
        observation_window={"min": 2025, "max": 2025, "time_basis": "fiscal"},
        category_results=(category,),
        coverage_summary=RunCoverageSummary(
            analyzable_categories=1,
            total_categories=1,
            analyzable_percentage=100.0,
            category_status_counts={CategoryStatus.ANALYZED_WITH_WARNING: 1},
            mapped=1,
            raw=1,
            unmapped_rate=0.0,
        ),
        confidence_summary=ConfidenceDistribution(bucket_0_7_to_0_9=1),
        materiality_summary=RunMaterialitySummary(
            top_theme_refs=("energy_transition",),
            ranking_basis="materiality_desc",
        ),
        divergence_summary=DivergenceSummary(),
        unmapped_summary=UnmappedSummary(),
        fve_handoff=FVEHandoffPayload(
            handoff_id="handoff_lucky_2025",
            entity_ref="lucky_cement",
            taxonomy_version="1.0.0",
            authority_matrix_version="1.0.0",
            workbook_fingerprint="fp_lucky_2025",
            themes=(handoff_theme,),
        ),
        run_status=RunStatus.ANALYZED_WITH_COVERAGE,
        versions=RunVersions(
            taxonomy_version="1.0.0",
            authority_matrix_version="1.0.0",
            assembly_contract_version="1.0.0",
            scorecard_contract_version="1.0.0",
        ),
    )

    restored = QualitativeRunResult.model_validate(run.model_dump(mode="json"))

    assert restored == run
    assert restored.coverage_summary.analyzable_percentage == 100.0
    assert restored.fve_handoff.themes[0].narrative_only is True


def test_run_result_rejects_category_version_mismatch() -> None:
    category = QualitativeCategoryResult(
        category_ref="governance",
        status="SKIPPED_INSUFFICIENT_COVERAGE",
        coverage=CategoryCoverage(mapped=0, raw=0, unmapped_rate=0.0),
        category_confidence=ConfidenceDistribution(),
        category_materiality=CategoryMateriality(aggregation_method="max"),
        skip_reason="No governance section was available.",
        evidence_refs=("coverage_gap:governance",),
        taxonomy_version="2.0.0",
        authority_matrix_version="1.0.0",
    )

    with pytest.raises(ValidationError, match="taxonomy_version"):
        QualitativeRunResult(
            entity_ref="lucky_cement",
            entity_scope="company",
            category_results=(category,),
            coverage_summary=RunCoverageSummary(
                analyzable_categories=1,
                total_categories=1,
                analyzable_percentage=100.0,
            ),
            confidence_summary=ConfidenceDistribution(),
            materiality_summary=RunMaterialitySummary(ranking_basis="materiality"),
            divergence_summary=DivergenceSummary(),
            unmapped_summary=UnmappedSummary(),
            fve_handoff=FVEHandoffPayload(
                handoff_id="handoff",
                entity_ref="lucky_cement",
                taxonomy_version="1.0.0",
                authority_matrix_version="1.0.0",
            ),
            run_status="ANALYZED_WITH_COVERAGE",
            versions=RunVersions(
                taxonomy_version="1.0.0",
                authority_matrix_version="1.0.0",
                assembly_contract_version="1.0.0",
                scorecard_contract_version="1.0.0",
            ),
        )
