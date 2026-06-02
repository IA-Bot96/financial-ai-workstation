# Financial DataFrame and Insight DataFrame Design

## 1. Scope

This document defines the Parsing Layer output contracts for the Financial Query Engine.

Target flow:

```text
.xlsx + CanonicalMetricRegistry
        |
        v
Parsing Layer
        |
        +--> FinancialDataFrame
        +--> InsightDataFrame
        +--> ParsingReport
        |
        v
CompanyKnowledgeBase
```

Important reconciliation note: `financial_query_engine_architecture_reconciled.md` was not present in the workspace. This design uses `financial_query_engine_implementation_design.md` as the reconciled architecture source. The architectural conclusion remains: visible workbook cells alone are not enough for production Query Engine data. The workbook must either contain machine-readable metadata sheets or be uploaded with an equivalent structured sidecar.

## 2. Parser Source of Truth

The Parsing Layer is the sole producer of Query Engine analytical data. It should not expose raw workbook parsing directly to the Query Engine.

Production-safe input:

```text
Generated workbook (.xlsx)
+ CanonicalMetricRegistry
+ embedded machine-readable workbook metadata
```

Recommended workbook metadata sheets:

| Sheet | Visibility | Purpose |
|---|---|---|
| `_fi_manifest` | hidden | Workbook id, fingerprint, schema version, company, report years, registry hash. |
| `_fi_financial_values` | hidden | Flattened selected financial records. |
| `_fi_consolidation_groups` | hidden | Duplicate/conflict groups and competing candidates. |
| `_fi_cell_mappings` | hidden | Authoritative workbook sheet/cell references. |
| `_fi_insights` | hidden or visible mirror | Accepted insight records. |
| `_fi_insights_review` | hidden or visible mirror | Review-bucket insight records. |

If metadata sheets are not available, the parser may enter degraded visible-grid mode. Degraded mode can parse visible financial sheets with the registry, but it cannot reconstruct authoritative conflict metadata, source class, statement scope, normalization confidence, source report year, or competing candidates. Degraded output is not sufficient for production financial Q&A.

## 3. Is DataFrame the Right Abstraction?

### Option A: Pandas DataFrame

Pros:

- Familiar to data teams.
- Convenient filtering and grouping.
- Easy integration with analytics code.

Cons:

- Weak schema enforcement.
- Nested provenance/conflict fields become awkward.
- Decimal precision and mixed value types are easy to corrupt.
- Poor boundary model for FastAPI/Electron serialization.
- Harder to guarantee invariants such as `value_year <= source_report_year`.

Verdict: useful as a runtime view, not as the canonical parser output.

### Option B: Typed Records

Pros:

- Strong validation.
- Excellent provenance and conflict modeling.
- Stable JSON serialization.
- Easy to index in memory.
- Safer for financial correctness.

Cons:

- More verbose.
- Filtering/grouping requires indexes or conversion to a dataframe view.

Verdict: best canonical contract.

### Option C: Columnar Model

Pros:

- Efficient for large data volumes.
- Good for vectorized calculations.
- Natural fit for Parquet/Arrow.

Cons:

- Overkill for single-workbook MVP.
- Nested evidence/citation/conflict structures are less ergonomic.
- Less friendly for API responses.

Verdict: good future storage format, not MVP contract.

### Recommended Approach: Hybrid

Use typed immutable records as the canonical parser output. Expose optional dataframe views for runtime analytics.

```text
Canonical contract:
  FinancialDataFrame.rows: tuple[FinancialDataRecord, ...]
  InsightDataFrame.rows: tuple[InsightDataRecord, ...]

Runtime convenience:
  to_pandas()
  to_arrow()
  metric_index
  insight_index
```

The word `DataFrame` should mean "validated analytical table", not necessarily `pandas.DataFrame`.

## 4. FinancialDataFrame Model

### Purpose

`FinancialDataFrame` is the Query Engine's authoritative financial dataset. It contains selected consolidated values only. Competing candidates live in `FinancialConflictFrame`, linked by `conflict_group_id`.

### Required Fields

