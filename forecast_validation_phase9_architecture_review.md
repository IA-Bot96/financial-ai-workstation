# Forecast Validation Engine — Phase 9 Architecture & Readiness Review

**Review date:** 2026-06-02
**Scope:** Architecture, product readiness, data contracts, implementation sequencing. No code review, no refactors.
**State reviewed:** HistoricalSeriesIntegrityGate (implemented); Forecast Validation Phases 1–9; infra (Models, Framework, Admission, Confidence Composition, Evidence, Scorecard); rules EPSBaseline, RevenueSeries, ForecastInput, RevenueGrowth, RevenueTrendBreak, RevenueForecastPlausibility; category RevenueValidationService.
**Evidence:** `forecast_validation_phase9_report.json`, `financial_series_integrity_sprint_report.json`, `historical_series_integrity_gate_report.json`, `forecast_validation_mvp_rescoping.md`, `forecast_validation_contract_decisions.md`.

---

## 0. The One Finding That Frames Everything

The team produced two high-quality governing decisions on 2026-06-02:

- **Re-scoping doc** → "MVP Out Of Scope: **Revenue growth validation**, … Trend-break validation, Forecast plausibility scoring."
- **Contract decisions doc** → Revenue growth, forecast plausibility, and trend-break are **Deferred Categories**, unlockable only when "`revenue` becomes `clean` or `clean_with_warning` after deterministic remediation **and** analyst truth validation."

Then Phases 5–9 implemented exactly those deferred items: four revenue rules plus a complete `RevenueValidationService` whose Phase 9 objective is literally *"Create the first complete Forecast Validation category."*

Meanwhile the latest remediation evidence says revenue did **not** unlock:

| Source | Revenue status |
|---|---|
| `historical_series_integrity_gate_report.json` | `baseline_not_validatable` |
| `financial_series_integrity_sprint_report.json` — after source-selection fixes | `baseline_not_validatable` (before **and** after; `metrics_whose_blocking_status_changed: []`) |

So the one fully-built category is the one that, on every real bundle that exists today, can only return `SKIPPED`. The build has diverged from its own contracts. Everything below follows from this.

---

## 1. Architecture Readiness

**Infrastructure layer: ready and genuinely good.** The contract-decisions doc is the strongest artifact in the series — it resolves the four blind spots from the pre-implementation review with real decisions: gate-owns-admission (not Query Engine retrieval), `min()` confidence composition with per-status ceilings (`clean_with_warning` ⇒ 0.80), a four-type citation taxonomy (`WORKBOOK_CELL` / `PDF_PROVENANCE` / `GATE_OVERRIDE` / `NONE`), and `SKIPPED ≠ FAIL`. The implemented Admission, Confidence Composition, Evidence, and Scorecard components map cleanly onto those decisions. This is the right spine.

**Category + orchestration layer: not ready.** Phase 9 explicitly records `"No multi-category orchestration implemented."` There is no `ForecastValidationOrchestrator` (architecture §10), no run-level `ForecastValidationResult` assembly, and no end-to-end run against the real Lucky bundle — only unit tests. The one category that exists (Revenue) is inert on real data. So the engine has excellent rails and one fully-built train that cannot leave the station, while the train that *can* run (EPS, readiness, forecast-input) has no assembled route.

**Verdict:** infrastructure readiness HIGH; product/category readiness LOW due to scope drift and a missing orchestration spine.

---

## 2. Does RevenueValidationService Form a Coherent MVP Category?

**As an engineering artifact: yes. As an MVP category: no.**

- It is internally coherent — three rules, deterministic aggregation (`pass`/`warning`/`fail`/`skipped`), min-composed confidence, evidence/citation dedup, category score (100/70/0/null). The shape is correct and reusable.
- It is **not MVP-appropriate**, for three independent reasons:
  1. **Inadmissible input.** Revenue is `baseline_not_validatable` on the only real bundle, and the latest remediation attempt failed to change that. On production data the service returns `SKIPPED` and validates nothing.
  2. **Contract violation.** Both governing docs place this category out-of-scope/deferred. Building it now contradicts the team's own accepted decisions.
  3. **Synthetic-only proof.** Phase 9's `pass`/`warning`/`fail` coverage runs on fixtures with clean revenue that does not exist in production. The rules' thresholds and logic have never executed against real admitted revenue — the same fixture-vs-real gap that blocked Query Engine v1 freeze (citation 1.0 on fixtures, 0/60 on the real bundle).

