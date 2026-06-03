# CV1 — Operationalization Spec (closes MI-1 … MI-5 + export + blind-gate)

**Status:** Execution operationalization. No code, no OCR redesign, no correctness redesign, no architecture change, no results. Closes the specification gaps from `cv1_execution_readiness_review.md`.
**Date:** 2026-06-03
**Pins:** `thresholds_version 1.0.0`; bundle fingerprints (Lucky `97c3123…`, Millat to pin).
**Determinism rule (applies throughout):** every derived field is a **verbatim read or a documented-convention mapping** from the **frozen** bundle keyed by `(bundle_fingerprint, cell_id)` — no heuristic re-inference, no analyst judgment, reproducible.

---

## 1. Section-B Population Mechanism (MI-1)

For each `cell_id = ocr:<issuer>:<metric>:<year>`, derive from the bundle's `financial_year_consolidation_result` (the **selected** consolidated `MetricValue` for `(metric, value_year)`):

| Field | Deterministic derivation |
|---|---|
| `actual_presence` | `present` if a selected consolidated value exists for `(metric, value_year)`, else `absent`. |
| `actual_value` | the selected `MetricValue.value` verbatim; `null` if `absent`. |
| `actual_scale` | the **documented consolidation scale convention** (below); read per-value scale metadata if the bundle carries it, else the global convention. |
| `actual_unit` | from the **canonical-metric reference** (§4) — `per_share` for EPS, `percent`/`ratio` for ratio metrics, else `PKR` (unit is metric-determined, not value-inferred). |
| `actual_canonical_label` | the selected candidate's `original_metric` (source label) **+** the system-assigned `canonical_metric` (so `corrected_label` is detectable). |
| `actual_source_page` · `actual_table_type` · `actual_source_class` | the selected candidate's `page_number`, `table_type`, `source_class` (feeds `corrected_source` detection — note-vs-statement). |
| `competing_candidates` (reference only) | the group's competing candidates, attached for **adjudication context only** (never shown in the blind phase). |

**Scale convention (the one sub-item to confirm).** The bundle stores a bare numeric value; `actual_scale` is therefore the **documented stored-value convention of the OCR consolidation** — to be **read from the OCR engine spec** (e.g. "consolidated currency values stored in full rupees post scale-normalization; per-share/ratio stored native"). If per-`MetricValue` scale metadata exists, use it; otherwise apply the global convention. The `numeric_scale_aware` comparator then compares **absolute magnitudes** (system value under its convention vs analyst's source value under the source's stated units) — so scale corruption (e.g. stored 25,417,143 vs source 528,651,878 thousand) **fails** regardless of how scale is tagged. **Must-before sub-item: confirm and document this convention** (documentation only — no OCR change).

Determinism guarantee: Section-B is a pure function of `(bundle_fingerprint, cell_id)`; re-running yields identical values.

---

## 2. Provenance-Page Extraction (MI-2)

For each `cell_id`:
- `cited_source_page` = the **selected** `MetricValue.page_number`.
- `statement_to_check` = derived from the selected candidate's `table_type`/`source_class` (income/balance/cashflow/note/summary/analysis), cross-checked against the canonical-metric reference's expected statement (§4).
- **Presence-absent cells** (no selected value, e.g. Lucky `total_debt`): `cited_source_page = null`; the analyst is directed to the **primary-statement pages for that metric** (from §4) to perform the presence check.
- Pre-population is a deterministic read of the bundle; populated into Section A before review.

---

## 3. Source-Document Mapping Rules (MI-3)

- **One source document per bundle.** Truth is the **annual report the bundle was generated from**, identified by `bundle_fingerprint` (Lucky → the 2025 report matching `97c3123…`). **All cited pages are in that document**; analysts do **not** hunt standalone prior-year reports.
- **Comparative years.** Prior `value_year`s (2020–2024 in a 2025 report) are validated against the **primary-statement comparative columns** if present; else the **financial-summary** value. Record which source column was used.
- **Five-year / multi-year summaries.** A **secondary** source and a known scale/restatement-difference origin (summaries often in millions where statements are in thousands). If a summary conflicts with the primary statement on a comparative year, **the primary statement wins**; the difference is recorded as `source_ambiguity` (frequently the corruption signal).
- **Primary-statement precedence (truth anchor):** primary statement > supporting schedule > note > summary > analysis.
- **Note-vs-statement.** If the system selected a `note_disclosure` value but the primary statement carries the line, the analyst records the **primary-statement value as `expected`** → disposition `corrected_source` (the documented Lucky revenue-from-page-320 failure).
- **Restatements.** A restated prior-year value shown in the current report's comparative **is the truth** (the bundle's source is the current report); flag "restated."
- **Single-source only.** CV1 validates each bundle against its own source report; cross-report reconciliation is out of scope.

