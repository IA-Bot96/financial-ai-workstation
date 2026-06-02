"""Tests for deterministic historical-series integrity gating."""

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.models.financial_year_consolidation import (  # noqa: E402
    ConsolidationCandidate,
    ConsolidationGroup,
    FinancialYearConsolidationResult,
)
from shared.models.metric_value import MetricValue  # noqa: E402
from shared.services.historical_series_integrity_gate import (  # noqa: E402
    HistoricalSeriesIntegrityGate,
)


def _metric_value(
    metric: str,
    year: int,
    value: int | float,
    *,
    table_type: str = "income_statement",
    page_number: int = 100,
) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=page_number,
        table_type=table_type,
    )


def _candidate(
    metric: str,
    year: int,
    value: int | float,
    *,
    table_type: str = "income_statement",
    source_class: str = "primary_statement",
    original_metric: str | None = None,
    confidence: float = 0.96,
    requires_review: bool = False,
) -> ConsolidationCandidate:
    return ConsolidationCandidate(
        metric=metric,
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=100,
        table_type=table_type,
        source_class=source_class,  # type: ignore[arg-type]
        statement_scope="unknown",
        normalization_confidence=confidence,
        source_confidence=confidence,
        original_metric=original_metric or metric.replace("_", " ").title(),
        requires_review=requires_review,
        label_cleanliness_score=50,
        source_context_score=55,
        table_type_priority=100 if source_class == "primary_statement" else 35,
    )


def _group(
    metric: str,
    year: int,
    selected: ConsolidationCandidate,
    competing: list[ConsolidationCandidate],
    *,
    unresolved_conflict: bool = False,
) -> ConsolidationGroup:
    return ConsolidationGroup(
        metric=metric,
        value_year=year,
        candidate_count=1 + len(competing),
        selected=selected,
        competing_candidates=competing,
        is_duplicate_group=True,
        is_conflict_group=True,
        conflict_resolved=not unresolved_conflict,
        unresolved_conflict=unresolved_conflict,
        conflict_status=(
            "unresolved_conflict"
            if unresolved_conflict
            else "resolved_conflict"
        ),
        resolution_reason="test_policy",
    )


def test_gate_marks_missing_exact_metric() -> None:
    result = HistoricalSeriesIntegrityGate().evaluate(
        FinancialYearConsolidationResult(metric_values=[]),
        metrics=["total_debt"],
    )

    assert result.status_counts == {
        "clean": 0,
        "clean_with_warning": 0,
        "baseline_not_validatable": 0,
        "missing": 1,
    }
    series = result.series_results[0]
    assert series.status == "missing"
    assert series.blocking_issues[0].issue_type == "missing_exact_canonical_metric"


def test_gate_marks_clean_statement_series() -> None:
    result = HistoricalSeriesIntegrityGate().evaluate(
        FinancialYearConsolidationResult(
            metric_values=[
                _metric_value("revenue", 2024, 1000),
                _metric_value("revenue", 2025, 1200),
            ]
        ),
        metrics=["revenue"],
    )

    series = result.series_results[0]
    assert series.status == "clean"
    assert series.validation_readiness is True
    assert series.blocking_issues == []


def test_gate_blocks_same_year_candidate_spread_above_100x() -> None:
    selected = _candidate("revenue", 2025, 100)
    competing = [_candidate("revenue", 2025, 20_000_000)]
    result = HistoricalSeriesIntegrityGate().evaluate(
        FinancialYearConsolidationResult(
            metric_values=[_metric_value("revenue", 2025, 100)],
            groups=[_group("revenue", 2025, selected, competing)],
        ),
        metrics=["revenue"],
    )

    series = result.series_results[0]
    assert series.status == "baseline_not_validatable"
    assert {
        issue.issue_type for issue in series.blocking_issues
    } >= {"candidate_spread_gt_100x"}
    assert series.candidate_spread_by_year[0].candidate_spread == 200000


def test_gate_keeps_eps_scale_outliers_as_warning() -> None:
    selected = _candidate(
        "earnings_per_share",
        2025,
        52.53,
        original_metric="Earnings per share - basic and diluted",
    )
    competing = [
        _candidate(
            "earnings_per_share",
            2025,
            19_100_000,
            original_metric="Earnings per share - scaled artifact",
        )
    ]
    result = HistoricalSeriesIntegrityGate().evaluate(
        FinancialYearConsolidationResult(
            metric_values=[
                _metric_value(
                    "earnings_per_share",
                    2025,
                    52.53,
                    table_type="income_statement",
                )
            ],
            groups=[_group("earnings_per_share", 2025, selected, competing)],
        ),
        metrics=["earnings_per_share"],
    )

    series = result.series_results[0]
    assert series.status == "clean_with_warning"
    assert series.validation_readiness is True
    assert series.blocking_issues == []
    assert {
        issue.issue_type for issue in series.warning_issues
    } == {"candidate_spread_gt_100x_rejected_eps_candidates"}


def test_gate_blocks_note_selected_over_primary_statement() -> None:
    selected = _candidate(
        "revenue",
        2025,
        100,
        table_type="revenue_note",
        source_class="note_disclosure",
        original_metric="Revenue note",
    )
    competing = [
        _candidate(
            "revenue",
            2025,
            120,
            table_type="income_statement",
            source_class="primary_statement",
            original_metric="Turnover",
        )
    ]
    result = HistoricalSeriesIntegrityGate().evaluate(
        FinancialYearConsolidationResult(
            metric_values=[
                _metric_value(
                    "revenue",
                    2025,
                    100,
                    table_type="revenue_note",
                )
            ],
            groups=[_group("revenue", 2025, selected, competing)],
        ),
        metrics=["revenue"],
    )

    series = result.series_results[0]
    assert series.status == "baseline_not_validatable"
    assert {
        issue.issue_type for issue in series.blocking_issues
    } >= {"disallowed_source_table", "note_selected_over_primary_statement"}


def test_gate_blocks_yoy_scale_jump_above_10x() -> None:
    result = HistoricalSeriesIntegrityGate().evaluate(
        FinancialYearConsolidationResult(
            metric_values=[
                _metric_value("operating_profit", 2024, 100),
                _metric_value("operating_profit", 2025, 2500),
            ]
        ),
        metrics=["operating_profit"],
    )

    series = result.series_results[0]
    assert series.status == "baseline_not_validatable"
    assert series.yoy_scale_issues[0].status == "block"
    assert {
        issue.issue_type for issue in series.blocking_issues
    } >= {"yoy_scale_issue"}


def test_gate_simulation_parity_for_latest_lucky_bundle() -> None:
    bundle_path = (
        ROOT_DIR
        / "output"
        / "lucky_full_ocr_after_regression_fixes_20260602T133227682153_d80f3614.kb.json"
    )
    simulation_path = ROOT_DIR / "output" / "historical_series_gate_simulation_audit.json"
    if not bundle_path.exists() or not simulation_path.exists():
        pytest.skip("Lucky bundle or simulation audit is not available.")

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    simulation = json.loads(simulation_path.read_text(encoding="utf-8"))
    consolidation_result = FinancialYearConsolidationResult.model_validate(
        bundle["financial_year_consolidation_result"]
    )

    result = HistoricalSeriesIntegrityGate().evaluate(consolidation_result)

    expected_status_counts = {
        "clean": 0,
        "clean_with_warning": 0,
        "baseline_not_validatable": 0,
        "missing": 0,
    }
    expected_status_counts.update(simulation["summary"]["status_counts"])

    assert result.status_counts == expected_status_counts
    assert result.metrics_by_status == simulation["summary"]["metrics_by_status"]
