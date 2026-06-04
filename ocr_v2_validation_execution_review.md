# OCR V2 — Validation Execution Review

**Status:** Validation planning & cutover-readiness review only. No code, no implementation, no OCR/governance/selection/workbook/MSIL redesign.
**Date:** 2026-06-04
**Authoritative:** OCR V2 Architecture Review · Migration Review · Contracts · Implementation Plan · Regression Oracle · Cutover Readiness Review · CV1 Protocol · CV1 Truth Set Inventory · Thresholds Version 1.0.0.
**Current status (input):** P0–P7 implemented; OCR + MSIL suites passing; 15/15 oracle cases passing; **READY_FOR_COMPARISON**; cutover NOT authorized.
**Objective:** define exactly how OCR V2 must be validated before it may replace OCR V1.

---

## Task 1 — Validation Obligations (reconstructed from existing reviews)

| Obligation (evidence: Cutover Readiness Review §7/§9, Pre-Cutover §5) | Class |
|---|---|
| Full CV1 66-cell census re-run on V2 = CERTIFIED or CONDITIONAL (thresholds 1.0.0) | **Must-Before-Cutover** |
| `V2-regresses` set empty (no regression on V1-correct cells) | **Must-Before-Cutover** |
| Capture recall validated — `missing_extraction` (EPS 2020–2023) found, or honestly `source_insufficient` | **Must-Before-Cutover** |
| Multi-candidate selection paths exercised (N>2, AMBIGUOUS, NO_SELECTION) | **Must-Before-Cutover** |
| Workbook + OCR→MSIL output-equivalence to V1 confirmed on the full census | **Must-Before-Cutover** |
| Downstream revalidation clean (MSIL/FVE/QAE/Query) | **Must-Before-Cutover** |
| Cross-issuer handled (Millat) — or cutover explicitly scoped Lucky-first | **Must-Before-Cutover** |
| Pin frozen V1 baseline + run V2 over the same pinned Lucky bundle | **Can-Resolve-During-Validation** (prerequisite to comparison) |
| Comparison methodology defined against the 66-cell truth set | **Can-Resolve-During-Validation** |
| Expand oracle with multi-candidate + Millat cases; mechanized comparison tooling | **Can-Resolve-During-Validation** |
| Non-core metric-class handling | **Can-Resolve-During-Validation** |
| Candidate drill-down in Query; broader issuer generalization | **Post-Cutover** |
| V1 retirement after a stability window | **Post-Cutover** |

---

## Task 2 — V1 vs V2 Comparison Methodology

**Inputs:** (a) frozen V1 workbook output, pinned to the Lucky bundle fingerprint; (b) OCR V2 workbook output over the **same pinned bundle**; (c) the CV1 truth set (66 cells: 11 metrics × 6 years) carrying the verified-correct value + scale + disposition per cell.

**Per-cell classification** (using the `numeric_scale_aware` comparator — value **and** scale, `scale_exact:true`):

| V1 vs truth | V2 vs truth | Class |
|---|---|---|
| V1 ≠ truth | V2 = truth | **V2-fixes-V1-error** |
| V1 = truth | V2 = truth | **V2-matches-V1-correct** |
| V1 = truth | V2 ≠ truth | **V2-regresses** *(critical — must be empty)* |
| V1 ≠ truth | V2 ≠ truth | **both-wrong** |

