# OCR V2 — Generalization Architecture Audit

**Status:** Audit only. No code changes.
**Date:** 2026-06-04
**Objective:** determine whether issuer-specific bridge configs are an *intended* architectural component, or whether OCR V2 is expected to run on unseen issuers without issuer-specific configuration.
**Inputs:** Lucky OCR V2 implementation · `default_ocr_v2_bridge_config()` · Lucky validation artifacts · Millat validation-block report · integration design.
**Companion:** `ocr_v2_generalization_inventory.json`.

---

## 1–2. Inventory of Lucky-specific assumptions, classified

| # | Component | Lucky value | Classification | Note |
|---|---|---|---|---|
| A1 | **basis page ranges** | 162–164 & 236–283→uncons; 286–375→cons | **ISSUER_SPECIFIC** / DERIVABLE | Basis is printed in statement headers ("Unconsolidated"/"Consolidated") → derivable without page ranges |
| A2 | **statement_type page ranges** | 162 SUMMARY; 163–164 SUPPORTING; 236–243 & 286–294 PRIMARY; 244–283 & 295–375 NOTE | **ISSUER_SPECIFIC** / DERIVABLE | Derivable from statement titles + "Notes to" markers + analysis-section headers |
| A3 | **entity_scope page ranges** | 162–320 ISSUER; 321–324 INVESTEE; 325–375 ISSUER | **ISSUER_SPECIFIC** / DERIVABLE | Lucky investee pages (NutriCo/ASIL); derivable but harder — needs entity-name/MSIL detection on investment-note tables |
| A4 | **label aliases** | turnover→revenue, net cash from operating activities→operating_cash_flow, share capital & reserves→total_equity, long-term financing→long_term_debt, … | **GENERIC** | Standard accounting vocabulary + OCR-garble variants; **reusable across issuers** |
| A5 | **section_statement_type_overrides** | "vertical/horizontal analysis", "cumulative", "year on year" → ANALYSIS_TABLE | **GENERIC** / DERIVABLE | Section-header markers are issuer-independent; already a generic document-derived rule |
| A6 | **label_page_year_aliases** | page 162 + "Long term finance" (2020–25)→summary_reference; page 162 + "Net Cash…" (2024–25)→summary_reference | **ISSUER_SPECIFIC** / REQUIRES_EXTERNAL_CONFIGURATION | **Most over-fit:** hardcoded to Lucky page 162 + specific years — "source-reference guards from the CV1 Lucky truth set." Not derivable; pure tuning |
| A7 | **statement_type precedence** | ANALYSIS→INELIGIBLE; SUMMARY→REVIEW; NOTE→NOTE_ONLY; PRIMARY/SUPPORTING→ELIGIBLE | **GENERIC** | Issuer-independent governance core; reusable as-is |
| A8 | **total_liabilities subtotal heuristic** (R2) | label the unlabeled subtotal immediately before TOTAL EQUITY AND LIABILITIES | **DERIVABLE_FROM_DOCUMENT** | Structural/positional; **fragile** — Millat's standalone BS has no such subtotal (correctly → SOURCE_INSUFFICIENT). Must be cross-issuer validated |
| A9 | **duplicate-artifact pages + marker** | (162,163,164) + "bbox_pdfplumber_text_table" | **GENERIC** (mechanism) / ISSUER_SPECIFIC (page list) | Dedup concept is generic; the page list is Lucky-specific — should key on (value, year, provenance), not pages |
| A10 | **document_fingerprint default** | Lucky `97c3123…` | **ISSUER_SPECIFIC** | Per-document; expected to vary — confirms single-document binding |

**The split is the key result:** the *governance/selection core and the vocabulary layer* (A4, A5, A7, A8) are **generic or document-derivable**; what is hard-bound to Lucky is the **spatial layer** — page ranges (A1–A3), page/year aliases (A6), the dedup page list (A9), and the fingerprint (A10). The dominant blocker for an unseen issuer is **A1–A3 + A6**: with only Lucky page ranges, every page of a new issuer maps to `UNKNOWN` → governance cannot classify → selection collapses (exactly the Millat block).

## 3. Current support level

