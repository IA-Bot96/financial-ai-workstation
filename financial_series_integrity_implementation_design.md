# Financial Series Integrity Implementation Design

## 1. Purpose

This document designs the minimum implementation required to satisfy the Forecast Validation MVP input contract for historical financial series.

Source artifacts:

- `financial_series_integrity_remediation_plan.md`
- `output/scale_consistency_audit.json`
- Latest Lucky production bundle:
  `output/lucky_full_ocr_after_regression_fixes_20260602T133227682153_d80f3614.kb.json`

This is design only. It does not contain code or implementation instructions.

## 2. Problem Statement

Forecast Validation cannot safely run YoY growth, CAGR, margin, cash-flow, debt, or plausibility rules over the current selected consolidated values without a historical-series data-integrity gate.

The latest Lucky scale audit found:

| Measure | Result |
|---|---:|
| Core metrics audited | 11 |
| Exact series found | 8 |
| Exact series missing | 3 |
| Total anomalies | 51 |
| Critical anomalies | 50 |
| High anomalies | 1 |
| Safe for Forecast Validation | 1 metric |
| Requires review | 10 metrics |

The minimum design objective is therefore:

```text
Do not let corrupted or ambiguous historical baselines enter Forecast Validation calculations.
```

The first deliverable is not better forecast scoring. It is a reliable gate that classifies each historical series as clean, usable with warnings, invalid, or missing.

## 3. Design Principles

1. **Gate before calculate.** Series integrity must run before YoY, CAGR, margin, forecast, or trend calculations.
2. **Selected value is not automatically trusted.** A consolidated value can be selected and still fail integrity checks.
3. **Resolved conflict is not the same as clean.** `unresolved_conflict=false` is necessary but not sufficient.
4. **Normalization confidence is not source quality.** A high-confidence note label must not outrank a cleaner primary-statement value by itself.
5. **Source precedence is metric-specific.** Revenue, PAT, assets, cash, and OCF have different acceptable source tables.
6. **Missing critical metrics must stay missing.** Do not silently substitute `current_portion_long_term_debt` for `total_debt`.
7. **Every decision must be evidenced.** The gate must explain why a series was accepted, warned, blocked, or marked missing.

## 4. Scope

In scope:

- `HistoricalSeriesIntegrityGate`
- `HeadlineMetricSelectionPolicy`
- `NoteVsStatementGuardrail`
- `ScaleConsistencyContract`
- `MissingMetricPolicy`
- Evidence outputs for Forecast Validation MVP

MVP target metrics:

- `revenue`
- `profit_after_tax`
- `operating_profit`
- `total_assets`
- `cash_and_cash_equivalents`
- `operating_cash_flow`
- `gross_profit`
- `earnings_per_share`
- `total_debt`
- `long_term_debt`
- `total_equity`

Out of scope:

- OCR extraction changes.
- Normalization threshold changes.
- New canonical metric registry expansion.
- Forecast generation.
- LLM explanations.
- Analyst approval workflow.
- Sector-specific forecast rules.

## 5. Inputs And Source Fields

Primary input:

| Input | Usage |
|---|---|
| `CompanyKnowledgeBase` | Root immutable Query Engine object. |
| `FinancialDataset` | Selected consolidated rows. |
| `ConflictDataset` | Consolidation groups and competing candidates. |
| `WorkbookCellMapping` | Workbook citation references. |

The gate should operate on the same fields already present in the production `.kb.json`:

| Field | Usage |
|---|---|
| `metric` | Canonical metric key. |
| `value_year` | Chronological series key. |
| `value` | Numeric value candidate. |
| `source_report_year` | Provenance and source-of-truth context. |
| `page_number` | PDF citation/provenance. |
| `table_type` | Source-table classification. |
| `source_class` | Primary statement, note disclosure, analysis/ratio, schedule, unclassified. |
| `statement_scope` | Consolidated, standalone, or unknown. |
| `normalization_confidence` | Normalization quality signal. |
| `requires_review` | Existing normalization/review gate. |
| `conflict_status` | Consolidation conflict state. |
| `unresolved_conflict` | Whether conflict remains unresolved. |
| `resolution_reason` | Why the current selected value was selected. |
| `candidate_count` | Number of candidates in the group. |
| `competing_candidates` | Alternative values and provenance. |
| `workbook_citation` | Sheet/cell evidence for selected values. |

