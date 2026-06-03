# QAE MVP Freeze Readiness Review — Post-Millat

**Status:** Freeze-readiness review across two issuers (Lucky, Millat) against the five frozen contracts. No code, no architecture changes. Focus: freeze readiness and accepted limitations.
**Date:** 2026-06-02
**Evidence:** six Lucky audits + `qae_millat_generalization_audit`, `qae_phase8_report`, `qae_pre_millat_review`. Taxonomy `1.0.0`, engine frozen (`constraints_observed`: all false), 68/68 tests passing.

---

## 0. Lucky vs Millat Snapshot

| Metric | Lucky | Millat | Read |
|---|---|---|---|
| Insights → signals | 244 | 60 | Millat much lower volume |
| Mapped coverage | 90.2% | 86.7% | held (−3.5 pts) |
| Unmapped rate | 9.8% | 13.3% | mild degradation |
| **Keyword-tier** | **84.4%** | **81.7%** | **dependence confirmed cross-issuer** |
| Exact + alias | 5.7% | **5.0%** | seed too thin on both |
| Section conflict | 34.4% | 21.7% | lower (fewer ESG-financial cross-cuts) |
| Zero-confidence signals | 73/244 (30%) | 25/60 (**42%**) | OCR-confidence inheritance worse on Millat |
| Themes created | 24 | 14 | volume-driven |
| Divergences | 8 | **0** | wildly issuer-variable |
| Categories | 4 ANALYZED / 2 WARNING / 0 SKIPPED | 1 ANALYZED / 4 WARNING / **1 SKIPPED (outlook)** | honest degradation |
| Run status | `ANALYZED_WITH_COVERAGE` | **`PARTIAL_COVERAGE`** | scorecard told the truth |

**Headline:** the frozen engine generalized **executably** to a second issuer and — critically — **reported its own degradation honestly** (PARTIAL_COVERAGE, outlook SKIPPED, four WARNINGs, ceiling reasons). That is the strongest possible evidence the anti-illusion design works. What is still **not** demonstrated, now confirmed across both issuers, is **classification correctness**: ~82% keyword-tier matching with no truth set.

---

## 1. Architecture Fidelity (Task 1) — HIGH, now cross-issuer confirmed

- The engine ran on Millat **with zero changes** (`taxonomy_changes`, `theme_changes`, `admission_rule_changes`, `scorecard_changes`, `architecture_changes` all false) — a true frozen generalization test, deterministic, 68/68 tests.
- Version pins, text-independent `signal_id`s, provenance-keyed dedup, one-signal-one-theme, three-axis separation, **no fused score**, coverage-framed `run_status` — all held on both issuers.
- **Section alias map generalized:** every *actual* Millat section (Chairman Review, CEO Review, Business Review, Financial Review, Opportunities, Risks, Strategy, Sustainability) routed at `route_confidence 0.9`. Chairman Review correctly carried governance (where Lucky used Directors Report). The pre-Millat blocker B-2 is **resolved** — the "unrecognized" labels (Director Report, Governance, Risk) were probe variants **not present** in Millat, not real gaps.
- Confidence ceilings fired with correct, issuer-specific reasons: `elevated_unmapped_rate` (Millat business_risk), `no_eligible_signals` (Millat outlook).

Fidelity is the standout strength of the program.

---

## 2. Taxonomy Readiness (Task 2) — EXECUTABLY READY, NOT CORRECTNESS-PROVEN

- **Executable transfer: yes.** Categories and themes mapped both issuers without modification; mapped coverage held at 86.7% on Millat.
- **Keyword-tier dominance is structural, not Lucky-specific** (84% → 82%); exact+alias is ~5% on both. The vocabulary classifies by broad keyword guessing on every issuer seen so far.
- **Outlook is a confirmed taxonomy gap:** weakest on Lucky (36% unmapped) and **fully SKIPPED on Millat** (`SKIPPED_NO_ELIGIBLE_SIGNALS`, both outlook signals unmapped). Outlook theme/alias coverage is inadequate.
- **Financial/numeric narrative leaks to unmapped** ("Revenue and profitability", "Margin drivers", "Margin performance") — partly correct (these are FVE-domain numeric claims), but it also signals thin outlook/margin theme coverage.
- Verdict: v1.0.0 is a sound, generalizable **baseline vocabulary** — but its correctness is unproven and its known gaps (outlook, alias thinness) are real.

