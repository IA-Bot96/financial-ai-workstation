# CV1 Sign-Off Template

**Status:** Attestation templates for CV1. No results, no measurements — blank templates to be completed during/after execution. All sign-offs pin `thresholds_version 1.0.0`, `truth_set_version`, `bundle_fingerprint`, `engine_version`.

---

## 1. Reviewer Sign-Off (one per reviewer, per issuer)

| Field | Entry |
|---|---|
| `reviewer_name` / `role` | __________ (qualified financial analyst) |
| `issuer` | lucky_cement / millat_tractors |
| `bundle_fingerprint` | __________ |
| `cells_reviewed` (ids / count) | __________ |
| `blind_first_attested` | ☐ I recorded and **locked Section A before** Section B was revealed for every cell. |
| `no_coi_attested` | ☐ I did not review cells my team produced. |
| `dispositions_complete` | ☐ Every reviewed cell has a disposition + direction + severity (or excluded). |
| `adjudication_flags_raised` | count + `adjudication_ref`s: __________ |
| `source_insufficient` / `indeterminate` | counts: __________ (excluded per CV0) |
| `signature` / `date` | __________ |

---

## 2. Adjudicator Sign-Off

| Field | Entry |
|---|---|
| `adjudicator_name` / `role` | __________ (senior financial analyst, independent) |
| `disputes_adjudicated` (`adjudication_id`s) | __________ |
| `dispute_type_breakdown` | scale __ · unit __ · multi_table __ · s1_dispute __ · source_ambiguity __ |
| `resolution_rules_applied_attested` | ☐ scale→units header · unit→label context · multi-table→primary-statement anchor. |
| `s1_handling_attested` | ☐ Every S1 had a second reviewer; uncorrected adjudicated S1 = Failure; corrected+root-caused S1 triggered a stratum **re-sample**. |
| `re_samples_triggered` (`re_sample_ref`s) | __________ |
| `unresolved → source_insufficient` | count: __________ |
| `signature` / `date` | __________ |

---

## 3. Census Completion Sign-Off

| Field | Entry |
|---|---|
| `census_cells_required` | Lucky 66 + Millat 66 (+ confirmed year-span adjustments) = __________ |
| `census_cells_reviewed` | __________ |
| `census_complete_attested` | ☐ Every required census `cell_id` reviewed (none skipped). |
| `adversarial_rows_appended` | scale-flagged ___ · note-vs-statement ___ · review-gated ___ · conflict ___ · missing-year ___ |
| `presence_cells_handled` | ☐ Aggregate presence-checks (total_debt/equity/long_term_debt) dispositioned per §4 (absent-as-discrete = confirmed). |
| `exclusions_recorded` | source_insufficient ___ · indeterminate ___ |
| `signature` (program lead) / `date` | __________ |

---

## 4. Truth-Set Publication Sign-Off

| Field | Entry |
|---|---|
| `truth_set_id` | ocr_extraction_lucky / ocr_extraction_millat |
| `truth_set_version` | __________ (semver) |
| `bundle_fingerprint` / `engine_version` / `thresholds_version` | __________ / __________ / 1.0.0 |
| `export_integrity_attested` | ☐ Every census `cell_id` present; non-excluded items carry `expected` + `actual` + `disposition`; comparators/tolerances set; version pins populated. |
| `schema_conformance_attested` | ☐ Exported 1:1 to `ocr_truth_set_schema.md`; deterministic-comparison-ready. |
| `harness_ready_attested` | ☐ Truth-set envelope ready for `platform_correctness_regression_harness` (CV5). |
| `append_versioned_attested` | ☐ Published append-only; not silently edited. |
| `signature` (program lead) / `date` | __________ |

---

## 5. Disposition → `ocr_extraction_correctness_audit` Handoff

On all four sign-offs complete, the published truth set is the input to `ocr_extraction_correctness_audit` (rates/CIs/bands — computed in execution, not here). This template authorizes **publication of the truth set**, not any correctness conclusion.

---

## 6. One-Line Note

Four attestations close CV1's review — reviewer (blind-first, COI-clear), adjudicator (rules applied, S1 re-sampled), census (complete, exclusions recorded), and publication (schema-conformant, version-pinned, harness-ready) — each pinned to the bundle and thresholds version, and none asserting a result; the measurement is the audit's job, downstream.
