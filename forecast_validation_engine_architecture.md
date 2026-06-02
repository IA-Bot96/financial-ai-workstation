# Forecast Validation Engine Architecture

## 1. Purpose

The Forecast Validation Engine validates historical financial performance and forecast reasonableness using the structured analytical data produced by OCR Engine v1 and exposed through Query Engine Core v1.

The engine is deterministic-first. It does not generate forecasts, rewrite source data, normalize metrics, or create narrative explanations from scratch. Its role is to test whether historical series and submitted forecasts are internally consistent, financially plausible, and adequately supported by evidence.

## 2. Source Of Truth

The engine consumes the same structured source of truth as the Query Engine:

```text
OCR Engine v1
  -> QueryEngineInputBundle
  -> CompanyKnowledgeBase
       -> FinancialDataset
       -> InsightDataset
       -> ConflictDataset
```

The generated workbook is a citation target and human-facing artifact. It is not the analytical source of truth for validation.

Primary inputs:

| Input | Purpose |
|---|---|
| `CompanyKnowledgeBase` | Immutable root object for the loaded company workbook/session. |
| `FinancialDataset` | Selected consolidated financial records, indexed by canonical metric, value year, source report year, and statement scope. |
| `InsightDataset` | Source-traced business insights with section, page, confidence, and report-year metadata. |
| `ConflictDataset` | Duplicate/conflict groups, competing candidates, resolution reasons, and unresolved conflict flags. |

The engine must preserve the distinction between:

| Field | Meaning |
|---|---|
| `value_year` | Financial year represented by the value. Used for historical series and validation math. |
| `source_report_year` | Annual report that supplied the value. Used for provenance and recency/source-of-truth logic. |

## 3. Engine Responsibilities

The Forecast Validation Engine is responsible for:

1. Validating historical financial series before they are used as forecast baselines.
2. Validating forecast assumptions and projected values against historical performance.
3. Detecting trend breaks, outliers, scale inconsistencies, and internal statement inconsistencies.
4. Surfacing unresolved conflicts and review-gated source data that weaken forecast confidence.
5. Producing evidence-backed validation issues, scorecards, and readiness outcomes.
6. Providing deterministic citations and provenance for every validation issue.
7. Separating validation severity from confidence so severe issues cannot be hidden by high aggregate scores.

The engine is not responsible for:

1. OCR extraction.
2. Metric normalization.
3. Financial year consolidation.
4. Workbook population.
5. Query planning or ad hoc financial Q&A.
6. Forecast generation.
7. Analyst recommendations.
8. LLM-authored explanations that alter deterministic findings.

## 4. Engine Boundaries

### Belongs In Forecast Validation Engine

- Validation rules over historical and forecast series.
- Plausibility checks for forecast values.
- Deterministic variance, CAGR, margin, ratio, and consistency tests.
- Issue severity assignment.
- Validation confidence scoring.
- Validation scorecards by category and overall readiness.
- Evidence assembly for validation issues.
- Blocking unresolved conflicts from high-confidence validation.

### Belongs In Query Engine

- Metric name resolution.
- Financial retrieval by metric/year/history/scope.
- Insight retrieval.
- Deterministic calculations such as YoY growth, CAGR, absolute change, trend series, and comparison values.
- Citation construction from workbook mappings and source provenance.
- Conflict-aware retrieval and ambiguity reporting.

Forecast Validation should call or reuse Query Engine retrieval/calculation contracts rather than duplicate metric lookup logic.

### Belongs In Future LLM Layers

- Natural-language summarization of validation results.
- Analyst-style commentary over already-selected evidence.
- User-friendly explanation rewriting.
- Clarifying-question generation.

LLM layers may not:

- Change calculations.
- Suppress critical validation issues.
- Invent missing evidence.
- Select alternate values when deterministic retrieval reports conflicts.
- Change citations or provenance.

## 5. Conceptual Data Flow

```text
CompanyKnowledgeBase
  |
  v
Validation Request
  |
  v
Metric Resolution and Retrieval
  - Query Engine MetricResolutionService
  - Query Engine FinancialRetrievalService
  - Query Engine InsightRetrievalService
  |
  v
Historical Series Construction
  - value_year chronology
  - statement scope checks
  - conflict/review gating
  |
  v
Deterministic Calculations
  - YoY growth
  - CAGR
  - margin series
  - ratio checks
  - variance checks
  |
  v
Validation Rules
  - historical consistency
  - forecast plausibility
  - statement integrity
  - outlier detection
  |
  v
Evidence Assembly
  - supporting metrics
  - years involved
  - calculations
  - citations
  - provenance
  - conflicts
  |
  v
Confidence Evaluation
  - data quality
  - coverage
  - conflict status
  - calculation reliability
  |
  v
ForecastValidationResult
  - ValidationIssue[]
  - ValidationEvidence[]
  - ValidationScorecard
```

