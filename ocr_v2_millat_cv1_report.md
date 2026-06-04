# OCR V2 — Millat CV1 Validation Report

**Status:** Validation only. No OCR logic changes, no Millat-specific rules added.
**Date:** 2026-06-04
**Objective:** execute the first blind CV1 of OCR V2 on Millat Tractors and determine whether Lucky 66/66 generalizes to a structurally different issuer.

---

## 0. Headline

A **real, verified Millat truth set was created for FY2024/FY2025** (read directly from the unconsolidated primary statements). But the **OCR V2 comparison could not be executed**: V2 cannot be run *unchanged* on Millat, and the task's own constraint ("no Millat-specific rules") forbids adding the configuration that would be required. The generalization question is therefore **answered in a specific, important sense — negatively: OCR V2 has no issuer-general execution path.**

**Determination: GENERALIZATION_NOT_DEMONSTRATED / VALIDATION_BLOCKED.**

---

## 1. Truth Set — `cv1_truth_set_millat_v1_0_0.csv` (partially created, verified)

**40 cells** (10 metrics × intended FY2022–FY2025). Read directly from `millat-2025.pdf`:

| Metric | FY2025 | FY2024 | Source |
|---|---:|---:|---|
| revenue | 52,108,997 | 91,534,501 | p110 P&L "Revenue from contracts with customers" |
| gross_profit | 13,867,091 | 21,434,290 | p110 |
| operating_profit | 10,236,479 | 18,017,751 | p110 (explicit line) |
| profit_after_tax | 6,372,928 | 10,224,875 | p110 "Profit after tax" |
| eps | 31.94 | 52.26 | p110 (restated) |
| total_assets | 32,988,591 | 32,873,428 | p108 balancing total |
| total_equity | 8,076,300 | 10,953,152 | p108 share capital & reserves |
| total_liabilities | **SOURCE_INSUFFICIENT** | **SOURCE_INSUFFICIENT** | p108 components only; no explicit line / no unlabeled subtotal |
| long_term_debt | 460,690 | 894,649 | p108 "Long-term finances – secured" (non-current) |
| operating_cash_flow | 3,341,999 | 6,870,709 | p112 "Net cash flows generated from operating activities" |

- **Verified:** 18 VALUE + 2 SOURCE_INSUFFICIENT (FY2024/25), all unconsolidated, thousands PKR.
- **Pending (NOT fabricated):** FY2022/FY2023 (20 cells) require reading `millat-2022.pdf` / `millat-2023.pdf`, not yet performed.

**Structural observations (already informative for the over-fit question):**
1. Millat is **four separate per-year reports** — **no Lucky-style six-year summary / analysis tables**.
2. Millat's standalone balance sheet has **no explicit total-liabilities line AND no unlabeled subtotal** before TOTAL EQUITY AND LIABILITIES → `total_liabilities` is correctly `SOURCE_INSUFFICIENT`. This is exactly the structure that would test the **Lucky-tuned positional TL heuristic** — and on Millat that heuristic has *no subtotal row to grab*, so the correct outcome is abstention.
3. Millat has the **same OCF ambiguity as Lucky** ("Cash generated from operations" `10,253,249` vs "Net cash flows generated from operating activities" `3,341,999`) — the OCF alias disambiguation is directly relevant.
4. Millat 2025 is **restated**; FY ends June 30; **consolidated statements also exist** (NCI present) → the basis dimension is testable here.

## 2. OCR V2 Run — BLOCKED (cannot run unchanged)

Three concrete blockers (verified against the codebase):

| ID | Type | Detail |
|---|---|---|
| **B1** | EXTRACTION_INPUT_ABSENT | No Millat bbox extraction tables exist. The pipeline (`ocr_v2_lucky_run` / `table_adapter`) reads `output/bbox_extraction_poc/tables` — **Lucky tables only**. |
| **B2** | BRIDGE_CONFIG_ISSUER_COUPLED | The default bridge config is **Lucky-hardcoded**: page ranges 162–164 (summary/analysis), 236–283 (unconsolidated), 286–375 (consolidated), Lucky fingerprint, Lucky label aliases — **no generic derivation, no Millat config**. Millat's statements are on different pages (unconsolidated P&L p110, BS p108, CF p112 in a 298-page report), so the Lucky config tags every Millat page `UNKNOWN` → governance cannot classify → selection collapses. |
| **B3** | CONSTRAINT_CONFLICT | Running would require a **Millat bridge config** (Millat page ranges + label aliases), but that is **Millat-specific configuration**, which this task explicitly prohibits. So "run unchanged" is **unsatisfiable** on Millat under the stated constraints. |

