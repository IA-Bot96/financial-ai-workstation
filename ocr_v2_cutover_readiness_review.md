# OCR V2 — Cutover Readiness Review

**Status:** Readiness review only. No code authored, no implementation, no redesign. Findings drawn from **executing the shipped P0–P7 modules and both test suites** against the authoritative oracle (read-only invocation; no behavior changed).
**Date:** 2026-06-04
**Phases complete:** P0 Foundations · P1 Capture · P2 Registry · P3 Statement Governance · P3 Scale Governance · P4 Entity Governance · P5 Canonical Selection · **P6 Workbook Generation · P7 OCR→MSIL Export**.
**Migration model:** Option B — parallel build, frozen-V1 rollback path.
**Executed evidence:** OCR suite **74 passed**; MSIL suite **113 passed**; end-to-end oracle→export harness (§3/§4).

---

## 1. OCR V1 Failure Classes (Task 1)

CV1 (48 evaluable errors, 84.6% S1, NOT_CERTIFIED):

| Class | CV1 count | Nature |
|---|---|---|
| Wrong statement selection | 27 | consolidated-for-unconsolidated (8), investee-for-issuer (6), analysis-%-table-for-value (13) |
| Scale corruption | 14 | ×1000; mixed-scale; note-number-as-value |
| Missing extraction | 4 | EPS 2020–2023 never captured |
| Other | 3 | structural |

The regression oracle's **15 verified cases** represent the selection-and-scale classes (statement_basis 5, note 3, investee 2, scale 2, analysis-table 1, summary 1, source-selection 1). **`missing_extraction` is a capture-recall class and is not represented** (see §2, §7).

---

## 2. Has OCR V2 Demonstrated Correction? (Task 2)

**Yes — for the represented selection-and-scale classes (~85% of CV1 error mass), with executed end-to-end evidence.** Driving all 15 cases through capture → registry → statement → scale → entity → P5 selection:

```
selected_correct = 15   selected_incorrect = 0
ambiguous = 0           no_selection = 0
integrity_violations = 0     ranking/scoring/LLM used = False
selection reason (all) = "single_candidate_after_filtering"
```

Governance **filters the wrong candidate out before selection runs**, leaving one eligible survivor — the correct value — selected deterministically without ranking. The S1 errors CV1 documented for these classes are **no longer producible**.

**Not demonstrated:** `missing_extraction` (capture-recall, not selection — the selection layer cannot recover an uncaptured candidate).

---

## 3. Implementation Completeness (Task 3) — COMPLETE through P7

All eight phases are built and tested. **Executed end-to-end** (oracle → … → P6 workbook → P7 export):

```
workbook_rows_generated   = 15      rows == 15 (one canonical row per case) = True
all workbook rows == verified-correct value = True   (canonical-only, no candidate scoring)
rows_exported = 15        export signals = 15
```

- **P6 Workbook** projects canonical-selection output into one canonical row per metric (canonical-only; no candidate/loser leakage into the human workbook).
- **P7 Export** adapts the canonical workbook into the **existing MSIL `IntelligenceSignal`** input — no MSIL schema change.
- **Suites:** OCR **74 passed**, MSIL **113 passed**.

Implementation completeness is not the gap; the gap is *validation breadth* (§7).

---

## 4. Contract Compatibility (Task 4) — PRESERVED

Executed export audit over the 15-case run:

```
contract_preserved         = True
value_mutations            = 0
provenance_preserved_count = 15
msil_contract_compatible   = True
```

The canonical value reaches MSIL **unchanged** (zero value mutation), provenance survives for every row, and the export targets the **frozen MSIL contract** (the module performs no MSIL schema change). Decisive corroboration: **MSIL's own 113 tests still pass** after the OCR V2 export integration — the frozen MSIL contract is demonstrably untouched. Output shape remains one canonical value/metric/year + provenance, equivalent to V1's downstream contract.

---

## 5. Rollback Readiness (Task 5) — READY

- **V1 frozen and serving**; no cutover yet, so the standing rollback is *not cutting over*.
- **Registry append-only** — no run corrupts inputs; re-runs are clean.
- **Selection deterministic** (confirmed) and config-versioned; regressing config reverts.
- **No MSIL schema change** — export is reversible by ceasing to emit the V2 bundle.
- Oracle **version-pinned, append-only, externally verified** — cannot be silently weakened.

---

## 6. Regression-Oracle Sufficiency (Task 6) — sufficient for the represented classes; structurally bounded

**Sufficient to prove** the prevention mechanism end-to-end for every represented failure class, deterministically, through to a contract-preserving export.
**Bounded by construction:** all 15 cases are **2-candidate pairs** resolving to `single_candidate_after_filtering`, so the oracle does **not** exercise multi-eligible-candidate precedence, the `AMBIGUOUS` path, the `NO_SELECTION` path, or candidate counts N>2 that real bundles produce. It is also **Lucky-only** and **15 cases, not the 66-cell census**.

---

## 7. Remaining Unproven Areas (Task 7)

1. **Capture recall from the raw PDF** — including `missing_extraction` (EPS). The audits validate representability/governance of oracle-defined candidates, not pixel-level extraction recall.
2. **Full CV1 census re-run** — 66 cells, S1 rate + Wilson CI vs `thresholds_version 1.0.0`.
3. **Multi-candidate selection paths** — precedence, `AMBIGUOUS`, `NO_SELECTION` (unexercised by the 15).
4. **V1 vs V2 regression** — that V2 does not regress the cells V1 got right (parallel comparison not yet run).
5. **Downstream revalidation** beyond MSIL contract-shape — FVE baselines (HSIG verdicts shift), QAE, Query answer/citation correctness against the V2 bundle.
6. **Cross-issuer (Millat)** generalization.

