# Financial Query Engine — Reconciled Implementation Design

## 1. Architecture Reconciliation

The architecture review is accepted as authoritative. No Must-Fix finding is rejected. The main architectural correction is that the generated `.xlsx` workbook is not the analytical source of truth. It is a human-facing deliverable and citation target. The Query Engine must consume a structured handoff artifact produced by the OCR pipeline.

### Must-Fix Resolution

| Finding | Decision | Why | Architectural Change |
|---|---|---|---|
| F1: `.xlsx` cannot reconstruct the required data model | Accepted | The workbook stores displayed values, labels, and year columns, but not consolidation candidates, review flags, source class, statement scope, normalization confidence, or unresolved conflicts. | Replace workbook-only input with `QueryEngineInputBundle`: structured consolidation result + insights result + workbook metadata + persisted cell mappings. |
| F2: `FinancialDataFrame` invents fields not present on `MetricValue` | Accepted | The proposed dataframe fields exist upstream in `ConsolidationCandidate` and `ConsolidationGroup`, not in workbook cells. | Define `FinancialDataFrame` as a flattened projection of `FinancialYearConsolidationResult`, not a parse of the `.xlsx`. |
| F3: Conflict subsystem has no live data source | Accepted | Conflicts are represented in `ConsolidationGroup`; they are not recoverable from workbook output. | Use `ConsolidationGroup` as the authoritative conflict source. Conflict indexes are projections over consolidation groups. |
| F6: Concurrency/session model is undefined | Accepted | A mutable global current workbook is unsafe even in a desktop app with concurrent UI actions. | Use a process-local `KnowledgeBaseRegistry` keyed by `workbook_id`. Queries pin `workbook_id` and `workbook_fingerprint` at planning time. |
| F9: Retrieval ranking depends on fields dropped by workbook | Accepted | Ranking requires conflict status, confidence, statement scope, and source class. | Retrieval operates on consolidated structured rows enriched from `ConsolidationCandidate` and `ConsolidationGroup`. |
| F14: Cell-reference provenance is promised but not persisted | Accepted | `WorkbookMapper` computes destinations but current workbook result does not expose the mapping. | Persist `WorkbookCellMapping` records during workbook population and include them in the Query Engine input bundle. |
| F24: No upstream input contract | Accepted | The engine cannot be implemented safely without an explicit handoff contract. | Add versioned `QueryEngineInputBundle` as the hard boundary between OCR/workbook generation and Query Engine. |

### Modified Review Findings

| Finding | Decision | Reason |
|---|---|---|
| F21: Too many indexes | Modified | The final design keeps index concepts but implements only three physical indexes for MVP: metric, insight, and cell mapping. Provenance and conflicts are row/group projections, not separately maintained subsystems. |
| F22: API surface too broad | Modified | MVP keeps only upload/load, query, and current workbook metadata. Metric and insight catalogs are useful but deferred. |
| F23: LLM narrative risk | Accepted with stricter boundary | The deterministic renderer is the primary response renderer. An LLM may only rephrase already-selected evidence and must not change calculations, evidence, citations, or confidence. |

### Rejected Review Findings

None.

## 2. Final Source of Truth

The production source of truth is:

```text
FinancialYearConsolidationResult
+ InsightsExtractionResult
+ WorkbookCellMapping records
+ WorkbookResult metadata
+ workbook_fingerprint
```

The `.xlsx` workbook is:

- The accountant/user-facing deliverable.
- The source for visual cell citations.
- A validation target for cell mappings.
- Not the source for conflicts, confidence, source scope, source class, review state, or competing candidates.

If only an `.xlsx` is provided without the structured sidecar, the Query Engine may enter a degraded workbook-only mode for exploratory lookup, but production financial Q&A must reject that input as incomplete because confidence, conflicts, and provenance cannot be guaranteed.

## 3. Final End-to-End Data Flow

