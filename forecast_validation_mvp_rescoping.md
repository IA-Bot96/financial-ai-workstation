# Forecast Validation MVP Rescoping

**Decision date:** 2026-06-02  
**Purpose:** Re-scope Forecast Validation Engine MVP to match the current historical-series integrity contract.

## Source Artifacts

- `forecast_validation_architecture_review.md`
- `forecast_validation_preimplementation_review.md`
- `output/historical_series_integrity_gate_report.json`

## Current Gate Reality

The Historical Series Integrity Gate is the admission contract for Forecast Validation MVP. On the latest Lucky production bundle it reports:

| Gate Status | Count | Metrics |
|---|---:|---|
| `clean` | 0 | None |
| `clean_with_warning` | 1 | `earnings_per_share` |
| `baseline_not_validatable` | 7 | `revenue`, `profit_after_tax`, `operating_profit`, `total_assets`, `cash_and_cash_equivalents`, `operating_cash_flow`, `gross_profit` |
| `missing` | 3 | `total_debt`, `long_term_debt`, `total_equity` |

Overall gate status is `baseline_not_validatable`.

The current system therefore cannot support the originally broad Forecast Validation MVP. The revised MVP must treat the integrity gate as the first-stage blocker and avoid running calculations over blocked or missing baselines.

## 1. Categories Executable Today

Executable means the category can run using only metrics admitted by the gate as `clean` or `clean_with_warning`.

| Category | Status Today | Required Metrics | Decision |
|---|---|---|---|
| Historical baseline readiness | Executable | All MVP metrics | Include. This is the first MVP category and must run before all numeric validation. |
| EPS standalone integrity | Executable with warning | `earnings_per_share` | Include narrowly. Validate/report EPS baseline readiness only; do not compare EPS to PAT yet. |
| Forecast input completeness and metadata checks | Executable | Forecast input payload, requested metrics, years, units | Include if forecasts are provided. This does not require historical calculations. |
| Evidence and provenance completeness | Executable | Gate evidence, citations, source metadata | Include. Report whether admitted or blocked metrics have sufficient evidence. |

No revenue, margin, cash-flow, debt, or balance-sheet numeric validation category is executable today against the current gate result.

## 2. Categories Blocked By Gate

These categories have required metrics present but classified as `baseline_not_validatable`.

| Category | Blocked Metrics | Blocking Reasons |
|---|---|---|
| Revenue growth consistency | `revenue` | candidate spread above 100x, disallowed source table, note selected over primary statement, YoY scale issue |
| Profitability validation | `profit_after_tax`, `operating_profit`, `gross_profit` | candidate spread above 100x, unresolved conflicts, YoY scale issues |
| Margin consistency | `revenue`, `gross_profit`, `operating_profit`, `profit_after_tax` | all required metrics are blocked or partly blocked |
| EPS consistency against PAT | `profit_after_tax` | PAT is blocked, so EPS-vs-PAT cannot run even though EPS is usable with warning |
| Cash-flow consistency | `operating_cash_flow`, `cash_and_cash_equivalents`, `profit_after_tax` | OCF and cash are blocked; PAT is blocked |
| Balance-sheet growth and asset plausibility | `total_assets`, `cash_and_cash_equivalents` | total assets and cash are blocked |
| Forecast plausibility for blocked metrics | Any blocked metric | Forecast plausibility cannot compare against an invalid historical baseline |
| Trend-break validation for blocked series | Any blocked metric | Trend calculations over blocked baselines would produce misleading results |

MVP behavior for these categories: return `SKIPPED` with reason `historical_baseline_not_validatable`, and include gate evidence. Do not calculate YoY, CAGR, margins, or plausibility scores for these series.

## 3. Categories Blocked By Missing Metrics

These categories require exact canonical metrics that are currently absent.

| Category | Missing Metrics | Decision |
|---|---|---|
| Debt consistency | `total_debt`, `long_term_debt` | Deferred. Do not infer from narrower debt components. |
| Balance-sheet equation validation | `total_equity` | Deferred. Do not substitute `share_capital_and_reserves` without an approved policy. |
| Debt-to-equity and leverage checks | `total_debt`, `long_term_debt`, `total_equity` | Deferred. |
| Interest coverage and debt capacity checks | `total_debt` or debt components | Deferred unless exact debt policy is added later. |

MVP behavior for these categories: return `SKIPPED` with reason `required_metric_missing`, and include missing-metric evidence.

## 4. Revised MVP

The revised MVP is a gate-first validation product, not a full forecast-plausibility engine.

### MVP In Scope

1. **Historical Baseline Readiness**
   - Run `HistoricalSeriesIntegrityGate`.
   - Emit one readiness result per MVP metric.
   - Classify each metric as `clean`, `clean_with_warning`, `baseline_not_validatable`, or `missing`.
   - Preserve gate evidence, issue types, confidence, source pages, table types, and candidate-spread diagnostics.

2. **Validation Category Admission**
   - Determine which validation categories may run based on gate output.
   - Mark blocked categories as `SKIPPED`, not `FAIL`.
   - Separate data-baseline failure from forecast failure.

3. **EPS Standalone Baseline Check**
   - Admit EPS as `clean_with_warning`.
   - Surface warning evidence:
     - rejected EPS candidate spread above 100x
     - YoY scale warning
   - Do not perform EPS-vs-PAT validation until PAT is admitted by the gate.

4. **Forecast Input Contract Checks**
   - Validate forecast payload shape, metric names, value years, units, and required fields.
   - Confirm forecast metrics map to exact canonical metrics.
   - Mark forecast rows as not comparable when their historical baseline is blocked or missing.

