# OCR V2 — Implementation Plan

**Status:** Planning only. No code, no implementation details. Frozen documents authoritative: OCR V2 Architecture Review, Migration Review, Contracts. All frozen contracts preserved; no platform redesign.
**Date:** 2026-06-03
**Migration model:** Option B — parallel V1 ‖ parallel V2, validated staged cutover, CV1 truth set as the oracle.
**Evidence base:** CV1 (NOT_CERTIFIED; 84.6% S1; **27 statement-selection + 14 scale + ~7 recall**; 0% metric-concept errors).

---

## 0. The Safest Path, Answered First

**What is the safest path from V1 to V2 while preserving the frozen platform and using CV1 as the migration oracle?**

**Build V2 in parallel behind a frozen, still-serving V1, and validate each governance layer against its own pre-attributed CV1 failure subset before integrating — cut over only on a full V2 CV1 re-run that is certified/conditional with zero regression, with rollback = flip to frozen V1.**

The safety comes from a property only the CV1 oracle provides: **every failure is already attributed to a class** — 8 consolidated-vs-unconsolidated + 13 analysis-table + 6 investee = **27 statement**, **14 scale**, **~7 recall**. So the migration decomposes into **independently-provable increments**:
- statement governance must drive the **8 + 13** to ~0;
- entity governance must drive the **6** to 0;
- scale governance must drive the **14** to 0/governed;
- capture must recover the **~7**.

Each layer is proven against its own subset *before* end-to-end integration, V1 never stops serving, the platform contract is preserved by construction (V2 output ≡ V1 output), and the only cutover gate is the oracle itself.

---

## 1. Build Order (Task 1)

```
P0 Foundations/prerequisites
P1 Candidate Capture (tag: statement_type, entity_scope, source-scale, provenance)
P2 Candidate Registry (validate mandatory dims · persist · dedup · provenance)
P3 Statement Governance + Scale normalization rules (no external dependency)
P4 Entity Governance (issuer-only; bound to MSIL identity)
P5 Canonical Selection (integrate P3+P4; eligibility-gated)
P6 Workbook Generation + OCR→MSIL Export (canonical-only .xlsx + sidecar; output-equivalence)
P7 Parallel comparison → staged cutover → downstream revalidation
```

**Why this order:** capture must exist before there is anything to register; the registry must be populated before governance has inputs; the two no-external-dependency governance layers (statement, scale-normalization) precede the externally-blocked one (entity needs MSIL); selection integrates all three; workbook/export consume selection; cutover is last and reversible.

---

## 2. Dependency Analysis (Task 2)

| Component | Prerequisites | Blockers | Hidden dependencies |
|---|---|---|---|
| **Candidate Capture** | capture contract; frozen bundle/PDF access | statement/entity/scale tagging vocabularies | table-detection **recall** (must find what V1 found + the ~7 it missed); page/provenance fidelity; units-header location |
| **Candidate Registry** | capture output; Candidate Fact contract | mandatory-dimension validation rules | provenance-keyed dedup correctness; append-only integrity |
| **Statement Governance** | statement_type tagging; **declared canonical basis** | declared basis confirmed per issuer (**unconsolidated** for Lucky) | analysis-table vs value-line detection; note-vs-statement; summary-table identification |
| **Entity Governance** | entity_scope tagging; **MSIL entity identity** | **MSIL issuer-vs-investee resolution available** (LASHL/NutriCo) | which table belongs to which entity; MSIL coverage of the investees |
| **Scale Governance** | per-candidate source scale captured; **scale-target convention documented** | the documented OCR scale convention (carried from CV1) | mixed-scale series (OCF-in-millions); header scope (which tables a header governs) |
| **Canonical Selection** | populated registry; all 3 governance layers; MSIL identity | all of the above | tie-break among multiple eligible candidates; conflict surfacing |
| **Workbook Generation** | selection output; Canonical Metric contract | none beyond selection | sidecar format; .xlsx canonical-only discipline |
| **OCR→MSIL Export** | Canonical Metric contract; **output-contract-equivalence confirmed** | equivalence harness | additive sidecar fields MSIL may ignore; version pins |

**The four named hidden dependencies are all Must-Before:** MSIL entity identity (P4 blocker), scale convention (P3 blocker), declared basis (P3 blocker), registry availability (P5 blocker).

---

## 3. Phase Plan (Task 3)

