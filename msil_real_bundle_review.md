# MSIL Real-Bundle Review — Lucky Bundle Execution

**Status:** Review of the MSIL substrate run on the real Lucky bundle. No code. Focus: real-data behavior, divergence interpretation, integration readiness.
**Date:** 2026-06-02
**Evidence:** `msil_real_bundle_smoke_audit.json`, `msil_real_bundle_validation_report.json`, `msil_pre_integration_review.md`.
**Input:** `lucky_full_ocr_after_regression_fixes_…133227….kb.json`, fingerprint `97c3123…`, `fingerprint_match: true`.

---

## 0. Result Snapshot

| Metric | Value | Read |
|---|---|---|
| Insights processed | 244 | Real bundle (vs 4-insight P3 fixture) |
| Signals generated | 363 | 244 narrative_claim + 119 numeric_claim references |
| Numeric references | 119 | reference-only (not asserted) |
| Mapping failures | **0** | clean adapter run |
| Unresolved entities | **0** | all → `lucky_cement`, `audited_issuer` ×363 |
| Provenance | 363× PDF_PAGE | full coverage, page + report ref |
| Timeline / supersession / corroboration | 0 / 0 / 0 | correct for single-source |
| **Divergences** | **120** | **all `fact_vs_fact`, all `annual_report\|annual_report`, all `audited_issuer\|audited_issuer`** |
| Validation status | WARNING | sole warning = divergence volume |

**Headline:** the real-bundle run is a **success on every dimension that MB-2 required** — source #1 absorbed the real 244-insight bundle with zero mapping failures, zero unresolved entities, full PDF_PAGE provenance, and no fixture-regression. The single WARNING (120 divergences) is **not a substrate failure; it is real data correctly exposing a divergence-*policy* issue that 2-row fixtures could never reveal.** The system's own diagnostics flagged and correctly diagnosed it.

---

## 1. Is MB-2 Closed? (Task 1) — YES

MB-2 ("run the annual-report adapter on the REAL Lucky `.kb.json` and demonstrate no-regression reconciliation") is **closed**:
- Real fingerprint `97c3123…` confirmed (`fingerprint_match: true`) — not the `fp_lucky_2025_phase3_fixture` used in P3.
- 244 insights → 363 signals, **0 mapping failures, 0 unresolved entities**, 363× PDF_PAGE provenance with page number + report reference.
- Validation report `regressions: none_detected`; `authority_anomalies: none`; `provenance_anomalies: none`.
- Single-source behavior is correct: timeline/supersession/corroboration empty (no cross-source records yet), exactly as the contract predicts.

The biggest pre-integration gap from the prior review is resolved: the substrate genuinely absorbs the real annual bundle, and the adapter/provenance/authority layers behave correctly at real volume.

---

## 2. Divergence Count Analysis (Task 2)

All 120 divergences share one signature, per the validation diagnostics:
- **Type:** 120/120 `fact_vs_fact`.
- **Source pair:** 120/120 `annual_report | annual_report` (**intra-source**).
- **Authority pair:** 120/120 `audited_issuer | audited_issuer` (**same authority**).
- **Population:** all among the **119 numeric *references*** (reference-only mentions, not authoritative values).
- **Clustering:** on coarse topic "subjects" — "renewable energy capacity details" (21), "cost energy efficiency" (10), "capacity expansion renewable energy" (10), "completed capacity expansions" (6), "energy mix transition" (6), etc.

What this means: the divergence detector grouped numeric references by a **coarse topic-label subject** and pairwise-compared their values; references that share a topic bucket but describe **genuinely different numbers** (different plants/MW/years/percentages within one report) were flagged as conflicting "facts." A bucket like "renewable energy capacity details" with 21 numeric mentions is not 21 competing claims about one metric — it is 21 distinct figures about one topic. The 120 count is **pairwise noise from over-coarse subject keying**, not 120 real contradictions.

---

## 3. Defect Classification (Task 3)

**Primarily a POLICY defect** — not an implementation defect, and not (mostly) expected behavior:

- **Not an implementation defect.** The mechanism executes its spec faithfully: "two `numeric_claim`s, same subject, different value → `fact_vs_fact` divergence, surfaced, not resolved." The code did exactly what it was told; the audit even self-diagnosed the cause ("*likely intra-report numeric-reference comparison rather than cross-source divergence*"). The engine is honest and working.
- **Primarily a policy defect (two compounding policy errors):**
  1. **Reference-only numerics are wrongly eligible for `fact_vs_fact` divergence.** They were explicitly created as *non-authoritative* (`authoritative_numeric_values_created: false`); treating loose narrative numeric mentions as competing factual claims contradicts their own status.
  2. **The "subject" key is too coarse.** A topic label ("renewable energy capacity details") is not a same-fact key; divergence requires a precise `(canonical_metric, value_year)` identity before two numbers are "the same fact."
