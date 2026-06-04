# OCR V1 → V2 Migration Review

**Status:** Migration strategy & risk analysis. No code, no implementation, no prompt design. No redesign of MSIL/FVE/QAE/Query. Frozen platform contracts preserved. OCR correctness is the priority.
**Date:** 2026-06-03
**Primary evidence:** the executed CV1 OCR extraction-correctness audit (Lucky, unconsolidated basis).
**Target state:** the completed OCR V2 capture-first architecture specification.

---

## 0. The Central Question, Answered First

**Can OCR V2 be introduced incrementally while preserving the frozen platform, or does correctness require a clean replacement of OCR V1?**

**Both — at different layers:**
- **At the platform boundary: incremental / preserving.** V2 keeps the **single-canonical-value output contract** (one value per metric/year + provenance in the `.kb.json`/workbook). Therefore **MSIL, FVE, QAE, and Query need no redesign.** The platform is preserved *by construction*.
- **Inside OCR: replacement, not evolution.** V1's dominant flaw — **canonical selection performed *during* extraction** — is **structural**, and **85% of CV1 errors occur *after* the right value was already found**. You cannot patch selection into a V1 that has no candidate representation; the selection logic must be **replaced**, not amended.
- **Delivered via: parallel build + validated staged cutover (Option B), reaching the capture-first (Path C) end-state.** Not in-place evolution of V1 (Option A — impossible without building V2's front-end anyway), and not big-bang retirement (Option C as a *path* — reckless given unproven V2 extraction recall).

**Net: incremental at the platform, clean replacement inside OCR, executed parallel-and-staged.**

---

## 1. Reconstructing OCR V1 (Task 1)

**Architecture (monolithic, fused):** detect tables → classify → extract values → normalize (label→canonical, scale inline) → **select canonical value** → consolidate (resolve duplicates, raise on conflict, **discard losers**) → populate workbook. Selection happens *inside* this opaque flow.

**Workbook generation flow:** consolidated `MetricValue`s → `WorkbookPopulationService` → one cell per (metric, year) + `WorkbookCellMapping`.

**Canonical metric generation flow:** extraction emits candidate values; normalization maps source label → canonical metric; consolidation picks **one** value per (metric, value_year) with partial source-class precedence and **no representation of basis, entity scope, source type, or scale**; competing candidates are **discarded**.

**Downstream consumers:** the `.xlsx` (human) and `.kb.json` (`FinancialYearConsolidationResult` + `InsightsExtractionResult`) consumed by **MSIL** (annual_report source), **FVE** (HSIG baselines), **QAE** (insights/narrative), **Query** (retrieval/citation).

**Embedded V1 assumptions:** (a) a canonical value is selectable *during* extraction; (b) source-label→canonical mapping is sufficient; (c) losing candidates are disposable; (d) scale is handled inline with no explicit representation; (e) "primary" precedence is partial, with **no basis (consolidated/unconsolidated) and no entity_scope (issuer/investee) dimension.**

**Assumptions that CONFLICT with V2:** all five — V2 **defers** selection, **persists** all candidates, makes **basis / entity_scope / source_type / scale first-class**, and makes selection a **separate, governed, auditable** layer.

---

## 2. Reconstructing OCR V2 (Task 2)

**Capture-first pipeline:** `PDF → fact candidates → candidate registry → governed canonical selection → workbook`.

- **Candidate capture** — every plausible fact as `(value, year, page, table, statement_type, entity_scope, unit, scale, label, provenance)`; captures **presence, not authority**.
- **Candidate registry** — persists + dedups candidates with full provenance; the auditable store of everything found (losers retained).
- **Statement governance** — basis (consolidated/unconsolidated) + source-type (primary-statement / note / analysis-table) precedence.
- **Entity governance** — issuer vs investee (LASHL JV, NutriCo associate); **issuer-default**; MSIL owns entity identity, selection enforces issuer-only.
- **Scale governance** — explicit unit/scale per candidate; governed normalization to a documented target; auditable.
- **Canonical selection layer** — chooses **one** canonical value per metric/year from the registry, applying statement/entity/scale governance + precedence, **recording the rationale and the losing candidates**.

**Architectural difference from V1:** capture-first (not select-first), candidates persisted (not discarded), basis/entity/source/scale first-class (not absent), selection separate+auditable (not fused) — **same single-canonical output contract.**

---

## 3. Gap Analysis (Task 3)

| Component | V1 | V2 | Migration difficulty |
|---|---|---|---|
| **Extraction** | fused detect+classify+extract+select | capture-only (candidates) | **Medium** — re-scope to capture; recall work |
| **Scale handling** | inline normalization, no representation | explicit per-candidate unit/scale + scale governance | **Medium** |
| **Statement classification** | partial `table_type`, **no basis** | basis (cons/uncons) + source-type governance | **High** — new dimension |
| **Entity scope** | **absent** | first-class `entity_scope` + issuer-default | **High** — new dimension; LASHL/NutriCo contamination |
| **Provenance** | partial (page/table) | full per-candidate provenance + registry | **Medium** |
| **Candidate registry** | none (losers discarded) | persistent dedup registry | **High** — new component |
| **Canonical selection** | fused into consolidation, opaque | separate governed auditable layer | **High** — the core change |
| **Workbook generation** | from consolidated values | from canonical-selected values | **Low** — contract unchanged |
| **Metric registry integration** | label→canonical inline | reused in selection layer | **Low** — reuse |
| **Downstream `.kb.json`** | `FinancialYearConsolidationResult` | same shape (one canonical value + provenance) | **Low** — contract preserved |

The high-difficulty items (statement basis, entity scope, registry, selection layer) are exactly the **dimensions whose absence caused the 27 selection failures** — they are new *because* V1 never represented them.

---

## 4. Migration Options (Task 4)

| Option | Complexity | Risk | Validation burden | Disruption | Rollback |
|---|---|---|---|---|---|
| **A — Incremental in-place** (add capture → add registry → replace selection on live V1) | Medium-high | **High** — mutating the live engine; "add capture" to a no-candidate V1 = building V2's front-end anyway; re-runs the expensive pipeline | Continuous; regressions hard to attribute | High | **Poor** (V1 mutated) |
| **B — Parallel V2** (build V2 alongside frozen V1 → compare → staged cutover) | Medium-high | **Low** — V1 stays frozen & serving; V2 validated against CV1 truth pre-cutover | Clean — A/B vs CV1 oracle | Low until cutover | **Excellent** (flip back to V1) |
| **C — Full replacement** (retire V1 → build V2) | High | **High** — no fallback; big-bang; V2 extraction recall unproven | Clean oracle but no safety net | High | **None** (V1 retired) |

**A rejected:** V1's flaw is structural — you cannot bolt candidate capture/registry/deferred-selection onto a fused select-during-extraction engine without effectively building V2, and doing it in-place forfeits rollback and risks regressing the cells V1 gets right.
**C rejected as a *path*** (it is the *end-state*): retiring V1 first removes the safety net while V2's genuine extraction-recall (~7 cells) is unproven.
**B recommended:** reaches the capture-first end-state with V1 as a frozen fallback and the CV1 truth set as the cutover oracle.

---

## 5. Downstream Compatibility (Task 5)

V2 preserves the single-canonical-value contract, so **no contract changes** — but values **improve**, so **re-validation** (not redesign) is required.

| Engine | Contract unchanged? | New information available | Migration risk |
|---|---|---|---|
| **MSIL** | ✅ (annual_report source still emits canonical value + provenance) | `entity_scope` (issuer/investee) reinforces MSIL entity governance | None to the contract; re-ingest the improved bundle |
| **FVE** | ✅ (HSIG baselines from canonical values) | Cleaner baselines — the 27 selection + 14 scale errors that drove `baseline_not_validatable` are eliminated/governed | **FVE re-validation needed** — HSIG verdicts shift (far more `clean`); a *beneficial* change, but must be re-run |
| **QAE** | ✅ (narrative path largely separate) | `entity_scope` can curb investee-narrative contamination | Minimal; re-ingest |
| **Query** | ✅ (canonical value + provenance for citation) | Candidate provenance enables future "why this value" drill-down | Citations now point to the *right* value; re-validate answers |

**Frozen contracts preserved.** The migration's downstream cost is **re-validation** (especially FVE baselines and Query answers), not contract rework.

---

## 6. Workbook Strategy (Task 6)

| Option | Tradeoff |
|---|---|
| A — canonical only | Preserves contract + human deliverable; loses the audit trail V2 enables |
| B — candidates only | **Breaks the contract** (downstream expects one value) — rejected |
| C — candidates + canonical | Preserves contract (canonical consumed) + adds auditability; risks workbook growth |

**Recommendation — "C, layered":** the **`.xlsx` carries canonical values only** (human deliverable + frozen contract unchanged, no growth); the **`.kb.json` sidecar carries canonical values + the candidate registry + losing candidates + selection rationale** (machine + audit consume). This preserves the consumed contract exactly, adds full auditability where it belongs (the sidecar), and avoids bloating the human workbook — enabling post-MVP drill-down without any platform change.

---

## 7. Validation Strategy (Task 7)

**The CV1 truth set is the migration oracle** — V2 success = re-running CV1 against V2 output and clearing the failures the truth set documents.

| Validation | Target (from CV1 evidence) |
|---|---|
| **Statement-selection** | The 27 wrong-statement errors (8 cons/uncons, 13 analysis-table, 6 investee) → correct statement selected → wrong-statement rate **~0** |
| **Entity-selection** | The 6 issuer-vs-investee (LASHL/NutriCo) → issuer selected → **investee-contamination = 0** |
| **Scale** | The 14 scale-corruption errors → governed normalization → scale-error rate within band; OCF 2020–2023 (millions) handled |
| **Extraction-recall** | The ~7 genuine find/read failures (4 missing EPS + 3 absent/structural) → V2 capture must find what exists; flag truly-absent as `source_insufficient` |

**Go/No-Go for cutover (M3):**
- Re-running CV1 on V2 achieves **S1 within `thresholds_version 1.0.0` bands** (S1 near-zero on baseline metrics) → CV1 disposition **certified or conditional** (not NOT_CERTIFIED).
- Wrong-statement + investee selection → **~0**; scale errors governed/auditable.
- **No regression** on the cells V1 got right (the 4 confirmed OCF cells + any others).
- Downstream re-validation (FVE/Query) passes against the improved bundle.

---

## 8. Hidden Risks (Task 8)

- **Investee contamination + candidate explosion (top risk).** Capture-first surfaces *more* LASHL/NutriCo figures; without strict `entity_scope` + issuer-default governance, V2 could make contamination *worse*. **Mandatory:** issuer-default selection, MSIL-owned entity identity, bounded capture, dedup.
- **Duplicate facts.** Same value across tables/pages → dedup by (metric, year, value, provenance).
- **Scale drift.** Mixed-scale candidates (thousands/millions/full; OCF-in-millions is a real case) → strict per-candidate scale + governed normalization, never inferred from magnitude.
- **Provenance dilution.** Many candidates → keep provenance precise per candidate; never average.
- **Migration regressions.** V2 might break V1's correct cells → the parallel A/B comparison (Option B) catches this *before* cutover.
- **Downstream incompatibility.** Values shift (improve) → re-validation burden, not contract break.
- **Workbook growth.** Mitigated by keeping candidates in the sidecar, not the `.xlsx` (§6).
- **Validation complexity.** Governing selection across basis/entity/scale/source is intricate → stage validation per governance dimension against the CV1 oracle.

---

## 9. Sequencing (Task 9)

| Phase | Scope | Prerequisites | Output | Validation gate | Rollback |
|---|---|---|---|---|---|
| **M0 — Foundations** | Freeze V2 contracts (candidate schema, registry, governance rules, selection contract); **confirm V2 canonical output ≡ V1 output contract** | V2 spec + CV1 truth set + thresholds 1.0.0 | Frozen V2 contracts; platform-preservation confirmed | Contracts frozen; output-equivalence verified | n/a (no build) |
| **M1 — Candidate capture (parallel)** | Build capture-first front-end → registry, with statement_type/entity_scope/unit/scale/provenance; **V1 still serving** | M0 | Candidate registry for Lucky (+Millat) | Capture recall ≥ V1 extraction (no lost data); candidates carry all governance dimensions | Discard V2 path; V1 untouched |
| **M2 — Governed selection (parallel)** | Build statement/entity/scale governance + selection layer → V2 canonical values | M1 | V2 canonical values (parallel to V1) | V2 vs CV1 truth: wrong-statement + investee → ~0; scale governed; S1 in band; **no regression on V1-correct cells** | V1 still primary |
| **M3 — Comparison + staged cutover** | Run V1 ‖ V2; compare; cut over to V2 when it passes CV1 at certified/conditional and beats V1 with no regressions; sidecar carries candidates | M2 | V2 is canonical OCR; `.kb.json` from V2 | CV1 re-run = certified/conditional; downstream (FVE/Query) re-validation passes | **Flip back to frozen V1** |
| **M4 — Downstream re-validation + V1 retirement** | Re-validate FVE baselines, Query answers, QAE against V2; confirm frozen contracts hold; retire V1 after a stability window | M3 | V2 sole OCR; V1 archived | Downstream re-validation clean; stability window passed | V1 archived (recoverable) until window closes |

---

## 10. Recommendation (Task 10)

**Recommended path: Option B — parallel build + validated staged cutover — reaching the Path-C capture-first end-state.**

**Rationale.** CV1 proved the failure is **selection + normalization, not extraction** (85% of wrong values already existed in the PDF; 0% metric-concept errors), and that the cause is V1's **selection-during-extraction** — a structural flaw no in-place patch (A) can fix. A big-bang replacement (C as a path) is reckless while V2's extraction recall is unproven. Parallel build (B) keeps V1 frozen and serving, validates V2 against the **CV1 truth oracle** before any cutover, and offers clean rollback — while preserving every frozen platform contract *by construction* (V2 output ≡ V1 output).

**Estimated implementation risk: MEDIUM.** V2 is a genuine build (new registry + governance + selection layer), but staged, validated, and reversible; the dominant residual risk is **investee contamination + candidate explosion**, governed by strict `entity_scope`/issuer-default.

**Estimated correctness gain: LARGE and measured.** Eliminates the **27 selection errors (56%)** outright, converts the **14 scale errors (29%)** to governed/auditable → moves CV1 from **84.6% S1 / NOT_CERTIFIED** toward **certified**, leaving ~7 genuine extraction-recall items — i.e., **~85% of failures resolved by architecture, not patching.**

**Classification:**
- **Must-Before:** freeze V2 contracts + confirm output-contract equivalence (platform preservation); CV1 truth set as oracle (done); define basis / entity-scope / scale governance; **document the OCR stored-value scale convention** (carried from CV1); confirm **MSIL ownership of issuer-vs-investee identity**.
- **During Migration:** extraction recall, dedup, analysis-table exclusion, candidate-explosion/investee governance, downstream re-validation (FVE/Query).
- **Post-Migration:** candidate drill-down in Query, cross-issuer generalization, V1 retirement after the stability window.

---

## 11. One-Paragraph Verdict

CV1 settled the question that drives this migration: OCR V1's problem is not that it cannot read the document — 85% of its wrong values already exist in the PDF and none are metric-concept errors — but that it **chooses the wrong candidate**, picking consolidated over unconsolidated, investee over issuer, and analysis-percentages over value lines, then corrupting scale, all inside a fused select-during-extraction step that discards the evidence of its own mistake. That flaw is structural, so the answer is not to patch V1 (Option A) but to **replace its selection internally** with the capture-first V2 — and because V2 keeps the single-canonical-value output contract, the **frozen platform is preserved by construction**, making MSIL/FVE/QAE/Query a re-validation exercise, never a redesign. The safe road to that end-state is **parallel build with a validated, reversible, staged cutover (Option B)**: stand V2 up beside a frozen V1, prove against the CV1 truth oracle that it drives wrong-statement and investee selection to zero and governs scale without regressing the cells V1 got right, keep candidates in the sidecar for auditability while the human workbook stays canonical-only, and cut over only on a certified/conditional CV1 re-run — capturing roughly 85% of the correctness gain through architecture, at medium and fully reversible risk, without changing a single downstream contract.
