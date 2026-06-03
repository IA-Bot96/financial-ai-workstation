# CV1 — OCR Extraction Correctness Validation Protocol

**Status:** CV1 execution package. No code, no implementation, no OCR redesign. Correctness-validation execution only.
**Date:** 2026-06-03
**Pins:** `thresholds_version 1.0.0`, the validated bundles' fingerprints (Lucky `97c3123…`, Millat per its context), engine_version.
**Precondition:** **MB-1 (entity sign-off) confirmed** — every item's issuer/entity attribution must be MB-1-validated, or extraction truth attaches to the wrong entity.
**Foundational:** CV1 establishes the extraction error baseline that CV2/CV3/CV4 attribute against; it runs first among engine validations.

---

## 1. Executable Analyst Workflow (Task 1)

CV1 turns the OCR truth-set spec into a per-item, **source-PDF-first, blind-first** review producing a machine-comparable truth set (`ocr_truth_set_schema.md`) and the `ocr_extraction_correctness_audit`. The unit of work is a **validation item** = `(issuer, canonical_metric, value_year, source-page reference)`. The analyst records truth from the source **before** seeing system output, dispositions the comparison, and routes scale/multi-table disputes to adjudication.

---

## 2. Census Population (Task 2)

The **baseline-eligible core metrics** (the values that feed FVE/HSIG) × **all value-years** × **both issuers**, validated across **five value classes**.

**Baseline-eligible metrics (11):** `revenue`, `gross_profit`, `operating_profit`, `profit_after_tax`, `earnings_per_share`, `total_assets`, `total_equity`, `cash_and_cash_equivalents`, `total_debt`, `long_term_debt`, `operating_cash_flow`.
**Value-years:** all present in each bundle (Lucky 2020–2025 ≈ 6; Millat similar).
**Issuers:** Lucky + Millat.
**Value classes (validated per item):** `value` (the number) · `scale` (thousands / millions / full) · `unit` (PKR / per-share / %) · `label` (canonical-metric mapping) · `presence` (present vs expected-but-missing).

**Census size:** ≈ 11 × 6 × 2 ≈ **132 (metric, year, issuer) cells**, each carrying all five value-class checks. EPS is unit-special (per-share). `total_debt`/`long_term_debt`/`total_equity` enter as **`presence` checks** (they were "missing" on Lucky — validate truly-absent vs extraction-missed). Final n confirmed against the actual bundle inventory.

This is **S1 stratum → census** (per thresholds §5).

---

## 3. Adversarial Sample Population (Task 3)

Over-sampling the known-weak cells where errors concentrate:

| Sub-population | Method | Rationale |
|---|---|---|
| **Scale-flagged values** | **Census** | The dominant S1 failure (e.g. revenue 41,871 → 62.9bn → 95m). All `scale_consistency_audit` flags (16 consolidation-scale-corruption + the YoY/candidate-spread flags) validated. |
| **Note-vs-statement selections** | **Census** | Wrong-source-selected = S1 (e.g. revenue 2024/2025 from page-320 notes over income-statement Turnover). |
| **Review-gated values** | **Stratified sample** | ~65% of consolidated values; sample by business area, over-weight core-metric-adjacent. |
| **Unresolved-conflict groups** | **Stratified sample, core-first** | Lucky 187 (26 critical); for each, validate which candidate is correct. |
| **Missing-year cases** | **Stratified sample** | Lucky 93 missing-year tables; validate truly-absent vs extraction-missed (withholding vs assertion). |

Census the two highest-risk (scale-flagged, note-vs-statement); sample the rest, over-weighted to core metrics, reported **population-weighted** (thresholds §3) so over-sampling doesn't inflate the headline rate.

---

## 4. Analyst Review Procedure (Task 4) — step by step

1. **Receive item** `(issuer, metric, value_year, cited source page)` — **system value withheld** (blind).
2. **Open the source PDF** at the cited page **and** the relevant primary-statement page.
3. **Locate the line item** in the source financial statement.
4. **Record blind truth** into the schema: `value`, `scale`, `unit`, `canonical_label`, `presence`, and the **exact source location** (page, statement, line label, statement_scope).
5. **Record reviewer confidence + any source ambiguity** (value stated multiple ways, restated, footnoted, scale-header unclear).
6. **Reveal system output** — the OCR-consolidated `value/scale/unit/label/presence` for the item.
7. **Compare and disposition** (§5).
8. **Classify** any error by **direction** (assertion / withholding) and **severity** (§6).
9. **Route disputes** (scale, unit, multi-table) to **adjudication** (§7).
10. **Persist** the item to the truth set (`ocr_truth_set_schema.md`).

**Invariants:** truth is the **source PDF, never the workbook**; truth is recorded **before** the system value is revealed (anti-anchoring); the reviewer is **not** the OCR implementer.

---

## 5. Disposition Vocabulary (Task 5)

| Disposition | Meaning | Direction |
|---|---|---|
| `confirmed` | System matches source on all value classes | — |
| `corrected_value` | Right scale/label, **wrong number** | assertion |
| `corrected_scale` | Right magnitude family wrong (thousands/millions/full) — **the dominant OCR failure** | assertion |
| `corrected_unit` | Wrong unit (per-share vs currency, % vs absolute) | assertion |
| `corrected_label` | Mapped to the wrong canonical metric / wrong line | assertion |
| `corrected_source` | **Note/summary/analysis value selected over the primary statement** | assertion |
| `spurious_extracted` | System extracted a value the source does not support | assertion |
| `missing_extracted` | Value present in source, system did not extract | **withholding** |
| `source_ambiguous` | Source states it multiple ways / restated → **adjudicate** | — |
| `source_insufficient` | Source cannot establish truth → **excluded from rate**, counted separately | — |

---