---

## 8. Readiness for the Migration-Validation Activities (Task 8)

| Activity | Ready? | Basis |
|---|---|---|
| **V1 vs V2 comparison** | ✅ Ready to run | V1 frozen; V2 produces parallel canonical values; cell-by-cell diff is the activity itself |
| **Full CV1 re-run** | ✅ Ready to run | Engine proven on the oracle; the 66-cell census is what this activity measures |
| **Downstream revalidation** | ✅ Ready to run | Export contract-preserving (value_mutations=0); MSIL 113 green; FVE/QAE/Query re-ingest is the activity |
| **Migration cutover** | ⛔ Not yet | Gated by §9 Must-Before-Cutover (full census certified/conditional, zero regression, recall, multi-candidate, downstream clean) |

The first three are **ready to enter**; cutover is **explicitly gated** — entry to validation ≠ cutover.

---

## 9. Classification of Findings (Task 9)

**Must-Before-Comparison** (prerequisites to start V1↔V2 comparison):
- Pin the frozen V1 baseline output and run V2 over the **same pinned Lucky bundle**.
- Define the cell-by-cell comparison methodology against the **CV1 66-cell truth set** (classify each cell: V2-fixes / V2-matches-V1-correct / V2-regresses / both-wrong).

**Must-Before-Cutover:**
- Full CV1 census re-run on V2 = **certified or conditional** within thresholds 1.0.0.
- **Zero regression** on V1-correct cells (`V2-regresses` empty).
- **Capture recall validated**, incl. `missing_extraction` (EPS) found or honestly `source_insufficient`.
- **Multi-candidate paths exercised** (precedence / AMBIGUOUS / NO_SELECTION) on N>2 real candidates.
- **Workbook + export output-equivalence to V1** confirmed on the full census.
- **Downstream revalidation** (MSIL/FVE/QAE/Query) clean against the V2 bundle.
- **Cross-issuer** handled, or cutover scoped Lucky-first.

**Can-Resolve-During:**
- Expand the oracle with multi-candidate + Millat cases.
- Mechanized comparison tooling; non-core metric-class handling.

**Post-Cutover:**
- Candidate drill-down in Query; V1 retirement after a stability window; broader issuer generalization.

---

## 10. Determination (Task 10)

# READY_FOR_COMPARISON

Implementation is complete through P7 (OCR 74 / MSIL 113 passing); OCR V2 demonstrably corrects the represented selection-and-scale failure classes end-to-end (15/15 correct, 0 wrong, deterministic, no ranking) and carries the correct value through to a **contract-preserving MSIL export with zero value mutation**; the frozen MSIL contract is untouched (its own 113 tests still pass); and rollback is fully intact (V1 frozen, registry append-only, no schema change). Nothing blocks **entering** the migration-validation stage. The unproven areas — full census, recall, multi-candidate paths, cross-issuer, downstream revalidation — are precisely what that stage measures, and are correctly classified as **Must-Before-Cutover, not Must-Before-Comparison.** This is a clean clearance to begin comparison and the CV1 re-run; it is **not** authorization to cut over.

---

## 11. Has OCR V2 Earned the Right to Enter the Migration-Validation Stage? (Task 11)

**Yes.** OCR V2 is a complete, tested, parallel-built engine that — on every one of the fifteen verified CV1 cases — selects the correct value, filters the value V1 wrongly produced, and delivers it to MSIL through the frozen contract without mutation, with rollback intact and the frozen platform demonstrably undisturbed. It has earned entry to V1↔V2 comparison, the full CV1 re-run, and downstream revalidation. It has **not** earned cutover: that right must be earned *inside* the validation stage, by a certified/conditional full-census re-run with zero regression and validated recall — none of which can be claimed before the stage runs. Enter the validation stage; keep V1 frozen behind it.

---

## 12. One-Paragraph Verdict

Run against the shipped P0–P7 modules rather than asserted, OCR V2 has demonstrated through the entire pipeline — capture, registry, the three governance layers, canonical selection, workbook generation, and the OCR→MSIL export — that for all fifteen verified CV1 cases the engine now selects the correct value and filters the value V1 wrongly produced, deterministically and with no ranking, scoring, or LLM, then carries that value into MSIL through the existing IntelligenceSignal contract with zero mutation and full provenance, leaving the frozen platform untouched as proven by MSIL's own one-hundred-thirteen tests still passing. Implementation is complete, contract compatibility is preserved, rollback is intact because V1 stays frozen and nothing built is irreversible, and the regression oracle is sufficient for the classes it represents while honestly bounded to two-candidate cases on a single issuer. What remains unproven — raw-PDF recall including the missing-extraction items, the full sixty-six-cell census S1 rate, multi-candidate precedence and the ambiguous and no-selection paths, regression against V1-correct cells, and downstream revalidation of FVE, QAE, and Query — is exactly the work of the migration-validation stage, not a precondition to entering it. The determination is therefore **READY_FOR_COMPARISON**: OCR V2 has earned the right to enter the migration-validation stage, and it has not yet earned cutover, which must be won inside that stage with V1 frozen behind it.
