# Query Engine v2 — Implementation Plan

**Status:** Implementation sequencing plan. No code. **All ten Query v2 contracts assumed frozen at P0.**
**Date:** 2026-06-03
**Sources:** `query_engine_v2_architecture.md`, `query_engine_v2_contracts.md`.
**Target:** the federated answering layer atop MSIL (evidence) + QAE (themes) + FVE (validation).

---

## 0. Sequencing Principles

1. **Contracts before logic** (P0) — freeze enums, contracts, version pins before any answering logic.
2. **Bottom-up the lifecycle, then enforce on top.** Build intent → plan → rank → assemble (P1–P4); then layer **citation, divergence, and authority enforcement** (P5–P6) onto the assembled answer — they police what assembly produces, so they follow it.
3. **Deterministic-first.** Intent, planning, ranking are rule-based and auditable; any LLM is a **thin rephraser over already-cited claims**, never a fact generator — kept minimal, not a phase.
4. **Federate, never re-derive.** Every phase consumes MSIL/QAE/FVE *as authored*; no phase recomputes entity, authority, theme, validation, or divergence resolution.
5. **Prove on real data before freeze** (P7) — the platform's invariant discipline; fixtures prove plumbing, the real Lucky bundle proves behavior.
6. **Build only what the available sources justify.** MVP intents run on annual report + official triad + QAE + FVE; analyst/sector/market/news are post-MVP, so `risk_analysis` is partial until they land — do not over-build it (the FVE-Phase-9 trap).
7. **MB-1 gates trust, not the build.** P0–P6 proceed against the proven resolution mechanism; MB-1 (entity sign-off) must close before P7/P8 *trust* Query output.

---

## 1. Phases (with audit gate, freeze criteria, exit)

| Phase | Scope | Depends on | Audit gate | Freeze criteria / exit |
|---|---|---|---|---|
| **P0 — Contracts** | Materialize + freeze the 10 contracts, enums, version-pin set | architecture/contracts docs | `query_v2_contract_integrity_audit.json` | Enums valid; version-pin set complete; ownership table consistent. **Nothing builds before this.** |
| **P1 — Intent Layer** | `QueryIntent`: deterministic `intent_type` classification + entity-mention extraction (resolved via MSIL); clarify/unsupported off-ramps | P0 + MSIL entity resolution | `query_v2_intent_audit.json` | Deterministic classification on a query set; ambiguity→clarify; entities resolved **by MSIL**, not Query. |
| **P2 — Retrieval Planning** | `RetrievalPlan` + `EvidenceRequest`: intent→auditable steps (`rule_id`), entity-resolved-first, **metric-always-includes-FVE**, request issuance | P1 + QAE/FVE consumption contracts | `query_v2_planning_audit.json` | Every step carries `rule_id`; resolved-entity-only requests; metric plans include FVE step; unsupported→no-plan. |
| **P3 — Evidence Ranking** | `EvidenceBundle` + `RankedEvidence`: retrieve *as-authored*; rank authority/recency/provenance-complete-first; exclude un-provenanced | P2 | `query_v2_ranking_audit.json` | Items unmodified (as-authored); provenance-complete-first; un-provenanced excluded; authority/corroboration **consumed, not recomputed**. |
| **P4 — Answer Assembly** | `AnswerAssemblyContext` + `QueryResponse`: ground every claim; bound confidence (`min`, no cross-engine multiply); status off-ramps | P3 | `query_v2_assembly_audit.json` | Every claim grounded; confidence bounded-not-inflated; `INSUFFICIENT_EVIDENCE`/`NEEDS_CLARIFICATION`/`UNSUPPORTED_INTENT` fire; domain conclusions as-authored. |
| **P5 — Citation Enforcement** | `CitationContract`: render only from MSIL provenance; drop on `NONE`; no false precision | P4 | `query_v2_citation_audit.json` | **100% of shipped claims cited**; `NONE`→claim dropped (never un-cited); precision ≤ provenance; no invented citations. |
| **P6 — Divergence & Authority Presentation** | `DivergencePresentationContract` + `AuthorityPresentationContract`: both sides + authority, surfaced-never-resolved, no equal-weighting; attribution mandatory; low-authority-never-as-fact | P4–P5 | `query_v2_divergence_authority_audit.json` | Divergence surfaced both-sides-authority-weighted, never resolved; authority displayed-not-recomputed; every claim attributed; low-authority not presented as fact. |
| **P7 — Real-Bundle Validation** | End-to-end on the real Lucky bundle (`97c3123…`): representative queries across supported intents; verify all contract invariants on real data | P0–P6 + MSIL real-bundle + **MB-1 (for trust)** | `query_v2_real_bundle_audit.json` | Representative query set answered correct-by-contract on real data; no re-derivation; no fabrication; insufficiency where evidence absent. |
| **P8 — Freeze Review** | Freeze evidence + answer-correctness truth-set spot check + decision | P7 + **MB-1 closed** | `query_v2_freeze_readiness_audit.json` | All freeze criteria met or limitations explicitly accepted. |

