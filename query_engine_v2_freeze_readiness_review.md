# Query Engine v2 — Freeze Readiness Review

**Status:** Freeze evaluation of Query v2 as built (P0–P7 complete; P8 is this review). No code, no redesign. Architecture/contract/ownership fidelity, real-bundle behavior, trust guarantees, risks, recommendation.
**Date:** 2026-06-03
**Evidence:** P0–P6 phase reports + `query_v2_real_bundle_audit.json` + `query_v2_real_bundle_validation_report.json` (bundle `97c3123…`, `validation_passed: true`).

---

## 0. Headline & Result Snapshot

| Metric | Result |
|---|---|
| Queries executed | 10 (all 8 intents + `ambiguous` + `unsupported`) |
| Intent / status matches | **10/10 / 10/10**, 0 failed expectations |
| Claims generated / cited / dropped | 40 / **40** / 0 (**100% citation coverage**) |
| Authority coverage | **100%** |
| Metric integrity-status coverage | **100%** |
| Anomalies (citation / authority / confidence / divergence) | **0 / 0 / 0 / 0** |
| Confidence ceilings observed | 0.55–0.8, **no inflation** |
| Off-ramps exercised | 1 `NEEDS_CLARIFICATION`, 1 `UNSUPPORTED_INTENT`, 0 `INSUFFICIENT_EVIDENCE` |
| Ownership-boundary booleans | **9/9 correct** (re-derives nothing) |
| Platform invariants | **8/8 hold** |

**Headline:** Query v2 is the **cleanest engine freeze in the platform** — every contract invariant holds on the real bundle, every claim is cited, every number carries its FVE integrity status, authority is displayed-not-recomputed, divergence is surfaced-not-resolved, confidence is bounded-not-inflated, and **Query re-derives nothing.** It has **no Query-specific blocker.** Its limitations are the platform's familiar boundary — single-source validation, curated queries, no answer-correctness truth set — making it **READY_WITH_LIMITATIONS**, conditioned only on the carried platform item (MB-1) and an honest scope statement.

---

## 1. Architecture Fidelity (Task 1) — HIGH

The full v2 lifecycle is implemented and behaves as designed: intent → plan → request → bundle → rank → assemble → cite → present. Deterministic-first held (rule-based intent/planning/ranking; no generative answering; `llm_logic` in `prohibited_changes`). Federate-never-re-derive held (Query consumes MSIL/QAE/FVE as authored). Evidence-or-silence held (`NEEDS_CLARIFICATION` and `UNSUPPORTED_INTENT` fired correctly; insufficiency off-ramp present though not triggered on this set).

---

## 2. Contract Fidelity (Task 2) — HIGH

Every contract invariant is observed on the real bundle:
- **QueryIntent:** deterministic classification, 10/10 intent matches; ambiguous → clarify; unsupported → refused.
- **RetrievalPlan:** 2–4 auditable steps per query; **metric/forecast/comparison plans carry FVE integrity** (`integrity_status_present: true` for those).
- **EvidenceBundle/RankedEvidence:** as-authored; exclusion works (e.g. metric ranked 2→included 1; comparison 8→5; forecast 7→4).
- **AnswerAssemblyContext/QueryResponse:** every claim grounded; bounded confidence; correct `status` per query.
- **Citation:** 40/40 cited, 0 dropped, 0 anomalies, no synthetic citations.
- **Divergence/Authority:** surfaced-never-resolved; authority displayed + attributed; 0 anomalies.
- **Version pins** present per response.

---

## 3. Ownership-Boundary Compliance (Task 3) — PERFECT

The validation report's nine boolean checks are all correct:

| Concept | Owner | Query behavior |
|---|---|---|
| **MSIL authority** | MSIL | `query_assigns_authority: false` — displayed, not assigned ✓ |
| **MSIL divergence** | MSIL detect / engine interpret | `query_recomputes_divergence: false`, `query_resolves_divergence: false` ✓ |
| **MSIL corroboration / timeline / entities** | MSIL | `recomputes_corroboration / recomputes_timeline / resolves_entities: false` ✓ |
| **FVE integrity** | FVE | metric/forecast answers carry FVE integrity status; Query displays it (e.g. `validation_status:WARNING`, `SKIPPED_BASELINE_NOT_VALIDATABLE`), never computes it ✓ |
| **QAE themes** | QAE | `qualitative_analysis` consumed QAE conclusions, not re-assembled ✓ |
| **Citations / ranking policy** | MSIL provenance / frozen policy | `generates_synthetic_msil_citations: false`, `changes_retrieval_ranking_policy: false`, `preserves_existing_workbook_citations: true` ✓ |

Every owned concept stayed with its owner.

---

## 4. Real-Bundle Behavior (Task 4) — CLEAN

All 10 queries behaved correct-by-contract: 8 `ANSWERED` (each fully cited, authority-labeled, bounded), 1 `NEEDS_CLARIFICATION` (the bare-token "Tell me about Lucky" — correctly routed to clarification, the MSIL ambiguity case), 1 `UNSUPPORTED_INTENT` ("Write a poem about cement" — refused). Forecast/comparison answers correctly surfaced FVE's `SKIPPED_BASELINE_NOT_VALIDATABLE` and capped confidence at 0.55; the EPS metric carried FVE's `WARNING`. Zero regressions, zero anomalies.

---

## 5. Does Query Re-Derive Anything? (Task 5) — NO

**Provably not.** The nine ownership booleans + the `no_authority_recomputation` / `no_divergence_resolution` invariants confirm Query computes none of: entity resolution, authority assignment, corroboration, divergence detection/resolution, timeline, theme assembly, numeric validation, citation provenance, or ranking policy. It plans, ranks, assembles, and renders — and consumes everything else as authored. This is the cleanest expression of *federate-never-re-derive* in the platform.

