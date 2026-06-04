# OCR V2 — Pre-Cutover Validation Review

**Status:** Validation review only. No code authored, no implementation, no redesign. Findings drawn from **executing the shipped P0–P5 modules and the project test suite** against the authoritative oracle (read-only invocation; no behavior changed).
**Date:** 2026-06-04
**Phases complete:** P0 Foundations · P1 Capture · P2 Registry · P3 Statement Governance · P3 Scale Governance · P4 Entity Governance · **P5 Canonical Selection**.
**Authoritative oracle:** `backend/ocr/ocr_v2_regression_cases.json` (15 verified cases, `entity_ref lucky_cement`, `declared_basis unconsolidated`).
**Executed evidence:** project suite **59 passed**; per-case end-to-end selection harness over all 15 cases (results in §3).

---

## 1. Verified CV1 Failure Classes (Task 1)

CV1 produced 48 evaluable errors (84.6% S1, NOT_CERTIFIED). The verified taxonomy:

| CV1 failure class | CV1 count | Nature |
|---|---|---|
| **Wrong statement selection** | 27 | consolidated-for-unconsolidated (8), investee-for-issuer (6), analysis-%-table-for-value (13) |
| **Scale corruption** | 14 | ×1000 thousands→full; mixed-scale (OCF millions); note-number read as value |
| **Missing extraction** | 4 | EPS 2020–2023 never captured |
| **Other** | 3 | structural |

**The regression oracle's 15 cases are a curated, candidate-pair-resolved representative subset** covering the *selection-and-scale* classes: `statement_basis` (5), `note_contamination` (3), `investee_contamination` (2), `scale_governance` (2), `analysis_table_contamination` (1), `summary_table_contamination` (1), `source_selection` (1). **Note: `missing_extraction` is deliberately not represented** — it is a capture-recall problem, not a selection problem, and is addressed in §5/§10.

---

## 2. Failure Class → Responsible OCR V2 Layer (Task 2)

| Failure class | Responsible layer | Prevention mechanism |
|---|---|---|
| Consolidated-for-unconsolidated (`statement_basis`) | **Statement Governance (P3)** | wrong basis → `INELIGIBLE` |
| Analysis-%-table-for-value | **Statement Governance (P3)** | analysis-table → `INELIGIBLE` |
| Note / summary contamination | **Statement Governance (P3)** | note/summary → `REVIEW_REQUIRED` (not selectable while a clean primary exists) |
| Investee-for-issuer | **Entity Governance (P4)** | non-issuer scope → `INELIGIBLE` (MSIL-bound) |
| Scale corruption | **Scale Governance (P3)** | magnitude-inferred → `SCALE_REVIEW_REQUIRED` |
| (Source selection / note-number) | **Statement + Scale (P3)** | `REVIEW_REQUIRED` + `SCALE_REVIEW_REQUIRED` |
| Single canonical pick | **Canonical Selection (P5)** | selects only a fully-clean candidate; **no ranking/scoring/LLM** |
| Missing extraction | **Candidate Capture (P1)** — *not selection* | recall (validated separately) |

---

## 3. Prevention Mechanism — Exists and Exercised (Task 3)

**Executed end-to-end** (capture → registry → statement → scale → entity → P5 selection) over all 15 cases:

```
total = 15
selected_correct        = 15      selected_incorrect = 0
ambiguous               = 0       no_selection       = 0
integrity_violations    = 0
ranking / scoring / LLM used anywhere = False
distinct selection reason = {"single_candidate_after_filtering"}
distinct selection status = {"selected"}
```

**Every case selected the verified-correct value; none selected the verified-incorrect value.** The uniform reason `single_candidate_after_filtering` is the decisive finding: **governance eliminates the wrong candidate before selection runs, so Selection sees exactly one eligible candidate and takes it — it does not rank or prefer.** This is the by-construction guarantee operating exactly as the Selection Architecture Review specified: the wrong value is *impossible to select* because it is filtered, not *less likely* because it scored lower. Confirmed: `ranking_logic_used`, `candidate_scoring_used`, `llm_logic_used` are **False** for all cases, and **zero integrity violations**.

