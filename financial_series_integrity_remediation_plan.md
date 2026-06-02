# Historical Financial Series Integrity Remediation Plan

## 1. Scope

Source artifacts:

- `output/scale_consistency_audit.json`
- `forecast_validation_architecture_review.md`

Objective:

Create a remediation plan for historical financial series integrity before Forecast Validation Engine MVP implementation.

This is analysis only. It does not propose code, implementation details, or model definitions.

## 2. Executive Summary

The current Lucky production bundle is not yet suitable as a Forecast Validation MVP baseline.

From `scale_consistency_audit.json`:

| Measure | Result |
|---|---:|
| Core metrics audited | 11 |
| Exact series found | 8 |
| Exact series missing | 3 |
| Total anomalies | 51 |
| Critical anomalies | 50 |
| High anomalies | 1 |
| Metrics safe for Forecast Validation | 1 |
| Metrics requiring review | 10 |

Only `earnings_per_share` is currently safe for Forecast Validation. The following core series require remediation or review:

- `revenue`
- `gross_profit`
- `operating_profit`
- `profit_after_tax`
- `total_assets`
- `total_equity`
- `cash_and_cash_equivalents`
- `total_debt`
- `long_term_debt`
- `operating_cash_flow`

The architecture review correctly identifies the main blocker: Forecast Validation cannot safely calculate growth, CAGR, margins, trend breaks, or forecast plausibility over selected consolidated values until the input baseline passes a data-integrity gate.

## 3. Forecast Validation MVP Input Contract

The smallest practical input contract should require every historical series used by Forecast Validation to pass these checks before numeric validation rules run:

| Contract Requirement | Required For MVP |
|---|---|
| Exact canonical metric exists | Yes |
| At least two consecutive `value_year` records for simple YoY validation | Yes |
| At least three years for trend validation | Yes |
| At least four years for CAGR-based validation | Preferred |
| No unresolved conflicts on selected values | Yes |
| No candidate spread above 100x | Yes |
| No unexplained YoY jump/drop above 10x | Yes |
| One consistent unit, currency, and scale | Yes |
| Statement source policy satisfied | Yes |
| Workbook/PDF citation available | Yes |

If a series fails this contract, the Forecast Validation Engine should return:

```text
baseline_not_validatable
```

not:

```text
forecast_failed
```

That distinction is the central remediation requirement.

## 4. Anomaly Categorization

The 51 anomalies are not mutually exclusive. For remediation planning, each anomaly is assigned a primary category, with secondary causes called out where relevant.

| Category | Estimated Count | Affected Metrics | Fixability | Notes |
|---|---:|---|---|---|
| OCR scale corruption | 10-14 | `revenue`, `profit_after_tax`, `operating_cash_flow`, `earnings_per_share` candidates | Automatically fixable in some cases | Values differ by thousands/millions/billions or EPS/per-share scale. EPS selected values are clean, but rejected candidates show scale corruption. |
| Normalization error | 4-8 | `revenue`, `cash_and_cash_equivalents`, some note-derived labels | Policy-fixable | High-confidence normalization sometimes selects a semantically incomplete or context-contaminated label. |
| Consolidation selection error | 18-24 | `revenue`, `total_assets`, `operating_cash_flow`, `profit_after_tax`, `gross_profit` | Policy-fixable | Selected values are not always the best source candidate even when cleaner candidates exist. |
| Note-vs-statement selection error | 4-6 | `revenue`, possibly `cash_and_cash_equivalents` | Policy-fixable | Note disclosures can outrank primary statement rows due to higher normalization confidence. |
| Source ambiguity | 30-35 | `gross_profit`, `operating_profit`, `profit_after_tax`, `total_assets`, `cash_and_cash_equivalents`, missing debt/equity metrics | Review-only or policy-fixable | Candidate spreads above 100x and unresolved conflicts prevent clean baseline selection. |
| Valid business event | 0 | None confirmed | Not applicable | No anomaly currently has enough evidence to classify as a valid business event. |

The dominant problem is not one isolated OCR defect. It is an interaction between extraction scale, normalization confidence, consolidation precedence, and source-selection policy.

## 5. Fixability Estimate

| Fixability Class | Estimated Anomalies | Description |
|---|---:|---|
| Automatically fixable | 8-12 | Mechanical cases where scale/unit corruption is obvious and a same-year clean candidate is present. Includes EPS rejected candidates and some cash-flow scale candidates. |
| Policy-fixable | 28-34 | Cases requiring deterministic source precedence, scale-consistent series selection, or note-vs-statement rules. Most revenue, total assets, operating cash flow, and some PAT/gross profit cases fall here. |
| Review-only | 7-12 | Missing exact critical metrics, unresolved source ambiguity without a clearly dominant candidate, and cases where statement scope/source semantics are insufficient. |

