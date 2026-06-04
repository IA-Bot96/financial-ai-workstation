# OCR V2 — Shadow Validation Review

**Status:** Audit only. No implementation. Findings read directly from the shadow artifacts.
**Date:** 2026-06-04
**Read:** `ocr_v2_shadow_history.json` · `ocr_v2_shadow_dashboard.json` · `ocr_v2_shadow_trend_report.md`.

---

## 0. Headline

The shadow **harness works** (it ran both engines, compared, and emitted history/dashboard/trend). But the **evidence is non-representative**: the entire corpus is **2 synthetic smoke-test documents**, run in a single burst, with microsecond runtimes — **no real annual report (not Lucky, not Millat, not a live filing) has been shadow-processed.** No production-relevant conclusion can be drawn.

**Corpus (verbatim from history):**
| document_id | year | V1 rows / metrics | V2 rows / metrics | V2 source_insufficient | status |
|---|---|---|---|---|---|
| `Shadow Aggregate Smoke A …shadow_smoke_a.pdf` | 2025 | 2 / 0 | 2 / 2 | 0 | **diverged** |
| `Shadow Aggregate Smoke B …shadow_smoke_b.pdf` | 2024 | 3 / 0 | 1 / 0 | 1 | **diverged** |

Total documents = **2**; shadow runs = **2**; both `diverged_counts`. Runtimes: V1 avg `5.8e-05s`, V2 avg `1e-05s` — **microseconds**, i.e. fixture overhead, not OCR.

---

## 1. V1 vs V2 Runtime — NON-INFORMATIVE

V2/V1 ratio `0.172` ("V2 faster") is meaningless: both runtimes are tens of microseconds, impossible for real OCR (table detection + extraction + model calls run in seconds–minutes). These are **stub timings on smoke fixtures**. Real V2 performance is **unmeasured**.

## 2. Completeness — SPLIT, NOT A TREND

V2 more complete: **1** (Smoke A: 2 metrics vs V1's 0). V2 less complete: **1** (Smoke B: 1 row vs V1's 3). One-for-one on two synthetic docs is **noise, not a trend** — and the "more/less complete" counts are over fixture rows with no truth reference.

## 3. Source-Insufficient Behavior — UNVERIFIABLE

V2 emitted **1** source_insufficient (Smoke B); V1 emitted 0. With **no truth set for the smoke fixtures**, it is impossible to say whether that abstention was correct (honest) or a missed value (regression). Uninterpretable.

## 4. Workbook Differences — DIVERGED ON BOTH, UNATTRIBUTABLE

Both runs diverged on counts (A: same row count, different metric counts; B: 3 vs 1 rows). Real divergence exists, but with synthetic inputs and no ground truth it **cannot be attributed** to a V2 defect or a V1 quirk.

## 5. Error Rate — CLEAN BUT TRIVIAL

V1 errors 0, V2 errors 0, runs-with-errors 0 — across **2 trivial documents**. No operational stress; no meaningful error-rate signal.

## 6. Recurring Divergence Patterns — 100% DIVERGENCE (unexplained)

**Every shadow run diverged (2/2).** A 100% count-divergence rate is itself a pattern that must be root-caused — but on smoke fixtures it cannot be diagnosed. If this pattern persists on real documents it would signal a systematic V1↔V2 completeness mismatch; on this corpus it is simply unexplained.

## 7. Candidate Coverage Trends — NO TREND ESTABLISHABLE

Two data points do not constitute a trend. Candidate coverage over real filings is **unobserved**.

---

## Determinations

| Question | Answer | Basis |
|---|---|---|
| Is V2 consistently more complete? | **No** | 1 more / 1 less complete; one case V2 was *less* complete |
| Is V2 introducing regressions? | **Unknown / cannot rule out** | Smoke B shows V2 less complete + an unverified abstention; no truth/real doc to confirm or clear |
| Is V2 operationally stable? | **Not established** | 2 synthetic runs, 0 errors — no real-document operational evidence |
| Is performance a blocker? | **Cannot determine** | microsecond stub runtimes are not real OCR performance; performance is unvalidated, not "cleared" |

---

## Final Determination

# NOT_READY_FOR_P-I6_SHADOW_EXPANSION

**Evidence.** The shadow corpus is **2 synthetic smoke documents** (`shadow_smoke_a.pdf`, `shadow_smoke_b.pdf`), executed in one burst, with microsecond runtimes and no truth reference — this validates that the **shadow harness functions**, not that **V2 behaves correctly on real documents**. Across this corpus: **100% of runs diverged**, V2 was **less complete in half** of them, an **unverifiable source-insufficient** appeared, and **no real annual report has ever been shadow-processed**. None of the four advancement questions (consistently-more-complete, no-regressions, operationally-stable, performance-not-a-blocker) can be answered affirmatively. Advancing to P-I6 on this evidence would be advancing blind.

**To become ready, P-I4 shadow must accumulate real-PDF evidence:** run the shadow harness over **real production filings (Lucky, Millat, and a broader live corpus)**, against truth where available, and demonstrate across that corpus a **non-diverging or fully-explained** comparison — `V2-regresses = ∅`, no fabrication-on-source-insufficient, and realistic (seconds-scale) V2 runtimes within an acceptable band.

---

## Largest Remaining Risk Before Production Cutover

**V2's behavior on real production documents is entirely unobserved.** The shadow phase — the mechanism specifically built to surface real-world divergence, regression, completeness, and performance before cutover — has so far seen **only synthetic stubs**. Compounding this, **every run it has seen diverged**, so the one signal it did produce (a 100% count-divergence rate) is unexplained. Until the shadow harness runs on real filings and either eliminates or fully root-causes that divergence, cutting production over to V2 would be a cutover with no real-input evidence behind it — strictly worse than the staged-table validation, which at least ran on the real Lucky PDF tables. This risk sits *on top of* the still-open freeze blocker (Millat over-fit retirement), and is the single most important thing to close before P-I6.

---

## One-Paragraph Verdict

The shadow infrastructure is alive and correctly instrumented — it ran both engines, compared their outputs, and produced history, dashboard, and trend artifacts — but the evidence it has gathered is non-representative to the point of being unusable for an advancement decision: the entire corpus is two synthetic smoke documents (`shadow_smoke_a/b.pdf`) executed in a single burst with microsecond runtimes and no ground truth, on which every run diverged, V2 was more complete once and less complete once, and a single source-insufficient abstention can be neither confirmed nor faulted. Nothing here establishes that V2 is consistently more complete, free of regressions, operationally stable, or performant, because none of those properties can be read off two stub fixtures. The determination is therefore **NOT_READY_FOR_P-I6_SHADOW_EXPANSION**, and the largest remaining risk before any production cutover is precisely the gap this audit exposes: V2 has never been shadow-run on a real production filing, so its real-world behavior — and the meaning of the 100% divergence the harness has so far recorded — remains entirely unobserved, a gap that must be closed with a real-PDF shadow corpus (Lucky, Millat, and live filings) before P-I6 can be considered.