## 6. Output Statuses

The gate assigns one status per canonical metric series.

| Status | Meaning | Forecast Validation Behavior |
|---|---|---|
| `clean` | Series satisfies the MVP input contract. | Numeric validation may run. |
| `clean_with_warning` | Series is usable, but has non-blocking limitations. | Numeric validation may run with warnings and lower confidence. |
| `baseline_not_validatable` | Series exists but fails integrity checks. | Numeric validation must not run. |
| `missing` | Exact canonical series is unavailable. | Category is unavailable; no substitute is silently used. |

Status assignment is deterministic.

## 7. Conceptual Models

These are design-level models. Concrete Pydantic/dataclass definitions belong in the implementation phase.

### HistoricalSeriesIntegrityGateResult

Purpose:

Root result for a gate run.

Fields:

| Field | Description |
|---|---|
| `company_name` | Company being validated. |
| `workbook_id` | Query Engine workbook id. |
| `workbook_fingerprint` | Bundle/workbook fingerprint. |
| `metrics_evaluated` | Canonical metric keys evaluated. |
| `series_results` | One `HistoricalSeriesIntegrityResult` per metric. |
| `overall_status` | Worst status across required metrics. |
| `clean_metrics` | Metrics that passed. |
| `warning_metrics` | Metrics that passed with warnings. |
| `blocked_metrics` | Metrics classified as `baseline_not_validatable`. |
| `missing_metrics` | Metrics classified as `missing`. |
| `critical_issue_count` | Count of blocking issues. |
| `warning_count` | Count of non-blocking issues. |
| `evidence` | Shared evidence records. |

### HistoricalSeriesIntegrityResult

Purpose:

One metric-level series decision.

Fields:

| Field | Description |
|---|---|
| `metric` | Canonical metric key. |
| `status` | `clean`, `clean_with_warning`, `baseline_not_validatable`, or `missing`. |
| `value_years` | Years available after policy evaluation. |
| `selected_series` | Final candidate selected per year for validation, if status permits. |
| `rejected_candidates` | Candidates rejected by policy. |
| `issues` | Blocking and warning issues. |
| `scale_result` | Scale consistency decision. |
| `source_policy_result` | Headline source-selection decision. |
| `note_guardrail_result` | Note-vs-statement decision. |
| `missing_metric_result` | Missing metric decision, if applicable. |
| `confidence` | Gate confidence in the status. |
| `validation_readiness` | Whether Forecast Validation may calculate over the series. |

### SeriesValueCandidate

Purpose:

Comparable representation of selected and competing consolidation candidates.

Fields:

| Field | Description |
|---|---|
| `candidate_id` | Deterministic candidate id. |
| `metric` | Canonical metric key. |
| `original_metric` | Raw or reconstructed source label. |
| `value_year` | Financial year represented. |
| `value` | Candidate value. |
| `source_report_year` | Source report year. |
| `page_number` | PDF page. |
| `table_type` | Table classification. |
| `source_class` | Source class. |
| `statement_scope` | Consolidated, standalone, unknown. |
| `normalization_confidence` | Normalization confidence. |
| `requires_review` | Existing review flag. |
| `is_currently_selected` | Whether upstream consolidation selected this candidate. |
| `workbook_citation` | Workbook citation if available. |

### HeadlineMetricSelectionDecision

Purpose:

Explain which candidate should represent a headline metric for a given year.

Fields:

| Field | Description |
|---|---|
| `metric` | Canonical metric. |
| `value_year` | Year selected. |
| `selected_candidate` | Candidate chosen by the policy. |
| `upstream_selected_candidate` | Candidate selected by consolidation. |
| `decision_status` | `accepted_upstream`, `overrode_upstream`, `blocked`, or `no_candidate`. |
| `selection_reason` | Deterministic reason. |
| `rejected_candidates` | Candidates rejected and reasons. |
| `source_precedence_score` | Deterministic source score. |
| `scale_consistency_score` | Series-level scale score contribution. |
| `requires_review` | Whether analyst review is required. |

### ScaleConsistencyResult

Purpose:

Series-level scale/unit decision.

Fields:

