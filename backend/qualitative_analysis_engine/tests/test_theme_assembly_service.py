"""Tests for QAE Phase 5 deterministic theme assembly."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from qualitative_analysis_engine.models import (  # noqa: E402
    DivergenceType,
    ThemeSalience,
)
from qualitative_analysis_engine.services import (  # noqa: E402
    InsightToSignalAdapter,
    QualitativeCoverageGate,
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


def _assemble(insights):
    signals = _adapter().adapt_insights(insights)
    gate_result = QualitativeCoverageGate().evaluate(signals)
    return signals, gate_result, ThemeAssemblyService().assemble(signals, gate_result)


def test_theme_creation_and_identity_stability() -> None:
    _, _, result = _assemble(
        [
            _insight(page_number=10),
            _insight(
                page_number=11,
                takeaway="Capacity addition supports future demand growth.",
            ),
        ]
    )

    assert len(result.themes) == 1
    theme = result.themes[0]
    assert theme.theme_reference.entity_ref == "lucky_cement"
    assert theme.theme_reference.entity_scope == "company"
    assert theme.theme_reference.theme_ref == "capacity_expansion"
    assert theme.theme_reference.taxonomy_version == "1.0.0"
    assert theme.category_ref == "strategy"
    assert theme.salience == ThemeSalience.FULL_SALIENCE
    assert result.themes_by_category == {"strategy": 1}


def test_evidence_aggregation_preserves_signal_metadata() -> None:
    signals, _, result = _assemble(
        [
            _insight(page_number=10),
            _insight(
                page_number=12,
                source_section="Strategy",
                takeaway="Expansion project improved production flexibility.",
            ),
        ]
    )

    theme = result.themes[0]
    assert set(theme.signal_ids) == {signal.signal_id for signal in signals}
    assert theme.evidence.signal_claims[signals[0].signal_id] == signals[0].claim
    assert theme.evidence.observation_times[signals[0].signal_id] == 2025
    assert theme.evidence.subject_periods[signals[0].signal_id] == 2025
    assert theme.evidence.provenance_refs[0].startswith("PDF_PAGE:")
    assert theme.evidence.duplicate_count == 2
    assert theme.evidence.independent_origins == ("annual_report",)


def test_deduplication_removes_duplicate_artifacts_without_cross_source_dedup() -> None:
    signals, gate_result, result = _assemble(
        [
            _insight(page_number=10),
            _insight(page_number=10),
        ]
    )

    assert len(signals) == 2
    assert len(result.themes) == 1
    assert len(result.themes[0].signal_ids) == 1
    assert result.duplicate_artifacts_removed == 1
    assert result.themes[0].evidence.duplicate_count == 2
    assert gate_result.total_signal_count == 2


def test_contradiction_tracking_records_unresolved_divergence() -> None:
    _, _, result = _assemble(
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

    assert len(result.themes) == 1
    assert len(result.divergences) == 1
    divergence = result.divergences[0]
    assert divergence.divergence_type == DivergenceType.NARRATIVE_VS_NARRATIVE
    assert divergence.auto_resolved is False
    assert result.themes[0].divergence_refs == (divergence,)
    assert result.themes[0].theme_confidence < 0.9


def test_unmapped_signals_never_create_themes_and_are_queued() -> None:
    _, _, result = _assemble(
        [
            _insight(
                area="Unknown topic",
                takeaway="This statement has no frozen taxonomy match.",
            )
        ]
    )

    assert result.themes == ()
    assert len(result.unmapped_queue) == 1
    assert result.unmapped_queue[0].area == "Unknown topic"
    assert result.unmapped_queue[0].category_ref == "strategy"


def test_low_confidence_mapped_signals_do_not_create_themes() -> None:
    _, _, result = _assemble(
        [
            _insight(area="capacity expansion", page_number=10, confidence=0.9),
            _insight(
                area="cost optimization",
                takeaway="Cost reduction continued.",
                page_number=11,
                confidence=0.9,
            ),
            _insight(
                area="diversification",
                takeaway="New product line was mentioned.",
                page_number=12,
                confidence=0.0,
            ),
        ]
    )

    theme_refs = {theme.theme_reference.theme_ref for theme in result.themes}
    assert theme_refs == {"capacity_expansion", "cost_optimization"}


def test_theme_confidence_uses_strongest_signal_with_keyword_ceiling() -> None:
    _, _, result = _assemble(
        [
            _insight(
                area="Exports and Margin Drivers",
                takeaway="Export volumes increased after entering overseas markets.",
                source_section="CEO Review",
                confidence=0.95,
                page_number=30,
            ),
            _insight(
                area="Exports and Margin Drivers",
                takeaway="Export sales increased across overseas markets.",
                source_section="CEO Review",
                confidence=0.85,
                page_number=31,
            ),
        ]
    )

    assert len(result.themes) == 1
    theme = result.themes[0]
    assert theme.theme_reference.theme_ref == "market_geographic_expansion"
    assert theme.theme_confidence == 0.65
    assert result.confidence_distribution["0.5-0.7"] == 1


def test_materiality_calculation_uses_category_prior_support_and_quantification() -> None:
    _, _, result = _assemble(
        [
            _insight(
                area="liquidity",
                takeaway="Borrowings increased by 15% due to working capital needs.",
                source_section="Risks",
                page_number=40,
            ),
            _insight(
                area="liquidity",
                takeaway="Debt servicing pressure remained elevated.",
                source_section="Financial Review",
                page_number=41,
            ),
        ]
    )

    theme = result.themes[0]
    assert theme.category_ref == "business_risk"
    assert theme.materiality >= 0.7
    assert theme.evidence_weight > 0.6
    assert result.materiality_distribution["0.7-0.9"] == 1
