# OCR Review Workbook Specification (CV1)

**Status:** CV1 preparation artifact — the analyst review workbook, reviewer assignment, and adjudication worksheet. No code, no measurement, no results. Directly usable to begin CV1.
**Date:** 2026-06-03
**Pins:** `thresholds_version 1.0.0`; bundle fingerprints (Lucky `97c3123…`, Millat to confirm).
**Maps to:** `ocr_truth_set_schema.md` (each completed row produces one truth item).

---

## 1. Review Workbook — Columns (Task 2)

The workbook enforces **blind-first**: Section A is completed and **locked** from the source PDF *before* Section B (system output) is revealed.

### Section A — Blind Truth (filled from the source PDF; locked before reveal)
| Column | Type / allowed values | Req | Notes |
|---|---|---|---|
| `cell_id` | text (`ocr:<issuer>:<metric>:<year>`) | R | Pre-populated from the inventory. |
| `entity_ref` | text (MB-1-confirmed) | R | Pre-populated. |
| `canonical_metric` | enum (11 metrics) | R | Pre-populated. |
| `value_year` | int | R | Pre-populated. |
| `stratum` | enum: census / scale_flagged / note_vs_statement / review_gated / conflict_group / missing_year | R | Pre-populated (census) or set when appended. |
| `cited_source_page` | int | R | From provenance; the page to open. |
| `statement_to_check` | enum: income / balance / cashflow / note / summary / analysis | R | Per metric reference. |
| `expected_value` | number or `null` | R | Blind, from source; `null` if absent. |
| `expected_scale` | enum: full / thousands / millions / billions | R | From the statement's units header. |
| `expected_unit` | enum: PKR / per_share / percent / ratio / count | R | EPS = per_share. |
| `expected_canonical_label` | text | R | The canonical metric the source line maps to. |
| `expected_presence` | enum: present / absent | R | Is the line in the source for this year? |
| `source_location_recorded` | text (page, statement, exact line label) | R | The verified location. |
| `reviewer_confidence` | enum: high / medium / low | R | Reviewer's certainty. |
| `source_ambiguity_note` | text | O | Restated / multiple-statement / unclear-units. |
| `blind_locked` | bool | R (D) | Set true to open Section B. |

### Section B — Comparison (revealed only after `blind_locked = true`)
| Column | Type / allowed values | Req | Notes |
|---|---|---|---|
| `actual_value` | number or `null` | R | System output. |
| `actual_scale` | enum (as above) | R | System output. |
| `actual_unit` | enum (as above) | R | System output. |
| `actual_canonical_label` | text | R | System output. |
| `actual_presence` | enum: present / absent | R | System output. |
| `disposition` | enum (protocol §5): confirmed / corrected_value / corrected_scale / corrected_unit / corrected_label / corrected_source / spurious_extracted / missing_extracted / source_ambiguous / source_insufficient | R | The verdict. |
| `direction` | enum: assertion / withholding / na | R (D) | Auto from disposition; analyst confirms. |
| `severity` | enum: S1 / S2 / S3 / S4 | R | Auto-suggested from (metric-class × disposition); analyst confirms. |
| `needs_adjudication` | bool | R | True for scale/unit/multi-table disputes + all S1. |
| `adjudication_ref` | text | O | Link to the adjudication worksheet entry. |
| `pass` | bool | R (D) | `confirmed` ⇒ true; any `corrected_*`/`spurious`/`missing` ⇒ false; `source_insufficient`/`indeterminate` ⇒ excluded. |
| `reviewer` · `review_date` | text / date | R | Primary reviewer signature. |

### Section C — Version Pins (per row, pre-populated)
`truth_set_version` · `bundle_fingerprint` · `engine_version` · `thresholds_version (1.0.0)`.

**Workbook rules:** Section B columns are **hidden/disabled until `blind_locked = true`** (anti-anchoring); `severity` auto-suggestion uses the protocol §6 mapping (e.g. `corrected_scale` on a baseline metric → S1) but is analyst-overridable with a note; any S1 row auto-sets `needs_adjudication = true`.

---

## 2. Reviewer Assignment Guidance (Task 3)

