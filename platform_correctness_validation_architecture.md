# Platform Correctness Validation Architecture

**Status:** Validation program design. No code, no implementation, no engine redesign. Validation governance only.
**Date:** 2026-06-03
**Objective:** Convert the platform from *contract-correct* to *accuracy-certified with measured, severity-scaled error rates* — closing the recurring gap that every freeze review named: structural correctness proven, substantive correctness unproven.

---

## 0. The Gap This Program Closes

Across OCR, MSIL, QAE, FVE, and Query, two tiers of correctness exist:

| Tier | Correctness types | Status | How established |
|---|---|---|---|
| **Structural** | contract · implementation · provenance · authority | **Proven** | Audits (deterministic, ownership-clean, cited, invariant-holding) |
| **Substantive** | extraction · resolution · classification · validation · answer | **Unproven** | Requires **external analyst ground truth** |

Every engine froze READY_WITH_LIMITATIONS with "correctness not certified" as the honest accepted scope, and "no truth set" as the platform-wide limitation (PL-2). **MB-1 (entity-resolution sign-off) is the first instance of this program already in motion** — the one substantive-correctness check elevated to a freeze blocker. This program generalizes MB-1's pattern to all five substantive types.

**The defining law:** substantive correctness can be established **only against external reality an analyst confirms — never against the system's own outputs** (the closed-loop trap that MB-1 and the QAE co-authored-truth-set both exposed).

---

## 1. Correctness Validation Principles (Task 1)

**The five substantive correctness types (each distinct, each separately validated):**

| Type | Owner engine | Question it answers |
|---|---|---|
| **Extraction correctness** | OCR | Do extracted values/labels/scale match the source document? (the deepest — all else rests on it) |
| **Resolution correctness** | MSIL | Does an identifier resolve to the *right real-world entity*? (the keystone — MB-1) |
| **Classification correctness** | QAE | Is content mapped to the *right* category/theme? (keyword-tier 80–84%, unvalidated) |
| **Validation correctness** | FVE | Is the gate verdict / plausibility assessment *right*? ("validated ≠ correct") |
| **Answer correctness** | Query | Does the cited answer *correctly* answer the question? (composite — §2) |

**Principles:**
- **PR-1 — Structural ≠ substantive.** Audits prove "does it do what we specified"; only external truth proves "is what it produced right about the world."
- **PR-2 — External truth only.** Validate against analyst-confirmed reality, never against system output (anti-closed-loop).
- **PR-3 — Measured error rate, not zero.** "Correct" means *within the accepted error band*, not infallible. Honesty over aspiration (the coverage≠correctness ethic).
- **PR-4 — Per-type method.** Extraction, resolution, classification, validation, and answer correctness each need their own truth and method; they do not substitute.
- **PR-5 — Error propagates; attribute it.** Answer correctness ≤ retrieval ≤ classification/validation ≤ extraction ≤ resolution. Errors must be attributed to the originating layer, not blamed on the consumer.
- **PR-6 — Severity-weighted.** A wrong baseline number (S1) ≠ a thin theme (S3); tolerance scales with severity (§6, §7).
- **PR-7 — Asymmetric tolerance.** Confidently asserting a wrong fact is far worse than honestly saying "insufficient." The platform already errs toward silence (evidence-or-silence, quarantine-not-force, default-deny, SKIPPED≠FAIL); the error philosophy formalizes this (§6).
- **PR-8 — Honest scope.** Correctness is certified *per validated issuer/sector*, never as a blanket claim.

---

## 2. Validation Ownership (Task 2)

The **engine team owns validation execution; analysts own the truth.** Layered by dependency (foundational first):

| Engine | Substantive correctness validated | Truth source (external) | Dependency role |
|---|---|---|---|
| **OCR** | Extraction (value/label/scale vs source PDF) | Analyst reading the PDF | **Foundational** — all downstream rests on it |
| **MSIL** | Resolution (entity facts vs PSX/SECP/filings) + provenance authenticity | Exchange/regulator/filings | **Keystone** — all attribution rests on it (MB-1) |
| **QAE** | Classification/theme (theme vs analyst reading of narrative) | Analyst reading report sections | Consumes OCR insights |
| **FVE** | Validation (gate verdict + plausibility vs analyst financial judgment) | Analyst financial review | Consumes OCR/MSIL numbers |
| **Query** | **Answer correctness — composite** | Analyst Q&A review | Consumes all of the above |

