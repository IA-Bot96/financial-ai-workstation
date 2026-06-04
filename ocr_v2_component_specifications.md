# OCR V2 — Component Specifications

**Status:** Final pre-implementation artifact. **Behavioral specifications only** — no code, no implementation details, no class design, no schema design. Frozen documents authoritative: OCR V2 Architecture Review, Migration Review, Contracts, Implementation Plan. No redesign of MSIL/FVE/QAE/Query.
**Date:** 2026-06-03
**Evidence base:** CV1 (27 statement-selection + 14 scale failures; 0% metric-concept errors).

---

## 0. The Behavior That Makes Failures Impossible (answers the central question)

**What exact behavior must each component exhibit so the 27 statement-selection + 14 scale failures become impossible by construction?**

Each failure class maps to a *specific mandatory behavior* in a *specific component*:

| CV1 failure | Count | Component | Behavior that makes it impossible |
|---|---|---|---|
| Analysis-table read as a value | 13 | Statement Governance | MUST classify analysis/%-tables and mark them **canonical-ineligible**; Selection MUST refuse them |
| Consolidated read for an unconsolidated series | 8 | Statement Governance | MUST tag `basis` on every candidate; Selection MUST admit **only the declared basis** |
| Investee read as issuer | 6 | Entity Governance | MUST tag `entity_scope` (MSIL-bound); Selection MUST admit **only `issuer`** |
| Scale corruption (×1000 / mixed) | 14 | Scale Governance | MUST read source scale from the **units header**, never magnitude; normalize explicitly; surface conflicts |

The common spine across all four: **(a) capture has no selection authority**, **(b) the governance dimension is a mandatory field** (a candidate lacking it is rejected), and **(c) Selection is eligibility-gated** — the failing candidate is *ineligible*, not *low-ranked*. Below, each component's behavioral contract enforces this.

---

## 1. Candidate Capture Component

**Responsibilities:** read the source bundle/PDF and emit **candidate facts** — observations of presence, tagged with their captured context. Capture, never select.
**Inputs:** the pinned, frozen source bundle + its source PDF (fingerprint-matched).
**Outputs:** a stream of tagged candidate facts, each carrying the mandatory set `{value, value_year, source_label, page, table_ref, statement_type, basis, entity_scope, unit, scale, provenance}`.

**Invariants:**
- Every emitted candidate carries **all** mandatory dimensions.
- `scale`/`unit` are read from the source **units header**, never inferred from magnitude.
- `entity_scope` and `statement_type`/`basis` are the **observed** tags of the source table.
- Provenance is exact and per-candidate (document fingerprint, page, table, line/cell).

**Prohibited behaviors:** selecting a canonical value; ranking candidates; discarding a plausible candidate; inferring scale from magnitude; inventing entity identity; emitting a candidate with a missing/uncaptured mandatory dimension.

**Valid candidate:** a numeric observation with all mandatory dimensions populated from the source.
**Causes rejection:** any missing mandatory dimension; no readable source scale; no resolvable provenance location.

---

## 2. Candidate Registry Component

**Responsibilities:** persist, validate, dedup, and serve candidates with intact provenance; the single input to Selection.
**Lifecycle:** receive → **validate mandatory dimensions** → persist (append-only) → dedup → serve to Selection.

**Deduplication behavior:** removes **exact** duplicates only (identical value + year + provenance locator). **Different sources of the same metric are distinct candidates and are kept.** Dedup is by provenance, **never** by cross-source value-equality.

**Provenance guarantees:** every retained candidate's provenance is preserved precisely and immutably; the registry is the audit trail.

**Append behavior:** append-only; never mutates or overwrites a persisted candidate.
**Retention behavior:** retains **all** candidates, **including losing candidates** (those Selection does not pick).
**Invalid candidate handling:** a candidate failing mandatory-dimension validation is **rejected at the boundary** (logged, not persisted as canonical-eligible); it never reaches Selection.

---

## 3. Statement Governance Component

**Responsibilities:** classify each candidate's `statement_type` + `basis`; assign **canonical-selection eligibility** per the frozen Statement Governance contract.

**Eligibility & precedence rules:** source-type precedence is **primary statement > supporting schedule > note > summary > analysis-table**; basis precedence admits **only the declared canonical basis**.

| Type | Behavior |
|---|---|
| **Consolidated** | classified; canonical-eligible **only if** consolidated is the declared basis; else **supporting-only** |
| **Unconsolidated** | classified; canonical-eligible **only if** unconsolidated is the declared basis (Lucky: yes) |
| **Note** | classified; **ineligible** when a primary-statement candidate exists (**supporting-only**); eligible only if no primary exists and explicitly linked |
| **Summary table** | classified; **supporting-only** — a primary statement always wins; eligible only when no primary candidate exists |
| **Analysis table (%)** | classified; **NEVER canonical-eligible** — barred by construction (kills the 13) |

**Determination:** consolidated/unconsolidated eligibility is decided **solely** by the declared basis (kills the 8); analysis-tables are structurally barred (kills the 13); notes/summaries are supporting-only behind any primary statement.

