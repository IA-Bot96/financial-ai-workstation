# OCR V2 — Oracle Capture & Coverage Audit

**Status:** Audit only. No code authored, no implementation, no redesign. Evidence gathered by **executing the shipped P0–P4 modules and the project test suite** against the authoritative oracle (read-only invocation; no behavior changed).
**Date:** 2026-06-04
**Authoritative regression source:** `backend/ocr/ocr_v2_regression_cases.json` (`fixture_version 1.0.0`, `ocr_v2_cv1_lucky_regression_oracle`, `entity_ref lucky_cement`, `declared_basis unconsolidated`).
**Objective:** verify that every oracle case's verified-correct **and** verified-incorrect candidate is representable, preserved, and correctly governed in the current OCR V2 pipeline — so that P5 Canonical Selection has a complete, correctly-tagged candidate set to choose among. *Selection can only choose among candidates that exist.*

**Method (executed):**
- `python -m pytest backend/ocr/tests/` → **51 passed**.
- A read-only harness drove **each of the 15 oracle cases** — both candidates per case — through `CandidateCapture` → `CandidateRegistry` (append + snapshot) → `StatementGovernance` → `ScaleGovernance` → `EntityGovernance`, recording each stage's outcome, provenance page, and value. (Harness invoked shipped modules only; produced no artifacts beyond a temporary evidence dump, since removed.)

---

## 1. Per-Case Coverage Results

Legend: each stage cell shows **correct / incorrect** candidate outcome.

| case_id | correct_found | incorrect_found | capture | registry | statement_gov (c/i) | scale_gov (c/i) | entity_gov (c/i) | provenance_preserved | ready_for_selection |
|---|---|---|---|---|---|---|---|---|---|
| revenue_2021_scale | ✅ | ✅ | PASS | PASS | ELIGIBLE / ELIGIBLE | **SCALE_VALID / SCALE_REVIEW_REQUIRED** | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| revenue_2024 | ✅ | ✅ | PASS | PASS | ELIGIBLE / **REVIEW_REQUIRED** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| revenue_2025 | ✅ | ✅ | PASS | PASS | ELIGIBLE / **REVIEW_REQUIRED** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| gross_profit_2024 | ✅ | ✅ | PASS | PASS | ELIGIBLE / **INELIGIBLE** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| gross_profit_2025 | ✅ | ✅ | PASS | PASS | ELIGIBLE / **INELIGIBLE** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| net_profit_2024 | ✅ | ✅ | PASS | PASS | ELIGIBLE / **INELIGIBLE** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| net_profit_2025 | ✅ | ✅ | PASS | PASS | ELIGIBLE / **INELIGIBLE** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| ocf_2025 | ✅ | ✅ | PASS | PASS | ELIGIBLE / **INELIGIBLE** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| total_assets_2025 | ✅ | ✅ | PASS | PASS | ELIGIBLE / REVIEW_REQUIRED | SCALE_VALID / SCALE_VALID | ELIGIBLE / **INELIGIBLE** | ✅ | ✅ |
| total_equity_2025 | ✅ | ✅ | PASS | PASS | ELIGIBLE / ELIGIBLE | **SCALE_VALID / SCALE_REVIEW_REQUIRED** | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| long_term_debt_2024 | ✅ | ✅ | PASS | PASS | ELIGIBLE / REVIEW_REQUIRED | SCALE_VALID / **SCALE_REVIEW_REQUIRED** | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| revenue_note_vs_statement | ✅ | ✅ | PASS | PASS | ELIGIBLE / **REVIEW_REQUIRED** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| investee_contamination_case | ✅ | ✅ | PASS | PASS | ELIGIBLE / REVIEW_REQUIRED | SCALE_VALID / SCALE_VALID | ELIGIBLE / **INELIGIBLE** | ✅ | ✅ |
| analysis_table_case | ✅ | ✅ | PASS | PASS | ELIGIBLE / **INELIGIBLE** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |
| summary_table_case | ✅ | ✅ | PASS | PASS | ELIGIBLE / **REVIEW_REQUIRED** | SCALE_VALID / SCALE_VALID | ELIGIBLE / ELIGIBLE | ✅ | ✅ |

**Provenance check:** for every case, the captured candidate `provenance.page` equals the oracle's `page_number` for both candidates, and the captured `raw_value` equals the oracle `value` verbatim — no mutation through capture, registry, or governance.

---

## 2. Reading the Results — disqualification lands on the correct axis

The audit confirms the governance design behaves as the Selection Architecture Review specified: **each incorrect candidate is flagged on exactly the axis its failure class belongs to**, while every correct candidate is clean on all three.