---

## 6. User-Facing Trust Guarantees (Task 6) — ALL HOLD

- **Citation integrity:** 100% of shipped claims cited from MSIL provenance; 0 dropped-but-shown; no synthetic citations; existing workbook citations preserved.
- **Authority integrity:** 100% displayed, attributed per claim, never recomputed; low-authority-as-fact not observed (single-authority bundle, so the inversion is structurally untested — §7).
- **Divergence integrity:** surfaced-never-resolved; 0 surfaced on this single-source bundle (none to surface), contract path correct but **unexercised on real multi-source data**.
- **Confidence integrity:** bounded by weakest evidence + FVE status; no inflation (ceilings 0.55–0.8); driven down correctly where FVE flagged the baseline.

---

## 7. Remaining Risks (Task 7)

- **R-1 — Single-source validation.** All 363 evidence signals are annual-report (one authority class). Divergence presentation, corroboration, and cross-source authority ranking/inversion are **built and contract-correct but unexercised on real multi-source data.** The federated value proposition is not yet demonstrated end-to-end.
- **R-2 — Missing analyst/news/market sources.** `risk_analysis` `ANSWERED` from annual-report evidence alone — contract-valid but **coverage-thin** (no SECP/news/market risk inputs); risk of an answer reading as more complete than its sourcing (mitigated by bounded confidence + authority labels).
- **R-3 — Ranking limitations.** Deterministic ranking is barely exercised on single-authority/single-provenance-type data; authority-differentiated ranking is untested.
- **R-4 — Deterministic intent limitations.** 10/10 classification on a **curated** one-query-per-intent set; robustness on messy real-user phrasing is unproven (mechanism proven, not distribution).
- **R-5 — Retrieval-plan limitations.** Multi-source routing (announcements vs SECP vs payouts) is unexercised — only annual_report + QAE + FVE consulted.
- **R-6 — No answer-correctness truth set.** The audit proves **contract**-correctness (cited, attributed, bounded, status-correct), not **answer**-correctness (were the 6 claims explaining "operating profit decline" the *right* ones?). The recurring platform gap.
- **R-7 — MB-1 (carried).** Query binds answers to MSIL entities; a wrong entity fact → confidently-wrong cited answer. Platform-level open condition.

None is a Query-specific defect; all are the platform's familiar "contract-correct, real-world-unexercised" boundary.

---

## 8. Findings Classification (Task 8)

**Must Resolve Before Freeze**
- **MB-1 (carried platform blocker)** — entity-registry analyst sign-off; Query's entity-bound answers depend on it.
- **Honest scope statement published** — deterministic federated answering, contract-correct, single-source-validated; multi-source synthesis and answer correctness not yet certified.

**Should Resolve Before Freeze**
- **Bounded answer-correctness truth-set spot check** (the P8 freeze criterion) — convert "contract-correct" to "accepted answer-correctness" on a sample (mitigated meanwhile by mandatory citation + attribution).
- **Messy-query robustness check** — validate deterministic intent classification on a non-curated query sample (R-4).

**Post-Freeze**
- Multi-source validation (divergence/corroboration/authority-ranking) when real official-triad / analyst / news feeds land (R-1, R-3, R-5).
- `risk_analysis` full sourcing (SECP + market + news) (R-2).
- Convergence of the dual citation path (OCR-direct + MSIL) onto MSIL.

---

## 9. Determination (Task 9)

### READY_WITH_LIMITATIONS

**Justification.** Query v2 has **no engine-specific blocker**: on the real bundle, all 8 platform invariants hold, all 9 ownership booleans are correct, citation/authority/metric-integrity coverage is 100%, anomalies are zero, confidence is bounded, off-ramps are honest, and Query provably re-derives nothing. It is **not READY** unconditionally only because of the **carried platform condition (MB-1)** — its entity-bound answers inherit the unconfirmed-registry risk — and because its **multi-source value and answer correctness are unexercised/uncertified** (single-source bundle, curated queries, no truth set). It is **firmly not NOT_READY** — there is no defect, no leakage, no re-derivation. Therefore **READY_WITH_LIMITATIONS**, conditioned on MB-1 closing and an honest scope statement, with multi-source and correctness validation as accepted Should/Post-Freeze items. This mirrors the platform posture exactly: a deterministic, evidence-bound, citation-honest answering layer that is trustworthy by construction — not autonomous truth.

---

## 10. One-Paragraph Verdict

Query v2 is the cleanest freeze in the platform: ten queries across every intent answered correct-by-contract on the real Lucky bundle, forty of forty claims cited, every number carrying its FVE integrity status, authority displayed exactly as MSIL assigned it, divergence surfaced-never-resolved, confidence bounded-never-inflated, ambiguity routed to clarification and nonsense refused — and a nine-for-nine ownership ledger proving the engine resolves no entity, assigns no authority, computes no corroboration or divergence, validates no number, and assembles no theme. It federates and renders; it re-derives nothing. The honest caveats are the same ones every engine in this platform carries: the run was single-source so divergence, corroboration, and cross-source authority synthesis are built-and-correct but unexercised; the query set was curated so intent robustness on messy phrasing is unproven; and there is no answer-correctness truth set, so the engine is contract-correct rather than accuracy-certified. With **no Query-specific blocker**, it is **READY_WITH_LIMITATIONS** — freeze it once MB-1 closes and the scope is stated honestly, leaving multi-source and correctness validation to land as the real sources and a truth set arrive, and Query v2 stands as the usable, citeable, authority-honest, divergence-honest interface the platform was built to expose.
