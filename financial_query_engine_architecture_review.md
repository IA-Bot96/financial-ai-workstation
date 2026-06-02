# Financial Query Engine — Architecture Review

**Reviewer role:** Principal Architect
**Artifact reviewed:** `financial_query_engine_architecture.md`
**Review date:** 2026-06-02
**Scope:** Review only. No code modified. No models implemented.

---

## 0. How This Review Was Grounded

This is not a paper review. The proposed design was checked against the **actual upstream
pipeline** that produces the inputs the Query Engine will consume:

- `backend/shared/models/metric_value.py` — `MetricValue` (6 fields only).
- `backend/shared/models/financial_year_consolidation.py` — `ConsolidationCandidate`,
  `ConsolidationGroup`, `FinancialYearConsolidationResult` (rich scope/conflict/confidence).
- `backend/shared/services/financial_year_consolidator.py` — how consolidation resolves duplicates.
- `backend/workbook_population/services/workbook_population_service.py` — what reaches the `.xlsx`.
- `backend/workbook_population/services/workbook_mapper.py` — how values land in cells.
- `backend/ocr_engine/models/insights_extraction.py` — `Insight` (7 fields) + review/diagnostics concepts.

The single most consequential finding falls directly out of this grounding and is described first.

---

## 1. Headline Finding (read this before anything else)

### F1 — The stated source of truth (the `.xlsx`) cannot reconstruct the data model the engine depends on

**Severity:** Critical
**Classification:** Must Fix Before Implementation

**The problem.** Sections 1 and 20 declare *"Workbook is the Query Engine's source of truth"* and
Section 16/17 say *"Parse generated workbook into `CompanyKnowledgeBase`."* But the workbook is a
grid of cell values. Tracing the real pipeline:

- `WorkbookPopulationService.generate_workbook()` consumes `list[MetricValue]`, and `MetricValue`
  carries only `metric, value_year, value, source_report_year, page_number, table_type`.
- `WorkbookMapper` writes **only the value** into a cell at `(sheet, row, col)`. Year is a column
  header; metric is a row label. Nothing else is serialized.
- The proposed `FinancialDataFrame` requires ~18 fields including `statement_scope`,
  `source_class`, `normalized_confidence`, `requires_review`, `unresolved_conflict`,
  `conflict_group_id`, `original_metric`, `display_name`, `units`, `cell_reference`.

None of `statement_scope`, `source_class`, `normalized_confidence`, `requires_review`, or any
conflict metadata exists in the `.xlsx`. Worse, `WorkbookPopulationService._validate_inputs()`
**raises `ValueError` on duplicate `(metric, value_year, table_type)`** — so by the time data is in
the workbook, conflicts have already been collapsed and the competing candidates are gone. A
`ConflictIndex` built by re-parsing the `.xlsx` would be empty by construction.

**Where the data actually lives.** All of it already exists upstream in
`FinancialYearConsolidationResult`: `ConsolidationCandidate` has `source_class`, `statement_scope`,
`normalization_confidence`, `requires_review`, `original_metric`; `ConsolidationGroup` has
`competing_candidates`, `is_conflict_group`, `unresolved_conflict`, `conflict_status`,
`resolution_reason`. This is the real provenance/conflict store — and it never reaches the `.xlsx`.

**Impact.** If built as written, the engine either (a) re-parses the `.xlsx` and silently produces
a `FinancialDataFrame` with ~12 of 18 fields null — collapsing the confidence model, retrieval
ranking, scope guardrails, and the entire conflict subsystem to no-ops — or (b) the team discovers
mid-build that the source of truth is wrong and re-plans Phase 1. Either way, the document's central
data-flow premise is incorrect.

**Recommendation.**
1. **Change the source of truth.** The Query Engine should consume the **structured pipeline
   output** — `FinancialYearConsolidationResult` (metric values + consolidation groups) and
   `InsightsExtractionResult` (insights + review buckets + diagnostics) — *not* a re-parse of the
   `.xlsx`. The `.xlsx` is a human deliverable, not an analytical store.
2. If the `.xlsx` must remain the transport boundary (e.g. it is the only artifact persisted),
   then **emit a structured sidecar** next to it (`<workbook>.kb.json` / parquet) carrying the
   consolidation result and insights result, and parse *that*. The `.xlsx` then carries
   `cell_reference` provenance only.