5. **Evidence, Citation, And Provenance Reporting**
   - Every result must cite:
     - historical gate evidence when baseline-driven
     - forecast input reference when forecast-driven
     - bundle/workbook fingerprint where available
   - Gate-overridden candidates must be identified as PDF-provenance-only unless a workbook cell mapping exists.

6. **Scorecard**
   - Produce a scorecard that distinguishes:
     - executable categories
     - skipped due to blocked baseline
     - skipped due to missing metric
     - forecast-input validation issues
   - Overall status should be `SKIPPED` or `WARNING` when no forecast plausibility rules can run, not `FAIL` due to invalid historical data alone.

### MVP Out Of Scope

- Revenue growth validation
- Margin validation
- EPS-vs-PAT validation
- Balance-sheet equation validation
- Debt consistency validation
- Cash-flow consistency validation
- Forecast plausibility scoring against historical CAGR or YoY trends
- Trend-break validation
- Restatement-aware validation
- Insight-aware plausibility validation
- LLM-generated validation explanations

## 5. Deferred MVP Items

Deferred items are not rejected; they require gate-admitted historical baselines first.

| Deferred Item | Unlock Condition |
|---|---|
| Revenue growth validation | `revenue` becomes `clean` or `clean_with_warning` after deterministic remediation and analyst truth validation |
| Margin consistency | `revenue`, `gross_profit`, `operating_profit`, and `profit_after_tax` become gate-admitted |
| EPS consistency | `profit_after_tax` becomes gate-admitted |
| Cash-flow consistency | `operating_cash_flow`, `cash_and_cash_equivalents`, and `profit_after_tax` become gate-admitted |
| Debt consistency | exact `total_debt` and/or approved debt component policy exists |
| Balance-sheet validation | exact `total_equity` exists or approved equity aggregate policy exists |
| Forecast plausibility | the forecasted metric has a gate-admitted historical baseline |
| Trend-break checks | the target metric is gate-admitted and has sufficient clean history |
| Restatement/source-recency checks | at least two `source_report_year` filings exist |
| Insight-supported plausibility | InsightDataset quality and citation contract are frozen for this use case |

## 6. Acceptance Criteria

Forecast Validation MVP may proceed only if all criteria below are met.

### Gate Admission Criteria

- The integrity gate runs before any validation calculation.
- No calculation runs for `baseline_not_validatable` metrics.
- No substitution is performed for `missing` metrics.
- `clean_with_warning` metrics may run only in categories that do not require blocked companion metrics.
- Every skipped category includes a deterministic reason:
  - `historical_baseline_not_validatable`
  - `required_metric_missing`
  - `insufficient_gate_admitted_metrics`
  - `forecast_metric_not_supported`

### Source-Of-Truth Criteria

- The Forecast Validation Engine consumes a single canonical selected value contract.
- If gate policy differs from Query Engine retrieval selection, the result explicitly states which source was used.
- Gate-overridden values must preserve provenance.
- Values without workbook cell mappings must not claim workbook-cell citation coverage.

### Confidence Criteria

- Gate confidence and validation confidence must be separately reported or explicitly composed.
- Validation confidence cannot override severity.
- A critical baseline issue must block downstream forecast validation for that metric.
- `clean_with_warning` sets an upper bound on validation confidence for that metric unless a later policy states otherwise.

### Evidence Criteria

- Every issue references evidence ids.
- Every evidence item includes metric, years, source report year, page number when available, table type, and baseline status.
- Missing metric evidence must state that no substitute was used.
- Skipped categories must be evidenced, not silently omitted.

### Forecast Input Criteria

- Forecast payloads must declare metric, forecast year, value, unit/scale when available, and source.
- Forecast inputs must be checked for metric-resolution and year validity.
- Forecast inputs for blocked or missing historical baselines must be marked not comparable.

## 7. Freeze Criteria

Forecast Validation MVP can freeze when all criteria below pass on the latest production bundle.

### Required Freeze Gates

| Freeze Gate | Required Result |
---|---|
| Historical gate execution | Runs successfully and persists result or is recomputed deterministically with versioned evidence |
| Category admission | 100% deterministic category admission/skip decisions |
| Blocked metric handling | 0 numeric calculations over blocked baselines |
| Missing metric handling | 0 silent substitutions |
| Evidence coverage | 100% of issues and skipped categories have evidence references |
| Citation honesty | 100% of workbook citations refer only to mapped workbook cells |
| Confidence policy | Gate confidence and validation confidence relationship documented and tested |
| Scorecard clarity | Scorecard separates `SKIPPED` due to data baseline from forecast `FAIL` |
| Tests | Unit and regression tests cover clean, clean_with_warning, baseline_not_validatable, and missing paths |

### Data Freeze Conditions

At least one of these must be true before numeric forecast-plausibility categories are included:

1. Required category metrics are `clean` or `clean_with_warning` on the production bundle.
2. An analyst-approved truth set validates the metric series and gate decision.
3. A documented manual-review override has been accepted and preserved as evidence.

### Current Freeze Recommendation

**Freeze only the gate-first readiness MVP.**

Do not freeze full Forecast Validation MVP yet. The current gate result supports readiness reporting and EPS standalone warning-level handling, but it does not support broad historical performance or forecast plausibility validation.

## Final Decision

The Forecast Validation MVP is re-scoped from:

```text
Historical financial performance and forecast plausibility validation
```

to:

```text
Gate-first historical baseline readiness, category admission, evidence-backed skips,
forecast input contract checks, and EPS standalone warning-level baseline reporting.
```

This preserves the architecture's deterministic-first posture while avoiding the central production risk identified by both reviews: running precise calculations over invalid historical baselines.