| Phase | Scope | Outputs | Validation gate | Rollback |
|---|---|---|---|---|
| **P0 Foundations** | Confirm 13 contracts frozen; secure MSIL identity, declared basis, scale-target, CV1 oracle; stand up output-equivalence harness | Pinned prerequisites; equivalence harness | All 4 hidden deps available; contract-equivalence harness runs against V1 | n/a (no build) |
| **P1 Capture** | Capture-first front-end: read + tag candidates (statement_type, entity_scope, source-scale, provenance); V1 still serving | Tagged candidate stream for Lucky (+Millat) | **Capture recall ≥ V1 extraction** (no lost data) + recovers the ~7 missing cells; every candidate carries mandatory dims | Discard V2 path; V1 untouched |
| **P2 Registry** | Validate mandatory dims; persist append-only; provenance-keyed dedup | Populated candidate registry + provenance | All-losers-retained verified; dedup exact-only; zero provenance loss | Rebuild registry; V1 untouched |
| **P3 Statement + Scale gov.** | Statement eligibility rules (analysis-table-never-canonical, basis, note/summary supporting-only) + scale normalization (header-only, governed) | Eligibility-tagged candidates; normalized scales | **Statement subset: 8+13 → ~0**; **scale subset: 14 → 0/governed**, validated in isolation vs CV1 | V1 primary; discard rule set |
| **P4 Entity gov.** | Issuer-only eligibility bound to MSIL identity; contamination gate | Issuer-scoped eligibility | **Entity subset: 6 (LASHL/NutriCo) → 0**, validated in isolation vs CV1 | V1 primary; discard gate |
| **P5 Canonical Selection** | Integrate P3+P4; one canonical value/metric/year; record rationale + losers | V2 canonical values (parallel to V1) | **Full V2 CV1 re-run** within thresholds 1.0.0; **no regression on V1-correct cells** | V1 still primary |
| **P6 Workbook + Export** | Canonical-only .xlsx + sidecar registry; OCR→MSIL export | V2 .xlsx + .kb.json sidecar | **Output ≡ V1 contract** (equivalence harness green); sidecar additive | Serve V1 output |
| **P7 Cutover** | Parallel V1‖V2 comparison; staged cutover; downstream revalidation | V2 canonical; V1 archived | CV1 re-run certified/conditional + downstream revalidation clean | **Flip to frozen V1** |

---

## 4. Validation Gates (Task 4)

**The CV1 truth set is the oracle at every gate.** Per-class pre-attributed targets:

| Layer | Metric that matters | Must prove before advancing |
|---|---|---|
| Capture (P1) | **recall** vs V1 + the ~7 missing | no data lost; missing cells found or marked `source_insufficient` |
| Statement (P3) | **wrong-statement rate** (8 basis + 13 analysis) | → **~0** in isolation |
| Scale (P3) | **scale-error rate** (14) | → **0/governed**; mixed-scale (OCF) correct |
| Entity (P4) | **investee-contamination rate** (6) | → **0** in isolation |
| Selection (P5) | **S1 rate** vs thresholds 1.0.0 (Wilson CI upper ≤0.5% on baseline); **regression count** | within bands; **zero regression** on V1-correct cells |

**Go/no-go for cutover (P7):** full V2 CV1 re-run = **certified or conditional** (not NOT_CERTIFIED); wrong-statement + investee → ~0; scale governed; **zero regression** on the cells V1 got right (the 4 confirmed OCF + any others); downstream revalidation passes.

---

## 5. Migration Strategy — Option B (Task 5)

**Comparison methodology:** run frozen V1 and parallel V2 on the **same pinned bundles**; cell-by-cell diff against the CV1 truth set, classifying each cell as `V2-fixes-V1-error` / `V2-matches-V1-correct` / `V2-regresses` / `both-wrong`. The `V2-regresses` set must be **empty** to cut over.

**Cutover criteria:** V2 CV1 disposition certified/conditional **AND** wrong-statement + investee → ~0 **AND** scale governed **AND** zero `V2-regresses` **AND** downstream revalidation (FVE/Query) passes.

**Rollback criteria:** any regression on V1-correct baseline cells, OR V2 CV1 below threshold, OR downstream revalidation fails → **flip to frozen V1** (retained through a stability window before retirement).

---

## 6. Downstream Revalidation (Task 6) — *revalidation, not redesign*

| Engine | Action | Expectation |
|---|---|---|
| **MSIL** | Re-ingest the improved bundle; confirm `entity_scope` consumed as additive | Contract unchanged; corroboration/divergence recomputed on cleaner values |
| **FVE** | Re-run HSIG on V2 baselines; confirm NAG roles unchanged | **More `clean`** — the 27+14 that drove `baseline_not_validatable` are gone; verdicts shift *beneficially*; re-validate, don't rework |
| **QAE** | Re-ingest; `entity_scope` curbs investee-narrative contamination | Contract unchanged |
| **Query** | Re-validate citations + answers | Citations now point to the **right** value; answer-correctness re-checked |

No contract changes anywhere; the cost is re-validation effort, concentrated in FVE baselines and Query answers.

---

## 7. Hidden Risks (Task 7)