3. Rewrite Section 1, Section 2 diagram, and Section 20 principle #1 to say the engine consumes the
   **consolidated structured output**, with the `.xlsx` used only for cell-level citation backing.

This finding cascades into F2, F3, F6, and F9 below.

---

## 2. Findings by Category

Each finding: **Severity** · **Impact** · **Recommendation** · **Classification**.

### 2.1 Architectural Correctness

**F2 — Model boundary mismatch: `FinancialDataFrame` invents fields not present on `MetricValue`.**
- Severity: High · Impact: The parser cannot populate `statement_scope`, `source_class`,
  `normalized_confidence`, `requires_review`, `unresolved_conflict`, `conflict_group_id`,
  `original_metric` from anything the workbook contains. These map 1:1 onto `ConsolidationCandidate`
  fields that exist but are not propagated. Retrieval ranking (§7) and confidence (§12) are built
  on these fields, so they fail silently.
- Recommendation: Define `FinancialDataFrame` as a flattened projection of
  `ConsolidationCandidate` (+ selected `ConsolidationGroup` flags), and state explicitly that its
  source is `FinancialYearConsolidationResult`. Do not redefine field semantics; reuse the upstream
  `SourceClass` / `StatementScope` `Literal` types verbatim.
- Classification: **Must Fix Before Implementation**

**F3 — Conflict subsystem has no live data source.**
- Severity: High · Impact: §13 specifies 8 conflict types, competing-candidate surfacing, and a
  `ConflictIndex`. But duplicates are eliminated (with a raised error) before the workbook stage,
  and `ConsolidationGroup` diagnostics are not carried into the engine's stated input. The entire
  conflict feature is designed against data that, on the current path, does not arrive.
- Recommendation: Wire `ConsolidationGroup` (specifically `competing_candidates`,
  `unresolved_conflict`, `conflict_status`, `resolution_reason`) into the engine input as the
  authoritative conflict source. Drop conflict types the upstream cannot detect today
  (e.g. "scale disagreement", "year disagreement") to a clearly-labeled *future* list rather than
  MVP, or specify where that detection will be added.
- Classification: **Must Fix Before Implementation**

**F4 — Pipeline is described as linear but has real fan-in/ordering hazards.**
- Severity: Medium · Impact: The §2 diagram shows Financial/Insight/Calculation as parallel siblings
  feeding one Evidence Builder, but Calculation strictly *depends on* Financial Retrieval output, and
  Conflict/Confidence depend on both. Drawn as peers, this invites an implementation that runs them
  concurrently and races.
- Recommendation: Redraw as: Plan → (Financial Retrieval → Calculation) ∥ (Insight Retrieval) →
  Evidence Builder → Conflict/Confidence → Citation → Narrative. Make the Calculation→Financial
  dependency explicit.
- Classification: **Should Fix**

### 2.2 Service Boundaries

**F5 — Service boundaries are sound and well-separated; one overlap.**
- Severity: Low · Impact: §3 is the strongest part of the document — clean "Must Not Do" columns,
  narrative layer correctly forbidden from inventing facts, calculation correctly deterministic.
  The one overlap: both the Evidence Builder and the Citation Service "attach citations"; ownership
  of citation assembly is ambiguous.
- Recommendation: Citation Service *produces* `Citation` objects; Evidence Builder *references* them
  by id. State that the Evidence Builder never mints citations.
- Classification: **Nice To Have**

**F6 — "Knowledge Base Store" implies a service that is really just a process-local variable.**
- Severity: Medium · Impact: One active in-memory workbook (§16, §20) means the "store" is a single
  mutable global. With a stateless HTTP API (§14) and any concurrency (two browser tabs, two users,
  one async worker pool), `POST /workbooks` replacing the active KB will corrupt an in-flight query
  on another request. The doc never states the concurrency model.
- Recommendation: Either (a) explicitly declare the engine single-session / single-process and
  serialize requests, or (b) key the KB by `workbook_id` in a small registry and have queries pin
  the id they planned against. Given MVP intent, (a) is acceptable *if stated and enforced*.
- Classification: **Must Fix Before Implementation** (the ambiguity, not the choice)

### 2.3 Query Planning Design

