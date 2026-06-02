# Forecast Validation Engine — Architecture Readiness Review

**Review date:** 2026-06-02
**Artifact reviewed:** `forecast_validation_engine_architecture.md`
**Scope:** Architecture readiness and data-contract assumptions only. No code, no refactors proposed.
**Grounding context:**
- OCR Engine v1 freeze audits (`ocr_engine_v1_final_report.json`, `ocr_v1_freeze_readiness_audit.json`, `ocr_v1_freeze_preparation_report.json`)
- Query Engine Core v1 freeze audits (`query_engine_freeze_checklist.json`, `query_engine_production_artifact_audit.json`)
- `scale_consistency_audit.json` (source bundle `lucky_full_ocr_after_regression_fixes_...133227...kb.json`, `report_years=[2025]`)

---

## 0. Verdict

**The architecture is conceptually strong and correctly scoped, but it is NOT yet ready to enter implementation.** Its design treats scale corruption, source-data ambiguity, and unresolved conflicts as *edge-case failure modes and confidence-reducers*. The grounding data shows they are the **dominant case**: in the audited production bundle, **only 1 of 11 core MVP metrics (EPS) is `safe_for_forecast_validation`**; the other 10 are `requires_review`, with **50 critical and 1 high** scale/source anomalies across **every** value-year 2020–2025.

The engine's central premise — "build historical series from selected consolidated values, then validate forecasts against them" — assumes a baseline that does not currently exist. Until the **input data contract** and a **pre-validation data-integrity gate** are defined, building the forecast-plausibility rules on top would produce confident, cited, and wrong validation conclusions.

---

## 1. Architecture Quality Review

### Strengths (keep these)
1. **Deterministic-first, non-authoritative LLM boundary** (§3, §4, §5.LLM). Correct for a financial trust tool; the explicit "LLM may not change calculations / suppress critical issues / select alternate values" rules are exactly right.
2. **Severity decoupled from confidence** (§7, §9). "Confidence cannot override severity" is the single most important design decision and it is correct.
3. **Mandatory evidence with provenance + conflict references** (§8). Aligns with the persisted `WorkbookCellMapping` + consolidation diagnostics that the Query Engine production artifact audit confirmed are now real (citation rate 1.0).
4. **Rejects workbook-only input; requires structured sidecar** (§10 `ValidationInputAdapter`, §12, §15.7). Correct — the workbook cannot reconstruct conflict/scope/confidence metadata.
5. **`value_year` vs `source_report_year` discipline** (§2, §15.4–5). Consistent with the upstream models and necessary for restated comparatives.
6. **It already names scale inconsistency, conflict, and review-gating as first-class checks** (§6 Historical Series Readiness, §7 example). The intent to catch the revenue >100× case is present.

### Weaknesses that block readiness
1. **It models the disease as the exception.** The architecture's failure-mode table (§12) and confidence components (§9) "reduce confidence" or "warn/fail depending on rule" for scale/conflict/review. But the data says these conditions apply to ~91% of core metrics. As written, **every validation run on current data fails at category and overall level**, which collapses the engine's discriminating power — it cannot distinguish "input data not validatable" from "forecast implausible." This is the same failure the OCR validation layer already exhibits (`validation_is_valid=false`, 11 critical, treated as an exception report, not a gate). The architecture does not define this separation.
2. **Data-flow ordering hazard (§5).** The conceptual flow runs `Deterministic Calculations` (YoY, CAGR, margins) **before** `Validation Rules` (which include scale/conflict detection). On the current revenue series — `41,871 → 62,940,805,000 → 95,000,000 → 95,832 → 26,282,162 → 25,417,143` — CAGR and margin numbers would be computed and available for evidence/citation *before* the scale rule flags the series as corrupt. The architecture does not specify that a data-integrity gate must short-circuit numeric rules for failed series.
3. **The trust signals it relies on are not trustworthy in the current data** (see §3 below): `unresolved_conflict=false` does not mean clean; `normalization_confidence=1.0` does not mean correct; `statement_scope` is almost always `unknown`.
4. **Hard dependency on an unfrozen, unproven dependency.** §4 and §15.6 mandate reusing Query Engine retrieval/calculation contracts. Per the Query Engine freeze checklist, Core v1 is **`DO_NOT_FREEZE`**, its golden-suite accuracy criteria are unproven on the real bundle, and broad terms (`debt`, `cash`, `net income`) resolve ambiguously. The architecture assumes a stable contract that does not yet exist.
5. **Single-source-report blind spot.** The architecture's recency/source-of-truth logic and "trend breaks coinciding with restatements" (§6 Trend Breaks) require multiple `source_report_year` filings. The production bundle has `by_source_report_year = 1` (`report_years=[2025]`); all six value-years are comparatives from one report. Restatement/recency logic cannot be exercised and must not be assumed available at MVP.

---

## 2. Hidden Dependencies on Historical-Series Integrity

These are dependencies the architecture relies on implicitly but never states as preconditions. Each is currently violated by the grounding data.