- **Primary reviewers = qualified financial analysts** (read financial statements, scale/unit literate). **Never the OCR implementer** (or their team) for any cell.
- **Split the grid to avoid single-reviewer bias:** assign by issuer or metric-block; a given cell has one primary reviewer.
- **S1 cells → mandatory second independent reviewer** (CV0): every scale-flagged (**S**), note-vs-statement (**N**), and any cell that disposition-resolves to a baseline-metric `corrected_*`. The second reviewer must **not** be the primary for that cell.
- **Adjudicator = senior financial analyst**, independent of both reviewers; handles all disputes + all S1 (§3).
- **Calibration first:** all reviewers complete a small shared calibration set (≈5 mixed cells incl. a scale and a note-vs-statement case) and reconcile scale/disposition judgment *before* the main pass.
- **Conflict-of-interest:** no reviewer reviews cells their team produced; record reviewer↔cell assignment for audit.
- **Workload:** ~66 census cells/issuer + appended adversarial rows; balance to keep blind-recording unrushed (PDF line-reading is the slow step).

---

## 3. Adjudication Worksheet Specification (Task 4)

One entry per dispute, referenced by `adjudication_ref`.

| Column | Type / allowed values | Notes |
|---|---|---|
| `adjudication_id` | text (`ADJ-OCR-NNN`) | Referenced from the workbook. |
| `cell_ids` | list | One or more cells (multi-table conflicts span cells). |
| `dispute_type` | enum: scale / unit / multi_table / s1_dispute / source_ambiguity | The class. |
| `reviewer_a_position` | text | Primary reviewer's recorded truth. |
| `reviewer_b_position` | text | Second reviewer's recorded truth. |
| `source_evidence_examined` | text | Units header, comparative-column consistency, primary-statement line, footnotes. |
| `resolution_rule_applied` | enum: stated_units_header / primary_statement_anchor / label_context / unresolvable | The governing rule (§ below). |
| `resolution` | object `{value, scale, unit, canonical_label, source}` | The adjudicated truth. |
| `resolution_rationale` | text | Why. |
| `outcome_disposition` | enum (protocol §5) | Final disposition. |
| `final_severity` | enum: S1 / S2 / S3 / S4 | Final. |
| `corrected_and_root_caused` | bool | S1 only — was it fixed (data) + root-caused? |
| `re_sample_required` · `re_sample_ref` | bool / text | S1 correction triggers stratum re-sample (CV0). |
| `adjudicator` · `adjudication_date` | text / date | Senior analyst signature. |

**Adjudication rules (protocol §7):**
- **Scale dispute →** `stated_units_header` (the statement's "Rupees in thousands/millions"); never infer scale from magnitude.
- **Unit dispute →** `label_context` (EPS=per-share; ratio lines=%); not magnitude.
- **Multi-table conflict →** `primary_statement_anchor` (precedence: primary statement > supporting schedule > note > summary > analysis); non-primary selection ⇒ `corrected_source`.
- **Irreconcilable →** `source_ambiguous` → if still undeterminable, `source_insufficient` (excluded from rate; counted separately).
- **All S1 disputes:** senior adjudicator required; uncorrected adjudicated S1 = **Failure**; corrected+root-caused S1 → re-sample the stratum.

---

## 4. Execution Readiness Checklist

- ☐ Workbook instantiated with Lucky 66 + Millat 66 census rows pre-populated (Sections A/C).
- ☐ Section B reveal **gated** on `blind_locked`.
- ☐ `severity` auto-suggestion wired to protocol §6; S1 rows auto-flag `needs_adjudication`.
- ☐ Reviewers assigned (financial analysts, COI-clear), grid split, S1 second-reviewer routing set.
- ☐ Calibration set completed and reconciled.
- ☐ Adjudication worksheet stood up; adjudicator assigned.
- ☐ Version pins populated; bundles pinned by fingerprint.

When every box is checked, **CV1 analyst review may begin.** (This document produces no measurement; results are recorded into the workbook → truth set → `ocr_extraction_correctness_audit` during execution.)

---

## 5. One-Line Posture

The review workbook is a strictly blind-first instrument — analysts record the source-verified value, scale, unit, label, and presence and lock them *before* the system output is ever shown — paired with COI-clear financial-analyst assignment, mandatory second review and senior adjudication for every S1 (scale, source, baseline-value) dispute, and an adjudication worksheet anchored to the statement's units header and primary-statement precedence: everything an analyst needs to start CV1 immediately, and nothing that pre-judges a result.
