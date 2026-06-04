# OCR V2 — Final Gap Audit (R1-B)

**Status:** Audit only. No implementation. No code changes.
**Scope:** Lucky Cement truth set `cv1_truth_set_lucky_v1_0_0` (66 cells, 11 metrics × FY2020–FY2025).
**Run under audit:** `ocr_v2_r1_*` (real extraction run, `oracle_injected_values = false`).

## Sources read

| File | Role |
|---|---|
| `cv1_truth_set_lucky_v1_0_0.csv` | Ground truth (66 cells) |
| `output/ocr_v2_r1_report.json` | Headline R1-B validation summary |
| `output/ocr_v2_r1_audit.json` | Per-cell results (`cell_results`, 66), `per_metric`, `coverage` |
| `output/ocr_v2_r1_run_audit.json` | Stage-level run audit |
| `output/ocr_v2_lucky_candidates_r1.json` | Upstream candidates (`candidate_inputs`, 1,905) |
| `output/ocr_v2_lucky_registry_r1.json` | Registry (`candidates`, 1,905) |
| `output/ocr_v2_lucky_workbook_r1.xlsx` | Emitted workbook |
| `output/source_precedence_audit.json`, `source_insufficient_audit.json`, `scale_capture_audit.json`, `metric_resolution_audit.json`, `eps_alias_audit.json` | Supporting stage audits |

## Current standing (from artifacts, not re-derived)

| Metric | Value |
|---|---|
| Truth-set cells | 66 |
| Covered cells | 60 (90.91%) |
| Exact matches (VALUE) | 46 |
| Correct `SOURCE_INSUFFICIENT` abstentions | 14 |
| `SOURCE_INSUFFICIENT` violations | 0 |
| Value mismatches | 0 |
| Scale mismatches | 0 |
| **Missing cells** | **6** |

The 14 truth `SOURCE_INSUFFICIENT` cells (`total_debt` 2020–2025; `total_liabilities` 2020–2023; `long_term_debt` 2020–2023) are **correctly abstained** and are **not** gaps. The only gaps are the 6 missing VALUE cells below.

### Pages present in the extraction input (`bbox_extraction_poc`)

Present: **162, 163, 164, 271, 321, 322, 324, 328, 353, 356**
Absent (primary statements): **240 (Balance Sheet), 241 (P&L), 243 (Cash Flow)** — confirmed `false` in `source_precedence_audit.primary_statement_pages_present_in_bridge_input`.

Note: every FY2024/FY2025 VALUE that *was* recovered (revenue, gross_profit, operating_profit, profit_after_tax, EPS, total_assets, total_equity) came from the **six-year summary / supporting tables on pages 162–164 (columns 6–7)** — not from the absent primary statements. Page **241 is therefore NOT required** for 66/66; only the data that exists *solely* on pages 240 and 243 remains unreachable.

---

## 1. Exact list of unresolved cells (6)

### Cell 1 — `operating_cash_flow_2024`
- **Metric / Year:** operating_cash_flow / 2024
- **Truth value:** 27,580,741 (thousands, PKR) — source page 243 (primary statement)
- **Candidate exists upstream:** YES (page 162 summary, `27,581` **millions**; relabeled `operating_cash_flow_summary_reference`)
- **Candidate exists in registry:** YES (retained as non-canonical summary reference)
- **Governance outcome:** Summary FY2024 OCF demoted to `operating_cash_flow_summary_reference` (precedence requires `PRIMARY_STATEMENT`; the only available figure is millions-rounded `27,581` = 27,581,000 thousands ≠ truth 27,580,741)
- **Selection outcome:** Abstained — `selected_rows: []`, `summary_table_selected: false`, `remaining_limitation: primary_statement_candidate_not_available_in_bbox_input`
- **Root cause:** Thousands-precision value exists only on page **243** (absent). Summary proxy is millions-rounded and does not equal truth.
- **Classification:** `EXTRACTION_FAILURE` (required source page not in extraction input)
- **Required fix:** Ingest page 243 CSV into `bbox_extraction_poc` input.

### Cell 2 — `operating_cash_flow_2025`
- **Truth value:** 27,572,567 (thousands) — page 243
- **Candidate upstream:** YES (page 162 summary `27,573` **millions**, demoted to summary_reference)
- **Candidate in registry:** YES (non-canonical reference)
- **Governance outcome:** Same as Cell 1 — millions-rounded `27,573` ≠ truth; demoted.
- **Selection outcome:** Abstained (`primary_statement_candidate_not_available_in_bbox_input`)
- **Root cause:** Thousands value exists only on page **243** (absent).
- **Classification:** `EXTRACTION_FAILURE`
- **Required fix:** Ingest page 243 CSV.