## 6. Validation Categories

### Historical Series Readiness

Purpose: Determine whether historical values are safe to use as a forecast baseline.

Checks:

- Missing years in a required historical window.
- Insufficient history for CAGR or trend validation.
- Mixed statement scope in one series unless explicitly allowed.
- Unresolved conflicts on selected values.
- Review-gated records in critical metrics.
- Unit, currency, or scale inconsistency.
- `value_year > source_report_year`.

Example issue:

```text
Revenue history contains a >100x magnitude drop between 2021 and 2022.
Classification: likely scale issue.
Impact: forecast baseline requires review.
```

### Revenue Growth Consistency

Checks:

- YoY revenue growth outside configurable sector-neutral bounds.
- Forecast revenue growth materially above historical CAGR without supporting insight evidence.
- Sudden revenue decline without matching insight or segment explanation.
- Revenue growth inconsistent with capacity, volume, price, or market commentary when available.

### Margin Consistency

Metrics:

- Gross margin.
- Operating margin.
- EBITDA margin.
- Net margin.

Checks:

- Margin expansion/contraction beyond historical range.
- Forecast margin inconsistent with cost pressure or price commentary.
- Gross margin and operating margin moving in contradictory directions without evidence.
- Net margin improvement while finance cost/tax expense worsens materially.

### EPS Consistency

Checks:

- EPS growth inconsistent with net income growth.
- EPS forecast assumes share count behavior not supported by historical data.
- EPS values mistakenly scaled as currency or thousands.
- EPS conflicts or review-gated EPS source values.

### Balance Sheet Consistency

Checks:

- Assets = liabilities + equity, within tolerance.
- Working capital components reconcile directionally.
- Cash, debt, equity, and asset growth plausibility.
- Forecast balance sheet growth inconsistent with capex or retained earnings.

### Cash Flow Consistency

Checks:

- Operating cash flow trend versus profit trend.
- Free cash flow versus capex and operating cash flow.
- Cash at beginning/end of period consistency.
- Persistent profit growth with deteriorating operating cash flow.

### Debt Consistency

Checks:

- Debt growth versus finance cost.
- Debt growth versus cash flow capacity.
- Debt-to-equity and interest coverage plausibility.
- Missing `total_debt` fallback risk when only narrower debt metrics are available.

### Forecast Plausibility

Checks:

- Forecast growth versus historical CAGR.
- Forecast margin versus historical range.
- Forecast cash conversion versus historical cash conversion.
- Forecast capex versus historical capex/capacity commentary.
- Forecast debt reduction without cash flow support.

### Trend Breaks

Checks:

- Structural breaks in revenue, margins, cash flow, debt, or assets.
- Forecast reversal of historical trend without insight evidence.
- Breakpoints coinciding with restatements, reclassifications, or source conflicts.

### Outlier Detection

Checks:

- YoY magnitude jumps/drops above thresholds.
- Values outside historical interquartile range or median-multiple range.
- Ratios outside plausible financial bounds.
- Candidate-source spread inside consolidation groups.

## 7. Severity Model

Severity describes business risk, not confidence.

| Severity | Meaning | Example | Result |
|---|---|---|---|
| Info | Useful context, no validation failure. | Forecast revenue growth is above the three-year average but within historical range. | Included in evidence only. |
| Warning | Potential concern, does not block validation alone. | Forecast margin is near historical high. | Reduces confidence. |
| High | Material concern requiring review. | Forecast operating cash flow diverges from profit trend. | Validation category may fail. |
| Critical | Must fail validation regardless of score. | Forecast relies on unresolved conflicting revenue values or impossible balance sheet equation. | Overall validation fails. |

Critical issues always fail the affected category and the overall validation readiness if they involve core forecast inputs.

## 8. Evidence Model

Every validation issue must provide evidence.

Required evidence contents:

| Evidence Element | Purpose |
|---|---|
| Supporting metrics | Canonical metrics used in the rule. |
| Years involved | `value_year` values used in calculations. |
| Calculations | Deterministic formula outputs and inputs. |
| Citations | Workbook cell references and PDF/page references where available. |
| Provenance | Source report year, source page, table type, statement scope, source class. |
| Conflict references | Competing candidates and resolution status when relevant. |
| Insight references | Narrative support or contradiction when a rule uses insight evidence. |

