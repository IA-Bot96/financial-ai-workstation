# OCR V2 — Millat Validation Program Design

**Status:** Planning and validation design only. No implementation, no code changes.
**Date:** 2026-06-04
**Purpose:** design the minimum validation program to establish **multi-issuer confidence** and clear the sole remaining freeze blocker (validation completed only on Lucky).

---

## 0. Why Millat, and what it must prove

The freeze review left exactly one blocker: the Lucky 66/66 rests on a **single issuer** and leans on **Lucky-tuned remediations** — most of all the **positional total_liabilities subtotal labeling** and the **OCF alias disambiguation**. The Millat program exists to **retire that over-fit risk** by proving the *same unchanged pipeline* reaches correctness on a **structurally different** issuer.

**Structural difference (verified):** Millat is **four separate annual PDFs** (2022, 2023, 2024, 2025), each a single-year report with current + one comparative year (e.g. the 2025 report carries 2024/2025). There is **no "Six Years at a Glance" summary and no analysis-table block** like Lucky's p162/163/164. Millat's metric values therefore come from **each report's primary statements**, not from summary/analysis tables. This matters enormously:
- The Lucky heuristics most at risk (TL positional subtotal, OCF alias, summary-vs-primary precedence) operate on structures Millat presents *differently* — so Millat is a genuine generalization test, not a re-run.
- A "66-cell (11×6)" census is **not natural** for Millat: from four report-years the clean span is **2022–2025 (4 report years)**, extendable to 2021 via comparatives. The natural full census is ~**11 × 4–5 = 44–55 cells**, not 66.

---

## 1. Artifacts that MUST be created for Millat

| Artifact | Description |
|---|---|
| **Millat truth set** | `millat_truth_set_v1_0_0.csv/json` — schema-conformant (same 15 fields as `cv1_truth_set_lucky_v1_0_0`), one row per (metric, year), `truth_status ∈ {VALUE, SOURCE_INSUFFICIENT}`, sourced from the four PDFs' primary statements |
| **Millat regression oracle** | `ocr_v2_millat_regression_cases.json` — mirrors the Lucky oracle (failure-class-tagged candidate pairs + `expected_governance_result`) |
| **Millat V2 extraction tables** | bbox CSVs for the metric-bearing pages across the 4 PDFs (staged like `bbox_extraction_poc/tables`) |
| **Millat bridge config** | Millat-specific `page-range → (basis, statement_type, entity_scope)` map + label/alias confirmations (analogous to the Lucky bridge config) |
| **Millat validation/comparison run + audit** | run the unchanged V2 pipeline → workbook → comparison vs truth set → coverage audit |

## 2. Artifacts REUSABLE from Lucky (no recreation)

| Reusable | Reuse note |
|---|---|
| Truth-set **schema** (15 fields) | identical; only data differs |
| Regression-oracle **structure** (failure classes, `expected_governance_result` vocabulary) | mirror exactly so the same fixture harness loads it |
| **Comparison workbook spec** + `numeric_scale_aware` comparator | unchanged |
| **CV1 protocol** (blind Section-A lock, adjudication, S1 second-review) | unchanged; applied to a Millat calibration subset |
| **Thresholds 1.0.0** | unchanged |
| **Entire V2 pipeline** — capture, registry, governance (statement/scale/entity), canonical selection, workbook, MSIL export | **must not change** — that is the whole point of the test |
| **bbox extraction method** (camelot + pdfplumber) + table-adapter + lucky_run harness pattern | reused; only inputs/config differ |

**Principle:** Millat reuses all *machinery and schema*; it creates only *data* (truth set, oracle, extraction tables, config). If the pipeline needs to change to pass Millat, that is a finding, not a fix.

## 3. Is a full 66-cell truth set required? — NO

A 66-cell census is a Lucky artifact (one report, six-year summary). Millat's natural census is ~44–55 cells (11 metrics × 4–5 report years). More importantly, the **freeze gate does not require a full census at all** — it requires evidence that the pipeline generalizes. A full Millat census is part of **FULL** validation (for CERTIFIED pooling), not the **minimum**.

## 4. Is a reduced validation set sufficient? — YES, for the freeze gate

The minimum must do one job: **retire the over-fit risk**. That requires a **targeted truth subset** that (a) covers all failure classes Millat actually presents and (b) **specifically exercises the Lucky-tuned heuristics**:
- **total_liabilities** — does the positional "unlabeled subtotal before TOTAL EQUITY AND LIABILITIES" rule fire correctly on Millat's balance sheet? (highest-priority over-fit check)
- **operating_cash_flow** — does the "Net cash generated from operating activities" alias disambiguation generalize?
- **consolidated vs unconsolidated basis** — *only if* Millat presents consolidated statements (Millat Tractors is largely standalone; if no consolidated set exists, this class cannot be tested on Millat and remains Lucky-only — a documented residual).
- **investee contamination** — *only if* Millat discloses JV/associate figures (Millat has a Related Parties table; to be confirmed).
- **scale, note, summary, source-selection** — covered where Millat presents them.

**Minimum truth subset:** the 11 metrics × the 4 report years (2022–2025), sourced from each report's primary statements (≈44 cells minus Millat's genuine `SOURCE_INSUFFICIENT` cells), with the heuristic-bearing metrics (TL, OCF, LTD) mandatory. This is "reduced" by dropping the 2021 comparative reconstruction and not requiring full blind-CV1 across every cell.

