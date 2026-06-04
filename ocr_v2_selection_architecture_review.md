# OCR V2 — Canonical Selection (P5) Architecture Review

**Status:** Architecture review only. No code, no implementation, no redesign. Frozen documents authoritative: OCR V2 Architecture Review, Migration Review, Contracts, Implementation Plan, Component Specifications.
**Date:** 2026-06-04
**Phases complete:** P0 Foundations · P1 Capture · P2 Registry · P3 Statement Governance · P3 Scale Governance · P4 Entity Governance.
**Next phase:** P5 Canonical Selection.
**Binding oracle:** `backend/ocr/ocr_v2_regression_cases.json` (`fixture_version 1.0.0`, `ocr_v2_cv1_lucky_regression_oracle`, `entity_ref lucky_cement`, `declared_basis unconsolidated`) — **15 verified candidate-pair cases.**

---

## 0. The Architectural Rules That Make the 15 Failures Impossible (answers the central question)

The oracle's 15 cases reduce to **three governance mechanisms** Selection must obey. Each case carries a verified-correct candidate (the authoritative source) and the verified-incorrect candidate V1 produced, with an `expected_governance_result`:

| Mechanism | Rule Selection MUST obey | Oracle cases | Verdict on the wrong candidate |
|---|---|---|---|
| **R2 — Hard eligibility bar** | Exclude entirely any candidate whose `basis ≠ declared`, `entity_scope ≠ issuer`, or `statement_type = analysis-table` | `gross_profit_2024/2025`, `net_profit_2024/2025`, `ocf_2025` (5 basis) · `total_assets_2025`, `investee_contamination_case` (2 investee) · `analysis_table_case` (1 analysis) = **8** | **INELIGIBLE** |
| **R3 — Source-type precedence + surfacing** | `primary > supporting > note > summary`; a lower tier is selectable **only if no higher-tier eligible candidate exists**, and such a selection is flagged — **never silent** | `revenue_2024/2025`, `revenue_note_vs_statement` (3 note) · `summary_table_case` (1 summary) = **4** | **REVIEW_REQUIRED** |
| **R4 — Scale from header only** | Header-sourced scale → `SCALE_VALID`; **magnitude-inferred scale → SCALE_REVIEW_REQUIRED, never silently canonical** | `revenue_2021_scale`, `total_equity_2025` (2 scale) · `long_term_debt_2024` (1 note-number) = **3** | **SCALE_REVIEW_REQUIRED** |

**8 + 4 + 3 = 15.**

**The precise guarantee (stated honestly):**
- The **8 R2 cases are impossible by construction** — the wrong candidate is *structurally excluded* and can never be considered.
- The **7 R3/R4 cases are impossible-as-a-silent-canonical-error** — because capture (P1) guarantees the authoritative candidate is present and `ELIGIBLE`/`SCALE_VALID`, and Selection ranks it above any note/summary/magnitude-inferred candidate while flagging the inferior one, the wrong value **can never silently win** over the present authoritative value.

**This makes Selection's guarantee conditional on two upstream facts:** (a) capture surfaced the authoritative candidate (P1 recall), and (b) entity scope was correctly tagged via MSIL (P4). Selection itself adds **no new way to fail** — given a correct `ELIGIBLE` candidate exists, no `INELIGIBLE` or inferior candidate can displace it.

---

## 1. Reconstructing OCR V1 Selection Behavior (Task 1)

V1 had **no candidate registry and no concept of eligibility.** It performed selection *during extraction/consolidation*: whatever value the extractor/normalizer emitted for a `(metric, value_year)` became canonical, and "duplicate" values were resolved by limited, position-driven precedence with **no representation of basis, entity_scope, source_type, or header scale.** There was no step at which a candidate could be *preferred* or *excluded* on governed grounds — selection was not wrong-headed, it **did not exist as a governed stage.**

---

## 2. Why V1 Produced the Verified CV1 Failures (Task 2)

A single root cause expresses itself across all 15 cases: **the four governance dimensions were never represented, so V1 had no basis on which to exclude or rank.**

