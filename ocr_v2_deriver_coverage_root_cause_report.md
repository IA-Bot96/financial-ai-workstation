# OCR V2 — Deriver Coverage Root-Cause Audit

**Status:** Audit only. No code modified. Causes attributed by re-ingesting the Lucky tables through the shipped adapter + derivers (read-only) and inspecting each cell's `document_context`.
**Date:** 2026-06-04
**Objective:** determine why the content derivers classified only a minority of Lucky candidates (basis 4.3%, statement_type 39.7%, entity_scope 0%).
**Companion:** `ocr_v2_deriver_coverage_root_cause_audit.json`.

---

## 0. Headline

**One cause dominates: `missing_statement_title`.** The signals the derivers need — the basis word ("Unconsolidated"/"Consolidated"), the NOTE marker, and the issuer/investee context — all live in the **page-level statement title**, but the adapter captures the title only from the **table grid** (`_statement_title_from_rows`), so it is present on just **156/1905 cells (8.2%)** and `notes_to_marker` is **never set (0/1905)**. The derivers therefore return UNKNOWN and the Lucky page-range fallback silently classifies the rest.

## 1–2. Failure causes — counts & percentages (1905 cells)

**Context presence:** statement_title **156 (8.2%)** · section_heading **1893 (99.4%)** · named_entities 523 (27.5%) · notes_to_marker **0 (0%)**.

| Tag | Derived | Fallback | Fallback causes |
|---|---:|---:|---|
| **basis** | 82 (4.3%) | 1823 | `missing_statement_title` **1667** · `unsupported_pattern` 156 |
| **statement_type** | 757 (39.7%) | 1148 | `missing_statement_title` **980** · `unsupported_pattern` 156 · `missing_section_header` 12 |
| **entity_scope** | **0 (0%)** | 1905 | `missing_statement_title` **1226** · `unsupported_pattern` 523 · `missing_entity_context` 156 |

**Reading:**
- **`missing_statement_title` is the controlling cause** (1667 / 980 / 1226). `section_heading` is almost always present but carries table-row text ("property plant and equipment"), not basis/entity signals.
- **entity_scope = 0% derived:** even the ISSUER *default* never fires, because its trigger words ("statement of", "issuer", "company's") live in the absent title; the 523 `unsupported_pattern` are cells with named_entities that match no investee/subsidiary marker.
- **`notes_to_marker` never set** → NOTE detection can only come from title text, which is absent.

## 3. Minimum enrichment changes

| ID | Change | Fixes | Leverage |
|---|---|---|---|
| **E1** | Capture the **page-level statement title** into `document_context.statement_title` (from page text above the table, not only the grid) | `missing_statement_title` for **all three tags** (1667 / 980 / 1226) | **HIGHEST — one change, dominant cause** |
| **E2** | Set `notes_to_marker` from the page title "Notes to the … Financial Statements" | statement_type NOTE detection (marker currently 0/1905) | HIGH (note cells) |
| **E3** | Capture the **investee/associate note-section title** ("Investment in associates and joint ventures") for cells under that note | entity_scope INVESTEE (currently 0) | HIGH (investee cells; rest default ISSUER once title present) |
| E4 | (supporting) broaden the ISSUER default so titled primary/issuer cells resolve ISSUER rather than UNKNOWN | entity_scope ISSUER reach | MEDIUM |

**E1 is the keystone:** the dominant cause for every tag is the same missing field, and that field's data exists in page text the extractor already reads — it simply is not threaded into the cell.

## 4. Post-fix estimated derived coverage

Assuming E1–E3 populate the title / notes marker / note-section title for cells under a titled statement or note (every statement and note page carries a title):

| Tag | Post-fix estimate | Note |
|---|---|---|
| **basis** | ~60–80% | primary/note/consolidated pages carry "unconsolidated"/"consolidated" in the title; six-year-summary/analysis pages may lack an explicit basis word → residual fallback. **Millat primary statements explicitly print "Unconsolidated" → Millat basis coverage likely *higher* than Lucky's summary-heavy pages.** |
| **statement_type** | ~85–95% | titles + notes_to_marker + existing analysis/summary markers cover primary/note/summary/analysis |
| **entity_scope** | ~85–100% | most cells ISSUER once title present; investee note pages → INVESTEE via E3 |

**Residual:** cells whose title carries no basis word (summary/analysis) still fall back to page ranges — fine on Lucky, **UNKNOWN on Millat**. The residual must be validated as small and non-load-bearing for governance.

## 5. Does G1.3 Millat execution become feasible after enrichment alone?

**No — not by enrichment alone.**
1. **B1 unchanged:** no Millat extraction tables exist; enrichment produces no Millat input.
2. **Residual fallback:** basis-UNKNOWN cells (titles lacking a basis word) still fall back to Lucky page ranges, which do not apply to Millat → those cells UNKNOWN. The residual must be validated non-load-bearing first.

**G1.3 feasibility therefore requires, in order:** (1) implement **E1–E3** (close `missing_statement_title`); (2) **re-validate Lucky** that derived coverage is high and the page-range fallback is no longer load-bearing (a per-tag derived-coverage gate, not just zero-mismatch); (3) **produce Millat extraction tables**. Enrichment is the necessary *first* step and the highest-leverage one, but it is not sufficient alone.

---

## 6. One-Paragraph Verdict

The derivers under-fired for a single, fixable reason: the basis word, the NOTE marker, and the issuer/investee signals all live in the statement title, but the adapter reads the title only from the table grid, so it is present on just 156 of 1905 cells and the notes marker on none — leaving `missing_statement_title` as the controlling fallback cause for basis (1667), statement_type (980), and entity_scope (1226), and leaving entity_scope at literally zero because even its ISSUER default trigger sits in that absent title. The fix is correspondingly concentrated: capture the page-level statement title (E1), set the notes-to marker from it (E2), and carry the investee note-section title (E3) — three changes against data the extractor already reads, with E1 alone addressing the dominant cause for all three tags and lifting estimated derived coverage to roughly 60–80% (basis), 85–95% (statement_type), and 85–100% (entity_scope), with Millat's explicitly-titled "Unconsolidated" statements likely faring better on basis than Lucky's summary pages. But enrichment alone does not unblock G1.3: no Millat extraction tables exist, and the residual basis-unknown cells would still fall back to Lucky page ranges that mean nothing for Millat — so the path is to implement E1–E3, re-validate Lucky against a derived-coverage gate (not merely zero tag-mismatch) to prove the page-range crutch is no longer load-bearing, and only then produce Millat's tables and run G1.3.