| Field | Description |
|---|---|
| `metric` | Canonical metric. |
| `status` | `pass`, `warning`, or `fail`. |
| `candidate_spread_max` | Maximum same-year candidate spread. |
| `yoy_ratio_max` | Maximum selected-series YoY magnitude ratio. |
| `scale_inconsistency_years` | Years with scale problems. |
| `blocking_reasons` | Reasons that prevent validation. |
| `warning_reasons` | Non-blocking warnings. |
| `evidence` | Values and candidates used. |

### IntegrityIssue

Purpose:

One gate issue.

Fields:

| Field | Description |
|---|---|
| `issue_type` | `scale_inconsistency`, `source_ambiguity`, `missing_metric`, `note_statement_conflict`, `unresolved_conflict`, `review_gated_value`, `insufficient_history`. |
| `severity` | `info`, `warning`, `high`, `critical`. |
| `metric` | Affected metric. |
| `value_years` | Affected years. |
| `description` | Human-readable issue. |
| `blocking` | Whether this issue blocks Forecast Validation. |
| `fixability` | `automatic`, `policy`, or `review_only`. |
| `evidence_refs` | Linked evidence records. |

### IntegrityEvidence

Purpose:

Evidence that supports a gate decision.

Fields:

| Field | Description |
|---|---|
| `evidence_id` | Deterministic id. |
| `metric` | Canonical metric. |
| `value_year` | Year. |
| `candidate_values` | Selected and competing values. |
| `calculations` | Spread and YoY ratios. |
| `citations` | Workbook/PDF citations. |
| `provenance` | Page, table, source class, report year, scope. |
| `policy_applied` | Selection/scale/missing policy used. |

## 8. HistoricalSeriesIntegrityGate

### Responsibility

Classify historical series before Forecast Validation calculations run.

It answers:

```text
Can this canonical metric history be used as a forecast-validation baseline?
```

### Validation Flow

For each requested canonical metric:

1. **Load candidates**
   - Pull selected values from `FinancialDataset`.
   - Pull competing candidates from `ConflictDataset`.
   - Combine into a `SeriesValueCandidate` set.

2. **Apply MissingMetricPolicy**
   - If no exact canonical metric exists, return `missing`.
   - Do not substitute narrower/broader metrics unless a deterministic aggregate policy is explicitly approved.

3. **Evaluate candidate eligibility**
   - Remove non-numeric candidates for numeric validation.
   - Flag review-gated candidates.
   - Flag candidates with missing citations/provenance.

4. **Apply HeadlineMetricSelectionPolicy**
   - Select the best candidate per `value_year` for the requested headline metric.
   - Compare the policy-selected candidate against upstream consolidation selection.
   - Record whether the policy accepts, overrides, or blocks upstream selection.

5. **Apply NoteVsStatementGuardrail**
   - Prevent note disclosures from becoming headline values when acceptable primary-statement candidates exist.
   - Allow notes only under defined fallback conditions.

6. **Apply ScaleConsistencyContract**
   - Compute same-year candidate spread.
   - Compute selected-series YoY magnitude ratios.
   - Detect scale, unit, and source-lineage inconsistencies.

7. **Check history sufficiency**
   - Require at least two consecutive years for YoY validation.
   - Require at least three years for trend validation.
   - Prefer four or more years for CAGR validation.

8. **Assign status**
   - `missing` if exact metric is unavailable.
   - `baseline_not_validatable` if any blocking issue exists.
   - `clean_with_warning` if no blocking issue exists but warnings remain.
   - `clean` if all required checks pass.

9. **Emit evidence**
   - Every blocking or warning decision must include candidate values, calculations, citations, and provenance.

### Status Rules

| Condition | Status |
|---|---|
| Exact canonical metric absent | `missing` |
| Required years absent | `baseline_not_validatable` or `missing`, depending on whether any records exist |
| Same-year candidate spread `> 100x` | `baseline_not_validatable` |
| Unexplained YoY magnitude ratio `> 10x` | `baseline_not_validatable` |
| YoY magnitude ratio `5x - 10x` with clean source lineage | `clean_with_warning` |
| Candidate spread `10x - 100x` with clean selected candidate | `clean_with_warning` |
| Any selected value has unresolved conflict | `baseline_not_validatable` |
| Review-gated selected value in core metric | `baseline_not_validatable` |
| Note disclosure selected over valid primary statement value | `baseline_not_validatable` |
| Missing workbook/PDF citation | `clean_with_warning` if data is otherwise clean |
| Clean values, clean provenance, no conflicts | `clean` |

