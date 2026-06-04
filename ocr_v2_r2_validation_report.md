# OCR V2 R2 Validation Report

Determination: **READY_FOR_PRODUCTION_INTEGRATION**

## Summary

- Total cells: 66
- Exact matches: 52
- Source-insufficient matches: 14
- Covered cells: 66 / 66
- Coverage percent: 100.0%
- Value mismatches: 0
- Scale mismatches: 0
- Missing cells: 0
- Governance violations: 0

## Recovered Target Cells

- total_liabilities 2024: exact_match (truth=86,256,813, selected=86,256,813, page=240, provenance=page_0240_bbox_00_bbox_camelot_stream_table_00.csv:row:42:col:4)
- total_liabilities 2025: exact_match (truth=90,837,630, selected=90,837,630, page=240, provenance=page_0240_bbox_00_bbox_camelot_stream_table_00.csv:row:42:col:3)
- operating_cash_flow 2024: exact_match (truth=27,580,741, selected=27,580,741, page=243, provenance=page_0243_bbox_00_bbox_camelot_stream_table_00.csv:row:11:col:4)
- operating_cash_flow 2025: exact_match (truth=27,572,567, selected=27,572,567, page=243, provenance=page_0243_bbox_00_bbox_camelot_stream_table_00.csv:row:11:col:3)

## Remediation Notes

- OCF disambiguation uses the extracted source row label: only "Net cash generated from operating activities" maps to operating_cash_flow; "Cash generated from operations" is retained as cash_generated_from_operations.
- Total liabilities recovery labels the extracted unlabeled subtotal row under CURRENT LIABILITIES immediately before TOTAL EQUITY AND LIABILITIES. No arithmetic derivation or component summing is used.
- Canonical selection, governance, workbook generation, OCR extraction, and MSIL export logic were not redesigned.

## Remaining Failures

- None.
