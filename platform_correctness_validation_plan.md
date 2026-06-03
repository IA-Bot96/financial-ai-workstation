# Platform Correctness Validation Plan

**Status:** Execution plan for the correctness-validation program. No code, no implementation, no engine redesign. Validation sequencing only.
**Date:** 2026-06-03
**Sources:** `platform_correctness_validation_architecture.md`, `platform_truth_set_specifications.md`.
**Nature:** This is an **analyst-bound** program — its cost is analyst review time, not development. The only engineering is a minimal compare-to-golden regression harness (CV5).

---

## 0. Sequencing Principles

1. **Governance before validation** (CV0) — freeze severity definitions, error-band thresholds, analyst protocol, sign-off format, and the truth-set/regression contract before any engine is validated.
2. **Foundation-first** — OCR extraction (CV1) and MSIL resolution (MB-1, already in motion) are foundational; QAE/FVE/Query correctness is **bounded by and attributed to** them, so they precede the consumers.
3. **Composite-last** — Query (CV4) is validated after OCR/QAE/FVE because answer errors must be **attributed by layer** (Query-assembly vs inherited), which requires the upstream error baselines first.
4. **Roll-up, then freeze** — platform scorecard + harness (CV5) precede the freeze-doc update (CV6).
5. **Sample, don't census (except S1)** — census the critical few; adversarial-stratified-sample the many. Over-censusing is the program's main over-engineering trap.
6. **Validate what's built and live** — not deferred capabilities (FVE plausibility rules, analyst/news QAE sources) and not structural correctness (already audit-proven).
7. **Validate frozen bundles** — pin fingerprints (`97c3123…` etc.); never validate against a live re-extraction (OCR/LLM variability).

---

## 1. Phases

| Phase | Scope | Depends on | Audit / artifact | Analyst effort* | Exit |
|---|---|---|---|---|---|
| **CV0 — Governance** | Freeze severity defs, per-engine/severity **error-band thresholds**, blind-analyst protocol, sign-off template, truth-set versioning/pinning, regression-harness contract | architecture/spec docs | `cv0_governance_readiness` + the threshold table | **S** (~2–4 program-lead days + 1 analyst to ratify protocol) | Program contracts frozen; thresholds ratified. |
| **CV1 — OCR validation** | Extraction-correctness truth set (foundational) | CV0 + **MB-1** (entity attribution) | `ocr_extraction_correctness_audit` + OCR golden values + scale/value/label error catalogue | **L** (~8–15 analyst-days; PDF line-reading is slow) | S1 baseline-metric scale/value error near-zero; signed. |
| **CV2 — QAE validation** | Classification/theme/divergence truth set | CV0 + **CV1** (attribution) | `qae_classification_correctness_audit` + golden classifications + divergence-genuineness verdicts | **L** (~8–14 analyst-days; many items, fast per-item) | Classification within band; divergence false-positive near-zero. |
| **CV3 — FVE validation** | Validation-correctness truth set (verdicts both directions + admission roles) | CV0 + **CV1** | `fve_validation_correctness_audit` + golden verdicts (FP/FN split) | **M** (~4–7 analyst-days; small population, financial judgment) | Bad-baseline admission (S1) near-zero; admission roles correct. |
| **CV4 — Query validation** | Answer-correctness truth set (composite, layer-attributed) | CV0 + **CV1 + CV2 + CV3 + MB-1** | `query_answer_correctness_audit` + golden Q&A + layer-attributed error catalogue | **M** (~5–8 analyst-days; layer attribution adds per-item overhead) | Wrong-cited-answer + wrong-citation-target near-zero; intent robust on messy queries. |
| **CV5 — Platform validation** | Roll-up scorecard + regression harness | CV1–CV4 | `platform_correctness_scorecard` + `platform_correctness_regression_harness` | **S** (~2–4 days; program lead + light adjudication) | Scorecard published (error rate × severity, FP/FN split, coverage); harness re-runnable. |
| **CV6 — Freeze update** | Re-scope PL-2; tiered certification; publish error-rate scorecard | CV5 | updated `platform_freeze_readiness_review` + `platform_known_limitations` + correctness-tier statement | **S** (~1–2 governance days) | PL-2 re-scoped to a tracked retiring program; Tier-1 (S1) certification recorded. |