---

## 4. Canonical-Metric Reference Appendix (MI-4)

| Metric | Statement | Unit | Scale | Common source labels | Presence rule |
|---|---|---|---|---|---|
| `revenue` | income | PKR | thousands | Turnover, Turnover – Net, Net Revenue, Sales | discrete top line |
| `gross_profit` | income | PKR | thousands | Gross Profit | discrete |
| `operating_profit` | income | PKR | thousands | Operating Profit, Profit from Operations, Operating Income | discrete |
| `profit_after_tax` | income | PKR | thousands | Profit after taxation, Profit for the year, Net profit | discrete (bottom) |
| `earnings_per_share` | income | **per_share** | full | EPS, Earnings per share (Basic/Diluted) | discrete; **never thousands** |
| `total_assets` | balance | PKR | thousands | Total Assets | discrete total |
| `total_equity` | balance | PKR | thousands | Total Equity, Shareholders' Equity, Share capital and reserves | **aggregate** — `present` only if a discrete equity total/subtotal is stated; else `absent` ⇒ system-missing is **correct** |
| `cash_and_cash_equivalents` | balance (x-check cash-flow end) | PKR | thousands | Cash and cash equivalents, Cash and bank balances | discrete; reconcile to cash-flow ending cash |
| `total_debt` | balance | PKR | thousands | Total debt, Total borrowings | **aggregate** — usually **no discrete line** ⇒ `absent` and system-missing is **correct**; do **not** sum components as "truth" |
| `long_term_debt` | balance (non-current) | PKR | thousands | Long-term financing, Long-term borrowings | `present` if a discrete non-current borrowings line exists |
| `operating_cash_flow` | **cash_flow** | PKR | thousands | Net cash from operating activities, Cash flow from operations | discrete; **must be the cash-flow statement**, not a balance-sheet-classified figure (the documented mixed-lineage failure) |

**Presence-check semantics (closes HR-3):** for aggregates (`total_debt`, `total_equity`, `long_term_debt`), **absent-as-discrete-line ⇒ `expected_presence = absent` ⇒ a system "missing" is `confirmed` (correct), not an error.** Never fabricate an aggregate by summing components.

---

## 5. Severity Auto-Suggestion Lookup (MI-5)

`disposition × metric_class → severity` (per `thresholds_version 1.0.0` §6). Census metrics are `baseline_eligible`; adversarial non-core values are `material_non_core` or `non_load_bearing`.

| Disposition | baseline_eligible | material_non_core | non_load_bearing |
|---|---|---|---|
| `corrected_scale` | **S1** | S2 | S3 |
| `corrected_value` | **S1** | S2 | S3 |
| `corrected_unit` | **S1** | S2 | S3 |
| `corrected_source` | **S1** | S2 | S3 |
| `corrected_label` | **S1** (corrupts baseline series) | S2 | S3 |
| `spurious_extracted` | **S1** | S2 | S3 |
| `missing_extracted` | **S3** (→ S2 if a whole baseline series is systematically missing) | S3 | S3 |
| `confirmed` | pass | pass | pass |
| `source_ambiguous` | pending adjudication | pending | pending |
| `source_insufficient` | excluded | excluded | excluded |
| label-casing / formatting only | **S4** | S4 | S4 |

Auto-suggested; **analyst-overridable with a recorded note**. Direction: all `corrected_*`/`spurious` = `assertion`; `missing_extracted` = `withholding`.

---

## 6. Workbook-to-Schema Export Rules (MI / export)

A completed review row exports to one `ocr_truth_set_schema` item:
- **Eligibility:** export a row as **final** only when `blind_locked = true`, `disposition` set, and (for S1) adjudication complete. Incomplete rows are not exported.
- **Mapping (1:1, deterministic):** `expected{value,scale,unit,canonical_label,presence}` ← Section A; `actual{…}` ← Section B; `disposition`, `direction`, `severity`, `reviewer`, `adjudication_ref` ← workbook; `comparator`/`tolerance` ← fixed schema defaults (`numeric_scale_aware`, `scale_exact:true`, etc.); `pass` ← derived (`confirmed`⇒true; `corrected_*`/`spurious`/`missing`⇒false); version pins ← Section C.
- **Exclusions:** `source_insufficient` / `indeterminate` exported with `excluded = true` (harness omits from rates; counts in the separate tallies).
- **Envelope:** one truth-set per issuer (`truth_set_id`, `truth_set_version`, pins, `items[]`); **append-versioned**, never silently edited.
- **Export integrity check (pre-handoff):** every census `cell_id` present (census completeness), every non-excluded item has `expected` + `actual` + `disposition`, version pins populated. The export is the artifact CV5's harness consumes.

