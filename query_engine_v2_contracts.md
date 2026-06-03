# Query Engine v2 — Contracts

**Status:** Contract specification. No code. Source: `query_engine_v2_architecture.md`.
**Date:** 2026-06-03
**Purpose:** Freeze the ten Query v2 contracts so the answering layer can be built contracts-first without re-deriving any domain conclusion.

---

## 0. Principles & How to Read

Field status: **R** required · **O** optional · **D** derived. Every contract states **fields · invariants · ownership · version pins · freeze decisions.** Consolidated version pins, ownership, and the master freeze list are in §11–§13.

Three platform invariants bind all ten:
1. **Federate, never re-derive** — Query consumes MSIL evidence, QAE themes, FVE validations *as authored*; it never recomputes entity identity, authority, themes, numeric validation, or divergence resolution.
2. **Evidence-or-silence** — no ungrounded, un-cited, or fabricated answer; insufficiency/clarification are first-class outcomes.
3. **Deterministic-first** — intent, planning, selection, ranking are rule-based and auditable; any LLM rephrases only already-cited claims.

---

## 1. QueryIntent

| Field | R/O | Semantics |
|---|---|---|
| `query_id` | R | Stable id for the query. |
| `raw_query` | R | The user's question verbatim. |
| `intent_type` | R | §enum below. |
| `secondary_intents[]` | O | Decomposed sub-intents for multi-intent queries. |
| `entity_mentions[]` | R | Each: `{raw_mention, entity_ref (MSIL-resolved), entity_resolution_status}`. |
| `requested_metrics_or_topics[]` | O | Parsed metric/topic targets. |
| `forecast_target` | O | Submitted forecast (forecast_validation intent only). |
| `time_scope` | O | Period/recency the query implies. |
| `classification_confidence` | R (D) | Deterministic intent-classification confidence. |
| `needs_clarification` | R | True when intent/entity is ambiguous. |
| `clarification_prompt` | O | Required when `needs_clarification`. |
| `query_contract_version` | R | Version pin. |

**`intent_type` enum (frozen):** `factual_lookup` · `metric_lookup` · `qualitative_analysis` · `forecast_validation` · `comparison` · `timeline` · `risk_analysis` · `source_exploration` · `ambiguous` · `unsupported`.

**Invariants:** classification is deterministic; ambiguity → `ambiguous`/`needs_clarification` (never guessed); unsupported → `unsupported` (never forced); **entity resolution is referenced from MSIL, not performed by Query**; multi-intent decomposes into `secondary_intents`.
**Ownership:** Query (classification); MSIL (entity resolution, referenced).
**Freeze:** `intent_type` enum; clarification/unsupported off-ramps; entity-resolution-is-MSIL rule.

---

## 2. RetrievalPlan

| Field | R/O | Semantics |
|---|---|---|
| `plan_id` | R | Id. |
| `intent_ref` | R | The QueryIntent it serves. |
| `entity_refs[]` | R | MSIL-resolved entities in scope. |
| `plan_steps[]` | R | Each: `{step_id, target_domain, source_types[], content_classes[], purpose, required_authority_floor, recency_requirement, rule_id}`. |
| `is_multi_source` | R (D) | More than one source/domain. |
| `unsupported_reason` | O | Set when no plan can be formed. |
| version pins | R | §11. |

**`target_domain` enum:** `msil` · `ocr_via_msil` · `qae` · `fve`.

**Invariants:** deterministic + **auditable** (every step carries the `rule_id` that produced it); **entity-resolved-first** (no step over an unresolved/quarantined entity); no plan → `unsupported`; **a `metric_lookup` plan ALWAYS includes an FVE integrity step** (a number never planned without its trust state).
**Ownership:** Query.
**Freeze:** the intent→plan rule set; auditability (`rule_id`) requirement; metric-always-carries-FVE rule.

---

## 3. EvidenceRequest

| Field | R/O | Semantics |
|---|---|---|
| `request_id` | R | Id. |
| `plan_step_ref` | R | The plan step it executes. |
| `target_domain` | R | Exactly one of `msil` / `qae` / `fve`. |
| `entity_ref` | R | **MSIL-resolved id only** (never a raw identifier). |
| `selectors` | R | Domain-specific: MSIL `{content_classes[], source_types[]}`; QAE `{theme_scope/category}`; FVE `{metric / forecast_target}`. |
| `authority_floor` | O | Minimum effective authority required. |
| `recency_window` | O | Time bound. |
| `max_results` | O | Cap. |
| version pins | R | §11. |