Evidence rules:

- Validation may cite Query Engine calculation evidence directly.
- Workbook citations must come from persisted `WorkbookCellMapping` records.
- PDF/page citations must come from OCR provenance.
- Missing citations reduce confidence and may create a warning.
- Evidence must state whether values are selected consolidated values or review/conflicted candidates.

## 9. Confidence Model

Confidence answers: "How reliable is this validation conclusion?"

It is computed deterministically from components:

| Component | Effect |
|---|---|
| Data coverage | Higher when required years and metrics exist. |
| Retrieval confidence | Inherited from Query Engine retrieval and metric resolution. |
| Normalization confidence | Lower confidence when values were fuzzy/low-confidence mappings. |
| Conflict status | Unresolved conflicts sharply reduce confidence. |
| Review gate status | Review-gated values reduce confidence. |
| Unit/scale consistency | Scale inconsistencies reduce confidence or create critical failure. |
| Citation completeness | Missing cell/page provenance reduces confidence. |
| Insight support | Relevant high-confidence insights can raise confidence for plausibility explanations, not for arithmetic correctness. |

Confidence buckets:

| Bucket | Range | Meaning |
|---|---:|---|
| High | `>= 0.85` | Strong data and evidence. |
| Medium | `0.65 - 0.84` | Usable with caveats. |
| Low | `0.40 - 0.64` | Requires analyst review. |
| Unreliable | `< 0.40` | Not suitable for validation conclusions. |

Confidence cannot override severity. A critical issue with high-confidence evidence still fails validation.

## 10. Service Architecture

```text
ForecastValidationOrchestrator
  |
  +-- ValidationInputAdapter
  |     - accepts CompanyKnowledgeBase and forecast target data
  |     - enforces source-of-truth and schema compatibility
  |
  +-- HistoricalSeriesService
  |     - builds value_year-based histories
  |     - applies conflict/review gates
  |
  +-- ForecastSeriesService
  |     - aligns submitted forecast values to canonical metrics and years
  |     - validates units, scales, and statement scope
  |
  +-- ValidationRuleRegistry
  |     - groups deterministic rules by category
  |
  +-- ValidationRuleExecutor
  |     - executes rules
  |     - emits issue candidates and calculation references
  |
  +-- ValidationEvidenceService
  |     - assembles metric, calculation, citation, provenance, conflict, and insight evidence
  |
  +-- ValidationConfidenceService
  |     - computes deterministic confidence scores
  |
  +-- ValidationScorecardService
  |     - aggregates issues by category
  |     - applies critical-failure overrides
  |
  +-- ForecastValidationResultBuilder
        - returns final result, issues, evidence, and scorecard
```

### ForecastValidationOrchestrator

Coordinates a validation run. It does not contain financial rule logic.

### ValidationInputAdapter

Verifies that the input knowledge base is loaded, valid, and compatible with the validation request. It rejects workbook-only inputs without the structured sidecar because conflicts, confidence, and provenance cannot be guaranteed.

### HistoricalSeriesService

Builds historical series from `FinancialDataset` using `value_year`. It uses Query Engine retrieval contracts for canonical lookup and preserves conflict/review status.

### ForecastSeriesService

Aligns submitted forecast values to canonical metrics and forecast years. It is responsible for validating that forecast inputs are comparable to historical values by unit, scale, currency, and statement scope.

### ValidationRuleRegistry

Stores available validation rules by category. The registry must distinguish MVP rules from future sector-specific rules.

### ValidationRuleExecutor

Runs deterministic validation rules. It returns structured issue candidates and references the calculations used.

### ValidationEvidenceService

Builds auditable evidence for every issue. It reuses Query Engine evidence, citations, and conflict references where available.

### ValidationConfidenceService

Computes confidence scores and limiting factors. It does not change issue severity.

### ValidationScorecardService

Aggregates category-level and overall validation status. Critical issues override aggregate scores.

## 11. Output Contracts

Architecture-level outputs:

| Output | Purpose |
|---|---|
| `ForecastValidationResult` | Root validation response for a run. |
| `ValidationIssue` | One deterministic validation finding. |
| `ValidationEvidence` | Supporting facts, calculations, citations, provenance, and conflicts. |
| `ValidationScorecard` | Category and overall readiness summary. |

The concrete model definitions should be created in the implementation design phase. This architecture only fixes their responsibilities and required evidence semantics.

