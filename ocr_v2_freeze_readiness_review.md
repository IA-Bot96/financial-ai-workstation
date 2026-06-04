# OCR V2 — Freeze Readiness Review

**Status:** Review only. No implementation, no redesign. Findings verified against current-state artifacts (latest run = R2, 17:32).
**Date:** 2026-06-04
**Read:** OCR V2 Architecture Review · Migration Review · Contracts · Implementation Plan · validation reports (R1-A, final-gap/R1-B, final-validation, **R2**) · Integration Audit · plus independent verification of `output/ocr_v2_r2_workbook.xlsx` against `cv1_truth_set_lucky_v1_0_0.csv`.

---

## 0. Determinations (up front)

| Question | Determination |
|---|---|
| **Freeze OCR V2 as the validated OCR engine?** | **NOT_READY_FOR_FREEZE** (narrowly — one bounded step away) |
| **Ready for production integration?** | **NOT_READY_FOR_PRODUCTION_INTEGRATION** (decisively) |

The Lucky result is genuine and strong — **independently verified 66/66** — but freeze and integration each require evidence the current state does not yet provide.

---

## Evidence basis (independently verified, not taken from the reports)

Re-running the latest R2 workbook against the 66-cell truth set:
```
exact_match = 52   source_insufficient_correct = 14   →  66/66 covered correctly
value_mismatch = 0   scale_mismatch = 0   missing = 0   source_insufficient_VIOLATION = 0
```
The 14 source-insufficient cells (total_debt 2020–2025; total_liabilities + long_term_debt 2020–2023) are **correctly abstained** — the R2 total_liabilities fix did **not** break them. OCR test suite: **91 passed.**

---

## 1. Architectural Compliance — PASS

The B3 run executes the specified capture-first pipeline end-to-end: `bbox adapter → CandidateCapture → CandidateRegistry → StatementGovernance → ScaleGovernance → EntityGovernance → CanonicalSelection → WorkbookGenerator → MSIL export`. No selection-during-capture; registry append-only; workbook emits only `SELECTED` rows. Matches the frozen architecture.

## 2. Contract Compliance — PASS

Output contract ≡ V1 (one canonical value per metric/year + provenance); MSIL export preserves the `IntelligenceSignal` contract (`value_mutations = 0`, `msil_contract_compatible = true`, verified earlier and unchanged). Candidate mandatory-dimension and append-only registry contracts hold.

## 3. Governance Correctness — PASS (proven on real data)

R1-A proved statement governance correctly marks `ANALYSIS_TABLE` rows `INELIGIBLE`; R2 resolved the residual selection ambiguity. Verified behaviors: contaminated summary LTD and millions-rounded OCF proxies **demoted to non-canonical** (not emitted); 0 SI violations; 0 fabrications; precedence `PRIMARY > NOTE > SUPPORTING > SUMMARY > ANALYSIS` honored. The by-construction guarantees hold on the real run.

## 4. Truth-Set Performance — PASS on Lucky, but SINGLE-ISSUER and AUTOMATED-ONLY

- **Verified 66/66 on Lucky** (52 exact + 14 correct abstentions, 0 mismatches).
- **But:** this is **one issuer** (Lucky). Millat — the program's second validation issuer — has **not** been run through OCR V2.
- **And:** this is an **automated coverage comparison**, not the **blind-protocol CV1 re-run** (analyst Section-A lock, adjudication, S1 second-review) that the Validation Execution Review defined as the certification gate. Per thresholds 1.0.0, a single 66-cell census — even perfect — supports at most a **CONDITIONAL** disposition (the Wilson ≤0.5% bar needs a pooled multi-issuer census), and no blind CV1 disposition has been issued.

## 5. Regression Protection — PASS (with scope note)

The 15-case regression oracle is version-pinned, external, append-only; the OCR suite is **91 passing** (grown with R1/R2/bridge tests). Protects the engine against regressions on the encoded cases. Scope note: the oracle + truth set are **Lucky-only**; no Millat regression cases exist.

## 6. Remaining Technical Risks

- **Over-fit risk in R2 remediations (primary freeze risk).** The total_liabilities fix labels "the unlabeled subtotal row immediately before TOTAL EQUITY AND LIABILITIES" — a **positional heuristic tuned to Lucky's balance-sheet layout**. The OCF fix (alias only "Net cash generated from operating activities") is more principled, but the TL heuristic's generalization is **unproven**. 66/66 on the one document it was tuned against cannot, by itself, distinguish "fixed the engine" from "fit the test."
- **Workbook is a 582-row dump**, not a clean 66-cell canonical projection; census cells resolve correctly, but the projection carries large non-canonical residue (schema-cleanliness debt).
- **Bridge input is staged bbox CSVs**, not the production PDF path (see §7).

## 7. Production Integration Risks — BLOCKING (from the Integration Audit)