### Cell 3 — `long_term_debt_2024`
- **Truth value:** 12,760,637 (thousands) — page 240 ("Long-term financing")
- **Candidate upstream:** YES but unusable — page 162 summary "Long term finance" `14,527` **millions**, retained as `long_term_debt_summary_reference`. No clean `Long-term financing` candidate exists (0 canonical LTD candidates resolved).
- **Candidate in registry:** YES only as contaminated summary reference; clean primary value NO.
- **Governance outcome:** Summary LTD demoted to `long_term_debt_summary_reference` — the summary "Long term finance" line is **deferred-grant-contaminated** (same reason 2020–2023 are truth `SOURCE_INSUFFICIENT`) and millions-rounded (14,527,000 ≠ 12,760,637).
- **Selection outcome:** Abstained (`primary_statement_candidate_not_available_in_bbox_input`)
- **Root cause:** Clean "Long-term financing" line exists only on page **240** (absent). Summary line is contaminated and not truth-equal.
- **Classification:** `EXTRACTION_FAILURE`
- **Required fix:** Ingest page 240 CSV.

### Cell 4 — `long_term_debt_2025`
- **Truth value:** 9,184,522 (thousands) — page 240
- **Candidate upstream:** YES but unusable — page 162 summary `10,567` millions (contaminated, demoted to summary_reference)
- **Candidate in registry:** YES (contaminated reference only); clean value NO
- **Governance outcome:** Same as Cell 3 — contaminated/rounded summary demoted.
- **Selection outcome:** Abstained (`primary_statement_candidate_not_available_in_bbox_input`)
- **Root cause:** Clean value exists only on page **240** (absent).
- **Classification:** `EXTRACTION_FAILURE`
- **Required fix:** Ingest page 240 CSV.

### Cell 5 — `total_liabilities_2024`
- **Truth value:** 86,256,813 (thousands) — page 240 ("unlabeled liabilities subtotal")
- **Candidate exists upstream:** NO explicit total-liabilities line anywhere (0 `total liabilities` rows). Components ARE present on page 163 (thousands): `non current liabilities` 32,068,340 + `current liabilities` 54,188,473 = **86,256,813 (exact)**.
- **Candidate in registry:** Explicit total NO; components YES.
- **Governance outcome:** No explicit-total candidate to promote; components are **not summed** (no-derivation policy — consistent with the truth set itself marking `total_liabilities` 2020–2023 as `SOURCE_INSUFFICIENT` / "components only (not summed)").
- **Selection outcome:** Abstained — no eligible explicit candidate.
- **Root cause:** Explicit subtotal line exists only on page **240** (absent). Value is arithmetically derivable from page-163 components, but derivation is intentionally not performed.
- **Classification:** `EXTRACTION_FAILURE` (primary). *Secondary note:* the figure is reconstructable by summation from currently-available sources — but doing so would be a **governance/policy change**, not an extraction recovery, and would not be truth-consistent (see Determination).
- **Required fix:** Ingest page 240 CSV (truth-faithful). Do **not** add blanket component-summation (see §4).

### Cell 6 — `total_liabilities_2025`
- **Truth value:** 90,837,630 (thousands) — page 240
- **Candidate upstream:** NO explicit total; components on page 163: 32,196,247 + 58,641,383 = **90,837,630 (exact)**
- **Candidate in registry:** Explicit total NO; components YES
- **Governance outcome:** No explicit total; components not summed (no-derivation).
- **Selection outcome:** Abstained.
- **Root cause:** Explicit subtotal only on page **240** (absent); derivable but not derived.
- **Classification:** `EXTRACTION_FAILURE` (primary; derivable — see §4)
- **Required fix:** Ingest page 240 CSV.

---

## 2. Root-cause breakdown

| Classification | Cells | Cell IDs |
|---|---|---|
| **EXTRACTION_FAILURE** (required source page absent from extraction input) | **6** | operating_cash_flow_2024, operating_cash_flow_2025, long_term_debt_2024, long_term_debt_2025, total_liabilities_2024, total_liabilities_2025 |
| ALIAS_FAILURE | 0 | — |
| GOVERNANCE_FAILURE | 0 | — |
| SELECTION_FAILURE | 0 | — |
| PRECEDENCE_FAILURE | 0 | — |
| WORKBOOK_FAILURE | 0 | — |
| OTHER | 0 | — |

**All 6 gaps share a single root cause: primary-statement pages 240 and 243 are absent from the `bbox_extraction_poc` input.**

