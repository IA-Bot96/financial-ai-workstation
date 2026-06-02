# Forecast Validation Contract Decisions

**Decision date:** 2026-06-02  
**Purpose:** Define the authoritative contracts required before Forecast Validation Phase 2 implementation begins.

This is a decision document. It contains no implementation plan, code, refactoring proposal, or rule logic.

## Source Artifacts

- `forecast_validation_architecture_review.md`
- `forecast_validation_preimplementation_review.md`
- `forecast_validation_mvp_rescoping.md`
- `financial_series_integrity_implementation_design.md`
- `output/historical_series_integrity_gate_report.json`

Note: the requested source `historical_series_integrity_implementation_design.md` is not present in the workspace. The available and referenced design artifact is `financial_series_integrity_implementation_design.md`.

## Current Baseline

The Historical Series Integrity Gate currently reports the following on the latest Lucky production bundle:

| Status | Count | Metrics |
|---|---:|---|
| `clean` | 0 | None |
| `clean_with_warning` | 1 | `earnings_per_share` |
| `baseline_not_validatable` | 7 | `revenue`, `profit_after_tax`, `operating_profit`, `total_assets`, `cash_and_cash_equivalents`, `operating_cash_flow`, `gross_profit` |
| `missing` | 3 | `total_debt`, `long_term_debt`, `total_equity` |

Forecast Validation must treat this gate result as binding. Numeric validation rules must not run over blocked or missing baselines.

## 1. Selected Value Ownership

### Decision

For Forecast Validation, **HistoricalSeriesIntegrityGate owns validation admission and validation-selected baseline eligibility**.

The underlying value candidates remain sourced from:

1. `FinancialYearConsolidationResult` for selected values and competing candidates.
2. `CompanyKnowledgeBase` / Query Engine datasets for retrieval, citations, and user-facing evidence.

Query Engine Retrieval does not own Forecast Validation selected-value eligibility.

### Source Of Truth

| Concern | Authoritative Owner |
|---|---|
| Raw consolidated selected value | `FinancialYearConsolidationResult.metric_values` |
| Competing candidates and conflicts | `FinancialYearConsolidationResult.groups` |
| Forecast Validation admission | `HistoricalSeriesIntegrityGate` |
| Workbook cell mappings and user-facing citations | Query Engine input bundle / `CompanyKnowledgeBase` |
| Query response retrieval | Query Engine Retrieval |
| Forecast Validation scorecard outcome | Forecast Validation Engine |

### Rationale

The architecture reviews showed that a value can be consolidated, retrievable, and highly normalized while still being invalid for forecast validation. Examples include:

- resolved conflicts that remain scale-corrupted
- high-confidence note fragments selected over primary-statement values
- statement scope remaining `unknown`
- same-year candidate spreads above 100x

Therefore Forecast Validation must not treat Query Engine retrieval success as baseline validity. Retrieval answers "what value is in the knowledge base?" The integrity gate answers "may this value be used as a forecast-validation baseline?"

### Downstream Implications

- Phase 2 must run or consume the gate result before any validation rule executes.
- Query Engine retrieval may be used to fetch values, but Forecast Validation must filter them through gate status.
- If Query Engine retrieval returns a metric whose gate status is `baseline_not_validatable` or `missing`, the validation category must be skipped.
- If the gate identifies a better candidate than the workbook-selected value, Forecast Validation may surface it as evidence, but must not pretend it has workbook-cell citation coverage unless a mapping exists.
- Future LLM layers may summarize gate decisions but may not override them.

## 2. Citation Contract

### Citation Types

Forecast Validation evidence must use one or more of the following citation types.

| Citation Type | Meaning | Allowed Usage |
|---|---|---|
| `WORKBOOK_CELL` | Value is written to the generated workbook and has a persisted cell mapping. | Selected workbook values, Query Engine retrieved values with mappings. |
| `PDF_PROVENANCE` | Value has source report year, page number, table type, and source label, but no workbook cell mapping. | Competing candidates, gate-selected overrides, blocked baseline evidence. |
| `GATE_OVERRIDE` | Gate policy identifies or prefers a candidate different from the workbook/consolidation selected value. | Evidence only unless a future explicit override policy is approved. |
| `NONE` | No reliable citation exists. | Missing metrics, absent evidence, forecast input rows without source reference. |

### Workbook-Selected Values

Workbook-selected values must cite `WORKBOOK_CELL` when a mapping exists.

Required evidence:

- workbook fingerprint
- sheet name
- cell reference
- metric
- value year
- source report year
- page number when available
- table type

If workbook mapping is unavailable, the value may fall back to `PDF_PROVENANCE`, but the evidence must explicitly state `workbook_cell_missing`.