---

## 4. Entity Governance Component

**Responsibilities:** assign canonical-selection eligibility by `entity_scope`, **bound to MSIL entity identity**.

| Scope | Handling / eligibility outcome |
|---|---|
| **Issuer** | the only **canonical-eligible** scope for the issuer's metric |
| **Subsidiary** | captured; **canonical-ineligible** for issuer metrics (supporting/contextual) |
| **Associate** (e.g. NutriCo) | captured; **canonical-ineligible** |
| **Joint venture** (e.g. LASHL) | captured; **canonical-ineligible** |
| **Investee** (any non-issuer) | captured; **canonical-ineligible** |

**Contamination prevention:** issuer-only eligibility **plus** validation of each candidate's `entity_scope` against **MSIL's resolved identity** — a candidate whose source entity resolves (via MSIL) to a non-issuer is **barred** from issuer canonical selection (kills the 6).

**MSIL ownership preserved:** **MSIL owns entity identity.** This component captures the *observed* scope and *enforces* issuer-only using MSIL's resolution. It **does not invent or re-resolve** identity.

---

## 5. Scale Governance Component

**Responsibilities:** govern source-scale capture and normalization to the documented target scale.

- **Source-scale capture:** the scale is read from the source statement's **units header** ("PKR in '000") and attached to each candidate verbatim. **Magnitude is never used to infer scale.**
- **Normalization behavior:** an **explicit, governed, auditable** transform `source_scale → target_scale`, recording both. Normalization is Selection-side; capture-side scale is source-truth.
- **Mixed-scale handling:** each candidate carries **its own** source scale, so a series with mixed scales (the OCF-2020–2023-in-millions case) normalizes correctly **without** any blanket series-scale assumption.
- **Scale conflicts:** two candidates for the same `(metric, year)` with different source scales are a **surfaced conflict**, resolved by the units header — **never silently picked**.

| Case | Outcome |
|---|---|
| **Accepted** | candidate with an explicit, header-sourced scale → normalized to target |
| **Rejected** | candidate with no readable source scale, or scale inferred from magnitude |
| **Surfaced** | conflicting source scales for the same metric/year (header arbitrates) |

(Kills the 14 by making scale a captured fact and normalization an explicit governed transform.)

---

## 6. Canonical Selection Component

**Responsibilities:** select **one** canonical value per `(metric, value_year)` from the registry by **eligibility evaluation**, applying basis + entity (issuer-only) + source-type precedence + scale normalization; generate a rationale; retain losers.

**Eligibility evaluation:** a candidate is selectable **only if** it is statement-eligible (right basis, eligible source type), entity-eligible (issuer), and scale-resolved. Ineligible candidates are **excluded from consideration entirely** — not ranked lower. Among multiple eligible candidates, source-type precedence + the units header break ties; an unresolved tie is **surfaced**, not guessed.

**Rationale generation:** records *why* the chosen candidate won and *why* each rejected class was ineligible.
**Losing-candidate handling:** all non-selected candidates retained (registry/sidecar) with reasons.

**Required inputs:** the validated candidate registry + governance eligibility (statement, entity, scale) + MSIL identity + governance config (declared basis, target scale, precedence).
**Required outputs:** one canonical value/metric/year + provenance + selection rationale + retained losers.

**Prohibited:** selecting during extraction; using magnitude for scale; selecting an analysis-table/investee/wrong-basis candidate; selecting a candidate with missing dimensions; owning/inventing entity identity; any learned/probabilistic ranking that converts eligibility into a score.

---

## 7. Workbook Generation Component

**Responsibilities:** present the **canonical values** (human deliverable) — one value per metric/year.
**Guarantees:** canonical-only; one value per metric/year; provenance-cited; contract-preserving; **no candidate growth** in the `.xlsx`.
**Exclusions:** candidates, losing candidates, and the registry are **not** in the workbook (they live in the `.kb.json` sidecar).
**Canonical-only behavior:** the workbook consumes **only** Selection's canonical output; it never reads the registry directly and never re-selects.

---

## 8. OCR→MSIL Export Component

**Responsibilities:** export the canonical metrics to MSIL with frozen-contract compatibility.
**Export contents:** canonical value/metric/year + provenance + `entity_scope = issuer` + `basis` + normalized `scale`; the candidate registry as an **additive sidecar**.
**Export guarantees:** output shape **≡ V1's** (one value/metric/year + provenance); additive fields are ignorable by current MSIL consumers; version pins populated.
**Compatibility guarantees:** the `annual_report` source contract is **unchanged**; MSIL **owns entity identity** and does **not** re-select; FVE/QAE/Query consume the canonical value and **never** re-select from candidates.

**Frozen MSIL contracts preserved.**

---

## 9. Validation Responsibilities (Task 9)