**The Query decomposition (critical):** answer correctness splits into
- **Query-assembly correctness** (near-structural — did Query correctly assemble/cite/bound from the evidence it had?) — **Query owns**; and
- **Upstream-evidence correctness** (is the underlying evidence right?) — **OCR/MSIL/QAE/FVE own**.
Query can be perfectly correct on wrong upstream evidence; the program must not blame Query for inherited errors (PR-5).

---

## 3. Truth-Set Strategy (Task 3)

- **Externally grounded & blind** — analysts record ground truth from the source *before/independently of* seeing system output (anti-anchoring; anti-closed-loop).
- **Layered build order** — foundational truth sets first (**OCR extraction, MSIL resolution**) because downstream correctness is bounded by them (PR-5). MSIL resolution truth = the `entity_resolution_signoff_checklist` (MB-1), already seeded.
- **Golden sets** — stable, versioned `(input → known-correct output)` per engine: OCR golden values, MSIL golden resolutions, QAE golden classifications, FVE golden verdicts, Query golden Q&A.
- **Provenance-anchored** — every truth item cites the exact source location the analyst verified.
- **Versioned + fingerprint-pinned** — each truth set pins the bundle fingerprint + engine version it validates; no cross-version reuse without migration.
- **Regression harness** — once built, truth sets become a **re-runnable CI eval gate** — the eval harness the platform never had (a finding open since the first Query Engine architecture review). This is a durable byproduct, not a one-off.
- **Multi-issuer** — span ≥2 issuers (Lucky + Millat) with an explicit path to a non-manufacturer (bank/power) — the generalization gap flagged platform-wide.

---

## 4. Sampling Methodology (Task 4)

- **Census for small/critical populations** — attest *all* of: MSIL entity facts (≈20, per MB-1), FVE baseline-eligible metrics (a handful), regulatory-contradiction items. S1 populations get full coverage.
- **Stratified sampling for large populations** — strata by (correctness type × severity × source/category); sample insights, narrative claims, and answers within strata.
- **Risk-weighted / adversarial over-sampling** — deliberately over-sample the *known-weak* areas where errors concentrate: keyword-tier QAE classifications, scale-corrupted OCR values, the 84 section-theme conflicts, review-gated values, ambiguous resolutions, cross-source divergences. Sample to *find* errors, not to confirm success.
- **Confidence-bounded** — each stratum yields an error-rate estimate *with a confidence interval*, never a point claim.
- **Census vs sample rule:** census when (population small) OR (severity S1); stratified sample otherwise.

---

## 5. Analyst-Review Requirements (Task 5)

- **Independent & blind** — truth recorded from source before/without system output (anti-anchoring).
- **Qualified by domain** — financial analyst for extraction/validation; narrative/domain analyst for classification; sector-aware reviewer for resolution.
- **Structured per item** — source location · correct value/class/verdict · reviewer confidence · disposition (`confirmed`/`corrected` + correct value).
- **Adjudication** — a second independent reviewer for disputed and all **S1** items.
- **Signed, versioned record** — dated, pinned to bundle fingerprint + engine version (the MB-1 sign-off pattern, generalized to every engine).
- **Bounded & recurring** — sampling keeps each pass finite; the program re-runs per major version / new issuer (regression).

---

## 6. Acceptable Error-Rate Philosophy (Task 6)

