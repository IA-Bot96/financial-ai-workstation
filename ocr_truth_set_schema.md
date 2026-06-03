# OCR Truth-Set Schema (CV1)

**Status:** Machine-comparable truth-set schema for OCR extraction correctness. No code, no redesign. Compatible with `platform_correctness_regression_harness`.
**Date:** 2026-06-03
**Pins:** `thresholds_version 1.0.0`; per-record `truth_set_version`, `bundle_fingerprint`, `engine_version`.
**Comparator family:** `numeric_scale_aware` (primary), `canonical_id_match`, `unit_match`, `presence_match` (CV0 comparator vocabulary).

---

## 0. Design Rules

- **Deterministic comparison only** — the harness applies fixed comparators; **no LLM** (deterministic-first).
- **Blind-recorded `expected`** — populated by the analyst from source *before* `actual` is attached.
- **Scale is first-class** — `numeric_scale_aware` compares **value AND scale**; `scale_exact: true` (no scale slack — scale corruption is the dominant failure).
- **Append-versioned** — corrections bump version; never silently edited.
- **Reusable as regression** — valid only against the same `engine_version` + `bundle_fingerprint` (or via migration).

---

## 1. Truth-Set Envelope

| Field | Semantics |
|---|---|
| `truth_set_id` | e.g. `ocr_extraction_lucky` / `ocr_extraction_millat` |
| `truth_set_version` | semver |
| `engine` | `ocr` |
| `correctness_type` | `extraction` |
| `bundle_fingerprint` | the validated bundle (e.g. `97c3123…`) |
| `engine_version` | OCR engine version validated |
| `thresholds_version` | `1.0.0` |
| `created_date` · `primary_analyst` · `adjudicator` | provenance of the truth |
| `items[]` | the truth items (§2) |

---

## 2. Truth Item Schema

| Field | R/O | Semantics |
|---|---|---|
| `item_id` | R | Stable, deterministic id. |
| `entity_ref` | R | **MB-1-confirmed** issuer/company. |
| `canonical_metric` | R | e.g. `revenue`, `earnings_per_share`. |
| `value_year` | R | Financial year the value represents. |
| `stratum` | R | `census` / `scale_flagged` / `note_vs_statement` / `review_gated` / `conflict_group` / `missing_year`. |
| `severity` | R | `S1`/`S2`/`S3`/`S4` (per protocol §6). |
| `direction` | R | `assertion` / `withholding` / `na`. |
| `source_provenance` | R | `{pdf_page, statement (income/balance/cashflow/note/summary/analysis), statement_scope, line_label}` + `workbook_fingerprint`. |
| `expected` | R (blind) | `{value, scale, unit, canonical_label, presence}` — analyst-recorded from source. |
| `actual` | R (at compare) | `{value, scale, unit, canonical_label, presence}` — system output. |
| `comparator` | R | `{value+scale: numeric_scale_aware, label: canonical_id_match, unit: unit_match, presence: presence_match}`. |
| `tolerance` | R | `{numeric: exact|rounding_epsilon, scale_exact: true}`. |
| `disposition` | R | protocol §5 vocabulary. |
| `pass` | R (D) | derived (§4). |
| `reviewer` · `confidence` | R | primary reviewer + confidence. |
| `adjudication_ref` | O | link to adjudication log entry (scale/unit/multi-table disputes). |

**`expected` / `actual` value-class objects:**
- `value` — numeric (or `null` if `presence=absent`).
- `scale` — `full` / `thousands` / `millions` / `billions`.
- `unit` — `PKR` / `per_share` / `percent` / `ratio` / `count`.
- `canonical_label` — the canonical metric the line maps to.
- `presence` — `present` / `absent`.

### Example item (data, not code)
```
{ "item_id": "ocr:lucky:revenue:2025:census",
  "entity_ref": "lucky_cement", "canonical_metric": "revenue", "value_year": 2025,
  "stratum": "note_vs_statement", "severity": "S1", "direction": "assertion",
  "source_provenance": { "pdf_page": 365, "statement": "income", "statement_scope": "unknown",
                          "line_label": "Revenue", "workbook_fingerprint": "97c3123…" },
  "expected": { "value": 528651878, "scale": "thousands", "unit": "PKR",
                "canonical_label": "revenue", "presence": "present" },
  "actual":   { "value": 25417143, "scale": "full", "unit": "PKR",
                "canonical_label": "revenue", "presence": "present" },
  "comparator": { "value_scale": "numeric_scale_aware", "label": "canonical_id_match",
                  "unit": "unit_match", "presence": "presence_match" },
  "tolerance": { "numeric": "exact", "scale_exact": true },
  "disposition": "corrected_source", "pass": false,
  "reviewer": "analyst_A", "confidence": "high",
  "adjudication_ref": "ADJ-OCR-014" }
```
*(Illustrative of the documented revenue note-over-statement failure: system took the page-320 note value over the page-365 income-statement Revenue.)*

---

## 3. Comparator Semantics

| Comparator | Applies to | Pass condition |
|---|---|---|
| `numeric_scale_aware` | `value` + `scale` | normalized magnitudes equal **AND** `scale` identical (`scale_exact: true`); a right number at the wrong scale = **fail** |
| `canonical_id_match` | `canonical_label` | maps to the same canonical metric id |
| `unit_match` | `unit` | identical unit class |
| `presence_match` | `presence` | present/absent agree (a value present in source but `absent` in system = `missing_extracted`; absent in source but `present` in system = `spurious_extracted`) |

A truth item **passes only if all four comparators pass.** Any comparator fail → the corresponding `corrected_*` / `missing_*` / `spurious_*` disposition at the item's severity.

---

## 4. Derived Pass/Fail & Exclusions

- `pass = true` iff `disposition == confirmed` (all comparators pass).
- `pass = false` for any `corrected_* / missing_extracted / spurious_extracted` (failure counted at `severity`).
- `source_insufficient` / `indeterminate` → **excluded from pass/fail rates**; counted in the separate source-insufficiency / indeterminate tallies (CV0).
- `source_ambiguous` → not scored until adjudicated; resolves to `confirmed` or a corrected disposition.

---

## 5. Harness Roll-Up (consumed by `platform_correctness_regression_harness`)

The harness, per truth set:
1. For each item, apply the comparators+tolerance → per-item pass/fail (deterministic).
2. Roll up to **error rate per (stratum × severity)** with **95% Wilson CI**.
3. Emit the **false-assertion vs false-withholding split** and, for over-sampled strata, the **population-weighted estimate**.
4. Compare rates to `thresholds_version 1.0.0` bands → per-severity Target/Warning/Failure.
5. Emit the `ocr_extraction_correctness_audit` payload + overall disposition.
**Re-runnable** against the pinned `engine_version` + `bundle_fingerprint`; this is the durable regression eval.

---

## 6. One-Line Posture

The OCR truth set is a deterministic, scale-first, MB-1-anchored, version-pinned record where every baseline value carries the source-verified `value/scale/unit/label/presence` an analyst recorded blind — compared by `numeric_scale_aware` so a right number at the wrong scale always fails — making the platform's foundational extraction correctness measurable, re-runnable, and honestly bounded without changing a line of OCR.
