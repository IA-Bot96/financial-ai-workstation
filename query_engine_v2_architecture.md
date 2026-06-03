# Query Engine v2 — Architecture

**Status:** Architecture proposal. No code, no implementation detail. Architecture only.
**Date:** 2026-06-03
**Position:** The user-facing **federated answering / orchestration layer** atop the completed platform (MSIL evidence substrate + QAE + FVE; OCR upstream of MSIL).
**Builds on:** Query v1 (deterministic-first retrieval + citations) and MSIL integration 8A (evidence/provenance/authority consumption).

---

## 0. What Query v2 Is

Query v1 retrieves MSIL evidence and renders citations. Query v2 adds the **intelligence layer** — intent understanding, retrieval planning, source selection, ranking, answer assembly, multi-source reasoning, and authority-aware synthesis — becoming the **federated brain** that routes a question across the evidence substrate (MSIL) and the domain engines (QAE, FVE) and assembles an authority-aware, divergence-honest, fully-cited answer.

Three principles, inherited and binding:
1. **Deterministic-first.** Intent classification, retrieval planning, and source selection are rule-based and auditable; any LLM is confined to rephrasing already-assembled, already-cited evidence — never inventing facts, sources, or authority (the platform's narrative-layer rule).
2. **Federate, never re-derive.** Query orchestrates and assembles; it consumes MSIL evidence, QAE themes, and FVE validations **as authored** and never recomputes entity identity, authority, themes, numeric validation, or divergence resolution.
3. **Evidence-or-silence.** An answer is grounded in cited evidence or it returns *insufficient evidence / needs clarification* — never a fabricated answer (Query v1's discipline, preserved).

---

## 1. Query Engine Responsibilities (Task 1)

1. **Intent understanding** — classify the question into a supported intent (§4).
2. **Retrieval planning** — decide which sources/engines to consult (§5).
3. **Source selection** — choose MSIL source types / QAE / FVE by intent + authority + recency (§8).
4. **Evidence retrieval** — pull from the MSIL evidence store; pull QAE theme outputs and FVE validation outcomes.
5. **Evidence ranking** — authority-aware, recency-aware, provenance-complete-first.
6. **Answer assembly** — compose a grounded answer from ranked evidence + domain conclusions.
7. **Authority-aware synthesis** — present every claim with its authority; rank by it, never override it (§6).
8. **Divergence surfacing** — present conflicting evidence; never resolve it (§7).
9. **Citation rendering** — from MSIL provenance / workbook mappings; no invented citations, no false precision.
10. **Ambiguity & insufficiency handling** — deterministic clarification / "insufficient evidence," not fabrication.

**Not Query's job:** entity resolution, authority assignment, numeric validation, theme assembly, divergence resolution, forecast generation.

---

## 2. Boundaries (Task 2)

| Engine | Query consumes | Query must NOT do |
|---|---|---|
| **MSIL** | Evidence store, provenance, authority, timeline, entity index, divergence references | Resolve entities; assign/recompute authority; snapshot provenance; compute corroboration/divergence |
| **QAE** | Theme outputs (themes + coverage + confidence + narrative divergence), **as authored** | Re-assemble or re-classify themes; create themes |
| **FVE** | Validation outcomes (baseline status, validation verdicts, plausibility, NumericEvidence), **as authored** | Validate numbers; admit baselines; gate; generate forecasts |
| **OCR** | Nothing directly — OCR financial values reach Query via MSIL (and, transitionally, the existing workbook-cell path) | Touch OCR directly |

Cardinal boundary: **Query is sovereign only over planning, ranking, assembly, and citation rendering.** Every conclusion it presents is authored by its owner (identity/authority/provenance/divergence-detection = MSIL; themes = QAE; numeric validation/plausibility = FVE).

---

## 3. Query Lifecycle (Task 3)

| Stage | Owner | Responsibility | Off-ramp |
|---|---|---|---|
| **User Query** | — | Raw question + (optional) submitted forecast/forecast target | — |
| **Intent** | Query | Deterministic classification into a supported intent; entity mention extraction | Unclear → **clarify** |
| **Retrieval Plan** | Query | Map intent → required content classes + domains (§5) | No plan → **unsupported intent** |
| **Source Selection** | Query | Choose MSIL source types / QAE / FVE, governed by authority + recency + entity resolution (§8) | No eligible source → **insufficient evidence** |
| **Evidence Retrieval** | Query (from MSIL/QAE/FVE) | Pull entity-resolved, provenance-backed evidence + domain conclusions | Quarantined/unresolved entity → **excluded** |
| **Evidence Ranking** | Query | Authority-aware, recency-aware, provenance-complete-first ordering | Un-provenanced → **excluded** |
| **Answer Assembly** | Query | Compose grounded answer; attach authority; surface divergence; bound confidence | No groundable claim → **insufficient evidence** |
| **Citation Rendering** | Query | Render citations from MSIL provenance / workbook mappings | Missing provenance → **claim dropped, never un-cited** |

Cross-cutting through every stage: **entity binding (MSIL-resolved), authority tags, and provenance travel with the evidence**, and an insufficiency/ambiguity off-ramp exists at each stage so the engine degrades to honest silence rather than fabrication.

---

## 4. Query Intents (Task 4)

| Intent | Primary domain(s) | What it answers |
|---|---|---|
| **Factual lookup** | MSIL (narrative/event) + provenance | A fact about an entity. |
| **Metric lookup** | MSIL numeric / OCR-via-MSIL **+ FVE** | A number **+ its integrity status** (baseline/clean/review-gated). |
| **Qualitative analysis** | **QAE** | Outlook, strategy, risk, governance, ESG themes. |
| **Forecast validation** | **FVE** | Is a baseline clean / a submitted forecast plausible. |
| **Comparison** | MSIL + FVE (numeric integrity) / QAE (narrative) | Cross-entity or cross-period contrast. |
| **Timeline** | MSIL timeline + events | What happened when. |
| **Risk analysis** | QAE (risk themes) + MSIL (SECP/divergence) + FVE (numeric flags) | Composite risk posture. |
| **Source exploration** | MSIL evidence store + provenance + authority + divergence | What evidence/sources exist on X, and where they disagree. |

Rules: intents are **deterministically classified**; **multi-intent queries decompose** into sub-plans; **metric lookups always carry FVE integrity status** (a number is never returned without its trust state); **qualitative/forecast intents route to QAE/FVE conclusions, never re-derived**.

---

## 5. Retrieval Planning (Task 5)

Source choice is governed by **content need × recency × authority × content class**:

| Source | Use when | Authority role |
|---|---|---|
| **Annual report** (audited, lagging) | Audited historical financials; comprehensive audited narrative; default for "what the company reports / audited history" | `audited_issuer` — baseline-grade for facts |
| **PSX announcements** (timely, unaudited) | Recent events/results/guidance; "latest / since the report / what just happened" | `official_issuer_unaudited` — timely, optimism-flagged |
| **Company payouts** | Dividend/bonus events and amounts (corporate actions) | `exchange_official` — authoritative for the payout event |
| **SECP notices** | Compliance, enforcement, restatements, regulatory actions | `regulatory_independent` — highest for compliance facts |
| **QAE** | Strategy/risk/outlook/ESG/governance **narrative interpretation** | Theme owner; coverage-honest |
| **FVE** | Number **trust/validation**, baseline cleanliness, forecast plausibility | Numeric/forecast authority |

Planning rules: **forward/recent → announcements; audited/historical → annual report; corporate-action → payouts; compliance/regulatory → SECP; narrative interpretation → QAE; numeric trust/forecast → FVE.** Multi-source plans are explicit (e.g. *current risk posture* = QAE risk themes + recent announcements + SECP notices + any surfaced divergence). **Entity resolution (MSIL) runs first**; nothing is retrieved for an unresolved/quarantined entity. (MVP availability: annual report + official triad + QAE + FVE; analyst/sector/market/news are post-MVP, so "risk analysis" is partial until they land.)

---

## 6. Authority-Aware Answering (Task 6)

- **Every claim carries its evidence's authority** (claim-type-scoped, from MSIL) — the user sees *"per the audited report"* vs *"per SECP"* vs *"per analyst."*
- **Authority drives ranking and framing**, not truth selection: higher-authority evidence ranks first and frames the answer; lower-authority is presented as supporting/opinion, labeled.
- **Authority is displayed and used for ranking — never recomputed or overridden** by Query.
- **The authority inversion holds for forward claims:** for expectations, analyst/guidance/market are the relevant voices; for facts, audited/regulatory dominate.
- **Hard rule:** an answer must never present low-authority evidence (news/analyst/market) as fact, nor present a single high-authority voice as settled when divergence exists.
- **Confidence is bounded, never inflated:** an answer's confidence is capped by its weakest required evidence and by MSIL authority ceilings; Query reports confidence, never multiplies it across sources or engines.

---

## 7. Divergence Handling (Task 7)

- Query **surfaces** divergence (both sides, authority-weighted) and **never resolves** it — the platform invariant.
- A divergent answer presents the disagreement explicitly — *"the annual report states X; the SECP notice states Y"* — with authority labels, **never a single adjudicated value**.
- Divergence **lowers answer confidence and is reported**, never hidden.
- By domain: numeric divergence is presented as **FVE** surfaced it; narrative divergence as **QAE** surfaced it; cross-source as **MSIL** surfaced it — Query relays, never adjudicates.
- Post-MB-4, reference-only numeric noise no longer reaches Query; only genuine divergences surface.

---

## 8. Source-Selection Governance (Task 8)

- **Deterministic & auditable** — intent → source rule, not LLM-improvised; the selected sources and *why* are logged.
- **Authority-class governs eligibility** — news/analyst/market may inform but may not be the **sole** source for a factual claim; audited/regulatory is required for fact claims where available.
- **Entity-resolved-first** — only MSIL-resolved, non-quarantined entities contribute; quarantined evidence is excluded.
- **Provenance-required** — no source contributes to an answer without citable MSIL provenance.
- **Coverage honesty** — if the selected sources hold no evidence, return *insufficient evidence*, not a fabricated answer; **a well-sourced answer is not a correct answer** (coverage ≠ correctness — the user/analyst judges).
- **Forward-compatible** — unknown/new source types are ignored gracefully (additive).

---

## 9. Ownership Boundaries (Task 9)

| Concept | Owner |
|---|---|
| Intent classification · retrieval planning · source selection · ranking · answer assembly · citation rendering | **Query** |
| Entity resolution · authority assignment · provenance · corroboration · divergence **detection** | **MSIL** |
| Theme generation | **QAE** |
| Numeric validation · forecast plausibility | **FVE** |
| Divergence **interpretation/adjudication** | Owning domain engine — **Query surfaces only** |

The cardinal rule: **Query orchestrates and assembles; it never re-derives any domain conclusion** (entity, authority, theme, validation, or divergence resolution). Citation provenance is MSIL's; citation *rendering* is Query's.

---

## 10. One-Paragraph Verdict

Query Engine v2 is the platform's federated answering layer: a deterministic-first brain that classifies a question's intent, plans which sources and engines to consult, retrieves entity-resolved and provenance-backed evidence, ranks it by authority and recency, and assembles a fully-cited, authority-labeled, divergence-honest answer — routing factual and timeline questions to MSIL evidence, narrative questions to QAE themes, and numeric-trust and forecast questions to FVE validations, always with each number carrying its integrity status and each claim carrying its authority. It earns the user's trust by federating rather than re-deriving: it consumes MSIL identity/authority/provenance, QAE themes, and FVE validations exactly as authored, never recomputing authority, never validating a number, never assembling a theme, and — above all — never resolving a divergence, only surfacing it with both sides and their authority. It degrades to honest silence (*insufficient evidence / needs clarification*) rather than fabrication, bounds confidence rather than inflating it across engines, and treats a well-sourced answer as evidence for an analyst's judgment, not as certified truth. Built this way, v2 turns the completed platform into a usable interface while preserving every invariant the platform was built on: resolve identity before trusting evidence, gate numbers before believing them, cite from snapshotted provenance, surface divergence without resolving it, and never mistake coverage for correctness or source abundance for source authority.