---

## 3. Generalization Readiness (Task 3) — DEMONSTRATED (executable), correctness pending

- Phase 8 classifies all four generalization dimensions as **WARNING** (category coverage, section routing, taxonomy, theme assembly) — i.e. "executes end-to-end with caveats," which is the honest outcome.
- The engine degraded gracefully and visibly on a lower-volume, different-sector issuer rather than failing or faking coverage.
- **Limits:** still only **two manufacturers**; no bank/power/non-manufacturer. Divergence collapsed 8→0, showing the divergence signal is highly issuer/volume-sensitive and unvalidated either way.
- Generalization is proven **mechanically**, not for **correctness**.

---

## 4. Scorecard Readiness (Task 4) — HIGH (the program's clearest success)

The scorecard proved itself precisely when coverage dropped: Millat returned `PARTIAL_COVERAGE`, surfaced `outlook` as `SKIPPED_NO_ELIGIBLE_SIGNALS`, flagged four WARNING categories, attached ceiling reasons, and **emitted no fused score**. The Forecast-Validation "70/warning coverage illusion" lesson is fully internalized: a sparsely-covered issuer is reported as sparsely covered. Confidence is a distribution + reasons; materiality is separate. This is freeze-ready.

---

## 5. Remaining Risks (Task 5)

- **R-1 (dominant, cross-issuer-confirmed) — Keyword-tier classification with no correctness validation.** ~82% keyword-tier on both issuers; no analyst truth set → coverage cannot certify correctness.
- **R-2 — Outlook category structurally weak** → SKIPPED on Millat. The one category that fully fails on a second issuer.
- **R-3 — Zero-confidence inheritance** from OCR (42% of Millat signals at 0.0) — QAE confidence is bounded by upstream insight quality.
- **R-4 — Divergence unvalidated and issuer-volatile** (8 vs 0). No basis yet to trust or distrust it.
- **R-5 — Two-manufacturer validation only.** Non-manufacturing generalization (bank/power) untested; sector overfit unretired.
- **R-6 — Input-artifact inconsistency.** Millat used an OCR **context** file, not a `.kb.json` sidecar (`kb_json_available: false`; fingerprint from generated-workbook bytes). Frozen runs should standardize the input artifact.
- **R-7 — No analyst truth set** — the platform-wide open assurance gap, now the single gating item for any correctness claim.

---

## 6. Findings Classification (Task 6)

**Must Resolve Before Freeze**
- **M-1 — Minimal analyst truth-set spot check.** A small, bounded sample (~30–50 classifications) spanning Lucky section-conflicts, the governance-inflation question, Millat keyword mappings, and the skipped outlook — enough to convert "unknown correctness" into "known, acceptable error rate." Without *any* correctness evidence, READY_WITH_LIMITATIONS is indistinguishable from NOT_READY. (Phase 8 itself recommends this before freeze.)
- **M-2 — Honest freeze framing.** Freeze must be explicitly scoped as **coverage-first, executable-generalization, correctness-not-certified**, with the accepted limitations (R-1…R-7) documented. The freeze must make **no classification-accuracy claim.**

**Should Resolve Before Freeze**
- **S-1 — Standardize the input artifact** (Millat `.kb.json` sidecar) so frozen runs are reproducible from a consistent source (R-6).
- **S-2 — Document divergence as surfaced-but-unvalidated** and clearly labeled in outputs (R-4).
- **S-3 — Record outlook weakness + keyword-tier + zero-confidence inheritance as named known limitations** consumers must respect (R-1/R-2/R-3).

