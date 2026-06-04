# OCR V2 — Remediation R1-A Report (Selection-Path Diagnosis)

**Status:** Diagnostic trace only. No extraction changes, no alias changes, no workbook redesign. Findings executed against the shipped B3 pipeline and the real candidate artifacts.
**Date:** 2026-06-04
**Read:** OCR V2 Missing-Cell Root-Cause Audit · OCR V2 Comparison Readiness Audit · `ocr_v2_lucky_candidates.json` (1905 real candidates) · `backend/ocr/ocr_v2_lucky_run.py` (B3 runner).
**Goal:** identify the exact stage where the 18 selection-failure cells (revenue, gross_profit, total_assets × 2020–2025) are lost.
**Companion artifact:** `ocr_v2_selection_path_audit.json` (per-cell trace).

---

## Does the B3 path invoke governance + selection?

**Yes — confirmed by reading `ocr_v2_lucky_run.py:run()`.** The pipeline is, in order:
```
bridge_adapter → CandidateCapture → CandidateRegistry
   → StatementGovernance.govern → ScaleGovernance.govern → EntityGovernance.govern
   → _select_metric_year_groups (CanonicalSelection.select per group)
   → WorkbookGenerator.write_xlsx  (emits ONLY status == SELECTED rows)
```
All four stages run, and the workbook emits **only `SELECTED` rows**. **The workbook does not bypass governance/selection.** → Determination **B is ruled out.**

---

## End-to-end trace (revenue / gross_profit / total_assets)

Grouping key (from `_select_metric_year_groups`): **`(raw_label, value_year)`**. Representative cell **revenue 2020** (all 18 cells follow the identical pattern):

| Stage | Observation |
|---|---|
| **1. Candidates entering governance** | **10** (raw_label `revenue`, year 2020) |
| **2. Governance outcomes** | `ELIGIBLE: 5`, `REVIEW_REQUIRED: 2`, `INELIGIBLE: 3` — statement governance **correctly** marked the `ANALYSIS_TABLE` %-rows `INELIGIBLE` and the `SUMMARY_TABLE` rows `REVIEW_REQUIRED` |
| **3. Candidates entering selection** | **10** (full group; selection applies the eligibility filter internally) |
| **4. Selection winner** | **NONE** — `status = ambiguity`, `reason = ambiguous_multiple_equivalent_candidates` |
| **5. Workbook row emitted** | **NO** (only `SELECTED` rows are written) |

The **5 ELIGIBLE candidates** that survive the filter (revenue 2020):
| value | statement_type | locator |
|---|---|---|
| `41,870,796` | SUPPORTING_SCHEDULE | row:2:col:2 ← **correct value line** |
| `41,870,796` | SUPPORTING_SCHEDULE | row:3:col:4 ← **duplicate of value line** |
| `100.00` | SUPPORTING_SCHEDULE | row:31:col:4 ← **% mis-tagged as SUPPORTING_SCHEDULE** |
| `(7.23)` | SUPPORTING_SCHEDULE | row:60:col:4 ← **% mis-tagged** |
| `50.32` | SUPPORTING_SCHEDULE | row:89:col:5 ← **% mis-tagged** |

→ **4 distinct values in the eligible set** → selection cannot resolve a single winner → **AMBIGUOUS** → nothing emitted.

**Uniform across all 18 cells** (from `ocr_v2_selection_path_audit.json`): every revenue/gross_profit/total_assets 2020–2025 group enters with 8–15 candidates, governs to ~`{ELIGIBLE:4–5, REVIEW_REQUIRED:2–7, INELIGIBLE:2–3}`, retains **3–4 distinct eligible values**, and returns **`ambiguity` → emitted = False**.

**Contrast — why the workbook showed a year-2019 percentage:** the `(revenue, 2019)` group has **1 candidate** (a `(12.81)` %-row that was tagged `SUPPORTING_SCHEDULE`, so `ELIGIBLE`); being the lone candidate it is `SELECTED` (`single_candidate_after_filtering`) and written. That is why the only `revenue` row in the workbook is the spurious 2019 percentage.

---

## Determination

# C — Selection executed, but eligibility filtering failed to produce a clean single-value eligible set

Not **A** (governance/selection did not execute correctly end-to-end — the value lines are never emitted), and not **B** (the workbook does **not** bypass governance/selection — both ran). The failure is **C**, with two precise upstream causes that pollute the eligible set:

1. **Statement mis-classification (eligibility-filter gap).** Percentage/ratio rows inside the p163/p164 analysis blocks were tagged `statement_type = SUPPORTING_SCHEDULE` instead of `ANALYSIS_TABLE`, so statement governance did **not** mark them `INELIGIBLE`. They survive the filter as eligible candidates with values like `100.00`, `(7.23)`, `50.32`. (The rows that *were* tagged `ANALYSIS_TABLE` — 3 per group — were correctly excluded, proving governance logic itself works.)
2. **No deduplication of identical value-line candidates.** The correct value (`41,870,796`) is extracted twice (e.g. camelot + pdfplumber, row:2:col:2 and row:3:col:4) and both survive as separate eligible candidates.

The result: the eligible set holds **multiple distinct values** (the true value line, its duplicate, and several mis-tagged percentages), so `CanonicalSelection` correctly refuses to guess and returns **AMBIGUOUS** — and because the workbook emits only `SELECTED` rows, the value line is dropped.

**Exact stage of loss:** the **Canonical Selection AMBIGUOUS branch** — the 18 value lines are present and pass governance as eligible, but are discarded because the eligible set is polluted (mis-classified percentages + un-deduped duplicates) and selection cannot resolve a single winner.

---

## Generated artifacts

- **`ocr_v2_selection_path_audit.json`** — per-cell trace for all 18 cells: candidates entering governance, governance-outcome counts, eligible count, distinct eligible values, selection status/reason, winner, workbook-emitted flag.
- **`ocr_v2_r1a_report.md`** — this report.

(No remediation applied — R1-A is the diagnosis; the fix is out of scope per the constraints. The localized fix would be upstream tagging: classify analysis-block percentage rows as `ANALYSIS_TABLE`, and dedup identical value-line candidates — neither requires extraction, alias, or workbook-schema changes.)

---

## One-Paragraph Verdict

The B3 path is not bypassing anything: `ocr_v2_lucky_run.run()` pushes the real candidates through capture, registry, statement, scale, and entity governance, and then canonical selection, with the workbook writing only `SELECTED` rows — so the eighteen revenue, gross-profit, and total-assets cells are lost inside selection, not before it. Tracing each `(raw_label, value_year)` group shows governance working as designed — the rows correctly tagged `ANALYSIS_TABLE` are marked `INELIGIBLE` — but the eligible set still carries four distinct values per cell, because some analysis-block percentage rows were mis-tagged `SUPPORTING_SCHEDULE` and slipped past the filter, and because the true value line (e.g. `41,870,796`) is duplicated by two extractors; with several distinct eligible values in hand, `CanonicalSelection` correctly returns `AMBIGUOUS` and emits nothing, while the lone year-2019 percentage that happened to be a single-candidate group is the only thing written. The determination is therefore **C — selection executed but eligibility filtering failed to yield a single clean value** — and the exact point of loss is the Canonical Selection ambiguity branch, fed by upstream statement mis-classification and missing value-line deduplication, both fixable without touching extraction, aliases, or the workbook schema.