| Risk | Mitigation |
|---|---|
| **Entity contamination (top)** | Capture-first surfaces *more* LASHL/NutriCo → issuer-only eligibility + MSIL-bound gate is mandatory; validated against the 6 in P4 isolation |
| **Candidate explosion** | Bounded capture + provenance-keyed dedup; registry append-only; monitor candidates-per-metric |
| **Scale drift** | Header-only source scale; magnitude-inference prohibited; mixed-scale carried per-candidate; conflicts surfaced not picked |
| **Selection regressions** | Parallel comparison requires empty `V2-regresses` before cutover |
| **Workbook growth** | Candidates in the `.kb.json` sidecar, **not** the `.xlsx`; human workbook stays canonical-only |
| **Performance** | Capture-first is heavier (more candidates persisted); V1 serving during build absorbs latency; optimize only if a measured gate fails |

---

## 8. Overengineering Risks — do NOT build yet (Task 8)

- **LLM-based extraction** — not needed; CV1 shows 0% metric-concept errors and 85% of values already captured. Capture is a structured-table problem, not a comprehension problem.
- **Advanced / ML ranking of candidates** — **contrary to the by-construction guarantee.** The contracts guarantee correctness via *deterministic eligibility gating* ("impossible"); a learned ranker reintroduces *probabilistic preference* ("less likely"), regressing the core guarantee. Selection must stay deterministic and rule-based.
- **Cross-document selection** — out of scope; selection operates within one issuer bundle. Cross-document is MSIL/Query territory.
- **Learning / feedback systems** — no adaptive selection; rules are governed config, versioned, not learned.
- **Multi-issuer auto-generalization** — prove Lucky + Millat first; generalize post-MVP.
- **Confidence-scoring models / fuzzy entity resolution** — entity identity is MSIL's, deterministic; do not build a competing probabilistic resolver in OCR.

**Principle:** anything that converts a structural bar into a score is not just premature — it is a correctness regression.

---

## 9. Freeze Criteria (Task 9)

OCR V2 is freeze-ready when **all** hold:
1. All P0–P6 phase gates passed.
2. Full V2 CV1 re-run = **certified or conditional**.
3. Per-class targets met: wrong-statement (8+13) ~0, investee (6) = 0, scale (14) governed.
4. **Zero regression** on V1-correct cells (parallel comparison `V2-regresses` empty).
5. **Output-contract equivalence** to V1 confirmed (equivalence harness green).
6. Every §12 prohibited behavior **enforced and tested** (the failure modes are unrepresentable, not merely avoided).
7. Selection is **deterministic** — no learned/ML components.
8. Downstream revalidation (MSIL/FVE/QAE/Query) clean.
9. Version pins populated (contract/schema/governance/scale-target/registry/bundle/engine).
10. Stability window passed before V1 retirement.

---

## 10. Recommendation (Task 10)

**Implementation order:** P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7, with **per-layer isolated CV1 validation** (statement, scale, entity) before P5 integration, V1 frozen and serving throughout, cutover only at P7 on the oracle.

**Risk assessment: MEDIUM, fully reversible.** V2 is a real build (new registry + governance + selection), but each layer is validated against its own pre-attributed CV1 subset, V1 is the live fallback until cutover, and rollback is a switch. The dominant residual risk is **entity contamination + candidate explosion**, contained by the issuer-only MSIL-bound gate and bounded/deduped capture. The named anti-pattern (learned ranking) is excluded to protect the by-construction guarantee.

**Estimated correctness gain: LARGE and measured.** Eliminates the **27 statement-selection errors (56%)** and governs the **14 scale errors (29%)** → moves CV1 from **84.6% S1 / NOT_CERTIFIED toward certified**, leaving the **~7 genuine recall items** as the only residual — **~85% of failures resolved by architecture and deterministic governance, not by patching or scoring.**

**Classification:**
- **Must-Before:** MSIL entity identity; documented scale convention; declared basis (unconsolidated/Lucky); CV1 oracle ready; output-equivalence harness; contracts frozen.
- **During:** capture recall, dedup, analysis-table exclusion, candidate-explosion monitoring, downstream revalidation.
- **Post:** candidate drill-down in Query, multi-issuer generalization, V1 retirement after stability window.

---

## 11. One-Paragraph Verdict

The safest path from V1 to V2 is not a leap but a sequence of independently-provable increments, and the CV1 truth set is what makes that possible: because every failure is already attributed to a class — 27 statement, 14 scale, ~7 recall — each governance layer can be built behind a frozen, still-serving V1 and validated against its own subset before anything integrates, so statement governance is proven to erase the 8 basis and 13 analysis-table errors, entity governance to erase the 6 investee errors, and scale governance to erase the 14 corruptions, each measured in isolation against the oracle rather than hoped for end-to-end. Selection then integrates these as deterministic eligibility gates — never a learned ranker, which would trade the by-construction guarantee back for mere likelihood — and emits a canonical value shape-identical to V1's, so the frozen platform is preserved and MSIL/FVE/QAE/Query face revalidation, not redesign. Build P0 through P6 with per-layer CV1 gates, hold V1 as the live fallback, cut over at P7 only on a certified/conditional re-run with an empty regression set, and OCR V2 captures roughly 85% of the correctness deficit at medium, fully reversible risk — turning CV1's catalogue of failures into a checklist of outcomes that are now impossible by construction.