## 6. OCR Severity Mapping (Task 6) — `thresholds_version 1.0.0`

| Disposition | On baseline-eligible core metric | On material non-core | On non-load-bearing |
|---|---|---|---|
| `corrected_scale` | **S1** (feeds FVE — the strict zero-tolerance failure) | S2 | S3 |
| `corrected_value` | **S1** | S2 | S3 |
| `corrected_unit` | **S1** (changes magnitude/meaning, e.g. EPS-as-currency) | S2 | S3 |
| `corrected_source` (note-over-statement) | **S1** | S2 | S3 |
| `corrected_label` | **S1** if it corrupts a baseline series | S2 | S3 |
| `spurious_extracted` | **S1** | S2 | S3 |
| `missing_extracted` (withholding) | **S3** (→ S2 only if a whole core series is systematically missing) | S3 | S3 |
| label casing/formatting, rounding-display | — | — | **S4** (informational, non-gating) |
| `source_ambiguous` | not an error until adjudicated; on resolution → `confirmed` or the corrected disposition's severity |
| `source_insufficient` | **excluded** from the error rate; counted in the **source-insufficiency rate** (attributed to source/page quality, not OCR-correctness) |

**The asymmetry (CV0 DNA):** wrong value/scale/unit/source/spurious on a baseline metric = **S1, target zero**; a missing extraction = **S3, tolerable**.

---

## 7. OCR Adjudication Rules (Task 7)

- **Scale disputes (most common, most dangerous).** Resolve against the **source document's stated units** (the "Rupees in thousands/millions" header) and the comparative-column consistency. A scale disagreement on a **baseline metric is an S1 dispute** → mandatory **second reviewer + senior adjudicator** (CV0). If the source itself is scale-ambiguous → `source_ambiguous`; if unresolvable → `source_insufficient` (excluded).
- **Unit disputes.** Adjudicate against the line label + statement context (EPS line = per-share; ratio lines = %); never infer unit from magnitude alone.
- **Multi-table conflicts (note-vs-statement / consolidation conflict).** The **primary-statement value is the truth anchor** (precedence: primary statement > supporting schedule > note > summary > analysis). If the system selected a non-primary value → `corrected_source` (**S1** for core metrics). If the primary statement is itself internally inconsistent → adjudicate; if irreconcilable → `source_ambiguous`/`source_insufficient`.
- **S1 handling (CV0):** uncorrected adjudicated S1 = **Failure**; corrected + root-caused S1 = move out of failure tally **+ re-sample the affected stratum** (systemic check). All disputes logged in the adjudication log.

---

## 8. Truth-Set Schema (Task 8)

→ specified in `ocr_truth_set_schema.md` (machine-comparable, `numeric_scale_aware` comparator, harness-compatible).

---

## 9. `ocr_extraction_correctness_audit` (Task 9)

**Contents:**
- Pins: `truth_set_version`, `bundle_fingerprint`, `engine_version`, `thresholds_version 1.0.0`.
- Sample design: census list + adversarial sample design (n per stratum, sampling weights).
- Per-item dispositions; **error catalogue** (item, expected, actual, disposition, severity, direction).
- Adjudication log; `indeterminate_count`; `source_insufficient_count`.
- Analyst + adjudicator sign-off.

**Metrics:**
- **Error rate per severity** with **95% Wilson CI**.
- **Headline: S1 scale-error rate** on baseline metrics (census).
- **False-assertion vs false-withholding split.**
- Per-stratum rate **+ population-weighted estimate** (adversarial cells).
- **Source-insufficiency rate** (separate, attributed upstream).
- Per-metric × per-year disposition matrix.

**Pass/Fail logic (per thresholds 1.0.0):**
- **S1:** 0 errors in census (CI upper ≤ 0.5%) → **certified**; isolated corrected + root-caused S1 with passing re-sample → **conditional**; any uncorrected S1 OR rate > 1% OR systemic → **Failure**.
- **S2:** ≤5% (CI upper ≤8%) target / 5–15% warning / >15% Failure.
- **S3:** ≤20% target / 20–40% warning / >40% Failure.
- **Overall disposition:** **certified** only if S1 **and** S2 in Target; **conditional** if any gating severity in Warning (with required follow-up + re-sample); **not-certified** if any in Failure.
- `source_insufficient` / `indeterminate` items **excluded** from rates (CV0).

**Gate:** CV1 is foundational — its disposition (certified/conditional/not-certified) and per-item error baseline are required before CV2/CV3 attribution and feed the Tier-1 freeze gate.

---

## 10. One-Paragraph Verdict

CV1 validates the numbers that everything else rests on, the only honest way: an analyst opens the **source PDF first**, records the correct value, **scale**, unit, label, and presence **blind**, and only then compares to the OCR-consolidated output — censusing every baseline-eligible metric across all years and both issuers, and additionally censusing the two highest-risk weak cells (scale-flagged values and note-over-statement selections) where the platform's worst extraction failures live. Errors are dispositioned with a vocabulary that names the real failure modes (`corrected_scale`, `corrected_source`, `spurious_extracted`), mapped under `thresholds_version 1.0.0` so a wrong scale or wrong source on a baseline metric is **S1 with target zero** while a missing extraction is a tolerable **S3** — the platform's asymmetry made operational. Scale, unit, and multi-table conflicts route to a senior adjudicator who resolves against the source's stated units and the primary-statement precedence, and items the source cannot adjudicate are excluded from the rate and attributed to source quality rather than charged against OCR. The result — a signed, version-pinned, machine-comparable truth set and the `ocr_extraction_correctness_audit` — is the foundational correctness baseline of the whole program: it builds nothing and changes no OCR logic, it simply proves, scale-first and census-validated, whether the platform's baseline numbers are right or honestly missing.
