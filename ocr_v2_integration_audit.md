# OCR V2 Integration Wiring Audit

**Status:** audit only. No code changes, implementation, refactoring, OCR logic changes, governance changes, selection changes, workbook changes, or MSIL changes were made.

## Executive Determination

OCR V2 is **not connected** to the production orchestration path.

Current status:

```text
OCR V2 wiring status: validation-only
Production OCR package: ocr_engine
OCR V2 package: ocr
Cutover by configuration only: no
Integration work required: yes
```

OCR V2 exists as a separate validation/cutover substrate under `backend/ocr`. It can run manually through its own Lucky validation path, but production entrypoints do not invoke it.

## 1. Which OCR Package Is Invoked By Production Entrypoints?

### CLI: `backend/run_pipeline.py`

`backend/run_pipeline.py` imports the production OCR stack from `ocr_engine`:

```python
from ocr_engine.pipeline.ocr_pipeline import OCRPipeline
from ocr_engine.services.camelot_table_extractor import CamelotTableExtractor
from ocr_engine.services.openai_insights_extractor import OpenAIInsightsExtractor
from ocr_engine.services.openai_table_classifier import OpenAITableClassifier
from ocr_engine.services.table_metric_normalizer import TableMetricNormalizer
from ocr_engine.services.table_transformer_detector import TableTransformerDetector
from ocr_engine.validation.financial_validation_service import FinancialValidationService
```

`build_default_pipeline()` constructs:

```text
ocr_engine.pipeline.ocr_pipeline.OCRPipeline
```

with concrete `ocr_engine` services.

No `backend/ocr` / OCR V2 service is imported or selected.

### API Route: `backend/api/routes/ocr.py`

The API route depends on:

```python
from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline
```

The route calls:

```text
ocr_pipeline.process(context)
```

The dependency is injectable, but the interface type belongs to `ocr_engine`, and no production composition root was found that binds it to OCR V2.

## 2. OCR V2 Reachability From Production Paths

| Path | OCR V2 reachable? | Finding |
|---|---:|---|
| `backend/run_pipeline.py` | No | Directly imports and constructs `ocr_engine.OCRPipeline`. |
| API OCR route | No | Route depends on `ocr_engine.IOCRPipeline`; no OCR V2 binding found. |
| Batch processing | No dedicated batch entrypoint found | `OCRPipeline` docstring says batch jobs should call `process(context)`, which is the `ocr_engine` pipeline. |
| Orchestrators | No | Production orchestrator is `ocr_engine.pipeline.ocr_pipeline.OCRPipeline`; OCR V2 has its own validation runner but is not attached. |
| Workbook generation | V1 path only | Production workbook population is `OpenPyXLWorkbookPopulationService`; OCR V2 workbook generator is separate and not called. |
| Query bundle generation | V1 path only | Runs after production workbook population via `QueryEngineBundleGenerationService`. |
| MSIL | Not wired from OCR production | MSIL `AnnualReportAdapter` can consume `ocr_engine` `Insight` records, but it is not invoked by `run_pipeline.py` or the API route. |
| QAE | Not wired from OCR production | QAE consumes `ocr_engine` `Insight` models through its own services; not called by OCR production entrypoints. |

## 3. OCR V2 Status Classification

OCR V2 is:

```text
validation-only
```

It is not fully unused because tests and manual validation utilities import and exercise it. But it is not partially production-wired: there is no production entrypoint, dependency injection binding, feature flag, or configuration setting that routes OCR requests into OCR V2.

## 4. Import Path Inventory

The generated inventory is in:

```text
ocr_v2_wiring_inventory.json
```

Summary:

| Import root | Total imports | Production non-test imports | Test imports | Interpretation |
|---|---:|---:|---:|---|
| `ocr_engine` | 229 | 125 | 104 | Production OCR V1 package and shared OCR model provider. |
| `ocr` | 14 | 0 | 14 | OCR V2 package is imported only by tests in the top-level import inventory. |