| Field | Type | Description |
|---|---|---|
| schema_version | string | Parser output schema version. |
| workbook_id | string | Stable workbook/session id. |
| workbook_fingerprint | string | Hash binding workbook content to parsed metadata. |
| company_name | string | Company name. |
| registry_hash | string | Hash of the canonical metric registry used for validation. |
| records | tuple[FinancialDataRecord, ...] | Selected financial value records. |
| conflicts | FinancialConflictFrame | Duplicate/conflict groups. |
| generated_at | datetime | Parse completion timestamp. |
| parser_mode | string | `metadata_backed` or `degraded_grid_parse`. |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| source_workbook_path | string | Local workbook path. |
| report_years | tuple[int, ...] | Available financial years. |
| warnings | tuple[ParsingWarning, ...] | Parser warnings. |
| quality_summary | FinancialDataQualitySummary | Counts and readiness indicators. |

### FinancialDataRecord Required Fields

| Field | Type | Description |
|---|---|---|
| record_id | string | Deterministic id for the selected value. |
| metric | string | Canonical snake_case metric key from registry. |
| display_name | string | Registry display name. |
| category | string | Registry category, for example `income_statement`. |
| value_year | int | Financial year represented by the value. |
| source_report_year | int | Report year from which the value was sourced. |
| value_raw | string | Original workbook/metadata value representation. |
| value_kind | string | `numeric`, `text`, `missing`, or `not_applicable`. |
| value | Decimal/string/null | Parsed value. Decimal for numeric values. |
| table_type | string | Source table type. |
| source_class | string | `primary_statement`, `note_disclosure`, `analysis_or_ratio`, `supporting_schedule`, or `unclassified`. |
| statement_scope | string | `consolidated`, `standalone`, or `unknown`. |
| normalization_confidence | float | Normalization confidence from 0 to 1. |
| requires_review | bool | Whether this value should be review-gated. |
| provenance | FinancialProvenance | Source report, page, workbook, and table provenance. |
| workbook_citation | WorkbookCitation | Authoritative workbook cell/range citation. |
| confidence | FinancialRecordConfidence | Record-level confidence components. |
| conflict | FinancialConflictReference | Conflict state for this selected value. |

### FinancialDataRecord Optional Fields

| Field | Type | Description |
|---|---|---|
| original_metric | string | Raw metric label before normalization. |
| normalization_input_metric | string | Metric text used by normalizer if different from original. |
| normalization_rule | string | Rule that produced the canonical metric. |
| parent_metric_context | string | Preserved note/header parent context. |
| unit | string | `currency`, `percentage`, `per_share`, `ratio`, `days`, `count`, `text`, or `unknown`. |
| currency | string | ISO currency code where applicable, for example `PKR`. |
| scale | string | `ones`, `thousands`, `millions`, `billions`, or `unknown`. |
| source_table_id | string | OCR/detection table id when available. |
| table_index | int | Table index on page. |
| detected_table_id | string | Propagated detection identity. |
| extraction_quality_score | float | Extraction quality score from OCR pipeline. |
| tags | tuple[string, ...] | Optional query/retrieval tags. |

### Provenance Fields

`FinancialProvenance` captures where the financial value originated before workbook population.

Required:

| Field | Type | Description |
|---|---|---|
| source_report_year | int | Annual report year. |
| page_number | int | One-based PDF page number. |
| table_type | string | Classified table type. |
| source_class | string | Coarse source class. |

Optional:

| Field | Type | Description |
|---|---|---|
| source_section | string | Section or note name when available. |
| source_table_id | string | Table identity propagated from OCR. |
| bbox | tuple[float, float, float, float] | Source table bounding box. |
| row_index | int | Row index in extracted table. |
| column_index | int | Column index in extracted table. |
| extraction_strategy | string | Camelot/pdfplumber/text-mode/other. |

### Workbook Citation Fields

`WorkbookCitation` is mandatory in production mode, even when cell-level mapping is missing. It carries status.

Required:

| Field | Type | Description |
|---|---|---|
| workbook_fingerprint | string | Workbook hash. |
| sheet_name | string | Workbook sheet. |
| citation_status | string | `cell_mapped`, `row_mapped`, `sheet_only`, or `missing`. |

Optional:

| Field | Type | Description |
|---|---|---|
| cell_reference | string | Excel cell, for example `C12`. |
| row | int | One-based row. |
| column | int | One-based column. |
| range_reference | string | Excel range, for example `A12:C12`. |
| visible_label | string | Label as displayed in workbook. |
| write_status | string | `written`, `skipped_formula`, `mapping_missing`, or `conflict_replaced`. |

### Conflict Fields

Each selected financial row has a compact conflict reference.

