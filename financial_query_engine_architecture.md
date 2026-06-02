# Financial Query Engine Architecture

## 1. Purpose

The Financial Query Engine answers user questions against a generated OCR workbook. The workbook is parsed once on upload, converted into in-memory analytical structures, and reused until the user uploads a different workbook or the application closes.

The engine must support:

- Financial questions: metric lookup, trends, comparisons, growth calculations.
- Insight questions: risks, drivers, management commentary, operational explanations.
- Mixed questions: combine financial values with narrative evidence.

The Query Engine should not re-run OCR, normalize raw PDF tables, mutate the workbook, or perform forecasting. It consumes the OCR Engine's final workbook and exposes a reliable question-answering layer with citations, confidence, and conflict visibility.

## 2. High-Level Architecture

```text
Generated Workbook (.xlsx)
        |
        v
Workbook Upload / Selection
        |
        v
Workbook Parser
        |
        +--> FinancialDataFrame
        +--> InsightsDataFrame
        +--> InsightsReviewDataFrame
        |
        v
CompanyKnowledgeBase
        |
        v
Query API
        |
        v
Query Planner
        |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
Financial Retrieval   Insight Retrieval    Calculation Service
        |                    |                    |
        +--------------------+--------------------+
                             |
                             v
                      Evidence Builder
                             |
                             v
              Conflict + Confidence Evaluation
                             |
                             v
                 Citation / Provenance Builder
                             |
                             v
                  Narrative Generation Layer
                             |
                             v
                         QueryResponse
```

## 3. Service Boundaries

| Service | Responsibility | Must Not Do |
|---|---|---|
| Workbook Parser | Load workbook once, parse financial and insight sheets into dataframes, build indexes. | Run OCR, call OpenAI, infer missing financial facts. |
| Knowledge Base Store | Hold the active `CompanyKnowledgeBase` in memory for the current workbook. | Persist long-term user data unless explicitly added later. |
| Query Planner | Classify query intent, identify requested metrics, years, calculations, and evidence needs. | Generate final answers directly. |
| Financial Retrieval Service | Retrieve metric values from `FinancialDataFrame`. | Interpret narrative explanations. |
| Insight Retrieval Service | Retrieve relevant insights from `InsightsDataFrame` and optionally review insights. | Calculate financial metrics. |
| Calculation Service | Compute deterministic financial calculations such as growth, deltas, trends, and comparisons. | Forecast future values or invent missing data. |
| Evidence Builder | Combine financial values, insights, calculations, conflicts, and citations into structured evidence. | Hide conflicts or low-confidence data. |
| Conflict Handling Service | Detect unresolved conflicts, review-gated values, duplicate candidates, and ambiguous answers. | Override analyst-review requirements silently. |
| Confidence Service | Score answer confidence based on data quality, retrieval quality, conflicts, and coverage. | Treat LLM confidence as the only confidence source. |
| Citation Service | Attach workbook sheet, cell, metric, page, section, and source report provenance. | Create citations without source backing. |
| Narrative Generation Layer | Turn structured evidence into a user-facing answer. | Perform unsupported calculations or use uncited facts. |

## 4. Core Models

### CompanyKnowledgeBase

Represents the active in-memory knowledge base for one uploaded workbook.

| Field | Type | Purpose |
|---|---|---|
| workbook_id | string | Stable identifier for the uploaded workbook session. |
| workbook_path | string | Local path to the parsed workbook. |
| workbook_fingerprint | string | Hash or fingerprint used to detect stale uploads. |
| company_name | string or null | Company name from workbook metadata when available. |
| report_years | list of integer | Years available in the workbook. |
| loaded_at | datetime | Time the workbook was loaded into memory. |
| financial_data | FinancialDataFrame | Parsed metric values from financial sheets. |
| insights_data | InsightsDataFrame | High-confidence exported insights. |
| insights_review_data | InsightsReviewDataFrame | Review-bucket insights. |
| metric_index | MetricIndex | Fast lookup index by canonical metric, aliases, year, table type, and statement scope. |
| insight_index | InsightIndex | Fast lookup index by area, section, year, keywords, and confidence. |
| provenance_index | ProvenanceIndex | Lookup of workbook cells, PDF page numbers, source report years, and sections. |
| conflict_index | ConflictIndex | Lookup of unresolved conflicts and competing candidates. |
| quality_summary | KnowledgeBaseQualitySummary | Workbook-level quality, review count, conflict count, and coverage. |