```text
OCR Output
  CompanyContext
    reports
    normalization_results[report_year]
    insights_results[report_year]
    metric_values
        |
        v
Financial Year Consolidation
  FinancialYearConsolidationResult
    metric_values: selected consolidated MetricValue records
    groups: ConsolidationGroup records
    duplicate/conflict diagnostics
        |
        v
Insights Extraction
  InsightsExtractionResult per report year
    insights: Insight records
    diagnostics: InsightsExtractionDiagnostics
        |
        v
Workbook Population
  WorkbookResult
    output_file_path
    sheets_created/reused/replaced
    metrics_written
  WorkbookCellMapping records
    metric/value_year/table_type/source_report_year -> sheet/cell
        |
        v
Query Engine Input Contract
  QueryEngineInputBundle
    schema_version
    workbook_id
    workbook_fingerprint
    company_name
    report_years
    workbook_result
    financial_year_consolidation_result
    insights_results_by_report_year
    workbook_cell_mappings
        |
        v
Knowledge Base Construction
  CompanyKnowledgeBase
    financial_rows: FinancialDataFrame
    insight_rows: InsightsDataFrame
    metric_index
    insight_index
    cell_mapping_index
    consolidation_groups_by_key
        |
        v
Query Planning
  QueryPlan
    query_type
    intent
    metrics
    years
    operations
    ambiguity
        |
        v
Retrieval
  FinancialRetrievalResult
  InsightRetrievalResult
        |
        v
Calculation
  CalculationResult
    deterministic formulas
    input values
    missing inputs
    unit/coercion warnings
        |
        v
Evidence Assembly
  EvidencePackage
    financial evidence
    insight evidence
    calculation evidence
    conflict references
        |
        v
Confidence Evaluation
  ConfidenceAssessment
    score
    bucket
    limiting factors
        |
        v
Citation Construction
  Citation records
    workbook sheet/cell
    PDF page
    source section
    source report year
        |
        v
Response Generation
  QueryResponse
    deterministic answer
    citations
    warnings
    conflicts
    clarification requests
```

## 4. Query Engine Input Contract

### QueryEngineInputBundle

Ownership: Query Engine boundary model.

Source: Produced by OCR pipeline orchestration after workbook population.

Required fields:

| Field | Type | Invariant |
|---|---|---|
| schema_version | string | Semantic version. MVP starts at `1.0.0`. |
| workbook_id | string | Stable id for this loaded bundle. |
| workbook_fingerprint | string | SHA-256 of workbook bytes plus structured sidecar payload hash. |
| company_name | string | Non-empty. |
| report_years | list[int] | Non-empty, unique, sorted during load. |
| workbook_result | WorkbookResult | `output_file_path` points to the generated workbook. |
| financial_year_consolidation_result | FinancialYearConsolidationResult | Must contain selected `metric_values` and may contain `groups`. |
| insights_results_by_report_year | dict[int, InsightsExtractionResult] | Keys must be present in `report_years`. |
| workbook_cell_mappings | list[WorkbookCellMappingRecord] | Must reference `workbook_fingerprint`. |

Optional fields:

| Field | Type | Purpose |
|---|---|---|
| generated_at | datetime | Bundle creation time. |
| source_context_path | string | Path to serialized `CompanyContext`, if retained. |
| quality_summary | object | Precomputed OCR/workbook quality metadata. |

Versioning strategy:

- Patch version: diagnostics-only additions.
- Minor version: optional fields added with defaults.
- Major version: required field changes or changed semantics.
- Query Engine must reject newer major versions and warn on newer minor versions it does not fully understand.

### FinancialYearConsolidationResult

Source module: `backend/shared/models/financial_year_consolidation.py`

Ownership: Shared financial platform model, produced by consolidation.

Required fields consumed by Query Engine:

| Field | Required | Usage |
|---|---|---|
| metric_values | Yes | Selected consolidated values used for answers. |
| groups | Yes for conflict-aware Q&A | Competing candidates, conflict status, and resolution reason. |
| duplicate_groups_resolved | Yes | Quality summary. |
| conflict_groups_resolved | Yes | Quality summary. |
| unresolved_conflict_groups | Yes | Confidence and readiness summary. |

Invariant:

- Every `MetricValue` must satisfy `value_year <= source_report_year`.
- Every selected `MetricValue` that belongs to a duplicate/conflict group should be traceable to one `ConsolidationGroup.selected`.
- `groups[*].selected` must not contradict the corresponding selected `MetricValue`.

### ConsolidationGroup

Source module: `backend/shared/models/financial_year_consolidation.py`

Ownership: Shared consolidation layer.