---

## 2. Per-Phase Detail (scope · audit · freeze)

**P0 — Contracts.** Freeze enums (`intent_type`, `target_domain`, `status`, `citation_type`, ranking signals), the 10 contracts, and the version-pin set. *Audit:* integrity (no enum gaps, version-pin completeness, ownership consistency). *Freeze:* integrity passes; nothing builds first.

**P1 — Intent Layer.** Deterministic `intent_type` classification + entity-mention extraction with **MSIL resolution referenced** (Query does not resolve). Multi-intent decomposition; clarify/unsupported off-ramps. *Audit:* classification on a representative query set; ambiguity→clarify rate; confirm entities resolved by MSIL. *Freeze:* deterministic, off-ramps work, no Query-side resolution.

**P2 — Retrieval Planning.** `RetrievalPlan` from intent via auditable `rule_id` rules; **entity-resolved-first**; the **metric-always-carries-FVE** rule; `EvidenceRequest` issuance (one domain each, resolved entity only). *Audit:* every step traceable to a rule; resolved-entity-only; metric→FVE present; unsupported→no-plan. *Freeze:* deterministic + auditable; metric-FVE enforced.

**P3 — Evidence Ranking.** Retrieve `EvidenceBundle`s from MSIL/QAE/FVE *as authored*; build `RankedEvidence` — authority-aware, recency-aware, provenance-complete-first; exclude un-provenanced with reason. *Audit:* items unmodified; provenance-complete-first; exclusions correct; authority/corroboration not recomputed. *Freeze:* deterministic ranking; consume-not-recompute.

**P4 — Answer Assembly.** Build `AnswerAssemblyContext` (ground every claim) → `QueryResponse`; **confidence ceiling = min(weakest evidence, MSIL authority ceiling)** — never multiplied across engines; status off-ramps first-class. *Audit:* no ungrounded claim; bounded confidence; off-ramps fire; domain conclusions as-authored. *Freeze:* grounding + bounded confidence + honest status.

**P5 — Citation Enforcement.** `CitationContract` rendering from MSIL provenance only; `NONE`→claim dropped; no false precision; workbook-cell only where a mapping exists. *Audit:* 100% claims cited; `NONE` handling; precision discipline; MSIL-only sourcing. *Freeze:* cite-every-claim; no-false-precision; no-invented-citation.

**P6 — Divergence & Authority Presentation.** `DivergencePresentation` (both sides + authority, surfaced-never-resolved, no equal-weighting; relay per-domain) + `AuthorityPresentation` (displayed-not-recomputed, attribution mandatory, low-authority-never-as-fact, forward-inversion respected). *Audit:* divergence never resolved; both sides authority-weighted; attribution present; low-authority not as fact. *Freeze:* surfaced-never-resolved; attribution-mandatory; display-not-recompute.

**P7 — Real-Bundle Validation.** Run a representative query set across supported intents end-to-end on the real Lucky bundle; assert every contract invariant holds on real data; confirm honest insufficiency where the bundle lacks evidence (single-source → many "official-source pending" answers). *Audit:* the real-bundle invariant sweep. *Freeze:* correct-by-contract behavior on real data.

**P8 — Freeze Review.** Assemble freeze evidence; a bounded **answer-correctness truth-set spot check** (the recurring platform assurance gap); decide. *Audit:* freeze readiness. *Freeze:* criteria met or limitations accepted.

---

## 3. Audit Gates (consolidated)

| Gate | Phase | Verifies |
|---|---|---|
| `query_v2_contract_integrity_audit` | P0 | Enums/version-pins/ownership consistent. |
| `query_v2_intent_audit` | P1 | Deterministic classification; clarify/unsupported; MSIL-resolved entities. |
| `query_v2_planning_audit` | P2 | Auditable `rule_id` plans; resolved-entity-only; metric→FVE. |
| `query_v2_ranking_audit` | P3 | As-authored; provenance-complete-first; consume-not-recompute. |
| `query_v2_assembly_audit` | P4 | Grounded claims; bounded confidence; honest status. |
| `query_v2_citation_audit` | P5 | 100% cited; no-false-precision; MSIL-only. |
| `query_v2_divergence_authority_audit` | P6 | Surfaced-never-resolved; attribution; low-authority-not-as-fact. |
| `query_v2_real_bundle_audit` | P7 | All invariants hold end-to-end on real data. |
| `query_v2_freeze_readiness_audit` | P8 | Freeze criteria + truth-set spot check. |

---

## 4. Freeze Criteria (platform-consistent)

