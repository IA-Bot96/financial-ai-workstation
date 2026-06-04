# OCR V2 — Extraction Bridge Architecture Review

**Status:** Architecture review only. No code, no implementation, no OCR/governance/selection redesign.
**Date:** 2026-06-04
**Authoritative:** OCR V2 Architecture Review · Migration Review · Implementation Plan · Output Readiness Audit · existing OCR V1 workbook/`kb.json` structure · existing OCR V2 `CandidateCaptureInput` schema.
**Problem (from the Output Readiness Audit):** OCR V2 has no PDF extraction front-end; its capture ingests injected rows, so the only V2 workbook is a 15-row echo of the regression oracle's correct values. This review designs the missing bridge: **real PDF extraction → OCR V2 candidates → real V2 workbook.**

---

## 0. The Decisive Finding (read first)

**The bridge must source from V1's *pre-selection table extraction*, not V1's *post-selection workbook*.**

- V2's entire value is **selecting the right candidate among many**. That requires *multiple candidates* per (metric, year).
- V1's **workbook / `kb.json`** holds **one already-selected value per cell** — the value V1's flawed selection produced (84.6% S1 in CV1) — with scrambled metric labels and no basis/entity/PDF-page. Feeding it to V2 gives V2 **a single candidate to "choose" from → nothing to govern → V2 re-emits V1's wrong pick.** This is the same circular echo the Output Readiness Audit caught.
- V1's **intermediate raw table extraction** (`output/bbox_extraction_poc/tables/*.csv`) holds the **pre-selection candidate grids** — page (in filename), scale (in header), row labels, year columns. **These are the candidates V2 needs.**

So **Option A as literally framed (V1 *workbook* → adapter) is a trap**; the correct path is a refinement (Option C below) that sources from V1's extraction layer.

---

## 1. What OCR V2 Candidate Capture requires (exact schema)

`CandidateCaptureInput` (frozen, `extra="forbid"`):

| Field | Required? | Meaning |
|---|---|---|
| `raw_value` | **Required** | the observed number (str/int/float) |
| `raw_label` | **Required** | the source row label |
| `value_year` | **Required** | int ≥ 1900 |
| `page_number` | **Required** | PDF page (>0) |
| `table_reference` | **Required** | table id |
| `document_fingerprint` | **Required** | bundle fingerprint |
| `locator` | **Required** | within-table cell locator |
| `statement_type` | Optional | PRIMARY_STATEMENT / NOTE / ANALYSIS_TABLE / SUMMARY_TABLE / SUPPORTING_SCHEDULE / SEGMENT |
| `basis` | Optional | consolidated / unconsolidated |
| `entity_scope` | Optional | ISSUER / INVESTEE / … |
| `source_scale` | Optional | from the units header |
| `source_unit` | Optional | PKR, etc. |

Capture does **no** inference/selection; missing optional fields default to `unknown`. The four optional governance fields are exactly what V2's P3/P4 layers consume — so the bridge's real job is **populating them correctly without inventing them.**

## 2. What OCR V1 currently produces (exact structures)

| V1 output | Structure | Selection state |
|---|---|---|
| **Workbook** `.xlsx` | 22 sheets (Notes, Balance Sheet, Income Statement, Debt Schedule…); per-sheet `Metric × year` grid | **post-selection** |
| **`kb.json` → `financial_year_consolidation_result`** | dict: `metric_values` (consolidated, **selected**), `groups`, `conflict_groups_resolved`, `duplicate_groups_resolved` | **post-selection** |
| **`kb.json` → `workbook_cell_mappings`** (1867) | `cell_reference, column, row, sheet_name, metric, table_type, value_year, source_report_year, written_value, write_status, workbook_fingerprint` | post-selection; `metric` can be **scrambled OCR** (e.g. `"& seli essa - bomotuA senohp 5202"`); **no PDF page_number** (only workbook cell ref) |
| **`bbox_extraction_poc/tables/*.csv`** (27) | per-page raw grids; **page in filename** (`page_0164_…`), **scale in header** (`Financial Position (PKR in million)`), row labels, year columns (2020–2025) | **PRE-selection — multiple candidates** |

## 3. Can V1 workbook output be transformed into V2 candidate rows?

