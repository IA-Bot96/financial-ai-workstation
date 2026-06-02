# QAE Pre-Millat Review — Real-Bundle Execution (Lucky Cement)

**Status:** Review of QAE MVP real-bundle execution against the five frozen contracts. No code, no architecture changes. Focus: architecture fidelity, generalization risk, freeze readiness.
**Date:** 2026-06-02
**Bundle:** `lucky_full_ocr_after_regression_fixes_...133227...kb.json` (fingerprint `97c3123a…`), taxonomy `1.0.0`, authority-matrix `1.0.0`.
**Evidence:** `qae_mapping_audit`, `qae_signal_generation_audit`, `qae_coverage_gate_audit`, `qae_theme_assembly_audit`, `qae_scorecard_audit`, `qae_real_bundle_smoke_audit`.

---

## 0. Execution Snapshot

| Metric | Value |
|---|---|
| Insights → signals | 244 → 244 |
| Mapped / unmapped | 220 / 24 (**9.8%** run-wide) |
| **Mapping method** | **keyword 206 (84%)**, alias 11, exact 3, unmapped 24 |
| **Section-theme conflict** | **84 / 244 (34%)** |
| Signal confidence | **73 @ 0.0**, 162 @ 0.5–0.7, 9 ≥0.7 |
| Review routing | 190 accepted, 52 rejected_low_confidence, 2 review |
| claim_type | forward_expectation 125, audited_fact 116, regulatory_compliance 3 |
| Categories | 4 `ANALYZED` (business_risk, esg, governance, strategy) · 2 `ANALYZED_WITH_WARNING` (operational_risk, outlook) · **0 SKIPPED** |
| Themes created | 24 of 27; duplicates removed 21; divergences 8 (all narrative-vs-narrative) |
| Confidence vs materiality | confidence skewed **low** (18 themes @ 0.5–0.7); materiality skewed **high** (18 themes ≥0.7) |
| Run status | `ANALYZED_WITH_COVERAGE` (coverage-framed; **no fused score**) |

**Headline:** the engine executed end-to-end with **high structural fidelity** to the contracts. But the run is carried by the **weakest classification mechanism** (84% keyword-tier) with a **34% section-theme conflict rate**, and its classification *correctness* is unvalidated. Coverage looks healthy; reliability beneath it is unproven.

---

## 1. Architecture Fidelity (Task 1) — HIGH

The contracts were faithfully implemented:
- **Gate-first, deterministic, version-pinned.** Every signal/theme carries taxonomy + authority-matrix versions + workbook fingerprint.
- **Text-independent `signal_id`** (`qae:v1_0_0:lucky_cement:annual_report:2025:p10:ceo_review:outlook:2025:i15`) — exactly the signal-contract HR-2 mitigation; ids derive from provenance, not claim text.
- **One signal → one theme; provenance-keyed dedup** (21 removed); primary-category ownership held.
- **Three axes reported separately, no fused score**, `run_status` coverage-framed (`ANALYZED_WITH_COVERAGE`) — the Forecast-Validation 70/warning coverage-illusion is structurally avoided.
- **Confidence ceiling firing with explicit reason** (`keyword_or_review_confidence_ceiling`) — honest about why confidence is capped.
- **Low-confidence / high-materiality separation working** (themes are mostly 0.5–0.7 confidence but 0.7–0.9+ materiality) — the designed independence of the two axes held.
- **PDF_PAGE provenance + unmapped queue surfaced**; SKIPPED-accounting machinery present.

**Two fidelity deviations from the plan's assumptions (not defects, but notable):**
- Divergence was assumed **inert on single-source**; it fired **8 narrative-vs-narrative** divergences — the single annual report contains genuine internal tension. Exercised, not inert (good — but unvalidated, §4).
- The **FVE handoff payload** is not evidenced in the smoke audit (no `cross_engine_candidates`, no `narrative_only` export shown). Untested at MVP.

---

## 2. Hidden Assumptions Exposed by Real Execution (Task 2)

- **HA-1 — "Section is the reliable axis, area only the precision layer" is weaker than designed.** 84% of signals matched via **keyword tier** (only 14 via exact+alias), and the section prior **disagreed with the theme mapping 34% of the time**. The taxonomy's central reliability premise is carried by its weakest mechanism.
- **HA-2 — Governance/ESG were assumed boilerplate-starved (HD6); the opposite occurred.** Governance 97.7% mapped (44 signals), ESG 96%. But the conflict samples show governance volume is fed by **keyword cross-section matches** ("Robust risk management and governance" from *Outlook* → `board_oversight`; "Governance & regulatory compliance" from *Business Review* → `compliance_ethics`). Not starvation — likely **inflation**.
- **HA-3 — Single-source ≠ no divergence.** 8 within-document divergences fired; intra-report narrative tension is real and is being exercised.
- **HA-4 — QAE inherits OCR's confidence problems directly.** 73 signals at 0.0 signal-confidence exceeds the 24 unmapped → ~49 are floored by **zero upstream extraction confidence** (the OCR final report logged 43 insights at 0.0 confidence). QAE confidence is only as good as the insight confidence it consumes.
- **HA-5 — Authority hinges on a shaky derived `claim_type`.** 125/244 (51%) derived as `forward_expectation` from `source_section` — but with 34% section conflict, the section signal that drives `claim_type` (and thus authority weighting) is itself ambiguous half the time.