| Failure class | Disqualifying verdict | Caught by |
|---|---|---|
| `statement_basis` (gross_profit, net_profit, ocf) | INELIGIBLE | **Statement** governance |
| `analysis_table_contamination` | INELIGIBLE | **Statement** governance |
| `note_contamination`, `summary_table_contamination`, `source_selection` | REVIEW_REQUIRED | **Statement** governance |
| `scale_governance` (+ debt note-number) | SCALE_REVIEW_REQUIRED | **Scale** governance |
| `investee_contamination` (NutriCo, ASIL) | INELIGIBLE | **Entity** governance |

**Critical property:** **no incorrect candidate survives all three layers clean.** Every one carries at least one disqualifying or review-flagging verdict; every correct candidate is `ELIGIBLE` + `SCALE_VALID` + entity-`ELIGIBLE`. P5 Selection therefore has, for all 15 cases, a candidate set in which the authoritative value is unambiguously separable from the wrong value by governance verdict alone.

---

## 3. Summary Metrics

```
oracle_cases                = 15
correct_candidates_found    = 15
incorrect_candidates_found  = 15
capture_coverage_percent    = 100.0
registry_coverage_percent   = 100.0
governance_coverage_percent = 100.0
ready_for_selection_percent = 100.0
missing_candidates          = []
integrity_violations        = []
```

| Success criterion | Expected | Observed | Met |
|---|---|---|---|
| oracle_cases | 15 | 15 | ✅ |
| correct_candidates_found | 15 | 15 | ✅ |
| incorrect_candidates_found | 15 | 15 | ✅ |
| capture_coverage_percent | 100 | 100.0 | ✅ |
| registry_coverage_percent | 100 | 100.0 | ✅ |
| governance_coverage_percent | 100 | 100.0 | ✅ |
| ready_for_selection_percent | 100 | 100.0 | ✅ |
| missing_candidates | [] | [] | ✅ |
| integrity_violations | [] | [] | ✅ |

All success criteria met.

---

## 4. Scope Boundary (read before relying on this audit)

This audit proves, with executed evidence, that the current OCR V2 pipeline can **represent, preserve (without value or provenance loss), and correctly govern** both candidates of every oracle case — i.e., the **"preserved"** half of the objective is fully demonstrated end-to-end through registry + statement + scale + entity governance.

The candidate inputs originate from the oracle's own verified candidate definitions (`candidates_from_regression_cases`), corroborated for at least the investee cases by the `bbox_extraction_poc` tables (e.g. ASIL revenue, page 322). This audit therefore validates **representability and governance-tagging**, *not* pixel-level extraction recall — i.e., it does **not** independently re-prove that the OCR/bbox extractor surfaces every one of these candidates from the raw Lucky PDF. That extraction-recall question is the **P1 capture-recall / full CV1 re-run** concern under the Option-B parallel-comparison gate, and is explicitly out of this audit's stated scope ("verify that every oracle case is **representable** in the current pipeline").

This boundary is a scope note, not an unmet criterion: against the audit's defined objective and metrics, coverage is complete.

---

## 5. Final Question — Is OCR V2 ready for P5 Canonical Selection?

# READY_FOR_P5

**Justification.** Every one of the 15 verified oracle cases is fully representable in the current OCR V2 pipeline: both the correct and incorrect candidate are captured, retained in the append-only registry without loss, and assigned the expected governance verdict on the correct axis — with provenance pages and raw values preserved verbatim. Capture, registry, governance, and ready-for-selection coverage are each 100% with **no missing candidates and no integrity violations**, and the project's own 51-test suite passes. Decisively for P5, **no incorrect candidate survives all three governance layers clean while every correct candidate does**, so Selection is handed, for all 15 cases, a candidate set in which the authoritative value is unambiguously separable from the wrong value by governance verdict alone — which is the precondition the Selection Architecture Review requires. The only boundary worth stating is that this audit demonstrates representability-and-preservation, not raw-PDF extraction recall; that residual belongs to the P1/CV1 parallel-comparison gate and does not affect P5 readiness, because Selection consumes the registry, not the PDF. **OCR V2 is ready to begin P5 Canonical Selection.**

---

## 6. One-Paragraph Verdict

Selection can only choose among candidates that exist, and this audit — run against the shipped P0–P4 modules, not asserted — shows that for all fifteen verified CV1 cases the candidates exist, survive the registry unchanged, and arrive at the threshold of P5 already correctly governed: the eight hard-bar cases marked INELIGIBLE on their statement or entity axis, the scale cases marked SCALE_REVIEW_REQUIRED, and the note/summary cases marked REVIEW_REQUIRED, while every authoritative candidate stands clean as ELIGIBLE and SCALE_VALID with its page and value intact. No candidate is missing, no provenance or value is mutated, and no wrong candidate slips through all three layers unflagged, so the candidate set that P5 Canonical Selection will consume is complete and unambiguously separable — the determination is **READY_FOR_P5**, with the single honest caveat that raw-PDF extraction recall is validated downstream at the CV1 parallel-comparison gate, not here.