Required fields consumed:

| Field | Usage |
|---|---|
| metric | Conflict key. |
| value_year | Conflict key. |
| selected | Selected candidate evidence. |
| competing_candidates | Conflict disclosure. |
| is_duplicate_group | Duplicate diagnostics. |
| is_conflict_group | Conflict diagnostics. |
| conflict_resolved | Confidence factor. |
| unresolved_conflict | Answer guardrail. |
| conflict_status | User-facing conflict state. |
| resolution_reason | Evidence explanation. |

Invariant:

- `candidate_count == 1 + len(competing_candidates)`.
- If `unresolved_conflict` is true, responses using the selected value must include a warning or clarification request.

### Insight and InsightsExtractionResult

Source module: `backend/ocr_engine/models/insights_extraction.py`

Ownership: OCR Insights Extraction Layer.

Required `Insight` fields:

| Field | Required | Usage |
|---|---|---|
| value_year | Yes | Year filtering. |
| source_report_year | Yes | Provenance. |
| area | Yes | Insight retrieval. |
| takeaway | Yes | Evidence text. |
| source_section | Yes | Citation. |
| page_number | Yes | Citation. |
| confidence | Yes | Retrieval ranking and confidence model. |

Required `InsightsExtractionResult` fields:

| Field | Usage |
|---|---|
| insights | High-confidence insight evidence. |
| diagnostics | Quality summary and observability. |

Invariant:

- `page_number > 0`.
- `0 <= confidence <= 1`.
- `value_year <= source_report_year`.

### WorkbookCellMappingRecord

Current source: `backend/workbook_population/services/workbook_mapper.py` contains a dataclass named `WorkbookCellMapping`.

Required implementation change: promote/persist a versioned record owned by workbook population, preferably in `backend/workbook_population/models/workbook_cell_mapping.py` or a shared model if Query Engine imports it directly.

Required fields:

| Field | Type | Invariant |
|---|---|---|
| workbook_fingerprint | string | Must match input bundle fingerprint. |
| metric | string | Canonical metric key. |
| value_year | int | Same year as written value. |
| source_report_year | int | Same source report year as `MetricValue`. |
| table_type | string | Same table type as `MetricValue`. |
| sheet_name | string | Existing workbook sheet. |
| row | int | `> 0`. |
| column | int | `> 0`. |
| cell_reference | string | Excel coordinate, for example `C12`. |
| write_status | string | `written`, `skipped_formula`, `mapping_missing`, or `conflict_replaced`. |
| written_value | number/string/null | Value written or attempted. |

Optional fields:

| Field | Purpose |
|---|---|
| template_mode | Template vs dynamic workbook mode. |
| formula_preserved | Whether a formula cell was intentionally preserved. |
| warning | Mapping/write warning. |

Invariant:

- At most one successful `written` mapping exists for `(metric, value_year, source_report_year, table_type)`.
- Mapping records are authoritative for workbook citations. Query Engine must not re-derive cells by scanning the workbook unless explicitly in degraded mode.

### workbook_fingerprint

Ownership: OCR pipeline handoff.

Purpose:

- Bind structured sidecar to the exact workbook.
- Prevent stale query results after a workbook replacement.
- Pin queries to a stable knowledge base snapshot.

Computation:

- Hash workbook bytes.
- Hash canonical serialized sidecar payload excluding volatile timestamps.
- Combine both hashes into one fingerprint.

Invariant:

- Query requests may include `workbook_fingerprint`.
- If provided and it does not match the loaded knowledge base, the engine returns `stale_workbook`.

## 5. Final Knowledge Base Design

### CompanyKnowledgeBase

Represents one immutable loaded workbook bundle.

| Field | Purpose |
|---|---|
| workbook_id | Query/session key. |
| workbook_fingerprint | Stale-read guard. |
| company_name | Display and answer context. |
| report_years | Relative year resolution and query constraints. |
| financial_rows | Flattened financial dataframe rows. |
| insight_rows | Flattened high-confidence insight rows. |
| review_insight_rows | Review-bucket insight rows if supplied. |
| metric_index | Primary financial lookup index. |
| insight_index | Primary insight lookup index. |
| cell_mapping_index | Workbook citation lookup. |
| consolidation_groups_by_key | Conflict lookup by metric/year. |
| quality_summary | Counts and coverage. |

