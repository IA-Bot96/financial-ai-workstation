# CV1 — Execution Readiness Review

**Status:** Operational readiness gate for CV1 (OCR extraction correctness). No code, no OCR redesign, no architecture change. Execution readiness only.
**Date:** 2026-06-03
**Reviewed:** CV1 protocol, OCR truth-set schema, census inventory, review-workbook spec, validation architecture, validation plan.

---

## 0. Headline

The CV1 **design** is ready: the census inventory, blind-first workbook spec, adjudication worksheet, and machine-comparable schema are coherent, mutually consistent, and faithful to `thresholds_version 1.0.0`. But CV1 is **NOT_READY for execution** because of bounded **operational-setup gaps** — most importantly, **the prep never specifies how the system's output value reaches the workbook for comparison** (Section B population), plus unstaffed analysts, no calibration set, unconfirmed source-PDF↔fingerprint matching, an unenforced blind gate, and an unpinned Millat bundle. None requires redesign; all are setup. The path to READY is short and enumerated below.

---

## 1. Dependency Validation (Task 1)

| Dependency | Status |
|---|---|
| **CV0 governance** (thresholds 1.0.0, CI rule, census/sample, adjudication, sign-off, machine format) | ✅ Satisfied |
| **MB-1 — issuer identity slice** (bundle → correct canonical entity: `lucky_cement`, `millat_tractors`) | ⚠️ **Unconfirmed** — trivially verifiable but not yet recorded. CV1-critical slice of MB-1 (full MB-1 [CONFIRM] facts are *not* CV1-critical). |
| **Lucky bundle pinned** (`97c3123…`) | ✅ |
| **Millat bundle pinned** | ❌ **Not firmly pinned** — MSIL review noted Millat used an OCR *context*, not a `.kb.json` sidecar; fingerprint = generated-workbook-bytes hash, to be confirmed. |
| **Source PDFs available + fingerprint-matched** | ⚠️ PDFs exist in `data/`, but the **exact file matching each bundle's fingerprint** is not confirmed as the analyst's source-of-truth. |
| **Regression harness** (CV5) | ⏳ Not built — **not required for CV1 execution** (CV1 produces the schema-conformant truth set; harness consumes it in CV5). |

---

## 2. Missing Analyst Inputs (Task 2)

- **MI-1 (critical) — Section B system-output extraction.** The workbook reveals "system output" after blind-lock, but **no artifact specifies how the OCR-consolidated `value/scale/unit/label/presence` per `cell_id` is extracted from the bundle into Section B.** Without this, analysts have nothing to compare against. This is the one *design-level* (not merely logistical) gap.
- **MI-2 — Per-cell provenance pages.** The inventory marks `cited_source_page` "from provenance" but does **not pre-populate** the page per cell. Analysts need the cited page per cell (deterministically pulled from the bundle) to open the right PDF location.
- **MI-3 — Source-document mapping.** Analysts need to know **which PDF and which page** is truth for each `value_year` — e.g. Lucky `value_year 2020` is the **2025 report's comparative/5-year-summary column**, not the standalone 2020 report. Validate against the bundle's source report (matching fingerprint), not separate-year reports.
- **MI-4 — Canonical-metric reference.** To disposition `corrected_label`, analysts need the canonical metric definitions (what counts as canonical `revenue`, etc.).
- **MI-5 — Severity auto-suggestion table.** The protocol §6 (metric-class × disposition → severity) must be embedded in the workbook for the auto-suggest column.

---

## 3. Hidden Execution Risks (Task 3)

- **HR-1 — Millat artifact shape differs.** Millat's provenance/system-output live in a *context* file, not a `.kb.json` sidecar; Section-B extraction (MI-1) and provenance pre-fill (MI-2) for Millat may need a different pull path than Lucky. The Millat half is materially less ready than Lucky.
- **HR-2 — Blind-truth ambiguity for multi-stated metrics.** A `value_year` can appear in several places in one report (primary statement, 5-year summary, notes). Analysts must record the **primary-statement value** as blind truth and flag others as `source_ambiguity` — the prep covers this via `statement_to_check` + adjudication, but reviewers must be **trained** that blind-truth = primary-statement value (else two reviewers record different "truths" legitimately).
- **HR-3 — Presence-check semantics for aggregates.** `total_debt`/`long_term_debt`/`total_equity` are aggregates that may have **no discrete source line**. Guidance needed: if the source has no discrete line, `expected_presence = absent` and the system's "missing" is **`confirmed` (correct)** — not an error. Without this, the 18 Lucky presence cells risk being mis-dispositioned.
- **HR-4 — Blind-gate enforcement.** The spec says Section B is "hidden/disabled until `blind_locked`," but this requires **tooling or a controlled process** to actually enforce; a plain spreadsheet lets reviewers peek, defeating anti-anchoring.
- **HR-5 — Analyst throughput is the critical path** (per the plan). Named, available, COI-clear financial analysts + a senior adjudicator are not yet confirmed.

---

## 4. Census Completeness (Task 4)

- **Lucky:** 66 cells (11 metrics × 2020–2025) ✅ complete and pre-flagged (S/P/N).
- **Millat:** 66 cells **contingent on confirming the value-year span** — if Millat's bundle doesn't span 2020–2025, the grid changes; absent years stay as `presence` cells.
- **Adversarial census parts:** core-metric scale-flagged cells are in the census (marked **S**); **non-core scale-flagged and note-vs-statement census lists are not yet enumerated** (must be extracted from the `scale_consistency_audit` + bundle scan).
- **Metric-set completeness:** the 11 baseline-eligible metrics match the scale audit, but **confirm against FVE's actual baseline requirements** — e.g. is capex/PP&E or finance_cost a baseline metric that should be censused? (PP&E appeared in the OCR freeze-prep critical conflicts.)

