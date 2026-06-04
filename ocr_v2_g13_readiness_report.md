# OCR V2 — G1.3 Readiness Audit

**Status:** Audit only. No code modified, no Millat config created, no Millat OCR executed.
**Date:** 2026-06-04
**Objective:** can OCR V2 now execute on Millat via the document-derived classification path **without** a Millat-specific bridge config?
**Companion:** `ocr_v2_g13_readiness_audit.json`.

---

## 0. Headline

**No — BLOCKED.** And the audit overturns the optimistic reading of the G1 parity result. The parity report says `G1_PARITY_PASSED` (Lucky 66/66, 0 tag mismatches), but the **derived-vs-fallback split shows the page-range dependence was not actually eliminated** — it was demoted in *name* while still doing the *work*:

| Tag | Derived from content | **Lucky page-range fallback** |
|---|---:|---:|
| basis | 82 / 2113 (3.9%) | **2031 (96.1%)** |
| entity_scope | **0 / 2113 (0%)** | **2113 (100%)** |
| statement_type | 757 / 2113 (35.8%) | 1356 (64.2%) |

Lucky parity passed because the **Lucky page ranges silently classified the cells the derivers could not** — `statement_title` is present on only **204/2113** cells (the title lives in page text above the table, not in the extracted grid). On Millat, where the Lucky fallback cannot apply, basis and entity_scope would be `UNKNOWN` for ~96–100% of cells → governance collapse. The deriver-first path is **deriver-in-name, fallback-in-fact** for basis and entity_scope.

---

## 1. Remaining Lucky-specific dependencies (classified)

| Dependency | Status | Detail |
|---|---|---|
| **basis derivation** | PARTIALLY_ELIMINATED | deriver 3.9%; page-range fallback 96.1% → effectively still active / blocking on Millat |
| **statement-type derivation** | PARTIALLY_ELIMINATED | deriver 35.8%; fallback 64.2% → majority still page-range |
| **entity-scope derivation** | **NOT_ELIMINATED** | deriver **0%**; **100% page-range fallback** → entirely page-dependent; BLOCKING |
| **page-range config (A1/A2/A3)** | **STILL_ACTIVE — de-facto primary** | intended fallback-only, but bears 96% of basis + 100% of entity_scope. On Millat → UNKNOWN → collapse. **BLOCKING** |
| page/year aliases (A6) | STILL_ACTIVE, inert for Millat | Lucky page-162+year+label keys won't match Millat. Non-blocking |
| document fingerprint (A10) | STILL_ACTIVE, non-blocking | Lucky default stamped; **not validated** anywhere (confirmed). Cosmetic mis-stamp; parameterize per-document (implementation-only) |
| duplicate-page assumptions (A9) | STILL_ACTIVE, correctness risk | `(162,163,164)`; Millat (298pp) also has those pages → could mis-fire. Non-blocking; should key on provenance, not page numbers |

## 2. Can Millat execute (deriver-first + fallback) without Millat config?

**No.** Two independent blockers:
1. **No Millat extraction input exists** — nothing to run on.
2. **Even if it existed**, the derivers classify only a small minority; basis (96%) and entity_scope (100%) would fall back to Lucky page ranges that do not match Millat → `UNKNOWN` tags → governance cannot classify → selection collapses.

Neither is solved by a Millat-specific config (which is forbidden and, per the generalization goal, the wrong fix). Both are extraction/enrichment gaps.

## 3. Blockers

| ID | File / component | Reason | Type |
|---|---|---|---|
| **B1** | `ocr_v2_table_adapter.py` (`DEFAULT_BBOX_TABLES_DIR`) · `output/bbox_extraction_poc/tables` | **No Millat bbox extraction tables exist** (0 found). No Millat input to run on. | **IMPLEMENTATION** — camelot/pdfplumber available; producing Millat tables is mechanical, not a Millat config. (Forbidden to execute here.) |
| **B2** | `ocr_v2_table_adapter.py` (`_statement_title_from_rows`, `document_context` population) + extraction stage | **G1.0 context enrichment is incomplete.** `document_context` is under-populated (statement_title 204/2113; investee context absent → entity deriver fires 0), so BasisDeriver/EntityScopeDeriver return `UNKNOWN` and the **Lucky page-range fallback** silently does the classification. On Millat the fallback cannot rescue this → basis/entity_scope `UNKNOWN` → collapse. **This is the true generalization blocker.** | **ARCHITECTURAL + IMPLEMENTATION** — the derivers are sound, but their input signal (page-level statement title + investee-note context) is not captured into the cell. Fix = complete the enrichment to capture page-text context; **not** a Millat-specific rule. |

## 4. Determination

# BLOCKED_FOR_G1_3_MILLAT_EXECUTION

**Justification.** G1 successfully wired a deriver-first path and preserved Lucky at 66/66 with zero tag mismatches — genuine, but **the parity is fallback-driven**: the content derivers classify only 3.9% of basis and 0% of entity_scope, with the Lucky page-range fallback carrying the remaining 96% and 100%. Because the document context the derivers depend on is rarely captured into the extracted cell (statement_title on 204/2113), the page-range crutch is still bearing the load — invisible on Lucky (where the ranges are correct), fatal on Millat (where they are not). Millat cannot execute via the document-derived path today: there is no Millat extraction input (B1), and even with it the derivers would under-fire and fall back to Lucky page ranges that do not match Millat, collapsing basis and entity_scope classification (B2). Both blockers are extraction/enrichment work, **not** Millat-specific configuration — so the generalization architecture is the right one, but **G1 is not yet complete**: the context enrichment must actually deliver the title/investee signals the derivers need before "deriver-first" is true rather than nominal.

---

## 5. One-Paragraph Verdict

The G1 parity result is a trap for the unwary: `G1_PARITY_PASSED`, Lucky 66/66, zero tag mismatches — yet the audit's decisive number is not the mismatch count but the derived-versus-fallback split, which shows the content derivers actually classified only 82 of 2113 basis tags and **zero** of 2113 entity-scope tags, with Lucky's own page ranges silently supplying the other 96% and 100% under the banner of a "deprecated fallback." The reason is that the statement titles and investee-note context the derivers read are present on only about a tenth of cells, because the enrichment captures the table grid but not the page-level text where those titles live, so on Lucky the page-range fallback invisibly rescues every gap while on Millat — different pages, no matching ranges — the same gaps would surface as `UNKNOWN` basis and entity scope across nearly all cells and collapse governance. Millat therefore remains **BLOCKED_FOR_G1_3_MILLAT_EXECUTION**, held back not by any missing Millat configuration but by two extraction-and-enrichment gaps: no Millat tables have been produced (implementation), and the context enrichment that is supposed to feed the derivers is incomplete (architectural-and-implementation), so the page-range dependence G1 set out to eliminate is still, in practice, doing the work — and the honest path forward is to finish G1's enrichment until the derivers stand on their own, then produce Millat's extraction tables, before G1.3 can run.
