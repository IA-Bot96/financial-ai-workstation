# Freeze Readiness Review — OCR Engine v1 & Query Engine Core v1

**Review date:** 2026-06-02
**Scope:** Release readiness only. No refactor, architecture, or cleanup recommendations are included by design.
**Reviewer inputs (artifacts actually on disk):**

- `output/ocr_engine_v1_final_report.json` (07:04)
- `output/ocr_v1_freeze_preparation_report.json` (07:44)
- `output/ocr_v1_freeze_readiness_audit.json` (12:21)
- `output/query_engine_freeze_checklist.json` (12:18)
- `output/query_engine_production_artifact_audit.json` (13:41)
- `financial_query_engine_architecture_review.md`

> Note: the named deliverables "release notes" and "known limitations" do not exist as standalone files. Their content lives inside the JSON freeze/final reports above. This review treats those as the authoritative source and flags (R1) that they are not yet captured as release-facing documents.

---

## 0. Headline

| Engine | Documented verdict | Real release-readiness verdict after cross-checking artifacts |
|---|---|---|
| OCR Engine v1 | "READY WITH KNOWN LIMITATIONS after final verification run" | **Pilot-ready with a review gate. Not autonomous.** A fresh full Lucky run *was* produced at 13:32, partially closing the open verification blocker — but only for Lucky, and only on plumbing, not financial cleanliness. |
| Query Engine Core v1 | "NOT_READY_FOR_CORE_V1_FREEZE / DO_NOT_FREEZE" | **The stated primary blocker is already stale.** Citation coverage was resolved 83 minutes after the checklist was written. The *real* remaining blocker is that the golden 60-question MVP audit was never rerun on the fixed bundle, so every accuracy criterion is still failing on stale evidence. |

The single most important release-readiness fact in this whole set: **the two freeze documents disagree because they were written before and after the same fix.** Anyone reading only the freeze checklist will make the wrong go/no-go call.

---

## 1. Hidden Production Risks

These are risks that are **not** visible from the top-line verdicts and would bite in production.

### R1 — The freeze checklist's "primary blocker" is already resolved; nobody updated the verdict
- `query_engine_freeze_checklist.json` (12:18) names the primary blocker as: *"Real-run citation/provenance proof is missing because latest full OCR artifacts predate QueryEngineInputBundle sidecar generation"* and records `citation_coverage = 0.0 (0/60, FAIL_BLOCKING)`.
- `query_engine_production_artifact_audit.json` (13:41) shows a **fresh Lucky run** (`...133227...kb.json`) with `workbook_mappings_count = 1867`, `citation_ready_mappings_count = 1867`, `citation_coverage_rate = 1.0`, `evidence_metric_citation_rate = 1.0`, fingerprint match, bundle `contract_is_valid = true`.
- **Hidden risk:** the official freeze artifact (`DO_NOT_FREEZE`) is **stale by ~83 minutes**. A release decision made on it is wrong in *both* directions — it overstates the citation blocker (now fixed) and understates the real blocker (accuracy never re-measured, see R2). **The freeze checklist must be regenerated against the 13:32 bundle before any go/no-go.**

### R2 — Every Query Engine accuracy number is from a superseded bundle and is below threshold
- The production artifact audit only proves **plumbing**: sidecar exists, mappings persist, fingerprints match, citations attach. It does **not** rerun the 60-question golden MVP audit.
- So the only accuracy numbers we have are still the pre-fix MVP scorecard, all **below freeze thresholds**: planner `0.9333`, retrieval `0.9333`, response `0.85`, conflict propagation `0.8333`, provenance `0.875`, metric resolution `0.8667`. Threshold is `0.95` (conflict `1.0`).
- **Hidden risk:** the fix that resolved citations (rebuilding the KB from a fresh sidecar) changes the very data those accuracy tests run against. The numbers could move up *or* down. Freezing now means shipping with **unknown** planner/retrieval/response accuracy. `QE-FREEZE-MF-003` (rerun the full MVP audit) is the true gating item, not citations.

### R3 — Core financial metrics carry internally inconsistent scales within a single series
This is the most dangerous silent-correctness risk and it is buried in `ocr_v1_freeze_preparation_report.json`.