- **No basis filter** → it wrote consolidated values for an unconsolidated series (`gross_profit`, `net_profit`, `ocf` — e.g. consolidated PAT 2025 `84,498,377` instead of unconsolidated `33,092,162`).
- **No entity filter** → it wrote investee values as issuer (`total_assets` NutriCo `16,845,584` p323; `revenue` ASIL `27,828,317` p322).
- **No source-type precedence** → it wrote NOTE values over the primary statement (`revenue` `26,282,162`/`25,417,143` p320 instead of `115,324,942`/`124,511,744` p241) and SUMMARY-table values over the value line.
- **No header-anchored scale** → it inferred scale from magnitude, producing ×1000 full-rupee corruptions (`revenue_2021` `…,805,000`; `total_equity` `…,400,000`), a millions/thousands summary mismatch, and a note-number (`1,000`) read as a value.

Every failure is a **missing-governance** failure, not an extraction-quality failure — consistent with CV1's 0% metric-concept error finding.

---

## 3. Responsibilities of Canonical Selection (Task 3)

Selection MUST, for each `(metric, value_year)`:
1. **Filter by hard eligibility** (R2) — drop `INELIGIBLE` candidates (wrong basis, non-issuer, analysis-table) from consideration entirely.
2. **Rank eligible candidates by source-type precedence** (R3) — choose the highest tier; select a lower tier only when no higher-tier eligible candidate exists, emitting `REVIEW_REQUIRED`.
3. **Resolve scale** (R4) — accept header-sourced scale as `SCALE_VALID`; mark magnitude-inferred scale `SCALE_REVIEW_REQUIRED` and never treat it as silently canonical.
4. **Emit exactly one canonical value** (or an explicit *no-eligible-candidate* outcome) + provenance.
5. **Record a machine-checkable rationale** and **retain all losing candidates** with their verdicts.

It does **not** extract, re-resolve entity identity, or rank by learned scores.

---

## 4. What Selection Consumes (Task 4)

- The **candidate registry** (P2) — validated candidates carrying all mandatory governance dimensions.
- **Governance config** — `declared_basis = unconsolidated`, source-type precedence order, scale target.
- **MSIL entity identity** (P4 binding) — to confirm `entity_scope = issuer`.
- The **metric registry** — canonical metric identities.

---

## 5. What Selection Must Never Consume (Task 5)

- **Magnitude** to infer scale (the direct cause of the 3 scale cases).
- **Raw PDF / extraction output** — Selection works only from the registry.
- **Its own prior outputs or any downstream value** (FVE/Query) — anti-closed-loop.
- **Any learned/statistical ranking model** — converting eligibility into a score reopens every failure the gate closes.
- **Self-invented entity identity** — identity is MSIL's.

---

## 6. Selection Invariants (Task 6)

- Exactly **one** canonical value per `(metric, value_year)`, or an explicit no-eligible-candidate outcome.
- An `INELIGIBLE` candidate is **never** selected.
- A lower source-type tier is selected **only if** no higher eligible tier exists, and the result is flagged `REVIEW_REQUIRED`.
- A magnitude-inferred scale is **never** `SCALE_VALID`.
- **Deterministic:** same registry + same config → same output and same per-candidate verdicts.
- Every canonical value has a **rationale** and **retained losers**.
- Selection runs **only after capture** — never during.

---

## 7. Losing-Candidate Behavior (Task 7)

Every non-selected candidate is **retained** (registry/sidecar) with its per-candidate verdict (`INELIGIBLE` / `REVIEW_REQUIRED` / `SCALE_REVIEW_REQUIRED`) and the reason it lost (wrong basis · investee · analysis-table · note-below-primary · summary-below-primary · magnitude-inferred-scale). **Never discarded.** This is both the audit trail and the substrate the regression oracle checks.

---

## 8. Rationale Requirements (Task 8)

