# OCR V2 — Missing-Cell Root-Cause Audit

**Status:** Audit only. No code, no implementation. Counts/classifications computed by reading the actual artifacts.
**Date:** 2026-06-04
**Artifacts read:** `output/ocr_v2_lucky_candidates.json` (1905 candidate_inputs) · `output/ocr_v2_lucky_registry.json` (1905 candidates) · `output/ocr_v2_lucky_workbook.xlsx` · `cv1_truth_set_lucky_v1_0_0.csv`.
**Scope:** the 26 census cells the Comparison Readiness Audit found missing — Revenue 2020–2025, Gross Profit 2020–2025, Total Assets 2020–2025, EPS 2020–2025, Total Liabilities 2024–2025.

**Method:** for each missing cell, its **truth value** was searched (normalized) against the 1905 real candidates by `(value, year)`; the matching candidates' `raw_label`, `statement_type`, and `page` were inspected to localize the loss across the six pipeline stages.

---

## 1–6. Stage trace by metric group

### Revenue (6), Gross Profit (6), Total Assets (6) — value present, lost in selection
- **(1) Candidate exists upstream?** YES — e.g. Revenue 2020 `41,870,796` at p164 `SUPPORTING_SCHEDULE`; Gross Profit 2020 `6,076,765` p164; Total Assets 2020 `135,868,474` p163. All six years present for each.
- **(2) Exists in registry?** YES (registry mirrors candidate_inputs, 1905).
- **(3) Wrong metric_id?** PARTIAL — the value lines **already carry the canonical label** (`revenue`/`gross_profit`/`total_assets`). But the **same label was over-assigned** to contaminant rows in the same table block: ANALYSIS_TABLE percentages (`100.00`, `(7.23)`, `(12.81)`) and SUMMARY_TABLE rounded values (`41,871`). 70 candidates carry `raw_label="revenue"`, 60 `gross_profit`, 60 `total_assets`.
- **(4) Rejected by governance?** The contaminant ANALYSIS_TABLE rows are correctly tagged `statement_type=ANALYSIS_TABLE` (governance *can* reject them), and the value lines are tagged `SUPPORTING_SCHEDULE` (eligible).
- **(5) Lost during selection?** **YES — this is the failure.** The workbook's `revenue`/`gross_profit`/`total_assets` cell ended up as a **year-2019 ANALYSIS_TABLE percentage** (`(12.81)`/`(56.54)`/`8.62`), not the eligible value line — i.e. canonical selection did not filter the ineligible analysis-% candidates nor prefer the value line, and did not emit one canonical row per `(metric, year)`.
- **(6) Lost during workbook projection?** Contributing — the workbook is a 440-row candidate dump (153 labels), indicating selection's eligibility/one-per-cell discipline was not applied on the bridge path.
- **Classification: SELECTION_FAILURE** (value-line candidate present and eligible; ineligible analysis-% surfaced instead).

### EPS (6) — value present under the wrong label
- **(1) Upstream?** YES — all six EPS values present: `2.07 / 8.70 / 9.46 / 8.61 / 18.91 / 22.59`, p162 `SUMMARY_TABLE`, under `raw_label="earnings_per_share"`.
- **(2) Registry?** YES.
- **(3) Wrong metric_id?** **YES — the decisive failure.** Candidates are labeled `earnings_per_share`; the census/canonical id is `eps`; **zero candidates carry `raw_label="eps"`**. The alias `earnings_per_share → eps` is absent, so the canonical `eps` cell never populated.
- **(4)/(5)/(6)** Not reached — the cell never resolved to the canonical id.
- **Classification: ALIAS_RESOLUTION_FAILURE.**

### Total Liabilities 2024–2025 (2) — value never extracted
- **(1) Upstream?** **NO** — `86,256,813` and `90,837,630` appear in **no candidate at any year**.
- These are the **unlabeled liabilities subtotal** on the primary balance sheet (p240); the 27 extracted tables (p162/163/164 summary+analysis, etc.) did not capture this computed, unlabeled subtotal row.
- **Classification: EXTRACTION_FAILURE** (value absent upstream; cannot be recovered downstream).

---

## Root-Cause Table (26 cells)