| Component | Component-level | Integration | CV1 oracle |
|---|---|---|---|
| **Capture** | every candidate has mandatory dims; scale from header | feeds registry without loss | recall ≥ V1 + recovers the ~7 missing |
| **Registry** | append-only; all losers retained; exact-only dedup | serves validated candidates to Selection | zero provenance loss vs truth set |
| **Statement Gov.** | correct type/basis classification; analysis-table flagged ineligible | eligible set reaches Selection | **8 basis + 13 analysis → ~0** in isolation |
| **Entity Gov.** | issuer-only eligibility; MSIL-bound | enforced inside Selection | **6 investee → 0** in isolation |
| **Scale Gov.** | header-sourced scale; explicit normalization; conflicts surfaced | normalized values reach Selection | **14 scale → 0/governed**; OCF mixed-scale correct |
| **Selection** | eligibility-gated; rationale + losers recorded | integrates all governance + MSIL | full CV1 re-run within thresholds 1.0.0; **zero regression** |
| **Workbook** | canonical-only; provenance-cited | consumes only Selection output | matches canonical truth cells |
| **OCR→MSIL** | output ≡ V1; pins populated | MSIL re-ingest clean | downstream revalidation passes |

---

## 10. Component Dependency Diagram (Task 10)

**Build / dependency order:**
```
Capture → Registry → (Statement Gov. ‖ Scale Gov.) → Entity Gov.[needs MSIL] → Selection → Workbook → OCR→MSIL Export
```
- Capture precedes Registry (nothing to store otherwise).
- Registry precedes all governance (governance needs populated inputs).
- Statement + Scale governance have **no external dependency** → built first.
- Entity governance is **blocked on MSIL identity** → built after.
- Selection integrates all three + MSIL.
- Workbook and Export consume Selection.

**Validation order:** validate each governance layer **in isolation against its own CV1 subset** (statement → 8+13; scale → 14; entity → 6) **before** Selection integration; then full CV1 re-run at Selection; then output-equivalence at Export.

---

## 11. Ownership Matrix (Task 11)

| Concept | Owner |
|---|---|
| Candidate existence + observed tags (statement_type, entity_scope, source scale, provenance) | **OCR Capture** |
| Persistence, exact-dedup, provenance integrity, loser retention | **Registry** |
| Statement type/basis classification + statement eligibility | **Statement Governance** |
| Issuer-only eligibility enforcement (using MSIL identity) | **Entity Governance** |
| Source-scale truth (header) + normalization to target | **Scale Governance** |
| Which candidate is canonical + rationale + tie/conflict surfacing | **Canonical Selection** |
| **Entity identity** (issuer vs investee resolution) | **MSIL** |

One owner per concept; no component recomputes another's owned concept.

---

## 12. Freeze Conditions (Task 12) — per component

A component is **complete** only when:
1. **Capture** — proven recall ≥ V1 + the ~7 missing recovered; 100% of emitted candidates carry mandatory dims; zero magnitude-inferred scales.
2. **Registry** — append-only + all-losers-retained + exact-only-dedup proven; zero provenance loss.
3. **Statement Gov.** — analysis-tables 100% flagged ineligible; basis classification correct on the CV1 set; **8 + 13 → ~0** in isolation.
4. **Entity Gov.** — issuer-only enforced; MSIL-bound; **6 → 0** in isolation; no in-OCR identity invention.
5. **Scale Gov.** — header-sourced scale; explicit normalization with recorded source→target; conflicts surfaced; **14 → 0/governed**; OCF mixed-scale correct.
6. **Selection** — eligibility-gating proven (ineligible classes excluded, not ranked); rationale + losers recorded; full CV1 re-run within thresholds 1.0.0; **zero regression** on V1-correct cells; **deterministic** (no learned ranking).
7. **Workbook** — canonical-only verified; matches canonical truth cells; no candidate leakage into `.xlsx`.
8. **OCR→MSIL** — output ≡ V1 confirmed by the equivalence harness; pins populated; downstream revalidation clean.

Overarching: **every prohibited behavior is enforced and tested** (the failure modes are unrepresentable, not merely avoided).

---

## 13. One-Paragraph Verdict

These specifications convert CV1's catalogue of failures into a set of behaviors each component must exhibit before it is allowed to exist: Capture must observe and tag — never select, never guess scale from magnitude, never emit a candidate missing a governance dimension; the Registry must keep everything, including the losers, with provenance intact; Statement Governance must bar analysis-tables and admit only the declared basis, killing the 13 and the 8; Entity Governance must admit only the issuer, bound to MSIL's identity, killing the 6; Scale Governance must read the units header and normalize explicitly, surfacing conflicts rather than picking, killing the 14; and Canonical Selection must treat all of this as *eligibility* — excluding the wrong candidate from consideration entirely rather than ranking it lower — so that no learned score can ever reintroduce the failure the gate removed. Validated layer-by-layer against the CV1 subset each is responsible for, then end-to-end at Selection and for output-equivalence at Export, the components compose into an engine whose canonical output is shape-identical to V1's — preserving the frozen platform — while the 27 statement-selection and 14 scale failures are no longer outcomes the system can produce. With these behavioral contracts frozen, OCR V2 is fully specified and ready for implementation.
