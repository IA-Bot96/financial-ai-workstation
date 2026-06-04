# OCR Missing Page Generation Audit

**Status:** preparation audit only. No OCR logic, OCR V2 logic, governance, selection, workbook, or MSIL changes were made.

## Sources Inspected

- `experiments/bbox_extraction_poc.py`
- `experiments/bbox_guided_extraction_experiment.py`
- `backend/ocr/ocr_v2_table_adapter.py`
- `backend/ocr/ocr_v2_lucky_run.py`
- `output/bbox_extraction_poc/tables`
- `output/lucky-cement_insights_diagnostics_context.json`
- `data/lucky-cement-2025.pdf`

## Current BBox CSV Inventory

The current OCR V2 bridge input directory is:

```text
output/bbox_extraction_poc/tables
```

`backend/ocr/ocr_v2_table_adapter.py` defines this as the default OCR V2 raw-table input path.

Current available pages:

```text
162, 163, 164, 271, 321, 322, 324, 328, 353, 356
```

Current file count:

```text
27 CSV table files
```

Missing required recovery pages:

```text
page_240: missing
page_243: missing
```

Page 241 is also missing, but the final gap audit determined it is not required for the remaining 66-cell recovery target.

## Why Page 240 Is Missing

Page 240 is missing because `experiments/bbox_extraction_poc.py` was originally scoped to the high-impact classification/extraction mismatch pages:

```python
TOP_MISMATCH_PAGES = [164, 163, 162, 271, 321, 356, 324, 353, 322, 328]
```

When the POC was generated using the default page set, page 240 was not requested, so no `page_0240_*` CSV files were written.

This is not a detection failure. The latest Lucky diagnostics context contains page 240:

- Classification: `balance_sheet`
- Detected table count: `1`
- Detected table id: `2025:240:0`
- Detection confidence: `0.9994327425956726`

The production extraction context also contains a page 240 balance-sheet table with the needed rows, including:

- `Long-term financing`
- total liabilities subtotal
- total equity and liabilities

## Why Page 243 Is Missing

Page 243 is missing for the same reason: it is not part of the POC default page list.

This is not a detection failure. The latest Lucky diagnostics context contains page 243:

- Classification: `cash_flow_statement`
- Detected table count: `1`
- Detected table id: `2025:243:0`
- Detection confidence: `0.9996144771575928`

The production extraction context also contains a page 243 cash-flow table with the needed row:

- `Net cash generated from operating activities`

## Were Pages 240 And 243 Intentionally Excluded?

They were intentionally outside the original POC scope, but not intentionally excluded as invalid OCR sources.

The POC was created for the earlier multi-logical-table mismatch pages. Pages 240 and 243 became relevant later during the final coverage-gap audit, after R1-B had reduced the remaining gaps to six cells.

So the exclusion is best classified as:

```text
POC source-scope omission
```

not:

```text
detection failure
classification failure
OCR V2 bridge failure
governance failure
selection failure
```

## Can They Be Regenerated From The Original PDF?

Yes.

Required inputs exist:

```text
data/lucky-cement-2025.pdf
output/lucky-cement_insights_diagnostics_context.json
```

The POC script accepts arbitrary page numbers via `--pages`, and pages 240 and 243 both have classification records in the context JSON. Therefore the existing POC generation path can be used without OCR V2 code changes.

## Exact Command To Generate The Missing Page CSVs

Run this from the repository root:

```powershell
python -B experiments\bbox_extraction_poc.py `
  --pdf data\lucky-cement-2025.pdf `
  --context-json output\lucky-cement_insights_diagnostics_context.json `
  --source-report-year 2025 `
  --pages 240 243 `
  --output-dir output\bbox_extraction_poc `
  --confidence-threshold 0.90 `
  --dpi 144 `
  --bbox-padding-points 6.0
```

This writes table CSVs into:

```text
output/bbox_extraction_poc/tables
```

which is the directory consumed by the current OCR V2 bridge.

Important note: this command will also rewrite:

```text
output/bbox_extraction_poc/bbox_extraction_poc.json
output/bbox_extraction_poc/bbox_extraction_poc_summary.csv
```

for the requested pages. OCR V2 consumes the `tables/*.csv` files, not those summary files. If preserving the previous POC summary is important, generate into a staging directory first:

```powershell
python -B experiments\bbox_extraction_poc.py `
  --pdf data\lucky-cement-2025.pdf `
  --context-json output\lucky-cement_insights_diagnostics_context.json `
  --source-report-year 2025 `
  --pages 240 243 `
  --output-dir output\bbox_extraction_poc_missing_pages `
  --confidence-threshold 0.90 `
  --dpi 144 `
  --bbox-padding-points 6.0

Copy-Item output\bbox_extraction_poc_missing_pages\tables\page_0240*.csv output\bbox_extraction_poc\tables\
Copy-Item output\bbox_extraction_poc_missing_pages\tables\page_0243*.csv output\bbox_extraction_poc\tables\
```

## Expected CSV Outputs

The latest diagnostics context has one detected table on each required page, so the expected detection index is `bbox_00`.

The POC tries three extraction strategies per detected bbox:

- `bbox_pdfplumber_text`
- `bbox_camelot_stream`
- `bbox_camelot_lattice`

CSV files are written only for strategies that return at least one table. Therefore the expected output filenames are:

```text
output/bbox_extraction_poc/tables/page_0240_bbox_00_bbox_pdfplumber_text_table_00.csv
output/bbox_extraction_poc/tables/page_0240_bbox_00_bbox_camelot_stream_table_00.csv
output/bbox_extraction_poc/tables/page_0240_bbox_00_bbox_camelot_lattice_table_00.csv   (if lattice succeeds)

output/bbox_extraction_poc/tables/page_0243_bbox_00_bbox_pdfplumber_text_table_00.csv
output/bbox_extraction_poc/tables/page_0243_bbox_00_bbox_camelot_stream_table_00.csv
output/bbox_extraction_poc/tables/page_0243_bbox_00_bbox_camelot_lattice_table_00.csv   (if lattice succeeds)
```

Based on the existing POC inventory, the most consistently produced strategy files are `bbox_pdfplumber_text` and `bbox_camelot_stream`. `bbox_camelot_lattice` may or may not produce a CSV for a given page.

## Expected Recovery Content

Page 240 should produce a balance-sheet table containing the remaining balance-sheet recovery rows:

| Metric | Year | Expected value | Source row |
|---|---:|---:|---|
| `long_term_debt` | 2024 | `12,760,637` | `Long-term financing` |
| `long_term_debt` | 2025 | `9,184,522` | `Long-term financing` |
| `total_liabilities` | 2024 | `86,256,813` | explicit liabilities subtotal |
| `total_liabilities` | 2025 | `90,837,630` | explicit liabilities subtotal |

Page 243 should produce a cash-flow table containing the remaining cash-flow recovery rows:

| Metric | Year | Expected value | Source row |
|---|---:|---:|---|
| `operating_cash_flow` | 2024 | `27,580,741` | `Net cash generated from operating activities` |
| `operating_cash_flow` | 2025 | `27,572,567` | `Net cash generated from operating activities` |

## Post-Generation Validation Command

After the CSVs are generated into `output/bbox_extraction_poc/tables`, rerun the unchanged OCR V2 Lucky path with the existing R1/R2 validation tooling. The expected result from the final gap audit is:

```text
page_240 added only       -> 64 / 66 coverage
page_240 + page_243 added -> 66 / 66 coverage
```

If the generated CSVs exist but coverage does not improve as predicted, the next issue would be CSV content quality, not page inventory.

## Final Determination

Pages 240 and 243 are missing because the bbox POC was generated with the old high-impact mismatch page list. They were not missing because of OCR V2 logic, governance, selection, workbook generation, MSIL export, or unavailable source PDFs.

They can be regenerated from the original Lucky 2025 PDF using the existing `experiments/bbox_extraction_poc.py` command with explicit `--pages 240 243`.

No OCR V2 code changes are required for the preparation step.