Supporting audits (all passing, executed): P3 statement governance, P3 scale governance, P4 entity governance, P5 canonical selection, and the prior oracle capture-coverage audit (100% representability, no value/provenance mutation).

---

## 4. Are the 15 Oracle Cases Sufficient Evidence? (Task 4) — *partially; sufficient for what they cover*

**Sufficient for:** proving that the eligibility-filter prevention mechanism **works end-to-end** for every represented failure class — consolidated, analysis-table, note, summary, investee, scale, and source-selection. Each class is exercised by ≥1 verified case, the correct value is selected, the wrong value is filtered, and the behavior is deterministic with no ranking. For the **selection-and-scale objective** (the 41 of 48 CV1 errors, ~85%), this is genuine, executed evidence of correction.

**Not sufficient for (structural limits of the 15):**
- Every oracle case is a **2-candidate** pair (one clean correct, one flagged wrong), so each resolves to `single_candidate_after_filtering`. The **multi-eligible-candidate precedence path** (primary outranking a *clean* note/summary when both are eligible) and the **AMBIGUOUS** and **NO_SELECTION** decision paths are **not exercised**.
- The oracle is **Lucky-only**; cross-issuer (Millat) generalization is unproven.
- The oracle covers **15 curated cases**, not the **66-cell CV1 census** — full-census S1 rate against `thresholds_version 1.0.0` is not yet measured.

---

## 5. Remaining Unproven Areas (Task 5)

1. **Capture recall from the raw PDF.** The audits validate representability/governance of oracle-defined candidates; they do **not** re-prove that the OCR/bbox extractor surfaces every candidate from pixels. `missing_extraction` (e.g. EPS) is entirely a recall problem and is **not** covered.
2. **Multi-candidate selection behavior.** Precedence among multiple clean candidates, ties (`AMBIGUOUS`), and empty eligible sets (`NO_SELECTION`) are unexercised by the 15.
3. **Full CV1 census re-run.** 66 cells, S1 rate + Wilson CI vs thresholds 1.0.0 — not yet run.
4. **Cross-issuer (Millat).** Oracle is Lucky-only.
5. **Output phases not yet built.** Workbook generation and OCR→MSIL export do not yet exist; output-contract equivalence to V1 is therefore unverified.

---

## 6. Rollback Readiness (Task 6) — READY

- **V1 remains frozen and serving** (Option B); no cutover has occurred, so the standing rollback is simply *not cutting over*.
- The **candidate registry is append-only** — no selection run can corrupt inputs; re-running is always clean.
- **Selection is deterministic** (identical results across repeated runs, confirmed) and governed by **versioned config**; a regressing config change reverts to the last passing version.
- The oracle is **version-pinned, append-only, externally verified** — it cannot be silently weakened.

Rollback posture is sound; nothing built so far is irreversible.

---

## 7. Readiness for the Output Phases (Task 7)

| Phase | Ready? | Basis |
|---|---|---|
| **Workbook generation** | ✅ Ready to build | Selection emits one clean canonical value per case deterministically; workbook consumes Selection output (canonical-only) and is downstream-safe |
| **Export integration (OCR→MSIL)** | ✅ Ready to build | Canonical value + provenance shape preserved; equivalence harness required *within* this phase |
| **V1 comparison** | ✅ Ready to run | V1 frozen and serving; V2 produces parallel canonical values; cell-by-cell diff is the phase's job |
| **CV1 re-run** | ✅ Ready to run | Selection proven on the oracle; the full 66-cell census re-run is the phase that measures the migration objective |

All four are **ready to enter**. Critically, these phases *are* the remaining validation — V1 comparison and the CV1 re-run are precisely where recall, full-census S1, and multi-candidate behavior get proven. Entering them now is correct; **cutover remains gated by their exit criteria** (§9).

---

## 8. Determination (Task 8)