---

## 3. Taxonomy Risks (Task 3)

- **TX-1 — Keyword-tier dominance (84%) is the top taxonomy risk.** The exact/alias seed is too thin; classification rides broad keywords, which both causes the 34% conflict and is exactly what will **not transfer** to a different issuer's vocabulary.
- **TX-2 — 34% section-theme conflict, concentrated in integrated-reporting language.** Modern reports deliberately fuse ESG/strategy/risk/finance ("Access to capital via ESG performance", "Margin drivers through energy efficiency", "Sustainability-driven cost efficiencies"); the category boundaries don't cleanly partition this, and the area→theme mapper routes it inconsistently vs the section prior.
- **TX-3 — Outlook is the weakest category** (63.6% mapped, **36.4% unmapped**): composite/vague area labels ("Outlook / sustainable growth", "Manufacturing capacity and market position", "Thar coal outlook") don't match outlook theme aliases.
- **TX-4 — Granularity collapse on several themes** (demand_outlook, ownership_related_party dropped; health_safety, production_plant_reliability, macro_regulatory_outlook, margin_pricing_outlook each =1) — single-signal/zero themes, salience near-degenerate (taxonomy TR4 confirmed).
- **TX-5 — "energy" collision leakage toward `energy_transition` (16) vs `input_cost_energy` (7).** Conflict samples show energy-in-a-*risk*-context routed to ESG (`energy_transition`), suggesting the disambiguation aliases under-protect the cost/risk side.

---

## 4. Theme-Assembly Risks (Task 4)

- **TA-1 — Materiality may be uniformly high.** Materiality skews 0.7–0.9+ across most of 24 themes; if nearly everything is "material," materiality loses discriminating power. The axis separation is faithful, but the materiality *scale* needs calibration evidence.
- **TA-2 — Divergence false-positive risk (unvalidated).** 8 narrative-vs-narrative divergences on a single promotional document — these could be genuine management-vs-risk tension or **artifacts of keyword-tier mis-grouping** (two oppositely-toned signals in one theme because one was mis-mapped). Unverifiable without a truth set.
- **TA-3 — Single-signal themes asserted on one keyword-tier signal** (health_safety, production_plant_reliability) — `low_salience` labeling must be confirmed to actually gate these from over-presentation.
- **TA-4 — Dedup verified (21 removed) but only within one source.** The **dedup-vs-corroboration boundary** — the contract's sharpest assembly rule — is **untested** (no cross-source data).
- **TA-5 — Corroboration logic unexercised.** All 244 signals are `audited_issuer`; independent-origin corroboration never ran on real data. It remains scaffolding, as planned.

---

## 5. Scorecard Risks (Task 5)

- **SC-1 — "6/6 analyzable, 0 skipped" over-represents reliability.** The breadth is real at the mapping level but rests on 84% keyword-tier classification; the scorecard honestly reports unmapped rates + ceiling reasons, yet the top-line breadth can read as more trustworthy than the underlying classification is.
- **SC-2 — Mapped-coverage % measures match success, not correctness.** Governance at 97.7% "coverage" may be substantively cross-contaminated (HA-2). Without a truth set, high coverage can co-exist with mis-classification — the scorecard cannot detect this by construction.
- **SC-3 — Anti-illusion design held (the FVE lesson worked).** Confidence as a distribution + ceiling reason, materiality ranked separately, coverage-framed run status, no fused score. This is a genuine success vs the Forecast-Validation precedent.
- **SC-4 — `operational_risk` warned at 0% unmapped** — warning correctly driven by low-salience/single-signal themes rather than unmapped rate; good that the warning fired, but the warning reason should be explicit in the output.

---

## 6. Coverage-Illusion Risks (Task 6)

- **CI-1 (the deepest) — A classification-correctness illusion, distinct from the volume illusion the scorecard correctly avoids.** Run-wide 90% mapped-coverage answers "did the area string match a theme," not "is the theme right." With 84% keyword-tier + 34% section conflict, **high coverage can mask substantial mis-classification.** The scorecard says *analyzable*; a consumer may read *correct*.
- **CI-2 — Governance/ESG richness may be keyword-inflated** (HA-2): "we analyzed governance thoroughly" when much of the volume is strategy/opportunity text containing the words "governance/compliance."
- **CI-3 — 73 zero-confidence signals in the pipeline**; any that reach accepted themes mean themes partly rest on zero-trust evidence that still counts toward coverage.
- **CI-4 — The structural guards worked; the residual illusion is correctness**, which only an analyst truth set resolves.