## 12. Failure Modes

| Failure Mode | Expected Behavior |
|---|---|
| `CompanyKnowledgeBase` missing | Return validation unavailable. |
| Workbook-only input | Reject for production validation. |
| Missing metric | Emit issue or unavailable category depending on rule criticality. |
| Missing years | Fail rules requiring continuous history. |
| Unresolved conflicts | Block high-confidence validation for affected metrics. |
| Review-gated values | Downgrade confidence and require analyst review if used in core validation. |
| Unit or scale mismatch | High or critical issue depending on affected metric. |
| Non-numeric value | Exclude from numeric rules and report unavailable evidence. |
| Citation missing | Validation may continue, but confidence is reduced and citation warning is emitted. |
| Insight evidence missing | Arithmetic rules continue; plausibility commentary receives lower confidence. |
| Unsupported forecast metric | Return unsupported metric issue; do not infer broad substitutes silently. |
| Mixed statement scope | Warn or fail depending on rule and request scope. |

## 13. MVP Scope

The MVP should validate a focused set of high-impact metrics and rules.

### MVP Metrics

- Revenue.
- Gross profit.
- Operating profit.
- Profit after tax / net income.
- EPS.
- Operating cash flow.
- Cash and cash equivalents.
- Total assets.
- Total equity.
- Total debt where available.
- Long-term debt where available.
- Capex where available.

### MVP Historical Checks

- Missing history.
- YoY growth outliers.
- CAGR sanity.
- Scale consistency.
- Unit/currency consistency.
- Review/conflict gating.
- Margin consistency.
- EPS versus PAT consistency.
- Operating cash flow versus profit consistency.

### MVP Forecast Checks

- Forecast revenue growth versus historical CAGR.
- Forecast margin versus historical range.
- Forecast EPS growth versus PAT growth.
- Forecast operating cash flow versus profit.
- Forecast debt trend versus cash flow capacity.
- Forecast capex trend versus historical capex and insight evidence where available.

### MVP Outputs

- Overall validation status.
- Category scorecard.
- Validation issues with severity and confidence.
- Evidence bundle for every issue.
- Citation and provenance coverage summary.
- Forecast readiness: safe, safe with warnings, or requires review.

## 14. Phase Roadmap

### Phase 0: Contracts And Boundaries

- Define final validation output contracts.
- Define accepted input sources.
- Define critical metrics and rule categories.
- Define severity and confidence semantics.

### Phase 1: Historical Readiness Validation

- Build historical series from `CompanyKnowledgeBase`.
- Validate coverage, conflicts, review gates, unit/scale consistency, and citation readiness.
- Produce scorecards without forecast inputs.

### Phase 2: Core Forecast Plausibility

- Validate submitted forecasts against historical CAGR, YoY growth, margins, EPS, cash flow, and debt trends.
- Add category-level readiness outcomes.

### Phase 3: Insight-Aware Plausibility

- Use `InsightDataset` as supporting evidence for trend breaks, cost pressures, expansion plans, debt changes, and regulatory/ESG factors.
- Keep insight use evidence-based and non-authoritative for arithmetic.

### Phase 4: Sector-Aware Rule Packs

- Add sector-specific validation ranges and rules for cement, banking, fertilizer, power, textile, automobile, oil and gas, and technology.
- Keep sector rules configurable and separate from core rules.

### Phase 5: LLM Explanation Layer

- Optional narrative renderer over deterministic validation results.
- No LLM calculation, evidence selection, conflict resolution, or severity assignment.

## 15. Readiness Criteria

The Forecast Validation Engine is ready for v1 when:

1. Every issue has evidence, years, citations, and provenance when available.
2. Critical issues always fail the affected category.
3. Unresolved conflicts and review-gated values are never treated as clean baselines.
4. `value_year` is used for all historical calculations.
5. `source_report_year` is used only for provenance and source-of-truth explanation.
6. Query Engine retrieval and calculation contracts are reused rather than duplicated.
7. Workbook-only inputs are rejected for production validation.
8. Forecast outputs clearly distinguish deterministic validation from narrative interpretation.

## 16. Architecture Verdict

The Forecast Validation Engine should be built as a deterministic validation layer on top of `CompanyKnowledgeBase`, Query Engine retrieval, Query Engine calculations, and OCR provenance.

Its first production value is not forecasting automation. Its first production value is preventing bad historical baselines, conflicted values, scale-corrupted series, or unsupported assumptions from silently flowing into forecasts.