OCR V2 is **validation-only and not wired to production**, confirmed by the wiring audit:
- `run_pipeline.py` and the API route construct/inject **`ocr_engine` (V1)**; **0 production (non-test) imports of `ocr` (V2)** — V2 is imported only by 14 test references.
- No production `IOCRPipeline`-compatible V2 orchestrator; no composition root, feature flag, env var, or DI binding selects V2.
- V2 consumes **manually-staged bbox CSVs**, not the production `CompanyContext` PDF orchestration.
- MSIL is not even invoked from OCR production (`run_pipeline.py` stops at Query bundle generation).

Cutover therefore **requires integration work** — it is not a configuration switch.

## 8. Rollback Readiness — PASS (trivially)

V1 (`ocr_engine`) remains the live, untouched production engine; V2 is a separate parallel substrate. Rollback is trivial because nothing is wired — but that is the flip side of §7: excellent rollback posture *because* integration has not begun.

---

## Determination 1 — Freeze

# NOT_READY_FOR_FREEZE

**Justification.** OCR V2 has reached a real, independently-verified milestone: **66/66 on the Lucky truth set** with governance correct, source-insufficient abstentions preserved, zero fabrications, contracts intact, and 91 passing tests. The engine *logic* is validated. But freezing it as "**the** validated OCR engine" is premature on two grounds the evidence makes unavoidable: (1) the result is **single-issuer** and includes **Lucky-tuned remediations** (notably the positional total_liabilities labeling), so generalization is unproven and the over-fit risk is live — 66/66 on the one document the fixes were tuned against cannot establish a validated engine; and (2) no **blind-protocol CV1 certification** has been issued — the 66/66 is automated coverage, and per thresholds 1.0.0 a single-issuer census can at best support a **CONDITIONAL** disposition, which has not been formally rendered. The path to freeze is **bounded and short**: run Millat through the identical pipeline (confirming the TL/OCF heuristics generalize and adding Millat regression cases), and execute the blind CV1 re-run to a **CONDITIONAL** disposition. Until then the honest status is "**validated on Lucky**," not "frozen validated engine."

## Determination 2 — Production Integration

# NOT_READY_FOR_PRODUCTION_INTEGRATION

**Justification.** The Integration Audit is unambiguous and decisive: OCR V2 is **validation-only**. Production entrypoints (`run_pipeline.py`, the API OCR route) import and construct the V1 `ocr_engine` stack; there are **zero production imports of the V2 `ocr` package**, no V2 orchestrator compatible with the production `IOCRPipeline`/`CompanyContext` contract, and no composition root, feature flag, or DI binding that could route requests to V2. V2 currently runs only from **manually-staged bbox CSVs**, not the production PDF path. Production integration is therefore not a configuration cutover but a build effort — and it must not begin until the freeze gate (Determination 1) is cleared, so that integration wires a *validated* engine rather than a single-issuer candidate.

---

## Bounded Path to Both Gates

1. **Run Millat** through the identical OCR V2 pipeline; confirm the R2 TL/OCF heuristics generalize; add Millat regression-oracle cases. *(Closes the over-fit risk.)*
2. **Execute the blind CV1 re-run** (analyst Section-A lock, adjudication, S1 second-review) on the V2 output → render a **CONDITIONAL** (single-issuer) or, once pooled, **CERTIFIED** disposition. *(Closes the certification gap.)* → then **FREEZE**.
3. **Build the production bridge**: a `CompanyContext`/PDF → V2 candidate path (removing manual CSV staging), a V2 `IOCRPipeline`-compatible orchestrator, and a composition-root/feature-flag selector between V1 and V2, with the frozen-V1 rollback retained. → then **PRODUCTION INTEGRATION**.

---

## One-Paragraph Verdict

OCR V2 has earned a verified milestone but not a freeze: re-running its latest R2 output against the truth set independently confirms **66/66** — fifty-two exact values and fourteen correctly-abstained source-insufficient cells, with zero value or scale mismatches, zero fabrications, intact contracts, and ninety-one passing tests — and the governance and selection behaviors that the R1-A diagnosis exposed are now demonstrably correct on real extracted data. Yet that 66/66 stands on a single issuer and leans on Lucky-tuned remediations (the positional total-liabilities labeling most of all), so it cannot yet distinguish a validated engine from a well-fit one, and it was produced by automated coverage rather than the blind-protocol CV1 certification the program defines as its correctness gate — which, on one census, could reach only CONDITIONAL regardless. The engine is therefore **NOT_READY_FOR_FREEZE**, but only one bounded step away: a Millat run plus a blind CV1 CONDITIONAL disposition. It is **NOT_READY_FOR_PRODUCTION_INTEGRATION** by a wider and unambiguous margin — the wiring audit shows production still runs entirely through `ocr_engine`, with zero production imports of the V2 package, no compatible orchestrator, and a bridge that still consumes hand-staged CSVs rather than the production PDF path — so integration is a build effort to be started only after the freeze gate is cleared, with V1 retained as the untouched rollback throughout.