| Field | Type | Description |
|---|---|---|
| conflict_group_id | string/null | Deterministic conflict group id. |
| candidate_id | string | Candidate id of the selected value. |
| candidate_count | int | Number of candidates considered. |
| is_duplicate_group | bool | Multiple candidates existed. |
| is_conflict_group | bool | Candidate values differed. |
| conflict_resolved | bool | Conflict resolved deterministically. |
| unresolved_conflict | bool | Analyst/policy review still needed. |
| conflict_status | string | Human-readable status. |
| resolution_reason | string | Deterministic reason selected. |

Competing candidates are not duplicated on every financial row. They live in `FinancialConflictFrame`.

### Confidence Fields

`FinancialRecordConfidence` should be deterministic and componentized.

| Field | Type | Description |
|---|---|---|
| normalization_confidence | float | Canonical metric mapping confidence. |
| source_confidence | float | Source quality confidence from consolidation candidate. |
| extraction_confidence | float/null | OCR/table extraction confidence when available. |
| value_confidence | float | Numeric parsing and unit confidence. |
| conflict_confidence | float | Confidence after conflict handling. |
| overall_confidence | float | Combined record confidence. |
| confidence_bucket | string | `high`, `medium`, `low`, or `review`. |
| limiting_factors | tuple[string, ...] | Reasons confidence was capped. |

### Normalized Metric Fields

| Field | Required | Description |
|---|---|---|
| metric | Yes | Canonical metric key. |
| display_name | Yes | Registry display name. |
| category | Yes | Registry category. |
| registry_hash | Yes at frame level | Registry version/hash used. |
| original_metric | Optional | Raw label. |
| normalization_input_metric | Optional | Text sent to normalizer. |
| normalization_rule | Optional | Exact/alias/dirty_alias/parent_prefix/metadata. |
| normalization_confidence | Yes | 0 to 1. |
| requires_review | Yes | Review flag. |

Parser rule:

- A record in `FinancialDataFrame.records` must have a canonical `metric`.
- Unmatched visible-grid rows should become parsing warnings or review records, not authoritative financial records.
- No generic catch-all metric is allowed.

### `value_year` vs `source_report_year`

Rules:

- `value_year` is the analytical year used for trends, calculations, forecasts, and queries.
- `source_report_year` is provenance only.
- `value_year <= source_report_year` must always hold.
- Query calculations group by `value_year`.
- Source quality and latest-report provenance use `source_report_year`.
- The parser must never infer `source_report_year` from a visible year column. It must come from metadata.

## 5. FinancialConflictFrame

### Purpose

Conflict data is query-relevant but should not pollute selected financial rows with repeated candidate lists.

### Fields

| Field | Type | Description |
|---|---|---|
| schema_version | string | Conflict schema version. |
| groups | tuple[FinancialConflictGroup, ...] | Duplicate/conflict groups. |

### FinancialConflictGroup

Required fields:

| Field | Type | Description |
|---|---|---|
| conflict_group_id | string | Deterministic id. |
| metric | string | Canonical metric key. |
| value_year | int | Analytical year. |
| selected_candidate_id | string | Candidate chosen by consolidation. |
| candidate_count | int | Candidate count. |
| candidates | tuple[FinancialConflictCandidate, ...] | All candidates. |
| is_duplicate_group | bool | Duplicate group flag. |
| is_conflict_group | bool | Values differ. |
| conflict_resolved | bool | Deterministically resolved. |
| unresolved_conflict | bool | Still requires review. |
| conflict_status | string | User-facing status. |
| resolution_reason | string | Selection rationale. |

### FinancialConflictCandidate

Required fields:

| Field | Type | Description |
|---|---|---|
| candidate_id | string | Candidate id. |
| metric | string | Canonical metric. |
| value_year | int | Analytical year. |
| value_raw | string | Original value representation. |
| value | Decimal/string/null | Candidate value. |
| source_report_year | int | Source report year. |
| page_number | int | Source page. |
| table_type | string | Source table. |
| source_class | string | Source class. |
| statement_scope | string | Scope. |
| normalization_confidence | float | Mapping confidence. |
| requires_review | bool | Review flag. |
| original_metric | string | Raw metric label. |

## 6. InsightDataFrame Model

### Purpose

`InsightDataFrame` is the Query Engine's authoritative narrative evidence dataset. It includes accepted insights and can optionally include review-bucket insights in the same frame via `review_status`.

### Required Fields