| # | Hidden dependency | Reality in `scale_consistency_audit.json` |
|---|---|---|
| H1 | A metric's selected values share **one consistent scale** across years. | Revenue spans 5+ orders of magnitude within one series; 16 anomalies classified "consolidation-scale corruption." |
| H2 | `unresolved_conflict=false` ⇒ the value is safe to use as a baseline. | The entire revenue series is `unresolved_conflict=false` / `conflict_status=resolved_conflict` **and** scale-corrupted. "Resolved" ≠ "correct." |
| H3 | `normalization_confidence` is a positive selector of the right value. | Revenue 2024/2025 were selected from a note fragment `"and liabilities is as follows: - Revenue"` (`note_disclosure`, conf `1.0`) **over** the primary income-statement `Turnover` line, via `resolution_reason="higher_normalization_confidence"`. |
| H4 | `statement_scope` is populated enough to enforce "primary statement over notes" and "mixed scope" rules. | `statement_scope` is `unknown` for essentially all values (freeze-prep candidate counts: 1466 `unknown` vs 22 `consolidated`). Scope-based gating is inert. |
| H5 | `source_class` precedence (primary > note) is already applied upstream. | The bad revenue selection took a `note_disclosure` over `primary_statement`. Precedence is **not** reliably enforced at consolidation; FVE would inherit the wrong selection. |
| H6 | Candidate consolidation collapsed to a defensible single value. | `candidate_spread_ratio` reaches **66,330,223×** within a single year's group while still marked resolved. The selected value is one point in a chaotic cloud. |
| H7 | Core series exist as exact canonical metrics. | `total_equity`, `total_debt`, `long_term_debt` are **missing as exact metrics** (3 of 11 MVP metrics absent). |
| H8 | Cross-metric rules can anchor on a clean metric. | EPS is the only "safe" series, but EPS-vs-PAT and EPS-vs-share-count checks (§6 EPS Consistency) require PAT/share data that is `requires_review`. Even the clean metric's cross-checks are blocked. |
| H9 | History depth > 1 source report for recency/restatement logic. | `by_source_report_year = 1`. |

---

## 3. Assumptions That Become Invalid Under Each Condition

### 3.1 When scale inconsistencies exist
- **Invalid:** "Deterministic CAGR / YoY / margin / ratio calculations over `value_year` history produce meaningful numbers" (§5, §6). On a scale-corrupted series these calculations are arithmetically valid but financially meaningless, and §5 computes them *before* the scale rule fires.
- **Invalid:** "Scale inconsistency is a per-rule warning that 'reduces confidence or creates critical failure'" (§9, §12). Scale corruption is not a localized issue — it **poisons every numeric rule that touches the series**. It must be a gate, not a confidence input.
- **Invalid:** "`normalization_confidence` raises confidence" (§9). H3 shows a `1.0`-confidence note-fragment was the wrong value; high normalization confidence co-exists with scale corruption.