### Evidence Output

The gate output must include:

- Selected value per year.
- Upstream-selected value per year.
- Policy-selected value per year.
- Competing candidate values.
- Candidate spread by year.
- YoY magnitude ratio by transition.
- Source table and page for every value.
- Reason for accepting or rejecting each candidate.
- Whether the issue is automatic, policy-fixable, or review-only.

## 9. HeadlineMetricSelectionPolicy

### Responsibility

Select the deterministic headline candidate for key financial metrics when consolidation groups contain multiple values.

This policy does not rewrite OCR output. It chooses whether the existing upstream selected candidate is suitable for Forecast Validation. If it is not suitable, it either selects a better candidate or blocks the series.

### Global Precedence Signals

Applied to all headline metrics:

1. Exact canonical metric match.
2. Numeric value suitable for metric unit.
3. Source table allowed for the metric.
4. Source class allowed for the metric.
5. Primary statement source over note disclosure.
6. Same statement/source lineage across years.
7. Same unit/scale across years.
8. Lower candidate spread.
9. Higher normalization confidence.
10. Cleaner source label.
11. Latest source report year only after quality ties.

Normalization confidence is deliberately below source quality and scale consistency.

### Metric-Specific Precedence

#### Revenue

Allowed headline sources, in order:

1. `income_statement` with `source_class=primary_statement`.
2. Trusted annual summary only if no income statement candidate exists and scale is consistent.
3. Note disclosure only if no primary statement/summary candidate exists.

Preferred labels:

- `Revenue`
- `Net Revenue`
- `Turnover`
- `Turnover - Net`
- `Sales`

Blocking conditions:

- Note-derived `Revenue` selected while income-statement `Turnover` or `Net Revenue` exists.
- Balance-sheet-classified source used as headline revenue when income statement exists.
- Same-year candidate spread `>100x`.
- YoY movement `>10x` without a same-scale explanation.

Lucky-specific observed failure that this policy addresses:

2024 and 2025 revenue were selected from page 320 notes despite primary income-statement turnover candidates existing.

#### Profit After Tax

Allowed headline sources, in order:

1. `income_statement` primary statement.
2. Financial summary only when statement source is absent and scale is consistent.
3. Notes only as supporting evidence, not headline source.

Preferred labels:

- `Profit after taxation`
- `Profit after tax`
- `Profit for the year`
- `Net profit`
- `Profit attributable to owners`

Blocking conditions:

- Unresolved conflict on selected PAT.
- Candidate spread `>100x`.
- Analysis/summary value selected over primary statement PAT.
- Mixed scale across years.

#### Operating Profit

Allowed headline sources, in order:

1. `income_statement` primary statement.
2. Statement-derived operating results table.
3. Financial summary only with consistent scale and no primary statement candidate.

Preferred labels:

- `Operating Profit`
- `Operating Income`
- `Profit from Operations`
- `EBIT`, only if EBIT is explicitly equivalent in the report context.

Blocking conditions:

- Unresolved conflict.
- Candidate spread `>100x`.
- Selected candidate from analysis table when statement candidate exists.
- Negative/positive sign contradiction among equal-precedence candidates unless resolved by statement context.

#### Total Assets

Allowed headline sources, in order:

1. `balance_sheet` primary statement total assets row.
2. Statement of financial position primary statement.
3. Financial summary only if statement source is absent and scale is consistent.

Disallowed headline sources:

- `vertical_analysis`
- `horizontal_analysis`
- Ratio tables
- Note disclosure partial totals

Blocking conditions:

- Selected value comes from a partial balance-sheet section rather than total assets.
- Analysis-table values such as `100`, percentages, or horizontal-analysis values compete as candidates.
- Candidate spread `>100x`.
- YoY drop/jump `>10x` without clean source explanation.

Lucky-specific observed failure:

2024 and 2025 selected total assets were tens of millions while same-year competing primary-statement candidates were hundreds of billions.

#### Cash And Cash Equivalents

