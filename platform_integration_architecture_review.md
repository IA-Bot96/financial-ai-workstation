# Platform Integration Architecture Review — MSIL ↔ Engines

**Status:** Pre-implementation integration architecture. No code, no implementation detail. Contracts, ownership, authority, provenance, evidence flow, sequencing, maintainability.
**Date:** 2026-06-02
**Scope:** OCR · Query · FVE · QAE (frozen) + MSIL (substrate, real-bundle validated) + FVE Phase 11 (NAG / NumericEvidence / Numeric Admission Policy; HSIG unchanged).
**Constraint honored:** no redesign of frozen engines; only additive consumption contracts.

---

## 1. Platform Re-Evaluation — What MSIL Is (Task 1)

**MSIL is the platform's canonical Evidence Layer** — a *system of record for cross-source evidence and identity/authority/provenance*. It is not the others:
- **Not orchestration** — it does not drive or sequence the engines; engines pull from it.
- **Not raw data** — it resolves entities, assigns authority, attaches immutable provenance, orders time, and computes corroboration/divergence; it adds governed semantics.
- **Not pure infrastructure** — it carries domain meaning (authority, divergence, supersession).
- **It is the evidence layer**: passive-producer, authoritative on *substrate* concerns (identity, authority, provenance, time, corroboration, divergence-detection), and sovereign-deferring on *domain* conclusions (numbers→FVE, themes→QAE, answers→Query).

**Revised platform shape:**
```
Sources (PDF, PSX, SECP, Payouts, …) ─▶ OCR + MSIL source adapters ─▶ MSIL (Evidence Layer)
                                                                          │
                              ┌───────────────────────────┬──────────────┴───────────────┐
                              ▼                            ▼                               ▼
                        Query Engine                     QAE                              FVE
                     (retrieve + cite)            (narrative themes)         (numeric validation + forecast)
                              └────────────── all consume ONE registry / authority matrix / provenance / timeline ──────────┘
```
The architectural payoff: the three engines stop each re-deriving identity/authority/provenance and converge on **one canonical substrate**. OCR becomes a *source feeding MSIL* (the `annual_report` adapter), not a parallel evidence path.

**Long-term maintainability finding (important):** for the MVP, engines keep their existing OCR-single-source path **and** additively consume MSIL — acceptable because it is non-breaking. But a permanent **dual evidence path** (OCR-direct + MSIL) is a maintainability hazard; post-MVP the OCR path should converge to "MSIL `annual_report` source" so there is **one** evidence layer, not two. Flag now, converge later.

---

## 2. MSIL → Query Engine Integration (Task 2)

| Aspect | Definition |
|---|---|
| **Query consumes** | The unified evidence store: IntelligenceSignals (all content classes) + timeline + provenance + entity index, for cross-source retrieval. |
| **Query-owned** | Query planning, retrieval ranking, answer generation, deterministic Q&A logic, and its existing OCR workbook-cell citations. Query owns "what value/what the source says." |
| **Retrieval boundary** | Query **retrieves** MSIL evidence; it never resolves entities, normalizes, or assigns authority. It may filter/rank by authority but does not set it. |
| **Citation ownership** | **MSIL owns provenance** (immutable source ref + snapshot); **Query owns citation rendering**, built only from MSIL provenance. No invented citations, no false precision. |
| **Authority handling** | Query **displays** claim-type-scoped authority and may rank by it; it never recomputes or overrides the authority matrix. An answer carries its evidence's authority ("per SECP…" vs "per analyst…"). |
| **Divergence handling** | Query **surfaces** divergence (both sides, authority-weighted); it **never resolves** it. An answer on a divergent fact presents the divergence, never silently picks a side. |
| **Provenance requirement** | Every retrieved item carries MSIL provenance; no un-provenanced answer; quarantined/unresolved-entity evidence is **not retrievable as attributed**. |

---

## 3. MSIL → QAE Integration (Task 3)

| Aspect | Definition |
|---|---|
| **Signals QAE may consume** | `narrative_claim` signals + corroboration + (narrative) divergence + coverage caveats + corporate-event narrative context. **Not** `numeric_claim` as fact. |
| **Narrative vs numeric boundary** | A number inside a narrative is *context*, not a validated value. QAE may report "the narrative claims revenue grew" but must not assert the figure — that routes to FVE. Hard boundary. |
| **Theme creation rules** | QAE's frozen rules stand: themes from admitted narrative signals; market/overview **never create**; analyst/sector creations **quarantined** as opinion/sector. MSIL supplies source/authority tags; **QAE owns taxonomy + theme assembly**. |
| **Corroboration usage** | QAE uses MSIL-computed independent-origin corroboration to strengthen theme salience/confidence; QAE does **not** recompute corroboration (circularity already defended in MSIL). |
| **Divergence usage** | QAE surfaces narrative-vs-narrative divergence (management vs analyst vs market); never resolves. Numeric divergences belong to FVE; QAE may reference them as context. |
| **Authority influence** | Source authority **caps/weights** theme confidence (analyst opinion ceilinged below audited fact). MSIL provides authority; QAE applies it within its confidence model. |
| **Coverage implications** | Multi-source **expands** coverage (announcements, SECP narrative) but **per-source coverage must be reported** — a theme covered only by low-authority/news is flagged; absence of a source ≠ absence of issue (the coverage-illusion rule). |

