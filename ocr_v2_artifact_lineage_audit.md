# OCR V2 — Artifact Lineage Audit (Lucky Rerun)

**Status:** Audit only. No code changes. Profiled and compared the actual workbook artifacts.
**Date:** 2026-06-04

---

## 0. Headline

The Lucky rerun emits **two kinds** of workbook from **two different engines**:
- a **V2 canonical-metrics workbook** (single sheet, 582 rows, governed) — produced **twice** as two **content-identical** files (a validation copy and a named/published export); and
- a **V1 shadow statement workbook** (49 sheets) — the human-readable served output, **not OCR V2**.

The two V2 canonical files are byte-equivalent (same header, same 582 rows, both 66/66). The 49-sheet file is V1.

---

## 1. Workbook Inventory

| # | Filename | Generator module | Intended purpose | Rows (data) | Sheets | Consumer | Type |
|---|---|---|---|---|---|---|---|
| 1 | `ocr_v2_r2_workbook.xlsx` | `OCRV2WorkbookGenerator.write_xlsx` (R2 remediation/validation run) | R2 remediation validation output | 582 | 1 (`OCR V2 Canonical Metrics`) | R2 validation report + comparison harness | **validation workbook** (canonical schema) |
| 2 | `ocr_v2_lucky_cement_2025_20260604T161417Z.xlsx` | `OCRV2WorkbookGenerator` (entity-year-stamped published export, 16:14 run) | Named/published canonical export for the Lucky 2025 bundle | 582 | 1 (`OCR V2 Canonical Metrics`) | downstream / MSIL export / canonical record | **canonical registry export** |
| 3 | `lucky_2025_shadow_20260604T161415401563_42b6f676.xlsx` | V1 `ocr_engine` workbook population via `ShadowOCRPipeline` (primary = V1) | Shadow-mode V1 served (human-readable) statement workbook | 1323 | 49 (`Notes`, `Income Statement`, …) | shadow rendering review (and user-facing if mistaken for V2) | **shadow / statement-rendering workbook (V1)** |

**Equivalence proof (1 vs 2):** identical header and identical 582-row set — the two are the same V2 canonical result under two names (validation copy vs published export).

## 2. Lineage Diagram

```
Lucky bundle (PDF / bbox tables)
│
├── OCR V2 governed pipeline
│     capture → registry → statement/scale/entity governance → canonical selection
│     → OCRV2WorkbookGenerator  ("OCR V2 Canonical Metrics", 582 rows, 66/66)
│        │
│        ├── (1) ocr_v2_r2_workbook.xlsx              ← VALIDATION copy → 66/66 result
│        └── (2) ocr_v2_lucky_cement_2025_…Z.xlsx     ← PUBLISHED export (identical content)  ← AUTHORITATIVE
│
└── ShadowOCRPipeline.process()   [primary = V1, shadow = V2; returns V1; v2_output_consumed_by_caller = False]
      └── V1 ocr_engine workbook population
            └── (3) lucky_2025_shadow_…xlsx           ← 49-sheet V1 served workbook (NOT OCR V2) → shadow rendering review
```

## 3. Which workbook produced which result

| Result | Workbook | Verified |
|---|---|---|
| **66/66 validation result** | `ocr_v2_r2_workbook.xlsx` (≡ `ocr_v2_lucky_cement_2025_…`) | ✅ re-scored: 52 exact + 14 SI, 0 mismatch, 0 missing |
| **52 exact + 14 SI** | same V2 canonical workbook (both copies) | ✅ |
| **shadow rendering review** | `lucky_2025_shadow_…xlsx` (V1, 49 sheets) | ✅ (V1 ×1000-scale + wrong-value cells) |

## 4. Reconciliation of the three named files

- **`ocr_v2_r2_workbook.xlsx`** and **`ocr_v2_lucky_cement_2025_…Z.xlsx`** are the **same V2 canonical output** (content-identical, both 66/66). #1 is the validation-named artifact; #2 is the production/entity-year-named published export. Either is the governed OCR V2 result; they are not two different results.
- **`lucky_2025_shadow_…xlsx`** is a **different engine's output (V1)** — the shadow-served human-readable statement workbook. It is *not* an OCR V2 artifact despite the `lucky_2025` name and its proximity in time (16:14, same run window). It carries V1's CV1 failures (×1000 scale; 2022 revenue 95,000,000; 2025 revenue 528,651,878,000).

## 5. Final Determination — Authoritative OCR V2 Output

**The authoritative OCR V2 output is the V2 canonical-metrics workbook — specifically the published export `ocr_v2_lucky_cement_2025_20260604T161417Z.xlsx`, with `ocr_v2_r2_workbook.xlsx` as its content-identical validation copy.**

- It is the governed output (capture → governance → canonical selection → `OCRV2WorkbookGenerator`), single `OCR V2 Canonical Metrics` sheet, 582 rows, **66/66 (52 exact + 14 source-insufficient), 0 mismatches**.
- **`lucky_2025_shadow_…xlsx` is NOT authoritative OCR V2** — it is the V1 engine's shadow-served workbook and must not be treated as OCR V2 output.

**Naming hazard flagged:** the V2 authoritative file (`ocr_v2_lucky_cement_2025_…`) and the V1 shadow file (`lucky_2025_shadow_…`) share the `lucky…2025` stem and the same 16:14 run window, but are different engines — exactly the confusion that makes a single, clearly-named canonical export important.

---

## One-Paragraph Verdict

The Lucky rerun produced three workbooks that resolve into two: a governed OCR V2 canonical-metrics workbook, emitted as two content-identical files — `ocr_v2_r2_workbook.xlsx` (the validation copy) and `ocr_v2_lucky_cement_2025_20260604T161417Z.xlsx` (the published export), both a single 582-row "OCR V2 Canonical Metrics" sheet scoring 52 exact plus 14 source-insufficient for 66/66 — and a 49-sheet `lucky_2025_shadow` workbook that is not OCR V2 at all but the V1 engine's shadow-served output, returned by `ShadowOCRPipeline` with `v2_output_consumed_by_caller=False` and still carrying V1's ×1000 scale and wrong-value failures. The 66/66 and 52+14 results came from the V2 canonical workbook; the shadow rendering review came from the V1 file. The authoritative OCR V2 output is therefore the canonical-metrics workbook — the published `ocr_v2_lucky_cement_2025_…` export, with `ocr_v2_r2_workbook.xlsx` as its identical validation twin — and the shared `lucky…2025` naming with the V1 shadow file is precisely the lineage hazard to eliminate, because the only governed, validated, downstream-safe OCR V2 artifact is the single-sheet canonical export, never the 49-sheet V1 workbook that merely sits beside it.
