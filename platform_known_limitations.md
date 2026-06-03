# Platform Known Limitations

**Status:** Release-facing known-limitations catalogue for the integrated platform (OCR · MSIL · Query · QAE · FVE). Ships with the freeze.
**Date:** 2026-06-03
**Companion to:** `platform_freeze_readiness_review.md` (recommendation: READY_WITH_LIMITATIONS).
**Freeze scope statement:** *An analyst-review-grade, single-issuer-validated, official-source-ready, deterministic integrated platform whose outputs are evidence-and-provenance-bound but **not autonomously certified for correctness**, and whose high-risk sources (analyst/sector/market/news) and real-source-volume validation are deferred.*

Severity legend: **Blocking** (must close before freeze) · **Material** (real; accepted under the freeze scope; must be respected by consumers) · **Bounded** (minor/edge; manage operationally).

---

## 0. How to Read This

The platform is built on five invariants; every limitation below is a known boundary of one of them, **disclosed rather than hidden**:
1. Resolve identity before trusting evidence.
2. Gate numbers before believing them.
3. Snapshot provenance before citing it.
4. Surface divergence without resolving it.
5. Coverage ≠ correctness; source abundance ≠ source authority.

The platform is **analyst-review-grade with a respected gate** — not autonomous truth. Consumers must treat every output as evidence-backed and gated, never as certified fact.

---

## 1. Platform-Wide / Cross-Cutting

| ID | Limitation | Severity | Consumer guidance |
|---|---|---|---|
| **PL-1** | **Entity registry is analyst-unconfirmed (MB-1).** Resolution validated against a closed-loop, co-authored truth set; `[CONFIRM]` facts (tickers, registration numbers, listed status) not externally signed off. A wrong real-world fact would mis-bind evidence across all engines, invisibly. | **Blocking** | Do not rely on cross-source attribution until the registry is analyst-signed-off. |
| **PL-2** | **No platform-wide correctness truth set.** Coverage, provenance, and gating are validated; *correctness* of extracted values, classifications, and resolutions is not. The platform is coverage-honest, not accuracy-certified. | Material | Treat outputs as analyst-review-grade; verify material conclusions against source. |
| **PL-3** | **Single-issuer-deep / two-issuer-broad validation.** Real-bundle validation is Lucky (cement); generalization shown on Millat (tractors). No non-manufacturer (bank/power/textile) validated. | Material | Expect degraded behavior on unvalidated sectors; revalidate before trusting new issuer classes. |
| **PL-4** | **Limited real-source volume.** Only the OCR annual report is real at volume; the official triad (PSX/SECP/payouts) is fixture-proven, not run on real feeds at scale. | Material | "Official-source-ready" means contract-ready, not volume-proven; first real feeds need a smoke pass. |
| **PL-5** | **High-risk sources deferred.** Analyst, sector, market, futures, and news adapters are not built; their authority-inversion, forecast-context, and circularity defenses are designed but **unexercised**. | Bounded (deferred by design) | No analyst/news/market evidence exists in the platform yet; absence is not coverage. |
| **PL-6** | **Dual evidence path (maintainability).** OCR feeds engines both directly and via MSIL; a permanent dual path risks divergent evidence models. | Bounded | Post-freeze: converge OCR onto MSIL as the single evidence layer. |
| **PL-7** | **Determinism depends on pinned inputs.** Upstream OCR/LLM extraction varies run-to-run; reproducibility requires pinned bundle fingerprints. | Bounded | Pin fingerprints for any reproducible/audited run. |

---

## 2. OCR Engine

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| OCR-1 | **High review-gated rate** — a large share of consolidated values carry review flags; not autonomously trustworthy. | Material | Respect review flags; do not treat unreviewed values as final. |
| OCR-2 | **Pre-integrity-gate scale corruption** exists in raw consolidated values (the reason HSIG exists). | Material | Never consume raw consolidated values for math without HSIG. |
| OCR-3 | **OpenAI extraction variability** changes insight/classification counts run-to-run. | Bounded | Pin runs; expect count drift across extractions. |
| OCR-4 | **Zero-confidence insights** propagate into downstream confidence (e.g. QAE). | Material | Confidence is bounded by upstream insight quality. |

---