### FinancialDataFrame Row

Source: flattened projection of `FinancialYearConsolidationResult`.

Required fields:

| Field | Source |
|---|---|
| metric | `MetricValue.metric` / `ConsolidationCandidate.metric` |
| value_year | `MetricValue.value_year` |
| value | `MetricValue.value` |
| source_report_year | `MetricValue.source_report_year` |
| page_number | `MetricValue.page_number` |
| table_type | `MetricValue.table_type` |
| source_class | `ConsolidationCandidate.source_class` where available |
| statement_scope | `ConsolidationCandidate.statement_scope` where available |
| normalization_confidence | `ConsolidationCandidate.normalization_confidence` where available |
| original_metric | `ConsolidationCandidate.original_metric` where available |
| requires_review | `ConsolidationCandidate.requires_review` where available |
| conflict_group_id | Derived from `ConsolidationGroup` key |
| unresolved_conflict | `ConsolidationGroup.unresolved_conflict` |
| conflict_status | `ConsolidationGroup.conflict_status` |
| resolution_reason | `ConsolidationGroup.resolution_reason` |
| cell_mapping | `WorkbookCellMappingRecord` if available |

If a selected `MetricValue` has no matching candidate/group, the row is still loaded, but the engine sets:

- `source_class = "unclassified"`
- `statement_scope = "unknown"`
- `normalization_confidence = 0`
- `requires_review = true`
- warning: `missing_consolidation_candidate_metadata`

### Indexes

| Index | Key Structure | Purpose | Lookup Complexity | Memory Impact | MVP Decision |
|---|---|---|---|---|---|
| metric_index | `(metric)` -> rows; `(metric, value_year)` -> rows | Primary financial lookup. | O(1) key lookup, O(k) row filtering. | Low. One reference per financial row. | Keep. |
| insight_index | area/section/year/keyword maps -> insight ids | Insight retrieval. | O(1) for structured filters, O(k) scoring. | Low to medium depending keyword index. | Keep lightweight. |
| cell_mapping_index | `(metric, value_year, source_report_year, table_type)` -> mapping | Workbook cell citations. | O(1). | Low. One mapping per written value. | Keep. |
| consolidation_groups_by_key | `(metric, value_year)` -> groups | Conflict lookup. | O(1). | Low. One entry per duplicate/conflict group. | Keep as dict, not separate service-owned index. |
| provenance_index | separate provenance records | Citation lookup. | O(1) possible but duplicate data. | Unnecessary. | Remove as physical index; provenance lives on rows and cell mappings. |
| conflict_index | separate conflict subsystem index | Conflict lookup. | O(1) possible but duplicate data. | Unnecessary for MVP. | Remove as physical index; use `consolidation_groups_by_key`. |

### KnowledgeBaseRegistry

Purpose:

- Hold immutable knowledge base snapshots.
- Avoid race conditions during workbook replacement.
- Support one active workbook while allowing in-flight queries to finish against the snapshot they pinned.

MVP behavior:

- `POST /workbooks` loads a new knowledge base and makes it current.
- Existing in-flight queries continue using their pinned `workbook_id`.
- Old knowledge bases are evicted after no active queries reference them.
- Queries without `workbook_id` use the current id at request start.

## 6. Service Design

### Query Planner

Responsibility:

- Convert a user question into a deterministic `QueryPlan`.

Inputs:

- `QueryRequest`
- `CompanyKnowledgeBase.report_years`
- shared metric registry / normalizer

Outputs:

- `QueryPlan`
- planner warnings
- clarification options when metric/year intent is ambiguous

Dependencies:

- Metric normalizer.
- Report year resolver.
- Intent classifier rules.

Error behavior:

- Returns `needs_clarification` when multiple critical interpretations remain.
- Does not guess on headline financial metrics when ambiguity is material.

Rules:

- `query_type` is the data-domain axis: `financial`, `insight`, `mixed`.
- `intent` is the operation axis: `lookup`, `trend`, `comparison`, `growth`, `explanation`, `risk_summary`.
- Relative years resolve against `CompanyKnowledgeBase.report_years`. For example, "latest year" maps to `max(report_years)`.