| metric | year | candidate_found | root_cause | required_fix |
|---|---|---|---|---|
| revenue | 2020 | ✅ (p164 value line) | SELECTION_FAILURE | Apply canonical selection to bridge candidates: filter ANALYSIS_TABLE, prefer value line, one row per (metric,year) |
| revenue | 2021 | ✅ | SELECTION_FAILURE | as above |
| revenue | 2022 | ✅ | SELECTION_FAILURE | as above |
| revenue | 2023 | ✅ | SELECTION_FAILURE | as above |
| revenue | 2024 | ✅ | SELECTION_FAILURE | as above |
| revenue | 2025 | ✅ | SELECTION_FAILURE | as above |
| gross_profit | 2020 | ✅ | SELECTION_FAILURE | as above |
| gross_profit | 2021 | ✅ | SELECTION_FAILURE | as above |
| gross_profit | 2022 | ✅ | SELECTION_FAILURE | as above |
| gross_profit | 2023 | ✅ | SELECTION_FAILURE | as above |
| gross_profit | 2024 | ✅ | SELECTION_FAILURE | as above |
| gross_profit | 2025 | ✅ | SELECTION_FAILURE | as above |
| total_assets | 2020 | ✅ | SELECTION_FAILURE | as above (also dedup vs `total_equity_and_liabilities` same value) |
| total_assets | 2021 | ✅ | SELECTION_FAILURE | as above |
| total_assets | 2022 | ✅ | SELECTION_FAILURE | as above |
| total_assets | 2023 | ✅ | SELECTION_FAILURE | as above |
| total_assets | 2024 | ✅ | SELECTION_FAILURE | as above |
| total_assets | 2025 | ✅ | SELECTION_FAILURE | as above |
| eps | 2020 | ✅ (label `earnings_per_share`) | ALIAS_RESOLUTION_FAILURE | Add alias `earnings_per_share` / `"earning per share (rupees)"` → `eps` |
| eps | 2021 | ✅ | ALIAS_RESOLUTION_FAILURE | as above |
| eps | 2022 | ✅ | ALIAS_RESOLUTION_FAILURE | as above |
| eps | 2023 | ✅ | ALIAS_RESOLUTION_FAILURE | as above |
| eps | 2024 | ✅ | ALIAS_RESOLUTION_FAILURE | as above |
| eps | 2025 | ✅ | ALIAS_RESOLUTION_FAILURE | as above |
| total_liabilities | 2024 | ❌ | EXTRACTION_FAILURE | Extract the unlabeled liabilities subtotal from primary BS (p240) — requires extraction change |
| total_liabilities | 2025 | ❌ | EXTRACTION_FAILURE | as above |

---

## Totals by Root Cause

| Root cause | Cells | Candidate present? | Recoverable without extraction change? |
|---|---|---|---|
| **SELECTION_FAILURE** | **18** (revenue 6, gross_profit 6, total_assets 6) | YES | **YES** |
| **ALIAS_RESOLUTION_FAILURE** | **6** (eps) | YES | **YES** |
| **EXTRACTION_FAILURE** | **2** (total_liabilities 2024, 2025) | NO | **NO** |
| GOVERNANCE_FAILURE | 0 | — | — |
| WORKBOOK_FAILURE | 0 (manifests within SELECTION_FAILURE) | — | — |
| **Total** | **26** | 24 present | **24 recoverable** |

---

## Final Determination

**24 of the 26 missing cells can be recovered without changing extraction.**

- **18 SELECTION_FAILURE** cells (revenue, gross_profit, total_assets): the correct value-line candidates already exist in the registry, correctly labeled and tagged `SUPPORTING_SCHEDULE`/value, alongside contaminant `ANALYSIS_TABLE` percentages tagged as such. Applying the canonical selection that already exists in the V2 engine (reject analysis-table, prefer value line, one row per metric-year) recovers all 18 — **no extraction change**.
- **6 ALIAS_RESOLUTION_FAILURE** cells (eps): the values are present under `earnings_per_share`; adding the alias to the canonical `eps` id recovers all 6 — **no extraction change**.
- **2 EXTRACTION_FAILURE** cells (total_liabilities 2024/2025): the unlabeled balance-sheet subtotal was never captured; recovery **requires an extraction change** (capture the p240 liabilities subtotal).

---

## One-Paragraph Verdict

Tracing every missing census cell's truth value through the 1,905 real candidates shows the misses are overwhelmingly post-extraction: the revenue, gross-profit, and total-assets value lines all exist in the registry with correct values, canonical labels, and a `SUPPORTING_SCHEDULE` tag, but the same label was also pasted onto the analysis-table percentages in those blocks and the workbook ended up emitting a year-2019 percentage instead of the value line — a selection failure (eighteen cells) in which the engine's own analysis-table-ineligible and value-line-preference rules were simply not applied on the bridge path; the six EPS values are likewise present and correctly extracted at p162 but sit under the label `earnings_per_share` with no alias to the canonical `eps`, an alias-resolution failure; and only the two Total-Liabilities 2024–2025 cells are genuinely absent upstream, because they are the unlabeled liabilities subtotal on the primary balance sheet that the twenty-seven extracted tables never captured — a true extraction failure. Net, **twenty-four of the twenty-six missing cells are recoverable without touching extraction** (apply the existing canonical selection and add one EPS alias), and only **two require an extraction change**, confirming that the bridge's real gap is selection-and-alias wiring, not the ability to read the document.