| Field | Type | Description |
|---|---|---|
| schema_version | string | Parser output schema version. |
| workbook_id | string | Workbook/session id. |
| workbook_fingerprint | string | Workbook hash. |
| company_name | string | Company name. |
| records | tuple[InsightDataRecord, ...] | Insight records. |
| generated_at | datetime | Parse completion timestamp. |
| parser_mode | string | `metadata_backed` or `degraded_grid_parse`. |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| source_workbook_path | string | Local workbook path. |
| embedding_metadata | EmbeddingMetadata | Embedding model/version/dimensions. |
| warnings | tuple[ParsingWarning, ...] | Parser warnings. |

### InsightDataRecord Required Fields

| Field | Type | Description |
|---|---|---|
| insight_id | string | Deterministic insight id. |
| value_year | int | Year discussed by the insight. |
| source_report_year | int | Annual report year where insight was found. |
| area | string | Business topic. |
| takeaway | string | Concise insight. |
| source_section | string | Annual report section. |
| page_number | int | One-based PDF source page. |
| confidence | float | Insight confidence from 0 to 1. |
| confidence_bucket | string | `high`, `review`, `low`, or `rejected`. |
| review_status | string | `accepted`, `review`, or `rejected`. |
| source_metadata | InsightSourceMetadata | Source traceability. |
| workbook_citation | InsightWorkbookCitation | Workbook row/cell citation. |

### InsightDataRecord Optional Fields

| Field | Type | Description |
|---|---|---|
| review_reason | string | Why the insight is in review/rejected. |
| generic_filter_flag | bool | Governance/compliance boilerplate filter flag. |
| quantitative_evidence_present | bool | Whether numbers protected a low-confidence insight. |
| linked_metrics | tuple[string, ...] | Canonical metrics mentioned or related. |
| keywords | tuple[string, ...] | Extracted retrieval keywords. |
| evidence_refs | tuple[EvidenceReference, ...] | Supporting references. |
| embedding_id | string | Stable id for vector lookup. |
| embedding_model | string | Embedding model name. |
| embedding_vector | tuple[float, ...] | Optional in-memory vector. |
| text_hash | string | Hash of area + takeaway + source metadata. |

### Insight Source Metadata

| Field | Type | Description |
|---|---|---|
| source_report_year | int | Annual report year. |
| value_year | int | Discussed year. |
| source_section | string | Report section. |
| page_number | int | Source page. |
| text_source | string/null | `pymupdf`, `tesseract_ocr`, `manual`, or null. |
| section_confidence | float/null | Section identification confidence. |

### Evidence References

`EvidenceReference` supports linking insights to other evidence.

| Field | Type | Description |
|---|---|---|
| reference_id | string | Stable id. |
| reference_type | string | `pdf_page`, `workbook_cell`, `financial_metric`, `source_section`, or `external_none`. |
| target_id | string | Referenced financial record, insight, or citation id. |
| description | string | Short human-readable reference. |

### Workbook Citations

`InsightWorkbookCitation` should cite the visible workbook row whenever available.

| Field | Type | Description |
|---|---|---|
| sheet_name | string | `Insights` or `Insights Review`. |
| row | int/null | Workbook row. |
| range_reference | string/null | Row range, for example `A8:G8`. |
| area_cell | string/null | Cell containing area. |
| takeaway_cell | string/null | Cell containing takeaway. |
| page_cell | string/null | Cell containing source page. |
| citation_status | string | `row_mapped`, `sheet_only`, or `missing`. |

### Embeddings Support

Embeddings are optional and should not be required for MVP.

Rules:

- If `embedding_vector` is present, `embedding_model` and `embedding_id` are required.
- All vectors in one `InsightDataFrame` must share the same dimension.
- Vectors should not be serialized into the workbook visible sheets.
- For large workbooks, store vectors in a separate embedding store and keep only `embedding_id`.
- Retrieval must work without embeddings using area, keyword, section, year, and confidence scoring.

## 7. Dataclass-Style Contracts

These are implementation contracts, not executable code in this document.