**Invariants:** one request targets exactly one domain; carries a **resolved** `entity_ref`; **never requests quarantined/unresolved entities**; Query requests, the domain fulfills (Query computes nothing).
**Ownership:** Query issues; MSIL/QAE/FVE fulfill.
**Freeze:** `target_domain` enum; resolved-entity-only rule.

---

## 4. EvidenceBundle

| Field | R/O | Semantics |
|---|---|---|
| `bundle_id` | R | Id. |
| `request_ref` | R | The request fulfilled. |
| `source_domain` | R | Which domain authored the items. |
| `items[]` | R | `EvidenceItem` (below). |
| `coverage_note` | R | What was / was not found (empty bundles carry a note, never silence). |
| version pins | R | §11. |

**`EvidenceItem` fields:** `evidence_ref` (signal/theme/validation id) · `content_class` · `claim_or_value_or_theme_summary` · `authority_class` · `source_type` · `provenance` (MSIL) · `observation_time` · `subject_period` · `supersession_state` · `divergence_refs[]` · `entity_ref` · (numeric) `integrity_status` (from FVE).

**Invariants:** every item is **entity-resolved + provenance-backed** (`NONE` forbidden); items carry MSIL/QAE/FVE authority, provenance, and divergence **as authored — Query never modifies them**; superseded items flagged; empty bundle → `coverage_note`, never a fabricated item.
**Ownership:** MSIL/QAE/FVE author item content; Query owns the bundle envelope only.
**Freeze:** `EvidenceItem` shape; provenance-required; as-authored (no-modify) rule.

---

## 5. RankedEvidence

| Field | R/O | Semantics |
|---|---|---|
| `ranked_id` | R | Id. |
| `bundle_ref` | R | Source bundle. |
| `ranked_items[]` | R | Each: `{evidence_ref, rank, ranking_signals, included, exclusion_reason}`. |
| `ranking_policy_version` | R | Version pin for the ranking rules. |
| version pins | R | §11. |

**`ranking_signals` (frozen set):** `authority_weight` (from MSIL, claim-type-scoped) · `recency` · `provenance_completeness` · `corroboration_strength` (from MSIL).

**Invariants:** ranking is **deterministic, authority-aware, recency-aware, provenance-complete-first**; un-provenanced items are **excluded** with an `exclusion_reason`; authority and corroboration are **consumed from MSIL, never recomputed**; ranking signals are recorded for audit.
**Ownership:** Query (ranking); MSIL (authority/corroboration inputs).
**Freeze:** the `ranking_signals` set; provenance-complete-first; deterministic ranking; consume-not-recompute.

---

## 6. AnswerAssemblyContext

| Field | R/O | Semantics |
|---|---|---|
| `context_id` | R | Id. |
| `intent_ref` | R | The intent. |
| `ranked_evidence_refs[]` | R | Evidence grounding the answer. |
| `domain_conclusions[]` | O | QAE themes / FVE validations, **as authored**. |
| `divergence_set[]` | O | Surfaced divergences carried in. |
| `authority_set[]` | R | Per-claim authority. |
| `confidence_ceiling` | R (D) | Bounded composed ceiling (below). |
| `insufficiency_flag` | R | True if no groundable claim exists. |
| version pins | R | §11. |

**Invariants:** **every claim grounds in ranked evidence** (no ungrounded claim); domain conclusions consumed **as authored** (never re-derived); **`confidence_ceiling = min(weakest required evidence, MSIL authority ceilings)` — never inflated, never multiplied across engines**; divergence carried in, **never resolved**; no groundable claim → `insufficiency_flag`.
**Ownership:** Query.
**Freeze:** grounding requirement; the `min`-composition confidence ceiling (no cross-engine multiplication); no-ungrounded-claim rule.

---

## 7. QueryResponse

```
{ "response_id": "...", "query_id": "...", "status": "ANSWERED|ANSWERED_WITH_WARNINGS|INSUFFICIENT_EVIDENCE|NEEDS_CLARIFICATION|UNSUPPORTED_INTENT",
  "answer_text": "...", "claims": [ { "statement": "...", "supporting_evidence_refs": [...],
      "authority_class": "...", "citations": [...], "confidence": 0.0 } ],
  "divergences": [...], "warnings": [...], "overall_confidence": 0.0,
  "numeric_integrity_status": null, "clarification_prompt": null,
  "version_pins": {...}, "generated_at": "..." }
```