---

## 7. Blind-Gate Operational Enforcement (process only — no tooling)

Enforce blind-first by **artifact separation + a release gatekeeper**, not software:
- **Two-phase, separated artifacts.** Analysts receive a **Blind Pack** (Section A blanks + `cited_source_page` + `statement_to_check`) **without any system values**. Section-B values are held by a **release gatekeeper** (program lead / second person), not the analyst.
- **Lock-then-reveal.** The analyst completes and **submits/locks Section A** (timestamped, initialed); the gatekeeper releases the **Section-B value sheet** for that cell/batch **only after** the lock.
- **Batch option** for throughput: lock Section A for a batch, then reveal Section B for the batch.
- **Integrity controls:** Section A is immutable after lock; any post-reveal edit to Section A **flags the cell as blindness-broken → mandatory re-review by a different reviewer**; the lock timestamp precedes the reveal timestamp in the audit trail.
- This reproduces the schema's "Section B hidden until `blind_locked`" as a **procedural control** the program runs without building tooling.

---

## 8. Classification

**Must Before Execution (closed by this spec, except one confirm):**
- ✅ MI-1 Section-B mechanism — **defined**; *open sub-item:* **confirm/document the OCR stored-value scale convention** (documentation only).
- ✅ MI-2 provenance-page extraction — defined.
- ✅ MI-3 source-document mapping rules — defined.
- ✅ MI-4 canonical-metric reference (incl. presence/aggregate semantics) — defined.
- ✅ MI-5 severity lookup — defined.
- ✅ Export rules — defined.
- ✅ Blind-gate process — defined.

**Residual Must-Before (logistics, carried from the readiness review — NOT spec gaps, NOT closed here):**
- Assign named financial analysts + senior adjudicator (COI-clear); build + reconcile the calibration set.
- Confirm source-PDF ↔ fingerprint match (Lucky 2025 report); confirm issuer-identity slice of MB-1.
- Pin the Millat bundle + confirm its value-year span (**start Lucky-first**).

**Can Resolve During Execution:**
- Non-core scale-flagged / note-vs-statement census enumeration (core cells already in census).
- Edge-case label/line variants discovered in calibration → append to §4 appendix.
- Mechanized export (rules defined; manual export acceptable until CV5 harness).
- Metric-set completeness vs FVE baseline requirements (core 11 sufficient to start).

---

## 9. Final Determination

### READY_AFTER_OPERATIONALIZATION

This spec **closes every specification-level gap** (MI-1…MI-5, export, blind-gate): Section-B is a deterministic read of the frozen bundle's selected consolidated values, provenance pages are pulled from the same source, source-document mapping anchors truth to the primary statement of the bundle's own report with explicit summary/note/restatement precedence, the canonical-metric appendix resolves the aggregate-presence ambiguity, the severity lookup makes scoring deterministic-and-overridable, the export rules make the workbook harness-ready, and the blind gate is enforced procedurally by artifact separation. **No additional design gaps were found** — the only open sub-item is documentation (confirming the OCR stored-value scale convention), and the only remaining blockers are **logistics** (staff analysts, calibrate, match/pin PDFs, confirm issuer identity, pin Millat), which are inherent to standing up any analyst run and require **no redesign of the protocol, schema, or any engine**. Clear the residual logistics, start Lucky-first, and CV1 executes exactly as designed.

---

## 10. One-Paragraph Verdict

The five MI gaps were real but specification-shaped, and they close cleanly without touching OCR or the correctness design: every Section-B comparison value is now a verbatim, convention-documented read of the frozen bundle's selected consolidated `MetricValue` (so scale corruption fails the `numeric_scale_aware` comparator no matter how scale is tagged), provenance pages come from the same selected candidate, truth is anchored to the bundle's own annual report with primary-statement precedence over summaries and notes and explicit handling of comparatives and restatements, the canonical-metric appendix finally resolves the aggregate-presence trap (a missing `total_debt` line is *correctly* missing), severity is a deterministic disposition × metric-class lookup that analysts may override with a note, the workbook exports 1:1 into the harness-ready schema with exclusions and integrity checks, and blindness is enforced by holding the system values behind a release gatekeeper rather than any tooling. CV1 is therefore **READY_AFTER_OPERATIONALIZATION** — the design is complete and gap-free, one documentation confirm aside, and what remains is purely the logistics of staffing, calibrating, and pinning that every honest analyst pass requires before its first cell is scored.