```python
@dataclass(frozen=True, slots=True)
class FinancialDataFrame:
    schema_version: str
    workbook_id: str
    workbook_fingerprint: str
    company_name: str
    registry_hash: str
    records: tuple[FinancialDataRecord, ...]
    conflicts: FinancialConflictFrame
    generated_at: datetime
    parser_mode: Literal["metadata_backed", "degraded_grid_parse"]
    source_workbook_path: str | None = None
    report_years: tuple[int, ...] = ()
    warnings: tuple[ParsingWarning, ...] = ()
    quality_summary: FinancialDataQualitySummary | None = None


@dataclass(frozen=True, slots=True)
class FinancialDataRecord:
    record_id: str
    metric: str
    display_name: str
    category: str
    value_year: int
    source_report_year: int
    value_raw: str
    value_kind: Literal["numeric", "text", "missing", "not_applicable"]
    value: Decimal | str | None
    table_type: str
    source_class: SourceClass
    statement_scope: StatementScope
    normalization_confidence: float
    requires_review: bool
    provenance: FinancialProvenance
    workbook_citation: WorkbookCitation
    confidence: FinancialRecordConfidence
    conflict: FinancialConflictReference
    original_metric: str | None = None
    normalization_input_metric: str | None = None
    normalization_rule: str | None = None
    parent_metric_context: str | None = None
    unit: ValueUnit = "unknown"
    currency: str | None = None
    scale: ValueScale = "unknown"
    source_table_id: str | None = None
    table_index: int | None = None
    detected_table_id: str | None = None
    extraction_quality_score: float | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InsightDataFrame:
    schema_version: str
    workbook_id: str
    workbook_fingerprint: str
    company_name: str
    records: tuple[InsightDataRecord, ...]
    generated_at: datetime
    parser_mode: Literal["metadata_backed", "degraded_grid_parse"]
    source_workbook_path: str | None = None
    embedding_metadata: EmbeddingMetadata | None = None
    warnings: tuple[ParsingWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class InsightDataRecord:
    insight_id: str
    value_year: int
    source_report_year: int
    area: str
    takeaway: str
    source_section: str
    page_number: int
    confidence: float
    confidence_bucket: Literal["high", "review", "low", "rejected"]
    review_status: Literal["accepted", "review", "rejected"]
    source_metadata: InsightSourceMetadata
    workbook_citation: InsightWorkbookCitation
    review_reason: str | None = None
    generic_filter_flag: bool = False
    quantitative_evidence_present: bool = False
    linked_metrics: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceReference, ...] = ()
    embedding_id: str | None = None
    embedding_model: str | None = None
    embedding_vector: tuple[float, ...] | None = None
    text_hash: str | None = None
```

## 8. Validation Rules

### Frame-Level Rules

| Rule | Applies To |
|---|---|
| `schema_version` must be supported by parser and Query Engine. | Both frames |
| `workbook_id` and `workbook_fingerprint` cannot be empty. | Both frames |
| `registry_hash` must match the registry used during parsing. | FinancialDataFrame |
| `records` may be empty only if parser emits a blocking warning. | Both frames |
| `parser_mode = degraded_grid_parse` must emit `degraded_parser_mode` warning. | Both frames |
| All records must share the frame workbook id and fingerprint. | Both frames |

### Financial Record Rules

| Rule |
|---|
| `metric` must be snake_case and exist in `CanonicalMetricRegistry`. |
| `display_name` and `category` must match registry entry for `metric`. |
| `value_year >= 1900`. |
| `source_report_year >= 1900`. |
| `value_year <= source_report_year`. |
| `normalization_confidence` must be between 0 and 1. |
| `requires_review = True` if `normalization_confidence < configured_review_threshold`. |
| `page_number > 0` when PDF provenance is present. |
| `value_kind = numeric` requires `value` to be Decimal. |
| `value_kind != numeric` cannot be used by Calculation Service. |
| `unit = percentage`, `ratio`, `days`, `count`, or `per_share` must not inherit currency scaling. |
| `workbook_citation.citation_status = cell_mapped` requires `cell_reference`, `row`, and `column`. |
| `unresolved_conflict = True` caps query confidence at Low for answers using the row. |

### Conflict Rules

| Rule |
|---|
| `candidate_count == len(candidates)`. |
| `selected_candidate_id` must exist in `candidates`. |
| If candidate values differ, `is_conflict_group = True`. |
| If `unresolved_conflict = True`, `conflict_resolved = False`. |
| Each selected financial record can reference at most one conflict group. |

### Insight Record Rules

| Rule |
|---|
| `area`, `takeaway`, and `source_section` cannot be empty. |
| `page_number > 0`. |
| `0 <= confidence <= 1`. |
| `value_year <= source_report_year`. |
| `review_status = accepted` requires `confidence_bucket = high`. |
| `review_status = review` requires a `review_reason`. |
| `embedding_vector` requires `embedding_id` and `embedding_model`. |
| All embedding vectors in the frame must have the configured dimension. |
| `workbook_citation.citation_status = row_mapped` requires `row` or `range_reference`. |