*Effort = **order-of-magnitude estimates**, driven by sample size; per-issuer (Lucky + Millat ≈ ×2 for the substantive phases). To be refined once CV0 sets sample sizes.

---

## 2. Per-Phase Detail

**CV0 — Governance.** Ratify the **error-band thresholds** (per engine × severity; e.g. S1 near-zero, S3 moderate), the **blind/independent analyst protocol** (truth from source before system output), the **sign-off template** (dated, fingerprint+version-pinned), and the **machine-comparable truth-set format** (so CV5's harness can re-run them). *Audit:* `cv0_governance_readiness` — thresholds + protocol + format frozen. *Exit:* no validation begins until this is locked (validation's contracts-first).

**CV1 — OCR (foundational).** Census the baseline-eligible core metrics × value-years; adversarial over-sample scale-flagged/review-gated/conflict values; analyst reads the **source PDF**, records value/scale/label/page blind, then compares. *Artifacts:* OCR golden values; scale/value/label error catalogue. *Exit:* S1 (baseline-metric scale/value) near-zero; this establishes the **OCR error baseline that downstream attribution depends on**.

**CV2 — QAE.** Adversarial over-sample keyword-tier classifications + the 84 conflicts + every divergence; census high-materiality themes; analyst classifies per the frozen taxonomy from source, judges divergence genuineness and materiality defensibility. *Artifacts:* golden classifications; divergence-genuineness verdicts. *Exit:* classification within band; **divergence false-positive near-zero**.

**CV3 — FVE.** Census baseline verdicts in **both directions** (admitted-but-bad and blocked-but-good) + admission-role check; analyst judges baseline cleanliness from source financials. *Artifacts:* golden verdicts with the false-positive/false-negative split. *Exit:* **bad-baseline admission (S1) near-zero**; roles correct.

**CV4 — Query (composite, last).** Golden Q&A across 8 intents + messy-phrasing variants + divergence/metric/off-ramp cases; analyst formulates the correct answer from source, then **attributes each error to its layer** (Query-assembly vs inherited from OCR/MSIL/QAE/FVE — using the CV1–CV3 baselines). Verify citation targets, authority display, integrity status, off-ramps. *Artifacts:* golden Q&A; layer-attributed error catalogue. *Exit:* wrong-cited-answer + wrong-citation-target near-zero; intent robust on messy phrasing.

**CV5 — Platform.** Assemble `platform_correctness_scorecard` (error rate by correctness type × severity with CI, the **false-assertion vs false-withholding split**, and the **coverage statement** — issuers/sectors validated); wire the versioned truth sets into the re-runnable `platform_correctness_regression_harness` (the eval the platform never had). *Exit:* scorecard published; harness green and re-runnable.

**CV6 — Freeze update.** Re-scope **PL-2** ("no truth set / correctness not certified") from a permanent caveat into a **tracked, retiring program**; record **Tier-1 (S1) certification** (MB-1 + OCR/QAE/FVE/Query S1 items) in the platform freeze docs; publish the error-rate scorecard as a release signal. *Exit:* freeze docs reflect the correctness-tier model.

---

## 3. Consolidated Analyst Effort

| Phase | Effort tier | Driver |
|---|---|---|
| CV0 | S | Governance, not sampling |
| CV1 OCR | **L** | PDF line-reading × census + adversarial sample × 2 issuers |
| CV2 QAE | **L** | Largest item count (keyword-tier + conflicts + divergences) |
| CV3 FVE | M | Small population, but two-direction financial judgment |
| CV4 Query | M | Layer attribution adds per-item overhead |
| CV5 / CV6 | S | Roll-up + governance |

The program is **analyst-throughput-bound**, not dev-bound; OCR and QAE dominate. Effort is bounded by sampling — the explicit lever against runaway cost.

---

## 4. Hidden Dependencies

