# OCR V2 — Comparison & Validation Execution Package

**Status:** Execution package only. No code, no implementation, no OCR/governance/selection/workbook/MSIL redesign. Converts the approved validation review into an analyst-runnable package.
**Date:** 2026-06-04
**Authoritative:** OCR V2 Validation Execution Review · Cutover Readiness Review · Pre-Cutover Validation Review · Regression Oracle · CV1 Protocol · CV1 Truth Set Schema · CV1 Truth Set Inventory · CV1 Reviewer Guide · CV1 Execution Checklist · CV1 Signoff Template · Thresholds Version 1.0.0.
**Determination carried in:** READY_FOR_VALIDATION · NOT_READY_FOR_CUTOVER.
**Scope of this run:** **Lucky-first.** (Millat deferred to a second cycle — see Task 7.)

**Roles (assign before Step 1):**
- **Validation Lead (VL)** — owns inputs, pinning, matrices, summary, go/no-go.
- **Reviewers (R1…Rn)** — qualified financial analysts, **COI-clear** (not OCR V2 implementers/their team).
- **Adjudicator (ADJ)** — senior independent analyst.
- **Gatekeeper (GK)** — holds Section-B (V2) values; not a reviewer.
- **Downstream Owners** — MSIL / FVE / QAE / Query leads.

---

## TASK 1 — V1 vs V2 Comparison Package

### Inputs
- **V1 workbook** — frozen V1 output, pinned to the Lucky bundle fingerprint.
- **V2 workbook** — OCR V2 output over the **same pinned bundle**.
- **CV1 truth set** — 66 cells (11 metrics × 6 years), each with verified value + scale + disposition (`ocr_truth_set_schema`).
- **Source PDFs** — the exact Lucky report matching the fingerprint.

### Workflow
1. **Preparation (VL)** — confirm V1 + V2 generated over the *same* fingerprint; load the truth set; verify 66 cells present; lock all three as read-only inputs.
2. **Comparison (VL)** — for each of the 66 cells, record `(V1_value, V2_value, truth_value, truth_disposition)`; apply the **`numeric_scale_aware`** comparator (value **and** scale, `scale_exact:true`) for V1-vs-truth and V2-vs-truth.
3. **Classification (VL)** — assign one class per cell (table below).
4. **Adjudication (ADJ)** — every `V2-regresses` and every disputed comparator verdict is adjudicated (scale→units header; multi-table→primary-statement anchor; investee→MSIL identity).
5. **Reporting (VL)** — emit the four required outputs; VL + ADJ sign off.

### Per-cell classification
| Class | Rule |
|---|---|
| **V2-fixes-V1-error** | V1 ≠ truth, V2 = truth |
| **V2-matches-V1-correct** | V1 = truth, V2 = truth |
| **V2-regresses** | V1 = truth, V2 ≠ truth — **critical; target ∅** |
| **both-wrong** | V1 ≠ truth, V2 ≠ truth |
| **correct-abstention** | truth = source_insufficient **and** V2 marks `source_insufficient` (V2 fabricating a value here = a regression, logged separately) |

### Ownership / responsibilities / signoff
- **VL** owns the matrix, classification, and summary.
- **Reviewers** verify comparator verdicts on a sampled subset + all `V2-regresses` and `both-wrong` cells against the PDF.
- **ADJ** adjudicates all `V2-regresses`, fabrication-on-abstention, and disputes.
- **Signoff:** VL + ADJ jointly sign the comparison summary.

### Required outputs
- `comparison_matrix.xlsx` — 66 rows: cell_id, metric, year, V1_value, V2_value, truth_value, scale check, V1-verdict, V2-verdict, class.
- `v2_fix_report.md` — every `V2-fixes` cell mapped to its CV1 failure class (statement_basis / analysis-table / note / investee / scale).
- `v2_regression_report.md` — every `V2-regresses` + fabrication-on-abstention cell with root cause (governance layer / candidate); **must be empty to proceed**.
- `comparison_summary.md` — set counts, fix-rate, regression count, correct-abstention count, success/rollback determination.