### Gate-Selected Override Values

Gate-selected override values must cite `GATE_OVERRIDE` plus `PDF_PROVENANCE`.

They must not cite `WORKBOOK_CELL` unless that exact candidate has a persisted workbook cell mapping.

Required evidence:

- upstream selected candidate
- gate-preferred candidate
- reason for override or preference
- source report year
- page number
- table type
- candidate spread or source-policy evidence
- statement that workbook-cell citation is unavailable when applicable

MVP behavior: gate overrides may support skip/readiness decisions. They must not become silent replacement values for forecast calculations.

### Missing Values

Missing values must cite `NONE`.

Required evidence:

- canonical metric requested
- missing status
- statement that no substitute was used
- affected validation categories

### `baseline_not_validatable` Values

Blocked baselines must cite the strongest available evidence:

1. `WORKBOOK_CELL` if the blocked selected value has a workbook mapping.
2. `PDF_PROVENANCE` for selected and competing candidates.
3. `GATE_OVERRIDE` if the gate identified an alternate candidate or source-policy issue.

Required evidence:

- gate status
- blocking issue types
- selected value when available
- competing candidates when available
- candidate spread / YoY scale checks when available
- source policy violations
- conflict status

## 3. Confidence Composition Contract

### Decision

Gate confidence and validation confidence are separate but composed.

`ValidationConfidence` must be capped by `GateConfidence` for metric-specific validations.

### Composition Method

For a validation rule involving one metric:

```text
validation_confidence = min(rule_confidence, gate_confidence, evidence_confidence)
```

For a validation rule involving multiple metrics:

```text
validation_confidence = min(rule_confidence, all_required_metric_gate_confidences, evidence_confidence)
```

If any required metric is `baseline_not_validatable` or `missing`, the rule must not execute. The result becomes `SKIPPED`, and confidence describes confidence in the skip decision, not confidence in a forecast conclusion.

### Confidence Ceilings

| Baseline Status | Validation Confidence Ceiling | Behavior |
|---|---:|---|
| `clean` | 1.00 | Full deterministic validation may run. |
| `clean_with_warning` | 0.80 | Validation may run only for categories that do not require blocked companion metrics. |
| `baseline_not_validatable` | No numeric validation | Rule must be skipped. Skip confidence may be high. |
| `missing` | No numeric validation | Rule must be skipped. Missing evidence confidence may be high. |

### Blocking Behavior

- Critical gate issues block downstream validation regardless of any high validation or rule confidence.
- Validation confidence cannot downgrade a critical gate issue into a warning.
- A skipped result can have high confidence if the skip reason is well evidenced.
- LLM-generated narrative confidence cannot increase deterministic validation confidence.

### Examples

| Scenario | Gate Status | Rule Outcome | Confidence Behavior |
---|---|---|---|
| EPS standalone baseline check | `clean_with_warning`, gate confidence 0.80 | `WARNING` or admitted with warning | validation confidence capped at 0.80 |
| EPS-vs-PAT consistency | EPS `clean_with_warning`, PAT `baseline_not_validatable` | `SKIPPED` | skip confidence may be high; no EPS/PAT calculation |
| Revenue growth | revenue `baseline_not_validatable` | `SKIPPED` | no YoY/CAGR calculation |
| Debt validation | `total_debt` missing | `SKIPPED` | missing evidence confidence may be 1.00 |

## 4. Forecast Validation MVP Scope

### Executable MVP Categories

| Category | Required Metrics | Gate Status Requirement | Rationale |
|---|---|---|---|
| Historical baseline readiness | All MVP metrics | Any status accepted for reporting | This category reports gate status itself and does not perform forecast math. |
| Validation category admission | Category-specific required metrics | Any status accepted for admission/skip decision | Determines whether a category may execute. |
| EPS standalone baseline | `earnings_per_share` | `clean` or `clean_with_warning` | EPS is currently the only admitted historical series. |
| Forecast input completeness | Forecast input rows | Forecast metric must resolve; historical gate may be any status for comparability classification | Input shape checks do not require historical calculations. |
| Evidence and provenance completeness | Gate evidence, workbook/PDF provenance | Any status accepted for evidence reporting | Evidence reporting is required for both admitted and skipped categories. |

### Deferred Categories

| Category | Required Metrics | Gate Status Requirement | Rationale |
|---|---|---|---|
| Revenue growth consistency | `revenue` | `clean` or `clean_with_warning` | Current revenue is `baseline_not_validatable`. |
| Forecast plausibility for revenue | `revenue` plus forecast revenue | `revenue` admitted by gate | Current revenue baseline cannot support plausibility math. |
| Trend-break validation | target metric | target metric admitted by gate and sufficient history | Current core targets are blocked except EPS. |
| Insight-supported plausibility | metric plus relevant insights | metric admitted by gate and insight evidence frozen | Narrative support cannot compensate for invalid numeric baseline. |