### FinancialDataFrame

One row should represent one financial value after OCR workbook population and consolidation.

| Field | Type | Purpose |
|---|---|---|
| metric | string | Canonical metric name, for example `revenue`. |
| display_name | string | Human-readable metric name. |
| original_metric | string or null | Original extracted label when available. |
| value_year | integer | Financial year the value belongs to. |
| value | number or string | Reported value. |
| table_type | string | Source table type, for example `income_statement`. |
| statement_scope | string | `consolidated`, `standalone`, or `unknown`. |
| source_report_year | integer | Annual report year from which the value was sourced. |
| source_class | string | Source priority class, for example financial statement, note disclosure, or workbook-generated. |
| sheet_name | string | Workbook sheet containing the value. |
| cell_reference | string or null | Excel cell reference when available. |
| page_number | integer or null | PDF source page number. |
| normalized_confidence | float | Confidence of metric normalization. |
| requires_review | boolean | Whether the value should be handled with caution. |
| unresolved_conflict | boolean | Whether unresolved competing values exist. |
| conflict_group_id | string or null | Conflict group reference. |
| units | string or null | Unit metadata when available. |

### InsightsDataFrame

One row should represent one accepted insight.

| Field | Type | Purpose |
|---|---|---|
| insight_id | string | Stable insight identifier. |
| area | string | Business area, for example Debt, Exports, ESG. |
| takeaway | string | Concise extracted insight. |
| source_section | string | Report section used as evidence. |
| page_number | integer | Source page. |
| value_year | integer or null | Year the insight concerns, when known. |
| source_report_year | integer | Report year from which the insight came. |
| confidence | float | Backend-governed confidence. |
| sheet_name | string | Workbook sheet name. |
| row_reference | integer or null | Workbook row reference. |

### InsightsReviewDataFrame

Same shape as `InsightsDataFrame`, with additional review metadata.

| Field | Type | Purpose |
|---|---|---|
| review_reason | string | Reason the insight was placed in review. |
| generic_filter_flag | boolean | Whether generic governance/compliance filtering was triggered. |
| quantitative_evidence_present | boolean | Whether quantitative evidence protected a low-confidence insight from rejection. |

### QueryRequest

| Field | Type | Purpose |
|---|---|---|
| question | string | User question. |
| workbook_id | string or null | Optional workbook identifier. Defaults to current workbook. |
| preferred_years | list of integer or null | Optional user-selected years. |
| include_review_data | boolean | Whether review-gated values and review insights may be used. |
| answer_style | string | `concise`, `analyst`, or `table`. |
| max_citations | integer | Maximum citations to return. |

### QueryPlan

| Field | Type | Purpose |
|---|---|---|
| query_type | string | `financial`, `insight`, or `mixed`. |
| intent | string | Lookup, trend, comparison, growth, explanation, risk summary, or mixed explanation. |
| metrics | list of string | Canonical metric candidates. |
| years | list of integer | Requested or inferred years. |
| table_types | list of string | Optional table filters. |
| insight_areas | list of string | Insight areas to retrieve. |
| calculations | list of string | Required deterministic calculations. |
| evidence_requirements | list of string | Financial, insight, calculation, conflict, or citation requirements. |
| ambiguity | list of string | Unresolved planning ambiguities. |

### QueryResponse

| Field | Type | Purpose |
|---|---|---|
| answer | string | Final user-facing answer. |
| query_type | string | Financial, insight, or mixed. |
| confidence | ConfidenceAssessment | Overall answer confidence. |
| financial_evidence | list of FinancialEvidence | Metric values used. |
| insight_evidence | list of InsightEvidence | Insights used. |
| calculations | list of CalculationResult | Deterministic calculations performed. |
| conflicts | list of ConflictRecord | Relevant conflicts or competing values. |
| citations | list of Citation | Workbook and report source references. |
| warnings | list of string | Missing data, review-gated data, ambiguous metric, or calculation warnings. |
| follow_up_suggestions | list of string | Optional next questions. |

