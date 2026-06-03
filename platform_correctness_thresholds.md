# Platform Correctness Thresholds (CV0-ratified)

**Status:** CV0-ratified severity bands and measurement rules. No code, no redesign. Governance/measurement only.
**Date:** 2026-06-03
**Version:** `thresholds_version 1.0.0` (pinned by every correctness audit).
**Companion:** `cv0_governance_framework.md`.

---

## 0. How Bands Work

- An error **rate** is measured per **(engine × severity × stratum)**: errors ÷ items reviewed in that stratum.
- Three bands per cell: **Target** (certify), **Warning** (conditional — investigate/correct/re-sample), **Failure** (do-not-certify).
- **Judged on the rate AND its confidence interval** (§ CI rule): a band claim requires the relevant CI bound to fall inside the band — you cannot claim "0% S1" from n=3.
- **Asymmetric by direction (the platform's DNA):** an error's *severity is assigned by direction* — a **false assertion** (a wrong fact stated) floors at **S2 and escalates to S1** when decision-impacting/cross-engine; a **false withholding** (honest silence) caps at **S3** and escalates to **S2 only if systemic**. The bands below then apply per assigned severity.

---

## 1. Common Severity Bands (default, all engines)

| Severity | Target (certify) | Warning (conditional) | Failure (do-not-certify) |
|---|---|---|---|
| **S1 — Critical** | **0 errors in census** (95% CI upper bound ≤ 0.5%) | isolated S1 error(s), **all corrected + root-caused**, ≤ 1% of census, and re-sample of the affected stratum passes | any **uncorrected** S1 error, OR rate > 1%, OR a **systemic** S1 pattern |
| **S2 — Material** | ≤ 5% (CI upper ≤ 8%) | 5–15% | > 15% |
| **S3 — Minor** | ≤ 20% (CI upper ≤ 30%) | 20–40% | > 40% |
| **S4 — Cosmetic** | **Informational — tracked, non-gating** | — | — |

**S1 is the freeze gate (Tier-1).** S2/S3 are progressive certification (Tier-2/3). S4 never gates.

---

## 2. Per-Engine Bands & S-Mapping

Bands inherit §1 unless tightened. Each engine's table names what counts as S1/S2/S3.

### OCR — extraction correctness
| Severity | Failure mode | Band |
|---|---|---|
| **S1** | Wrong value or **wrong scale** on a baseline-eligible core metric (false assertion → feeds FVE) | §1 S1 (target 0) |
| **S2** | Wrong value on a material non-core line; wrong label changing meaning | §1 S2 |
| **S3** | Non-load-bearing value/label imprecision | §1 S3 |
| **(withholding)** | A value the analyst found but OCR didn't extract | classified **S3** (caps at S2 if systemic) |

### MSIL — resolution correctness (= MB-1)
| Severity | Failure mode | Band |
|---|---|---|
| **S1** | **Mis-resolution** (wrong real-world entity); cross-group confusion | **Strict S1 — target 0; warning only if corrected+root-caused; any uncorrected = failure** |
| **S2** | Wrong listed-status/sector affecting routing | §1 S2 |
| **S3** | Non-load-bearing fact (e.g. unused registration id) | §1 S3 |
| **(withholding)** | Over-quarantine of a resolvable entity | **S3** |

### QAE — classification correctness
| Severity | Failure mode | Band |
|---|---|---|
| **S1** | **Fabricated divergence** surfaced as genuine (false contradiction) | §1 S1 (target 0) |
| **S2** | Mis-classification of a **material** theme; indefensible high materiality | §1 S2 |
| **S3** | Low-salience/minor mis-mapping | §1 S3 |
| **(withholding)** | A skipped/under-covered category (coverage-honest) | **S3** (S2 only if systemic starvation hides a material theme) |

### FVE — validation correctness
| Severity | Failure mode | Band |
|---|---|---|
| **S1** | **Bad baseline wrongly admitted** as clean (false positive → corrupts forecast math) | **Strict S1 — target 0** |
| **S2** | Wrong admission role; wrong plausibility verdict on a material forecast | §1 S2 |
| **S3** | Minor verdict imprecision | §1 S3 |
| **(withholding)** | **Good baseline wrongly blocked** (false negative) | **S3 — tolerable but tracked** (escalates to S2 if over-blocking is systemic, eroding usefulness) |

### Query — answer correctness
| Severity | Failure mode | Band |
|---|---|---|
| **S1** | **Confidently-wrong cited answer**; **citation pointing to the wrong source** | §1 S1 (target 0) |
| **S2** | Materially incomplete answer; intent mis-classified on reasonable phrasing; authority mis-displayed | §1 S2 |
| **S3** | Minor incompleteness; intent miss on edge phrasing | §1 S3 |
| **(withholding)** | `INSUFFICIENT_EVIDENCE` / `NEEDS_CLARIFICATION` where an answer was possible | **S3** |

**Query layer-attribution rule:** errors are split into **Query-assembly** (Query owns — held to the tighter band) vs **inherited upstream** (attributed to OCR/MSIL/QAE/FVE — counted in *their* rate, not Query's).

---

## 3. Confidence-Interval Rule

- Every reported rate carries a **95% Wilson score interval** (handles 0-error and small-n correctly).
- **S1:** certify only if the **CI upper bound ≤ 0.5%** — which, at near-zero observed errors, *requires the S1 stratum to be a census* (small n cannot bound near-zero).
- **S2/S3:** report point estimate + CI; band judged on the point estimate, with the CI upper bound used for the Target/Warning boundary (§1).
- **Over-sampled adversarial cells:** report **both** the per-cell rate **and** a **population-weighted estimate** (so deliberately over-sampling weak cells does not make the engine look worse than its true population rate).

---

## 4. Minimum Sample Sizes (per engine)

| Engine | S1 (census) | S2/S3 (adversarial-stratified sample) |
|---|---|---|
| **OCR** | All baseline-eligible core metrics × all value-years × 2 issuers (≈120–240) | ≥150 values stratified by sheet/table_type; **all** scale-flagged + a sample of review-gated |
| **MSIL** | All registry entity facts (≈20, MB-1) | n/a (S1 keystone) |
| **QAE** | **All** surfaced divergences + **all** high-materiality themes + **all** 84 section-theme conflicts | ≥120 classifications, over-weighted to keyword-tier, across 2 issuers |
| **FVE** | **All** baseline-eligible verdicts (both directions) + **all** admission decisions on the bundle | plausibility sample when rules exist (post-MVP) |
| **Query** | **Full golden Q&A** (all 8 intents × ≥3 phrasings ≈ ≥24 Q&A); **every** claim's citation-target checked | messy-phrasing + completeness sample within the golden set |

Rule of thumb: **≥30 items per S2/S3 stratum** for a usable CI; more for dominant strata (OCR values, QAE keyword-tier). Final n set so the **CI upper bound fits the target band**.

---

## 5. Census-vs-Sample Rule

- **Census** when: severity **S1**, OR population **≤ 50**, OR the stratum is **foundational** (baseline-eligible metrics, entities).
- **Adversarial-stratified sample** when: severity **S2–S4** AND population large.
- **Over-sample known-weak cells** (keyword-tier, scale-flagged, conflicts, review-gated, ambiguous resolutions) — report sampling weights and a population-weighted estimate (§3).

---

## 6. One-Line Posture

Thresholds are severity-scaled and **asymmetric** — **S1 (a confidently-asserted wrong fact) targets zero and is census-validated; withholdings cap at S3** — judged on rate-with-CI so "zero" is never claimed from a tiny sample, with adversarial over-sampling reported population-weighted so honesty about weak spots never penalizes the true rate.