### Financial Retrieval Service

Responsibility:

- Retrieve financial rows matching planned metrics, years, scopes, and table types.

Inputs:

- `QueryPlan`
- `CompanyKnowledgeBase.metric_index`
- `consolidation_groups_by_key`

Outputs:

- `FinancialRetrievalResult`
- matched rows
- missing metrics/years
- ambiguity records

Dependencies:

- Metric index.
- Consolidation group lookup.

Error behavior:

- Does not raise for missing data; returns structured `missing_evidence`.
- Downgrades fuzzy metric matches and emits "interpreted as" warnings.

Ranking:

1. Use consolidated selected rows; do not re-consolidate.
2. Prefer non-review, non-unresolved rows.
3. Prefer requested `statement_scope`.
4. Prefer primary statement source for headline metrics when multiple table types are valid.
5. Prefer higher normalization confidence.
6. Prefer latest source report year only after quality ties.

Fuzzy matching:

- MVP threshold: `>= 0.92` for non-headline metrics.
- Headline metrics should prefer clarification over fuzzy guessing.
- Any fuzzy match caps answer confidence at Medium and adds a warning.

### Insight Retrieval Service

Responsibility:

- Retrieve narrative evidence relevant to planned areas, metrics, years, and explanation intents.

Inputs:

- `QueryPlan`
- `insight_rows`
- `review_insight_rows`
- `include_review_data`

Outputs:

- `InsightRetrievalResult`
- scored insight evidence
- missing insight warnings

Dependencies:

- Lightweight insight index.
- Keyword scorer.

Error behavior:

- Returns empty evidence with warning when no relevant insights exist.
- Does not invent explanations.

MVP scoring:

| Signal | Weight |
|---|---:|
| area match | 40 |
| metric keyword match | 25 |
| year/source_report_year match | 15 |
| source section relevance | 10 |
| insight confidence | 10 |

### Calculation Service

Responsibility:

- Perform deterministic calculations from retrieved financial rows.

Inputs:

- `QueryPlan`
- `FinancialRetrievalResult`

Outputs:

- `CalculationResult` records.

Dependencies:

- Numeric coercion utility.
- Unit/scope consistency checker.

Error behavior:

- Returns `calculation_unavailable` when inputs are missing, non-numeric, conflicted, or unit-inconsistent.
- Does not raise for business-data gaps.

Supported MVP calculations:

- Lookup.
- Delta.
- Percentage change.
- YoY growth.
- CAGR.
- Trend series.
- Metric comparison.

Hard rules:

- No forecasting.
- No calculation over unresolved conflicts unless user explicitly allows review/conflicted data.
- No cross-unit math.
- No consolidated/standalone mixing unless requested.

### Evidence Builder

Responsibility:

- Assemble financial evidence, insight evidence, calculation evidence, and conflict references into one auditable package.

Inputs:

- Query plan.
- Financial retrieval result.
- Insight retrieval result.
- Calculation results.

Outputs:

- `EvidencePackage`

Dependencies:

- Conflict Service.
- Citation Service.

Error behavior:

- Produces partial evidence with missing-data warnings.
- Never mints citations directly; it references citations created by Citation Service.

### Conflict Service

Responsibility:

- Surface relevant duplicate/conflict groups and decide whether an answer can be authoritative.

Inputs:

- Evidence package.
- `consolidation_groups_by_key`

Outputs:

- `ConflictAssessment`
- competing candidates when needed
- conflict warnings
- clarification options

Dependencies:

- Consolidation groups.

Error behavior:

- Missing group metadata creates a low-confidence warning.
- Unresolved conflicts on cited critical metrics require either caveated answer or clarification.

### Confidence Service

Responsibility:

- Compute deterministic confidence score and bucket.

Inputs:

- Evidence package.
- Conflict assessment.
- Retrieval metadata.
- Calculation metadata.

Outputs:

- `ConfidenceAssessment`

Dependencies:

- None outside evidence structures.

MVP rule table:

| Condition | Confidence Cap |
|---|---|
| Required metric missing | Cannot answer |
| Required year missing | Low |
| Unresolved conflict on cited value | Low |
| Review-gated value used | Medium |
| Fuzzy metric match used | Medium |
| Calculation has missing input | Low |
| Insight-only answer with no relevant insight | Cannot answer |
| Complete direct lookup with clean selected value | High |

