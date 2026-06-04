# CV1 Truth Set — Schema-Conformant Export

**Status:** Mechanical transformation only. No new extraction, no new analysis, no re-review, no PDF interpretation, no protocol changes, no new truth determination.
**Date:** 2026-06-04
**Sole authoritative source:** `output/PDF_TRUTH_SET_lucky_cv1_phase1.md` (canonical CV1 Phase 1 blind extraction, unconsolidated basis).
**Explicitly NOT used:** `output/PDF_TRUTH_SET_lucky_2025.md` (non-authoritative precursor; contains summed/derived values prohibited by the CV1 no-aggregation rule).

## Deliverables produced
| File | Path | Content |
|---|---|---|
| `cv1_truth_set_lucky_v1_0_0.csv` | `C:\AI Financial Intelligence\cv1_truth_set_lucky_v1_0_0.csv` | 66 rows, 15 schema fields |
| `cv1_truth_set_lucky_v1_0_0.json` | `C:\AI Financial Intelligence\cv1_truth_set_lucky_v1_0_0.json` | envelope (id/version/basis/fingerprint) + 66 `cells` |
| `cv1_truth_set_export_audit.json` | `C:\AI Financial Intelligence\cv1_truth_set_export_audit.json` | computed audit (below) |

---

## 1. Transformation applied (mechanical)

1. **Direct field mapping** — each value, scale, unit, page, source, source_type, and disposition was copied verbatim from the canonical artifact's per-metric tables. No value was recomputed, rescaled, or re-judged.
2. **Total Debt expansion (the only structural change).** The canonical artifact represents Total Debt as a single collapsed row `2020–2025 SOURCE_INSUFFICIENT`. This was expanded into **six discrete rows** (`total_debt_2020 … total_debt_2025`), **each retaining `truth_status = SOURCE_INSUFFICIENT`**. No value invented, no component summed, no derivation performed. This raised the literal row count from 61 → 66.
3. **No other change.** All other 10 metrics already had six discrete year-rows; they were mapped 1:1.

## 2. Target schema (15 fields, one row per metric-year)

`cell_id · issuer · metric · value_year · truth_value · truth_scale · truth_unit · truth_status · page_number · source_location · source_type · basis · entity_scope · truth_set_version · bundle_fingerprint`

- `truth_status ∈ {VALUE, SOURCE_INSUFFICIENT}`.
- `truth_value = "SOURCE_INSUFFICIENT"`, `truth_scale = "n/a"`, `source_type = "n/a"`, `page_number` empty for source-insufficient cells (except where the canonical artifact cited a contaminated/component source page — `total_liabilities` 2020–2023 → 163; `long_term_debt` 2020–2023 → 162; `total_debt` → none).
- `basis = unconsolidated`, `entity_scope = ISSUER`, `truth_set_version = 1.0.0` for all rows.
- `bundle_fingerprint = 97c3123` — the Lucky bundle fingerprint pinned in the CV1 Execution Checklist (carried, not derived).
- `page_number` uses the **PDF page index** (the artifact's `p.N` of the `p.N / report p.M` convention).

## 3. Disposition map (faithful to the canonical artifact)

| Metric | VALUE years | SOURCE_INSUFFICIENT years |
|---|---|---|
| revenue, gross_profit, operating_profit, profit_after_tax, eps, total_assets, total_equity | 2020–2025 (all 6) | — |
| operating_cash_flow | 2020–2025 (all 6) | — |
| total_liabilities | 2024, 2025 | 2020, 2021, 2022, 2023 |
| long_term_debt | 2024, 2025 | 2020, 2021, 2022, 2023 |
| total_debt | — | 2020, 2021, 2022, 2023, 2024, 2025 |

**Scale preserved exactly, including the mixed-scale metric:** `operating_cash_flow` is `millions` for 2020–2023 (p162 summary) and `thousands` for 2024–2025 (p243 primary) — carried as-is, **not** rescaled. `eps` is `full` / `PKR_per_share`. All other valued cells are `thousands` / `PKR`.

## 4. Export audit (computed, not asserted)

```json
{
 "total_rows": 66,
 "unique_metrics": 11,
 "unique_years": 6,
 "valued_cells": 52,
 "source_insufficient_cells": 14,
 "missing_combinations": [],
 "duplicate_combinations": [],
 "integrity_violations": [],
 "source_artifact": "output/PDF_TRUTH_SET_lucky_cv1_phase1.md",
 "truth_set_version": "1.0.0",
 "bundle_fingerprint": "97c3123"
}
```

## 5. Success criteria — all met

| Criterion | Required | Produced | ✓ |
|---|---|---|---|
| total_rows | 66 | 66 | ✅ |
| unique_metrics | 11 | 11 | ✅ |
| unique_years | 6 | 6 | ✅ |
| valued_cells | 52 | 52 | ✅ |
| source_insufficient_cells | 14 | 14 | ✅ |
| missing_combinations | [] | [] | ✅ |
| duplicate_combinations | [] | [] | ✅ |
| integrity_violations | [] | [] | ✅ |

`52 valued + 14 source-insufficient = 66 cells` (11 metrics × 6 years); no metric-year pair missing or duplicated.

---

## 6. One-Paragraph Verdict

The canonical CV1 truth set has been mechanically exported into a schema-conformant CSV and JSON without any new extraction, judgment, or truth determination: every value, scale, page, and disposition was copied verbatim from `PDF_TRUTH_SET_lucky_cv1_phase1.md`, the non-authoritative precursor was excluded so no prohibited summed or derived value entered the set, and the only structural change was expanding the single collapsed Total Debt row into six discrete `SOURCE_INSUFFICIENT` rows — inventing nothing and summing nothing — to bring the literal count from sixty-one to the full sixty-six. The computed audit confirms eleven metrics, six years, sixty-six combinations, fifty-two valued and fourteen source-insufficient cells, with no missing pairs, no duplicates, and no integrity violations, including faithful preservation of the operating-cash-flow scale break (millions 2020–2023, thousands 2024–2025). The truth set is now machine-readable and version-pinned at 1.0.0, ready to serve as the oracle for the V1-vs-V2 comparison, the full CV1 re-run, downstream revalidation, and cutover validation.
