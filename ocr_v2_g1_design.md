# OCR V2 — Generalization Sprint G1 Design

**Status:** Architecture + implementation planning. No production cutover.
**Date:** 2026-06-04
**Objective:** eliminate issuer-specific page-range dependence (A1 basis / A2 statement_type / A3 entity_scope) by deriving these three tags from **extracted document content** instead of Lucky page numbers.
**Inputs:** Generalization Audit + Inventory · `default_ocr_v2_bridge_config()` · Lucky extraction tables · Millat PDFs/tables.
**Companion:** `ocr_v2_g1_migration_plan.md`.

---

## 0. Feasibility anchors (from the code + documents)

1. **The page-range dependence is isolated to one functional call site** — `ocr_v2_candidate_adapter.py:245–251`:
   ```
   statement_type = config.statement_type_for_cell(page, section_label=cell.section_label)
   basis          = config.basis_for_page(cell.page_number)          # page only — no content
   entity_scope   = config.entity_scope_for_page(cell.page_number)   # page only — no content
   ```
   (Other references are audit-only in `remediation_r1.py:425–430`.) Replacing three lines migrates the whole dependence.
2. **Content-signal machinery already exists** — the table adapter already derives `section_label` (`_section_label_from_row` / `_section_heading_from_row`) and detects percentage analysis (`_section_is_percentage_analysis`). `statement_type` already partly uses `section_label`; only `basis`/`entity_scope` use page alone.
3. **The decisive signals are present in both issuers' documents.** Lucky bbox CSVs carry section/scale in row 0 ("Financial Position (PKR in million)"); Millat page text prints "**Unconsolidated** Statement of Profit or Loss", "**Notes to** the Unconsolidated Financial Statements", and named investees. The titles that determine basis/statement_type/entity_scope are **in the document**, not invented by the page map.

**Enabling prerequisite (G1.0):** thread the **statement title + section header + "Notes to" marker + named entities** from page text into a `document_context` on `ExtractedTableCell`. The data exists in the page text the extractor already reads (pdfplumber); it simply is not currently carried to the cell. `basis` and `entity_scope` have *no* content signal today precisely because this context isn't threaded.

---

## 1. Generic Basis Deriver

**Input:** statement title / section context text (+ table caption).
**Rules (first match wins):**
| Signal in title/context | → Basis |
|---|---|
| contains "consolidated" / "the group" (and not preceded by "un") | **CONSOLIDATED** |
| contains "unconsolidated" / "standalone" / "separate financial statements" | **UNCONSOLIDATED** |
| neither present | **UNKNOWN** |

**Confidence: HIGH.** Both Lucky (p236 "Unconsolidated…", p286 "Consolidated…") and Millat (p110 "Unconsolidated Statement of Profit or Loss") print the basis word in the statement title. UNKNOWN is a safe outcome (selection precedence already handles unknown-basis as non-canonical).

## 2. Generic Statement Type Deriver

**Input:** title/section text + the existing percentage-analysis signal + column/units signals.
**Rules (ordered):**
| Signal | → Statement Type |
|---|---|
| title/section "notes to the … financial statements" | **NOTE** |
| section "vertical/horizontal analysis" / "% " columns / percentage scale (existing `_section_is_percentage_analysis`) | **ANALYSIS_TABLE** |
| title "… years at a glance" / "financial highlights" / "X-year" summary (often units = million) | **SUMMARY_TABLE** |
| title "statement of profit or loss" / "financial position" / "cash flow" / "changes in equity" **and not** "notes to"/"analysis" | **PRIMARY_STATEMENT** |
| title "analysis of statement of …" with multi-year **value** columns (not %) | **SUPPORTING_SCHEDULE** |
| none | **UNKNOWN** (governed as non-canonical) |

**Confidence: HIGH for NOTE / ANALYSIS / SUMMARY / PRIMARY** (reuses signals that already exist). **SUPPORTING_SCHEDULE is the fuzziest** residual (a multi-year value schedule that is neither primary nor a note); it is the one class most likely to need a bounded override.

## 3. Generic Entity Scope Deriver

**Input:** section/note context + named entities in the table/caption + **MSIL entity identity**.
**Rules (ordered):**
| Signal | → Entity Scope |
|---|---|
| containing note is "investment in **associates** / **joint ventures**" **and** the table names an entity that **MSIL resolves to a non-issuer investee** (e.g. NutriCo, ASIL) | **INVESTEE** |
| containing note is a **subsidiary**-detail table naming an entity MSIL resolves to a subsidiary | **SUBSIDIARY** |
| primary statements + issuer-level notes (named entity = issuer or unnamed) | **ISSUER** (default) |
| entity named but unresolved by MSIL | **UNKNOWN** |