| Field | R/O | Semantics |
|---|---|---|
| `status` | R | §enum (above). |
| `answer_text` | O | Grounded prose; LLM may rephrase **only** already-cited claims. |
| `claims[]` | R when `ANSWERED*` | Each statement + supporting evidence + authority + citations + confidence. |
| `divergences[]` | O | Presented per §9. |
| `warnings[]` | O | Incl. divergence, low-coverage, low-authority notes. |
| `numeric_integrity_status` | R for metric answers | From FVE (e.g. baseline-clean / clean-with-warning / review-gated / not-validatable / missing). |
| `overall_confidence` | R (D) | Bounded; never inflated. |
| `clarification_prompt` | O | Required when `NEEDS_CLARIFICATION`. |
| version pins · `generated_at` | R | §11. |

**`status` enum (frozen):** `ANSWERED` · `ANSWERED_WITH_WARNINGS` · `INSUFFICIENT_EVIDENCE` · `NEEDS_CLARIFICATION` · `UNSUPPORTED_INTENT`.

**Invariants:** `ANSWERED*` requires ≥1 **grounded, cited** claim; `INSUFFICIENT_EVIDENCE`/`NEEDS_CLARIFICATION`/`UNSUPPORTED_INTENT` are first-class (never a fabricated answer); **every claim carries ≥1 citation**; **metric claims carry FVE integrity status**; divergences **presented, not resolved**; no fused/inflated confidence; `answer_text` introduces **no fact absent from `claims`**.
**Ownership:** Query.
**Freeze:** `status` enum; cite-every-claim; metric-carries-integrity; LLM-rephrase-only-over-cited-claims.

---

## 8. CitationContract

| Field | R/O | Semantics |
|---|---|---|
| `citation_id` | R | Id. |
| `citation_type` | R | = MSIL `provenance_type`. |
| `source_ref` | R | Provenance locator (page/date/cell/announcement/notice id). |
| `entity_ref` | R | Resolved entity. |
| `evidence_ref` | R | The evidence cited. |
| `rendered_text` | R | User-facing citation string. |
| `precision_level` | R | `page` / `date` / `cell` / `ref` — no finer than provenance allows. |
| version pins | R | §11. |

**`citation_type` enum:** `WORKBOOK_CELL` · `PDF_PAGE` · `ANNOUNCEMENT_REF` · `REGULATORY_REF` · `PAYOUT_REF` · `MARKET_DATA_REF` · `FUTURES_REF` · `SECTOR_REF` · `URL_SNAPSHOT` · `NEWS_REF` (mirrors MSIL provenance; `NONE` **forbidden to render**).

**Invariants:** citations render **only from MSIL provenance** (Query invents none); `NONE` provenance → no citation → **the claim is dropped, never shown un-cited**; **no false precision**; `WORKBOOK_CELL` only where a mapping exists; **every user-facing claim has ≥1 citation**.
**Ownership:** MSIL owns provenance; **Query owns rendering**.
**Freeze:** `citation_type` enum; provenance-required; no-false-precision; no-un-cited-claim.

---

## 9. DivergencePresentationContract

| Field | R/O | Semantics |
|---|---|---|
| `presentation_id` | R | Id. |
| `divergence_ref` | R | MSIL-detected divergence. |
| `entity_ref` · `subject` | R | What disagrees. |
| `sides[]` | R | Each: `{claim_summary, authority_class, source_type, citation}`. |
| `authority_weighting` | R | **From MSIL**, as provided. |
| `presentation_status` | R | Always `surfaced`. |
| `resolution` | R | Always `not_determined_by_query`. |
| `detected_by` | R | `msil` (numeric→via FVE, narrative→via QAE, cross-source→MSIL). |
| version pins | R | §11. |

**Invariants:** **both sides presented with their `authority_class`**; authority-weighted; `presentation_status` always `surfaced`, `resolution` always `not_determined_by_query`; **Query never picks a winner**; divergence **lowers answer confidence and appears in `warnings`**; **equal-weighting forbidden**; Query relays per-domain divergence, never adjudicates.
**Ownership:** MSIL detects; owning engine interprets; **Query presents only**.
**Freeze:** surfaced-never-resolved; both-sides-with-authority; no-equal-weighting; relay-not-adjudicate.

---

## 10. AuthorityPresentationContract

