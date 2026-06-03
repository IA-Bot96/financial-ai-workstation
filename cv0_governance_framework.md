# CV0 — Correctness Validation Governance Framework

**Status:** CV0 execution — the ratified governance + measurement framework the correctness program runs against. No code, no implementation, no engine redesign.
**Date:** 2026-06-03
**Sources:** `platform_correctness_validation_architecture.md`, `platform_truth_set_specifications.md`, `platform_correctness_validation_plan.md`.
**Pins:** `thresholds_version 1.0.0` (see `platform_correctness_thresholds.md`).

---

## 0. Purpose & Principles

CV0 freezes the rules so every later phase (CV1–CV6) validates against ratified, machine-comparable, version-pinned criteria. Binding principles:
- **External & blind** — truth recorded from source before/independently of system output.
- **Severity-scaled, asymmetric** — false assertions (S1, near-zero) ≫ honest withholdings (S3, tolerable).
- **Rate-with-CI** — no "zero" claim from a tiny sample; S1 requires census.
- **Layer-attributed** — errors land on the originating engine, never the consumer.
- **Validate built-and-live only** — not deferred capabilities, not structural correctness (already audit-proven).

(Severity bands, CI rule, sample sizes, census-vs-sample → `platform_correctness_thresholds.md`. Tasks 1–4 of the CV0 brief are answered there.)

---

## 1. Confidence-Interval Requirements (Task 2)

- **Every reported error rate carries a 95% Wilson score interval** (correct for 0-error / small-n; avoids the normal-approximation failure at near-zero).
- **S1:** certify only if the **CI upper bound ≤ 0.5%** → forces S1 strata to be **census** (small n cannot bound near-zero).
- **S2/S3:** point estimate vs band; CI upper bound governs the Target/Warning boundary.
- **Adversarial over-sampled cells:** report the per-cell rate **and** a **population-weighted estimate**, so over-sampling weak cells never inflates the engine's headline rate.
- Counts + Wilson intervals only — **no heavier statistical modeling** (over-engineering guard OE-5).

---

## 2. Minimum Sample Sizes (Task 3) — summary

Per `platform_correctness_thresholds.md §4`: **S1 = census** for every engine (OCR baseline metrics×years×2 issuers; all MSIL entities; all FVE baseline verdicts; all QAE divergences/conflicts/high-materiality; full Query golden Q&A). **S2/S3 = adversarial-stratified sample, ≥30/stratum**, over-weighted to known-weak cells, with final n set so the **CI upper bound fits the target band**.

---

## 3. Census-vs-Sample Rules (Task 4) — summary

Per thresholds §5: **census** when S1, or population ≤ 50, or foundational; **adversarial-stratified sample** otherwise; **over-sample weak cells** and report population-weighted estimates. The sampling lever is the program's primary defense against runaway analyst cost (OE-1).

---

## 4. Analyst Qualification Requirements (Task 5)

| Role | Qualification | Validates |
|---|---|---|
| **Financial analyst** | Reads financial statements; judges scale/value; judges baseline cleanliness | OCR, FVE |
| **Narrative/domain analyst** | Reads MD&A/risk/strategy/ESG; classifies per the frozen taxonomy; sector-aware | QAE |
| **Composite analyst** | Both competencies + citation-target verification + intent judgment | Query |
| **Registry analyst** | PSX/SECP/filings literacy | MSIL (MB-1) |
| **Adjudicator** | Senior analyst, independent of the primary reviewer | All disputes / all S1 |

Hard rules: the reviewer is **never the engine implementer**; truth is recorded **blind**; the adjudicator is **independent** of the primary reviewer.

---

## 5. Adjudication Rules (Task 6)

- **S1 disputes.** Every S1 finding requires a **second independent reviewer**. Disagreement → **senior adjudicator** decides. An S1 error **stands until adjudicated**; an **uncorrected adjudicated S1 = Failure band**. A **corrected + root-caused** S1 (data fix) moves out of the failure tally but **triggers a re-sample** of the affected stratum (systemic check).
- **Split reviewer outcomes (non-S1).** Adjudicator breaks the tie. If the adjudicator cannot decide → item marked **`indeterminate`**, **excluded from the correctness rate** (not counted as pass), and flagged for source clarification. Track the **indeterminate rate** — a high rate signals a **truth-set quality** problem, not an engine problem.
- **Insufficient evidence** (analyst cannot establish truth from the source). Item marked **`source_insufficient`**, **excluded from the correctness rate**, and counted in a separate **source-insufficiency rate**. High source-insufficiency is an **OCR/source-quality finding**, attributed upstream — *never* counted against the engine under review.
- **Direction classification** (assertion vs withholding) is recorded per error and **drives severity** (thresholds §0); direction disputes are adjudicated like any S1/S2 dispute.

These rules protect the measured rate from pollution (indeterminate / source-insufficient excluded) while surfacing truth-set and source-quality problems separately.

---

## 6. Sign-Off Format (Task 7)