**F7 — Deterministic-first planner is the right call; metric/year extraction is underspecified.**
- Severity: Medium · Impact: §6 lists planner responsibilities but not *how* metrics and years are
  extracted from free text. "Revenue growth over 5 years" requires year-range inference;
  "compare debt and cash" requires multi-metric parsing; "last year" requires relative-date
  resolution against `report_years`. Without a defined extraction contract, this becomes ad-hoc
  regex that the team reinvents.
- Recommendation: Specify the extraction inputs (metric registry aliases, `report_years` from the
  KB), the relative-year resolution rule, and the multi-metric tokenization approach. Reuse the
  existing `MetricNormalizer` / registry rather than a new alias map.
- Classification: **Should Fix**

**F8 — Intent taxonomy conflates two axes.**
- Severity: Low · Impact: `query_type` (financial/insight/mixed) and `intent`
  (lookup/trend/growth/...) overlap — "explanation" is both a type and an intent. This will produce
  inconsistent planner branches.
- Recommendation: Keep `query_type` as the data-domain axis and `intent` as the operation axis;
  document that they are orthogonal and enumerate the valid combinations.
- Classification: **Nice To Have**

### 2.4 Retrieval Strategy

**F9 — Financial retrieval ranking depends on fields that won't be populated (see F1/F2).**
- Severity: High · Impact: §7 ranks by "non-conflicted consolidated value", "higher normalization
  confidence", "statement source before note disclosure" — i.e. `unresolved_conflict`,
  `normalized_confidence`, `statement_scope`, `source_class`. All four are exactly the fields the
  `.xlsx` drops. The ranking is correct *in design* but inert against the stated input.
- Recommendation: Gated on F1. Once the structured consolidation result is the input, this ranking
  is directly implementable — the precedence even mirrors the consolidator's own
  `resolution_reason`. Consider *reusing* the consolidator's selection rather than re-deriving it.
- Classification: **Must Fix Before Implementation** (the dependency; the ranking logic itself is good)

**F10 — Fuzzy match "with high threshold" is undefined and risky for financial lookups.**
- Severity: Medium · Impact: A wrong fuzzy metric match returns a confidently-wrong number with a
  citation — the worst failure mode for a financial tool. "High threshold" is not a spec.
- Recommendation: Define the threshold, and require that any fuzzy-matched answer is downgraded to
  at most Medium confidence and carries an explicit "interpreted your metric as X" warning. Prefer
  returning ambiguity over a fuzzy guess for headline metrics.
- Classification: **Should Fix**

**F11 — Insight retrieval keyword/area matching is a reasonable MVP; relevance is unranked.**
- Severity: Low · Impact: §8 lists signals but no scoring function to combine them, so "top
  insights" is undefined. Acceptable for MVP but will produce noisy mixed answers.
- Recommendation: Specify a simple weighted score (area match + keyword overlap + year match +
  confidence) and a max-N cutoff. Defer embeddings to Phase 4 as already planned.
- Classification: **Nice To Have**

### 2.5 Calculation Responsibilities

**F12 — Calculation guardrails are excellent; numeric-readiness is unaddressed.**
- Severity: Medium · Impact: `MetricValue.value` is `float | int | str` — values can be `"N/A"`,
  scaled ("1,500" / "1.5 (in millions)"), or unit-bearing. §9 computes CAGR/deltas but never says
  what happens when an input is a non-numeric string or when two operands have different `units`.
  CAGR on a string crashes; mixing units gives silent garbage.
- Recommendation: Add a numeric-coercion + unit-consistency precondition to the Calculation Service.
  On failure, return a calculation warning (the §15 "calculation input missing" path) rather than
  raising. State the unit-mismatch rule explicitly.
- Classification: **Should Fix**

**F13 — "Cash movement explanations using deltas plus insights" is a calculation that depends on narrative.**
- Severity: Low · Impact: Listed under deterministic calculations, but it inherently blends numeric
  deltas with retrieved insights — that is an Evidence-Builder/Narrative concern, not a deterministic
  calc. Boundary smell.
- Recommendation: Move it out of the Calculation Service's deterministic list; model it as a
  composed evidence pattern (financial delta + insight retrieval) assembled by the Evidence Builder.
- Classification: **Nice To Have**

### 2.6 Evidence / Provenance Handling

