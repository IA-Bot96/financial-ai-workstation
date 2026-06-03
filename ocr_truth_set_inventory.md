# OCR Truth-Set Census Inventory (CV1)

**Status:** CV1 preparation artifact — the exact census population for analyst review. No code, no measurement, no results. Directly usable to begin CV1.
**Date:** 2026-06-03
**Pins:** `thresholds_version 1.0.0`; Lucky bundle `97c3123…`; Millat bundle (per its OCR context — fingerprint to confirm).
**Precondition:** MB-1 entity sign-off confirmed (`entity_ref` validated).
**Cell-id convention:** `ocr:<issuer>:<metric>:<year>` (e.g. `ocr:lucky:revenue:2025`).

---

## 0. Scope

This inventory enumerates the **S1 census** — the baseline-eligible core metrics × all value-years × both issuers (≈132 cells). Each cell is one validation item carrying all five value-class checks (`value`, `scale`, `unit`, `label`, `presence`). The **adversarial sample** (scale-flagged, note-vs-statement, review-gated, conflict, missing-year) is appended per §4 and is **not** fully pre-enumerable (derived from bundle flags + sampling).

---

## 1. Metric Reference (applies to both issuers)

| # | `canonical_metric` | Expected statement | `unit` | `scale` (expected) | Special handling |
|---|---|---|---|---|---|
| 1 | `revenue` | income_statement | PKR | thousands | **Pre-flagged scale-corrupt (Lucky, all yrs); note-vs-statement on 2024/2025** |
| 2 | `gross_profit` | income_statement | PKR | thousands | Pre-flagged unresolved-conflict + scale |
| 3 | `operating_profit` | income_statement | PKR | thousands | Pre-flagged unresolved-conflict |
| 4 | `profit_after_tax` | income_statement | PKR | thousands | Pre-flagged unresolved-conflict + scale |
| 5 | `earnings_per_share` | income_statement | **per_share** | full | EPS in rupees/share; **the clean baseline metric** — unit-special |
| 6 | `total_assets` | balance_sheet | PKR | thousands | Pre-flagged scale-break 2023→2024 |
| 7 | `total_equity` | balance_sheet | PKR | thousands | **Lucky: MISSING exact metric → `presence` check** |
| 8 | `cash_and_cash_equivalents` | balance_sheet (cross-check cash-flow end) | PKR | thousands | Pre-flagged source-ambiguity (income-statement mis-source) |
| 9 | `total_debt` | balance_sheet | PKR | thousands | **Lucky: MISSING → `presence` check** |
| 10 | `long_term_debt` | balance_sheet | PKR | thousands | **Lucky: MISSING → `presence` check** |
| 11 | `operating_cash_flow` | cash_flow_statement | PKR | thousands | Pre-flagged mixed source-lineage (balance-sheet-classified early years) |

> **Scale & unit anchors:** confirm against each statement's *"Rupees in thousands/millions"* header; EPS is per-share regardless of statement scale; never infer scale from magnitude.

---

## 2. Lucky Census Grid (66 cells)

Value-years **2020–2025**. Each ✓ is one census cell `ocr:lucky:<metric>:<year>`. Flags: **S** = pre-flagged scale-risk (also adversarial-census); **P** = presence-check (metric missing on Lucky — verify truly-absent vs extraction-missed); **N** = note-vs-statement risk.

| Metric | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| revenue | ✓S | ✓S | ✓S | ✓S | ✓S**N** | ✓S**N** |
| gross_profit | ✓S | ✓S | ✓S | ✓S | ✓S | ✓S |
| operating_profit | ✓S | ✓S | ✓S | ✓S | ✓S | ✓S |
| profit_after_tax | ✓S | ✓S | ✓S | ✓S | ✓S | ✓S |
| earnings_per_share | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| total_assets | ✓ | ✓ | ✓ | ✓S | ✓S | ✓ |
| total_equity | ✓P | ✓P | ✓P | ✓P | ✓P | ✓P |
| cash_and_cash_equivalents | ✓ | ✓ | ✓ | ✓ | ✓S | ✓S |
| total_debt | ✓P | ✓P | ✓P | ✓P | ✓P | ✓P |
| long_term_debt | ✓P | ✓P | ✓P | ✓P | ✓P | ✓P |
| operating_cash_flow | ✓S | ✓S | ✓S | ✓S | ✓S | ✓S |

**Lucky totals:** 66 census cells · pre-flagged scale-risk (S) ≈ 40 · presence-checks (P) = 18 · note-vs-statement (N) = 2.

---

## 3. Millat Census Grid (66 cells — value-years [CONFIRM])

Value-years **2020–2025 [CONFIRM against the Millat bundle inventory]**. Each ✓ is one cell `ocr:millat:<metric>:<year>`. Millat presence/scale flags are **not** pre-seeded (no Millat scale audit yet) — analysts set flags during blind review; expect different missing/present metrics than Lucky.

| Metric | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| revenue | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| gross_profit | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| operating_profit | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| profit_after_tax | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| earnings_per_share | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| total_assets | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| total_equity | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| cash_and_cash_equivalents | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| total_debt | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| long_term_debt | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| operating_cash_flow | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**Millat totals:** 66 census cells (subject to year-span confirmation). Any year absent in the bundle → keep the row as a `presence` check, do not drop.

**Combined census ≈ 132 cells.**

---

## 4. Adversarial Sample Addendum (appended to the census)

Not fully pre-enumerable here — derived from bundle flags + sampling per protocol §3:

| Sub-population | How items are added | Pre-seeded source |
|---|---|---|
| **Scale-flagged (census)** | Append every value carrying a scale/candidate-spread/YoY flag | Lucky `scale_consistency_audit` flags (already marked **S** above); Millat: from its bundle flags |
| **Note-vs-statement (census)** | Append every case where a note/summary/analysis value was selected over a primary statement | Lucky revenue 2024/2025 (marked **N**); scan both bundles |
| **Review-gated (sample)** | Stratified sample by business area, over-weight core-adjacent | Lucky ~1,194 / Millat ~771 review-gated values |
| **Conflict groups (sample)** | Sample, core-metric conflicts first | Lucky 187 unresolved (26 critical) |
| **Missing-year (sample)** | Sample; verify truly-absent vs extraction-missed | Lucky 93 missing-year tables |

Each appended row uses the same cell schema; `stratum` set accordingly; sampling weights recorded for population-weighting (thresholds §3).

---

## 5. Analyst Starting Checklist

- ☐ Lucky 66 + Millat 66 census cells loaded into the review workbook (`ocr_review_workbook_spec.md`).
- ☐ Millat value-year span confirmed against the bundle; absent years kept as `presence` cells.
- ☐ Scale-flagged (S) and note-vs-statement (N) cells flagged for **S1 priority + mandatory second reviewer**.
- ☐ Presence-check (P) cells flagged (verify source has/lacks a discrete line).
- ☐ Adversarial rows appended from bundle flags + sampling.
- ☐ `entity_ref` for both issuers MB-1-confirmed.
- ☐ Bundles pinned by fingerprint; no live re-extraction.

---

## 6. One-Line Posture

This inventory hands analysts the exact 132-cell baseline census — every core metric across every year for Lucky and Millat, with Lucky's known scale-corruption, note-over-statement, and missing-metric cells pre-flagged — plus the rule for appending the adversarial sample, so CV1 review can begin immediately, scale-first and entity-anchored, without any measurement having yet occurred.