| Capability | Supported? | Evidence |
|---|---|---|
| **Unseen-issuer execution** | **No** | An issuer without a config gets `UNKNOWN` basis/statement_type/entity_scope on every page → collapse |
| **Multi-issuer execution** | **No** | `default_ocr_v2_bridge_config()` is a single Lucky config; no config-selection mechanism |
| **Issuer-configured execution only** | **Yes** | This is the current reality — V2 runs only with a per-issuer bridge config, and only Lucky's exists (Millat blocked) |

## 4–5. Architectural options

| Option | Effort | Operational burden | Validation implications | Production suitability |
|---|---|---|---|---|
| **A — Per-issuer bridge configs** | Low per issuer, **recurring** | **High** — manual config per issuer; pagination drifts every filing-year → reconfigure | Each issuer needs its own config **and** truth set; the config is itself unvalidated, over-fit-prone input | **Low** — does not scale to arbitrary issuers/annual filings |
| **B — Generic document-derived bridge** | **High** — derive basis/statement_type from headers + section markers; entity_scope from entity resolution; dedup generically | **Low** — no per-issuer config | Validate the **derivation once** across multiple issuers; generalization is the property tested; nothing per-issuer to over-fit | **High** — runs on unseen issuers; the platform goal |
| **C — Hybrid** | **Medium** — generic derivation as default + retain a **bounded** per-issuer override for hard cases | Low–medium — overrides only when derivation fails | Validate generic derivation cross-issuer; overrides are **logged, individually-validated exceptions**; bounded over-fit | **High** — scales **and** handles edge cases; pragmatic |

**Feasibility signal:** Option B/C is feasible, not speculative — A4 and A5 already demonstrate generic derivation working (vocabulary + section markers), and A1–A3 (the dominant issuer-specific component) are **derivable from document structure** that every audited financial report contains (statement titles, "Notes to" headers, basis labels). A6 is the one item that cannot be generalized and must be **eliminated** (it is pure Lucky tuning), with its intent — demoting contaminated summary proxies — re-expressed as a generic source-precedence rule (which A7 already is).

## 6. Final Determination

- **Current state: `ISSUER_SPECIFIC_CONFIGURATION_REQUIRED`.** OCR V2 today cannot run on an issuer without a hand-authored bridge config; only Lucky's exists. This was a legitimate **validation scaffold**, not a production architecture.
- **Production requirement: `GENERIC_EXECUTION_PATH_REQUIRED`** — delivered pragmatically as **Option C (Hybrid)**: a generic document-derived bridge (basis/statement_type from headers + markers, entity_scope from entity resolution, provenance-keyed dedup, structural subtotal handling) with a **bounded, validated** per-issuer override layer for genuine edge cases.

**Are issuer-specific configs an intended component?** No — not as the *execution model* for a multi-issuer financial-intelligence platform. They are acceptable only as **bounded overrides** on top of a generic path, never as the prerequisite for running at all. The current per-issuer requirement is the single architectural gap between "validated on Lucky" and "a platform," and it is the same gap that blocked Millat.

---

## 7. One-Paragraph Verdict

The audit shows OCR V2 is two architectures wearing one name: a **generic, reusable core** — the statement-type precedence, the standard-accounting alias map, the analysis-section markers, and the structural subtotal logic, all issuer-independent or derivable from any audited report — wrapped in a **Lucky-specific spatial shell** of hand-authored page ranges, page-and-year alias guards, a dedup page list, and a document fingerprint that together cause any unseen issuer to collapse into `UNKNOWN` classifications, exactly as Millat did. So OCR V2 today is unambiguously **ISSUER_SPECIFIC_CONFIGURATION_REQUIRED**: it supports neither unseen-issuer nor multi-issuer execution, only issuer-configured execution, and only Lucky is configured. That is fine for a validation scaffold but disqualifying for a platform, and the production requirement is therefore a **GENERIC_EXECUTION_PATH** — best built as a hybrid that derives basis, statement type, and entity scope from document structure (which every report carries and which the alias and section-marker layers already prove works) while keeping a small, logged, individually-validated override layer for true edge cases, and while eliminating the one irredeemably over-fit element, the page-and-year alias guards, by re-expressing their intent as the generic source-precedence rule the core already implements. The determination is **GENERIC_EXECUTION_PATH_REQUIRED**; per-issuer configuration is a bounded override, never the execution model.
