# OCR V2 — Comparison Readiness Audit

**Status:** Audit only. No implementation, no code changes. Counts computed by reading the actual generated artifacts.
**Date:** 2026-06-04
**Artifacts read:** `output/ocr_v2_lucky_workbook.xlsx` · `output/ocr_v2_lucky_candidates.json` · `output/ocr_v2_lucky_registry.json` · `cv1_truth_set_lucky_v1_0_0.csv`.

**Run provenance (read from artifacts):** `real_extraction_run = True`, `oracle_injected_values = False`, `tables_processed = 27`, `candidate_inputs = 1905`, registry `candidates = 1905`. **This is a genuine real-PDF extraction run — not the prior oracle echo.** That is real progress. The findings below concern whether its *output* can drive the comparison.

**Workbook shape:** sheet "OCR V2 Canonical Metrics", **440 data rows**, **153 distinct `metric_id` values** — i.e. a dump of extracted table rows (incl. OCR-garbled duplicates like `"ca sh"`/`"cash"`), not a clean 66-cell canonical set.

---

## TASK 1 — Census Coverage (66 cells)

| Status at census `(metric, year)` key | Count |
|---|---|
| **Present** (≥1 canonical row) | **30** |
| **Absent** | **36** (26 wrongly missing + 10 correctly-absent source-insufficient) |
| **Ambiguous** (multiple rows at one census key) | **0** |
| **Correctly source_insufficient (abstained)** | **10** |

### Per-metric coverage
| Metric | Census years present | Note |
|---|---|---|
| operating_profit | 6/6 | resolved correctly |
| profit_after_tax | 6/6 | resolved correctly |
| total_equity | 6/6 | resolved correctly |
| operating_cash_flow | 6/6 | present but scale/value issues (Task 2) |
| long_term_debt | 6/6 | present but wrong source (Task 2) |
| **revenue** | **0/6** | **absent** — only a stray analysis-% row (`metric_id="revenue"`, year 2019, value `(12.81)`) |
| **gross_profit** | **0/6** | **absent** — only `(year 2019, "(56.54)")` analysis-% |
| **total_assets** | **0/6** | **absent** — only `(year 2019, "8.62")` analysis-% |
| **eps** | **0/6** | **absent** — 0 rows |
| total_liabilities | 0/6 | 2020–2023 correctly SI; **2024/2025 missing** |
| total_debt | 0/6 | all 6 correctly source_insufficient (abstained) |

**Finding:** real candidates exist (1905), but **label → canonical-metric resolution failed for revenue, gross_profit, total_assets, eps** — their value lines (Turnover/Net Revenue/TOTAL ASSETS) were never mapped to the canonical id; only stray analysis-table percentages picked up the canonical name (at comparator year 2019).

---

## TASK 2 — Truth-Set Alignment (vs `cv1_truth_set_lucky_v1_0_0.csv`)

| Classification | Count | Cells |
|---|---|---|
| **exact_match** | **18** | operating_profit (6), profit_after_tax (6), total_equity (6) — all values + scale correct |
| **scale_mismatch** | **4** | operating_cash_flow 2020–2023 — value right, but scale tagged `source_header:PKR` (millions not captured) |
| **value_mismatch** | **8** | operating_cash_flow 2024/2025 (wb `27,581`/`27,573` = millions summary vs truth `27,580,741`/`27,572,567` thousands primary); long_term_debt 2024/2025 (wb `14,527`/`10,567` = **contaminated p162 summary** vs truth `12,760,637`/`9,184,522` clean primary); long_term_debt 2020–2023 (V2 **emitted a value where truth = SOURCE_INSUFFICIENT**) |
| **missing** | **26** | revenue (6), gross_profit (6), eps (6), total_assets (6), total_liabilities 2024/2025 (2) |
| **source_insufficient (correct abstention)** | **10** | total_debt (6), total_liabilities 2020–2023 (4) |

**Cells correct = 18 exact + 10 correct-abstention = 28/66 (42%). Cells wrong or missing = 38/66 (58%).**

**Two severe alignment defects:**
1. **Contaminated-source selection.** For long_term_debt 2024/2025 and operating_cash_flow 2024/2025, V2 selected the **p162 millions summary** over the **clean primary statement** — the exact source-precedence error the truth set warned of (SI-3). Governance did not prefer the primary.
2. **Fabrication on source-insufficient.** long_term_debt 2020–2023: V2 emitted the contaminated summary value where the truth is `SOURCE_INSUFFICIENT` — the worst comparison class (a false assertion where honest abstention was required).

---