## 9. Parser Output Contracts

### ParsedWorkbookData

The parser should return one top-level object.

| Field | Type | Description |
|---|---|---|
| schema_version | string | Parser output schema version. |
| workbook_id | string | Loaded workbook id. |
| workbook_fingerprint | string | Workbook/content fingerprint. |
| source_workbook_path | string | Local workbook path. |
| registry_hash | string | Canonical registry hash. |
| financial_data | FinancialDataFrame | Financial analytical records. |
| insight_data | InsightDataFrame | Accepted and review insight records. |
| parsing_report | ParsingReport | Diagnostics and validation results. |

### ParsingReport

| Field | Type | Description |
|---|---|---|
| parser_mode | string | `metadata_backed` or `degraded_grid_parse`. |
| financial_records_loaded | int | Count of financial records. |
| insight_records_loaded | int | Count of insights. |
| conflict_groups_loaded | int | Count of conflict groups. |
| cell_mappings_loaded | int | Count of workbook cell mappings. |
| unmapped_financial_rows | int | Visible workbook rows that could not map to registry. |
| missing_cell_mappings | int | Records missing authoritative cell mapping. |
| validation_errors | tuple[ParsingError, ...] | Blocking errors. |
| warnings | tuple[ParsingWarning, ...] | Non-blocking warnings. |

### Parser Modes

| Mode | Description | Query Engine Use |
|---|---|---|
| `metadata_backed` | Reads machine-readable workbook metadata and validates against registry. | Production. |
| `degraded_grid_parse` | Reads visible sheets and uses registry aliases to infer metrics/years. | Developer/debug only; not authoritative. |

## 10. Serialization Format

### Canonical Format

Use JSON for MVP.

Rules:

- Top-level object is `ParsedWorkbookData`.
- Field names are snake_case.
- Decimal values serialize as strings to preserve precision.
- Datetimes serialize as ISO-8601 UTC strings.
- Tuples serialize as arrays.
- `workbook_fingerprint` and `registry_hash` are required.
- Schema version is required at every frame level.

### Optional Future Formats

| Format | Use |
|---|---|
| JSONL | Large record streams without loading full JSON object. |
| Parquet | Large columnar datasets and analytics. |
| Arrow | In-memory cross-language dataframe transport. |

MVP recommendation: JSON sidecar or hidden workbook metadata sheets parsed into typed records. Pandas export is a view, not a persisted contract.

## 11. Parsing Responsibilities

The parser must:

- Validate workbook fingerprint.
- Validate registry hash.
- Read machine-readable financial records.
- Read machine-readable insight records.
- Validate canonical metrics against registry.
- Build workbook citations from cell mapping metadata.
- Build selected financial rows and conflict groups.
- Preserve `value_year` and `source_report_year`.
- Emit degraded-mode warnings when metadata is missing.
- Produce deterministic record ids.

The parser must not:

- Run OCR.
- Re-run consolidation.
- Re-rank conflict candidates.
- Invent missing confidence or source metadata.
- Use an LLM.
- Perform financial calculations.
- Silently convert unnormalized visible labels into authoritative metrics.

## 12. Record ID Strategy

Use deterministic ids so reloads produce stable references.

Financial record id:

```text
fin:{workbook_fingerprint}:{metric}:{value_year}:{source_report_year}:{table_type}:{cell_reference_or_page}
```

Conflict group id:

```text
conflict:{workbook_fingerprint}:{metric}:{value_year}
```

Insight id:

```text
insight:{workbook_fingerprint}:{value_year}:{source_report_year}:{page_number}:{text_hash}
```

## 13. Query Engine Readiness

The final models support:

- Metric lookup by canonical key.
- Trend construction by `value_year`.
- Source traceability by `source_report_year` and PDF page.
- Workbook citations by sheet/cell.
- Conflict-aware confidence.
- Review-gated retrieval.
- Insight retrieval by area, section, year, keywords, and embeddings.
- Deterministic evidence assembly.

The implementation should proceed only after workbook population persists machine-readable metadata or a sidecar equivalent. Without that, `.xlsx + CanonicalMetricRegistry` can produce a useful demo parser but not a production-safe Query Engine dataset.
