"""Tests for QAE Phase 4 qualitative coverage gate."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from qualitative_analysis_engine.services import (  # noqa: E402
    CategoryAdmissionStatus,
    InsightToSignalAdapter,
    QualitativeCoverageGate,
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
        "takeaway": "New line increased capacity.",
        "source_section": "Business Review",
        "page_number": 10,
        "confidence": 0.85,
    }
    payload.update(overrides)
    return payload


def _decision(result, category_ref: str):
    return next(
        decision
        for decision in result.category_coverage
        if decision.category_ref == category_ref
    )


def test_fully_admitted_category() -> None:
    signals = _adapter().adapt_insights(
        [
            _insight(area="capacity expansion", page_number=10),
            _insight(
                area="cost optimization",
                takeaway="Management delivered cost reduction initiatives.",
                page_number=11,
            ),
        ]
    )

    result = QualitativeCoverageGate().evaluate(signals)
    strategy = _decision(result, "strategy")

    assert strategy.admission_status == CategoryAdmissionStatus.ADMITTED
    assert strategy.raw_signal_count == 2
    assert strategy.mapped_signal_count == 2
    assert strategy.unmapped_signal_count == 0
    assert strategy.eligible_signal_count == 2
    assert strategy.mapped_coverage_percent == 100.0
    assert strategy.warning_reasons == ()
    assert "strategy" in result.admitted_categories
    assert strategy.provenance_records[0]["page_number"] == 10


def test_warning_category_for_thin_evidence() -> None:
    signals = _adapter().adapt_insights([_insight(area="capacity expansion")])

    result = QualitativeCoverageGate().evaluate(signals)
    strategy = _decision(result, "strategy")

    assert strategy.admission_status == (
        CategoryAdmissionStatus.ADMITTED_WITH_WARNING
    )
    assert strategy.warning_reasons == ("insufficient_category_evidence",)
    assert "strategy" in result.warning_categories


def test_insufficient_coverage_category() -> None:
    signals = _adapter().adapt_insights(
        [
            _insight(area="capacity expansion", page_number=10),
            _insight(
                area="Unmapped A",
                takeaway="Narrative does not match frozen seeds.",
                page_number=11,
            ),
            _insight(
                area="Unmapped B",
                takeaway="Another unmatched narrative statement.",
                page_number=12,
            ),
        ]
    )

    result = QualitativeCoverageGate().evaluate(signals)
    strategy = _decision(result, "strategy")

    assert strategy.admission_status == (
        CategoryAdmissionStatus.SKIPPED_INSUFFICIENT_COVERAGE
    )
    assert strategy.raw_signal_count == 3
    assert strategy.mapped_signal_count == 1
    assert strategy.unmapped_signal_count == 2
    assert strategy.mapped_coverage_percent == pytest.approx(33.333333)
    assert strategy.skip_reason == "Mapped coverage is below the category coverage floor."
    assert "strategy" in result.skipped_categories


def test_no_eligible_signals_category() -> None:
    signals = _adapter().adapt_insights(
        [
            _insight(
                area="Unmapped A",
                takeaway="Narrative does not match frozen seeds.",
                source_section="Business Review",
            )
        ]
    )

    result = QualitativeCoverageGate().evaluate(signals)
    strategy = _decision(result, "strategy")

    assert strategy.admission_status == (
        CategoryAdmissionStatus.SKIPPED_NO_ELIGIBLE_SIGNALS
    )
    assert strategy.raw_signal_count == 1
    assert strategy.mapped_signal_count == 0
    assert strategy.unmapped_signal_count == 1
    assert strategy.eligible_signal_count == 0
    assert strategy.warning_reasons == ("no_eligible_signals",)
    assert strategy.skip_reason == (
        "No mapped creation-eligible signals met the confidence floor."
    )


def test_source_section_coverage_and_version_pins_are_reported() -> None:
    signals = _adapter().adapt_insights(
        [
            _insight(area="capacity expansion", source_section="Business Review"),
            _insight(
                area="renewable energy",
                source_section="Sustainability",
                page_number=30,
            ),
        ]
    )

    result = QualitativeCoverageGate().evaluate(signals)

    assert result.taxonomy_version == "1.0.0"
    assert result.authority_matrix_versions == ("1.0.0",)
    assert result.total_signal_count == 2
    assert result.mapped_signal_count == 2
    assert result.unmapped_signal_count == 0
    assert result.source_section_coverage == {
        "Business Review": 1,
        "Sustainability": 1,
    }
    assert _decision(result, "esg").expected_sections_present == ("Sustainability",)


def test_gate_rejects_mixed_taxonomy_versions() -> None:
    signal = _adapter().adapt_insight(_insight())
    bad_signal = signal.model_copy(update={"taxonomy_version": "2.0.0"})

    with pytest.raises(ValueError, match="taxonomy versions"):
        QualitativeCoverageGate().evaluate([signal, bad_signal])