The plan should aim to convert policy-fixable issues into clean baseline series and leave review-only issues explicitly unavailable for Forecast Validation rather than forcing a selected value.

## 6. Priority Metrics

### 6.1 Revenue

Current state:

| Year | Selected Value | Source |
|---:|---:|---|
| 2020 | 41,871 | Page 162, `balance_sheet` |
| 2021 | 62,940,805,000 | Page 164, `income_statement` |
| 2022 | 95,000,000 | Page 143, `income_statement` |
| 2023 | 95,832 | Page 162, `balance_sheet` |
| 2024 | 26,282,162 | Page 320, `notes` |
| 2025 | 25,417,143 | Page 320, `notes` |

Anomalies:

- 10 critical anomalies.
- Multiple YoY jumps/drops above 100x.
- Candidate spreads above 100x for every year.
- 2024 and 2025 selected from notes despite primary statement candidates existing.

Primary categories:

- Consolidation selection error.
- Note-vs-statement selection error.
- OCR scale corruption.
- Normalization error on note-context revenue labels.

Fixability:

- Mostly policy-fixable.
- Some older comparative years may require review if only summary/analysis values are available.

Priority:

```text
P0 - Highest priority
```

Reason:

Revenue is the anchor for growth, margins, cash conversion, forecast plausibility, and most analyst queries. Forecast Validation MVP cannot operate credibly without a clean revenue baseline.

Remediation direction:

1. Prefer primary income-statement `revenue` / `turnover` candidates over note disclosures for headline revenue.
2. Reject note-derived revenue when a primary statement candidate exists unless the note is explicitly the statement source.
3. Enforce series-level scale consistency before selecting values.
4. Treat candidate spreads above 100x as baseline-blocking.

### 6.2 Profit After Tax

Current state:

| Year | Selected Value | Source |
|---:|---:|---|
| 2020 | -68,120 | Page 164, `income_statement` |
| 2021 | 14,070,189,000 | Page 164, `income_statement` |
| 2022 | 11,730 | Page 164, `income_statement` |
| 2023 | -10,280 | Page 164, `income_statement` |
| 2024 | 72,336,747 | Page 293, `income_statement` |
| 2025 | 84,498,377 | Page 293, `income_statement` |

Anomalies:

- 9 critical anomalies.
- YoY jumps/drops above 100x.
- Candidate spreads above 100x for every year.
- All years are unresolved conflicts.

Primary categories:

- Source ambiguity.
- OCR scale corruption.
- Consolidation selection error.

Fixability:

- Partly policy-fixable where primary income-statement candidates are present.
- Review-only where multiple same-source candidates remain irreconcilable.

Priority:

```text
P0 - Highest priority
```

Reason:

Profit after tax is required for EPS consistency, profitability validation, cash-flow conversion, and forecast net income reasonableness.

Remediation direction:

1. Require a consistent source lineage for PAT across years.
2. Apply scale-consistency checks before allowing PAT into calculations.
3. Do not allow unresolved PAT conflicts into Forecast Validation.
4. Prefer primary income-statement PAT over notes, analysis tables, and summaries.

### 6.3 Operating Profit

Current state:

| Year | Selected Value | Source |
|---:|---:|---|
| 2020 | -88,180 | Page 164, `income_statement` |
| 2021 | -31,040 | Page 164, `income_statement` |
| 2022 | 20,070 | Page 164, `income_statement` |
| 2023 | 16,180 | Page 164, `income_statement` |
| 2024 | 187,200 | Page 164, `income_statement` |
| 2025 | 25,130 | Page 164, `income_statement` |

Anomalies:

- 7 anomalies.
- 6 critical candidate-spread anomalies.
- 1 high YoY jump anomaly.
- All years are unresolved conflicts.

Primary categories:

- Source ambiguity.
- Consolidation selection error.
- OCR scale corruption.

Fixability:

- Policy-fixable if a consistent income-statement row is present.
- Review-only if operating profit rows are mixed with analysis/summary values.

Priority:

```text
P0 - Highest priority
```

Reason:

Operating profit is needed for operating margin, trend validation, and business-performance checks.

Remediation direction:

1. Define source precedence for operating profit versus alternate labels such as operating income, EBIT, and profit from operations.
2. Block unresolved conflicts from Forecast Validation.
3. Reject analysis-table values as headline operating profit unless explicitly requested.

### 6.4 Total Assets

Current state:

| Year | Selected Value | Source |
|---:|---:|---|
| 2020 | 135,868,474,000 | Page 163, `balance_sheet` |
| 2021 | 156,368,062,000 | Page 163, `balance_sheet` |
| 2022 | 184,962,368,000 | Page 163, `balance_sheet` |
| 2023 | 213,079,067,000 | Page 163, `balance_sheet` |
| 2024 | 16,152,486 | Page 323, `balance_sheet` |
| 2025 | 16,845,584 | Page 323, `balance_sheet` |

Anomalies:

- 7 critical anomalies.
- 2023 to 2024 drop above 100x.
- Candidate spreads above 100x for every year.
- All years are unresolved conflicts.

Primary categories:

- Consolidation selection error.
- OCR scale corruption.
- Source ambiguity.

Fixability:

- Strongly policy-fixable if the consistent page 163 balance-sheet series is the correct source.
- 2024/2025 likely require selection correction or review because selected values appear to be on a different scale/source.

Priority:

```text
P0 - Highest priority
```

Reason:

Total assets is required for balance sheet consistency, ROA, asset growth, debt capacity, and cross-statement validation.

Remediation direction:

1. Enforce same-source and same-scale continuity for balance-sheet totals.
2. Prefer primary balance-sheet total rows over note or partial-section totals.
3. Treat balance-sheet candidates with vertical/horizontal analysis values as non-headline candidates.

### 6.5 Cash And Cash Equivalents

Current state:

| Year | Selected Value | Source |
|---:|---:|---|
| 2024 | 336,917,000 | Page 324, `income_statement` |
| 2025 | 666,674,000 | Page 324, `income_statement` |

Anomalies:

- 2 critical anomalies.
- Candidate spread above 100x for both years.
- Only two selected years.
- Both years unresolved conflicts.

Primary categories:

- Source ambiguity.
- Consolidation selection error.
- Possible table classification/source-type issue.

Fixability:

- Policy-fixable if the source policy chooses balance sheet cash or cash-flow ending cash consistently.
- Review-only if balance sheet, cash-flow statement, and note values disagree without a clear bridge.

Priority:

```text
P1 - High priority
```

Reason:

Cash is essential for liquidity validation and explaining changes in debt/profit/capex. However, Forecast Validation can initially degrade this category if revenue/profit/asset baselines are fixed first.

Remediation direction:

1. Define cash source policy: balance sheet cash and cash equivalents should usually be the headline cash metric; cash-flow statement ending cash can be a cross-check.
2. Do not select from a table classified as `income_statement` for headline cash unless provenance confirms classification is wrong but source row is correct.
3. Require reconciliation between balance sheet cash and cash-flow ending cash where both exist.

### 6.6 Operating Cash Flow

Current state:

| Year | Selected Value | Source |
|---:|---:|---|
| 2020 | 5,047 | Page 162, `balance_sheet` |
| 2021 | 12,493 | Page 162, `balance_sheet` |
| 2022 | 15,469 | Page 162, `balance_sheet` |
| 2023 | 23,243 | Page 162, `balance_sheet` |
| 2024 | 45,207,351 | Page 294, `cash_flow_statement` |
| 2025 | 96,742,214 | Page 294, `cash_flow_statement` |

Anomalies:

- 3 critical anomalies.
- 2023 to 2024 jump above 100x.
- Candidate spread above 100x for 2024 and 2025.
- Early years come from a balance-sheet-classified table; later years come from cash-flow statement.

Primary categories:

- Consolidation selection error.
- OCR scale corruption.
- Source ambiguity.

Fixability:

- Policy-fixable if operating cash flow is restricted to cash-flow statement sources.
- Older years may be review-only unless they can be tied to a consistent cash-flow summary scale.

Priority:

```text
P1 - High priority
```

Reason:

Operating cash flow is needed for cash conversion, debt service, liquidity, and forecast plausibility. It is less central than revenue/PAT/assets for MVP readiness, but it is a key gating metric for forecast reasonableness.

Remediation direction:

1. Restrict headline operating cash flow to `cash_flow_statement` or trusted cash-flow summary tables.
2. Reject balance-sheet-classified candidates unless they are explicitly identified as cash-flow summary rows.
3. Enforce scale consistency between summary-period and statement-period values.

## 7. Missing Exact Critical Metrics

The following exact canonical metrics are absent:

- `total_equity`
- `total_debt`
- `long_term_debt`

These are not scale anomalies; they are source-availability and canonical-selection gaps.

Forecast Validation behavior:

| Metric | MVP Treatment |
|---|---|
| `total_equity` | Required for balance-sheet consistency; unavailable until exact aggregate is present or a deterministic equity aggregate policy is approved. |
| `total_debt` | Required for debt validation; unavailable until exact aggregate is present or a deterministic debt aggregation policy is approved. |
| `long_term_debt` | Useful but not mandatory for first MVP if `total_debt` is unavailable; should not be silently substituted. |

Smallest acceptable MVP decision:

```text
Do not infer total_debt or long_term_debt from narrower debt rows.
Return debt validation unavailable unless an exact aggregate or approved deterministic aggregate exists.
```

## 8. Remediation Priorities

### P0: Clean Revenue, PAT, Operating Profit, And Total Assets

Impact:

- Unlocks core forecast baseline.
- Enables revenue growth, profitability, margin, and asset-growth checks.
- Reduces risk of materially wrong validation conclusions.

Required remediation:

1. Primary-statement source precedence for headline metrics.
2. Series-level scale-consistency gate.
3. Candidate-spread blocking rule.
4. Note-vs-statement override rule.
5. Baseline-not-validatable outcome for unresolved cases.

Expected result:

At least revenue, PAT, operating profit, and total assets should either:

- pass the Forecast Validation input contract, or
- be explicitly unavailable/review-gated.

No selected value should be allowed to silently fail the scale-consistency contract.

### P1: Clean Cash And Operating Cash Flow

Impact:

- Enables liquidity, cash conversion, and debt service validation.
- Improves mixed financial/insight reasoning.

Required remediation:

1. Source policy for cash: balance sheet cash as headline, cash-flow ending cash as reconciliation.
2. Source policy for operating cash flow: cash-flow statement or trusted summary only.
3. Reject wrong table-type candidates for headline cash-flow metrics.

Expected result:

Cash and operating cash flow become usable for either:

- clean MVP validation, or
- explicitly review-gated validation.

### P2: Decide Debt And Equity Availability Policy

Impact:

- Enables debt consistency and balance sheet equation checks.
- Avoids false confidence from narrow debt substitutes.

Required remediation:

1. Define whether `total_debt` can be constructed from short-term debt, long-term debt, leases, and current portion.
2. Define whether `total_equity` maps to `equity`, `share_capital_and_reserves`, or another canonical aggregate.
3. Until policies are approved, return debt/equity validations as unavailable.

Expected result:

Debt/equity checks become honest and non-misleading, even if initially unavailable.

## 9. Smallest Set Of Fixes Required For Forecast Validation MVP

The smallest viable remediation set is not to solve every OCR issue. It is to guarantee that Forecast Validation never runs financial-plausibility rules on corrupted baselines.

### Fix 1: Pre-Validation Historical Series Integrity Gate

Before any YoY, CAGR, margin, or forecast plausibility calculation, every requested series must be classified:

| Status | Meaning |
|---|---|
| `clean` | Safe for Forecast Validation calculations. |
| `clean_with_warning` | Usable with caveats; not for high-stakes forecast assertions. |
| `baseline_not_validatable` | Do not run numeric validation rules. |
| `missing` | Exact canonical series unavailable. |

This satisfies the architecture review’s Must-Fix requirement to distinguish data-integrity failure from forecast failure.

### Fix 2: Candidate Selection Policy For Headline Metrics

For headline financial metrics:

1. Prefer primary statement source over note disclosure.
2. Prefer exact headline table type over analysis/ratio/supporting schedule.
3. Prefer consistent scale across years over isolated high-confidence normalization.
4. Treat candidate spread above 100x as blocking.
5. Do not let `normalization_confidence=1.0` override source quality.

This directly targets revenue, PAT, operating profit, total assets, cash, and operating cash flow.

### Fix 3: Note-Vs-Statement Guardrail

For headline metrics, note disclosures may support or explain the value, but should not replace the primary statement value unless:

- no primary statement candidate exists, or
- the note candidate is explicitly linked to the statement line, and
- it passes scale consistency.

This directly addresses the revenue issue where note-derived values outranked primary income-statement candidates.

### Fix 4: Scale And Unit Consistency Contract

Each series entering Forecast Validation must carry one consistent:

- unit,
- scale,
- currency,
- statement scope,
- source lineage.

If the selected series mixes thousands, millions, full rupees, percentages, ratios, or analysis-table values, the series must be rejected as `baseline_not_validatable`.