The coherent MVP category that *should* have been completed first — **EPS standalone baseline** (the only admitted metric) or **Historical Baseline Readiness** (runs on any status) — was left as loose rules while category-depth went to the blocked metric.

---

## 3. Hidden Architectural Risks

- **HR1 — Synthetic-validated logic on a metric that may never unlock.** The sprint report shows source-selection fixes corrected revenue's *selected values* (2025 → 528bn) yet revenue stayed blocked because the >100× candidate spread persists — that needs extraction/normalization fixes, which are outside the consolidation sprint's scope. The most-built category depends on the unlock least likely to arrive without deeper OCR work.
- **HR2 — A live, material cross-engine value divergence now exists.** Post-sprint, the gate prefers revenue 2025 = 528,651,878,000 (income statement) while the value written to the workbook / retrieved by Query Engine is the note-derived 25,417,143. That is the `GATE_OVERRIDE` case the contract anticipated — but it is now real and ~20,000× apart. The citation-honesty contract covers evidence; **user-facing reconciliation across engines (which revenue does the product show?) is unspecified.**
- **HR3 — Scorecard semantics when everything is SKIPPED.** Category score for `skipped` is `null`. With 0–1 executable categories, the run-level scorecard is mostly null. There is no defined run-level aggregation, so the overall result risks reading as "empty/green" rather than "we validated nothing." This is the prior "constant red light" risk inverted into a "constant blank light."
- **HR4 — Gate result is replay-only and unversioned.** The sprint changes are replay reconstructions ("OCR was not rerun"); the gate is recomputed against a static bundle with no persisted, fingerprint-bound gate sidecar. FVE admission depends on a recomputation whose version/fingerprint binding is undefined (open since the pre-implementation review).
- **HR5 — The MVP delivers a data-quality gate dressed as forecast validation.** EPS, the only admissible metric, has only a baseline-readiness rule — no forecast conclusion. Honestly stated (the rescoping calls it a "gate-first readiness product"), but the product framing must not be "Forecast Validation MVP" to stakeholders expecting forecast checks.

---

## 4. Missing Contracts

- **MC1 — Run-level scorecard aggregation** when categories are `SKIPPED`/null (overall status + score with mostly-skipped runs). Category-level aggregation exists; cross-category does not.
- **MC2 — `ForecastValidationOrchestrator` contract** (gate → admission → category execution → run assembly). Defined in architecture §10, not built or concretely specified.
- **MC3 — Gate-result provenance/versioning sidecar** binding a gate verdict to bundle fingerprint + gate-logic version, stamped on every evidence record.
- **MC4 — `unlock` contract for deferred categories.** The rescoping lists unlock conditions in prose; nothing machine-enforced prevents `RevenueValidationService` from being wired into a real run and executing its synthetic-validated logic on future admitted data **without** the required analyst-truth-set gate.
- **MC5 — Forecast-input source/units contract.** `ForecastInputValidationRule` exists, but where payloads originate, required unit/scale declaration, and forecast-vs-historical scale alignment are thin.
- **MC6 — Multi-`source_report_year` semantics** (restatement vs corruption) — still deferred, increasingly load-bearing now that the "correct" revenue values surface across pages/reports.

---

## 5. Over-Engineering

- **OE1 — The entire revenue category is depth on a blocked metric.** Four revenue rules + aggregation service + two result models + category scorecard, for a metric that is inadmissible and explicitly deferred. This is the clearest over-investment.
- **OE2 — Three distinct revenue numeric rules** (growth, trend-break, forecast-plausibility) built before any one has run on real admitted data — speculative breadth ahead of a single proven execution.
- (Not flagged as waste: the four-type citation taxonomy and multi-metric confidence composition are defensible infra even though only single-metric EPS runs today.)

---

## 6. Under-Engineering

