# Forecast Validation MVP Known Limitations

## Freeze Scope

Forecast Validation MVP is frozen as a gate-first historical-baseline readiness product. It reports what can and cannot be safely validated. It is not yet a full forecast-performance validation product.

## Current Executable Surface

The frozen executable MVP surface is:

- Historical baseline readiness
- EPS baseline readiness
- Forecast input structural validation when caller-supplied forecast inputs are provided

Revenue, profitability, cash flow, debt, and balance sheet validations remain deferred behind the unlock contract.

## Known Limitations

### Single Issuer Validation

The end-to-end smoke audit is based on the latest Lucky Cement production bundle. The orchestrated Forecast Validation MVP has not yet been smoke-tested across a broad issuer set.

### Single Source-Report-Year Bias

The current production readiness evidence is tied to a single latest Lucky production bundle and its available source-report-year context. Comparative-year policy exists upstream, but Forecast Validation freeze evidence is not yet cross-issuer or cross-report-year validated.

### Gate Not Analyst-Truth-Validated

The HistoricalSeriesIntegrityGate determines admission authority for validation categories. Its decisions are deterministic and tested, but not yet validated against an analyst-reviewed truth set. Numeric validation categories must not be unlocked until gate decisions for their required metrics are analyst-truth-validated.

### Deferred Categories

The following categories are intentionally deferred and must not execute in the frozen MVP:

- RevenueValidationService
- Profitability
- Cash Flow
- Debt
- Balance Sheet

### Revenue Blocked

Revenue remains `baseline_not_validatable` on the latest Lucky production bundle. Revenue growth, trend-break, and plausibility rules exist but are not activated in the frozen MVP orchestration.

### Debt And Equity Missing

Exact canonical metrics for total debt, long-term debt, and total equity are missing in the latest Lucky production bundle gate result. Debt and balance-sheet validation categories remain blocked until upstream OCR/consolidation produces admitted baseline series.

### Replay-Derived Gate Assumptions

The gate operates over the production bundle's consolidated MetricValues. Some upstream data quality conditions are inherited from OCR, normalization, and consolidation outputs. Forecast Validation does not repair those inputs.

### Forecast Inputs Are Caller-Supplied

The production QueryEngineInputBundle does not contain forecast inputs. ForecastInputCategory is part of the frozen executable scope only for caller-supplied `ForecastInput` records. Representative execution has been demonstrated separately during freeze completion.

### Scorecard Is Not Baseline Health

Run-level `overall_score` reflects executable MVP categories only. It must be interpreted together with:

- `metrics_admitted`
- `metrics_blocked`
- `metrics_missing`
- `coverage_percentage`

Coverage context is mandatory because a passing or warning score may still cover only a small portion of required historical metrics.

## Post-Freeze Unlock Conditions

Before activating any deferred numeric category:

1. Required metrics must reach `clean` or `clean_with_warning` in the HistoricalSeriesIntegrityGate.
2. Gate decisions for those metrics must be validated against an analyst-reviewed truth set.
3. The category must demonstrate end-to-end execution on a representative production bundle.
4. Evidence, citations, confidence, and skipped accounting must remain deterministic.