For each canonical value the rationale MUST record: the **winning candidate** + its provenance; the **verdict and losing reason for every competitor**; the **precedence applied**; the **scale resolution** (source header vs target). The rationale MUST be **machine-checkable against the oracle's `expected_governance_result`** — for each oracle case, the correct candidate must receive its expected verdict (`ELIGIBLE`/`SCALE_VALID`) and the incorrect candidate its expected verdict (`INELIGIBLE`/`REVIEW_REQUIRED`/`SCALE_REVIEW_REQUIRED`).

---

## 9. Rollback Requirements (Task 9)

P5 is a **parallel** stage; V1 remains primary and serving (Option B). Therefore:
- If Selection fails its gate, **no cutover occurs** — V1 stays canonical (the rollback *is* not cutting over).
- Selection's **governance config is versioned**; any config change that regresses the oracle is reverted to the last passing version.
- The registry is **append-only**, so no Selection run can corrupt inputs — re-running is always clean.
- Cutover (P7) is reversible by flipping back to frozen V1.

---

## 10. Regression-Oracle Requirements (Task 10)

`ocr_v2_regression_cases.json` is the **binding gate** for P5:
- Selection MUST reproduce **all 15** `expected_governance_result`s — **15/15 or no-go.** A single divergence blocks advancement.
- The oracle is **externally verified** (`CV1 manual verification` + the architecture review), never the system's own output — **anti-closed-loop preserved.**
- The oracle is **version-pinned and append-only** (`fixture_version 1.0.0`); it may be **expanded** with new verified cases (e.g. Millat) but **never weakened** to make Selection pass.
- Selection is run against it **deterministically**; results are checked per-candidate, not just on the final value, so that a *right value reached for the wrong reason* still fails.
- The oracle is **basis-pinned** (`declared_basis = unconsolidated`); a change of declared basis requires a new oracle version.

---

## 11. Freeze Criteria for P5 (Task 11)

Canonical Selection is complete only when **all** hold:
1. **15/15** oracle cases pass with their exact `expected_governance_result`s (per-candidate).
2. R2 hard bars, R3 precedence+surfacing, and R4 scale resolution are each **independently enforced and tested.**
3. Selection is **deterministic** — no learned/probabilistic ranking.
4. Rationale is **machine-checkable**; all losers retained with verdicts.
5. Selection consumes **only** the registry + config + MSIL identity (never magnitude, raw extraction, or its own output).
6. Integrated **full CV1 re-run** within `thresholds_version 1.0.0`, with **zero regression** on V1-correct cells.
7. Output **≡ V1 canonical contract** (one value/metric/year + provenance) — frozen platform preserved.
8. The two upstream preconditions are **confirmed**: capture (P1) surfaces the authoritative candidate for every oracle case; entity scope (P4) is MSIL-bound.

---

## 12. One-Paragraph Verdict

The fifteen verified CV1 failures resolve into exactly three rules Canonical Selection must obey, and the regression oracle proves the decomposition: eight cases (consolidated basis, investee scope, analysis-table percentages) must be made structurally impossible by a **hard eligibility bar** that drops them from consideration entirely; four cases (note and summary contamination) must be made impossible-as-a-silent-error by **source-type precedence with surfacing**, so the primary statement always outranks the note or summary and any fallback selection is flagged `REVIEW_REQUIRED` rather than chosen quietly; and three cases (×1000 corruptions and a note-number read as a value) must be made impossible by reading **scale from the units header only**, marking every magnitude-inferred value `SCALE_REVIEW_REQUIRED` and never silently canonical. Because capture now guarantees the authoritative candidate is present and entity scope is MSIL-bound, Selection — operating deterministically over the registry, consuming no magnitude, no raw extraction, and no learned score, recording a machine-checkable rationale and retaining every loser — can displace none of those correct values with a wrong one. The honest boundary is that Selection's guarantee is conditional on its two upstream inputs (capture recall and entity tagging), and it introduces no new failure mode of its own; gate P5 on 15/15 against the externally-verified, append-only, never-weakened oracle, confirm zero regression on the cells V1 got right, and the canonical value Selection emits remains shape-identical to V1's — preserving the frozen platform while turning the fifteen documented failures into outcomes the engine can no longer produce.