Score bands:

- High: `0.85 - 1.00`
- Medium: `0.65 - 0.84`
- Low: `0.40 - 0.64`
- Cannot answer: `< 0.40` or hard blocker

### Citation Service

Responsibility:

- Produce authoritative citations from cell mappings and source provenance.

Inputs:

- Financial evidence rows.
- Insight evidence rows.
- `cell_mapping_index`

Outputs:

- `Citation` records.

Dependencies:

- Cell mapping index.

Error behavior:

- If cell mapping is missing, falls back to sheet/table/page citation and emits `cell_citation_unavailable`.
- Does not scan workbook cells in production mode.

### Response Renderer

Responsibility:

- Convert evidence into a user-facing response.

Inputs:

- Query plan.
- Evidence package.
- Confidence assessment.
- Citations.
- Conflicts.

Outputs:

- `QueryResponse`

Dependencies:

- Deterministic templates.
- Optional LLM rewriter, disabled by default for MVP.

Error behavior:

- If optional LLM fails, deterministic response remains the final response.

Boundary:

- Renderer may not add facts.
- Renderer may not change calculations.
- Renderer may not remove warnings or conflicts.
- Renderer may not create citations.

## 7. QueryResponse Contract

### QueryResponse

| Field | Type | Required | Purpose |
|---|---|---|---|
| response_id | string | Yes | Trace id. |
| workbook_id | string | Yes | KB snapshot used. |
| workbook_fingerprint | string | Yes | Stale-read protection. |
| status | string | Yes | `answered`, `needs_clarification`, `insufficient_evidence`, or `cannot_answer`. |
| query_type | string | Yes | `financial`, `insight`, or `mixed`. |
| intent | string | Yes | Operation performed. |
| answer | string | Yes | Deterministic answer text. |
| confidence | ConfidenceAssessment | Yes | Score, bucket, and limiting factors. |
| citations | list[Citation] | Yes | Source references. |
| warnings | list[WarningRecord] | Yes | Review, missing, ambiguity, conflict, or citation warnings. |
| financial_evidence | list[FinancialEvidence] | Yes | Numeric rows used. |
| insight_evidence | list[InsightEvidence] | Yes | Narrative rows used. |
| calculations | list[CalculationResult] | Yes | Calculations performed. |
| conflicts | list[ConflictRecord] | Yes | Relevant competing candidates. |
| clarification_requests | list[ClarificationRequest] | Yes | User-actionable ambiguity choices. |

### Successful Answer Example

```json
{
  "status": "answered",
  "answer": "Revenue in 2025 was PKR 129.2 billion.",
  "confidence": {"bucket": "high", "score": 0.94},
  "citations": [
    {"type": "workbook_cell", "sheet_name": "Income Statement", "cell_reference": "C5"},
    {"type": "pdf_page", "source_report_year": 2025, "page_number": 162}
  ],
  "warnings": [],
  "conflicts": [],
  "clarification_requests": []
}
```

### Conflict Detected Example

```json
{
  "status": "answered",
  "answer": "The selected consolidated cash and cash equivalents value for 2025 is PKR 20.4 billion, but competing candidates exist and one conflict remains unresolved.",
  "confidence": {"bucket": "low", "score": 0.58},
  "warnings": [
    {"code": "unresolved_conflict", "message": "Competing values exist for cash_and_cash_equivalents in 2025."}
  ],
  "conflicts": [
    {
      "metric": "cash_and_cash_equivalents",
      "value_year": 2025,
      "selected_value": 20400000000,
      "competing_values": [20380000000, 20400000000],
      "conflict_status": "unresolved"
    }
  ],
  "clarification_requests": []
}
```

### Insufficient Evidence Example

```json
{
  "status": "insufficient_evidence",
  "answer": "I could not calculate five-year revenue growth because revenue is available for only three years.",
  "confidence": {"bucket": "low", "score": 0.42},
  "warnings": [
    {"code": "missing_years", "message": "Revenue is missing for 2021 and 2022."}
  ],
  "calculations": [
    {"operation": "cagr", "status": "unavailable", "missing_inputs": ["revenue:2021", "revenue:2022"]}
  ],
  "clarification_requests": []
}
```