---

## 4. MSIL → FVE Integration (Task 4) — building on Phase 11

| Aspect | Definition |
|---|---|
| **NumericEvidence ownership** | **FVE owns** NumericEvidence (role-tagged boundary envelope). MSIL produces `numeric_claim`; FVE's NAG wraps it with role + integrity verdict + provenance + divergence refs. |
| **NAG ownership** | **FVE owns** the Numeric Admission Gate — routes by role; delegates OCR-historical numbers to HSIG. |
| **HSIG ownership** | **FVE owns** HSIG, **unchanged**, sole authority for OCR-historical baselines. |
| **Supporting-evidence usage** | Payout/announcement/SECP numbers enter as supporting/event/re-validation-trigger NumericEvidence — **never baseline**; may adjust confidence or surface divergence. |
| **Forecast-context usage** | Analyst expectations + management guidance = **non-authoritative forecast-context benchmarks** for future plausibility rules; never historical, never baseline. |
| **Baseline authority rules** | Only audited + HSIG-passed = baseline. Analyst never baseline; unaudited issuer never overrides audited; superseded never baseline; conflicts → divergence/review, never auto-pick. |
| **Future plausibility-rule usage** | Compare a submitted forecast against baseline (HSIG) + analyst consensus + guidance (forecast-context) — non-authoritative, mirroring QAE's narrative-support pattern. |

---

## 5. Cross-Engine Ownership (Task 5) — single authority per concept

| Concept | Single Authority |
|---|---|
| Entity resolution | **MSIL** |
| Authority assignment | **MSIL** (authority matrix) |
| Provenance | **MSIL** (immutable ref + snapshot) |
| Corroboration (computation) | **MSIL** (independent-origin) |
| Divergence **detection** | **MSIL** |
| Divergence **interpretation/adjudication** | **The owning domain engine** — FVE (numeric), QAE (narrative). **Never MSIL; never Query** (Query only surfaces). |
| Citation **provenance** / Citation **rendering** | **MSIL** owns provenance; the **consuming engine** renders the citation from it. |
| Numeric validation | **FVE** (NAG + HSIG) |
| Theme generation | **QAE** |
| Forecast plausibility | **FVE** |

One concept, one owner. No engine recomputes another's owned concept.

---

## 6. Prohibited Behaviors (Task 6)

- **QAE inventing numeric authority** — asserting a number as validated, or promoting a narrative figure to fact. (Numbers route to FVE.)
- **FVE creating or resolving entities** — must consume MSIL resolution; quarantined/unresolved entities never reach baseline.
- **Query resolving divergence** — Query surfaces only; it must never pick a side.
- **MSIL producing forecast/validation/theme conclusions** — it must stay substrate; it detects divergence but never interprets it, validates numbers, or assembles themes.
- **Any engine recomputing/overriding authority** — the authority matrix is MSIL's; engines apply, never redefine.
- **Any engine citing without MSIL provenance**, inventing citations, or claiming precision the provenance lacks.
- **Any engine consuming quarantined/unresolved-entity evidence as attributed.**
- **FVE admitting a non-OCR number as baseline** — only audited + HSIG-passed; analyst/issuer-unaudited/superseded barred from baseline.
- **QAE creating themes from market/overview signals**, or promoting analyst/sector opinion to issuer fact.
- **Any engine treating reference-only numerics as authoritative** (the MB-4 hazard).
- **MSIL auto-resolving divergence or selecting a winner.**
- **Cross-engine authority laundering** — FVE treating a QAE theme as a validated number, or QAE treating an FVE number as narrative fact. The split holds **both** directions.
- **Re-deriving corroboration independently** — engines consume MSIL's, to avoid duplicate/circular counting.

---

## 7. Hidden Integration Risks (Task 7)