**Source-insufficient cells** (the truth set's excluded cells — e.g. Total Debt all years; Total Liabilities & Long-Term Debt 2020–2023): the correct behavior is **honest abstention**. V2 marking such a cell `source_insufficient` = **correct-abstention** (counts as match, not regression). **V2 fabricating a value where the truth is source-insufficient = a regression worse than V1's honest gap** (asymmetric-tolerance: a false assertion is S1).

**Outputs:** per-cell comparison matrix; the four set counts; the **`V2-regresses` set** (target ∅); **fix-rate** = `V2-fixes / (V1-errors)`; regression count; correct-abstention count.

**Required reports:**
1. **Comparison matrix** — every census cell with V1 value, V2 value, truth value, comparator verdict, class.
2. **Regression report** — every `V2-regresses` cell with root cause (which governance layer / candidate).
3. **Fix report** — every `V2-fixes` cell mapped to its CV1 failure class (statement_basis / analysis-table / note / investee / scale).

**Success criteria:** `V2-regresses = ∅`; `V2-fixes` covers the documented CV1 statement-selection + scale error cells; V2 abstains correctly on all source-insufficient cells (no fabrication).

**Rollback criteria (halt, no cutover):** any `V2-regresses` cell on a baseline metric; any V2 fabricated value on a source-insufficient cell; comparison cannot run on a fingerprint-matched bundle.

---

## Task 3 — Full CV1 Re-Run Against OCR V2

The **engine under test changes; the CV1 protocol does not.** Re-run the frozen CV1 protocol with V2's workbook as the system-under-test value (Section B).

**Analyst workflow:** qualified financial analysts, **COI-clear** (not the OCR V2 implementers/their team); census grid split by issuer/metric-block; each cell reviewed against the exact source PDF (fingerprint-matched).

**Blind requirements:** Section A (analyst's independent reading from the PDF) **locked + timestamped before** Section B (V2's value) is revealed by a gatekeeper holding the V2 values; any post-reveal edit to a locked Section A → cell re-assigned to a different reviewer.

**Adjudication:** a **senior independent analyst** adjudicates disputes — scale → units header; multi-table → primary-statement anchor; investee → MSIL identity. Every **S1** gets a second independent reviewer; an uncorrected adjudicated S1 = **Failure**; a corrected + root-caused S1 triggers a **stratum re-sample**.

**Census evaluation:** all **66 cells** dispositioned (confirmed / source_insufficient / source_ambiguous / …) via the `numeric_scale_aware` comparator; aggregate-presence rule applied for the presence cells (Total Debt etc.).

**Threshold evaluation (thresholds 1.0.0):** S1 target **0**; S2 ≤ **5%**; S3 ≤ **20%**; S4 informational. Severity by disposition × metric-class lookup.

**Wilson interval evaluation:** compute the Wilson 95% interval on the S1 proportion over **evaluable** cells. **Critical, honest constraint:** thresholds 1.0.0 sets the S1 bar at *Wilson-CI-upper ≤ 0.5%*, which is **mathematically unreachable on a single-issuer ~50-evaluable-cell census even with 0 observed S1** — 0/50 yields a Wilson upper bound of ≈7%, and reaching ≤0.5% with zero errors requires **n ≈ 760+ evaluable cells** (i.e. many pooled issuer-censuses). Therefore:
- A clean single-issuer (Lucky) re-run with **0 observed S1** can reach **CONDITIONAL**, not CERTIFIED.
- **CERTIFIED at the 0.5% bar is a multi-issuer accumulation target** (Lucky + Millat + further issuers), not achievable from Lucky alone.

**Certification determination:**
- **CERTIFIED** — S1 Wilson-upper ≤ 0.5% (requires the pooled census n) **and** S2/S3 within bands **and** no uncorrected adjudicated S1.
- **CONDITIONAL** — 0 (or bounded) observed S1 with documented mitigation, S2/S3 within bands, but census n insufficient to certify at 0.5% (the expected Lucky-first outcome).
- **NOT_CERTIFIED** — any uncorrected adjudicated S1, or S2/S3 out of band.

---

## Task 4 — Coverage Gaps

| Gap | Risk | Probability | Impact | Validation method |
|---|---|---|---|---|
| **Capture recall** — missing EPS 2020–2023, uncaptured candidates, source_insufficient handling | **HIGH** (selection cannot recover an uncaptured candidate) | **MED–HIGH** (EPS was a confirmed V1 miss; V2 recall unproven) | **HIGH** (a missing baseline metric → FVE baseline gap) | Full CV1 capture census: confirm V2 captures EPS or marks `source_insufficient`; measure captured-candidates vs PDF-truth presence per cell |
| **Multi-candidate selection** — N>2 sets, AMBIGUOUS path, NO_SELECTION path | **MED–HIGH** (oracle only has 2-candidate pairs) | **HIGH** (real extraction always yields N>2) | **MED** (mis-ordered precedence → wrong pick; or honest abstention reducing coverage) | Run V2 over the full real Lucky bundle; inspect selection decisions on N>2 cells; explicitly exercise AMBIGUOUS + NO_SELECTION; expand oracle |
| **Cross-issuer — Lucky** | **LOW** | — | — | Proven for represented classes; covered by the Lucky CV1 re-run |
| **Cross-issuer — Millat** | **MED** (unvalidated issuer; different report structure) | **MED** | **MED** (generalization unknown) | Millat CV1 census re-run; **or** scope cutover Lucky-first and defer Millat to a second validation cycle |

---

## Task 5 — Downstream Revalidation Plan (no redesign)

| Engine | What must be rerun | Expected change | What constitutes regression | What blocks cutover |
|---|---|---|---|---|
| **MSIL** | Re-ingest the V2 bundle (annual_report source) | Same contract; cleaner values; `entity_scope` additive | MSIL test failure; contract break; entity mis-resolution | Any MSIL contract break or entity-identity regression |
| **FVE** | Re-run HSIG on V2 baselines + NAG roles | **More `clean`** baselines (27+14 corruptions gone); HSIG verdicts shift beneficially | A previously-clean baseline becomes `not_validatable`; a corrupted value passes HSIG | A should-pass baseline now fails, or a wrong value is admitted as baseline |
| **QAE** | Re-ingest narrative/insights | Minimal (narrative path largely separate); `entity_scope` curbs investee narrative | Theme/scorecard contract break | Any QAE contract break |
| **Query** | Re-run retrieval/citation/answers | Citations point to correct values; answer correctness improves | A previously-correct answer now wrong; citation points to wrong value | Any answer/citation correctness regression |

---

## Task 6 — Cutover Readiness Checklist (objectively measurable)

```
COMPARISON
[ ] V1 baseline output pinned to the Lucky bundle fingerprint
[ ] V2 output generated over the SAME pinned bundle
[ ] Comparison matrix produced for all 66 census cells
[ ] V2-fixes set covers the documented CV1 statement-selection + scale error cells
[ ] V2-regresses set = EMPTY
[ ] Zero V2-fabricated values on source-insufficient cells (honest abstention preserved)

CV1 RE-RUN (thresholds_version 1.0.0)
[ ] All 66 cells dispositioned under blind-first protocol (Section A locked before B)
[ ] Every S1 second-reviewed; zero uncorrected adjudicated S1
[ ] S2 ≤ 5%   [ ] S3 ≤ 20%
[ ] S1 Wilson 95% interval computed and recorded
[ ] CV1 disposition = CERTIFIED or CONDITIONAL

CAPTURE RECALL
[ ] EPS 2020–2023 captured, OR explicitly marked source_insufficient
[ ] No required baseline metric silently absent (capture census complete)

MULTI-CANDIDATE
[ ] N>2 candidate cells observed in selection decisions
[ ] AMBIGUOUS path exercised and behaves per contract
[ ] NO_SELECTION path exercised and behaves per contract

OUTPUT EQUIVALENCE
[ ] Workbook canonical-only on full census (no candidate leakage)
[ ] OCR→MSIL export: value_mutations = 0; provenance preserved for all cells; contract_preserved = true

DOWNSTREAM
[ ] MSIL re-ingest: contracts intact, suite green
[ ] FVE: no should-pass baseline regressed; no wrong value admitted
[ ] QAE: contracts intact
[ ] Query: no answer/citation correctness regression

SCOPE & ROLLBACK
[ ] Cutover scope declared (Lucky-first vs Lucky+Millat)
[ ] Frozen V1 rollback path confirmed available through a stability window
```

When every box is checked, replacement of OCR V1 is authorized **for the declared scope**.

---

## Task 7 — Recommendation

### READY_FOR_VALIDATION — **YES**

OCR V2 has earned the right to begin **V1 vs V2 comparison**, the **full CV1 re-run**, and **downstream revalidation**. Justification: implementation is complete through P7 (OCR + MSIL suites passing); the engine demonstrably corrects the 15 represented failure classes end-to-end (15/15 correct, deterministic, no ranking) and delivers through the frozen MSIL contract with zero value mutation; rollback is intact (V1 frozen, registry append-only, no MSIL schema change). The remaining obligations are precisely what these activities measure, so none of them block *entry* to validation.

### READY_FOR_CUTOVER — **NOT_READY**

OCR V2 has **not** earned cutover. Justification: every Task-1 Must-Before-Cutover obligation is, by definition, unproven until the validation stage runs — there is no full-census S1 result, no `V2-regresses` measurement, no capture-recall evidence (the EPS gap specifically remains open), no multi-candidate-path exercise, and no downstream revalidation. Furthermore, under thresholds 1.0.0 the **best achievable outcome from a Lucky-only re-run is CONDITIONAL, not CERTIFIED** (the Wilson 0.5% bar needs a pooled multi-issuer census); cutover should therefore be authorized **Lucky-first on a CONDITIONAL disposition with an empty `V2-regresses` set and preserved abstention**, with CERTIFIED pursued as a multi-issuer accumulation goal. Cutover is authorized only when the Task-6 checklist is fully green for the declared scope.

---

## One-Paragraph Verdict

OCR V2 is ready to be *validated*, not yet to *replace*: it is a complete, tested, parallel-built engine that corrects every represented CV1 failure class and reaches MSIL through the frozen contract without mutation, so it has plainly earned entry to the V1↔V2 comparison, the full CV1 re-run, and downstream revalidation — **READY_FOR_VALIDATION**. It has **NOT** earned cutover, because the obligations that authorize replacement — an empty regression set across all sixty-six cells, a CV1 disposition of certified or conditional, proof that capture now recovers the missing EPS years or honestly abstains, exercised multi-candidate and ambiguity paths, and clean FVE/MSIL/QAE/Query revalidation — are exactly the things the validation stage exists to measure and remain unproven until it runs. The one structural truth to carry into that stage is that thresholds 1.0.0's Wilson upper-bound of 0.5% is unreachable on a single sixty-six-cell census even with zero S1 errors, so the honest and achievable basis for a first cutover is a **Lucky-first CONDITIONAL** disposition with an empty regression set and preserved honest-abstention, with full CERTIFICATION earned later by pooling further issuer censuses — run the validation stage with V1 frozen behind it, and let the checklist, not optimism, authorize the replacement.