Allowed headline sources, in order:

1. `balance_sheet` cash and cash equivalents.
2. `cash_flow_statement` cash at end of period if it reconciles to the balance-sheet value.
3. Notes only as support or fallback when no primary statement value exists.

Blocking conditions:

- Selected candidate comes from `income_statement`.
- Balance-sheet and cash-flow statement values conflict above tolerance.
- Candidate spread `>100x`.
- Only note values exist without a statement-level value.

MVP behavior:

If balance sheet cash and cash-flow ending cash disagree materially, mark `baseline_not_validatable`. Do not choose one silently.

#### Operating Cash Flow

Allowed headline sources, in order:

1. `cash_flow_statement` primary statement.
2. Trusted cash-flow summary only if no statement source exists and scale is consistent.

Disallowed headline sources:

- `balance_sheet`
- `income_statement`
- notes, unless explicitly a cash-flow statement extract

Blocking conditions:

- Early years sourced from balance-sheet-classified tables while later years come from cash-flow statement.
- Candidate spread `>100x`.
- YoY jump/drop `>10x` caused by mixed source scale.

Lucky-specific observed failure:

2020-2023 operating cash flow values came from page 162 balance-sheet-classified data, while 2024-2025 came from cash-flow statement pages.

## 10. NoteVsStatementGuardrail

### Responsibility

Prevent note disclosures from replacing primary statement values for headline metrics.

### Policy

For headline metrics:

1. Notes are supporting evidence by default.
2. Notes may become headline only if no valid primary statement candidate exists.
3. Notes may become headline if the note is explicitly linked to the primary statement line and passes scale consistency.
4. A note candidate must not outrank a primary candidate solely because `normalization_confidence` is higher.

### Source Precedence

| Source Class / Table | Headline Priority |
|---|---:|
| Primary statement with correct table type | 100 |
| Statement summary with correct scale | 80 |
| Cash-flow/balance-sheet reconciliation source for matching metric | 75 |
| Supporting schedule | 50 |
| Note disclosure | 35 |
| Analysis/ratio table | 25 |
| Unclassified table | 10 |

Metric-specific table type must override generic source class. For example:

- `cash_and_cash_equivalents` from `income_statement` should be blocked even if `source_class=primary_statement`.
- `operating_cash_flow` from `balance_sheet` should be blocked.
- `total_assets` from `vertical_analysis` should be blocked even if normalized as `total_assets`.

### Guardrail Outcomes

| Outcome | Meaning |
|---|---|
| `statement_candidate_selected` | Primary statement candidate accepted. |
| `note_candidate_allowed` | Note candidate accepted because no primary candidate exists and scale is clean. |
| `note_candidate_blocked` | Note candidate rejected because primary candidate exists. |
| `source_ambiguous` | Multiple candidates remain plausible; analyst review required. |

### Evidence Requirements

For every note-vs-statement decision:

- Selected source class.
- Rejected source class.
- Page numbers.
- Table types.
- Values.
- Normalization confidence.
- Reason note was allowed or blocked.

## 11. ScaleConsistencyContract

### Responsibility

Decide whether a series uses one coherent financial scale and can support numeric validation.

### Same-Year Candidate Spread

For each `metric + value_year`, compute:

```text
candidate_spread = max(abs(candidate_values)) / min(abs(non_zero_candidate_values))
```

Thresholds:

| Spread | Status | Meaning |
|---:|---|---|
| `<= 5x` | Pass | Candidate values are broadly consistent. |
| `>5x and <=10x` | Warning | Potential source difference, not automatically blocking. |
| `>10x and <=100x` | Warning or block | Usable only if selected candidate is from the correct source and series is otherwise clean. |
| `>100x` | Block | Scale/source ambiguity too large for Forecast Validation. |

### YoY Magnitude Ratio

For adjacent selected values:

```text
yoy_magnitude_ratio = max(abs(current), abs(previous)) / min(abs(current), abs(previous))
```

Thresholds:

| Ratio | Status | Meaning |
|---:|---|---|
| `<= 5x` | Pass | No scale issue detected. |
| `>5x and <=10x` | Warning | Large movement; may be valid business event if supported. |
| `>10x and <=100x` | Block unless explicitly supported | Too large for default MVP baseline. |
| `>100x` | Block | Likely scale/source corruption. |

