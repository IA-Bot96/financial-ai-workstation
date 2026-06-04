# OCR V2 — Lucky Workbook Validation Audit

**Status:** Audit only. No code changes. Workbook not regenerated.
**Date:** 2026-06-04
**Issuer:** lucky_cement
**Truth set:** `cv1_truth_set_lucky_v1_0_0.csv` / `.json` (v1.0.0, bundle `97c3123`, declared basis: unconsolidated)

---

## 0. Determination

> **A. VALID_CANONICAL_WORKBOOK**

| Gate | Required | Observed | Pass |
|---|---|---|:--:|
| Coverage | 66 / 66 | 66 / 66 (52 exact + 14 source-insufficient) | ✅ |
| Value mismatches | 0 | 0 | ✅ |
| Scale mismatches | 0 | 0 | ✅ |
| Governance violations | 0 | 0 | ✅ |
| Integrity violations | 0 | 0 | ✅ |

The audited workbook is structurally valid, census-complete, internally consistent, fully provenance-tagged, and 100% truth-set aligned.

---

## Audited artifact & workbook selection

`output/ocr_v2_lucky_cement_2025_20260604T161417Z.xlsx` — the **most recent** OCR V2 Lucky canonical workbook on disk (generated 2026-06-04 16:14).

Two older Lucky workbooks also exist and were checked for context; **neither** is production-valid, which is why the latest workbook is the correct audit target:

| Workbook | Canonical rows | State |
|---|---:|---|
| `ocr_v2_lucky_workbook.xlsx` (base) | 440 | **INVALID** — 26 target VALUE cells missing, 4 value-mismatches (OCF & LTD picked summary proxies), 4 fabricated values on SOURCE_INSUFFICIENT cells |
| `ocr_v2_lucky_workbook_r1.xlsx` (r1) | 428 | **PARTIALLY_VALID** — 6 target VALUE cells missing (TL / OCF / LTD 2024–2025); 0 mismatches, 0 fabrications |
| `ocr_v2_lucky_cement_2025_…161417Z.xlsx` (latest) | 582 | **VALID_CANONICAL_WORKBOOK** (this audit) |

The latest workbook corresponds to the recovered state recorded in the R2 validation (`ocr_v2_r2_validation_audit.json` / `ocr_v2_r2_validation_report.md`: 52 exact + 14 SI, READY_FOR_PRODUCTION_INTEGRATION). This audit independently reproduces that result by reading the workbook directly.

---

## 1. Workbook structure validation

| Field | Value |
|---|---|
| workbook_path | `output/ocr_v2_lucky_cement_2025_20260604T161417Z.xlsx` |
| workbook exists / opens | yes / yes |
| sheet_count | 1 |
| sheet_names | `OCR V2 Canonical Metrics` |
| row_count (data) | 582 |
| column_count | 14 |
| schema_violations | **none** |

Columns present (all 14 expected): `metric_id, value_year, canonical_value, entity_ref, basis, statement_type, entity_scope, source_scale, source_unit, page_number, table_reference, source_reference, provenance_reference, selected_candidate_id`. No row is missing `metric_id`/`value_year`.

---

## 2. Census validation

Expected census: **11 metrics × 6 years (2020–2025) = 66 cells.**

| Measure | Value |
|---|---:|
| total_cells (target census) | 66 |
| target metric-year cells carrying a canonical value | 52 |
| duplicate_cells | **0** |
| missing_cells (VALUE truth cells absent) | **0** |
| source-insufficient cells correctly absent | 14 |
| unexpected_cells (target metric, off-census year) | **0** |

All 52 VALUE truth cells have exactly one canonical row; all 14 SOURCE_INSUFFICIENT truth cells are correctly *absent* (the engine abstained — see §5).

**Observation (not a census defect):** the canonical sheet also holds **530 non-target auxiliary rows** — other line items the extractor captured (e.g. `cost_of_sales`, `finance_cost`, subsidiary names, and many OCR-garbled labels such as `ash gen erat ed from op erations`). These fall outside the 11-metric truth-set census and do not affect the 66-cell result, but they mean the sheet is a full canonical dump rather than a 66-row digest. Worth a downstream filter if the workbook is consumed as-is.

---

## 3. Truth-set alignment

| Measure | Value |
|---|---:|
| total_cells | 66 |
| exact_matches | **52** |
| source_insufficient_matches | **14** |
| value_mismatches | **0** |
| scale_mismatches | **0** |
| missing_cells | **0** |
| coverage_percent | **100.0%** |

Per-metric breakdown (all VALUE cells EXACT_MATCH):