## TASK 3 — Can `comparison_matrix.xlsx` be populated?

**No — not validly.** Blockers:
- **26 of 66 cells have no V2 value** (revenue, gross_profit, eps, total_assets all years; total_liabilities 2024/2025) → the matrix's V2 column is empty for 39% of cells.
- **Canonical-metric resolution is wrong** for revenue/gross_profit/total_assets (mapped to stray analysis-% rows at year 2019) → even where a `metric_id` exists, it is not the census value.
- **Workbook is not keyed to the 66 census cells** (440 rows / 153 labels) → no clean 1:1 `(metric, year) → canonical_value` projection to load into the matrix.
- **Scale not fully captured** (OCF tagged `source_header:PKR` without millions/thousands) → the `numeric_scale_aware` comparator cannot evaluate scale for those cells.

The matrix could be *partially* populated for the 3 fully-resolved metrics (operating_profit, profit_after_tax, total_equity), but a 66-cell comparison cannot be completed.

---

## TASK 4 — Validation Gaps Before V1 vs V2 Comparison

1. **Label→canonical-metric mapping missing/incorrect** — revenue, gross_profit, total_assets, eps not resolved to their value lines (the single largest gap: 24 of 26 missing cells).
2. **Source-precedence governance not selecting primary over summary** — LTD/OCF 2024/2025 took the millions summary instead of the thousands primary.
3. **Source-insufficient abstention not enforced for contaminated candidates** — LTD 2020–2023 emitted contaminated values (fabrication-on-SI) instead of abstaining.
4. **Scale capture degraded** — header scale recorded as bare `source_header:PKR` (missing thousands/millions), defeating scale governance for OCF.
5. **Workbook schema** — a 440-row label dump, not a 66-cell canonical projection; needs collapse to one canonical row per `(metric, year)`.
6. **Missing total_liabilities 2024/2025** — the unlabeled-subtotal value lines not captured/mapped.

(Provenance itself is **present and good** — every row carries page + bbox CSV row/col locator; that is not a gap.)

---

## TASK 5 — Final Determination

# NOT_READY_FOR_V1_V2_COMPARISON

**Evidence:**
- The run is genuinely real (1905 real candidates, 27 tables, `oracle_injected_values = False`) and the pipeline **proves it can produce correct canonical values from real extraction** — operating_profit, profit_after_tax, and total_equity are **exact on all 6 years (18/18)**, and total_debt + total_liabilities 2020–2023 are **correctly abstained (10 cells)**. That is real validation of the architecture on real data.
- But **only 28 of 66 cells are correct**; **26 are missing** (revenue, gross_profit, eps, total_assets all years — canonical-metric resolution failed), **8 are value-mismatched** (including 4 fabrications where the truth is source-insufficient and 4 contaminated-summary selections), and **4 have unusable scale tags**.
- `comparison_matrix.xlsx` **cannot be validly populated** for 39% of cells, and the metric resolution is wrong where labels did map, so a comparison run today would be incomplete and partly meaningless.

The bridge exists and runs on real data — a decisive step past the oracle echo — but its **label-resolution, source-precedence selection, source-insufficient abstention, and scale capture are not yet correct enough** to drive a full, trustworthy V1-vs-V2 comparison.

---

## One-Paragraph Verdict

Reading the actual artifacts, OCR V2 has crossed the threshold the prior audit said it had not: this is a genuine real-PDF extraction run — 1,905 real candidates from 27 tables, `oracle_injected_values = False` — and the pipeline demonstrably produces correct canonical values from real data, nailing operating profit, profit after taxation, and total equity exactly across all six years and correctly abstaining on the ten genuinely source-insufficient total-debt and total-liabilities cells. But the same artifacts show it is not yet ready to be compared: twenty-six of the sixty-six census cells are missing because revenue, gross profit, total assets, and EPS were never resolved from their value lines to the canonical metric (only stray analysis-table percentages at year 2019 inherited the names), long-term debt and operating cash flow for 2024–2025 were taken from the millions summary instead of the clean primary statement, long-term debt 2020–2023 was emitted with contaminated values where the truth set requires abstention, and the operating-cash-flow scale was captured as a bare "PKR" with no thousands/millions distinction. With only twenty-eight of sixty-six cells correct and the workbook still a four-hundred-forty-row label dump rather than a sixty-six-cell canonical projection, `comparison_matrix.xlsx` cannot be validly populated — so the determination is **NOT_READY_FOR_V1_V2_COMPARISON**, with the gaps now precisely localized to label→metric resolution, source-precedence selection, source-insufficient abstention, and scale capture, not to extraction itself.