## 5. Should the Millat oracle mirror the Lucky structure? — YES

Mirror it exactly (same `fixture_version` schema, `failure_class` enum, `correct_candidate`/`incorrect_candidate` pairs, `expected_governance_result`). Reasons:
- The **same regression-fixture harness** loads and runs it — zero new tooling.
- It can be **pooled/appended** with the Lucky oracle into one multi-issuer regression suite.
- It forces the Millat cases to be expressed as the same governance verdicts (`ELIGIBLE`/`INELIGIBLE`/`REVIEW_REQUIRED`/`SCALE_*`), which is exactly the by-construction behavior being generalized.
- ~10–15 candidate-pair cases covering the failure classes Millat presents (mandatorily ≥1 TL-subtotal case and ≥1 OCF-alias case).

## 6. Estimated Effort

| Task | Minimum | Full | Driver |
|---|---|---|---|
| **Truth-set creation** | **Medium** (~1–2 analyst-days) | High (~3–4 days) | 4 PDFs to read (vs Lucky's 1), but primary statements are clean/labeled — no six-year-summary reconstruction. Minimum = 4 report-years; Full = +2021 comparatives + cross-report consistency |
| **Oracle creation** | **Low–Medium** (~0.5–1 day) | Medium (~1.5 days) | Mirror Lucky structure; derive pairs from truth subset + a V2 capture run; Full = exhaustive class coverage |
| **Validation execution** | **Low** (~1 day) | Medium (~2 days) | Reuse harness; bulk is staging bbox tables for metric pages + Millat page-range config. Full adds full blind-CV1 across all cells + Wilson pooling |
| **Blind CV1** | calibration subset only (~0.5 day) | full census blind review + adjudication | Minimum: blind-verify a calibration subset → CONDITIONAL; Full: full protocol |

**Total: minimum ≈ 3–4.5 effort-days; full ≈ 8–10.** The pipeline itself costs zero (unchanged).

---

## 7. Final Determination

# Recommended: MINIMUM_ACCEPTABLE_MILLAT_VALIDATION (for the freeze gate)

**Definition (minimum):** a targeted Millat truth subset (11 metrics × 4 report-years, heuristic-bearing metrics mandatory) + a mirrored ~12-case regression oracle (≥1 TL-subtotal, ≥1 OCF-alias) + staged extraction tables + Millat bridge config, run through the **unchanged** V2 pipeline and the existing comparison harness, with **blind CV1 on a calibration subset → CONDITIONAL** disposition.

**Rationale.** The freeze blocker is *multi-issuer confidence / over-fit retirement*, **not statistical certification**. The minimum set directly attacks the exact risks the freeze review named — it re-runs the Lucky-tuned heuristics (TL positional subtotal, OCF alias) and the failure-class governance on a **structurally different** issuer (per-year reports, no summary tables) using a pipeline that **may not change**. If the minimum set passes (correct values, preserved abstentions, zero governance violations, heuristics fire correctly), the over-fit risk is retired and freeze is justified at **CONDITIONAL**. If it fails, it has found a real generalization defect — which is the point.

**FULL_MILLAT_VALIDATION** (complete ~55-cell census incl. 2021 comparatives + cross-report consistency + full blind CV1 across all cells + Wilson pooling toward **CERTIFIED**) is **deferred to the pre-production / certification stage**, where multi-issuer pooling is needed to clear the thresholds-1.0.0 Wilson ≤0.5% bar that no single issuer can reach.

**Two honest caveats carried into the determination:**
1. **Some Lucky failure classes may be untestable on Millat** (consolidated-vs-unconsolidated basis and investee contamination, if Millat lacks consolidated statements / disclosed investees). Those remain **Lucky-only-validated** — a documented residual that a *third* issuer would eventually close. The minimum tests what Millat presents and records what it cannot.
2. **The minimum yields CONDITIONAL, not CERTIFIED** — sufficient to freeze, not to certify for production. That ordering matches the freeze-then-integrate sequence.

---

## One-Paragraph Verdict

Millat is the right instrument to retire the single risk blocking freeze, precisely because it is structurally unlike Lucky — four separate per-year PDFs with primary statements and no six-year summary or analysis-table block — so running the **unchanged** OCR V2 pipeline against it genuinely tests whether the Lucky-tuned remediations (the positional total-liabilities subtotal and the operating-cash-flow alias above all) generalize or merely fit. The program reuses every piece of machinery and schema — truth-set format, oracle structure, comparator, CV1 protocol, thresholds, and the entire pipeline — and creates only Millat data: a **targeted truth subset of the eleven metrics across the four report-years** (not a full 66- or 55-cell census), a **mirrored ~12-case regression oracle** that must include at least one total-liabilities-subtotal and one OCF-alias case, the staged extraction tables, and a Millat bridge config. That **MINIMUM_ACCEPTABLE_MILLAT_VALIDATION**, run to a blind-CV1 **CONDITIONAL** disposition with zero governance violations and the heuristics firing correctly, retires the over-fit risk and clears the freeze blocker at an estimated three to four-and-a-half effort-days, while the **FULL** census-plus-blind-CV1-plus-Wilson-pooling effort is correctly deferred to the certification stage that production integration — not freeze — actually requires.