### Blocked Categories

| Category | Required Metrics | Current Blocker | Rationale |
|---|---|---|---|
| Margin consistency | `revenue`, `gross_profit`, `operating_profit`, `profit_after_tax` | required profitability metrics blocked | Margin math over corrupted series is misleading. |
| EPS consistency against PAT | `earnings_per_share`, `profit_after_tax` | PAT blocked | EPS can be reported alone, not reconciled to PAT. |
| Cash-flow consistency | `operating_cash_flow`, `cash_and_cash_equivalents`, `profit_after_tax` | all three are blocked or partly blocked | No reliable cash/profit baseline. |
| Balance-sheet equation validation | `total_assets`, `total_equity`, liabilities/debt as applicable | total assets blocked, total equity missing | Required statement components unavailable. |
| Debt consistency | `total_debt`, `long_term_debt` | exact debt metrics missing | No silent substitution allowed. |

## 5. Missing Metric Policy

### `total_debt`

Decision: `SKIPPED`, not warning and not fail.

Rationale:

- Exact canonical `total_debt` is missing.
- No approved aggregate policy exists.
- Narrower metrics such as current finance, borrowings, lease liabilities, or debt ratios must not be silently substituted.

Affected categories:

- debt consistency
- debt-to-equity
- leverage
- interest coverage where broad debt is required
- debt-related forecast plausibility

### `long_term_debt`

Decision: `SKIPPED`, not warning and not fail.

Rationale:

- Exact canonical `long_term_debt` is missing.
- Current portion of long-term debt is not a valid substitute.
- Note-derived debt components require a separate approved component policy.

Affected categories:

- debt maturity structure
- long-term leverage
- debt forecast validation

### `total_equity`

Decision: `SKIPPED`, not warning and not fail.

Rationale:

- Exact canonical `total_equity` is missing.
- `share_capital_and_reserves` may be related but is not an approved automatic substitute.
- Balance-sheet equation validation requires exact or policy-approved equity.

Affected categories:

- balance-sheet equation
- debt-to-equity
- ROE checks
- equity forecast plausibility

## 6. Baseline Status Contract

### `clean`

Allowed validations:

- numeric historical calculations
- forecast plausibility checks
- trend-break checks
- cross-metric validations when companion metrics are also admitted

Prohibited validations:

- none by baseline status alone

Evidence requirements:

- selected value per year
- citations or source provenance
- conflict status
- confidence

Expected outcome:

- rule may return `PASS`, `WARNING`, `FAIL`, or `SKIPPED` depending on rule result.

### `clean_with_warning`

Allowed validations:

- standalone validation for that metric
- numeric validation when all companion metrics are `clean` or `clean_with_warning`
- scorecard reporting with confidence ceiling

Prohibited validations:

- validation requiring any blocked or missing companion metric
- high-confidence pass claims above the baseline confidence ceiling

Evidence requirements:

- all `clean` evidence
- warning issue details
- confidence ceiling applied

Expected outcome:

- rule may run with warning-level confidence.
- category must surface baseline warnings.

### `baseline_not_validatable`

Allowed validations:

- readiness reporting
- skip decision generation
- evidence/provenance reporting

Prohibited validations:

- YoY growth
- CAGR
- margin calculations
- trend-break calculations
- forecast plausibility comparisons
- cross-metric consistency checks

Evidence requirements:

- blocking issue types
- gate evidence ids
- selected and competing candidates where available
- source policy violations where available
- explicit skip reason

Expected outcome:

- category returns `SKIPPED` with reason `historical_baseline_not_validatable`.
- it must not return forecast `FAIL`, because the forecast was not evaluated.

### `missing`

Allowed validations:

- readiness reporting
- missing metric reporting
- category skip decision

Prohibited validations:

- all numeric validations for that metric
- substitute-based calculations unless a separately approved policy exists

Evidence requirements:

- exact canonical metric missing
- no substitute used
- affected categories

Expected outcome:

- category returns `SKIPPED` with reason `required_metric_missing`.

## 7. Forecast Validation Admission Contract

Before any validation rule executes, all conditions must pass.

### Required Conditions

1. Metric resolves to an exact canonical metric required by the rule.
2. Metric exists in the gate result.
3. Gate status is `clean` or `clean_with_warning`.
4. All companion metrics required by the rule are also `clean` or `clean_with_warning`.
5. Required historical years are present in the admitted series.
6. Required values are numeric where the rule requires math.
7. Source provenance is available.
8. Evidence ids can be attached to the result.
9. Citation behavior is honest:
   - workbook cell citation only when mapping exists
   - PDF provenance otherwise
