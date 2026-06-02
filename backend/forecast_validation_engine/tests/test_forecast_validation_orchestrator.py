"""Tests for Forecast Validation MVP orchestration spine."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from forecast_validation_engine.models import (  # noqa: E402
    ForecastInput,
    ValidationOutcome,
)
from forecast_validation_engine.services import ForecastValidationOrchestrator  # noqa: E402
from shared.models.financial_year_consolidation import (  # noqa: E402
    FinancialYearConsolidationResult,
)
from shared.models.metric_value import MetricValue  # noqa: E402


def _metric_value(
    metric: str,
    year: int,
    value: float,
    *,
    table_type: str = "income_statement",
    page_number: int = 292,
) -> MetricValue:
    return MetricValue(
        metric=metric,
        value_year=year,
        value=value,
        source_report_year=2025,
        page_number=page_number,
        table_type=table_type,
    )


def _run(
    consolidation_result: FinancialYearConsolidationResult,
    *,
    forecast_inputs: tuple[ForecastInput, ...] = (),
    metrics: tuple[str, ...] = ("earnings_per_share",),
):
    return ForecastValidationOrchestrator().run(
        consolidation_result=consolidation_result,
        forecast_inputs=forecast_inputs,
        validation_id="fv_orchestrator_test",
        company_name="Lucky Cement Limited",
        workbook_id="wb_lucky",
        workbook_fingerprint="fingerprint",
        bundle_fingerprint="bundle_fingerprint",
        metrics=metrics,
    )


def test_orchestrator_reports_all_categories_skipped_when_no_inputs_are_admitted() -> None:
    result = _run(FinancialYearConsolidationResult(metric_values=[]))

    assert result.historical_gate_result.status_counts["missing"] == 1
    assert result.scorecard.overall_outcome == ValidationOutcome.SKIPPED
    assert result.scorecard.category_outcomes["HistoricalBaselineReadinessCategory"] == (
        ValidationOutcome.SKIPPED
    )
    assert result.scorecard.category_outcomes["EPSBaselineCategory"] == (
        ValidationOutcome.SKIPPED
    )
    assert result.scorecard.category_outcomes["ForecastInputCategory"] == (
        ValidationOutcome.SKIPPED
    )
    assert set(result.scorecard.deferred_categories) == {
        "RevenueValidationService",
        "Profitability",
        "Cash Flow",
        "Debt",
        "Balance Sheet",
    }
    assert result.scorecard.metrics_admitted == 0
    assert result.scorecard.metrics_blocked == 0
    assert result.scorecard.metrics_missing == 1
    assert result.scorecard.coverage_percentage == 0.0
    assert result.bundle_fingerprint == "bundle_fingerprint"
    assert result.scorecard.bundle_fingerprint == "bundle_fingerprint"
    assert result.gate_version == "1.0.0"
    assert result.scorecard.gate_version == "1.0.0"
    assert all(not item.executed for item in result.execution_results)


def test_orchestrator_executes_eps_category_when_eps_baseline_is_admitted() -> None:
    result = _run(
        FinancialYearConsolidationResult(
            metric_values=[
                _metric_value("earnings_per_share", 2024, 48.0),
                _metric_value("earnings_per_share", 2025, 52.5),
            ]
        )
    )

    assert result.scorecard.category_outcomes["EPSBaselineCategory"] == (
        ValidationOutcome.PASS
    )
    assert result.scorecard.category_outcomes["HistoricalBaselineReadinessCategory"] == (
        ValidationOutcome.PASS
    )
    assert result.scorecard.overall_outcome == ValidationOutcome.PASS
    assert result.scorecard.metrics_admitted == 1
    assert result.scorecard.metrics_blocked == 0
    assert result.scorecard.metrics_missing == 0
    assert result.scorecard.coverage_percentage == 100.0
    eps_execution = next(
        item for item in result.execution_results if item.rule_id == "eps_baseline_validation"
    )
    assert eps_execution.executed is True


def test_orchestrator_blocks_deferred_revenue_category_even_when_revenue_is_available() -> None:
    result = _run(
        FinancialYearConsolidationResult(
            metric_values=[
                _metric_value("revenue", 2024, 100.0),
                _metric_value("revenue", 2025, 120.0),
            ]
        ),
        forecast_inputs=(
            ForecastInput(metric="revenue", forecast_year=2026, value=132.0),
        ),
        metrics=("revenue",),
    )

    assert result.scorecard.category_outcomes["RevenueValidationService"] == (
        ValidationOutcome.SKIPPED
    )
    assert "RevenueValidationService" in result.scorecard.deferred_categories
    assert {
        item.rule_id for item in result.execution_results
    } == {"eps_baseline_validation", "forecast_input_validation"}
    assert "revenue_growth_validation" not in {
        item.rule_id for item in result.execution_results
    }


def test_orchestrator_scorecard_aggregates_active_category_scores() -> None:
    result = _run(
        FinancialYearConsolidationResult(
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
    )

    assert result.scorecard.overall_outcome == ValidationOutcome.PASS
    assert result.scorecard.overall_score == 100.0
    assert result.scorecard.category_scores_by_name["EPSBaselineCategory"] == 100.0
    assert result.scorecard.category_scores_by_name["ForecastInputCategory"] == 100.0
    assert result.scorecard.category_scores_by_name["RevenueValidationService"] is None


def test_orchestrator_aggregates_run_level_evidence_and_citations() -> None:
    result = _run(
        FinancialYearConsolidationResult(
            metric_values=[
                _metric_value("earnings_per_share", 2024, 48.0, page_number=291),
                _metric_value("earnings_per_share", 2025, 52.5, page_number=292),
            ]
        ),
        forecast_inputs=(
            ForecastInput(
                metric="earnings_per_share",
                forecast_year=2026,
                value=55.0,
            ),
        ),
    )

    evidence_ids = {item.evidence_id for item in result.evidence}
    assert "historical_baseline_readiness:summary" in evidence_ids
    assert "eps_baseline_validation:earnings_per_share" in evidence_ids
    assert "forecast_validation_orchestrator:deferred_categories" in evidence_ids
    assert len(result.citations) >= 2
    assert result.provenance["gate_executed"] is True
    assert "RevenueValidationService" in result.provenance["deferred_categories"]