### Cannot Answer Example

```json
{
  "status": "cannot_answer",
  "answer": "I cannot answer this from the loaded workbook because no metric or insight evidence matches 'market share'.",
  "confidence": {"bucket": "cannot_answer", "score": 0.0},
  "citations": [],
  "warnings": [
    {"code": "metric_not_found", "message": "No canonical metric matched market share."}
  ],
  "clarification_requests": [
    {
      "question": "Did you mean one of these available metrics?",
      "options": ["revenue", "sales_volume", "export_sales"]
    }
  ]
}
```

## 8. Deterministic vs LLM Responsibilities

### Always Deterministic

- Query plan schema validation.
- Metric normalization for query terms.
- Year extraction and relative-year resolution.
- Financial retrieval.
- Insight retrieval scoring and selection.
- Numeric coercion and unit checks.
- All calculations.
- Conflict assessment.
- Confidence scoring.
- Citation construction.
- Warning generation.
- Final evidence package.

### Optional LLM Use

- Rephrase the deterministic answer into smoother prose.
- Summarize already-selected insight evidence.
- Generate suggested follow-up questions from selected evidence.

### Hard Boundaries

- LLM may not select evidence.
- LLM may not perform calculations.
- LLM may not change values, years, citations, conflicts, warnings, or confidence.
- LLM output must be discarded if it introduces uncited facts or contradicts deterministic evidence.
- Deterministic renderer remains the primary MVP path.

## 9. Golden Evaluation Framework

The Query Engine needs a golden regression suite before implementation is considered production-ready.

### Fixture Inputs

- Lucky Cement structured input bundle.
- Millat structured input bundle.
- Small synthetic bundle with known conflicts.
- Synthetic workbook with missing cell mappings.
- Synthetic insight-only bundle.

### Question Categories

| Category | Example | Expected Assertion |
|---|---|---|
| Metric lookup | What was revenue in 2025? | Exact metric, year, value, citation. |
| EPS lookup | What was EPS in 2025? | Unit-aware value, no scale corruption. |
| Trend | Show operating profit trend. | Ordered years and values. |
| Growth | Show revenue growth over 5 years. | Correct formula or missing-year warning. |
| Comparison | Compare debt and cash. | Both metrics retrieved and cited. |
| Insight | What were the major risks? | Relevant insights and section citations. |
| Mixed | Explain cash decline despite higher profit. | Financial deltas plus insight evidence. |
| Conflict | What was cash in 2025? | Conflict warning and competing candidates. |
| Ambiguous metric | Show margin. | Clarification request. |
| Missing evidence | What was market share? | Cannot answer with options if available. |

### Correctness Measures

| Dimension | Measurement |
|---|---|
| Planner correctness | Expected `query_type`, `intent`, metrics, and years. |
| Retrieval correctness | Expected metric rows selected; no incorrect fuzzy matches. |
| Calculation correctness | Exact numeric result within tolerance. |
| Citation correctness | Expected workbook sheet/cell and source page. |
| Conflict correctness | Expected conflict surfaced with selected and competing candidates. |
| Confidence correctness | Expected bucket and hard caps. |
| Determinism | Same input and question produce identical structured response. |
| Narrative safety | Answer contains no uncited values or unsupported claims. |

### Confidence Expectations

- Clean direct lookup: High.
- Review-gated answer: Medium maximum.
- Fuzzy metric match: Medium maximum.
- Unresolved conflict: Low maximum.
- Missing required input: Low or Cannot Answer.
- No evidence: Cannot Answer.

### CI Gate

Phase 1 cannot be considered complete until:

- 100% of golden metric lookup tests pass.
- 100% of citation tests pass.
- 100% of conflict scenario tests surface conflicts correctly.
- 0 uncited numeric claims appear in rendered answers.

## 10. API Scope

### MVP Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /query-engine/workbooks` | Load a `QueryEngineInputBundle` and make it current. |
| `GET /query-engine/workbooks/current` | Return active workbook metadata and quality summary. |
| `POST /query-engine/query` | Execute a query against the current or specified workbook id. |

Deferred:

- Metric catalog.
- Insight catalog.
- Query history.
- Answer style controls.
- Multi-workbook search.