Query v2 may freeze when, on the real bundle:
1. **Every shipped claim is cited** from MSIL provenance (no un-cited claim).
2. **Every metric answer carries FVE integrity status.**
3. **Divergence is surfaced, never resolved**; both sides authority-weighted.
4. **Authority is displayed as MSIL-assigned**, never recomputed; every claim attributed.
5. **Insufficiency/clarification/unsupported are first-class** — no fabricated answers.
6. **Confidence is bounded** (min-composition), never inflated across engines.
7. **Planning is deterministic + auditable** (`rule_id` on every step).
8. **No re-derivation** — entity/authority/theme/validation/divergence-resolution all consumed as authored.
9. **Version pins present** on every response; consumed versions recorded.
10. **MB-1 closed** (entity sign-off) + a bounded **answer-correctness truth-set spot check** performed.
11. **Honest scope statement** published: deterministic federated answering over available sources; correctness not certified; analyst/market/news intents deferred.

---

## 5. Hidden Dependencies

- **HD-1 — MB-1 (entity sign-off).** Query binds answers to MSIL entities; a wrong-entity fact yields a confidently-wrong cited answer. Gates P7/P8 *trust*, not the P0–P6 build.
- **HD-2 — QAE + FVE consumption contracts finalized.** The `qualitative_analysis` and `forecast_validation` intents depend on consuming QAE themes / FVE validations as authored; if not finalized, those intents can't wire (build factual/metric/timeline/source-exploration first).
- **HD-3 — MSIL consumability** (evidence store, provenance, authority, divergence) — satisfied through P8C; **MB-4 closed** so divergence presentation consumes clean divergences.
- **HD-4 — Source availability.** Only annual report + official triad + QAE + FVE; analyst/sector/market/news post-MVP → `risk_analysis` partial; many real-bundle answers will be single-source.
- **HD-5 — Dual evidence path.** Query v1's direct workbook-cell citations vs MSIL provenance; v2 should route via MSIL with the existing path additive (the platform maintainability debt) — define which path each citation type uses.
- **HD-6 — No answer truth set.** Correctness of assembled answers is unvalidated (the recurring platform gap); gates accuracy claims, addressed by the P8 spot check.

---

## 6. Over-Engineering Risks

- **OE-1 — Building `risk_analysis` (and other source-hungry intents) before their sources exist.** News/market/analyst are post-MVP; build the available intents, mark `risk_analysis` partial — do not deepen it on synthetic data (the FVE-Phase-9 trap).
- **OE-2 — A heavy LLM natural-language answer generator.** Deterministic-first + evidence-or-silence means the LLM is a *thin rephraser over already-cited claims*; a rich generative layer reintroduces the hallucination the platform forbids. Keep it minimal or defer.
- **OE-3 — Learned/ML ranking** before deterministic ranking is proven on real queries. Keep ranking deterministic and simple.
- **OE-4 — Rich NLU/intent models** before deterministic classification is validated; a rule-based classifier with a clarify off-ramp is sufficient for MVP.
- **OE-5 — Deep multi-source synthesis** before real multi-source volume exists (the triad is fixture-proven, not real-feed-at-volume); don't over-build cross-source reasoning the data can't yet exercise.
- **OE-6 — Answer-style/formatting surface area** (multiple answer modes, presentation options) before a single correct cited answer path is proven — the Query-v1-architecture-review F22 lesson.

---

## 7. Sequencing Rationale

Contracts first (P0) so every later phase builds against frozen shapes. Then the lifecycle bottom-up — **intent (P1) → planning (P2) → ranking (P3) → assembly (P4)** — because each consumes the prior's output. The **enforcement layers (citation P5, divergence/authority P6) follow assembly** because they police and decorate an assembled answer; building them before there is an answer to enforce would be premature. **Real-bundle validation (P7) is second-to-last** — the platform's "prove on real data before freeze" rule — and is the first point where the federated answer is exercised end-to-end. **Freeze (P8) is gated on MB-1** because trusting Query output requires the identity keystone confirmed. This order also lets the lowest-risk capability (deterministic intent + retrieval) prove the MSIL consumption contract before the higher-risk synthesis/citation/divergence layers depend on it.

---

## 8. One-Paragraph Verdict

Query v2 builds the way every successful layer in this platform built: freeze the ten contracts first (P0), then construct the lifecycle bottom-up — deterministic intent classification with MSIL-resolved entities (P1), auditable retrieval planning that always carries FVE integrity for metrics (P2), as-authored evidence ranked provenance-complete-first (P3), and answer assembly that grounds every claim and bounds confidence without inflating it across engines (P4) — before layering the three enforcement guarantees that make the answer trustworthy: cite every claim from MSIL provenance (P5), surface divergence with both sides and never resolve it while displaying authority exactly as assigned (P6). It is validated end-to-end on the real Lucky bundle (P7) and frozen only after MB-1 closes and a bounded answer-correctness spot check is done (P8). The dependencies are honest — MB-1 gates trust, QAE/FVE consumption contracts gate the qualitative/forecast intents, and source availability keeps `risk_analysis` partial — and the over-engineering risks are all the same temptation in different clothes: do not build generative answering, learned ranking, rich NLU, deep cross-source synthesis, or source-hungry intents ahead of the deterministic, evidence-grounded, real-data-proven path the platform's invariants require. Sequenced this way, v2 turns the integrated platform into a usable, citeable, authority-honest, divergence-honest interface without re-deriving a single thing it federates.