---

## 7. Overfitting Risks (Task 7)

- **OF-1 — Entire validation is one cement issuer.** The keyword aliases that carried 84% of classification (coal, energy, capacity, exports, WHR/renewable) are **cement-shaped**.
- **OF-2 — ESG/`energy_transition` richness (16) is a carbon-heavy-manufacturer artifact.** Millat (tractors) lacks WHR/solar narrative → `energy_transition`/`emissions_environment` will likely collapse, swinging ESG coverage.
- **OF-3 — Section prior + `claim_type` derivation are tuned to Lucky's section set** (CEO Review, Opportunities, Outlook, Sustainability). Millat has **Chairman Review** (not CEO) and a different section mix → conflict and unmapped rates will likely rise for structural reasons.
- **OF-4 — Strategy richness (capacity_expansion 19) reflects Lucky's expansion phase**, not just sector — a mature issuer would yield far fewer strategy signals. Coverage is issuer-*state*-dependent.

---

## 8. Blockers Before Millat Validation (Task 8)

- **B-1 — No correctness baseline.** With classification unvalidated on Lucky, a Millat run would produce coverage numbers no one can grade. A **small analyst spot-check** on Lucky's 84 section-conflicts + the governance-inflation sample is needed so Millat results are interpretable as generalization rather than noise.
- **B-2 — Millat section labels must be confirmed in the frozen section→category map.** Chairman Review and Millat's section mix must resolve to category priors, or Millat under-covers for a **trivial config reason** mistaken for a generalization failure.
- **B-3 — Interpretation gate:** the Millat audit must report **classification-quality caveats**, not just coverage %, or it will produce a misleading "it generalizes."
- **B-4 — Divergence interpretation:** decide whether Lucky's 8 divergences are validated as real before trusting Millat divergences (same mechanism, same uncertainty).

---

## 9. Findings Classification (Task 9)

**Must Resolve Before Millat Pass**
- B-2: confirm Millat section names are covered by the frozen section→category map (config/data check).
- B-1: minimal analyst correctness spot-check on Lucky (section-conflicts + governance inflation) to create an interpretation baseline.
- B-3: Millat audit must report classification-quality caveats alongside coverage % (reporting gate).

**Should Resolve Before Freeze**
- TX-1: expand exact/alias seed to reduce 84% keyword-tier reliance.
- TX-2 / HA-1: document a disposition for the 34% section-theme conflict (boundary refinement or accepted-and-explained).
- HA-2 / CI-2: validate governance/ESG are genuine, not keyword-inflated.
- TA-1: calibrate materiality so it discriminates (not uniformly high).
- TA-2: validate divergences are real, not mis-grouping artifacts.
- TX-3: strengthen outlook aliases (36% unmapped).
- HA-4 / CI-3: define handling of zero-confidence signals reaching themes.

**Post-Freeze**
- TA-4 / TA-5: real validation of dedup-vs-corroboration and corroboration logic (needs multi-source).
- FVE handoff exercise incl. quantified-claim routing (needs FVE integration).
- Non-manufacturing issuer (bank/power) generalization (OF-1).
- Sub-theme granularity tuning (TX-4).

---

## 10. Is QAE Ready for Millat Generalization Testing? (Task 10)

**Yes — ready to *run* Millat, conditioned on B-1, B-2, B-3 — but framed as a generalization *stress test*, not a correctness validation.**

The engine executed end-to-end with high architecture fidelity and honest, coverage-first reporting, so it **can** run Millat today. But the dominant finding — **84% keyword-tier classification with 34% section conflict and no correctness baseline** — means an unconditioned Millat run would yield coverage deltas that cannot be told apart from misclassification. Therefore:

- **Proceed to Millat** explicitly to measure **unmapped-rate and section-handling deltas** vs Lucky (the generalization signal the plan intended at P8).
- **Resolve B-1/B-2/B-3 first** so those deltas are interpretable.
- **Gate the freeze — not the Millat run — on the keyword-tier (TX-1) and section-conflict (TX-2) findings**, plus the truth-set validation that is still the platform-wide open assurance gap.

The MVP did what it was designed to do: run deterministically, report coverage honestly, and refuse to fabricate. What it has **not** yet shown is that its classifications are *correct* — and Millat is the right next step precisely to pressure that question, provided it is run as a stress test with a correctness baseline rather than as a victory lap.