# READY_FOR_OUTPUT_PHASES

The P5 selection core is proven on the oracle end-to-end (15/15 correct, 0 wrong, 0 ambiguous, 0 integrity violations, deterministic, no ranking/scoring/LLM), every governance layer's prevention mechanism exists and is exercised on the correct axis, rollback is intact, and nothing blocks building workbook/export or running the V1 comparison and CV1 re-run. This is a clearance to **enter** the output phases — **not** a declaration that the migration objective is fully validated, which is the *exit* criterion of those phases (§9). The honest qualifier (capture-recall, multi-candidate paths, full census, cross-issuer all still unproven) does not block entry because those are exactly what the output phases measure; it blocks **cutover**, not progress.

---

## 9. Must-Before-Cutover Items (Task 9)

Cutover (retiring V1 as canonical) must NOT occur until:
1. **Full CV1 census re-run on V2** = **certified or conditional** within `thresholds_version 1.0.0` (S1 near-zero on baseline metrics) — not just the 15 oracle cases.
2. **Zero regression** on the cells V1 got right (parallel-comparison `V2-regresses` set empty).
3. **Capture-recall validated** — V2 surfaces the candidates the census requires, including the `missing_extraction` items (EPS), or marks them `source_insufficient` honestly.
4. **Multi-candidate selection paths exercised** — precedence, `AMBIGUOUS`, `NO_SELECTION` validated against expanded cases (real bundles produce N>2 candidates).
5. **Workbook + OCR→MSIL output-contract equivalence to V1 confirmed** (equivalence harness green).
6. **Downstream revalidation** (MSIL/FVE/QAE/Query) clean against the V2 bundle.
7. **Cross-issuer (Millat)** oracle/spot-check, or cutover explicitly scoped to Lucky first.

---

## 10. Has OCR V2 Demonstrated Correction of the Verified CV1 Failures? (Task 10)

**Yes — for the statement-selection and scale classes (≈85% of CV1 errors), with executed end-to-end evidence; not yet for missing-extraction recall or full-census/multi-candidate generalization.**

- **Demonstrated:** all 15 verified cases — covering consolidated-basis, analysis-table, note, summary, investee, and scale corruption — now select the verified-correct value and filter the verified-incorrect value, deterministically, with no ranking/scoring/LLM and zero integrity violations. The exact failures CV1 documented as S1 are, for these cases, **no longer producible** by the engine.
- **Not yet demonstrated:** (a) `missing_extraction` — a capture-recall problem the selection layer cannot fix and the oracle does not cover; (b) the full 66-cell census S1 rate; (c) behavior with multiple eligible candidates; (d) cross-issuer. These are the output-phase / cutover gates, not P5 gaps.

---

## 11. One-Paragraph Verdict

Run against the shipped P0–P5 modules rather than asserted, OCR V2 has demonstrated — for all fifteen verified CV1 cases spanning the consolidated, analysis-table, note, summary, investee, and scale failure classes — that the value the system now selects is the verified-correct one and the value V1 wrongly produced is filtered out before selection ever runs, every case resolving deterministically as a single eligible survivor with no ranking, no scoring, no LLM, and zero integrity violations; this is the by-construction guarantee working exactly as specified, and it covers roughly eighty-five percent of the CV1 error mass. The engine is therefore **READY_FOR_OUTPUT_PHASES** — ready to build the workbook and export, and to run the V1 comparison and the full CV1 re-run — with rollback fully intact because V1 stays frozen and serving and nothing built is irreversible. What remains unproven is precisely what those phases exist to measure: raw-PDF capture recall (including the missing-extraction items the selection layer cannot address), the full sixty-six-cell census S1 rate, multi-candidate precedence and the ambiguous and no-selection paths, and cross-issuer generalization — all of which are correctly logged as Must-Before-Cutover rather than Must-Before-Entry. OCR V2 has corrected the verified statement-selection and scale failures in demonstrable, executed fact; it has not yet earned cutover, and this review authorizes the output phases that will decide whether it does.
