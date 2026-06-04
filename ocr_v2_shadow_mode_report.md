# OCR V2 Shadow Mode Report

## Status

Shadow mode is operational as integration scaffolding. `OCR_ENGINE_VERSION=shadow` builds a `ShadowOCRPipeline` that runs V1 and V2 from the same `CompanyContext`, returns only the V1 result, and persists V2 output plus a comparison artifact.

## Serving Contract

- Served engine: V1
- Shadow engine: V2
- Caller receives V2 output: false
- API contract changed: false
- Production cutover performed: false

## Artifacts

Per shadow run, the wrapper writes:

- `<run_id>_v2_context.json`
- `<run_id>_comparison.json`
- `ocr_v2_shadow_mode_report.md`
- `ocr_v2_shadow_metrics.json`
- `ocr_v2_shadow_history.json`
- `ocr_v2_shadow_dashboard.json`
- `ocr_v2_shadow_comparison_report.md`
- `ocr_v2_shadow_trend_report.md`

Default directory: `output/ocr_v2_shadow`.

## P-I4 Observability

Shadow metrics now capture per-run document identity, V1/V2 runtime, metric
counts, source-insufficient counts, workbook-row counts, errors, comparison
status, and V2 phase timings for extraction, capture, governance, selection,
workbook generation, and export.

## P-I5 Aggregation

Shadow history now stores one durable record per engine per document run. The
dashboard aggregates average runtime, runtime ratio, comparison statuses,
completeness deltas, and errors. The trend report summarizes performance,
completeness, recurring differences, and candidate bottlenecks from the
accumulated history.

## Verification

- New integration scaffolding tests: 5 passed
- Existing V1 orchestrator tests: 6 passed
- OCR V2 focused integration tests: 48 passed
- OCR V2 test suite: 91 passed

## Rollback

Set `OCR_ENGINE_VERSION=v1`. The default is already `v1`, so unset configuration keeps existing production behavior.