### Success / rollback
- **Success:** `V2-regresses = ∅`; `V2-fixes` covers the documented CV1 statement-selection + scale error cells; zero fabrication on source-insufficient cells.
- **Rollback (halt, no cutover):** any `V2-regresses` baseline cell; any fabricated value on a source-insufficient cell; inputs not fingerprint-matched.

---

## TASK 2 — Full CV1 Re-Run Package

The engine-under-test changes (V2 is Section B); the **CV1 protocol is unchanged.**

### Analyst assignments
- [ ] Reviewers named, **COI-clear**; census grid (66 cells) split by metric-block. *(VL)*
- [ ] **S1 second-reviewer** routing established (every scale-flagged / note-vs-statement / baseline-corrected cell → second independent reviewer). *(VL)*
- [ ] ADJ named, independent of reviewers. *(VL)*
- [ ] GK named (holds V2 Section-B values). *(VL)*

### Blind review process
- [ ] **Blind packs** prepared per reviewer — Section A blanks + `cited_source_page` + `statement_to_check`, **no system values**. *(VL/GK)*

### Section A lock procedure
- [ ] Reviewer records independent reading from the PDF into Section A; **Section A locked + timestamped** per cell. *(R → GK)*

### Section B reveal procedure
- [ ] GK reveals V2's value (Section B) **only after** Section A is locked. *(GK)*
- [ ] Post-reveal edit to a locked Section A → cell **re-assigned** to a different reviewer. *(GK)*

### Adjudication workflow
- [ ] Disputes routed to ADJ; rules: scale→units header; multi-table→primary-statement anchor; investee→MSIL identity. *(ADJ)*
- [ ] Every **S1** second-reviewed; uncorrected adjudicated S1 = **Failure**; corrected+root-caused S1 → **stratum re-sample**. *(ADJ)*

### Severity workflow
- [ ] Disposition × metric-class → severity (S1/S2/S3/S4) via the frozen lookup. *(R/ADJ)*
- [ ] Asymmetric tolerance enforced: false **assertion** = S1; honest **source_insufficient** = tolerable. *(ADJ)*

### Dispute workflow
- [ ] Each dispute carries an `adjudication_ref`; resolution recorded; re-samples logged with `re_sample_ref`. *(ADJ)*

### Publication workflow
- [ ] Census dispositions exported 1:1 to `ocr_truth_set_schema`; version pins populated (`thresholds_version 1.0.0`, `truth_set_version`, `bundle_fingerprint`, `engine_version=OCR_V2`). *(VL)*
- [ ] Four CV1 sign-offs completed (reviewer / adjudicator / census-completion / publication). *(per Signoff Template)*

### Census completion checklist
- [ ] All **66** cells dispositioned (none skipped). *(VL)*
- [ ] Presence cells (Total Debt etc.) handled per aggregate-presence rule. *(R)*
- [ ] Exclusions recorded (`source_insufficient` / `source_ambiguous`). *(VL)*

### Calibration checklist
- [ ] Calibration set completed + reconciled before the main pass; calibration sign-off recorded. *(R + ADJ)*

### Readiness checklist (start gate)
- [ ] Reviewers/ADJ/GK assigned & COI-clear; blind packs ready; Lucky PDF↔fingerprint confirmed; V2 workbook pinned; **OCR V2 stored-value scale convention documented**; calibration reconciled. *(VL)*

### Threshold / Wilson / certification
- [ ] S1 target 0; S2 ≤ 5%; S3 ≤ 20%; S4 informational.
- [ ] S1 **Wilson 95% interval** computed over evaluable cells and recorded.
- [ ] **Disposition:** CERTIFIED (Wilson-upper ≤ 0.5% — *requires pooled multi-issuer n*) / **CONDITIONAL** (0–bounded S1, bands met, single-issuer n insufficient to certify at 0.5% — *the expected Lucky-first outcome*) / NOT_CERTIFIED (any uncorrected adjudicated S1, or bands breached).

---

## TASK 3 — Downstream Revalidation Package

