# OCR V2 — Statement Workbook Rendering Audit

**Status:** Audit only. No code modified. Lineage traced from the shipped modules + the actual workbook artifacts.
**Date:** 2026-06-04
**Objective:** why does the 49-sheet human-readable statement workbook diverge from the validated 66/66 canonical OCR V2 workbook?
**Companion:** `ocr_v2_statement_rendering_audit.json`.

---

## 0. Headline

**The two workbooks are produced by two different engines.** The validated canonical workbook is V2's governed output; the 49-sheet human-readable workbook is **V1's served output** under the shadow pipeline — it never consumes V2's canonical values. There is **no V2 multi-sheet statement renderer**; the only V2 workbook is the single-sheet "OCR V2 Canonical Metrics" (66/66, correct). The divergence is an **architectural output split**, not a rendering bug.

## 1. Data lineage (Task 1)

| Workbook | Source inputs | Generation module | Generated from |
|---|---|---|---|
| **Canonical** `ocr_v2_r2_workbook.xlsx` (1 sheet) | V2 registry → statement/scale/entity governance → canonical selection | `OCRV2WorkbookGenerator` | **canonical selected values** (66/66, governed) |
| **Human-readable** `lucky_2025_shadow_…xlsx` (49 sheets) | V1 `ocr_engine` pipeline output (populated `CompanyContext`) | `ocr_engine` workbook population via `ShadowOCRPipeline` (primary = V1) | **V1 workbook structures** |

**Decisive evidence:** `ShadowOCRPipeline(IOCRPipeline).process()` runs `primary=V1` + `shadow=V2`, **returns `primary_result` (V1)**, and records `"v2_output_consumed_by_caller": False`. The 49-sheet workbook is V1's served output; it does not read V2 canonical values, registry candidates, or selections. Its sheet set (Notes, Du Pont Analysis, Economic Value Added, Statement Of Value Addition, Income Statement, Balance Sheet, Cash Flow…) is the V1 OCR workbook structure.

## 2. Canonical vs rendered values (Task 2)

**Divergence stage = the output source (engine), not a transform of V2.** The human-readable workbook is V1, which never passes through V2 governance/selection/scale-normalization, so it carries V1's original CV1 failures.

**Revenue (illustrative):**
| Year | Canonical V2 (thousands) | Human-readable V1 | Divergence |
|---|---|---|---|
| 2020 | 41,870,796 | 41,870,796,000 | **×1000 scale** |
| 2021 | 62,940,805 | 62,940,805,000 | ×1000 scale |
| 2022 | **81,093,525** | **95,000,000** | **wrong value** |
| 2023 | 95,832,147 | 95,832,147,000 | ×1000 scale |
| 2024 | 115,324,942 | 115,324,942,000 | ×1000 scale |
| 2025 | **124,511,744** | **528,651,878,000** | **wrong value (not unconsolidated revenue)** |

All seven headline metrics (revenue, gross_profit, operating_profit, profit_after_tax, eps, operating_cash_flow, long_term_debt) diverge for the **same** reason — the human-readable workbook is V1, not a rendering of V2 canonical — with per-metric divergence following V1's known CV1 failure pattern (scale corruption + wrong-statement/wrong-value selection).

## 3. Governance preservation (Task 3)

| Guarantee | Canonical V2 workbook | Human-readable V1 workbook |
|---|---|---|
| Canonical selections respected | ✅ | ❌ |
| Source-insufficient abstentions respected | ✅ | ❌ |
| Source precedence respected | ✅ | ❌ |
| Scale normalization preserved | ✅ | ❌ |

V2 governance is preserved **only** in the canonical workbook. The human-readable workbook is V1 output and reflects **none** of V2's governance — it predates/bypasses it entirely.

## 4. Root-cause classification (Task 4)

**`source_bypass` (architectural).** The human-readable workbook does not consume V2 canonical output at all; it is the V1 engine's served output under the shadow design. Ruled out: `rendering_bug` (no V2 statement renderer exists), `scaling_bug`/`candidate_selection_bypass` within V2 (V2 canonical is correct), `workbook_mapping_bug`. Confirmed: **source_bypass + architectural_split** (two engines, two workbooks).

## 5. Production impact (Task 5)

- **Canonical V2: CORRECT** (66/66, governed) — not affected.
- **Human-readable served output: V1, ungoverned** — scale-corrupted + wrong-selection (the original CV1 failures).
- Closest to **A (canonical correct; the human-facing output wrong)**, but the cause is the architectural split, not a renderer defect. **Partly expected by design:** shadow mode intentionally serves V1 and keeps V2 non-serving, so the V1-vs-V2 gap is the expected pre-cutover divergence — **not a new bug**. The real risk is **mislabeling** the V1 shadow workbook as "OCR V2" output: end users looking at the 49-sheet workbook are seeing V1, while the validated V2 values live only in the single-sheet canonical workbook and the shadow evidence.

---

## Final Determination

# ARCHITECTURAL_OUTPUT_SPLIT

The validated canonical OCR V2 workbook and the human-readable statement workbook are produced by **different engines**: the canonical is V2's governed single-sheet output (66/66 correct), and the 49-sheet human-readable workbook is **V1's served output** under the shadow pipeline, which by design returns V1 and does not consume V2 canonical values (`v2_output_consumed_by_caller: False`). The divergence — ×1000 scale plus outright wrong values like 2022 revenue 95,000,000 and 2025 revenue 528,651,878,000 — is V1's original ungoverned CV1-failure output, not a defect in any V2 renderer (none exists for multi-sheet statements). Canonical V2 is correct; the human-facing workbook is the un-fixed V1; the gap is an architectural split, expected in shadow mode but dangerous if the V1 workbook is presented as "OCR V2."

---

## One-Paragraph Verdict

The statement workbook does not diverge from the canonical because of a rendering bug — it diverges because it is not OCR V2 at all: the 49-sheet `lucky_2025_shadow` workbook is the V1 `ocr_engine` pipeline's served output, produced and returned by `ShadowOCRPipeline` which runs V2 only as non-serving shadow evidence and explicitly marks `v2_output_consumed_by_caller=False`, so it carries V1's original failures — revenue rendered at ×1000 scale and, for 2022 and 2025, simply wrong values (95,000,000 and 528,651,878,000 against the validated 81,093,525 and 124,511,744) — none of which pass through V2's governance, selection, abstention, or scale normalization. The validated canonical V2 workbook is correct and governed but exists only as a single "OCR V2 Canonical Metrics" sheet; there is no V2 renderer that projects those canonical values into a human-readable multi-statement workbook, which is exactly the gap. The determination is **ARCHITECTURAL_OUTPUT_SPLIT**: two engines, two workbooks, with the human-facing one still being the un-fixed V1 — expected under shadow mode, but a real hazard if anyone treats the 49-sheet workbook as OCR V2 output, and a clear signal that a V2 human-readable statement renderer (sourced strictly from canonical selected values) is the missing deliverable before V2 can be the served, user-facing engine.