- `revenue` auto-resolution set **2021 → 62,940,805,000** and **2022 → 95,000,000** (`auto_revenue_full_statement_scale_reconciliation`). Those two years differ by ~660×. A revenue series cannot legitimately drop from 62.9bn to 95m year-over-year — one of them is on the wrong scale.
- `profit_after_tax` remaining-unresolved selected values: 2020 `-68,120`, 2021 `14,070,189,000`, 2022 `11,730`, 2023 `-10,280`, 2024 `72,336,747`, 2025 `84,498,377`. At least three different magnitude scales appear inside one metric's history.
- **Hidden risk:** these values already passed consolidation and were *written to the workbook*. Any consumer that computes YoY growth, CAGR, or a forecast over these series will produce confident, cited, and completely wrong numbers. The citation guarantee makes the wrong number *look* trustworthy. This is exactly the failure mode the architecture review called out as highest trust-damage (review F4/F10/F26). It must be in known limitations and must be gated downstream.

### R4 — OCR output is non-deterministic run-to-run, and the freeze "improvements" are mostly replay estimates
- Between two Lucky full runs, classified tables moved `189 → 177`, accepted insights `198 → 175`, generated insights `241 → 230`, MetricValues `3000 → 2988`. The report attributes this to OpenAI classification/insight variability.
- The headline `+218 recovered mappings` from the final normalization sprint is explicitly **replay-only** (`final_sprint_full_ocr_run_executed = false`). The freeze readiness audit's own `OCR-FREEZE-MF-001` requires a fresh full run to materialize it.
- **Hidden risk:** the freeze is being justified partly by numbers that have never appeared in a real pipeline run, and the real pipeline is not reproducible run-to-run. The 13:32 Lucky run partially addresses this **for Lucky only** (note its consolidated count is `1867`, not the `1836`/`+218` projected — so the replayed gains did not all materialize). **Millat has had no post-sprint full run at all.**

### R5 — Validation is failing and will mislead if treated as a pass/fail gate
- Latest Lucky validation: `is_valid = false`, `score = 0.0`, `103 issues (11 critical / 40 major / 52 minor)`.
- The report's own position is that this is an *exception report*, not a gate, because some issues are extraction noise rather than true financial errors.
- **Hidden risk:** if any downstream automation or dashboard reads `validation_is_valid` as a boolean health signal, it will permanently show red and either be ignored (alarm fatigue) or block everything. The semantics ("advisory exception report, not a gate") must ship *with* the field or it will be misread.

