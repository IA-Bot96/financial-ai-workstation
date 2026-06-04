# OCR V2 — Generalization Sprint G1 Migration Plan

**Status:** Implementation planning. No production cutover.
**Date:** 2026-06-04
**Companion:** `ocr_v2_g1_design.md`.
**Goal:** migrate basis / statement_type / entity_scope from Lucky page ranges (A1/A2/A3) to content derivation, with **zero regression on Lucky (66/66)** and correct derivation on Millat.

**Invariants for this sprint:**
- Governance, selection, workbook, and MSIL-export logic **do not change** (G1 touches only the bridge/derivation layer feeding `CandidateCaptureInput` tags).
- Lucky must remain **66/66** at every gate (no-regression is the hard constraint).
- Page-range config is **retained as a deprecated override**, not deleted (hybrid), so rollback is a config flip.

---

## Phases

| Phase | Scope | Output | Validation gate | Rollback |
|---|---|---|---|---|
| **G1.0 — Context enrichment** | Thread statement title, section header, "Notes to" marker, named entities, and units from page text into a `document_context` field on `ExtractedTableCell` | Cells carry document context | Lucky cells gain context with **no change to existing `section_label`/scale**; re-run Lucky → still 66/66 (context additive, unused yet) | Drop the new field (no behavior change) |
| **G1.1 — Build derivers** | Implement `BasisDeriver`, `StatementTypeDeriver`, `EntityScopeDeriver` as pure, deterministic functions of `document_context` (+ MSIL identity for entity) | Three deriver units + unit tests | Deriver unit tests pass on hand-cased title/section inputs; deterministic | Discard derivers; nothing wired yet |
| **G1.2 — Rewire adapter (deriver-first, hybrid)** | At `candidate_adapter.py:245–251`, call the derivers; demote page-range config to an **override only when a deriver returns UNKNOWN** | Adapter emits content-derived tags | **Lucky parity:** re-run Lucky end-to-end → tags match the page-range result on every cell; **66/66 preserved, zero regression** | Flip a flag back to page-range-primary |
| **G1.3 — Cross-issuer validation** | Run derivers on **Millat** extraction tables (from the Millat program) + compare against the Millat truth set | Lucky-no-regression report + Millat derivation report | Lucky still 66/66; Millat basis/statement_type/entity_scope derive correctly; remaining gaps are real (extraction/recall), not page-range | Keep page-range-primary for Lucky; Millat stays validation-only |
| **G1.4 — Remove A6 (page/year aliases)** | Delete `label_page_year_aliases`; rely on the generic source-precedence (A7) to demote contaminated summary proxies | A6 removed | Lucky 66/66 unchanged after A6 removal (precedence covers the OCF/LTD summary-proxy demotion) | Restore A6 if precedence under-covers |

---

## Sequencing & dependencies

```
G1.0 (enrich) ─> G1.1 (derivers) ─> G1.2 (rewire, Lucky parity) ─> G1.3 (cross-issuer) ─> G1.4 (remove A6)
                                                  │
                          depends on ─────────────┴──> Millat extraction tables + Millat truth set (Millat Validation Program)
```
- **G1.0–G1.2 can proceed on Lucky alone** (the no-regression gate is self-contained).
- **G1.3 is gated on the Millat program** delivering extraction tables + truth set (the artifacts flagged `MISSING_MUST_CREATE`). G1.3 is where "generic derivation" is actually *proven* multi-issuer; G1.0–G1.2 only prove it *preserves Lucky*.
- **G1.4 is last** — remove the over-fit element only once precedence is confirmed to cover its intent on Lucky.

## No-regression discipline (the central guardrail)

The migration is correct only if, at **G1.2**, the content-derived tag **equals** the page-range tag for **every Lucky cell** — a per-cell parity diff (page-range tag vs derived tag) with **zero mismatches** required before the override is demoted. This converts "did we generalize without breaking Lucky?" into a mechanical check, not a hope. Any cell where derivation ≠ page-range is either a deriver bug or a page-range over-fit and must be adjudicated before proceeding.

## What this sprint does NOT do

- It does not touch governance/selection/workbook/MSIL logic.
- It does not cut over production (V1 remains the production engine; V2 remains validation/shadow).
- It does not eliminate the override layer — it **demotes** it (hybrid), preserving rollback and a home for the fuzzy SUPPORTING_SCHEDULE class and unresolved named entities.

## Effort

**Medium sprint.** Long poles: the **entity-scope deriver** (MSIL binding) and the **G1.3 dependency** on Millat extraction/truth-set existing. G1.0–G1.2 (Lucky-only, the bulk of the mechanical change) are independently completable now.

---

## One-Paragraph Verdict

The migration is staged so that the risky claim — that document-derived tags can replace Lucky's page ranges — is proven mechanically before it is trusted: G1.0 threads the statement title and section context (which the extractor already reads) onto each cell without changing behavior, G1.1 builds three deterministic derivers, and G1.2 rewires the single adapter call site to derive-first while keeping the page-range config as a demoted override, gated by a per-cell parity diff that must show the derived tag equals the page-range tag on every Lucky cell with zero mismatches and 66/66 preserved. Only then does G1.3 run the derivers on Millat — the step that actually demonstrates multi-issuer generalization and which depends on the Millat program delivering extraction tables and a truth set — and G1.4 finally deletes the irredeemable page-and-year alias guards once the generic precedence rule is confirmed to cover their intent on Lucky. Nothing in governance, selection, the workbook, or MSIL changes, production stays on V1, and the override layer is demoted rather than removed so rollback is a flag flip; it is a medium sprint whose long poles are the MSIL-bound entity-scope deriver and the dependency on Millat's extraction artifacts, and whose first three phases can begin immediately on Lucky under a strict no-regression gate.
