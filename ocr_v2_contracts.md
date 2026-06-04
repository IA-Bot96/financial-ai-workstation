# OCR V2 — Contracts

**Status:** Frozen-contract specification for OCR V2, pre-implementation. No code, no implementation, no schema design beyond contract concepts. No redesign of MSIL/FVE/QAE/Query. Frozen platform boundary preserved.
**Date:** 2026-06-03
**Pipeline:** `Capture-first → Candidate Registry → Governed Canonical Selection → Canonical Workbook Output`.
**Evidence base:** the executed CV1 audit (27 statement-selection failures, 14 scale failures, 0% metric-concept errors; 85% of wrong values already present in the PDF).

---

## 0. The By-Construction Principle (answers the central question)

CV1's 27 statement-selection + 14 scale failures become **impossible by construction** — not "less likely" — through three structural mechanisms encoded in these contracts:

1. **Extraction has no selection authority.** Capture produces *candidates only*; there is no selection step inside extraction, so a fused mis-selection (V1's flaw) cannot occur.
2. **Governance dimensions are mandatory on every candidate.** `basis`, `entity_scope`, `source_type`, `unit`, `scale` are **required** — a candidate missing any is **invalid and rejected**. Selection therefore always possesses the dimensions whose *absence* caused V1's failures.
3. **Selection is eligibility-gated, not score-ranked.** The failing candidate classes are made **structurally ineligible**, not merely down-weighted:
   - analysis/percentage tables → **never** canonical-selectable (kills the 13 analysis-table errors);
   - `entity_scope ≠ issuer` → **never** the issuer's canonical value (kills the 6 LASHL/NutriCo investee errors);
   - wrong `basis` for the declared canonical series → **ineligible** (kills the 8 consolidated-vs-unconsolidated errors);
   - magnitude-inferred or unscaled values → **prohibited**; scale captured from the header + governed normalization (kills the 14 scale corruptions).

**The guarantee is ineligibility (a structural bar), not preference (a probabilistic score).** A wrong candidate *cannot* be selected because it is ineligible — not because it scored lower.

---

## 1. Candidate Fact Contract

**Represents:** one observed numeric fact at one source location — `(value, value_year, source_label)` with mandatory captured context. It represents **presence/observation**, nothing more.
**Never represents:** a canonical value, a selected value, a "correct" value, an authoritative number, or a resolved entity identity. **A candidate is an observation, never a verdict.**

- **Ownership:** OCR (capture) owns a candidate's existence + captured attributes; **not** which candidate is canonical (Selection) and **not** entity identity (MSIL).
- **Invariants:** every candidate carries the **mandatory** set `{value, value_year, source_label, page, table_ref, statement_type, basis, entity_scope, unit, scale, provenance}`. **A candidate missing any mandatory governance dimension is invalid and rejected** (cannot enter the registry). Deterministic, text-independent id (provenance-derived).
- **Provenance requirements:** exact, immutable source location (document fingerprint, page, table, line/cell) per candidate; no dilution, no aggregation.
- **Scale requirements:** `scale` and `unit` captured **explicitly from the source statement's units header** — **never inferred from magnitude**; a candidate without an explicit source scale is invalid.
- **Entity requirements:** `entity_scope` captured as the **observed** scope (issuer/subsidiary/associate/JV/investee) of the source table; MSIL owns canonical identity — the candidate carries the observed tag only.
- **Statement requirements:** `statement_type` + `basis` captured per the source table (§3).

---

## 2. Candidate Registry Contract

- **Purpose:** the persistent, auditable store of **all** captured candidates + provenance; the single input to Selection.
- **Lifecycle:** capture → validate (mandatory dimensions) → persist → dedup → available for Selection. **Append-only, never mutated**, versioned per bundle.
- **Retention:** **all candidates retained, including losers.** *(Answer: yes — losing candidates are always retained.)* This is the auditability guarantee V1 lacked (V1 discarded losers, making errors unrecoverable).
- **Deduplication responsibilities:** dedup **exact** duplicates (identical value + year + provenance locator) **only**. **Different sources of the same metric are distinct candidates**, preserved for Selection and audit. Dedup by provenance, **never** by cross-source value-equality.
- **Provenance guarantees:** every candidate's provenance preserved precisely; the registry is the audit trail.
- **Ownership:** the Registry owns persistence/dedup/provenance integrity — **not** capture, **not** selection.

---

## 3. Statement Governance Contract

| Statement type | Capture eligibility | Canonical-selection eligibility |
|---|---|---|
| **Consolidated** | captured | eligible **only if** consolidated is the **declared canonical basis**; else **supporting-only** |
| **Unconsolidated / standalone** | captured | eligible **only if** unconsolidated is the declared basis (per CV1, the clean Lucky series) |
| **Note (disclosure)** | captured | **ineligible** for a primary-statement metric when a primary candidate exists (**supporting-only**); selectable only if no primary exists **and** explicitly linked |
| **Analysis table (horizontal/vertical %)** | captured (presence) | **NEVER canonical-selectable** — structurally barred (kills the 13 analysis-table errors) |
| **Summary table (5/6-year)** | captured | **supporting-only / secondary** — primary statement always wins; selectable only when no primary candidate exists |
| **Segment disclosure** | captured | **supporting-only** for entity-level canonical metrics (segment ≠ entity total) |

- **Capture is presence-broad** (all types captured); **selection is eligibility-narrow** (gated by declared basis + source-type precedence).
- **Source-type precedence:** primary statement > supporting schedule > note > summary > analysis-table (analysis-table = ineligible).
- The **declared canonical basis** per issuer/series is a **governed config item** (Selection-layer/MSIL-governed), not an OCR decision.

---

## 4. Entity Governance Contract

**Definitions:** issuer (the reporting entity), subsidiary, associate, joint venture, investee (any non-issuer entity whose figures appear in the report — e.g. LASHL JV, NutriCo associate).

- **Capture rules:** capture candidates from **all** entity scopes (presence), each tagged with its **observed** `entity_scope`.
- **Canonical-selection rules:** **issuer-only.** Only `entity_scope = issuer` candidates are canonical-selectable for the issuer's metric. Subsidiary/associate/JV/investee candidates are **canonical-selection-ineligible** (supporting/contextual). *(Kills the 6 LASHL/NutriCo investee errors by construction.)*
- **Contamination prevention:** the issuer-only eligibility gate **plus** validation of each candidate's `entity_scope` against **MSIL's entity identity** — a candidate whose source entity resolves (via MSIL) to a non-issuer is **barred** from issuer canonical selection.
- **MSIL ownership preserved:** **MSIL owns canonical entity identity** (issuer vs investee). OCR captures the *observed* scope; Selection *enforces* issuer-only *using* MSIL identity. **Neither OCR nor Selection invents entity identity.**

---

## 5. Scale Governance Contract

(Grounded in the verified CV1 scale failures: ×1000 thousands→full corruptions; OCF 2020–2023 only in PKR **millions** while the series is in thousands.)

- **Scale ownership — source scale:** owned at **capture**, read **verbatim from the source statement's units header** ("PKR in '000"). **Magnitude never determines scale** (prohibited).
- **Normalization authority:** the **Selection/normalization layer** owns the governed transform to a **documented target scale**, recording `source_scale → target_scale` (auditable). OCR captures source scale; Selection normalizes.
- **Scale inheritance:** a candidate's scale is inherited from **its own source table's header**, never from sibling candidates or a metric's "usual" scale. **Mixed-scale series are handled by construction** because each candidate carries its own source scale (the OCF-in-millions case normalizes correctly without a blanket series-scale assumption).
- **Scale conflict handling:** two candidates for the same `(metric, year)` with different source scales = a **surfaced scale conflict** resolved by the units header (governed), **never silently picked**.
- **Who owns scale truth:** **capture owns the source scale (from the header); Selection owns the normalized canonical scale (governed transform).** Magnitude owns nothing.

---

## 6. Canonical Selection Contract

- **Responsibilities:** select **one** canonical value per `(metric, value_year)` from the registry, applying **basis + entity (issuer-only) + source-type precedence + scale normalization**, recording the **rationale and the losing candidates**.
- **Authority:** owns *which* candidate is canonical and the *normalized scale*. Does **not** own entity identity (MSIL), capture, or persistence.
- **Inputs:** the validated candidate registry + governance config (declared basis, precedence, target scale) + MSIL entity identity.
- **Outputs:** one canonical value/metric/year + provenance + selection rationale + retained losing candidates (to the sidecar).
- **Can use:** the candidates' captured dimensions (basis, entity_scope, source_type, scale, label, provenance), the governance rules, and MSIL entity identity.
- **Cannot use:** magnitude to infer scale; an analysis-table candidate as a value; a non-issuer candidate for an issuer metric; a wrong-basis candidate for the declared series; a candidate missing mandatory dimensions; ungoverned heuristics. It **cannot run during extraction** and **cannot invent entity identity.**
- **Does Selection own entity identity?** **No — MSIL does.** Selection only *enforces* issuer-only using MSIL's identity.

---

## 7. Canonical Metric Contract (the output consumed by MSIL)

- **Meaning:** one governed, **issuer-scoped, declared-basis, scale-normalized** value per `(metric, value_year)`, with provenance + selection rationale.
- **Guarantees:** issuer-scoped (no investee), declared-basis, primary-statement-sourced (or governed fallback), explicitly scaled, provenance-backed, **derived only from a selection-eligible source class** (never analysis-table/investee/wrong-basis), with losing candidates retained for audit.
- **Provenance obligations:** cites the exact source location of the **selected** candidate + the selection rationale; losing candidates retained in the sidecar.
- **Downstream guarantees:** **same shape as V1's canonical value** (one value/metric/year + provenance) → MSIL/FVE/QAE/Query consume **unchanged**; the candidate registry is an **additive** sidecar (optional consumption).

---

## 8. Workbook Contract

- **Responsibilities:** present the **canonical values** (human deliverable) — one value/metric/year, the frozen contract.
- **Limitations:** the `.xlsx` carries **canonical values only** (no candidate explosion in the human workbook); it is **not** the audit store.
- **Guarantees:** canonical-only, contract-preserving, no growth from candidates.
- **Relationship to registry:** **"C, layered"** — the `.xlsx` = canonical view; the **`.kb.json` sidecar** carries canonical + the candidate registry (losers + rationale). Workbook consumes the selected canonical; the registry is the audit substrate.

---

## 9. OCR → MSIL Contract

- **Information transferred:** the canonical value/metric/year + provenance + `entity_scope = issuer` + `basis` + normalized `scale` + (sidecar) the candidate registry.
- **Information retained (OCR/registry side):** the full candidate registry / losing candidates — available for drill-down, **not required** by MSIL's frozen contract.
- **Ownership boundaries:** OCR delivers **issuer-scoped canonical values**; **MSIL owns entity identity** (validates the issuer scope), authority, and the evidence-layer role; MSIL **does not re-select**. OCR enforces issuer-only *using* MSIL identity.
- **MSIL contracts preserved:** the `annual_report` source contract (canonical value + provenance) is **unchanged**; `entity_scope`/`basis`/`scale` are **additive** information MSIL may use.

---

## 10. OCR V2 Versioning Contract

- **Version pins:** `ocr_v2_contract_version`, `candidate_schema_version`, `governance_config_version` (declared basis + precedence), `scale_target_version`, `registry_version`, + `bundle_fingerprint` + `engine_version`.
- **Compatibility rules:** the **canonical output contract is frozen-equivalent to V1** (one value/metric/year + provenance) — downstream compatibility guaranteed; the candidate sidecar is **additive** (consumers may ignore unknown fields); governance/basis/scale changes = **governed version bump**.
- **Migration guarantees:** **V2 output ≡ V1 output contract** (platform preserved by construction); re-validation (not redesign) on cutover; every run reproducible against pinned governance config + bundle fingerprint.

---

## 11. Ownership Table (one owner per concept)

| Concept | Owner |
|---|---|
| Candidate existence + captured attributes (observed scale/entity_scope/statement_type) | **OCR (capture)** |
| Candidate persistence, dedup, provenance integrity | **Candidate Registry** |
| Canonical selection (which candidate, normalized scale, basis/source/entity precedence enforcement) | **Canonical Selection** |
| **Entity identity** (issuer vs investee resolution) | **MSIL** |
| Source scale truth (from header) | **OCR (capture)** |
| Normalized canonical scale | **Canonical Selection** |
| Numeric validation / baselines | **FVE** |
| Themes / narrative | **QAE** |
| Retrieval / citation / answers | **Query** |

No engine recomputes another's owned concept; **downstream consumes the canonical value and never re-selects from candidates.**

---

## 12. Prohibited Behaviors

- **Selecting an investee/associate/JV/subsidiary candidate as the issuer's canonical value** (non-issuer = ineligible).
- **Selecting an analysis/percentage-table candidate as a value metric** (ineligible by construction).
- **Selecting a wrong-basis candidate** (e.g. consolidated when unconsolidated is the declared series).
- **Selecting a note/summary over a primary statement when a primary candidate exists.**
- **Discarding provenance or losing candidates** (registry retains all; append-only).
- **Inferring scale from magnitude** (scale comes from the header only).
- **Canonical selection during extraction** (capture has no selection authority).
- **Authority assignment inside OCR** (OCR captures presence; authority/governance is the selection/evidence layer).
- **OCR or Selection inventing entity identity** (MSIL owns it).
- **Emitting a candidate missing mandatory governance dimensions** (invalid).
- **Mutating/overwriting the registry** (append-only).
- **Downstream re-selecting from candidates** (FVE/QAE/Query consume the canonical, never re-select).

---

## 13. Freeze Checklist (conditions before OCR V2 implementation may begin)

1. ☐ **Candidate Fact** contract frozen — mandatory-dimension set enumerated; capture-is-presence-not-authority; provenance/scale/entity/statement requirements.
2. ☐ **Candidate Registry** contract frozen — retain-all-losers; provenance-keyed dedup; append-only; versioned.
3. ☐ **Statement Governance** frozen — the 6 statement types' capture vs selection eligibility; **analysis-table never canonical**; note/summary supporting-only; declared-basis config.
4. ☐ **Entity Governance** frozen — **issuer-only** selection; MSIL entity-identity ownership; contamination gate.
5. ☐ **Scale Governance** frozen — capture-from-header; **magnitude-inference prohibited**; normalization authority; mixed-scale + conflict handling.
6. ☐ **Canonical Selection** contract frozen — eligibility gates; can/cannot-use; no entity-identity ownership; runs after capture only.
7. ☐ **Canonical Metric + Workbook** contracts frozen — output ≡ V1; canonical-only `.xlsx`; sidecar registry.
8. ☐ **OCR→MSIL** contract frozen — **output-contract equivalence confirmed** (platform preserved); MSIL contracts intact.
9. ☐ **Versioning** contract frozen — version pins; output-equivalence; additive sidecar.
10. ☐ **Ownership table** ratified (one owner per concept).
11. ☐ **Prohibited behaviors** ratified.
12. ☐ **Declared canonical basis** confirmed per issuer (CV1: **unconsolidated** for Lucky) — governed config.
13. ☐ **Target normalized scale convention documented** (carried from CV1's scale-convention confirm).
14. ☐ **MSIL issuer-vs-investee identity** available for the validated issuers (LASHL/NutriCo distinct from Lucky).
15. ☐ **CV1 truth set** available as the cutover oracle (migration M2/M3 gate).

---

## 14. One-Paragraph Verdict

OCR V2's contracts answer the only question that matters — *can the CV1 failures become impossible rather than merely rarer?* — with a structural yes: extraction is stripped of all selection authority so a fused mis-pick cannot occur; every candidate must carry `basis`, `entity_scope`, `source_type`, and a header-read `scale` or it is invalid, so selection never lacks the dimensions whose absence caused V1's mistakes; and canonical selection is **eligibility-gated**, which bars the exact failing classes by construction — analysis/percentage tables can never be a value, a non-issuer candidate can never be the issuer's metric, a wrong-basis candidate can never enter the declared series, and a magnitude-guessed scale can never be emitted. The registry retains every losing candidate so the choice is auditable, the workbook stays canonical-only while the sidecar carries the candidates, and — because the canonical output is shape-identical to V1's — the frozen platform is preserved by construction, leaving MSIL/FVE/QAE/Query a re-validation rather than a redesign. Freeze these thirteen contracts, confirm the declared basis, the scale-target, and MSIL's issuer-vs-investee identity, and OCR V2 can be built knowing the 27 statement-selection and 14 scale failures are not down-weighted — they are made unrepresentable.
