# V1 vs V2 Comparison Workbook Specification

**Status:** Execution artifact. No code, no implementation, no OCR/validation redesign. Converts the approved comparison methodology into an analyst-executable workbook.
**Date:** 2026-06-04
**Authoritative:** OCR V2 Validation Execution Review · CV1 Protocol · CV1 Truth Set Schema · CV1 Truth Set Inventory · Thresholds Version 1.0.0.
**Scope:** Lucky-first; **66 census cells** (11 metrics × 6 years).
**Comparator:** `numeric_scale_aware` — equality requires **value AND scale** to match the truth (`scale_exact: true`).

**Workbook header block (top of file, one row each, all required):**
`workbook_id` · `truth_set_version` · `bundle_fingerprint` · `v1_engine_version` · `v2_engine_version` (= OCR_V2) · `thresholds_version` (= 1.0.0) · `comparison_date` · `validation_lead`.
**Sheets:** `comparison_matrix` · `v2_regression_report` · `v2_fix_report` · `summary` · `signoff`.

---

## SECTION A — `comparison_matrix`

One row per census cell (**exactly 66 rows**, no skips).

| Column | Type | Req? | Allowed values / source | Validation rule |
|---|---|---|---|---|
| `cell_id` | string | **Required** | truth set inventory id | unique; present for all 66; matches inventory |
| `issuer` | enum | **Required** | `lucky_cement` | constant this run |
| `metric` | enum | **Required** | one of the 11 canonical metrics | from inventory |
| `value_year` | int | **Required** | 2020–2025 | 6 years × 11 metrics = 66 |
| `truth_value` | number \| `source_insufficient` | **Required** | CV1 truth set | numeric, or the literal `source_insufficient` |
| `truth_scale` | enum | **Required** | `thousands` / `millions` / `units` / `n/a` | `n/a` only when `truth_value = source_insufficient` |
| `v1_value` | number \| `abstain` | **Required** | frozen V1 workbook | `abstain` if V1 emitted no value |
| `v1_scale` | enum | **Required** | as above | per V1 output |
| `v2_value` | number \| `abstain` | **Required** | V2 workbook (same fingerprint) | `abstain` if V2 marked `source_insufficient` |
| `v2_scale` | enum | **Required** | as above | per V2 output |
| `comparator_result_v1` | enum | **Required** (derived) | `MATCH` / `VALUE_MISMATCH` / `SCALE_MISMATCH` / `ABSTAIN_CORRECT` / `FABRICATION` | per comparator rules below |
| `comparator_result_v2` | enum | **Required** (derived) | same set | per comparator rules below |
| `classification` | enum | **Required** (derived) | the 5 allowed classes | per derivation matrix below; must be consistent with the two comparator results |
| `reviewer` | string | **Required** | reviewer id | COI-clear |
| `adjudicator` | string | Optional | ADJ id | **Required** when `classification = V2-regresses` or any `FABRICATION` |
| `notes` | string | Optional | free text | required when adjudicated |

### Comparator result rules (per side, vs truth)
- `MATCH` — value equal **and** scale equal to truth (`scale_exact`).
- `VALUE_MISMATCH` — value differs from truth.
- `SCALE_MISMATCH` — value digits match but scale differs (e.g. thousands vs full rupees) → **still a mismatch** under `numeric_scale_aware`.
- `ABSTAIN_CORRECT` — `truth_value = source_insufficient` **and** the system value = `abstain`.
- `FABRICATION` — `truth_value = source_insufficient` **but** the system emitted a number. *(Asymmetric tolerance: a false assertion where truth is insufficient is the worst outcome.)*

### Classification derivation matrix (deterministic — not analyst judgment)
| `comparator_result_v1` | `comparator_result_v2` | `classification` |
|---|---|---|
| any MISMATCH (`VALUE_`/`SCALE_`) **or** `FABRICATION` | `MATCH` | **V2-fixes-V1-error** |
| `FABRICATION` | `ABSTAIN_CORRECT` | **V2-fixes-V1-error** (false assertion → honest abstention) |
| `MATCH` | `MATCH` | **V2-matches-V1-correct** |
| `ABSTAIN_CORRECT` | `ABSTAIN_CORRECT` | **correct-abstention** |
| `MATCH` | any MISMATCH **or** `FABRICATION` | **V2-regresses** |
| `ABSTAIN_CORRECT` | `FABRICATION` | **V2-regresses** (fabrication subtype) |
| any MISMATCH | any MISMATCH | **both-wrong** |

**Cross-field validation:** `classification` MUST equal the matrix output for the two comparator results; any row where it does not is invalid and blocks the summary.

---

## SECTION B — `v2_regression_report`

One row per cell where `classification = V2-regresses` (**target: zero rows**).

| Field | Type | Req? | Allowed values |
|---|---|---|---|
| `cell_id` | string | **Required** | from matrix |
| `metric` | enum | **Required** | one of 11 |
| `value_year` | int | **Required** | 2020–2025 |
| `v1_status` | enum | **Required** | `correct` / `abstain_correct` |
| `v2_status` | enum | **Required** | `value_mismatch` / `scale_mismatch` / `fabrication` |
| `truth_status` | enum | **Required** | `value` / `source_insufficient` |
| `regression_type` | enum | **Required** | `value` / `scale` / `fabrication_on_abstention` |
| `root_cause` | string | **Required** | candidate/decision that produced the wrong value |
| `governance_layer` | enum | **Required** | `capture` / `statement` / `scale` / `entity` / `selection` |
| `severity` | enum | **Required** | `S1` / `S2` / `S3` / `S4` (per thresholds 1.0.0; fabrication ⇒ S1) |
| `corrective_action` | string | **Required** | remediation before re-comparison |