**Confidence: MEDIUM — the hardest deriver.** Default-ISSUER + investee-note detection covers the common case, but reliable INVESTEE/SUBSIDIARY tagging needs (a) named-entity detection inside the note context and (b) MSIL resolution. This is where the **bounded per-issuer override (hybrid)** is retained as a fallback — derivation primary, override only for unresolved named entities. **MSIL ownership of entity identity is preserved** (the deriver enforces, does not invent).

## 4. Current uses of the page-range maps (Task 4)

| Map | Functional call site | Audit-only references |
|---|---|---|
| `basis_page_ranges` (via `basis_for_page`) | `candidate_adapter.py:250` | — |
| `statement_type_page_ranges` (via `statement_type_for_cell`/`_for_page`) | `candidate_adapter.py:245` | `remediation_r1.py:425–430` |
| `entity_scope_page_ranges` (via `entity_scope_for_page`) | `candidate_adapter.py:251` | — |

**One functional consumer (the candidate adapter); the migration surface is three lines.**

## 5. Migration design — Current → Generic

```
CURRENT:  ExtractedTableCell ──(page_number)──> bridge_config.{basis,statement_type,entity_scope}_for_page ──> CandidateCaptureInput tags
GENERIC:  ExtractedTableCell + document_context ──> {Basis,StatementType,EntityScope}Deriver(content) ──> CandidateCaptureInput tags
          (bridge_config page ranges retained ONLY as a deprecated override when a deriver returns UNKNOWN and an override exists)
```
- **G1.0** enrich extraction → carry `document_context` (title, section, "Notes to", named entities, units).
- **G1.1** implement the three pure-function derivers (content → tag), no I/O, deterministic.
- **G1.2** rewire `candidate_adapter.py:245–251`: deriver-first; page-range config demoted to optional override (hybrid).
- **G1.3** cross-issuer validation: re-run Lucky (must preserve 66/66 — no regression) **and** Millat (tags must derive correctly) — the real generalization test.
- **G1.4** eliminate A6 (page/year aliases): re-express its intent (demote contaminated summary proxies) through the generic source-precedence (A7), removing the last irredeemably over-fit element.

## 6. Effort estimate

| Item | Effort | Note |
|---|---|---|
| G1.0 extraction context enrichment | **Medium** | thread page title/section/entities into the cell; data exists in page text |
| G1.1 Basis deriver | **Low** | title string match |
| G1.1 Statement-type deriver | **Low–Medium** | reuse existing section/percentage signals |
| G1.1 Entity-scope deriver | **Medium–High** | named-entity detection + MSIL binding (the long pole) |
| G1.2 adapter rewire + hybrid fallback | **Low** | three call sites |
| G1.3 cross-issuer validation | **Medium** | depends on Millat extraction tables + Millat truth set (Millat program) |
| G1.4 remove A6 | **Low** | delete page/year aliases; lean on A7 precedence |

**Total: a MEDIUM sprint.** Long poles: the entity-scope deriver and the dependency on Millat extraction/truth-set existing for G1.3.

---

## 7. Final Determination

# GENERIC_DERIVATION_FEASIBLE

**Justification.** The three tags are derivable from signals the documents already contain and the extractor already reads: basis from the statement title's "unconsolidated/consolidated" word (HIGH confidence, present in both Lucky and Millat), statement_type from the title + "Notes to" + the percentage-analysis detection the adapter already performs (HIGH for primary/note/analysis/summary), and entity_scope from investee-note context bound to MSIL identity (MEDIUM — the one deriver that retains a bounded override). The page-range dependence is concentrated in three lines of one adapter, so the migration surface is small; the enabling work is threading the page/statement title into the cell (data that exists but isn't carried today). Generic derivation is feasible — with the honest qualifications that the entity-scope deriver is the hardest and that a small, validated override layer (hybrid) should remain for unresolved named entities and the fuzzy SUPPORTING_SCHEDULE class, never as the execution model. Per-issuer page-range configuration is **not** required as the primary path.

---

## One-Paragraph Verdict

Sprint G1 is feasible because the information the Lucky page ranges encode is, in every case, printed in the documents themselves and already partly in OCR V2's hands: the statement title carries "unconsolidated" or "consolidated" for basis, the title plus a "Notes to" marker plus the percentage-analysis detector the table adapter already runs carry the statement type, and the investment-in-associates note context plus MSIL identity carry entity scope — so three content-driven derivers can replace `basis_for_page`, `statement_type_for_cell`, and `entity_scope_for_page` at the single adapter call site that consumes them. The only genuinely new plumbing is threading the page/section title and named entities into each extracted cell as document context, which the extractor can read but does not currently carry, and the only deriver that stays hard is entity scope, which leans on MSIL and keeps a bounded, validated override for unresolved names; the irredeemable page-and-year alias guards (A6) are deleted outright and their intent folded into the generic precedence rule. The determination is **GENERIC_DERIVATION_FEASIBLE**: a medium sprint, validated by re-running Lucky to 66/66 without regression and Millat to correct tags, after which OCR V2 stops being a Lucky-shaped engine and becomes a document-derived one with configuration demoted to a bounded exception.
