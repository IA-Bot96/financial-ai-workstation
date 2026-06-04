# OCR V2 — Production Integration Design

**Status:** Architecture & implementation planning only. No code changes.
**Date:** 2026-06-04
**Read:** OCR V2 Integration Wiring Audit · Final Validation Report · Freeze Readiness Review · Migration Review.
**Grounding (verified):** production interface is `ocr_engine.pipeline.interfaces.ocr_pipeline.IOCRPipeline.process(self, context: CompanyContext) -> CompanyContext`. Production entry: `run_pipeline.build_default_pipeline().process(context)`; API: `POST /ocr/process → Depends(get_ocr_pipeline) → IOCRPipeline.process(context)`. Downstream: `OpenPyXLWorkbookPopulationService → QueryEngineBundleGenerationService` (MSIL is a separate adapter, not in the production OCR graph).

---

## 0. Design principle

Integrate OCR V2 **behind the existing interface, invisibly to callers, defaulted off, in shadow first.** No consumer (`run_pipeline`, API route, Query bundle) should change; selection is a composition-root concern; V2 output is never consumed by production until shadow comparison on real PDFs proves it clean and the freeze gate is cleared.

## 1. Required Interfaces

- **`IOCRPipeline.process(context: CompanyContext) -> CompanyContext`** — the single production contract. OCR V2 must satisfy it exactly (same input, same populated-context output). No new public interface is introduced to callers.
- **Internal (reused, not new to callers):** the production **table-extraction front-end** (V1's `TableTransformerDetector` + `CamelotTableExtractor`) as the source of raw tables — so V2 does not rebuild extraction and does not depend on manually-staged bbox CSVs.

## 2. Required Adapters

1. **Input adapter — `CompanyContext`/PDF → V2 candidate stream.** Reuse the production table-extraction output (raw detected/extracted tables) and feed `OCRV2CandidateAdapter` (raw tables → `CandidateCaptureInput` rows), **replacing the manual bbox-CSV staging** the validation path currently uses. This is the production form of the bridge from the Extraction Bridge Review (reuse V1 extraction; tag basis/statement_type/entity_scope deterministically).
2. **Output projection adapter — V2 canonical values → `CompanyContext` output.** Project the single-canonical-value-per-(metric,year) result into the **same `FinancialYearConsolidationResult` + workbook** shape the context already carries, so `OpenPyXLWorkbookPopulationService` and `QueryEngineBundleGenerationService` consume V2 output **unchanged** (V2 preserves the single-canonical-value contract → no downstream change).

## 3. Should OCR V2 implement the existing OCR interface? — YES

Implement a new `OCRV2Pipeline(IOCRPipeline)` whose `process(context) -> context` runs capture → registry → governance → selection → workbook internally and populates the same context fields. Rationale: it is **Liskov-clean and caller-invisible** — the API route's injected `IOCRPipeline` and `build_default_pipeline()` can bind either engine with no change to routes, downstream services, or the bundle generator. This is the safest possible coupling: the seam already exists (`get_ocr_pipeline` is dependency-injection friendly); V2 just becomes a second implementation.

## 4. Feature-Flag Strategy

- A **composition-root selector** — settings field / env var `OCR_ENGINE_VERSION ∈ {v1, v2, shadow}`, **default `v1`**.
- Binds `get_ocr_pipeline()` (API) and `build_default_pipeline()` (CLI) to `ocr_engine.OCRPipeline` (`v1`), `OCRV2Pipeline` (`v2`), or the **shadow wrapper** (`shadow`).
- The flag lives only in the composition root; no caller reads it. Default `v1` means **doing nothing keeps production on the frozen V1**.

## 5. Side-by-Side (Shadow) Execution Strategy

- A **`ShadowOCRPipeline(IOCRPipeline)`** wrapper runs **both** engines on the same `CompanyContext`:
  - **V1 result is returned to production** (canonical; consumers see only V1).
  - **V2 result is written to a shadow artifact** (workbook + comparison record), **never returned to callers**.
  - Each run auto-emits a **V1-vs-V2 comparison** (the existing `numeric_scale_aware` comparison harness) on the real production PDF.
- This is the production analog of the Migration Review's Option-B parallel build: **zero production risk** (V2 output unconsumed), while generating **real-PDF comparison evidence** on live inputs — evidence that also strengthens the freeze case.

## 6. Rollback Strategy

- **Default-off flag + frozen V1.** `OCR_ENGINE_VERSION=v1` is the default and the rollback target; V1 (`ocr_engine`) is untouched throughout.
- **Shadow = inherently reversible** (V2 never consumed).
- **Cutover = a flag flip** (`v2` → `v1`), instant, no data migration (V2 output ≡ V1 contract). Retain frozen V1 through a stability window.
- The append-only V2 registry and deterministic selection mean re-runs are clean; nothing V2 produces can corrupt V1's path.

## 7. Validation Strategy After Integration

- **Shadow comparison on real production PDFs** — per-run V1-vs-V2 matrices; require `V2-regresses = ∅` and no fabrication-on-source-insufficient across a corpus of real runs (not just Lucky's staged tables).
- **Downstream revalidation in staging** — run MSIL/FVE/QAE/Query against V2-populated contexts; confirm contracts hold and FVE baselines improve without regression (per Validation Execution Review).
- **Truth-set gates** — Lucky (66/66, done) **and Millat (the freeze gate)**; cutover requires the freeze gate cleared.
- **Promotion ladder** — `shadow` (all traffic, V1 served) → `v2` for one issuer (Lucky-first) → broaden, with instant rollback at each step.

---

## 8. Final Determination

# READY_FOR_INTEGRATION_IMPLEMENTATION — scoped to scaffolding + shadow; production cutover hard-gated

**The design is complete and the safe portion can begin now.** Building the `OCRV2Pipeline(IOCRPipeline)` adapter, the input/output adapters, the `OCR_ENGINE_VERSION` flag (default `v1`), and the `ShadowOCRPipeline` wrapper is **zero production risk** — the flag defaults to V1, V2 output is never consumed, and V1 stays frozen. This scaffolding is not only safe but *valuable before freeze*, because shadow execution on real production PDFs produces exactly the real-world comparison evidence the freeze decision wants.

**Two hard scoping conditions:**
1. **Implementation proceeds through shadow only** until validated — the flag must not route any consumer to V2 output.
2. **Production cutover** (`OCR_ENGINE_VERSION=v2` for live traffic) is **hard-gated** behind the freeze gate — i.e., **Millat CONDITIONAL** (over-fit retired) **plus** clean downstream revalidation. This refines, not contradicts, the Freeze Readiness Review's "integration must not begin until freeze": the *cutover* must wait; the *zero-risk scaffolding and shadow* can proceed and will accelerate freeze.

So: **READY** to implement the design as scaffolding + shadow; **NOT READY** to cut production over to V2 until freeze is cleared.

---

## One-Paragraph Verdict

The safest integration is the one that changes nothing for callers and consumes nothing from V2 until it has earned it: OCR V2 should implement the existing `IOCRPipeline.process(CompanyContext) -> CompanyContext` as a drop-in `OCRV2Pipeline`, fed by an input adapter that reuses V1's table-extraction front-end (retiring the manual bbox-CSV staging) and finished by an output adapter that projects V2's single-canonical-value result into the same consolidation/workbook shape the Query bundle already reads, so MSIL/FVE/QAE/Query need no change. Selection between engines lives only in the composition root behind an `OCR_ENGINE_VERSION` flag defaulted to `v1`, with a `ShadowOCRPipeline` that runs both on every real PDF, serves V1, and writes V2 to a shadow artifact with an automatic comparison — zero production risk, real-PDF evidence, instant flag-flip rollback to a frozen V1. On that basis the determination is **READY_FOR_INTEGRATION_IMPLEMENTATION**, scoped: the adapters, flag, and shadow harness can be built now and should be, because they generate the very evidence freeze wants; but flipping production to consume V2 stays hard-gated behind the freeze gate — Millat CONDITIONAL plus clean downstream revalidation — so that the engine production trusts is a validated one, not a single-issuer candidate.