The downstream pipeline is **not** at fault — and the audit evidence proves each stage behaved correctly:
- **Alias / metric resolution:** OCF (`Net Cash from Operating Activities`) and LTD (`Long-term financing` / `Long term financing`) aliases are present and resolved; EPS/GP/etc. fully restored. Not the cause.
- **Governance:** Correctly **demoted** the millions-rounded OCF summary proxy and the deferred-grant-**contaminated** LTD summary line to non-canonical `*_summary_reference` rows instead of emitting wrong values. This is correct behavior, not failure (0 integrity violations).
- **Selection / precedence:** Correctly abstained per the `PRIMARY_STATEMENT > NOTE > SUPPORTING_SCHEDULE > SUMMARY_TABLE > ANALYSIS_TABLE` order when no primary candidate was available (0 value mismatches, 0 scale mismatches).
- **Workbook:** Emitted every selected canonical value faithfully; no workbook-layer loss.

By classification rule (correctness over downstream): these are upstream **EXTRACTION_FAILURE** (ingestion gap), not OCR misreads of present pages.

---

## 3. Recovery estimate

| Action | Cells recovered | Coverage |
|---|---|---|
| Current state | — | 60 / 66 (90.91%) |
| **+ Ingest page 240** (Balance Sheet) | long_term_debt 2024, long_term_debt 2025, total_liabilities 2024, total_liabilities 2025 (**+4**) | 64 / 66 (96.97%) |
| **+ Ingest page 243** (Cash Flow) | operating_cash_flow 2024, operating_cash_flow 2025 (**+2**) | **66 / 66 (100%)** |

- Pages **240 + 243** together recover **all 6** missing cells → **66/66**.
- **Page 241 is NOT required** — its FY2024/25 metrics were already recovered from the six-year summary tables (pages 162–164).
- No alias, governance, selection, precedence, or workbook changes are required; the existing pipeline already converts present candidates into exact matches with zero mismatches.
- The two contaminated/rounded summary proxies retained for OCF/LTD FY2024–25 must remain **non-canonical**; once pages 240/243 are ingested, the primary-statement candidates will outrank them by precedence and select automatically.

---

## 4. Determination

**Can OCR V2 reach 66/66 using currently available extraction sources?**

> **No. Additional source pages are required — specifically pages 240 (Balance Sheet) and 243 (Cash Flow Statement).**

Justification, cell by cell:

- **operating_cash_flow 2024–25 (2 cells):** The only value present in available sources is the **millions-rounded** summary figure (27,581 / 27,573), which does **not** equal the thousands-precision truth (27,580,741 / 27,572,567). No correct-precision candidate exists anywhere except page **243 (absent)**. → **Requires page 243.**
- **long_term_debt 2024–25 (2 cells):** The only LTD figure in available sources is the **deferred-grant-contaminated**, millions-rounded summary "Long term finance" (14,527 / 10,567), which does not equal the clean truth (12,760,637 / 9,184,522). The clean "Long-term financing" line exists only on page **240 (absent)**. → **Requires page 240.**
- **total_liabilities 2024–25 (2 cells):** Exactly derivable from page-163 components (non-current + current = truth, to the rupee). However, deriving them is **not** a sound path to 66/66:
  1. It is a **governance/policy change** (introducing component summation), not extraction from currently-available evidence; and
  2. It is **not truth-consistent** — the same components exist for 2020–2023, yet the truth set deliberately marks `total_liabilities` 2020–2023 as `SOURCE_INSUFFICIENT` ("components only, not summed"). A blanket summation rule would convert those 4 cells to VALUE and **break 4 currently-correct abstentions** (introducing `SOURCE_INSUFFICIENT` violations). The truth-faithful subtotal exists only on page **240 (absent)**. → **Requires page 240.**

**Conclusion:**
- Maximum coverage achievable from the **currently available extraction sources, under the current evidence-only / no-derivation governance policy: 60/66 (90.91%)** — i.e., it is **already at that ceiling**. No reconfiguration of extraction, alias, governance, selection, precedence, or workbook stages can lift it further, because 4 of the 6 missing cells have **no acceptable candidate anywhere** in the present pages and the other 2 cannot be derived without violating the truth contract.
- **66/66 is reachable only by adding source pages 240 and 243** to the extraction input. Once those two CSVs are present, the existing R1-B pipeline is expected to reach **66/66** with no further architectural change (0 redesigns required), since the FY2024/25 columns it already handles on pages 162–164 prove the selection/precedence/workbook path is sound.

**Bottom line:** This is an **input-coverage gap, not a pipeline defect.** Required action: ingest primary-statement pages **240 and 243**; page 241 is not needed.