| Source | Transformable? | Verdict |
|---|---|---|
| V1 **workbook / kb.json** (final) | Mechanically yes | **Unsuitable** — single post-selection value per cell, scrambled labels, no basis/entity/PDF-page; gives V2 no candidate set; re-imports V1's errors (circular) |
| V1 **raw table CSVs** (intermediate) | Yes | **Suitable** — preserves candidate multiplicity, carries page + header-scale + labels + years; the correct bridge source |

**Answer:** transforming V1's *workbook* is possible but defeats V2's purpose; transforming V1's *extraction layer* is the viable path.

## 4. Metadata that already exists (in the raw table layer)

- `raw_value` — table cell value.
- `raw_label` — table row header.
- `value_year` — table column header.
- `page_number` — from the CSV filename (`page_0164…`).
- `source_scale` / `source_unit` — from the table header (`PKR in million`, `'000`).
- `table_reference` / `locator` — table filename + row/col.
- `document_fingerprint` — V1 already pins `97c3123a7a…` (the Lucky bundle fingerprint).
- `table_type` (V1 classification) — notes / balance_sheet / income_statement / etc.

## 5. Metadata that is missing (must be *derived*, never invented)

These are precisely the governance dimensions V1 never represented — the reason V2 exists:

- **`statement_type` in V2 vocabulary** — V1's `table_type` is a different taxonomy and does **not** distinguish PRIMARY_STATEMENT vs NOTE vs ANALYSIS_TABLE vs SUMMARY_TABLE. Needs a **mapping + page-range rules**.
- **`basis` (consolidated/unconsolidated)** — V1 tags **nothing**. The single biggest gap (8 of the CV1 statement_basis errors). Derived from **page ranges** (the truth set documents: unconsolidated statements p236–283, consolidated p286–375, analysis p163–164, six-year summary p162).
- **`entity_scope` (issuer/investee)** — V1 tags nothing; investee note tables (NutriCo p323, ASIL p322) are undifferentiated. Derived from **page→entity mapping bound to MSIL identity**.
- **Clean `raw_label` → canonical metric** — V1 OCR labels can be scrambled; needs the **metric alias/registry** mapping.

**Principle:** the bridge *derives* these from page-ranges, headers, table classification, and MSIL identity — it must never fabricate a basis/entity tag (that would reintroduce the very errors V2 forbids).

## 6. Adapter layer required

A deterministic adapter (no ML, no selection) that:
1. **Extracts** raw tables over all metric-bearing Lucky pages (reusing the working bbox extraction).
2. **Explodes** each table into per-`(label, year)` cells = candidate rows — producing **multiple candidates per (metric, year)** (unconsolidated value, consolidated value, analysis-%, summary, investee) so governance has something to choose among.
3. **Tags** each row:
   - `source_scale`/`source_unit` ← table header (present).
   - `statement_type` ← V1 `table_type` → V2 vocabulary + page-range rules.
   - `basis` ← page-range → basis config.
   - `entity_scope` ← page→entity map, validated against MSIL identity.
   - `raw_label` → canonical metric ← alias/registry.
4. **Emits** `CandidateCaptureInput` rows → existing V2 capture → registry → governance → selection → workbook.

The adapter is **provenance-faithful and derivation-only**; it changes no V2 governance/selection logic.

## 7. Smallest implementation: PDF → real OCR V2 workbook (Lucky)