- **Zero is not the target — a documented, severity-scaled band is.** "Accepted" = within the published band for that correctness type and severity (PR-3).
- **Error rate is a release *signal*, not a binary** — each engine ships with a *published* error rate per correctness type + severity; consumers respect it (the analyst-review-grade posture made quantitative).
- **Asymmetric tolerance (the platform's DNA, formalized):**
  - **False *assertions* (confidently wrong facts)** — mis-resolution, scale-corrupt baseline, hallucinated/wrong cited answer, mis-targeted citation → **S1, near-zero tolerance**.
  - **False *withholdings* (honest silence)** — over-quarantine, SKIPPED-when-answerable, thin coverage → **more tolerable** (the system is *meant* to err toward "insufficient").
  - *It is worse to confidently say something wrong than to honestly say "insufficient."*
- **Tolerance scales inversely with severity** — S1 near-zero; S2 low; S3 moderate-and-reported; S4 cosmetic.
- **Bounded** — every accepted rate carries the sample's confidence interval.

---

## 7. Severity Classifications (Task 7)

| Severity | Definition | Tolerance | Examples |
|---|---|---|---|
| **S1 — Critical** | A confidently-asserted wrong fact with cross-engine or decision impact | **Near-zero** | Wrong entity resolution; scale-corrupt/wrong baseline number; missed regulatory contradiction; confidently-wrong cited answer; citation pointing to the wrong source |
| **S2 — Material** | A wrong substantive output affecting a material conclusion | **Low** | Wrong classification of a material theme; FVE wrongly admitting a bad baseline or blocking a good one; materially incomplete answer; authority mis-display |
| **S3 — Minor** | A substantive imprecision of limited impact | **Moderate, reported** | Thin/under-covered category; low-salience misclassification; minor narrative imprecision; non-load-bearing extraction error |
| **S4 — Cosmetic** | Presentation/labeling | **High** | Formatting, field-naming, reporting clarity |

Each correctness type maps its failure modes onto these; the **S1 set is the freeze-gating tier** (§9).

---

## 8. Audit Artifacts (Task 8)

| Artifact | Contents |
|---|---|
| `ocr_extraction_correctness_audit` | Golden-value sample; error rate per severity (CI); scale/label/value error catalogue; analyst sign-off |
| `msil_resolution_correctness_audit` | = the MB-1 entity sign-off; census of entity facts; 0-mis-resolution target; signed record |
| `qae_classification_correctness_audit` | Stratified theme/classification sample (over-weighted on keyword-tier + conflicts); error rate per severity |
| `fve_validation_correctness_audit` | Census of baseline-eligible verdicts + plausibility sample vs analyst financial judgment |
| `query_answer_correctness_audit` | Golden Q&A sample; **error attributed by layer** (Query-assembly vs upstream-evidence, PR-5) |
| **`platform_correctness_scorecard`** | Roll-up: error rate by correctness type × severity (with CI), the false-assertion-vs-false-withholding split, and the coverage statement (issuers/sectors validated) |
| **`platform_correctness_regression_harness`** | The versioned truth sets wired as a re-runnable eval gate (the institutionalized eval) |

Every artifact pins truth-set version + bundle fingerprint + engine version, and records the analyst sign-off.

---

## 9. Freeze Interaction (Task 9)

The program **does not block the current READY_WITH_LIMITATIONS freezes** — they froze with "correctness not certified" as an honest accepted scope. The program is what **lifts that limitation over time**, via tiers:

| Freeze tier | Certified | Status |
|---|---|---|
| **Tier-0 (current)** | Contract / implementation / provenance / authority | **Achieved** — READY_WITH_LIMITATIONS |
| **Tier-1 — S1 correctness** | Resolution (MB-1), baseline-number, regulatory-contradiction, citation-target correctness | **The hard gate** — MB-1 is its first item; near-zero S1 error required |
| **Tier-2 — S2/S3 per issuer** | Classification, answer, validation, extraction within accepted bands for issuer X | "Accuracy-certified for issuer X" |
| **Tier-3 — multi-issuer/sector** | Correctness generalized across issuers + a non-manufacturer | "Accuracy-certified, generalized" |

Rules:
- **S1 correctness is freeze-gating** (MB-1 already is); **S2–S4 are progressive post-freeze certification**.
- The program **re-scopes PL-2 ("no truth set / correctness not certified")** from a permanent caveat into a **tracked, retiring program** with a published error-rate scorecard.
- **Every new issuer / major version re-runs** the relevant truth sets (the regression harness).
- Engines remain frozen-as-built throughout — **this is validation, not redesign**; corrections surface as data fixes / version bumps, not architecture changes.

---

## 10. One-Paragraph Verdict

The platform has proven, exhaustively, that it does what it was specified to do — contracts hold, ownership is clean, provenance is immutable, authority is faithful, nothing is re-derived — but it has not yet proven that what it produces is *right about the world*, and the honest reviews said so at every freeze. This program closes that gap the only way it can be closed: against **external analyst ground truth, never the system's own outputs**, layered foundation-first (extraction and resolution before classification, validation, and answers), sampled risk-weighted toward the cases most likely to be wrong, and accepted not at an impossible zero but at a **documented, severity-scaled error band** that formalizes the platform's deepest instinct — that confidently asserting a wrong fact is far worse than honestly saying "insufficient." It owns correctness per engine while attributing error to its true layer, certifies in tiers that lift the "correctness not certified" caveat progressively (with the S1 set — led by MB-1 — as the hard gate), and leaves behind a re-runnable regression harness that becomes the eval the platform never had. It redesigns nothing; it validates everything that matters — turning an analyst-review-grade platform, over time and with measured honesty, into an accuracy-certified one without ever pretending it was certified before it was.