## 11. Failure Modes

| Failure | Response |
|---|---|
| Missing input bundle sidecar | Reject production load with `structured_input_required`. |
| Fingerprint mismatch | Reject with `workbook_fingerprint_mismatch`. |
| Unsupported schema major version | Reject with `unsupported_schema_version`. |
| Workbook file missing but structured data exists | Load KB but mark workbook cell citations unavailable. |
| Missing cell mapping | Answer may proceed with page/table citation and warning. |
| No current workbook | Return `workbook_not_loaded`. |
| Stale workbook id | Return `workbook_not_active`. |
| Ambiguous metric | Return `needs_clarification`. |
| Missing years | Return partial answer or insufficient evidence. |
| Non-numeric calculation input | Return calculation warning, not exception. |
| Unit mismatch | Refuse calculation with warning. |
| Unresolved critical conflict | Caveat answer or request clarification. |

## 12. Implementation Phases

### Phase 0: Handoff Contract

- Create versioned `QueryEngineInputBundle`.
- Persist `WorkbookCellMappingRecord`.
- Add `workbook_fingerprint`.
- Serialize structured sidecar next to workbook.
- Add load-time contract validation.

### Phase 1: Deterministic Financial Q&A

- Build `CompanyKnowledgeBase` from structured input.
- Build metric and cell mapping indexes.
- Implement Query Planner for lookup, trend, comparison, and growth.
- Implement Financial Retrieval Service.
- Implement Calculation Service with numeric/unit guards.
- Implement Citation Service.
- Implement deterministic Response Renderer.

### Phase 2: Conflicts and Confidence

- Project `ConsolidationGroup` into conflict records.
- Implement Confidence Service rule table.
- Add clarification request transport.
- Expand golden eval coverage.

### Phase 3: Insights and Mixed Q&A

- Build insight index.
- Implement Insight Retrieval Service.
- Implement mixed evidence assembly.
- Support insight review inclusion with explicit warnings.

### Phase 4: Optional LLM Polishing

- Add LLM rewrite only after deterministic response exists.
- Validate no uncited facts are introduced.
- Keep deterministic response as fallback and audit source.

### Phase 5: Multi-Session / Enterprise

- Multi-session registry.
- Persistent KB storage.
- Query logs and analytics.
- User feedback and analyst review workflows.
- Semantic insight retrieval.

## 13. Remaining Risks

| Risk | Mitigation |
|---|---|
| Cell mappings are not yet persisted | Phase 0 blocks implementation until resolved. |
| Unit/scale metadata may remain incomplete | Calculation Service refuses cross-unit math unless units are known or safely inferable. |
| Query metric normalization can over-match | Fuzzy matching capped and headline metrics prefer clarification. |
| Conflicts may be resolved upstream but still analytically relevant | Response can include resolved conflict metadata for critical metrics when requested. |
| Insight retrieval may be keyword-noisy | MVP uses weighted scoring; semantic retrieval is deferred. |
| Workbook-only user upload expectation conflicts with structured-input requirement | Electron/FastAPI must upload the workbook plus sidecar as one bundle. |

## 14. Unresolved Decisions

| Decision | Recommended Default |
|---|---|
| Sidecar format | JSON for MVP; parquet optional later for larger datasets. |
| Sidecar file naming | `<workbook_stem>.kb.json`. |
| Workbook-only degraded mode | Developer/debug only, disabled in production. |
| LLM polishing | Disabled for MVP. |
| Semantic insight search | Defer until keyword/structured retrieval has golden baseline. |
| Unit metadata owner | Upstream consolidation should own units; Query Engine enforces consistency. |

## 15. Final Architecture Assessment

Updated score: 8.6 / 10.

The original architecture had strong boundaries but the wrong source-of-truth premise. After reconciliation, the design is implementation-ready because it now consumes the structured artifacts that already contain consolidation, confidence, scope, conflict, and provenance metadata.

Implementation can proceed safely only in this order:

1. Implement the structured input bundle and persisted cell mappings.
2. Build deterministic financial Q&A against the bundle.
3. Add conflict/confidence and golden tests.
4. Add insight and mixed Q&A.
5. Add optional LLM polishing after deterministic correctness is proven.

Do not implement the original workbook-only parsing architecture for production.