**Post-Freeze (governed v1.1+)**
- Expand exact/alias seed to reduce keyword-tier reliance; strengthen outlook/margin themes.
- Section aliases for Director Report / Governance / Risk **only if** real issuers emit them.
- Non-manufacturing issuer generalization (bank/power).
- Multi-source corroboration/dedup validation; FVE handoff exercise; materiality calibration; sub-theme granularity.

---

## 7. Determinations (Task 7)

**Is taxonomy v1.0.0 freeze ready? — YES, as a versioned baseline (not as a correctness-certified artifact).**
Freeze it **as v1.0.0** precisely so its known gaps (outlook, alias thinness, keyword-tier reliance) become **measurable governed extensions** in v1.1. It executed on two distinct issuers without modification; locking it now gives generalization work a stable, comparable baseline. Freezing the vocabulary ≠ certifying its classifications.

**Is QAE MVP freeze ready? — YES with limitations**, conditioned on the small Must set (M-1 truth-set spot check + M-2 honest framing). The engine, scorecard, and generalization behavior are sound and — most importantly — **honest under stress**. The only thing standing between the current state and a defensible freeze is a bounded correctness baseline and explicit limitation labeling.

---

## 8. Recommendation (Task 8)

### READY_WITH_LIMITATIONS

The QAE MVP should be frozen as a **coverage-first, deterministic, evidence-grounded qualitative-understanding engine that generalizes executably across issuers and reports its own coverage honestly** — explicitly **not** as a correctness-certified classifier. Freeze is warranted because every structural guarantee held under a genuine second-issuer stress test; the limitations are known, bounded, and documentable; and the one missing piece (a minimal correctness baseline) is small and clearly scoped.

This mirrors the platform's established posture: like the OCR and Forecast-Validation freezes, QAE freezes as **analyst-review-grade with a respected gate**, not as autonomous truth.

---

## 9. Smallest Safe Remediation Set Before Freeze (Task 9)

Exactly three items — nothing more:

1. **Bounded analyst truth-set spot check (M-1).** ~30–50 classifications across Lucky conflicts, governance inflation, Millat keyword mappings, and skipped outlook. Record an accepted error rate; this converts the limitations from *unknown* to *accepted*.
2. **Freeze-framing document (M-2).** State the freeze scope (coverage-first / executable-generalization / correctness-not-certified) and list accepted limitations R-1…R-7. No accuracy claim.
3. **Input-artifact standardization (S-1).** Generate/pin a Millat `.kb.json` sidecar so the second-issuer evidence rests on the same artifact contract as Lucky.

Everything else — alias expansion, outlook strengthening, non-manufacturing validation, divergence/materiality calibration, multi-source — is **post-freeze governed improvement** and must not block the v1.0.0 freeze.

---

## 10. One-Paragraph Verdict

The Millat pass was the test the whole program was building toward, and it produced the right result for the right reasons: the frozen QAE ran end-to-end on a smaller, different-sector issuer **without a single taxonomy or engine change**, its section routing generalized, and — most importantly — its scorecard told the truth, returning `PARTIAL_COVERAGE` with `outlook` honestly `SKIPPED` rather than manufacturing coverage it did not have. That is the anti-illusion discipline this series has insisted on since the Forecast-Validation 70/warning finding, now proven under stress. The one thing two issuers also confirmed is that classification is ~82% keyword-tier and its **correctness is unproven** — so QAE is **READY_WITH_LIMITATIONS**: freeze taxonomy v1.0.0 as a versioned baseline and the MVP as a coverage-first, analyst-review-grade engine, conditioned only on a small truth-set spot check and an honest freeze-framing that makes no accuracy claim. Lock it now to make every future generalization gain measurable, and push alias expansion, outlook strengthening, and non-manufacturing validation into governed v1.1 — never letting coverage be mistaken for correctness.