| Field | R/O | Semantics |
|---|---|---|
| `presentation_id` | R | Id. |
| `claim_ref` | R | The claim being attributed. |
| `authority_class` | R | **From MSIL** (never recomputed). |
| `claim_type` | R | From MSIL. |
| `effective_authority` | R | From the authority matrix, **as provided**. |
| `attribution_label` | R | "per the audited report" / "per SECP" / "per analyst" / etc. |
| `authority_role` | R | `fact` / `supporting` / `opinion` / `forward_context`. |
| version pins | R | §11. |

**Invariants:** authority is **displayed as MSIL-assigned — never recomputed or overridden**; **every claim is attributed** (the user sees who said it); **low-authority (news/analyst/market) is never presented as fact**; high-authority is **not presented as settled when divergence exists**; **authority caps confidence, never sets truth**; the **forward-authority inversion** is respected (analyst/guidance/market are the relevant voices for expectations).
**Ownership:** MSIL assigns; **Query presents**.
**Freeze:** attribution-mandatory; display-not-recompute; low-authority-never-as-fact; authority-caps-not-sets-truth.

---

## 11. Version Pins (consolidated)

`query_contract_version` · `ranking_policy_version` — **owned by Query**.
Consumed (recorded, never modified): `msil_schema_version` · `authority_matrix_version` · `entity_registry_version` · `qae_consumption_contract_version` · `fve_consumption_contract_version` · `taxonomy_version`.
**Every `QueryResponse` pins `query_contract_version` + `ranking_policy_version` and records the consumed versions** it answered under; no cross-version interpretation without explicit migration.

---

## 12. Ownership (consolidated)

| Concept | Owner |
|---|---|
| Intent classification · retrieval planning · source selection · ranking · answer assembly · citation **rendering** | **Query** |
| Entity resolution · authority assignment · provenance · corroboration · divergence **detection** | **MSIL** |
| Theme generation | **QAE** |
| Numeric validation · forecast plausibility · numeric integrity status | **FVE** |
| Divergence **interpretation** | Owning domain engine — **Query presents only** |

---

## 13. Master Freeze Decisions

1. `intent_type` enum + clarification/unsupported off-ramps (§1).
2. Intent→plan rule set + `rule_id` auditability + metric-always-carries-FVE (§2).
3. `target_domain` enum + resolved-entity-only requests (§3).
4. `EvidenceItem` shape + provenance-required + as-authored no-modify (§4).
5. `ranking_signals` set + provenance-complete-first + consume-not-recompute (§5).
6. Grounding requirement + `min`-composition confidence ceiling (no cross-engine multiplication) (§6).
7. `status` enum + cite-every-claim + metric-carries-integrity + LLM-rephrase-only (§7).
8. `citation_type` enum + provenance-required + no-false-precision + no-un-cited-claim (§8).
9. Divergence surfaced-never-resolved + both-sides-with-authority + no-equal-weighting (§9).
10. Authority display-not-recompute + attribution-mandatory + low-authority-never-as-fact (§10).
11. Version-pin set + record-consumed-versions (§11).

---

## 14. One-Paragraph Verdict

These ten contracts freeze Query v2 as a federated answering layer that owns exactly four things — intent, planning, ranking, and assembly/citation-rendering — and re-derives nothing: a `QueryIntent` is classified deterministically with entity references resolved by MSIL; a `RetrievalPlan` maps it to auditable source steps (and always carries an FVE integrity step for metrics); `EvidenceRequest`s pull only resolved entities; an `EvidenceBundle` carries MSIL/QAE/FVE content *as authored* with mandatory provenance; `RankedEvidence` orders it authority-aware and provenance-complete-first, excluding the un-cited; an `AnswerAssemblyContext` grounds every claim and bounds confidence by the weakest evidence and MSIL authority ceilings (never multiplying across engines); and the `QueryResponse` cites every claim, attaches FVE integrity to every number, presents divergence without resolving it, and degrades to `INSUFFICIENT_EVIDENCE`/`NEEDS_CLARIFICATION` rather than fabricate. The `Citation`, `DivergencePresentation`, and `AuthorityPresentation` contracts encode the three hardest user-facing guarantees — cite only from snapshotted provenance, surface divergence with both sides and never pick a winner, and display authority exactly as MSIL assigned it while never presenting opinion as fact. Frozen together and version-pinned, they make the answering layer trustworthy by construction: it federates the platform's evidence and conclusions into cited, authority-honest, divergence-honest answers while preserving every invariant the platform was built on.