### Unit And Metric-Type Checks

Unit-aware rules:

| Metric Type | Scale Rule |
|---|---|
| Currency metrics | Must share consistent currency and scale. |
| EPS/per-share metrics | Must not receive currency table scaling. |
| Percentage metrics | Must not be mixed with currency values. |
| Ratio/times/day metrics | Must not be mixed with currency values. |
| Counts/headcount metrics | Must not be scaled as currency. |

Forecast Validation MVP should only accept series with unit-compatible selected values.

### Blocking Criteria

Block the series if any condition is true:

1. Same-year candidate spread `>100x`.
2. YoY magnitude ratio `>100x`.
3. YoY magnitude ratio `>10x` without explicit support.
4. Selected value is sourced from a disallowed table type for the metric.
5. Selected value is unresolved conflict.
6. Selected value is review-gated.
7. Unit type changes across years.
8. Currency changes across years.
9. Scale changes across years and cannot be reconciled deterministically.

### Warning Criteria

Mark `clean_with_warning` if:

1. Candidate spread is `>5x and <=10x`.
2. Candidate spread is `>10x and <=100x`, but source policy strongly supports the selected candidate.
3. YoY magnitude ratio is `>5x and <=10x`.
4. Workbook cell citation is missing but PDF provenance exists.
5. Statement scope is `unknown` but source table and scale are otherwise clean.

## 12. MissingMetricPolicy

### Responsibility

Define behavior when a required exact canonical metric is absent.

Affected metrics in latest Lucky bundle:

- `total_debt`
- `long_term_debt`
- `total_equity`

### Default Rule

If the exact canonical metric is absent:

```text
status = missing
validation_readiness = unavailable
```

No substitute is used unless a deterministic aggregate policy is separately approved.

### total_debt

Default MVP behavior:

- Missing if no exact `total_debt` exists.
- Do not substitute `current_portion_long_term_debt`.
- Do not substitute `short_term_borrowings`.
- Do not infer from debt-to-equity.

Future policy option:

`total_debt = short_term_debt + long_term_debt + current_portion_long_term_debt + lease_liabilities`

This requires all components to be clean and non-overlapping.

### long_term_debt

Default MVP behavior:

- Missing if no exact `long_term_debt` exists.
- Do not substitute current portion.
- Do not infer from notes unless source rows are clean and component policy exists.

### total_equity

Default MVP behavior:

- Missing if no exact `total_equity` exists.
- Do not silently substitute `share_capital_and_reserves` unless policy maps it as the report's equity aggregate.
- Do not substitute `total_equity_and_liabilities`.

Future policy option:

Allow `share_capital_and_reserves` as `total_equity` only when it is the primary statement equity aggregate and reconciles to assets minus liabilities.

## 13. Overall Gate Decision Logic

Metric-level status assignment:

```text
missing
  if exact canonical metric is absent

baseline_not_validatable
  if any critical/blocking issue exists

clean_with_warning
  if no blocking issue exists but warning issue exists

clean
  if exact metric exists and all required checks pass
```

Run-level status:

| Required Metrics | Overall Status |
|---|---|
| All required metrics clean | `clean` |
| Required metrics clean or clean_with_warning | `clean_with_warning` |
| Any required core metric baseline_not_validatable | `baseline_not_validatable` |
| Any required core metric missing | `missing_required_metric` |

Forecast Validation MVP should accept a run only when all metrics required by the requested validation category are `clean` or `clean_with_warning`.

## 14. Evidence Examples From Lucky

### Revenue

Current failure:

- 2024 selected: notes page 320, value `26,282,162`.
- Competing primary income-statement candidate exists: page 164, `Turnover`, value `115,324,942,000`.
- Resolution reason: `higher_normalization_confidence`.

Gate result:

```text
baseline_not_validatable
```

Issue:

```text
note_statement_conflict + candidate_spread_gt_100x
```

### Profit After Tax

Current failure:

- All years unresolved conflicts.
- 2021 selected value `14,070,189,000`; 2022 selected value `11,730`.
- YoY magnitude drop far above 100x.

Gate result:

```text
baseline_not_validatable
```

Issue:

```text
unresolved_conflict + scale_inconsistency
```

