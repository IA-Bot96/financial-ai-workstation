"""Tests for QAE Phase 6 category aggregation and scorecard services."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from qualitative_analysis_engine.models import (  # noqa: E402
    CategoryStatus,
    EntityScope,
    RunStatus,
    SourceType,
)
from qualitative_analysis_engine.services import (  # noqa: E402
    CategoryAggregationService,
    InsightToSignalAdapter,
    QualitativeCoverageGate,
    QualitativeScorecardService,
    ThemeAssemblyService,
)


def _adapter() -> InsightToSignalAdapter:
    return InsightToSignalAdapter(
        entity_ref="lucky_cement",
        workbook_fingerprint="fp_lucky_2025",
    )


def _insight(**overrides) -> dict:
    payload = {
        "value_year": 2025,
        "source_report_year": 2025,
        "area": "capacity expansion",
        "takeaway": "Capacity increased after commissioning of a new line.",
        "source_section": "Business Review",
        "page_number": 10,
        "confidence": 0.9,
    }
    payload.update(overrides)
    return payload


def _run(insights):
    signals = _adapter().adapt_insights(insights)
    coverage_result = QualitativeCoverageGate().evaluate(signals)
    assembly_result = ThemeAssemblyService().assemble(signals, coverage_result)
    category_results = CategoryAggregationService().aggregate(
        coverage_result=coverage_result,
        assembly_result=assembly_result,
    )
    run_result = QualitativeScorecardService().build_run_result(
        entity_ref="lucky_cement",
        entity_scope="company",
        workbook_fingerprint="fp_lucky_2025",
        coverage_result=coverage_result,
        assembly_result=assembly_result,
        category_results=category_results,
    )
    return signals, coverage_result, assembly_result, category_results, run_result


def _category(category_results, category_ref: str):
    return next(
        result for result in category_results if result.category_ref == category_ref
    )


def test_category_aggregation_rolls_up_themes_and_coverage() -> None:
    _, _, _, category_results, _ = _run(
        [
            _insight(page_number=10),
            _insight(
                page_number=11,
                takeaway="Capacity expansion improved future production headroom.",
            ),
        ]
    )

    strategy = _category(category_results, "strategy")

    assert strategy.status == CategoryStatus.ANALYZED
    assert len(strategy.owned_themes) == 1
    assert strategy.coverage.raw == 2
    assert strategy.coverage.mapped == 2
    assert strategy.coverage.source_mix == {SourceType.ANNUAL_REPORT: 2}
    assert strategy.category_confidence.total == 1
    assert strategy.category_materiality.max_materiality is not None
    assert strategy.evidence_refs == ("theme_evidence:lucky_cement:capacity_expansion:1.0.0",)


def test_category_status_assignment_for_analyzed_and_skipped_categories() -> None:
    _, _, _, category_results, _ = _run([_insight(page_number=10)])

    strategy = _category(category_results, "strategy")
    business_risk = _category(category_results, "business_risk")

    assert strategy.status == CategoryStatus.ANALYZED_WITH_WARNING
    assert strategy.skip_reason is None
    assert business_risk.status == CategoryStatus.SKIPPED_NO_ELIGIBLE_SIGNALS
    assert business_risk.skip_reason
    assert business_risk.evidence_refs == ("coverage_gap:business_risk",)


def test_run_result_generation_preserves_versions_and_source_snapshot() -> None:
    _, _, _, category_results, run_result = _run(
        [
            _insight(page_number=10),
            _insight(
                page_number=11,
                area="cost optimization",
                takeaway="Energy efficiency initiatives reduced operating costs.",
            ),
        ]
    )

    assert run_result.entity_ref == "lucky_cement"
    assert run_result.entity_scope == EntityScope.COMPANY
    assert run_result.run_status == RunStatus.INSUFFICIENT_COVERAGE
    assert run_result.versions.taxonomy_version == "1.0.0"
    assert run_result.versions.scorecard_contract_version == "1.0.0"
    assert run_result.source_set[0].source_type == SourceType.ANNUAL_REPORT
    assert run_result.source_set[0].snapshot_ref == "fp_lucky_2025"
    assert run_result.coverage_summary.total_categories == len(category_results)
    assert run_result.fve_handoff.narrative_only is True


def test_run_coverage_reporting_includes_unmapped_and_section_presence() -> None:
    _, coverage_result, _, _, run_result = _run(
        [
            _insight(area="capacity expansion", source_section="Business Review"),
            _insight(
                area="Unusual unexplained topic",
                takeaway="This statement has no frozen taxonomy match.",
                source_section="Business Review",
            ),
        ]
    )

    assert coverage_result.total_signal_count == 2
    assert run_result.coverage_summary.raw == 2
    assert run_result.coverage_summary.mapped == 1
    assert run_result.coverage_summary.unmapped_rate == 0.5
    assert run_result.coverage_summary.section_presence_map["Business Review"] is True
    assert (
        run_result.coverage_summary.category_status_counts[
            CategoryStatus.SKIPPED_NO_ELIGIBLE_SIGNALS
        ]
        >= 1
    )
    assert run_result.unmapped_summary.total_unmapped == 1
    assert run_result.unmapped_summary.unmapped_by_category_prior["strategy"] == 1


def test_divergence_reporting_rolls_up_category_and_run_counts() -> None:
    _, _, assembly_result, category_results, run_result = _run(
        [
            _insight(
                area="demand outlook",
                takeaway="Demand increased due to market recovery.",
                source_section="Outlook",
                page_number=20,
            ),
            _insight(
                area="demand outlook",
                takeaway="Demand declined due to weak market conditions.",
                source_section="Outlook",
                page_number=21,
            ),
        ]
    )

    outlook = _category(category_results, "outlook")

    assert len(assembly_result.divergences) == 1
    assert len(outlook.divergence_refs) == 1
    assert run_result.divergence_summary.total_divergences == 1
    assert run_result.divergence_summary.count_by_category["outlook"] == 1


def test_unmapped_only_run_preserves_review_queue_without_themes() -> None:
    _, _, assembly_result, category_results, run_result = _run(
        [
            _insight(
                area="Unknown topic",
                takeaway="This narrative does not map to the frozen taxonomy.",
            )
        ]
    )

    strategy = _category(category_results, "strategy")

    assert assembly_result.themes == ()
    assert strategy.status == CategoryStatus.SKIPPED_NO_ELIGIBLE_SIGNALS
    assert run_result.unmapped_summary.total_unmapped == 1
    assert run_result.unmapped_summary.sample_claims == (
        "This narrative does not map to the frozen taxonomy.",
    )
    assert run_result.run_status == RunStatus.INSUFFICIENT_COVERAGE