- **Duplicated logic / authority drift.** Each engine re-implementing identity/authority/provenance → three divergent models. *Governance:* single MSIL ownership; engines consume, never re-derive (ties to the dual-evidence-path maintainability finding §1).
- **Conflicting authorities.** An engine's internal confidence contradicts MSIL authority. *Governance:* MSIL authority is substrate truth; engine confidence is domain-scoped and **composes under MSIL authority ceilings**, never above them.
- **Divergence feedback loops.** FVE/QAE emits a verdict that re-enters MSIL as new evidence and re-surfaces. *Governance:* divergence flows as a **DAG, not a cycle** — MSIL detects/surfaces → engine adjudicates and records a verdict → the verdict is *not* re-ingested as new divergence evidence.
- **Circular corroboration.** News echoes (MSIL MB-4/lineage) **and** cross-engine echoes (a QAE theme counted as corroborating the signal it came from). *Governance:* MSIL `source_lineage`; engines never feed conclusions back as evidence.
- **Stale evidence.** Superseded numbers/narratives consumed as current. *Governance:* MSIL supersession; consumers default to current; consumption contracts carry supersession state.
- **Source-lineage leakage.** Lineage must propagate to every consumed signal or dedup/circularity defenses fail downstream. *Governance:* lineage in every consumed signal (and the MB-4 dedup-keying fix).
- **Cross-engine confidence inflation.** QAE corroboration boosts a theme → FVE uses the theme as forecast-context and boosts its own confidence → loop. *Governance:* forecast-context is non-authoritative (cannot lift a baseline); confidence is **never multiplied across engine boundaries**; each engine's confidence is capped by MSIL authority.
- **Carried prerequisites:** MB-1 (entity sign-off) and MB-4 (divergence policy) are integration-blocking, not background.

---

## 8. Integration Sequencing (Task 8)

**Sequential, risk-ascending: Query → QAE → FVE. Not parallel.**

1. **Query first.** Lowest risk: it retrieves and cites, surfaces (not resolves) divergence, and validates/assembles nothing. It exercises the **shared evidence store + provenance + entity index + authority display** — the foundation all three share — on the safest consumer, and delivers immediate cross-source value. It hardens the consumption contract cheaply.
2. **QAE second.** Additive narrative consumption; QAE is frozen and **sees zero of the numeric-divergence noise** (per the real-bundle review), so it is insulated from MB-4. Medium risk; proves corroboration + narrative-divergence surfacing.
3. **FVE last.** Highest risk: numbers, baseline authority, NAG/HSIG, and the MB-4 divergence noise hits it directly; it depends on **MB-4 fixed + MB-1 signed-off + MB-3/Phase-11 gate**. Integrate after the evidence-store and divergence contracts are proven on the safer consumers.

**Not parallel:** parallel integration would wire three consumers against an unproven consumption contract and hit MB-1/MB-4 simultaneously across all of them — the opposite of the platform's "prove the substrate on the safest path first" discipline.

---

## 9. Findings Classification (Task 9)

**Must Resolve Before Integration**
- **MB-1 — entity-resolution analyst sign-off + general ambiguity rule.** All three engines bind to entities; wrong-entity evidence poisons everything.
- **MB-4 — MSIL divergence-policy fix.** Query and FVE both consume divergence; reference-only numeric noise must be excluded first.
- **Single-ownership contracts ratified** (the §5 table) — engines agree MSIL owns identity/authority/provenance/corroboration/divergence-detection before any wiring.
- **Prohibited-behaviors guardrails + the divergence-DAG-not-cycle rule** encoded in the consumption contracts.
- **Additive, versioned consumption contracts confirmed** non-breaking for the frozen engines.

**Can Resolve During Integration**
- Per-source coverage reporting in each consumer.
- Citation-rendering specifics per engine.
- Confidence composition under MSIL authority ceilings.
- Supporting-evidence usage tuning (FVE/QAE).

**Post-MVP**
- Market / Futures / News / Analyst / Sector source onboarding (deferred).
- Forecast plausibility vs consensus (FVE future).
- Numeric-reference → canonical-metric grounding.
- Convergence of the OCR-direct path onto MSIL as the single evidence layer (the maintainability finding).
- Non-manufacturer generalization.

---

## 10. One-Paragraph Verdict

With MSIL present, the platform resolves into a clean layered shape: **MSIL is the canonical evidence layer** — the single owner of entity identity, authority, provenance, time, corroboration, and divergence-detection — feeding three sovereign analysis engines that own their conclusions and nothing of the substrate (Query retrieves and cites, QAE assembles themes, FVE validates numbers and forecasts). The integration is governed by one rule per concept (the §5 ownership table) and one cardinal prohibition: **no engine recomputes another's owned concept, and no engine resolves a divergence MSIL only surfaces** — numbers stay gated to FVE, themes to QAE, answers to Query, identity and authority to MSIL, in both directions. Sequence it Query → QAE → FVE so the shared evidence contract hardens on the lowest-risk consumer before the numeric/baseline path that depends on the still-open divergence-policy fix and entity-resolution sign-off; keep every consumption contract additive so no frozen engine is destabilized; and treat the temporary OCR-direct-plus-MSIL dual path as a maintainability debt to retire post-MVP by converging on MSIL as the one evidence layer. Done this way, the multi-source platform gains breadth without surrendering the discipline that carried every prior freeze — resolve identity before trusting evidence, gate numbers before believing them, snapshot provenance before citing it, surface divergence without resolving it, and never let coverage be mistaken for correctness or source abundance for source authority.