A signed attestation record per engine validation (CV1–CV4) and the platform roll-up (CV5):

| Field | Content |
|---|---|
| `engine` · `correctness_type` | e.g. OCR / extraction |
| `truth_set_version` · `bundle_fingerprint` · `engine_version` · `thresholds_version` | pinned versions |
| `sample_design` | census/sample, n per stratum, sampling weights |
| `error_rates` | per severity, with 95% Wilson CI, and population-weighted estimate where over-sampled |
| `direction_split` | false-assertion vs false-withholding counts |
| `adjudication_log` | S1 findings, disputes, resolutions |
| `indeterminate_count` · `source_insufficient_count` | excluded-item rates |
| `disposition` | **certified** / **conditional** (warning-band, with required follow-up) / **not-certified** |
| `primary_analyst` (name, role, date) · `adjudicator` (name, date) | signatures |

Disposition maps to bands: all gating severities in **Target** → certified; any in **Warning** → conditional (with documented follow-up + re-sample); any in **Failure** → not-certified.

---

## 7. Truth-Set Versioning Format (Task 8)

| Field | Content |
|---|---|
| `truth_set_id` | engine + scope (e.g. `ocr_extraction_lucky`) |
| `truth_set_version` | semver |
| `bundle_fingerprint` · `engine_version` · `thresholds_version` | what it validates |
| `created_date` · `analyst` · `adjudicator` | provenance of the truth |
| `items[]` | each: `item_id`, `source_provenance`, `expected` (typed), `severity`, `direction`, `stratum`, `reviewer`, `disposition` |

**Versioning rules:** data/value corrections or alias additions → **minor** bump; a change to scope, severity mapping, or comparator → **major** bump. A truth set is a valid regression baseline **only against the same engine + bundle version** (or via an explicit migration map). Truth sets are **append-versioned, never silently edited**.

---

## 8. Machine-Comparable Truth Format (Task 9) — for `platform_correctness_regression_harness`

Each truth item is a structured, deterministic-comparison record (no LLM in the harness — deterministic-first):

| Field | Content |
|---|---|
| `item_id` | stable id |
| `engine` · `correctness_type` · `stratum` · `severity` · `direction` | classification |
| `source_provenance` | the cited location the analyst verified |
| `expected` | typed: OCR `{value, unit, scale}`; QAE `{category, theme}`; FVE `{verdict, role}`; Query `{answer_key, required_citations[], authority}` |
| `comparator` | how to compare (vocabulary below) |
| `tolerance` | e.g. numeric tolerance; `scale_exact: true`; set-membership |

**Comparator vocabulary (frozen):**
- `numeric_scale_aware` (OCR/FVE values — value AND scale must match; the dominant OCR failure)
- `canonical_id_match` (QAE category/theme; MSIL entity)
- `verdict_match` (FVE verdict + role)
- `set_membership` (QAE multi-theme; required-citation set)
- `citation_target_match` (Query — the citation resolves to the expected source)
- `answer_key_contains` (Query — answer contains the required grounded claims)

**Harness behavior:** for each item, emit `actual` vs `expected`, apply the comparator+tolerance → per-item pass/fail → roll up to **rates per stratum × severity with Wilson CIs + population-weighting**. The harness is **deterministic, versioned, and re-run only against the pinned bundle/engine version**. It is the durable byproduct — the eval the platform never had.

---

## 9. CV0 Exit Criteria

CV0 is complete (and CV1 may begin) when:
1. **Thresholds ratified** (`platform_correctness_thresholds.md`, `thresholds_version 1.0.0`).
2. **CI rule + sample sizes + census/sample rules** locked.
3. **Analyst qualification + adjudication rules** ratified.
4. **Sign-off + truth-set versioning + machine-comparable formats** frozen (so CV5's harness can consume them).
5. **MB-1 acknowledged as the co-foundational S1 truth set** (already in motion).

`cv0_governance_readiness` audit confirms 1–5.

---

## 10. One-Paragraph Verdict

CV0 freezes the measurement so that every correctness verdict downstream is comparable, honest, and reproducible: severity bands that are **asymmetric by direction** (a confidently-asserted wrong fact targets zero and is census-validated; an honest withholding is tolerated), **Wilson confidence intervals** that forbid claiming "zero" from a thin sample, **adversarial sampling reported population-weighted** so candor about weak spots never inflates the headline rate, **blind independent analysts** with a senior adjudicator for every S1 and a disciplined handling of split and source-insufficient cases that excludes the un-gradeable rather than guessing, **signed version-pinned attestations** mapping band outcomes to certified/conditional/not-certified, and a **deterministic, machine-comparable truth format** whose comparators (scale-aware numeric, canonical-id, verdict, citation-target) become the platform's first re-runnable correctness eval. It builds nothing and redesigns nothing — it sets the rules of evidence for turning an analyst-review-grade platform into an accuracy-certified one, S1 first, with the same conviction the platform was built on: better to measure honestly and certify slowly than to claim a correctness the evidence does not yet support.