### R6 — The frozen Query Engine bundle covers a single source report year
- The 13:32 Lucky bundle reports `report_years = [2025]`, `by_source_report_year = 1` (7 value-years from one annual report's comparatives).
- **Hidden risk:** multi-report ingestion (separate 2023/2024/2025 filings) is not represented in the artifact being frozen. Any consumer expecting a multi-filing historical series (forecasting especially) is depending on behavior that the freeze artifact does not exercise.

---

## 2. Limitations That Must Be Documented Before Freeze

These are real and acknowledged in the artifacts but are **not yet written down anywhere release-facing**. Freeze should not proceed until they are captured in a known-limitations document that ships with the build.

**OCR Engine v1**
1. Financial data is **analyst-review grade, not autonomous**: 1,194 / 1,836 consolidated Lucky values (65.03%) carry `requires_review`; Millat is 771 / 817 (66.7%).
2. **187 unresolved equal-precedence conflict groups** remain (Lucky), 26 of them on critical core metrics (gross profit, operating profit, profit after tax, revenue/gross sales, PP&E/capex, reserves). Consumers must surface selected-vs-competing provenance.
3. **Scale inconsistency within core metric series** (R3) — explicitly list which metrics/years are affected.
4. **108 rejected tables, 93 missing-year tables, 66 unclassified, 47 unmatched** (Lucky). Complex/image tables are lost; no Azure/PaddleOCR backend integrated.
5. **OpenAI variability** changes classification and insight counts between identical runs (R4).
6. Workbook is **dynamically generated**, not formula-preserving template population.
7. **Validation is failing by design semantics** — advisory exception report, not a pass/fail gate (R5).
8. **Millat has no post-final-sprint full run**; generalization score is 64.0 ("generalizes with caveats").
9. Runtime ≈ **130 minutes** per full Lucky run — acceptable for review, costly for batch.

**Query Engine Core v1**
10. All golden-suite accuracy criteria were last measured **below threshold** and on a **superseded bundle** (R2). Until rerun, they are unknown, not passing.
11. Broad terms **"net income", "cash", "debt"** resolve ambiguously; e.g. "debt" resolves to `current_portion_long_term_debt`, and `total_debt` is absent from the Lucky KB. Document the ambiguity/clarification behavior users will see.
12. Citation/conflict/provenance propagation is **fixture-proven**; real-bundle proof exists only for plumbing (counts/fingerprints), not for the 60-question answer audit.
13. Frozen bundle covers a **single source report year** (R6).
14. No API/session layer, no LLM narrative, no semantic retrieval — all explicitly post-freeze; fine, but state it so "v1" is not over-read.

---

## 3. Cross-Engine Dependency Risk

Neither the **Forecast Validation Engine** nor the **Qualitative Analysis Engine** exists in the codebase yet — both are downstream *consumers* of OCR/Query output. The risk is therefore in the **contract** the frozen v1 outputs impose on them.

### 3.1 Forecast Validation Engine — **HIGH RISK / gate before any use**
OCR readiness verdict: `limited_ready_for_reviewed_metrics_only` (confidence `low_medium`); explicit `go_no_go: forecast_validation_on_all_values = no_go`.

- **Contaminated historical series (critical).** Forecasting consumes time-series of core metrics. Those exact series contain the scale inconsistencies in R3 (`revenue` 2021 vs 2022; `profit_after_tax` across years) and 26 unresolved critical conflicts. Feeding them to a forecast/variance check produces silently wrong trends. **The engine must consume only reviewed, non-conflicted, scale-consistent values — never the full consolidated set.**
- **Validation is red (R5).** `validation_is_valid = false` with 11 critical issues. The freeze conditions require forecast validation to **block or require explicit waiver** on unresolved critical validation issues. This must be enforced in the consumer, not assumed.
- **Single-report depth (R6).** The frozen bundle is one filing's comparatives; multi-year multi-filing series are unproven. Forecasting on shallow history is fragile.
- **Required controls before this engine consumes v1 (from the artifacts):** use only reviewed/high-confidence values; require critical validation issues resolved or waived; prefer primary-statement source over note disclosures for core metrics.

### 3.2 Qualitative Analysis Engine — **LOW–MEDIUM RISK / ready for v1 with monitoring**
OCR readiness verdict: `v1_ready` (confidence `medium_high`); `go_no_go: qualitative_insights_export = go_for_v1`.

- **Run-to-run insight drift (R4).** Accepted insights moved 198→175 between runs and 43 insights sit at `0.0` confidence. The qualitative engine must **rely on confidence-bucket routing and the Insights Review sheet**, not on the accepted-insight set being stable across runs.
- **Coverage asymmetry.** Millat produced far fewer insights (36 accepted vs Lucky 175) with lower section coverage. The engine should not assume Lucky-level density per issuer.
- **Required controls (from the artifacts):** keep confidence-bucket routing, continue filtering generic governance statements, monitor OpenAI variability by section/page.
- This is the **safest** cross-engine consumer to enable at freeze, provided it treats insights as confidence-tagged and review-routable.

### 3.3 Shared dependency risk affecting both
- Both depend on **provenance/flags being surfaced, not silently consumed**: `requires_review`, `unresolved_conflict`, `statement_scope`, `source_class`, page/table provenance. The fresh Query Engine bundle *does* now persist and surface these (production artifact audit shows `unresolved conflicts affect this result` warnings firing) — good — but the contract is only as safe as each future consumer's willingness to respect the flags. This should be a **hard interface requirement**, not a convention.

---

## 4. Release-Readiness Recommendation

**OCR Engine v1 — FREEZE AS CONTROLLED ANALYST-REVIEW v1, conditioned on:**
1. A fresh full **Millat** run after the final normalization sprint (Lucky was done at 13:32; Millat was not).
2. Shipping the **known-limitations document** in §2 alongside the build.
3. Publishing the **review/conflict/validation gating policy** as an enforced downstream contract (`OCR-FREEZE-MF-002`).
- Do **not** label as autonomous. `forecast_validation_on_all_values` stays no-go.

**Query Engine Core v1 — DO NOT FREEZE YET, but for a different reason than the checklist states:**
1. **Regenerate the freeze checklist** against the 13:32 bundle — its citation blocker is stale (R1).
2. **Rerun the 60-question golden MVP audit** on the fresh Lucky `.kb.json` after CAGR support (`QE-FREEZE-MF-003`). This is the real gate; all accuracy criteria are currently unknown, not passing (R2).
3. Resolve or explicitly classify the **broad-debt / total_debt** gap (`QE-FREEZE-MF-004`).
4. Freeze only once conflict coverage = 100% and provenance ≥ 95% on the **real** suite, not fixtures.

**Net:** the engineering is close. The blocking gap is **measurement freshness**, not missing capability — every "fail" in the Query Engine checklist is now either resolved (citations) or unverified-since-the-fix (accuracy). Close those two and the freeze decision becomes defensible.
