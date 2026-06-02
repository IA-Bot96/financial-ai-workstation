# Forecast Validation — Pre-Implementation Architectural Review

**Review date:** 2026-06-02
**Objective:** Identify remaining architectural blind spots before Forecast Validation Engine (FVE) implementation begins.
**Constraint:** No code review, no refactors. Focus only on architecture, data contracts, and implementation sequencing.

**State reviewed:**
- OCR Engine v1 — frozen as controlled analyst-review v1 (review-gated; `validation_is_valid=false`; single `source_report_year`).
- Query Engine Core v1 — citation/provenance plumbing proven on the fresh bundle (`citation_rate=1.0`); golden-suite accuracy still unrerun.
- `HistoricalSeriesIntegrityGate` — **implemented** (`backend/shared/services/historical_series_integrity_gate.py`), 7 unit tests passing, report generated.
- Forecast Validation architecture — design + `financial_series_integrity_implementation_design.md` + remediation plan.

**Evidence base:** `historical_series_integrity_gate_report.json`, `financial_series_integrity_root_cause_audit.json`, `scale_consistency_audit.json`, OCR/Query freeze audits.

---

## 0. Where Things Actually Stand

The integrity gate is real and it works: on the production Lucky bundle it returns **0 `clean`, 1 `clean_with_warning` (EPS), 7 `baseline_not_validatable`, 3 `missing`**, overall `baseline_not_validatable`, 86 critical issues, `forecast_validation_mvp_readiness = not_ready`. This is the correct, honest outcome and it closes the "validation always silently fails on corrupt data" risk from the previous review.

But the gate's success surfaces a set of **new architectural blind spots that only become visible now that the gate exists**. The most important one is not in any single artifact — it appears only when the gate output, the root-cause projection, and the FVE category dependency map are read together.

---

## 1. The Headline Blind Spot

### BS1 — After full planned remediation, almost none of the FVE MVP categories can run. The MVP scope has not been re-scoped to the gate's reality.

The root-cause audit projects the **best achievable** state after the planned deterministic source/scale policy (the five remediation fixes):

| Projected post-remediation status | Metrics |
|---|---|
| `clean` | **none** (`estimated_blocked_metrics_becoming_clean: 0`) |
| `clean_with_warning` | EPS (already), + revenue, total_assets, operating_cash_flow |
| `baseline_not_validatable` (stays blocked) | profit_after_tax, operating_profit, gross_profit, cash_and_cash_equivalents |
| `missing` | total_debt, long_term_debt, total_equity |

Now map that against the FVE category → required-metric table (implementation design §15):

| FVE MVP Category | Requires | Runnable post-remediation? |
|---|---|---|
| Revenue growth consistency | revenue | **Yes** (warning) — the only one |
| Margin consistency | revenue, gross_profit, operating_profit, PAT | **No** — 3 of 4 stay blocked |
| EPS consistency | EPS, **PAT** | **No** — PAT stays blocked |
| Balance sheet consistency | total_assets, **total_equity**, debt | **No** — equity missing |
| Cash flow consistency | operating_cash_flow, **PAT**, **cash** | **No** — PAT + cash blocked |
| Debt consistency | **total_debt, long_term_debt** | **No** — both missing |
| Forecast plausibility | depends on metric | Only for revenue |

**The blind spot:** the gate converts "confidently wrong" into "almost nothing runs." Of seven advertised MVP categories, **one** is executable after the full remediation effort, and even that one is `clean_with_warning`, never `clean`. The FVE architecture still lists 12 MVP metrics and 6–7 categories as the deliverable (design §13, §15). No artifact re-scopes the MVP to "revenue-growth-only at warning confidence" — which is what the data actually supports. Beginning implementation against the published category list would build six categories that cannot return a result on any current or near-term bundle.

**Sequencing consequence:** the MVP scope must be redefined as a function of gate output *before* rule implementation starts — not discovered category-by-category during the build.

---

## 2. Data-Contract Blind Spots

