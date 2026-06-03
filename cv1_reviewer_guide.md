# CV1 Reviewer Guide

**Status:** Analyst-facing how-to for CV1 OCR extraction-correctness review. No OCR changes, no protocol redesign. Execution material only — contains **no results or measurements**.
**Use with:** `ocr_truth_set_inventory.md` (your cells), `ocr_review_workbook_spec.md` (your columns), `cv1_operationalization_spec.md` (derivations & rules).

---

## 0. The Golden Rules

1. **The source PDF is the truth.** Never the workbook, never the system value.
2. **Blind first.** Record your source-verified answer and **lock it** before the system value is revealed to you.
3. **Primary statement wins.** When a metric appears in several places, the primary statement is the anchor.
4. **Scale comes from the units header, never from magnitude.**
5. **When unsure, don't guess** — mark `source_ambiguous` (→ adjudication) or `source_insufficient` (excluded).

---

## 1. Reviewer Workflow (step by step)

1. **Receive your Blind Pack** — a list of cells (`cell_id`, `canonical_metric`, `value_year`, `cited_source_page`, `statement_to_check`) **with no system values**.
2. **Open the bundle's source report** (the exact PDF matching the bundle fingerprint) at `cited_source_page`.
3. **Locate the line item** using the canonical-metric reference (statement + common labels).
4. **Record blind truth** in Section A: `expected_value`, `expected_scale`, `expected_unit`, `expected_canonical_label`, `expected_presence`, plus `source_location_recorded` (page, statement, exact line label).
5. **Record `reviewer_confidence` and any `source_ambiguity_note`** (restated / stated-in-summary-too / unclear units).
6. **Lock Section A** (timestamped). You cannot edit it after reveal without flagging the cell.
7. **Receive Section B** from the release gatekeeper (the system's `actual_value/scale/unit/label/presence` + `actual_source_page/table_type/source_class`).
8. **Compare and disposition** (§3).
9. **Set severity** — accept the auto-suggestion or override **with a note**.
10. **Flag adjudication** for any scale / unit / multi-table dispute or any S1; persist the row.

---

## 2. Blind-Review Procedure

- You only ever hold the **Blind Pack** until Section A is locked; the **gatekeeper** releases Section B per cell or per batch afterward.
- **Do not seek the system value** before locking — blindness is the integrity of the whole exercise.
- If you must edit a locked Section A after seeing Section B, the cell is **blindness-broken** → it is re-assigned to a different reviewer.
- Work unrushed: PDF line-reading is the slow, careful step.

---

## 3. Disposition Examples (one each)

| Disposition | When |
|---|---|
| `confirmed` | System value, scale, unit, label, and presence all match the source. |
| `corrected_value` | Right scale/label, **wrong number**. |
| `corrected_scale` | Right magnitude family wrong (thousands vs millions vs full). |
| `corrected_unit` | Wrong unit (EPS shown as currency; a % shown as absolute). |
| `corrected_label` | Mapped to the wrong canonical metric / wrong line. |
| `corrected_source` | A **note/summary/analysis** value chosen over the **primary statement**. |
| `spurious_extracted` | System has a value the source does not support. |
| `missing_extracted` | Value is in the source; system has none. |
| `source_ambiguous` | Source states it multiple ways → **adjudicate**. |
| `source_insufficient` | Source cannot establish truth → **excluded** (counted separately). |

---

## 4. Scale-Error Example (the dominant case)

> **Cell:** `ocr:<issuer>:revenue:<year>`. **Statement header reads "Rupees in thousands."** The income-statement Revenue line reads **528,651,878** (thousands).
> **Blind truth:** `expected_value = 528,651,878`, `expected_scale = thousands`, `expected_unit = PKR`.
> **Section B (revealed):** `actual_value = 25,417,143`, `actual_scale = full`.
> **Reasoning:** the magnitudes do not match under their scales (≈528.6bn vs ≈25.4m). **Scale comparison fails.**
> **Disposition:** `corrected_scale` → **S1** (baseline metric). *(If the number itself were also from the wrong line, see §5.)*
>
> **Rule:** read scale from the **units header**, never infer it from how big the number looks.

---

## 5. Note-vs-Statement Example

> **Cell:** `ocr:<issuer>:revenue:<year>`. The **income statement** (primary) shows Revenue on its page; the system instead selected a value from a **note** (`actual_source_class = note_disclosure`, e.g. a "Revenue – and liabilities is as follows" note).
> **Blind truth:** record the **primary-statement** Revenue value as `expected_*`; note the note value under `source_ambiguity_note`.
> **Section B:** `actual_source_class = note_disclosure`, value ≠ primary statement.
> **Disposition:** `corrected_source` → **S1** (system took the note over the statement).
>
> **Rule:** primary statement > supporting schedule > note > summary > analysis. A note value chosen when the statement has the line is always `corrected_source`.

---

## 6. Presence-Check Example (aggregates)

> **Cell:** `ocr:<issuer>:total_debt:<year>`. You scan the balance sheet: there is **no discrete "Total debt" line** (only short-term borrowings, long-term financing, lease liabilities as separate lines).
> **Blind truth:** `expected_presence = absent` (no discrete line). **Do NOT sum the components to invent a "total debt."**
> **Section B:** system has **no value** (`actual_presence = absent`).
> **Disposition:** `confirmed` — absent is the correct answer; the system's "missing" is right.
>
> **Contrast:** for `long_term_debt`, if a discrete **"Long-term financing"** line exists, `expected_presence = present` and you record its value/scale. A missing discrete line where one exists in the source → `missing_extracted`.

---

## 7. When to Flag Adjudication

Flag `needs_adjudication = true` and stop short of a final call when:
- **Scale dispute** — you and the units header disagree, or the header is unclear.
- **Unit dispute** — per-share vs currency vs % is unclear.
- **Multi-table conflict** — the metric appears with different values across statement / note / summary.
- **Any S1** — every baseline-metric `corrected_*` requires a second reviewer + adjudicator.
- **Restatement / summary-vs-statement difference** you cannot resolve to the primary statement.

The adjudicator resolves against the **units header** (scale), **label context** (unit), and **primary-statement precedence** (multi-table) — see `ocr_review_workbook_spec.md §3`.

---

## 8. One-Line Reminder

Open the source, record the truth blind, lock it, then compare — scale from the header, primary statement over notes, absent-aggregate is *correct*-missing, and when the source won't tell you cleanly, send it to adjudication rather than guess.