Minimum viable bridge — **reuse, don't rebuild**:
- **Reuse the existing bbox table extraction** (already produces page+header+labels+years); extend its coverage from the 27-table POC to the Lucky pages carrying the 11 metrics (uncons primary p240–243, analysis p163–164, summary p162, consolidated primary p291–294, investee notes p322–323).
- **One small, Lucky-specific deterministic config**: a `page-range → (basis, statement_type, entity_scope)` table — derivable directly from the CV1 truth set's already-documented basis/scale page map.
- **A thin label→canonical-metric alias map** (reusing V1's normalization aliases).
- **Feed rows into the already-built, already-tested V2 pipeline.**

Output: a **real 66-cell canonical V2 workbook** for Lucky, with the candidate registry retaining all competitors. No new extractor, no new ML, no governance change.

## 8. Option Comparison

| Dimension | **A — V1 workbook → adapter → V2** | **B — new PDF extractor → V2** | **C — V1 *extraction layer* → adapter → V2** *(synthesis)* |
|---|---|---|---|
| **Effort** | Low | High | **Medium** |
| **Risk** | **High** — circular; re-imports V1 errors | Med–High — unproven new extractor | Medium — bounded to extraction recall + page-range tagging |
| **Correctness** | **Near-zero gain** — single candidate per cell; V2 can't govern | Potentially highest, but unproven | **High** — preserves candidate multiplicity; governance/selection actually operate |
| **Validation burden** | Pointless (circular comparison) | High — validate new extractor from scratch | Medium — CV1 truth set is the oracle; measure recall |
| **Verdict** | **Reject** | Defer | **Recommend** |

Option A fails on correctness (it is the current oracle-echo problem in another form). Option B duplicates extraction capability V1 already has. Option C reuses V1's proven table extraction but feeds V2 the **pre-selection candidates**, which is the only configuration in which V2's governance can demonstrably fix the 27 statement-selection + 14 scale errors.

## 9. Determination

# RECOMMENDED_MIGRATION_PATH = Option C

**Reuse V1's table-extraction front-end (raw, pre-selection tables) and adapt each extracted cell into a multi-candidate V2 `CandidateCaptureInput` stream, deriving basis / statement_type / entity_scope from page-ranges + headers + MSIL identity — then feed the existing V2 pipeline.** Not Option A (post-selection workbook → circular), not a brand-new extractor (Option B → unnecessary, unproven).

## 10. Implementation Sequence

| Step | Scope | Output | Validation gate |
|---|---|---|---|
| **B0** | Confirm `CandidateCaptureInput` frozen; build the **Lucky page-range → (basis, statement_type, entity_scope) config** from the CV1 truth set's basis/scale map; build the label→canonical-metric alias map | Bridge config (deterministic, Lucky-specific) | config reviewed against truth set page map |
| **B1** | Extend bbox table extraction to **all metric-bearing Lucky pages** (uncons + cons primary, analysis, summary, investee notes) | Raw table grids per page | extraction recall ≥ V1 on the 66 cells |
| **B2** | Deterministic **adapter**: raw cell → `CandidateCaptureInput`, tagging scale/unit/statement_type/basis/entity_scope/metric; emit **multiple candidates per cell** | V2 candidate row stream | **both correct AND wrong candidates captured** (else governance test is vacuous); zero invented tags |
| **B3** | Run **PDF → adapter → V2 capture → registry → governance → selection → workbook** for Lucky | **Real 66-cell V2 workbook** + candidate registry | V2 selects the correct candidate on the 15 oracle cells; zero fabrication on the 14 source-insufficient cells |
| **B4** | Hand the real V2 workbook to the **V1-vs-V2 comparison** (`v1_v2_comparison_workbook_spec`) + **full CV1 re-run** against `cv1_truth_set_lucky_v1_0_0` | Comparison matrix + CV1 certification | `V2-regresses = ∅`; CV1 = CERTIFIED/CONDITIONAL |

**Validation subtlety (critical):** the bridge must capture the **wrong candidates too** — the consolidated values, investee figures, and analysis-% — not just the right ones. V2's governance is only meaningfully validated if it is given the contaminants to reject; a stream of only-correct candidates reproduces the current vacuous oracle-echo.

---

## One-Paragraph Verdict

The missing bridge is not a new extractor and it is emphatically not a flat map of V1's finished workbook: V1's workbook holds one already-selected, frequently-wrong value per cell with scrambled labels and no basis, entity, or PDF page, so adapting it would hand OCR V2 a single candidate per metric-year and reduce the whole governance-and-selection engine to an echo of V1's mistakes — the very circularity the Output Readiness Audit exposed. The candidates V2 needs already exist one layer earlier, in V1's pre-selection raw table extraction (`bbox_extraction_poc/tables`), where each grid carries the page in its filename, the scale in its header, the row labels, and the year columns; the only metadata genuinely missing — `basis`, V2-vocabulary `statement_type`, and `entity_scope` — is exactly what V1 never represented and what a small deterministic adapter must *derive* from documented page-ranges and MSIL identity rather than invent. The recommended path (Option C) therefore reuses V1's proven table extraction, explodes each table into a multi-candidate stream, tags the governance dimensions deterministically, and feeds the already-built V2 pipeline to produce a real sixty-six-cell Lucky workbook — provided the adapter surfaces the wrong candidates alongside the right ones so that V2's governance is tested on rejecting them, after which the existing comparison workbook and CV1 truth-set export finally have a real V2 output to validate.