| Engine | Inputs | Execution steps | Expected outputs | Regression criteria | Blocking criteria | Required report |
|---|---|---|---|---|---|---|
| **MSIL** | V2 export bundle (annual_report source) | Re-ingest; run MSIL suite + entity-resolution on V2 values | Same contract; cleaner values; `entity_scope` consumed additively | Contract break; entity mis-resolution; suite failure | Any contract break or entity-identity regression | `msil_revalidation_report.md` |
| **FVE** | V2 baseline values | Re-run HSIG + NAG on V2 baselines | **More `clean`** baselines; verdicts shift beneficially | A should-pass baseline → `not_validatable`; a corrupted value passes HSIG | Should-pass baseline fails, or wrong value admitted as baseline | `fve_revalidation_report.md` |
| **QAE** | V2 narrative/insights | Re-ingest; run QAE suite | Minimal change; investee narrative curbed | Theme/scorecard contract break | Any QAE contract break | `qae_revalidation_report.md` |
| **Query** | V2 canonical values + provenance | Re-run retrieval/citation/answer set | Citations point to correct values; answers improve | A previously-correct answer now wrong; citation→wrong value | Any answer/citation correctness regression | `query_revalidation_report.md` |

Owner per row = the respective Downstream Owner; **VL aggregates** the four reports into `downstream_revalidation_summary.md`.

---

## TASK 4 — Deliverable Inventory

| Artifact | Owner | Input | Output | Required signoff |
|---|---|---|---|---|
| `comparison_matrix.xlsx` | Validation Lead | V1 + V2 + Truth Set | 66-cell comparison matrix | VL + ADJ |
| `v2_fix_report.md` | Validation Lead | comparison_matrix | Fixes mapped to failure class | VL |
| `v2_regression_report.md` | Validation Lead | comparison_matrix | Regression set (target ∅) + root cause | VL + ADJ |
| `comparison_summary.md` | Validation Lead | comparison_matrix | Counts, fix-rate, determination | VL + ADJ |
| CV1 blind packs | Validation Lead / GK | Truth set + PDF | Per-reviewer Section-A packs | VL |
| CV1 census dispositions | Reviewers | Blind packs + PDF + V2 Section B | 66 dispositioned cells | Reviewers |
| CV1 adjudication log | Adjudicator | Disputes / S1s | Resolutions + re-samples | ADJ |
| `cv1_v2_truth_set` (published) | Validation Lead | Census dispositions | Schema-conformant, version-pinned truth set | VL (publication signoff) |
| `cv1_v2_certification.md` | Validation Lead | Census + Wilson | CERTIFIED/CONDITIONAL/NOT_CERTIFIED | VL + ADJ |
| `msil/fve/qae/query_revalidation_report.md` | Downstream Owners | V2 bundle | Pass/regression per engine | Each Downstream Owner |
| `downstream_revalidation_summary.md` | Validation Lead | 4 reports | Aggregate downstream verdict | VL |
| `ocr_v2_cutover_evidence_package.md` | Validation Lead | All above | Complete evidence dossier | VL + ADJ + Downstream Owners |

---

## TASK 5 — Cutover Evidence Package

Before OCR V1 may be retired (for the declared scope), all of the following must **exist and be signed**:

- **Comparison evidence:** `comparison_matrix.xlsx` (all 66 cells), `v2_regression_report.md` = **empty**, `v2_fix_report.md` covering the CV1 statement-selection + scale error cells, `comparison_summary.md` (success).
- **CV1 evidence:** published `cv1_v2_truth_set`, adjudication log (zero uncorrected adjudicated S1), `cv1_v2_certification.md` = **CERTIFIED or CONDITIONAL**, S1 Wilson interval recorded.
- **Recall evidence:** EPS 2020–2023 captured **or** explicitly `source_insufficient`; capture census shows no required baseline metric silently absent.
- **Multi-candidate evidence:** observed N>2 candidate cells; AMBIGUOUS and NO_SELECTION paths exercised and behaving per contract.
- **Output-equivalence evidence:** workbook canonical-only on full census; export `value_mutations = 0`, provenance preserved, `contract_preserved = true`.
- **Downstream evidence:** `downstream_revalidation_summary.md` — MSIL/FVE/QAE/Query all non-regressing.
- **Rollback evidence:** frozen V1 retained and re-activatable through a declared stability window; registry append-only confirmed.

