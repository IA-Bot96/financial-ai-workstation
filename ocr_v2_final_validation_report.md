# OCR V2 Final Coverage Validation

**Status:** validation only. No OCR logic, governance, selection, workbook, or MSIL changes were made.

## Result

**Determination:** `NOT_READY_FOR_PRODUCTION_INTEGRATION`

| Measure | Value |
|---|---:|
| total_cells | 66 |
| exact_matches | 48 |
| source_insufficient_matches | 14 |
| value_mismatches | 0 |
| scale_mismatches | 0 |
| missing_cells | 4 |
| ambiguous_cells | 0 |
| coverage_percent | 93.94% |

## Extraction Set

- Staged tables directory: `output\ocr_v2_final_validation_tables`
- CSV files: `33`
- Pages available: `162, 163, 164, 240, 243, 271, 321, 322, 324, 328, 353, 356`
- Page 0240 CSVs: `3`
- Page 0243 CSVs: `3`

## Final Six Gap Cells

| Metric | Year | Truth value | Selected value | Source page | Status |
|---|---:|---:|---:|---:|---|
| `total_liabilities` | 2024 | 86,256,813 | none | none | `missing` |
| `total_liabilities` | 2025 | 90,837,630 | none | none | `missing` |
| `operating_cash_flow` | 2024 | 27,580,741 | none | none | `missing` |
| `operating_cash_flow` | 2025 | 27,572,567 | none | none | `missing` |
| `long_term_debt` | 2024 | 12,760,637 | 12,760,637 | 240 | `exact_match` |
| `long_term_debt` | 2025 | 9,184,522 | 9,184,522 | 240 | `exact_match` |

## Remaining Failures

| Metric | Year | Root cause | Explanation |
|---|---:|---|---|
| `total_liabilities` | 2024 | `unlabeled_subtotal_not_captured_as_candidate` | Page 240 now supplies the explicit subtotal value, but the row has no label. The current bridge captures labeled numeric rows only, so no total_liabilities candidate is created. Component rows are present but no derivation/summation is performed. |
| `total_liabilities` | 2025 | `unlabeled_subtotal_not_captured_as_candidate` | Page 240 now supplies the explicit subtotal value, but the row has no label. The current bridge captures labeled numeric rows only, so no total_liabilities candidate is created. Component rows are present but no derivation/summation is performed. |
| `operating_cash_flow` | 2024 | `selection_ambiguity_after_source_recovery` | Page 243 now supplies the truth row, but the bridge maps both cash generated from operations and net cash generated from operating activities to operating_cash_flow. Canonical selection receives multiple eligible PRIMARY_STATEMENT candidates and correctly emits no winner under current no-guessing rules. |
| `operating_cash_flow` | 2025 | `selection_ambiguity_after_source_recovery` | Page 243 now supplies the truth row, but the bridge maps both cash generated from operations and net cash generated from operating activities to operating_cash_flow. Canonical selection receives multiple eligible PRIMARY_STATEMENT candidates and correctly emits no winner under current no-guessing rules. |

The final validation therefore demonstrates that adding pages 240 and 243 is sufficient to recover `long_term_debt` 2024-2025, but not sufficient by itself to reach 66/66 under current OCR V2 bridge and selection behavior.

## Conclusion

OCR V2 does not reach `66 / 66` truth-set coverage with the complete extraction set. Remaining failures are listed in `ocr_v2_final_validation_audit.json`.