- **Contract-intent mismatch (secondary).** The Divergence model was designed for **cross-source, authority-weighted contradiction** surfaced for adjudication. Firing it **intra-source, same-authority** on reference-only numerics is outside that intent — a same-document pair of different numbers is not a "divergence" in the architectural sense.
- **A small residue may be expected behavior** — a handful could be genuine in-report numeric inconsistencies worth surfacing — but it is a minority swamped by noise; the dominant 120 are false positives.

**Verdict: policy defect (divergence-eligibility + subject-keying), localized and well-diagnosed — fixable by policy, not redesign.**

---

## 4. Remaining Blockers Before P8 (Task 4)

- **NEW — Divergence-eligibility / subject-keying policy must be fixed before consumption is wired.** Otherwise FVE would ingest 120 spurious `fact_vs_fact` divergences, flooding it with noise and destroying the trustworthiness of the divergence signal. Minimum fix: exclude reference-only numerics from `fact_vs_fact`, and/or require a precise same-fact key, and/or restrict divergence to cross-source or differing-authority pairs (the architectural intent).
- **CARRIED — MB-1 (analyst sign-off + general ambiguity rule).** Still no evidence of closure; the registry foundation remains unconfirmed.
- **CARRIED — MB-3 (FVE integrity-gate extension to non-OCR provenance).** Still open; required before FVE consumes MSIL numbers.

MB-2 is closed; MB-1 and MB-3 persist; the divergence-policy blocker is added.

---

## 5. Integration Readiness (Task 5)

Readiness now diverges sharply by engine because of where the divergence noise lands:

- **Query Engine — most ready.** It consumes the evidence store + provenance + entity index for retrieval/citation: 363 cleanly-provenanced, fully-resolved signals. The divergence noise is a display/filter concern, not a retrieval-correctness blocker. **Ready to wire.**
- **QAE — close to ready.** The narrative substrate is clean (244 narrative_claims, 0 failures, full provenance); corroboration correctly empty (single-source). QAE consumes **narrative** divergences (`narrative_vs_narrative`), of which there are **zero** here, so the numeric-divergence noise barely touches it. **Ready to wire, pending a clear contract on which divergence types QAE receives.**
- **FVE — blocked.** FVE consumes numeric claims + numeric divergences — exactly the population polluted by the 120 false `fact_vs_fact` records. **Blocked on the divergence-policy fix (new) and MB-3 (gate extension).** Numeric references are correctly reference-only, but the divergence layer over them is not yet consumable.

---

## 6. Findings Classification (Task 6)

**Must Resolve Before P8**
- **MB-4 (new) — Fix divergence eligibility + subject-keying** so reference-only numerics don't generate intra-source `fact_vs_fact` noise; align with the cross-source, authority-weighted divergence intent.
- **MB-1 (carried) — Analyst sign-off + `[CONFIRM]` resolution + general ambiguity rule** on the registry.
- **MB-3 (carried) — FVE integrity-gate extension to non-OCR provenance** before FVE wiring.

**Can Resolve During P8**
- Restrict/tune divergence to the official-triad cross-source use-case as those adapters integrate (the real divergence value).
- Per-consumer divergence filtering in the consumption feeds (e.g. QAE gets narrative-only).
- `source_lineage` dedup cleanup.
- Quarantine review-queue operational path.
- Per-source coverage reporting.

**Post-MVP**
- Numeric-reference → canonical-metric mapping (to give numerics a precise same-fact key) — deeper, touches FVE's numeric domain.
- Market/Futures/News/Analyst/Sector adapters; news-circularity at scale.
- Non-manufacturer registry expansion; period-resolution depth.

---

## 7. One-Paragraph Verdict

The real-bundle run did exactly what a real-data pass is supposed to do: it **closed MB-2** — the substrate absorbed the real 244-insight Lucky bundle with zero mapping failures, zero unresolved entities, full PDF_PAGE provenance, and no regression — and it **exposed one thing the fixtures could not**: a divergence-*policy* flaw in which 119 reference-only numeric mentions, bucketed by coarse topic labels, produced 120 spurious intra-source `fact_vs_fact` divergences. This is a policy defect, not an implementation or design failure — the mechanism ran faithfully and the audit honestly diagnosed its own anomaly — and it is fixable by tightening divergence eligibility (exclude reference-only numerics; require a precise same-fact key; honor the cross-source intent) rather than by redesign. Query Engine and QAE are ready to wire (the retrieval substrate and narrative signals are clean, and QAE sees zero of the noisy numeric divergences); FVE is blocked until the divergence policy is fixed and its gate is extended to non-OCR numbers. Fix the divergence policy, close the carried registry-confirmation and gate-extension Musts, and MSIL is ready for P8 integration — the substrate itself proved correct on real data, which is the bar every engine in this platform had to clear.