### 3.2 When source-data ambiguity exists
- **Invalid:** "Selected consolidated value is the authoritative baseline" (§2, §6). 35 of 51 anomalies are classified "source-data ambiguity"; the selected value frequently sits among candidates differing by >100×.
- **Invalid:** "Prefer primary statement over notes" is already true in the data (§6 Debt, OCR minimum-controls). H5 shows the opposite occurred. FVE cannot assume source precedence; it must verify it.
- **Invalid:** "Missing `total_debt` is a fallback edge case" (§6 Debt). It is the actual state — `total_debt` and `long_term_debt` are absent. The Debt Consistency category is largely non-functional on current data and must degrade explicitly, not silently substitute (the architecture's "do not infer broad substitutes silently" rule in §12 is correct and must be enforced here).

### 3.3 When unresolved conflicts exist
- **Invalid:** "`unresolved_conflict` is the flag that blocks high-confidence validation" (§9, §12, §15.3). H2 shows scale-corrupted series flagged as **resolved**. Gating on `unresolved_conflict` alone passes corrupt data. The gate must combine `unresolved_conflict` **and** scale-consistency **and** `candidate_spread_ratio`.
- **Invalid:** "Critical issues cleanly identify forecast problems" (§7). With gross_profit, operating_profit, and profit_after_tax all `unresolved_conflict=true` across all years, the severity model fails the overall validation for **data** reasons on nearly every run, masking genuine **forecast** signals. The architecture lacks a distinct outcome for "baseline not validatable."

---

## 4. Recommended Gating Requirements Before Implementation Begins

These are architecture/data-contract gates, not code tasks.

1. **G1 — Define the input data contract explicitly.** Specify the minimum quality a series must meet to enter validation: scale-consistency status, `candidate_spread_ratio` ceiling, conflict status (resolved *and* unresolved), review-gate status, and presence of the exact canonical metric. Reference `scale_consistency_audit.json` readiness fields (`safe_for_forecast_validation` / `requires_review`) as the contract vocabulary.
2. **G2 — Specify a pre-validation data-integrity gate as a distinct, ordered first stage** that runs before any deterministic calculation and short-circuits numeric rules for series that fail it. Define a third top-level outcome — **"baseline not validatable"** — separate from "forecast fails" and "forecast passes."
3. **G3 — Redefine the trust gate to not rely on a single flag.** State in the architecture that `unresolved_conflict=false`, `normalization_confidence` high, and `statement_scope=unknown` are **insufficient** on their own; the gate must use scale-consistency and candidate-spread signals. (Resolves H2/H3/H4/H6.)
4. **G4 — Pin the upstream contract version.** Treat OCR v1 freeze-prepared output and the Query Engine bundle/calculation contracts as a versioned dependency. Do not begin implementation against Query Engine contracts while Core v1 is `DO_NOT_FREEZE`; require at least a frozen retrieval/calculation interface (not necessarily full accuracy).
5. **G5 — Declare MVP scope against *available, clean* metrics, not aspirational ones.** The §13 MVP metric list (12 metrics) does not match reality (1 currently safe; 3 missing entirely). Either narrow MVP to metrics that can pass G1 on the reference bundle, or explicitly mark the rest as "validatable once OCR review burden drops," with the engine returning "unavailable/requires-review," never a fabricated baseline.
6. **G6 — Specify multi-`source_report_year` as a precondition for recency/restatement rules.** Mark Trend-Break-vs-restatement and source-recency logic as inert until ≥2 filings exist; do not let them silently no-op.
7. **G7 — Specify the "clean anchor, dirty comparison" behavior for cross-metric rules** (EPS-vs-PAT, OCF-vs-profit, margin pairs). Define what the engine returns when the anchor metric is clean but the comparison metric is `requires_review` (H8).
8. **G8 — Require a re-run of `scale_consistency_audit` on a second issuer (Millat) before locking the contract.** The current contract is grounded on one Lucky bundle; the OCR freeze audit shows Millat has different (66.7%) review characteristics and no post-sprint full run.

---

## 5. Findings Classification

### Must Resolve Before Implementation
- **M1 (§1.1, §3.3):** Define the "baseline not validatable" outcome separating data-integrity failure from forecast-plausibility failure. Without it, the engine is a constant red light on current data. → G2
- **M2 (§1.2):** Specify the data-integrity gate ordering — it must run before deterministic calculations and short-circuit them for failed series. → G2
- **M3 (H2/H3/H4/H6):** Redefine the trust gate so it does not rely solely on `unresolved_conflict`, `normalization_confidence`, or `statement_scope`. "Resolved" and "high confidence" are demonstrably not clean. → G3
- **M4 (§1.4, G4):** Establish the upstream data contract and a versioned, frozen Query Engine retrieval/calculation interface dependency before building on it.
- **M5 (G1, G5):** Define the input data contract and align the MVP metric list with what can actually pass it (today: EPS only; `total_debt`/`long_term_debt`/`total_equity` absent).

### Can Be Handled During Implementation
- **C1 (G7):** Cross-metric "clean anchor / dirty comparison" handling for EPS-vs-PAT, OCF-vs-profit, margin pairs.
- **C2 (§6 Debt, §12):** Explicit graceful degradation when `total_debt`/`long_term_debt` are missing (the "no silent substitute" rule already exists; wire it to a defined unavailable-category outcome).
- **C3 (§8, §9):** Citation/confidence reduction wiring for missing provenance — mechanics are sound, tune during build.
- **C4 (§7):** Threshold calibration for YoY/CAGR/margin bounds — inherently iterative; safe to tune in implementation once the gate (M1–M3) exists.
- **C5 (G8):** Second-issuer (Millat) contract validation can run alongside early implementation, provided M5 used Lucky as the initial reference.

### Post-MVP
- **P1 (§6 Trend Breaks, G6):** Restatement-aware trend-break detection and source-recency logic (needs ≥2 `source_report_year` filings; not available now).
- **P2 (§14 Phase 3):** Insight-aware plausibility (`InsightDataset` as supporting evidence) — depends on Qualitative output, correctly already phased late.
- **P3 (§14 Phase 4):** Sector-aware rule packs — correctly deferred.
- **P4 (§14 Phase 5):** LLM explanation layer — correctly deferred and correctly constrained.

---

## 6. One-Paragraph Summary

The Forecast Validation Engine architecture is well-reasoned: deterministic-first, severity decoupled from confidence, evidence-and-provenance mandatory, workbook-only input rejected, and Query Engine contracts reused rather than duplicated. Its blocking gap is a grounding mismatch — it assumes consolidated values are usable baselines with occasional conflicts, while the production bundle shows pervasive scale corruption and source ambiguity across 10 of 11 core metrics, with the very flags the design trusts (`unresolved_conflict`, `normalization_confidence`, `statement_scope`) failing to identify the corruption. Before implementation begins, the architecture must add a data-integrity gate that runs first and short-circuits calculations, define a distinct "baseline not validatable" outcome, redefine the trust gate to use scale/spread signals rather than a single flag, pin a frozen upstream contract, and align the MVP metric list with what can actually pass that contract today. With those gates resolved, the rule-level design is sound and ready to build.