## 5. Query Pipeline

1. Receive query through API.
2. Verify that a workbook is loaded.
3. Normalize the question text.
4. Use the Query Planner to classify intent.
5. Normalize requested metric names using the shared metric registry.
6. Retrieve financial evidence when the query needs numeric data.
7. Retrieve insight evidence when the query needs explanation or qualitative context.
8. Run deterministic calculations when needed.
9. Build structured evidence with citations and provenance.
10. Evaluate conflicts and review-gated data.
11. Compute answer confidence.
12. Generate final narrative from evidence only.
13. Return answer, citations, warnings, conflicts, and confidence.

## 6. Query Planner

The Query Planner should be deterministic-first. LLM planning can be added later, but the MVP should support high-value questions using rules and metric normalization.

| Intent | Example | Required Services |
|---|---|---|
| Metric lookup | What was revenue in 2025? | Financial Retrieval |
| Metric comparison | Compare debt and cash. | Financial Retrieval, Calculation |
| Trend | Show operating profit trend. | Financial Retrieval, Calculation |
| Growth | Show revenue growth over 5 years. | Financial Retrieval, Calculation |
| Explanation | Why did operating profit decline? | Financial Retrieval, Calculation, Insight Retrieval |
| Risk summary | What were the major risks? | Insight Retrieval |
| Mixed explanation | Explain the decline in cash despite higher profit. | Financial Retrieval, Calculation, Insight Retrieval |

Planner responsibilities:

- Identify whether the query is financial, insight-only, or mixed.
- Extract candidate metrics, years, periods, and comparison targets.
- Identify whether a calculation is required.
- Decide whether insight retrieval is necessary.
- Flag ambiguity instead of guessing when terms are unclear.

## 7. Financial Retrieval Service

Financial retrieval should use a layered strategy:

1. Exact canonical metric match.
2. Alias match through shared normalization.
3. Deterministic dirty-alias match from registry.
4. Optional fuzzy match with high threshold.
5. Return ambiguity when multiple plausible metrics remain.

Retrieval filters:

- `value_year`
- `table_type`
- `statement_scope`
- `source_report_year`
- `requires_review`
- `unresolved_conflict`
- `source_class`

Retrieval ranking:

1. Non-conflicted consolidated value.
2. Higher normalization confidence.
3. Preferred statement scope when user specifies consolidated or standalone.
4. Financial statement source before note disclosure for headline metrics.
5. Latest source report year only when quality is otherwise equal.

## 8. Insight Retrieval Service

Insight retrieval should combine structured filtering and text relevance.

Retrieval signals:

- Area match, for example Debt, Exports, Cost, ESG.
- Metric-linked terms in the question.
- Source section relevance.
- Year or source report year match.
- Confidence bucket.
- Keyword overlap with takeaway.
- Optional semantic similarity in later phases.

Review insights should not be used by default. They may be included when:

- `include_review_data` is true.
- No high-confidence insight is available.
- The answer clearly labels them as review-level evidence.

## 9. Calculation Service

The Calculation Service performs deterministic calculations only.

Supported MVP calculations:

- Single metric lookup.
- Multi-year trend.
- Year-over-year delta.
- Year-over-year percentage growth.
- Five-year growth where enough years exist.
- CAGR.
- Metric comparison.
- Cash movement explanations using financial deltas plus insights.

Guardrails:

- Do not forecast.
- Do not calculate from unresolved conflicts unless explicitly allowed.
- Do not mix consolidated and standalone values unless the user asks for both.
- Do not silently use review-gated values.
- Return calculation warnings when years are missing.

## 10. Evidence Builder

Evidence should be structured before narrative generation.

Financial evidence includes:

- Metric.
- Value year.
- Value.
- Sheet name.
- Cell reference.
- Page number.
- Source report year.
- Table type.
- Statement scope.
- Review and conflict flags.

Insight evidence includes:

- Area.
- Takeaway.
- Source section.
- Page number.
- Source report year.
- Confidence.
- Review bucket status.

Calculation evidence includes:

- Formula description.
- Input values.
- Output value.
- Missing inputs.
- Warnings.

## 11. Citation and Provenance Layer

Every factual answer should cite evidence.

Citation types:

| Citation Type | Example |
|---|---|
| Workbook cell | Income Statement, cell C12 |
| Workbook row | Insights, row 8 |
| PDF page | Annual report page 84 |
| Report section | Management Discussion & Analysis |
| Source report year | 2025 annual report |
| Conflict group | Conflict group for revenue 2024 |

Citation policy:

- Numeric answers must cite workbook sheet and cell when available.
- Insight answers must cite source section and page.
- Mixed answers should include both financial and insight citations.
- If cell-level provenance is unavailable, use sheet and metric row provenance.

## 12. Confidence Model

The final confidence score should be backend-calibrated, not copied from a narrative model.

Recommended confidence components:

| Component | Description |
|---|---|
| Retrieval confidence | Strength of metric or insight match. |
| Data confidence | Normalization confidence and source quality. |
| Conflict penalty | Reduces confidence for unresolved conflicts or competing candidates. |
| Review penalty | Reduces confidence when review-gated evidence is used. |
| Coverage score | Whether all requested years and metrics were found. |
| Calculation completeness | Whether calculations had complete inputs. |
| Insight confidence | Confidence of retrieved narrative insights. |

Confidence buckets:

| Bucket | Meaning |
|---|---|
| High | Clean evidence, no material conflicts, complete coverage. |
| Medium | Minor missing data, review evidence, or weak insight support. |
| Low | Missing core evidence, unresolved conflicts, or ambiguous metric. |
| Cannot answer | Required evidence unavailable or too conflicted. |

## 13. Conflict Handling

Conflict handling must be visible to the user and to downstream systems.

Conflict types:

- Multiple values for the same metric and year.
- Statement vs note disagreement.
- Consolidated vs standalone ambiguity.
- Scale disagreement.
- Year disagreement.
- Review-gated metric used in answer.
- Missing core metric.
- Ambiguous query term.

Policy:

- Do not hide unresolved conflicts.
- Prefer clean consolidated values only when deterministic precedence is available.
- If a value is unresolved, answer with a caveat or ask for clarification.
- For critical metrics, include competing candidates when confidence is not high.

## 14. API Contracts

### Upload Workbook

Endpoint:

```text
POST /query-engine/workbooks
```

Request:

| Field | Type | Purpose |
|---|---|---|
| workbook_file | file | Generated OCR workbook. |
| replace_current | boolean | Whether to replace the active workbook. |

Response:

| Field | Type | Purpose |
|---|---|---|
| workbook_id | string | Active workbook identifier. |
| status | string | Loaded, failed, or partially_loaded. |
| company_name | string or null | Parsed company name. |
| report_years | list of integer | Available years. |
| quality_summary | object | Metric count, insight count, review count, conflict count. |
| warnings | list of string | Parser warnings. |

### Query

Endpoint:

```text
POST /query-engine/query
```

Request:

| Field | Type | Purpose |
|---|---|---|
| question | string | User question. |
| workbook_id | string or null | Optional workbook identifier. |
| include_review_data | boolean | Whether review-gated evidence may be used. |
| answer_style | string | Concise, analyst, or table. |

Response:

| Field | Type | Purpose |
|---|---|---|
| answer | string | Final answer. |
| confidence | object | Confidence score and bucket. |
| citations | list | Source citations. |
| financial_evidence | list | Numeric evidence used. |
| insight_evidence | list | Narrative evidence used. |
| calculations | list | Calculations performed. |
| conflicts | list | Relevant conflicts. |
| warnings | list | Missing data, ambiguity, or review warnings. |

### Current Workbook

Endpoint:

```text
GET /query-engine/workbooks/current
```

Purpose:

Returns the currently loaded workbook metadata and quality summary.

### Clear Current Workbook

Endpoint:

```text
DELETE /query-engine/workbooks/current
```

Purpose:

Clears the active in-memory `CompanyKnowledgeBase`.

### Metric Catalog

Endpoint:

```text
GET /query-engine/metrics
```

Purpose:

Returns available metrics, years, table types, review flags, and conflict counts.

### Insight Catalog

Endpoint:

```text
GET /query-engine/insights
```

Purpose:

Returns available insight areas, sections, years, and confidence distribution.

## 15. Failure Modes