### Fix 5: Missing Critical Metric Policy

For `total_equity`, `total_debt`, and `long_term_debt`:

- Do not silently substitute nearby metrics.
- Do not infer aggregates without an approved deterministic policy.
- Mark affected validation categories unavailable.

This prevents Forecast Validation from producing clean-looking debt or equity conclusions from incomplete source data.

## 10. Remediation Classification By Metric

| Metric | Primary Issue | Fixability | Forecast Validation MVP Status After Minimal Fixes |
|---|---|---|---|
| `revenue` | Note-vs-statement and consolidation selection error with scale corruption | Policy-fixable | Must be fixed or blocked. |
| `profit_after_tax` | Source ambiguity and scale-corrupted candidates | Policy-fixable with review fallback | Must be fixed or blocked. |
| `operating_profit` | Unresolved source ambiguity | Policy-fixable with review fallback | Must be fixed or blocked. |
| `total_assets` | Consolidation selection and scale inconsistency | Policy-fixable | Must be fixed or blocked. |
| `cash_and_cash_equivalents` | Source ambiguity and conflicting candidates | Policy-fixable/review-only | Can be review-gated in MVP. |
| `operating_cash_flow` | Wrong source lineage and scale inconsistency | Policy-fixable | Should be fixed for MVP liquidity checks; otherwise review-gated. |
| `gross_profit` | Source ambiguity and scale candidates | Policy-fixable/review-only | Needed for margin checks; can be secondary after revenue/PAT. |
| `earnings_per_share` | Selected values clean; rejected candidates scale-corrupted | Automatically guarded | Safe, with provenance warning. |
| `total_equity` | Exact metric missing | Review-only until policy approved | Unavailable. |
| `total_debt` | Exact metric missing | Review-only until policy approved | Unavailable. |
| `long_term_debt` | Exact metric missing | Review-only until policy approved | Unavailable. |

## 11. Recommended Execution Order

### Step 1: Define The Gate

Define the Forecast Validation historical-series gate using the scale audit vocabulary:

- `safe_for_forecast_validation`
- `requires_review`
- `baseline_not_validatable`
- `missing`

This can be done before correcting any upstream data.

### Step 2: Apply Headline Source Policy

Prioritize:

1. `revenue`
2. `profit_after_tax`
3. `operating_profit`
4. `total_assets`
5. `operating_cash_flow`
6. `cash_and_cash_equivalents`

This creates the largest business impact with the smallest policy surface.

### Step 3: Reclassify Note Disclosures As Support, Not Headline Source

For headline metrics, notes should become supporting evidence unless no primary statement value exists.

### Step 4: Re-run Scale Consistency Audit

The remediation is successful only if the next audit shows:

| Requirement | Target |
|---|---|
| Revenue | `safe_for_forecast_validation` or explicitly `baseline_not_validatable` |
| PAT | `safe_for_forecast_validation` or explicitly `baseline_not_validatable` |
| Operating profit | `safe_for_forecast_validation` or explicitly `baseline_not_validatable` |
| Total assets | `safe_for_forecast_validation` or explicitly `baseline_not_validatable` |
| Operating cash flow | `safe_for_forecast_validation` or explicitly `baseline_not_validatable` |
| Cash | `safe_for_forecast_validation`, `clean_with_warning`, or explicitly review-gated |
| Critical unresolved conflicts | No silent use in numeric validation |
| Candidate spread above 100x | Blocks validation |

### Step 5: Freeze MVP Scope Based On Clean Series Only

The Forecast Validation MVP should not claim support for metrics that still fail the gate.

## 12. Final Recommendation

Do not begin Forecast Validation MVP rule implementation by writing growth, CAGR, margin, or plausibility rules over the current selected consolidated values.

The smallest safe path is:

1. Add the historical-series integrity gate to the architecture contract.
2. Define deterministic headline source-selection policy.
3. Fix or block the six highest-impact series:
   - `revenue`
   - `profit_after_tax`
   - `operating_profit`
   - `total_assets`
   - `cash_and_cash_equivalents`
   - `operating_cash_flow`
4. Treat missing `total_debt`, `long_term_debt`, and `total_equity` as unavailable until explicit aggregation policies are approved.
5. Re-run the scale consistency audit and only then freeze Forecast Validation MVP inputs.

Until that happens, the correct Forecast Validation result for most current core series is:

```text
baseline_not_validatable_due_to_historical_series_integrity
```

not a passed or failed forecast reasonableness conclusion.
