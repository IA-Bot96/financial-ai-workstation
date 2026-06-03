# CV1 Calibration Set

**Status:** Reviewer-calibration material. **All cells below are ILLUSTRATIVE TRAINING SCENARIOS — not CV1 results, not measurements, not correctness conclusions about any bundle.** They exist so all reviewers align disposition/severity judgment *before* the main pass.
**Use:** every reviewer + the adjudicator completes these blind, then reconciles against the "expected review behavior" here. Discrepancies are discussed until aligned.

---

## 0. How to Run Calibration

1. Each reviewer receives the 5 cells as a Blind Pack (Section A blanks + the scenario's source description) **without** the "Section B" or "expected behavior."
2. Each records blind truth + disposition + suggested severity independently.
3. The release gatekeeper reveals Section B.
4. Reviewers compare to the **expected review behavior** below and reconcile differences with the adjudicator.
5. Calibration passes when reviewers converge on disposition + severity + adjudication-routing for all 5.

---

## 1. Calibration Cell C1 — Scale Error (S1)

- **Scenario (source):** statement header "Rupees in thousands"; income-statement Revenue line = **528,651,878** (thousands).
- **Section B (system):** `actual_value = 25,417,143`, `actual_scale = full`.
- **Expected blind truth:** value `528,651,878`, scale `thousands`, unit `PKR`, label `revenue`, presence `present`.
- **Expected disposition:** `corrected_scale` · **direction** assertion · **severity S1**.
- **Teaching point:** magnitudes don't match under their scales; scale read from the header, not the number's size.

---

## 2. Calibration Cell C2 — Note-vs-Statement (S1)

- **Scenario:** income statement shows Revenue on its page; system selected a **note-disclosure** value instead.
- **Section B:** `actual_source_class = note_disclosure`; value ≠ the income-statement line.
- **Expected blind truth:** the **primary-statement** Revenue value; note value recorded in `source_ambiguity_note`.
- **Expected disposition:** `corrected_source` · assertion · **S1**.
- **Teaching point:** primary statement outranks a note; selecting the note is `corrected_source`, not merely `corrected_value`.

---

## 3. Calibration Cell C3 — Aggregate Presence (Confirmed)

- **Scenario:** balance sheet has separate "short-term borrowings", "long-term financing", "lease liabilities" lines but **no discrete "Total debt" line**.
- **Section B:** system has **no value** for `total_debt` (`actual_presence = absent`).
- **Expected blind truth:** presence `absent` (no discrete line); **do not sum components**.
- **Expected disposition:** `confirmed` (absent is correct) · severity n/a (pass).
- **Teaching point:** a missing aggregate that has no discrete source line is *correctly* missing — not `missing_extracted`.

---

## 4. Calibration Cell C4 — Clean Match (Confirmed)

- **Scenario:** income statement shows EPS line = **52.53** (rupees per share).
- **Section B:** `actual_value = 52.53`, `actual_unit = per_share`, `actual_scale = full`.
- **Expected blind truth:** value `52.53`, unit `per_share`, scale `full`, label `earnings_per_share`, presence `present`.
- **Expected disposition:** `confirmed` · pass.
- **Teaching point:** the happy path; EPS is **per-share** (never thousands) — confirm unit explicitly.

---

## 5. Calibration Cell C5 — Source-Ambiguous → Adjudication

- **Scenario:** for a comparative `value_year`, the **primary statement** shows one figure while the **five-year summary** shows a different figure (a likely scale/restatement difference); the system selected one of them.
- **Section B:** system value matches the **summary**, not the primary statement.
- **Expected blind behavior:** record the **primary-statement** value as `expected_*`; set `source_ambiguity_note` (summary differs); set `needs_adjudication = true`.
- **Expected disposition (pre-adjudication):** `source_ambiguous`.
- **Teaching point:** summary is secondary to the primary statement; route to adjudication rather than self-resolving.

### Adjudication Example for C5
| Field | Value |
|---|---|
| `dispute_type` | multi_table (summary vs primary statement) |
| `reviewer_a_position` | primary-statement value is truth |
| `reviewer_b_position` | summary value (matches system) |
| `source_evidence_examined` | units headers of both; comparative-column consistency; restatement footnote |
| `resolution_rule_applied` | `primary_statement_anchor` |
| `resolution` | primary-statement value is `expected`; system selected the summary |
| `outcome_disposition` | `corrected_source` (system took the secondary summary) |
| `final_severity` | **S1** (baseline metric) |
| `corrected_and_root_caused` · `re_sample_required` | per CV0 — if corrected as data, re-sample the affected stratum |

> *Alternate outcome:* if the primary statement is itself internally inconsistent and the difference cannot be resolved → `source_insufficient` (excluded from rate; counted separately).

---

## 6. Calibration Pass Criteria

- All reviewers converge on disposition + severity for C1–C4 and on **adjudication-routing** for C5.
- Any persistent disagreement on **scale reading** (C1) or **primary-statement precedence** (C2/C5) must be reconciled before the main pass — these are the two highest-frequency real disputes.
- Record a short calibration sign-off (reviewers, adjudicator, date) before CV1 cells begin.

---

## 7. One-Line Note

These five illustrative cells train the exact judgments CV1 turns on — scale-from-the-header, primary-statement-over-notes-and-summaries, correctly-absent aggregates, the clean per-share path, and route-don't-guess — and contain no findings about any real bundle; they are practice, not measurement.