**F14 — Cell-reference provenance is promised but not produced by the pipeline.**
- Severity: High · Impact: §11 says "Numeric answers must cite workbook sheet and cell." The
  `WorkbookMapper` *computes* `(sheet, row, col)` at write time, but that mapping is **not persisted**
  anywhere the engine can read — and `MetricValue` has no `cell_reference`. The engine would have to
  re-derive cell locations by re-scanning the `.xlsx` with the same fragile label/year matching the
  mapper uses, which can mismatch.
- Recommendation: Persist the `WorkbookCellMapping` produced during population (into the structured
  sidecar from F1, keyed by metric/year/table_type). Then `cell_reference` is authoritative, not
  re-derived. The §11 fallback ("use sheet and metric row") is good and should remain.
- Classification: **Must Fix Before Implementation**

**F15 — `value_year` vs `source_report_year` separation is correctly preserved — strength.**
- Severity: n/a (positive) · The doc, the models, and the downstream notes (§19) all consistently
  keep these distinct. This is a genuine correctness win and should be guarded with a test.
- Classification: **Strength** (no action)

### 2.7 Conflict Handling

**F16 — Conflict policy is sound where data exists; "ask for clarification" needs a transport.**
- Severity: Medium · Impact: §13 says "answer with a caveat or ask for clarification." The
  `QueryResponse` has no field for a clarification request — only `answer`, `warnings`,
  `follow_up_suggestions`. A clarification need has nowhere to go except prose, which the UI cannot
  act on.
- Recommendation: Add a structured `clarification_needed` / `needs_disambiguation` field (with the
  competing options) to `QueryResponse`, or explicitly fold it into a typed warning. See also F3 for
  the data source.
- Classification: **Should Fix**

### 2.8 Confidence Model

**F17 — Backend-calibrated confidence is the right philosophy; the combination function is missing.**
- Severity: Medium · Impact: §12 lists 7 components and 4 buckets but no formula or weighting
  mapping components → bucket. Two engineers will implement two different scorers. "Calibrated"
  without a defined function is aspirational.