### BS2 — Two divergent data-access paths now exist into the same data; "the selected value" has two owners.
The FVE architecture mandates consuming `CompanyKnowledgeBase` and **reusing Query Engine retrieval/calculation contracts** (§2, §4, §15.6). But the implemented gate's contract is `evaluate(consolidation_result: FinancialYearConsolidationResult, …)` in `backend/shared/services` — it reads the consolidation result **directly, bypassing the Query Engine**, and its `HeadlineMetricSelectionPolicy` can **override** the upstream-selected value (`decision_status: overrode_upstream`). There are now two answers to "what is revenue for 2024?": the Query Engine's retrieved consolidated value, and the gate's policy-selected value. **Nothing defines which is canonical for FVE**, or what happens when they disagree (they will — the gate exists precisely because upstream selection is wrong). This is an unresolved source-of-truth ownership question, not a refactor: it must be decided as a contract before FVE consumes either path.

### BS3 — Gate overrides break the workbook-citation guarantee.
Query Engine v1 proved `citation_rate = 1.0`: every value written to the workbook has a `WorkbookCellMapping`. But **only the consolidation-selected candidate was written to the workbook.** When the gate's policy selects a *different* candidate (e.g. revenue 2025: gate would prefer the page-365 income-statement `Revenue` = 528,651,878,000 over the written note value 25,417,143), that gate-preferred value **has no workbook cell** and therefore no citation. The FVE architecture simultaneously requires (§8) "workbook citations must come from persisted `WorkbookCellMapping`" **and** (§9 of the gate design) that the gate may override selection. These two contracts collide. The architecture must state what citation a gate-overridden value carries (PDF-page-only? "uncited override"?) before evidence assembly is designed.

### BS4 — Gate confidence and validation confidence are two unreconciled scales.
The gate emits a `confidence` (observed 0.55–1.0; EPS = 0.8). The FVE architecture §9 defines a separate `ValidationConfidenceService` with buckets (High ≥0.85, Medium 0.65–0.84…). EPS at gate-confidence 0.8 lands in FVE "Medium" — but is that an input to validation confidence, a ceiling on it, or a parallel number shown alongside it? **The composition is undefined.** Two confidence numbers on the same finding, with no defined relationship, is a contract gap that will produce contradictory analyst-facing signals.

### BS5 — The gate is defined and proven only against single-`source_report_year` bundles.
The bundle has `report_years=[2025]`, `by_source_report_year=1`; the entire 2020–2025 "history" is one filing's comparative columns. The gate's `candidate_spread` and YoY rules are therefore tuned to *intra-report* candidate noise. When **multi-filing** bundles arrive (the real historical-series case), each `(metric, value_year)` will gain cross-report candidates, legitimate restatements will appear as candidate spread, and recency/source-of-truth logic becomes load-bearing. **The gate's data contract for multi-report candidate sets, restatement-vs-corruption disambiguation, and cross-report dedup is undefined.** FVE's own "trend breaks coinciding with restatements" rule (architecture §6) depends on exactly this and cannot be exercised today.

### BS6 — Missing metrics are a structural category-killer rooted outside the gate's power.
`total_equity`, `total_debt`, `long_term_debt` are `missing` because the exact canonical metric is absent (registry/normalization gap), not because of scale. The gate correctly refuses to substitute — but that permanently disables Balance-Sheet-identity and Debt-consistency validation regardless of remediation, because the fix lives in OCR/normalization, not FVE. The architecture advertises these categories in MVP; the data contract cannot supply them. They must be explicitly deferred, not built.

---

## 3. Sequencing Blind Spots

### BS7 — The gate is both the remediation acceptance test *and* the FVE input contract, with no independent ground truth.
The remediation plan's success criterion (Step 4) is "re-run the audit and watch metrics move to clean." The gate is what produces that verdict, and the same gate is FVE's admission contract. **There is no golden set of known-correct Lucky figures** validating the gate itself — only 7 unit tests on synthetic cases. If the gate has a false-negative (passes a corrupt series), remediation "succeeds" and FVE ingests bad data with full confidence. Before implementation, the gate needs validation against a small analyst-confirmed truth set for at least the P0 metrics (revenue, PAT, total_assets) — otherwise the entire integrity guarantee rests on an unverified classifier.

### BS8 — No OCR/normalization remediation has actually happened yet.
`financial_series_integrity_root_cause_audit.json`: `implementation_performed: false`, `code_modified: false`. The only thing built is the gate. The projected "3 metrics recover to clean_with_warning" is an **estimate**, not a measured result, and the audit's own confidence on it is "medium." Sequencing risk: starting FVE rule implementation in parallel assumes a remediation outcome that has not been produced or measured. The gate result must be re-materialized on a *post-remediation* bundle before MVP scope is frozen (mirrors the OCR freeze's own unmet "final verification run" condition).

