# OCR V2 — Output Readiness Audit

**Status:** Evidence-based audit. Files read directly; nothing inferred or assumed.
**Date:** 2026-06-04
**Objective:** determine whether a complete OCR V2 output exists that can participate in a V1 vs V2 comparison.

---

## SECTION 1 — OCR V1 Output

| Attribute | Finding (read from file) |
|---|---|
| **Workbook** | `lucky_full_ocr_after_regression_fixes_20260602T133227682153_d80f3614.xlsx` — `C:\AI Financial Intelligence\output\` |
| Row/sheet count | **22 sheets** (Notes 423 rows, Cash Flow 76, Balance Sheet, Income Statement, Debt Schedule, Financial Ratios, Insights, …) |
| Schema summary | Per-statement sheets, header `Metric` + year columns (e.g. `Metric, 2024, 2025`) |
| **MSIL bundle / kb.json** | `lucky_full_ocr_after_regression_fixes_20260602T133227682153_d80f3614.kb.json` |
| kb.json schema | keys: `company_name`, `financial_year_consolidation_result`, `insights_results_by_report_year`, `report_years` (list[1]), `workbook_cell_mappings` (**list[1867]**), `workbook_fingerprint`, `workbook_id`, `workbook_result` |
| Generation source | **Real full OCR run on the Lucky annual-report PDF** ("full_ocr_after_regression_fixes") |
| **Suitable for comparison?** | **YES** — a genuine, multi-sheet, 1867-cell-mapping extraction from the real PDF; this is a valid V1 baseline |

## SECTION 2 — OCR V2 Output

| Artifact | Path | Rows | Schema | Generation source |
|---|---|---|---|---|
| V2 workbook | `output/ocr_v2_workbook_generation.xlsx` | **15** data rows (sheet "OCR V2 Canonical Metrics") | `metric_id, value_year, canonical_value, entity_ref, basis, statement_type, entity_scope, source_scale, source_unit, page_number, table_reference, source_reference, provenance_reference, selected_candidate_id` | **Regression oracle** — rows are the oracle's *correct* candidates |
| V2 MSIL export | `output/ocr_v2_msil_export_audit.json` (audit) | **15** signals | MSIL-compatible IntelligenceSignal adapter | Same 15 oracle cases |
| V2 capture audit | `output/ocr_v2_candidate_capture_audit.json` | **3** candidates | candidate facts | **Audit fixture** (`_audit_fixture_rows`) |
| V2 selection audit | `output/ocr_v2_canonical_selection_audit.json` | **30** candidates evaluated → 15 selected | selection decisions | 15 oracle cases × 2 candidates = 30 |
| V2 phase reports P1/P6/P7 | `output/ocr_v2_phase{1,6,7}_report.json` | P1 `candidates_created: 3`; P6 `workbook_rows_generated: 15`, `regression_cases_verified: 15`; P7 `rows_exported: 15` | — | every report: `ocr_extraction_changes_added: false` |

**Direct evidence of source (read from the V2 workbook rows):** the 15 rows carry oracle cell-ids and provenance, e.g.
`revenue, 2021, "62,940,805", … table_reference="revenue_2021_scale_correct", provenance_reference="PDF_TRUTH_SET_lucky_2025.md:Revenue:2021:p164…"`.
The `*_correct` identifiers and `ocr_v2_candidate_*` synthetic ids show these are the **regression oracle's correct candidates**, not extracted values.

**Determination for Section 2:** **A — Regression-oracle test data only.** Not real OCR V2 extraction output.

## SECTION 3 — Comparison Readiness

**Can OCR V2 currently produce a workbook from a real PDF? — NO.** Evidence:

- **No PDF reader exists in any V2 module.** `grep` for `pdf|fitz|pymupdf|camelot|.pdf|kb.json|FinancialYearConsolidation|insights_extraction` across `backend/ocr/*.py` (excluding tests) returns **nothing**.
- **V2 capture ingests injected rows, not a PDF.** `CandidateCapture.capture(rows: Iterable[CandidateCaptureInput | Mapping])` — its input is pre-structured candidate dicts; the audit run created **3 candidates from an internal fixture**.
- **No real-PDF input, no real generated workbook.** There is no `input PDF → V2 workbook` path; the only V2 workbook (`ocr_v2_workbook_generation.xlsx`) was generated from the 15 oracle cases (P6 report: `regression_cases_verified: 15`, `ocr_extraction_changes_added: false`).
- **No bridge from V1 OCR output into V2 either** (no reference to `kb.json` / `workbook_cell_mappings` in any V2 module).

There is **no evidence of any real PDF run**; the required evidence (input PDF, generated workbook from it, row count, output location) **does not exist**.

## SECTION 4 — Gap Analysis

All four candidate gaps are **confirmed true**:

- ✅ **Extraction integration missing** — V2 has no PDF→candidate path and no adapter from the existing V1 OCR table extraction. The shipped "P1 Candidate Capture" is a candidate **ingestion/validation** layer (takes rows), not the "PDF → fact candidates" **extractor** the Implementation Plan described.
- ✅ **Workbook generated only from the regression fixture** — `ocr_v2_workbook_generation.xlsx` = 15 oracle correct candidates.
- ✅ **MSIL export generated only from oracle cases** — 15 signals, `regression_cases_verified: 15`.
- ✅ **No real PDF run completed** — capture produced 3 fixture candidates; no Lucky-PDF extraction artifact exists.

**What is missing, precisely:** a real **PDF → V2 `CandidateCaptureInput` rows** front-end (a new extractor, or an adapter mapping the existing V1 OCR table/extraction output into V2 candidate rows), run over the Lucky bundle to produce a **full canonical workbook across the 66 metric-year cells**. Until that exists, V2 has no real output to compare.

## SECTION 5 — Final Determination

# NOT_READY_FOR_V1_V2_COMPARISON

**Justification (actual artifacts only):**
- **V1 side is ready:** a genuine real-PDF workbook (`lucky_full_ocr_after_regression_fixes_*.xlsx`, 22 sheets) and `.kb.json` (1867 cell mappings) exist — a valid comparison baseline.
- **V2 side is not:** the only V2 output is `ocr_v2_workbook_generation.xlsx` containing **15 rows that are the regression oracle's own correct values**, produced by feeding injected candidates through the governance→selection→workbook→export pipeline. V2 has **no PDF extraction front-end**, **no real run**, and therefore **no extracted workbook** to compare.
- **A comparison is not merely incomplete but invalid:** (1) it would cover only 15 of 66 cells; and (2) for those 15, V2 was *handed the correct values* (the oracle), so it would trivially "match truth" — a circular result that measures nothing about extraction. Comparing a real V1 workbook against V2's oracle-echo would produce a meaningless verdict.

The V2 **engine logic** (governance, selection, workbook projection, MSIL adapter) is implemented and proven on the oracle — that finding from prior reviews stands. But the **extraction integration** that would let V2 produce a real workbook from the Lucky PDF **was never built**, and it is the precondition for any V1 vs V2 comparison. This audit corrects the operational picture: "engine ready on injected candidates" is true; "V2 can produce a real comparable output" is **false**.

---

## One-Paragraph Verdict

Reading the actual files, OCR V1 has a real output — a twenty-two-sheet workbook and a 1,867-mapping `.kb.json` extracted from the Lucky annual-report PDF — and is a valid comparison baseline, but OCR V2 has no comparable artifact: its only workbook contains exactly fifteen rows that are the regression oracle's own *correct* candidates, generated by pushing injected candidate dicts through the governance-selection-workbook-export pipeline, and every phase report confirms `ocr_extraction_changes_added: false` while no V2 module contains any PDF reader, extractor, or bridge from the V1 OCR output. OCR V2 therefore cannot currently produce a workbook from a real PDF; the extraction front-end the Implementation Plan called "Candidate Capture (PDF → fact candidates)" was shipped only as a candidate-ingestion-and-validation layer fed by fixtures, so the engine is genuinely proven on the oracle yet has never seen a real document. A V1-vs-V2 comparison run today would cover only fifteen of the sixty-six cells and, worse, would be circular because V2 was handed the truth values it would be "validated" against — so the determination is **NOT_READY_FOR_V1_V2_COMPARISON**, and the single missing piece is a real PDF→candidate extraction path feeding the existing, already-correct V2 pipeline.