- Recommendation: Specify at least a deterministic rule set (e.g. "any unresolved conflict on a
  cited value ⇒ at most Low"; "missing requested year ⇒ Medium ceiling"; "fuzzy metric match ⇒
  Medium ceiling"). A monotonic rule table is enough for MVP and is testable.
- Classification: **Should Fix**

**F18 — "Cannot answer" is a fourth bucket but interacts oddly with `answer: string` (required).**
- Severity: Low · Impact: When the bucket is "Cannot answer", what is `answer`? The contract makes
  `answer` non-optional, forcing a placeholder string.
- Recommendation: Define the "Cannot answer" response shape explicitly (answer = standardized
  message, evidence lists empty, warnings populated).
- Classification: **Nice To Have**

### 2.9 Scalability Risks

**F19 — Full in-memory KB + linear `iter_rows` scans won't scale, but MVP scope makes this acceptable *if bounded*.**
- Severity: Medium · Impact: `WorkbookMapper._find_metric_row` scans every cell of every sheet per
  lookup (O(cells) per metric). For one workbook in memory this is fine. The risk is the doc's
  silence on workbook size limits and the §15 "Memory pressure" mode that has no defined trigger.
- Recommendation: State an explicit upper bound (sheets, rows, metrics) the MVP supports, build the
  `MetricIndex`/`InsightIndex` once at load (as §4 already implies) so per-query lookups are O(1),
  and define the memory-pressure threshold concretely rather than "clear or reject."
- Classification: **Should Fix**

**F20 — Single global active workbook caps concurrency at effectively one user (see F6).**
- Severity: Medium · Impact: Fine for a single-analyst desktop tool; a blocker the moment this is a
  shared service. The doc markets "Enterprise Readiness" in Phase 5 without acknowledging the MVP's
  single-session assumption is load-bearing and must be unwound first.
- Recommendation: Document the single-session assumption as an explicit MVP constraint and list
  "multi-session KB registry" as the *first* Phase 5 prerequisite, not one bullet among many.
- Classification: **Should Fix**

### 2.10 Overengineering Risks

**F21 — Five indexes specified for an in-memory single-workbook MVP.**
- Severity: Medium · Impact: §4 defines `MetricIndex`, `InsightIndex`, `ProvenanceIndex`,
  `ConflictIndex`, plus `KnowledgeBaseQualitySummary`. For a single workbook held in memory, most
  "indexes" are dict comprehensions over a few hundred rows. Treating each as a first-class
  subsystem is premature structure.
- Recommendation: For MVP, collapse to one `MetricIndex` (dict keyed by canonical metric → rows) and
  one `InsightIndex`; derive provenance and conflict views as queries over the same rows rather than
  separate maintained structures. Promote to dedicated indexes only when a measured lookup is slow.
- Classification: **Should Fix**

**F22 — Six API endpoints + answer-style + max-citations before a single answer is proven.**
- Severity: Low · Impact: Metric Catalog, Insight Catalog, three workbook-lifecycle endpoints, and
  `answer_style` (concise/analyst/table) are surface area that delays the first end-to-end answer.
- Recommendation: MVP = `POST /workbooks`, `POST /query`, `GET /workbooks/current`. Defer catalogs
  and `answer_style` to after the deterministic answer path works.
- Classification: **Nice To Have**

**F23 — Narrative Generation as a full pipeline phase risks reintroducing the hallucination it forbids.**
- Severity: Medium · Impact: The deterministic-evidence philosophy is excellent. But Phase 3 adds an
  LLM narrative layer; if the deterministic fallback (§15 "Narrative model unavailable") is not the
  *default*, the team will lean on the LLM and the citation guarantees erode.
- Recommendation: Make the deterministic evidence-to-text generator the **primary** renderer and the
  LLM an optional polish layer that may only rephrase already-cited evidence. State this as a hard
  rule, not a fallback.
- Classification: **Should Fix**

### 2.11 Missing Components

**F24 — No defined contract for the engine's actual input (the upstream handoff).**
- Severity: High · Impact: The whole document assumes a workbook appears; it never specifies the
  contract with the OCR/consolidation pipeline. Given F1, this is the missing keystone.
- Recommendation: Add a section defining the input artifact: `FinancialYearConsolidationResult` +
  `InsightsExtractionResult` (+ cell mapping), its versioning, and the `workbook_fingerprint`
  derivation. This is the boundary the engine lives or dies on.
- Classification: **Must Fix Before Implementation**

**F25 — No observability / no test strategy / no eval harness for answer quality.**
- Severity: Medium · Impact: A financial Q&A engine with no defined "golden question set" or
  regression eval will silently regress on metric matching and confidence calibration. §17 ships
  features with no acceptance gate.
- Recommendation: Add a golden-Q&A fixture set (question → expected metric/year/value/citation) as a
  Phase 1 deliverable, run in CI. Add structured query logging (plan, retrieved rows, confidence) for
  debuggability — promote it out of Phase 5.
- Classification: **Should Fix**

**F26 — Units / scale normalization is unowned.**
- Severity: Medium · Impact: `units` appears on `FinancialDataFrame` as "when available" but no
  service owns unit reconciliation, and `MetricValue` has no units. Comparisons and growth across
  values reported in different scales (thousands vs millions, restated) will be silently wrong.
- Recommendation: Assign unit handling explicitly (likely upstream in consolidation, surfaced as a
  populated `units` field), and have the Calculation Service refuse cross-unit math (ties to F12).
- Classification: **Should Fix**

**F27 — No answer caching / idempotency, and `workbook_fingerprint` is defined but never used.**
- Severity: Low · Impact: `workbook_fingerprint` exists on the KB for "stale upload detection" but no
  flow references it. Repeated identical queries re-plan and re-retrieve.
- Recommendation: Define where `workbook_fingerprint` is checked (on query, to reject stale
  `workbook_id`), and note query-result caching as an explicit non-goal for MVP if intentional.
- Classification: **Nice To Have**

---

## 3. Classification Summary

### Must Fix Before Implementation
- **F1** — `.xlsx` cannot reconstruct the data model; change source of truth to structured output.
- **F2** — `FinancialDataFrame` fields not present on `MetricValue`; project from `ConsolidationCandidate`.
- **F3** — Conflict subsystem has no live data source; wire in `ConsolidationGroup`.
- **F6** — Concurrency model for the single active KB is undefined.
- **F9** — Retrieval ranking depends on dropped fields (resolved by F1).
- **F14** — Cell-reference provenance is promised but not persisted.
- **F24** — No defined input/handoff contract with the upstream pipeline.

### Should Fix
- **F4** — Pipeline dependency ordering misdrawn as parallel.
- **F7** — Metric/year extraction in the planner underspecified.
- **F10** — Fuzzy match threshold undefined and risky.
- **F12** — Numeric/unit readiness in calculations unaddressed.
- **F16** — Clarification requests have no structured transport.
- **F17** — Confidence combination function missing.
- **F19** — Workbook size bounds / memory-pressure trigger undefined.
- **F20** — Single-session assumption is load-bearing and unstated.
- **F23** — Deterministic renderer must be primary, not fallback.
- **F25** — No eval harness / observability.
- **F26** — Units/scale normalization unowned.

### Nice To Have
- **F5** — Citation ownership overlap (Evidence vs Citation service).
- **F8** — `query_type` vs `intent` axis overlap.
- **F11** — Insight relevance scoring function unspecified.
- **F13** — "Cash movement explanation" mis-placed in deterministic calc.
- **F18** — "Cannot answer" response shape undefined.
- **F21** — Five indexes is premature for an in-memory MVP.
- **F22** — Endpoint/answer-style surface area too large for MVP.
- **F27** — `workbook_fingerprint` defined but unused; no caching policy.

---

## 4. Architecture Score

### **6.5 / 10**

**Rationale.** The *conceptual* architecture is strong: clean service boundaries, the right
deterministic-first instinct, correct insistence on citations and exposed conflicts, and a genuinely
correct `value_year`/`source_report_year` separation that the rest of the codebase already honors.
As a statement of *principles and responsibilities*, it would score ~8.5.

It loses points because the **central data-flow premise is wrong**: the declared source of truth
(the `.xlsx`) structurally cannot supply the metadata that the data model, retrieval ranking,
conflict handling, and confidence scoring all depend on — even though that metadata *already exists*
one layer upstream in `FinancialYearConsolidationResult`. This is not a detail; it invalidates
Phase 1's input assumption and cascades into six other Must-Fix findings. Combined with the missing
upstream-handoff contract (F24) and unpersisted cell provenance (F14), the design is not yet safe to
implement as written — but it is close, because the fix is largely "consume the structured output you
already produce" rather than a redesign.

Resolve the seven Must-Fix items and this is an 8.5+ architecture.

---

## 5. Top 10 Risks

1. **Source-of-truth inversion (F1).** Building Phase 1 against the `.xlsx` yields a KB with most
   analytical fields null; discovered late, it forces a Phase 1 re-plan.
2. **Phantom conflict subsystem (F3).** Significant engineering on `ConflictIndex`/conflict UX that
   never receives data because duplicates are collapsed (and errored on) upstream.
3. **Missing upstream contract (F24).** No agreed handoff artifact means the OCR team and Query
   Engine team integrate on assumptions, not a spec.
4. **Confidently-wrong numbers (F10 + F12).** Fuzzy metric matches and non-numeric/unit-mismatched
   values produce cited but incorrect financial answers — the highest-trust-damage failure.
5. **Unpersisted cell provenance (F14).** Citations re-derived by re-scanning the `.xlsx` mismatch
   the real cell, undermining the "every fact is cited" guarantee.
6. **Concurrency corruption (F6 / F20).** A single global active KB + stateless API corrupts
   in-flight queries when a new workbook is uploaded; latent until the second user appears.
7. **Uncalibrated confidence (F17).** No combination function means inconsistent, untestable
   confidence — users can't trust the High/Medium/Low signal.
8. **LLM hallucination creep (F23).** If the narrative LLM is the default renderer, the
   evidence-only guarantee erodes despite the stated principle.
9. **Silent unit/scale errors (F26).** Cross-year or cross-metric math across mismatched scales
   produces plausible wrong answers with no warning.
10. **No quality gate (F25).** Without a golden-Q&A eval in CI, metric-matching and confidence
    regressions ship undetected.

---

## 6. Top 10 Strengths

1. **`value_year` vs `source_report_year` discipline (F15)** — correct, consistent with the existing
   models, and essential for restated comparatives. The strongest single decision.
2. **Service boundaries with explicit "Must Not Do" (§3)** — unusually clear, prevents the narrative
   layer from inventing facts and keeps calculations deterministic.
3. **Deterministic-first planner (§6)** — correct sequencing; LLM planning deferred, not assumed.
4. **Calculations isolated from narrative (§9, principle in §20)** — the right structural defense
   against hallucinated math.
5. **Conflicts must be exposed, not hidden (§13, §20)** — exactly right for a financial tool; the
   *policy* is sound even where the data plumbing (F3) needs fixing.
6. **Backend-calibrated confidence, not LLM-reported (§12)** — correct philosophy; refuses to trust
   the narrative model's self-assessment.
7. **Review-gated data labeled, not silently used (§8, §13)** — aligns with the upstream review-bucket
   concept and protects trust.
8. **Layered retrieval (exact → alias → registry → fuzzy → ambiguity) (§7)** — sensible degradation
   with ambiguity as a first-class outcome rather than a guess.
9. **Clear MVP / excluded-scope boundary (§16)** — forecasting, multi-company, persistence correctly
   pushed out; shows scope discipline.
10. **Downstream-readiness notes (§19)** — thinking ahead about Forecast/Qualitative engines reusing
    the same dataframes is good platform hygiene.

---

## 7. Revised Implementation Order

The original Phase 1–5 ordering is reasonable but front-loads the wrong input and defers the
contract/eval that de-risk everything. Recommended sequence:

**Phase 0 — Input contract & provenance (NEW, prerequisite).**
- Define and version the engine input: `FinancialYearConsolidationResult` + `InsightsExtractionResult`
  + persisted `WorkbookCellMapping`. (Resolves F1, F2, F3, F9, F14, F24.)
- Decide and document the concurrency/session model. (F6, F20.)
- Stand up the golden-Q&A fixture set and CI harness *before* answers exist. (F25.)

**Phase 1 — Deterministic financial Q&A (revised).**
- Parser builds KB from the structured contract (not the `.xlsx` grid).
- Single `MetricIndex` (collapse the five indexes — F21).
- Financial retrieval + layered matching with defined fuzzy threshold (F10).
- Calculation service with numeric-coercion + unit guards (F12, F26).
- Evidence + citation builder using persisted cell mappings (F14).
- Minimal API: `POST /workbooks`, `POST /query`, `GET /workbooks/current` (F22).

**Phase 2 — Conflict & confidence.**
- Project `ConsolidationGroup` into the conflict surface; competing candidates in responses (F3, F16).
- Confidence as an explicit, testable rule table (F17, F18).

**Phase 3 — Insight & mixed Q&A.**
- Insight index + weighted relevance scoring (F11).
- Mixed evidence assembly, including cash-movement composition in the Evidence Builder (F13).

**Phase 4 — Narrative generation.**
- Deterministic evidence-to-text renderer as the **primary** path; LLM as optional rephrasing only
  over already-cited evidence (F23). Answer-style controls here.

**Phase 5 — Advanced retrieval.**
- Embeddings/semantic search, query history, follow-ups (unchanged from original).

**Phase 6 — Enterprise readiness.**
- Multi-session KB registry **first** (unwinds the single-session assumption — F20), then
  multi-company, persistence, access control, audit, observability dashboards.

**Net change vs original:** insert Phase 0 (contract + concurrency + eval), pull confidence/conflict
*ahead* of insights (they harden the financial path that ships first), and make the deterministic
renderer primary before any LLM narrative.

---

## 8. One-Paragraph Verdict

This is a well-reasoned architecture with the right instincts — deterministic calculation, exposed
conflicts, mandatory citations, backend-owned confidence, and a clean `value_year`/`source_report_year`
model that the existing codebase already respects. Its blocking flaw is that it names the `.xlsx`
workbook as the source of truth when the analytically necessary metadata (scope, source class,
normalization confidence, conflict candidates, cell provenance) lives one layer upstream in
`FinancialYearConsolidationResult` and `InsightsExtractionResult` and never reaches the spreadsheet.
Re-point the engine at that structured output, pin down the upstream handoff contract and concurrency
model, persist cell mappings for citations, and the design moves from "not yet safe to build" to
"strong and implementable." Score: **6.5/10**, rising to **8.5+** once the seven Must-Fix items are
addressed.