---

## 5. Workbook Suitability (Task 5)

- Columns map cleanly to the schema; blind/reveal split, disposition/severity/adjudication, version pins all present. ✅
- **Gaps:** Section B population (MI-1); blind-gate enforcement (HR-4); embedded severity-suggestion table (MI-5); presence/aggregate disposition guidance (HR-3); the **workbook→schema export step** (the completed workbook must be persisted as the machine-comparable truth set, not left only in spreadsheet form — required for CV5 harness, MI/process).
- Otherwise suitable.

---

## 6. Adjudication Sufficiency (Task 6)

- The adjudication worksheet is complete: dispute types, resolution rules (stated-units header / primary-statement anchor / label context), S1 second-reviewer + senior adjudicator, corrected-then-re-sample. ✅
- **Gaps:** the **adjudicator is unassigned**; `dispute_type` does **not explicitly cover the presence/aggregate case** (fold into `source_ambiguity` or add `presence_aggregate`); confirm the worksheet handles **analyst-error** resolutions (system correct, blind truth wrong → `confirmed` on adjudication) — the outcome field allows it, but state it.

---

## 7. Regression-Harness Compatibility (Task 7)

- The schema is **harness-compatible by design** — `numeric_scale_aware` + `canonical_id_match` + `unit_match` + `presence_match`, with `scale_exact: true`, typed `expected`/`actual`, and a defined roll-up. ✅
- **The harness itself is a CV5 deliverable and is not required for CV1 execution.** CV1 produces the truth set; the harness re-runs it later. **The only compatibility requirement on CV1 is that the completed workbook is exported to the schema JSON** (MI/process, §5) so it is harness-ready. No incompatibility found.

---

## 8. Findings Classification

**Must Before Execution**
- **MI-1 — Define & build the Section B system-output extraction** (per `cell_id` from the bundle; deterministic; revealed post-blind-lock). *The one design-level blocker.*
- **MI-2 — Pre-populate per-cell `cited_source_page`** from the bundle.
- **MI-3 — Confirm source-PDF↔fingerprint mapping** (the exact files; bundle's source report per value_year).
- **HR-4 — Enforce the blind gate** (tooling or controlled process).
- **HR-5 — Assign named financial analysts + senior adjudicator** (COI-clear, available).
- **Calibration set built + reconciled** (≈5 mixed cells incl. a scale and a note-vs-statement case).
- **MB-1 issuer-identity slice confirmed** for both bundles (trivial but required as the entity anchor).
- **MI-4/MI-5 — Canonical-metric reference + severity-suggestion table** embedded in the workbook.

**Can Resolve During Execution**
- Millat fingerprint pin + value-year span confirmation (**start Lucky first**; bring Millat in once confirmed — HR-1).
- Non-core scale-flagged + note-vs-statement census enumeration (core cells already in census; append as extracted).
- Presence/aggregate disposition guidance (HR-3) + adjudication `presence_aggregate` handling.
- Metric-set completeness vs FVE baseline requirements (core 11 sufficient to start; add cells if confirmed needed).
- Workbook→schema export finalization.

**Post-CV1**
- Regression harness (CV5) — schema already compatible.
- Full MB-1 [CONFIRM] closure (deep ticker/relationship facts — not CV1-critical).
- Non-manufacturer issuer extension.

---

## 9. Final Determination

### NOT_READY

CV1's **design is complete and sound**, but it is **not operationally ready to execute**: there is no specified mechanism to populate the comparison values analysts must score against (MI-1), per-cell provenance pages are not pre-filled (MI-2), source-PDF↔fingerprint matching is unconfirmed (MI-3), the blind gate is not enforced as tooling (HR-4), no analysts or adjudicator are assigned (HR-5), and no calibration set exists. These are **bounded operational-setup gaps, not design or architecture flaws** — none requires redesigning the protocol, schema, or any engine. Clear the Must-Before list (centered on the Section-B extraction mechanism and analyst staffing), start with the firmly-pinned Lucky bundle while confirming Millat, and CV1 becomes **READY_FOR_EXECUTION**. Declaring readiness now would repeat the platform's cardinal error in miniature — claiming a thing is ready before the evidence (here, the operational setup) actually supports it.

---

## 10. One-Paragraph Verdict

The CV1 preparation is genuinely well-built — the 132-cell census is enumerated and risk-pre-flagged, the workbook is strictly blind-first, the adjudication worksheet is anchored to the right resolution rules, and the schema is harness-ready — but a readiness gate must judge whether an analyst could *actually start tomorrow*, and the answer is not yet: the single design-level gap is that nothing specifies how the OCR system's value per cell reaches the workbook for comparison, and around it sit ordinary but real setup blockers (provenance pages unfilled, source PDFs unmatched to fingerprints, the blind gate unenforced, no analysts or adjudicator assigned, no calibration set, Millat unpinned). So CV1 is **NOT_READY** — honestly, and only by a short, bounded, no-redesign distance: build the Section-B extraction, fill the provenance pages, match and pin the bundles, enforce the blind gate, staff and calibrate the reviewers, and confirm the two issuer identities, and the foundational extraction validation can begin Lucky-first exactly as designed — proving the platform's numbers scale-first and census-validated, the moment the setup catches up to the design.
