# OCR V2 — Production Integration Phases

**Status:** Implementation planning only. No code changes.
**Date:** 2026-06-04
**Companion:** `ocr_v2_integration_design.md`.
**Migration model:** Option B (parallel, frozen-V1 rollback). Flag `OCR_ENGINE_VERSION ∈ {v1, v2, shadow}`, default `v1`.

**Gate vocabulary:** *Safe-now* = zero production risk, may proceed before freeze. *Freeze-gated* = blocked until Millat CONDITIONAL + clean downstream revalidation.

---

## Phase Plan

| Phase | Scope | Output | Validation gate | Rollback | Gating |
|---|---|---|---|---|---|
| **P-I0 — Interface conformance** | Implement `OCRV2Pipeline(IOCRPipeline)` whose `process(context)->context` wraps the existing capture→…→workbook path | A V2 class that satisfies the production interface | Interface contract tests pass; output is a populated `CompanyContext` | Discard class; V1 untouched | **Safe-now** |
| **P-I1 — Input adapter** | `CompanyContext`/PDF → V2 candidate stream by **reusing V1 table extraction** (`TableTransformerDetector` + `CamelotTableExtractor`) → `OCRV2CandidateAdapter`; remove manual bbox-CSV staging | Production candidate stream from real PDF | Candidate recall ≥ staged-CSV path on Lucky; tags (basis/statement_type/entity_scope) populated | Revert to staged path (validation-only) | **Safe-now** |
| **P-I2 — Output projection** | V2 canonical values → `FinancialYearConsolidationResult` + workbook shape the context carries | V2-populated context consumable by `WorkbookPopulation` + `QueryEngineBundleGeneration` | Output ≡ V1 contract; bundle generation succeeds on V2-populated context | n/a (projection only) | **Safe-now** |
| **P-I3 — Feature flag + composition root** | `OCR_ENGINE_VERSION` selector binding `get_ocr_pipeline()` / `build_default_pipeline()`; **default `v1`** | Engine selectable at the root; callers unchanged | With default `v1`, production behavior **bit-identical** to today | Flag absent/`v1` = current behavior | **Safe-now** |
| **P-I4 — Shadow execution** | `ShadowOCRPipeline`: run both, **serve V1**, write V2 to shadow artifact, auto-compare per run on real PDFs | Per-run V1-vs-V2 comparison matrices over a real corpus | Across the corpus: `V2-regresses = ∅`, zero fabrication-on-SI, scale clean | Set flag `v1`; stop shadow | **Safe-now** (V2 never consumed) |
| **P-I5 — Downstream revalidation (staging)** | Feed V2-populated contexts to MSIL/FVE/QAE/Query in staging | Per-engine revalidation reports | Contracts intact; FVE baselines improve w/o regression; no answer/citation regression (Query) | Staging only; no prod impact | **Safe-now** (staging) |
| **P-I6 — Staged cutover (Lucky-first)** | Flip `OCR_ENGINE_VERSION=v2` for live traffic, **one issuer first** | V2 canonical in production for the cutover scope | **Freeze gate cleared** (Millat CONDITIONAL) + P-I4/P-I5 green; monitor live | **Flag flip → `v1`** (instant) | **Freeze-gated** |
| **P-I7 — V1 retirement** | After a stability window, retire V1 for the cutover scope | V2 sole engine (scoped) | Stability window clean; rollback retained until window closes | V1 archived, re-activatable until window closes | **Freeze-gated + window** |

---

## Sequencing logic

- **P-I0 → P-I3 are pure scaffolding** behind a default-off flag: production behavior is unchanged because nothing routes to V2. These can all proceed **now**, in parallel with the Millat validation program.
- **P-I4 shadow** is the highest-value safe phase: it runs V2 on **real production PDFs** (not staged CSVs), producing the real-world comparison evidence that both (a) hardens integration and (b) **feeds the freeze decision** — a stronger signal than the staged-table validation.
- **P-I5** confirms the frozen platform (MSIL/FVE/QAE/Query) consumes V2 cleanly in staging — required before any cutover.
- **P-I6 cutover is the only freeze-gated production step**: it must not flip until Millat CONDITIONAL is rendered and P-I4/P-I5 are green. Lucky-first scope, instant flag rollback.
- **P-I7 retirement** waits out a stability window with frozen V1 retained.

## What blocks what

```
Freeze gate (Millat CONDITIONAL + downstream revalidation)
        │  blocks
        ▼
P-I6 cutover ──blocks──> P-I7 retirement

P-I0..P-I5  ── NOT blocked by freeze (shadow/staging only, V2 unconsumed) ── may start now
```

---

## One-Paragraph Verdict

The integration splits cleanly into a long stretch of zero-risk work that can start immediately and a single gated step that cannot: phases P-I0 through P-I5 — implementing `OCRV2Pipeline` against the existing interface, wiring the input adapter that reuses V1's extraction, projecting V2 output into the consolidation/workbook contract, adding a default-`v1` engine flag, running shadow execution on real PDFs, and revalidating downstream in staging — all leave production bit-identical because nothing routes to or consumes V2, so they may proceed in parallel with Millat and in fact generate the real-PDF evidence the freeze decision wants. Only P-I6, the live cutover that flips the flag to consume V2, is freeze-gated, and it stays blocked until Millat returns CONDITIONAL and the shadow and downstream gates are green, after which it cuts over one issuer at a time with an instant flag-flip rollback to a frozen V1, and P-I7 retires V1 only after a clean stability window. Build the scaffolding and shadow now; hold the cutover for the validated engine.