### BS9 — Gate-result provenance/versioning has no contract.
The `.kb.json` sidecar carries a workbook fingerprint; the gate report carries the same fingerprint — but there is **no persisted binding** (a gate sidecar) that ties a gate verdict to a specific bundle fingerprint **and** gate-logic version. Undefined: does FVE consume a persisted gate result or recompute at query time? If it recomputes, gate-logic version + bundle fingerprint must both appear in every ValidationEvidence record, or two FVE runs on the same bundle could disagree after a gate-logic change. This contract must exist before evidence/provenance models are implemented.

### BS10 — The gate is Lucky-overfit and unproven on a second issuer.
The selection policies embed "Lucky-specific observed failure" cases (design §9: revenue page-320 notes, OCF page-162 balance-sheet lineage, total_assets page-323). Everything — scale audit, gate report, root-cause — is Lucky-only. Millat has different sheets (Remuneration, Pattern of Shareholding, Debt Schedule per the OCR freeze) and 66.7% review burden. **The gate's metric-specific source-precedence tables may not generalize**, and a gate that misclassifies on issuer #2 is worse than no gate (false confidence). A Millat gate run is a prerequisite for treating the gate as a general data contract, not a Lucky tool.

### BS11 — There is no integrity gate for the forecast *input* side.
The whole integrity effort hardens the **historical** baseline. But FVE also ingests **submitted forecast values** (architecture §10 `ForecastSeriesService`). No equivalent gate/contract is specified for forecast inputs — scale, unit, metric-alignment, and statement-scope checks on user-submitted forecasts are mentioned but not given the same deterministic gate treatment. The forecast-side data contract is now materially weaker than the history side, which is the opposite of where the risk concentrates (a wrong-scale forecast input is just as corrupting as a wrong-scale history).

---

## 4. Sequencing Verdict (classification)

**Must Resolve Before Implementation Begins**
- **BS1** — Re-scope FVE MVP to what the gate can admit (effectively revenue-growth at warning confidence today). Do not build categories whose required metrics are structurally blocked/missing.
- **BS2** — Decide the canonical source of truth for "selected value": Query Engine retrieval vs gate `HeadlineMetricSelectionPolicy`. One owner.
- **BS3** — Define the citation contract for gate-overridden values (which have no `WorkbookCellMapping`).
- **BS4** — Define how gate confidence composes with `ValidationConfidenceService` confidence.
- **BS6** — Explicitly remove Balance-Sheet-identity and Debt-consistency from MVP scope until exact canonical metrics exist.
- **BS7** — Validate the gate itself against an analyst-confirmed truth set for P0 metrics before trusting it as the admission contract.

**Can Be Handled During Implementation**
- **BS9** — Gate-result provenance/versioning binding (gate sidecar + version stamped in evidence).
- **BS11** — Forecast-input integrity contract (mirror the history gate for submitted forecasts).
- **clean_with_warning cross-metric matrix** — behavior when one required metric is `clean_with_warning` and another is blocked/missing (the unavoidable EPS+PAT case); definable as rules land.

**Post-MVP**
- **BS5** — Multi-`source_report_year` gate semantics (restatement vs corruption, cross-report dedup); not exercisable until multi-filing bundles exist.
- **BS10** — Second-issuer (Millat) gate generalization — required before *broad* rollout, can run alongside early single-issuer MVP work.
- **BS8** — Re-materialize gate output on a post-remediation bundle before *freezing* MVP scope (gating the freeze, not the start, since no remediation has run yet).

---

## 5. One-Paragraph Verdict

The `HistoricalSeriesIntegrityGate` is the right component, correctly built, and it has done its job: it makes the data's unfitness explicit instead of letting it flow silently into forecasts. But its success exposes the real pre-implementation problem — **the FVE MVP as scoped cannot run on the data the gate will admit.** Best-case remediation yields zero `clean` metrics and at most four `clean_with_warning`, which leaves exactly one of seven MVP categories executable. Before implementation begins, the team must (1) re-scope the MVP to the gate's actual admission set, (2) resolve the now-doubled source-of-truth and citation contracts created by the gate's override capability, (3) reconcile the two confidence scales, and (4) validate the gate against analyst truth before trusting it as the admission gate. The architecture's instincts remain sound; the blind spots are all in the *contracts and sequencing between* the gate, the Query Engine, and the forecast rules — none require a refactor, only decisions made before code, not during it.