Important note: `backend/api/routes/__init__.py` contains a relative import:

```python
from .ocr import router
```

This is an API route module import, not an import of the OCR V2 package.

## 5. Production Call Graph

Full machine-readable call graph:

```text
ocr_v2_call_graph.json
```

### CLI Path

```text
backend/run_pipeline.py::main
-> build_default_pipeline()
-> ocr_engine.pipeline.ocr_pipeline.OCRPipeline.process()
-> TableTransformerDetector
-> OpenAITableClassifier
-> CamelotTableExtractor
-> FinancialValidationService
-> TableMetricNormalizer
-> OpenAIInsightsExtractor
-> FinancialYearConsolidator
-> OpenPyXLWorkbookPopulationService
-> QueryEngineBundleGenerationService
```

There is no OCR V2 edge in this path.

There is also no MSIL edge in this path.

### API Path

```text
POST /ocr/process
-> Depends(get_ocr_pipeline)
-> ocr_engine.pipeline.interfaces.ocr_pipeline.IOCRPipeline
-> IOCRPipeline.process(context)
```

The route is dependency-injection friendly, but no OCR V2 implementation is registered.

### OCR V2 Validation Path

OCR V2 has its own manual/test path:

```text
output/bbox_extraction_poc/tables/*.csv
-> OCRV2CandidateAdapter
-> CandidateCapture
-> CandidateRegistry
-> StatementGovernance
-> ScaleGovernance
-> EntityGovernance
-> prepare_candidates_for_canonical_selection
-> CanonicalSelection
-> OCRV2WorkbookGenerator
-> OCRV2MSILExport
```

This path is not called by `run_pipeline.py`, the API route, or a batch entrypoint.

### MSIL Annual Report Adapter Path

MSIL has an annual-report adapter:

```text
ocr_engine.models.insights_extraction.Insight
-> multi_source_intelligence.services.AnnualReportAdapter
-> IntelligenceSignal
```

This is an adapter service, not a production OCR orchestration step. It is not invoked by `run_pipeline.py`.

## 6. Cutover Readiness

OCR V2 cannot replace OCR V1 through configuration only.

Reasons:

1. `run_pipeline.py` imports concrete `ocr_engine` implementations directly.
2. The API route dependency type is `ocr_engine.pipeline.interfaces.ocr_pipeline.IOCRPipeline`.
3. OCR V2 does not expose a production `IOCRPipeline`-compatible orchestrator.
4. OCR V2 consumes bbox CSV artifacts as its current bridge input, not the production `CompanyContext` PDF orchestration path.
5. OCR V2 workbook/MSIL export modules are separate projection/adaptation utilities, not production pipeline layers.
6. No feature flag, environment variable, settings field, factory, or dependency binding was found that switches between OCR V1 and OCR V2.

Therefore:

```text
Cutover requires integration work.
```

## 7. Integration Work Still Required

This audit does not recommend implementation details beyond the wiring conclusion, but the minimum missing production connections are:

- A production OCR V2 orchestrator or adapter compatible with `CompanyContext` / `IOCRPipeline`.
- A composition-root choice that can select OCR V1 or OCR V2.
- A bridge from production PDF extraction artifacts into the OCR V2 candidate stream without relying on manual CSV staging.
- A decision on whether production workbook generation remains V1, uses OCR V2 workbook projection, or maps OCR V2 selected values into the existing workbook population service.
- A production handoff decision for MSIL, since current `run_pipeline.py` stops at Query Engine bundle generation and does not invoke MSIL.

## Final Answer

OCR V2 is **validation-only** in the current codebase. Production OCR still runs through `ocr_engine`.

The production call graph is:

```text
Entry point
-> ocr_engine OCRPipeline
-> ocr_engine services
-> workbook_population
-> query_engine bundle generation
```

OCR V2 is not part of that graph. Integration work is required before OCR V2 can replace OCR V1.