- **HD-1 — MB-1 (entity sign-off) is co-foundational.** OCR value *attribution* and Query *answer attribution* depend on entities being right; MB-1 must complete alongside/before CV1 and before CV4.
- **HD-2 — Analyst availability & qualification (critical path).** Financial analyst (OCR/FVE), narrative/domain analyst (QAE), both (Query); the program's schedule is gated by analyst scheduling, not code.
- **HD-3 — Source access.** The actual Lucky/Millat PDFs (+ PSX/SECP/filings for cross-checks) must be available for blind truth recording.
- **HD-4 — CV0 thresholds gate CV1–CV4 pass/fail.** No phase can declare pass until the error bands are ratified.
- **HD-5 — Upstream baselines gate attribution.** CV2/CV3 attribution needs CV1; CV4 needs CV1–CV3 (+MB-1).
- **HD-6 — Machine-comparable truth format (CV0)** is required for the CV5 harness; if truth sets are recorded ad hoc, the regression eval can't be built.
- **HD-7 — Millat provenance caveat.** The MSIL real-bundle review noted Millat used an OCR *context*, not a `.kb.json` sidecar; Millat truth-set provenance anchoring must account for this.
- **HD-8 — Frozen bundles.** Validation pins fingerprints; a re-extraction invalidates the truth set (OCR/LLM variability).

---

## 5. Over-Engineering Risks

- **OE-1 — Exhaustive validation instead of sampled.** Censusing all ~1,867 OCR values / all 244 insights / all answers is infeasible and defeats the design. Census **only S1**; adversarial-sample the rest.
- **OE-2 — Building heavy validation tooling/UI** before the manual blind protocol is proven on one engine. Keep the harness a minimal compare-to-golden; do not build a "validation platform."
- **OE-3 — Validating deferred/non-existent capabilities.** No truth set for FVE forecast-plausibility rules (not built) or analyst/news QAE sources (deferred). Validate what is **built and live**.
- **OE-4 — Re-validating structural correctness.** Contracts/provenance/authority are already audit-proven; the program is **substantive-only** — do not re-audit them.
- **OE-5 — Statistical over-modeling.** Start with error **counts + simple confidence intervals**, not a measurement-science apparatus.
- **OE-6 — Throwaway truth instead of reusable golden sets.** Build **versioned, re-runnable** sets (the regression value), not one-off per-run truth.
- **OE-7 — Chasing S3/S4 to zero.** Tolerance is severity-scaled; do not burn analyst time driving minor/cosmetic errors to zero.

---

## 6. Sequencing Rationale

Governance first (CV0) so every phase validates against ratified thresholds and a machine-comparable format. OCR (CV1) next because **everything downstream is bounded by extraction correctness** and its error baseline is needed to attribute QAE/FVE/Query errors to the right layer; MB-1 runs co-foundationally for the same attribution reason. QAE and FVE (CV2/CV3) follow CV1 and are **parallelizable** (narrative vs numeric domains) — sequence them by analyst availability. Query (CV4) is **last among engine validations** because its composite answer correctness can only be layer-attributed once OCR/QAE/FVE/MSIL baselines exist. CV5 rolls the per-engine results into the platform scorecard and the regression harness; CV6 updates the freeze docs and re-scopes PL-2. The S1 results across CV1–CV4 (plus MB-1) constitute the **Tier-1 freeze gate**; S2–S3 certify progressively per issuer post-freeze.

---

## 7. One-Paragraph Verdict

The correctness program runs the way the platform was built — governance and thresholds first (CV0), then **foundation-first** validation of OCR extraction (CV1) and the co-foundational entity sign-off (MB-1), then QAE and FVE in parallel as their domains and analysts allow (CV2/CV3), then **Query last** because its answer correctness only resolves once each upstream error baseline lets the program attribute blame to the right layer (CV4), then a platform roll-up scorecard and a re-runnable regression harness (CV5), and finally a freeze-doc update that re-scopes the long-standing "correctness not certified" caveat into a tracked, retiring, tiered certification (CV6). It is an **analyst-throughput-bound** program whose cost is controlled by the one discipline that makes it feasible — census the critical few, adversarially sample the many, and refuse to chase minor errors to zero — and whose dependencies are honest: analysts, source access, ratified thresholds, frozen bundles, and the upstream baselines that make layer attribution possible. It builds nothing and redesigns nothing; it produces the truth, the scorecard, and the eval harness that turn an honestly-scoped analyst-review-grade platform into an accuracy-certified one — S1 first, where the danger is greatest, exactly as the platform's invariants demand.