## 3. Comparison Metrics

| Measure | Value |
|---|---|
| total_cells | 40 (10 × 4) |
| exact_matches | **NOT_COMPUTABLE** |
| source_insufficient_matches | **NOT_COMPUTABLE** |
| value_mismatches | **NOT_COMPUTABLE** |
| scale_mismatches | **NOT_COMPUTABLE** |
| missing_cells | **NOT_COMPUTABLE** |
| coverage_percent | **NOT_COMPUTABLE** |

**Reason:** OCR V2 produced **no Millat output**; there is nothing to compare against the truth set. *(No fabricated comparison is reported — doing so would violate the program's evidence-only / anti-closed-loop discipline.)*

## 4. Root-Cause Classification

Per-cell **miss** classification is **not applicable** — there is no V2 run, hence no misses. The **program-level blocker** is classified instead:

| Requested class | Blocker mapped |
|---|---|
| EXTRACTION_FAILURE | **B1** — no Millat extraction input exists |
| ALIAS_FAILURE | n/a (no run) |
| GOVERNANCE_FAILURE | n/a (no run) |
| SELECTION_FAILURE | n/a (no run) |
| WORKBOOK_FAILURE | n/a (no run) |
| *(new)* CONFIGURATION_GAP | **B2** — Lucky-coupled bridge config |
| *(new)* CONSTRAINT_CONFLICT | **B3** — Millat config forbidden by the task |

## 5. Generalization Finding

**Does Lucky 66/66 generalize to a structurally different issuer? — Not demonstrated; and the attempt reveals why.**

OCR V2's **governance/selection core may be issuer-general**, but the **executable pipeline is not**: it is coupled to a **per-issuer bridge config + staged extraction input**. Lucky 66/66 is the product of a **Lucky-tuned bridge config over the general core**, not a property of an engine that can be pointed at a new issuer and run. The very act of running on Millat requires creating Millat configuration — which is exactly where the over-fit risk the freeze review named would live. So the multi-issuer confidence the freeze gate needs **cannot be established by "running unchanged"**; it requires building Millat's bridge input and then testing whether the *same kind* of config + the unchanged core reach correctness.

## 6. Prerequisites to Unblock (then re-run)

1. Create **Millat bbox extraction tables** (camelot 1.0.9 / pdfplumber 0.11.9 are available) for the metric-bearing pages of the 4 reports.
2. Create a **Millat bridge config** (page ranges → basis/statement_type/entity_scope + label aliases) — the artifact the Millat Validation Plan flagged `MISSING_MUST_CREATE`. *(This is per-issuer input, the analog of telling the pipeline where Millat's statements are — distinct from a governance/selection logic change, but it must be reviewed for over-fit.)*
3. Complete the **FY2022/2023 truth set** from `millat-2022.pdf` / `millat-2023.pdf`.
4. Re-run the **unchanged governance/selection/workbook core** on the Millat input and compare — *that* is the valid generalization test.

---

## 7. One-Paragraph Verdict

This first attempt to validate OCR V2 on Millat produced a genuine, verifiable truth set for FY2024 and FY2025 — read straight from Millat's unconsolidated statement of profit or loss (p110), financial position (p108), and cash flow (p112), with revenue collapsing from 91.5bn to 52.1bn, total liabilities correctly source-insufficient because Millat prints no combined liabilities line and no unlabeled subtotal, and the same operating-cash-flow ambiguity Lucky has — but it could not produce an OCR V2 comparison, because OCR V2 cannot be run unchanged on Millat: there are no Millat extraction tables, the bridge config is hard-coded to Lucky's pages, aliases, and fingerprint with no generic fallback, and supplying a Millat config is precisely the "Millat-specific rule" the task forbids. No coverage number is reported because none exists, and fabricating one would betray the evidence-only discipline this program runs on. The honest determination is **GENERALIZATION_NOT_DEMONSTRATED / VALIDATION_BLOCKED**: Lucky's 66/66 is so far a property of a Lucky-tuned bridge over a possibly-general core, not of an issuer-general engine — and establishing real multi-issuer confidence requires first building Millat's extraction tables, bridge config, and full truth set, then re-running the unchanged core, which is the only path that can actually answer whether the engine generalizes or merely fit Lucky.