10. Forecast input rows, if present, provide metric, forecast year, value, and source/scale metadata when available.

### Admission Outcomes

| Admission Result | Meaning |
|---|---|
| `ADMITTED` | Rule may execute. |
| `ADMITTED_WITH_WARNING` | Rule may execute with confidence ceiling and warning evidence. |
| `SKIPPED_BASELINE_NOT_VALIDATABLE` | Historical baseline blocks execution. |
| `SKIPPED_REQUIRED_METRIC_MISSING` | Exact required metric is absent. |
| `SKIPPED_INSUFFICIENT_HISTORY` | Metric is admitted but required years are unavailable. |
| `SKIPPED_FORECAST_INPUT_INVALID` | Forecast input contract fails. |

Forecast Validation Phase 2 must implement admission behavior before implementing any forecast plausibility rule.

## 8. Freeze Acceptance Criteria

### Phase 2 Implementation May Begin When

- This contract decision document is accepted as authoritative.
- `HistoricalSeriesIntegrityGate` remains the admission authority.
- Selected-value ownership is agreed:
  - consolidation owns candidates
  - gate owns validation admission
  - Query Engine owns retrieval/citation plumbing
- Citation types are implemented in the evidence model or mapped from existing models.
- Confidence composition is implemented or explicitly represented.
- MVP scope is limited to gate-first readiness, category admission, EPS standalone baseline, input contract checks, and evidence/provenance reporting.

### MVP May Freeze When

| Freeze Criterion | Required Result |
|---|---|
| Gate-first ordering | 100% of validation runs execute admission before rules |
| Blocked baseline handling | 0 calculations over `baseline_not_validatable` metrics |
| Missing metric handling | 0 silent substitutions |
| Category admission | 100% deterministic category admitted/skipped decisions |
| Citation honesty | 100% workbook citations reference actual workbook mappings |
| PDF provenance fallback | Available for gate-selected or competing candidates without workbook cells |
| Confidence contract | Gate confidence ceilings are applied and tested |
| Evidence coverage | 100% of issues and skipped categories reference evidence |
| Scorecard clarity | Scorecard separates data-baseline skips from forecast failures |
| Regression tests | Cover `clean`, `clean_with_warning`, `baseline_not_validatable`, and `missing` |

### Post-Freeze Expansion Conditions

Deferred numeric categories may be added only when:

1. Required metrics become `clean` or `clean_with_warning`.
2. An analyst truth set validates gate decisions for those metrics.
3. Missing metric policies are approved for debt/equity aggregates if exact metrics remain absent.
4. Multi-report source-report-year semantics are defined when multiple annual reports are loaded.

## 9. Final Decision Summary

These decisions are binding for Forecast Validation Phase 2, Phase 3+, and future LLM layers.

1. **HistoricalSeriesIntegrityGate is the Forecast Validation admission authority.**
2. **FinancialYearConsolidationResult remains the source of selected and competing candidates.**
3. **Query Engine Retrieval does not determine whether a value is validatable.**
4. **Query Engine / CompanyKnowledgeBase remains the source for workbook mappings and citation plumbing.**
5. **No numeric validation rule may run on `baseline_not_validatable` or `missing` metrics.**
6. **`clean_with_warning` metrics may run only with a confidence ceiling and warning evidence.**
7. **EPS standalone baseline reporting is executable today; EPS-vs-PAT is deferred.**
8. **Revenue, margin, cash-flow, debt, balance-sheet, trend-break, and broad forecast plausibility categories are deferred or skipped until required metrics pass the gate.**
9. **Missing `total_debt`, `long_term_debt`, and `total_equity` produce `SKIPPED`, not fail, warning, or inferred substitute.**
10. **Workbook-cell citations are allowed only for values with persisted mappings.**
11. **Gate-selected override values must use `GATE_OVERRIDE` and `PDF_PROVENANCE`, not fake workbook citations.**
12. **Gate confidence caps validation confidence for metric-specific rules.**
13. **Critical gate issues always block downstream validation regardless of confidence.**
14. **Skipped categories must be evidenced and visible in the scorecard.**
15. **Future LLM layers may summarize but may not alter admission decisions, calculations, citations, or severity.**

The practical Phase 2 target is therefore:

```text
Forecast Validation admission, readiness, evidence, citation, confidence, and scorecard infrastructure.
```

It is not yet:

```text
Full historical performance and forecast plausibility validation.
```