---

## TASK 6 — Execution Order

```
Step 1  Prepare comparison inputs (pin V1 + V2 to same fingerprint; load truth set + PDF)        [VL]
Step 2  Run V1 vs V2 comparison (matrix → classify → adjudicate → 4 reports)                      [VL + ADJ]
Step 3  Resolve regressions — v2_regression_report MUST be empty; halt + root-cause if not        [VL + ADJ]
Step 4  Run full CV1 re-run against V2 (calibrate → blind census → adjudicate → certify → publish) [R + ADJ + GK + VL]
Step 5  Run downstream revalidation (MSIL, FVE, QAE, Query → 4 reports → summary)                 [Downstream Owners + VL]
Step 6  Cutover review — assemble evidence package; verify Task-6 checklist green for scope        [VL + ADJ]
Step 7  Authorize replacement — Lucky-first cutover on CONDITIONAL+empty-regression; V1 frozen     [VL sign + stakeholders]
```

Gate between steps: **Step 3 blocks Step 4** (no point certifying a regressing engine); **Steps 4 + 5 both feed Step 6**; **Step 6 must be fully green before Step 7.**

---

## TASK 7 — Final Determination

**If this execution package is completed successfully (Lucky-first):**

# LIMITED_EVIDENCE_REMAINING

**Justification.** Completing this package successfully produces everything required to authorize a **Lucky-first cutover on a CONDITIONAL disposition** with an empty regression set, validated recall, exercised multi-candidate paths, preserved output-equivalence, clean downstream revalidation, and an intact rollback path — sufficient to retire V1 **for the Lucky scope**. Two evidence items remain, both already known and bounded, neither resolvable within this Lucky-first run:
1. **CERTIFIED-grade statistical confidence.** Under thresholds 1.0.0 the Wilson 0.5% bar is unreachable on a single 66-cell census even with zero S1; full **CERTIFIED** status requires **pooling further issuer censuses** — an accumulation goal, not a defect of this run.
2. **Cross-issuer generalization (Millat).** This package is scoped Lucky-first; Millat requires its own CV1 census cycle before V1 is retired for *all* issuers.

Additionally, the **post-cutover stability window** (V1 retained, re-activatable) must elapse before V1 is physically retired. The remaining evidence is therefore *limited and pre-identified* — a second issuer cycle plus multi-issuer accumulation toward CERTIFIED — not substantial or open-ended. For the Lucky scope, completion of this package leaves **no blocking evidence**; for global V1 retirement, the Millat cycle and CERTIFIED accumulation remain.

---

## One-Paragraph Verdict

This package is executable by analysts tomorrow: it pins V1 and V2 to one fingerprint and classifies all sixty-six cells into fixes, matches, regressions, both-wrong, and correct-abstentions with the numeric-scale-aware comparator and an adjudicator gate that treats any regression — or any fabricated value where the truth is source-insufficient — as a hard stop; it reuses the frozen CV1 protocol unchanged, with blind Section-A locks before Section-B reveals, S1 second-review, calibration, and a thresholds-1.0.0 certification step; and it reruns MSIL, FVE, QAE, and Query with explicit regression and blocking criteria, all assembled into a signed cutover evidence dossier ordered prepare → compare → resolve-regressions → CV1-rerun → downstream → cutover-review → authorize. Completed successfully for Lucky, it leaves **LIMITED_EVIDENCE_REMAINING** — only the Millat cycle and the multi-issuer accumulation needed to convert a single-issuer CONDITIONAL into a pooled CERTIFIED, plus the stability window — which is exactly the honest, bounded residual the Wilson math and the Lucky-first scope predicted, and nothing further needs to be designed for the run to begin.