**Rule:** any non-empty `v2_regression_report` ⇒ **comparison fails; cutover blocked** (Step 3 halt).

---

## SECTION C — `v2_fix_report`

One row per cell where `classification = V2-fixes-V1-error`.

| Field | Type | Req? | Allowed values |
|---|---|---|---|
| `cell_id` | string | **Required** | from matrix |
| `metric` | enum | **Required** | one of 11 |
| `value_year` | int | **Required** | 2020–2025 |
| `v1_error_type` | enum | **Required** | `consolidated_basis` / `investee` / `analysis_table` / `note` / `summary` / `scale_corruption` / `fabrication` |
| `v2_resolution_type` | enum | **Required** | `correct_value` / `correct_abstention` |
| `failure_class` | enum | **Required** | `statement_basis` / `investee_contamination` / `analysis_table_contamination` / `note_contamination` / `summary_table_contamination` / `scale_governance` / `source_selection` |
| `governance_layer` | enum | **Required** | `statement` / `scale` / `entity` / `selection` |
| `notes` | string | Optional | provenance / oracle cross-ref |

**Coverage rule:** every CV1-documented statement-selection + scale error cell must appear here (or be explained in `notes` if no longer reproducible).

---

## SECTION D — `summary` (auto-computed from `comparison_matrix`)

| Metric | Definition |
|---|---|
| `total_cells` | COUNT(rows) — **must = 66** |
| `v2_fixes` | COUNT(`classification = V2-fixes-V1-error`) |
| `v2_matches` | COUNT(`classification = V2-matches-V1-correct`) |
| `v2_regresses` | COUNT(`classification = V2-regresses`) — **must = 0** |
| `both_wrong` | COUNT(`classification = both-wrong`) |
| `correct_abstentions` | COUNT(`classification = correct-abstention`) |
| `fix_rate` | `v2_fixes / (v1_errors)` where `v1_errors = v2_fixes + both_wrong` (cells V1 got wrong) |
| `regression_rate` | `v2_regresses / (v1_correct)` where `v1_correct = v2_matches + correct_abstentions` (cells V1 got right) |

**Integrity checks (must all pass):** `total_cells = 66`; `v2_fixes + v2_matches + v2_regresses + both_wrong + correct_abstentions = 66`; `v2_regresses = 0`; every `classification` equals its derivation-matrix output.

---

## SECTION E — `signoff`

| Signoff | Owner | Attestation | Gate |
|---|---|---|---|
| **Reviewer Signoff** | Reviewer(s) | "I verified the comparator result and classification for my assigned cells against the source PDF; all `V2-regresses` and `both-wrong` cells were PDF-checked." | per-reviewer; pinned to `bundle_fingerprint` |
| **Adjudicator Signoff** | Adjudicator | "I adjudicated every `V2-regresses` and `FABRICATION` row; resolutions and severities recorded; no classification overridden outside the derivation matrix." | required if any such row exists |
| **Validation Lead Signoff** | Validation Lead | "All 66 cells present; integrity checks pass; summary computed; reports complete and consistent." | blocks cutover review until signed |
| **Cutover Recommendation** | Validation Lead + Adjudicator | One of: **PROCEED** (`v2_regresses = 0`, fixes cover documented errors, zero fabrication-on-abstention) / **HALT** (any regression or fabrication) | feeds Step 6 of the execution order |

All signoffs pin `truth_set_version`, `bundle_fingerprint`, `v2_engine_version`, `thresholds_version 1.0.0`.

---

## Final Question — Is this workbook alone sufficient?

**Yes — for the V1 vs V2 comparison defined by the Validation Execution Review (Task 2 of that review).** This workbook provides every input column (truth/V1/V2 value+scale), the exact `numeric_scale_aware` comparator rules, a **deterministic classification derivation matrix** (so classification is computed, not judged), the regression and fix reports the methodology requires, the auto-computed summary with the hard `v2_regresses = 0` and `total_cells = 66` integrity gates, and the reviewer/adjudicator/lead signoffs plus the PROCEED/HALT cutover recommendation. An analyst can populate it and reach a defensible comparison verdict without any further design.

**Scope boundary (not a deficiency):** this workbook executes **the comparison only**. The full CV1 re-run (blind census, Wilson/certification) and downstream revalidation are separate artifacts in the execution package; this sheet feeds them but does not replace them. Within its stated job — comparing V1 and V2 across all 66 cells and producing a signed cutover recommendation — **this workbook is sufficient and immediately executable.**

---

## One-Paragraph Verdict

This specification is enough to run the V1-vs-V2 comparison tomorrow: it fixes a single 66-row `comparison_matrix` keyed to the CV1 truth-set cells, captures truth, V1, and V2 as value-plus-scale, derives each side's comparator result under the numeric-scale-aware rule (where a scale mismatch and a fabricated value over a source-insufficient truth are both failures), and then assigns one of the five classifications by a deterministic matrix rather than analyst opinion — so two analysts on the same data must reach the same verdict. The regression and fix sheets capture root cause, governance layer, and severity; the summary auto-computes the counts and enforces the hard gates that there are exactly sixty-six cells and zero regressions; and the signoff sheet turns the result into a PROCEED-or-HALT cutover recommendation pinned to the bundle fingerprint and thresholds 1.0.0. It deliberately does only the comparison — the CV1 re-run and downstream revalidation remain their own artifacts — but for that job it is complete, self-checking, and executable without any further architecture, governance, or design work.