| Failure Mode | Handling |
|---|---|
| No workbook loaded | Return explicit `workbook_not_loaded` error. |
| Workbook cannot be parsed | Return parser diagnostics and do not replace current valid workbook. |
| Required financial sheets missing | Load partial knowledge base and report missing sheets. |
| Insights sheet missing | Financial questions continue to work; insight questions return unavailable. |
| Metric not found | Return nearest known metrics and ask for clarification. |
| Year not found | Return available years for the requested metric. |
| Multiple conflicting values | Return conflict warning and competing candidates. |
| Review-gated value requested | Use only when allowed; otherwise warn and exclude. |
| Calculation input missing | Return partial calculation with missing input warning. |
| Narrative model unavailable | Return deterministic evidence summary. |
| Memory pressure | Clear current knowledge base or reject upload with actionable error. |
| Stale workbook id | Return `workbook_not_active` or load requested workbook if persistence exists later. |

## 16. MVP Scope

The MVP should prioritize deterministic, high-trust answers.

Included:

- Parse generated workbook into `CompanyKnowledgeBase`.
- Keep one active workbook in memory.
- Answer metric lookup questions.
- Answer trend and comparison questions.
- Calculate YoY growth and CAGR.
- Retrieve high-confidence insights by area and keyword.
- Answer mixed questions using financial deltas plus insights.
- Return citations, confidence, conflicts, and warnings.
- Expose workbook quality summary.

Excluded from MVP:

- Multi-company comparison.
- Forecasting.
- External market data.
- Long-term persisted knowledge bases.
- Agentic multi-step analysis beyond the query plan.
- Automatic analyst-judgment conflict resolution.

## 17. Implementation Phases

### Phase 1: Deterministic Financial Q&A

- Workbook parser.
- In-memory `CompanyKnowledgeBase`.
- Metric index.
- Financial retrieval.
- Basic calculation service.
- Evidence and citation builder.
- Query API.

### Phase 2: Insight and Mixed Q&A

- Insight index.
- Insight retrieval.
- Mixed query planner.
- Combined financial and narrative evidence.
- Confidence model.
- Conflict handling model.

### Phase 3: Narrative Generation

- Structured prompt inputs from evidence only.
- Deterministic fallback answer generator.
- Citation-aware response generation.
- Answer style controls.

### Phase 4: Advanced Retrieval

- Local embeddings for insights.
- Semantic metric and insight search.
- Query history.
- User feedback loop.
- Suggested follow-up questions.

### Phase 5: Enterprise Readiness

- Multi-workbook sessions.
- Multi-company support.
- Persisted knowledge bases.
- Access control.
- Audit logs.
- Query observability.
- Performance monitoring.

## 18. Future Roadmap

- Chart-ready query responses for trend visualization.
- Explainability drilldowns from answer to workbook cell to PDF page.
- Analyst review workflow for conflicted or review-gated values.
- User-confirmed conflict resolution.
- Formula-aware workbook parser.
- Multi-company benchmarking.
- Integration with Forecast Validation Engine.
- Integration with Qualitative Analysis Engine.
- Persistent vector index for insights.
- Natural language chart generation.

## 19. Readiness Notes for Downstream Engines

### Financial Query Engine

The Query Engine should use consolidated values by default and expose review/conflict flags. It should be ready for core financial lookup and trend questions once workbook parsing and provenance indexing are implemented.

### Forecast Validation Engine

The Forecast Validation Engine should consume the same `FinancialDataFrame` shape, but only after filtering unresolved conflicts and review-gated values. It should use `value_year`, not `source_report_year`, for historical series construction.

### Qualitative Analysis Engine

The Qualitative Analysis Engine should consume `InsightsDataFrame` and `InsightsReviewDataFrame`, preserving section, page, year, and confidence metadata. It should not rely on workbook text alone when PDF provenance is available.

## 20. Design Principles

- Workbook is the Query Engine's source of truth.
- Values and insights must remain cited.
- Conflicts must be exposed, not hidden.
- Deterministic calculations should happen outside narrative generation.
- The narrative layer should explain evidence, not invent evidence.
- Review-gated data may be useful, but must be labeled.
- One active workbook keeps the MVP simple and predictable.
- `value_year` and `source_report_year` remain separate concepts.