- **UE1 — No multi-category orchestrator / run-level scorecard** — the actual MVP spine, explicitly unbuilt.
- **UE2 — EPS, the only admissible metric, is under-built** — one baseline rule, no category surface, no scorecard parity with revenue. The thing that can run is thin; the thing that can't is thick.
- **UE3 — Historical Baseline Readiness as a first-class category** (rescoping MVP In-Scope #1) is not present as an FVE-side category emitting one readiness result per metric into the scorecard.
- **UE4 — No end-to-end run on the real bundle.** Everything is unit tests; there is no production-bundle smoke run producing an assembled `ForecastValidationResult`.
- **UE5 — Gate not validated against analyst truth.** The admission authority everything depends on is asserted by unit tests, not checked against known-correct Lucky figures.

---

## 7. Continue / Pause / Re-scope?

**PAUSE FOR AUDIT.** Not "continue" (more categories on this pattern — margin, cash-flow — would be equally inert and deepen the drift). Not "re-scope again" (the existing rescoping is correct; the *build* diverged from it, not the plan).

The pause should reconcile the built surface with the governing contracts:
1. Confirm `RevenueValidationService` and the three revenue numeric rules are **parked behind an explicit unlock contract** (MC4), counted as pre-built-deferred — not as MVP progress.
2. Redirect effort to the in-scope spine that is currently missing: orchestrator + run-level scorecard + the executable categories.

This is a sequencing correction, not a teardown. The infrastructure is sound; the category effort was aimed at the wrong metric.

---

## 8. Recommended Next Implementation Priority

**Build and run the gate-first MVP spine end-to-end on the real Lucky bundle:**

`ForecastValidationOrchestrator` → run `HistoricalSeriesIntegrityGate` → category admission → execute only the executable categories (**EPS standalone baseline**, **forecast-input contract**, **evidence/provenance completeness**, **historical baseline readiness**) → assemble a run-level `ForecastValidationResult` + scorecard with **honest SKIPPED accounting** (MC1).

Concretely: promote EPS from a loose rule to the flagship executable category (UE2), add the readiness category (UE3), define run-level aggregation (MC1/MC2), and produce one assembled result on the production bundle (UE4). Park revenue behind its unlock contract (MC4). This ships the product the rescoping actually defined.

---

## 9. Findings Classification

**Must Resolve Before Continuing**
- Scope-drift reconciliation: revenue category contradicts both governing contracts (§2, OE1). Park it; stop building deferred categories.
- Run-level orchestration + scorecard aggregation contract for SKIPPED/null runs (MC1, MC2, UE1) — without it there is no shippable MVP.
- Unlock contract preventing deferred categories from executing on real data without the analyst-truth gate (MC4, HR1).

**Should Resolve Soon**
- Promote EPS to the flagship executable category + add Historical Baseline Readiness category (UE2, UE3).
- End-to-end run on the real bundle producing an assembled result (UE4).
- Gate-result provenance/versioning sidecar (MC3, HR4).
- Cross-engine revenue value reconciliation: which value the product surfaces when gate ≠ workbook (HR2).
- Run-level score semantics for all-skipped runs (HR3).
- Gate validation against an analyst truth set for the metrics that matter (UE5).

**Post-MVP**
- Activate revenue/margin/cash-flow numeric categories once metrics unlock AND analyst truth validates them.
- Multi-`source_report_year` / restatement semantics (MC6).
- Deep forecast-input source/units contract (MC5, beyond shape checks).

---

## 10. One-Paragraph Verdict

The Forecast Validation Engine has excellent infrastructure and the best contract discipline in the program — gate-owned admission, composed confidence with ceilings, an honest citation taxonomy, and `SKIPPED ≠ FAIL` are all correctly decided and built. But Phase 9 declared a "first complete category" by building the **one category its own re-scoping and contract documents placed out of scope**, against a metric (`revenue`) that the latest remediation attempt left `baseline_not_validatable`, with pass/fail logic proven only on synthetic data. The result is depth on a blocked metric and thinness on the executable spine: no orchestrator, no run-level scorecard, EPS (the sole admissible metric) under-built, and no end-to-end run on real data. The right move is to pause for a short reconciliation audit, park the revenue category behind an explicit unlock contract, and redirect to the gate-first readiness MVP the rescoping already defined — shipping a truthful "what can and cannot be validated" product rather than a forecast-validation façade over data that cannot yet be validated.
