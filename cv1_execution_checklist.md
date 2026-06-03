# CV1 Execution Checklist

**Status:** Go/no-go operational checklist for starting CV1. No results, no measurements. Each item has an owner and a binary state.
**Rule:** CV1 analyst review begins only when all **Must-Before** items are ✅. Lucky-first is permitted while Millat items are still being confirmed.

---

## 1. Analyst Assignment

- ☐ Primary reviewers named — **qualified financial analysts**, COI-clear (not the OCR implementer or their team). *(Owner: program lead)*
- ☐ Census grid split across reviewers (by issuer or metric-block); each cell has one primary reviewer. *(Lead)*
- ☐ **S1 second-reviewer routing** established — every scale-flagged (**S**), note-vs-statement (**N**), and baseline-`corrected_*` cell routes to a second independent reviewer. *(Lead)*
- ☐ Reviewer ↔ cell assignment recorded for audit. *(Lead)*

## 2. Adjudicator Assignment

- ☐ **Senior financial analyst** named as adjudicator, independent of both reviewers. *(Lead)*
- ☐ Adjudication worksheet stood up (`ocr_review_workbook_spec.md §3`) and linked to the workbook by `adjudication_ref`. *(Adjudicator)*
- ☐ Adjudication rules confirmed: scale → units header; unit → label context; multi-table → primary-statement anchor; S1 → corrected-then-re-sample. *(Adjudicator)*

## 3. Blind-Gate Verification

- ☐ **Release gatekeeper** named (holds Section-B values; not a reviewer). *(Lead)*
- ☐ **Blind Packs** prepared per reviewer — Section A blanks + `cited_source_page` + `statement_to_check`, **with no system values**. *(Lead)*
- ☐ Lock-then-reveal sequencing in place (Section A locked + timestamped before Section B released). *(Gatekeeper)*
- ☐ Post-reveal-edit rule active: any locked Section A edited after reveal → cell re-assigned to a different reviewer. *(Gatekeeper)*

## 4. Bundle Pin Verification

- ☐ **Lucky** bundle pinned: fingerprint `97c3123…` confirmed; bundle is frozen (no live re-extraction). *(Lead)*
- ☐ **Millat** bundle pinned: fingerprint confirmed/recorded; **value-year span confirmed** against the bundle (absent years kept as `presence` cells). *(Lead — Lucky may start first)*

## 5. PDF Verification

- ☐ The **exact source report PDF matching each bundle fingerprint** is available to reviewers (Lucky 2025 report; Millat report). *(Lead)*
- ☐ PDF page numbering matches the bundle's `page_number` provenance (so `cited_source_page` opens the right page). *(Lead)*
- ☐ Reviewers confirmed to validate against the **bundle's own source report** (comparatives from its columns/summary), not standalone prior-year reports. *(Reviewers)*

## 6. Operationalization Confirms

- ☐ **OCR stored-value scale convention documented** (the one MI-1 sub-item) — read from the OCR engine spec, recorded for the `numeric_scale_aware` comparison. *(Lead)*
- ☐ Section-B per-cell values pre-derived from the frozen bundle (deterministic, per `cv1_operationalization_spec.md §1`) and held by the gatekeeper. *(Lead)*
- ☐ Per-cell `cited_source_page` pre-populated into Section A (§2). *(Lead)*
- ☐ Canonical-metric appendix (§4) + severity lookup (§5) embedded in the workbook. *(Lead)*

## 7. Census & Calibration

- ☐ Workbook instantiated with **Lucky 66 + Millat 66** census rows (Sections A/C pre-populated). *(Lead)*
- ☐ Adversarial rows appended (scale-flagged + note-vs-statement census; review-gated/conflict/missing-year sample). *(Lead)*
- ☐ **Calibration set completed + reconciled** (`cv1_calibration_set.md`); calibration sign-off recorded before main pass. *(All reviewers + adjudicator)*

## 8. Export Verification

- ☐ Workbook→schema **export rules** in place (`cv1_operationalization_spec.md §6`); mapping confirmed 1:1 to `ocr_truth_set_schema.md`. *(Lead)*
- ☐ Export **integrity check** defined: every census `cell_id` present; non-excluded items have `expected` + `actual` + `disposition`; version pins populated. *(Lead)*
- ☐ Truth-set envelope ready (`truth_set_id`, `truth_set_version`, pins) for CV5 harness consumption. *(Lead)*

---

## 9. Go / No-Go

- **GO (Lucky):** Sections 1–3, 4 (Lucky), 5 (Lucky), 6, 7, 8 ✅.
- **GO (Millat):** add Section 4 (Millat) + 5 (Millat) ✅.
- **NO-GO** if any Must-Before in 1–8 is unchecked.

CV1 produces no measurement until review begins; this checklist only authorizes the start.

---

## 10. One-Line Note

When the analysts and adjudicator are assigned and COI-clear, the gatekeeper holds the system values behind locked blind packs, both bundles are fingerprint-pinned with their exact source PDFs in hand, the scale convention is documented, and calibration is reconciled — CV1 may begin, Lucky-first.