| Metric | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | Source |
|---|---|---|---|---|---|---|---|
| revenue | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p164 supporting schedule |
| gross_profit | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p164 |
| operating_profit | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p164 |
| profit_after_tax | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p164 |
| eps | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p162 summary |
| total_assets | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p163 / p240 primary |
| total_equity | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p163 / p240 primary |
| operating_cash_flow | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | p162 summary (m) / p243 primary |
| total_liabilities | SI | SI | SI | SI | ✅ | ✅ | p240 primary (2024–25); SI 2020–23 |
| total_debt | SI | SI | SI | SI | SI | SI | no explicit line — SI all years |
| long_term_debt | SI | SI | SI | SI | ✅ | ✅ | p240 primary (2024–25); SI 2020–23 |

`SI` = SOURCE_INSUFFICIENT in truth set → correctly emitted as **no canonical row** (match). Scale handling is correct: OCF 2020–2023 are in `millions` (5,047 / 12,493 / 15,469 / 23,243) and 2024–2025 in `thousands` (27,580,741 / 27,572,567), all matching truth scale without a scale mismatch.

---

## 4. Provenance validation

| Field | Value |
|---|---:|
| emitted target VALUE rows | 52 |
| rows_with_provenance | **52** |
| rows_missing_provenance | **0** |

Every emitted canonical value carries `metric_id`, `value_year`, `page_number`, and a `provenance_reference` locator (e.g. `page_0240_bbox_00_bbox_camelot_stream_table_00.csv:row:42:col:4`). 100% provenance coverage.

---

## 5. Governance validation

| Check | Result |
|---|---|
| REVIEW_REQUIRED rows emitted as canonical | **0** (workbook emits only canonically-selected rows; no REVIEW_REQUIRED status surfaces) |
| ANALYSIS_TABLE rows in workbook (any metric) | **0** |
| ANALYSIS_TABLE rows emitted for target metrics | **0** |
| Contaminated summary proxy selected over primary | **0** |
| SOURCE_INSUFFICIENT truth cells emitted with fabricated values | **0** |
| **governance_violations** | **0** |
| affected_cells | none |

Key governance evidence:
- **No analysis-table contamination:** the workbook contains zero `ANALYSIS_TABLE` rows. The summary "Analysis of P&L" figures the truth set itself sources (operating_profit p164) are tagged `SUPPORTING_SCHEDULE`, consistent with truth.
- **No contaminated long-term-debt proxy:** `long_term_debt` 2024–2025 are taken from the **PRIMARY_STATEMENT on page 240** (12,760,637 / 9,184,522), not from the summary "Long term finance" line on p162 that is contaminated by deferred grant. The older base workbook failed exactly here (selected 14,527 / 10,567 from summary, and fabricated 380 / 4,042 / 16,273 / 16,679 for the 2020–2023 SI cells). The latest workbook abstains on 2020–2023 as required.
- **No fabricated SOURCE_INSUFFICIENT values:** all 14 SI cells (total_liabilities 2020–23, total_debt 2020–25, long_term_debt 2020–23) emit no canonical row.
- **OCF disambiguation correct:** operating_cash_flow 2024–2025 map to "Net cash generated from operating activities" (p243 primary, 27,580,741 / 27,572,567); "Cash generated from operations" is retained separately as `cash_generated_from_operations` (auxiliary), so no ambiguity survivor is emitted as OCF.

---

## 6. Canonical integrity validation

| Field | Value |
|---|---|
| one canonical row per (metric, year) | **yes** |
| canonical_duplicates | **none** |
| ambiguity_survivors | **none** |
| integrity_violations | **0** |

Each of the 52 target VALUE cells resolves to exactly one canonical row. No (metric, year) group has more than one emitted canonical selection.

---

## 7. Conclusion

The latest Lucky OCR V2 workbook (`ocr_v2_lucky_cement_2025_20260604T161417Z.xlsx`) is a **VALID_CANONICAL_WORKBOOK**: 66/66 truth-set coverage (52 exact + 14 correctly source-insufficient), zero value/scale mismatches, full provenance, no governance violations, and no integrity violations. It reproduces the R2 "READY_FOR_PRODUCTION_INTEGRATION" result by direct read of the workbook.

Two non-blocking notes for downstream consumers:
1. The canonical sheet is a **full dump (582 rows)** — 530 of which are non-target auxiliary line items, some with OCR-garbled labels. A target-metric filter (the 11 truth metrics) yields the clean 52-value + 14-abstention set.
2. Earlier on-disk workbooks (`ocr_v2_lucky_workbook.xlsx`, `…_r1.xlsx`) are **not** production-valid and should not be mistaken for the canonical output; only the latest passes all gates.

**Deliverables:** `ocr_v2_lucky_workbook_validation_audit.json`, `ocr_v2_lucky_workbook_validation_report.md`.