### Total Assets

Current failure:

- 2023 selected value `213,079,067,000`.
- 2024 selected value `16,152,486`.
- Same-year 2024 primary balance-sheet competing candidate exists at a different scale.

Gate result:

```text
baseline_not_validatable
```

Issue:

```text
candidate_spread_gt_100x + yoy_drop_gt_100x
```

### EPS

Current state:

- Selected EPS series is internally consistent.
- Rejected candidates include scale-corrupted values such as `44,000,000`.

Gate result:

```text
clean_with_warning
```

or:

```text
clean
```

depending on whether rejected candidate spread is treated as warning after explicit EPS precedence is applied.

Recommended MVP status:

```text
clean_with_warning
```

Reason:

Selected values are usable, but provenance should disclose rejected scale-corrupted EPS candidates.

## 15. Integration With Forecast Validation MVP

Forecast Validation should consume the integrity gate result before any validation category runs.

Category behavior:

| Forecast Validation Category | Required Clean Metrics |
|---|---|
| Revenue growth consistency | `revenue` |
| Margin consistency | `revenue`, `gross_profit`, `operating_profit`, `profit_after_tax` |
| EPS consistency | `earnings_per_share`, `profit_after_tax` |
| Balance sheet consistency | `total_assets`, `total_equity`, liabilities/debt metrics where available |
| Cash flow consistency | `operating_cash_flow`, `profit_after_tax`, `cash_and_cash_equivalents` |
| Debt consistency | `total_debt`, `long_term_debt`, `cash_and_cash_equivalents`, `operating_cash_flow` |
| Forecast plausibility | Depends on forecast metric being validated |

If a required metric is `baseline_not_validatable`:

```text
Do not run category calculations.
Return category status = baseline_not_validatable.
```

If a required metric is `missing`:

```text
Do not infer substitute.
Return category status = unavailable_missing_metric.
```

If a required metric is `clean_with_warning`:

```text
Run calculation, lower confidence, and include warning evidence.
```

## 16. Minimum Acceptance Criteria

The implementation satisfies the MVP input contract when:

1. Every requested series receives one of the four statuses.
2. No series with candidate spread `>100x` is marked clean.
3. No series with unexplained YoY magnitude ratio `>10x` is marked clean.
4. No note disclosure can outrank a valid primary statement value solely because of normalization confidence.
5. `total_debt`, `long_term_debt`, and `total_equity` remain missing unless exact metrics or approved aggregates exist.
6. Every blocked series includes evidence showing values, years, sources, pages, and reason.
7. Forecast Validation categories can short-circuit before numeric calculations.
8. EPS remains usable while rejected scale-corrupted EPS candidates remain visible as warning evidence.

## 17. Expected Result On Latest Lucky Bundle

Expected gate output before upstream remediation:

| Metric | Expected Status | Reason |
|---|---|---|
| `revenue` | `baseline_not_validatable` | Note-vs-statement selection and scale/candidate spread. |
| `profit_after_tax` | `baseline_not_validatable` | Unresolved conflicts and scale jumps. |
| `operating_profit` | `baseline_not_validatable` | Unresolved conflicts and candidate spread. |
| `total_assets` | `baseline_not_validatable` | 2023-2024 scale break and candidate spread. |
| `cash_and_cash_equivalents` | `baseline_not_validatable` | Unresolved conflict and source ambiguity. |
| `operating_cash_flow` | `baseline_not_validatable` | Mixed source lineage and scale break. |
| `gross_profit` | `baseline_not_validatable` | Unresolved conflicts and candidate spread. |
| `earnings_per_share` | `clean_with_warning` | Selected series is clean; rejected candidates are scale-corrupted. |
| `total_debt` | `missing` | Exact canonical metric absent. |
| `long_term_debt` | `missing` | Exact canonical metric absent. |
| `total_equity` | `missing` | Exact canonical metric absent. |

This result is acceptable for MVP readiness because it prevents corrupted historical baselines from entering forecast validation calculations.

The next milestone after this design is not to force these metrics clean. It is to make the gate truthful, evidenced, and deterministic. Once the gate exists, upstream OCR/consolidation fixes can be measured by how many series move from `baseline_not_validatable` to `clean` or `clean_with_warning`.