## 3. MSIL (Evidence Layer)

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| MSIL-1 | **Entity sign-off open (= PL-1).** | **Blocking** | See PL-1. |
| MSIL-2 | **Divergence policy (MB-4).** Reference-only coarse-subject numerics produced 120 false `fact_vs_fact` divergences on the real bundle; contained for FVE (excluded before reaching it), must be confirmed excluded at the Query/MSIL boundary. | Blocking-until-confirmed | Do not surface reference-only numeric divergences as conflicts; require precise same-fact keys. |
| MSIL-3 | **Corroboration/divergence proven on tiny fixtures + one real single-source run.** Cross-source edge density (multi-party divergence, chained supersession) untested. | Material | Treat multi-source corroboration/divergence as mechanism-proven, not volume-proven. |
| MSIL-4 | **News-circularity defense untested at scale.** Lineage mechanism built; news (the circularity-prone source) deferred. | Bounded (deferred) | Re-validate lineage before onboarding news. |
| MSIL-5 | **`source_lineage` dedup looseness** (duplicated lineage entries observed). | Bounded | Cosmetic now; tighten before news scale. |

---

## 4. Query Engine

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| Q-1 | **Surfaces divergence, never resolves it.** A divergent fact is presented with both sides, not adjudicated. | Material (by design) | Consumers must interpret divergent answers; the platform will not pick a side. |
| Q-2 | **Citation honesty depends on MSIL provenance.** Non-OCR citations are only as reproducible as their snapshots. | Bounded | Trust citations to provenance precision (page/date/ref), not finer. |
| Q-3 | **Authority is displayed, not adjudicated.** An answer carries its evidence's authority; Query does not rank truth. | Material (by design) | Read the authority label; "per analyst" ≠ "per audited statement." |

---

## 5. Qualitative Analysis Engine (QAE)

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| QAE-1 | **Keyword-tier classification dominance (~80–84%).** Most theme classification rides the weakest matching tier; correctness unvalidated. | Material | Themes are coverage-honest, not correctness-certified; multi-source amplifies, not resolves, this. |
| QAE-2 | **Coverage ≠ correctness.** High mapped-coverage can coexist with misclassification; the scorecard reports coverage, not accuracy. | Material | Read coverage as "what was analyzable," never as "what is correct." |
| QAE-3 | **Single-report temporal scope.** Year-over-year / recurring-across-reports is deferred (needs multi-report data). | Bounded (deferred) | No cross-report narrative-change claims yet. |
| QAE-4 | **Governance/ESG starvation.** Boilerplate filtering can leave these categories thin → `SKIPPED`, not "no issue." | Material | A skipped category is a coverage gap, never an all-clear. |

---

## 6. Forecast Validation Engine (FVE)

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| FVE-1 | **Baseline admission is narrow (by design).** Only audited + HSIG-passed values are baseline; on current data most series are review-gated/blocked (e.g. only EPS clean-with-warning on Lucky). | Material | Most metrics are not autonomously validatable; respect SKIPPED/blocked. |
| FVE-2 | **Baseline delegation not implemented.** Baseline flows via the existing OCR→HSIG path; NAG-delegated baseline (non-OCR numbers becoming baseline) is not built. | Bounded (not a gap) | External numbers are supporting/event/context only — never baseline today. |
| FVE-3 | **Forecast-context / plausibility largely forward.** Plausibility rules and analyst/guidance forecast-context are mostly post-MVP; only guidance (via PSX) is near-term. | Bounded (deferred) | Forecast plausibility is not yet a live capability at scale. |
| FVE-4 | **Divergence/conflict surfaced, never resolved.** Conflicting numbers (e.g. payout 15 vs 10) are flagged for review, not adjudicated. | Material (by design) | A flagged numeric conflict requires analyst resolution. |
| FVE-5 | **Correctness not certified.** HSIG ensures integrity (no corrupt baseline), not accuracy (no truth set). | Material | Validated ≠ correct; HSIG prevents bad baselines, it does not certify good ones. |

---

## 7. Acceptance Summary

- **Blocking (must close before platform freeze):** PL-1 / MSIL-1 (entity sign-off); MSIL-2 (MB-4 confirmation at Query/MSIL).
- **Material (accepted under the freeze scope; consumers must respect):** PL-2/3/4, OCR-1/2/4, MSIL-3, Q-1/3, QAE-1/2/4, FVE-1/4/5.
- **Bounded (manage operationally / post-freeze):** PL-5/6/7, OCR-3, MSIL-4/5, Q-2, QAE-3, FVE-2/3.

Once the two Blocking items close, the remaining limitations are **acceptable for a READY_WITH_LIMITATIONS freeze** provided the freeze scope statement (top of this document) is published with the platform and respected by every consumer.

---

## 8. One-Line Posture

**The platform is honest about what it does not know:** it resolves identity (pending sign-off), gates numbers, snapshots provenance, surfaces divergence, and reports coverage — but it certifies no correctness, validates one issuer deeply and one broadly, and defers its highest-risk sources. Use it as an analyst-review-grade, gated, evidence-bound system — never as autonomous truth.
