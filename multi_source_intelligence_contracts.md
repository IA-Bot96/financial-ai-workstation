# Multi-Source Intelligence Layer (MSIL) — Contracts

**Status:** Contract specification. No code. Source: `multi_source_intelligence_architecture.md`.
**Date:** 2026-06-02
**Purpose:** Freeze the ten MSIL contracts so adapters, resolution, timeline, and the three engine-consumption paths can be built contracts-first.

---

## 0. How to Read This

- Field status: **R** required · **O** optional · **D** derived (computed, not author-supplied).
- Every contract section states: **required fields · invariants · version pins · authority ownership · freeze-before-implementation decisions.** Cross-cutting **hidden dependencies** and the **master freeze list** are consolidated in §11–§13.
- Two platform invariants bind all ten: **(a) no signal/event/record without immutable provenance**, and **(b) MSIL owns substrate (entity/time/authority/provenance), never engine domains (numbers/themes/answers).**

---

## 1. Entity Registry Contract (Task 1)

**Purpose:** the canonical store of identity. The single source of "who."

**Entity record — required fields**
| Field | R/O | Semantics |
|---|---|---|
| `canonical_id` | R | Immutable, globally unique, **never reused**. |
| `entity_type` | R | `company` / `security` / `futures_instrument` / `sector` / `person` / `source` / `period`. |
| `display_name` | R | Canonical human name. |
| `aliases[]` | R | Each: `{value, alias_type}` where `alias_type` ∈ `ticker` / `secp_reg_no` / `legal_name` / `name_variant` / `isin`. |
| `relationships[]` | R | Each: `{rel_type, target_canonical_id}`; `rel_type` ∈ `security_of` / `futures_on` / `person_of` / `member_of_sector` / `parent_of` / `subsidiary_of`. |
| `status` | R | `active` / `merged` / `deprecated`. |
| `merged_into` | O | Tombstone pointer when `status=merged`. |
| `entity_registry_version` | R | Version pin. |

**Invariants**
- `canonical_id` is immutable; merges leave a **tombstone** (`merged`/`merged_into`), never delete.
- An alias resolves to **at most one** active canonical entity (no ambiguous alias in a frozen registry).
- Group/subsidiary entities are **distinct** (`Lucky Cement` ≠ `Lucky Core` ≠ `Lucky Motor`), linked by `parent_of`/`subsidiary_of`.
- A `security`/`futures_instrument` must link to a `company` via `security_of`/`futures_on`.

**Version pin:** `entity_registry_version`.
**Authority ownership:** **MSIL** owns the registry; no engine creates identity.
**Freeze decisions:** `canonical_id` scheme; `entity_type` enum; `alias_type` enum; `rel_type` enum; merge/tombstone policy.

---

## 2. Entity Resolution Contract (Task 2)

**Purpose:** bind a raw identifier (from any source) to a canonical entity + period — **the keystone**.

**EntityResolution record — required fields**
| Field | R/O | Semantics |
|---|---|---|
| `raw_identifier` | R | As it appeared in the source. |
| `resolved_entity_ref` | O | Canonical id; **null when quarantined**. |
| `entity_scope` | R | `company`/`security`/`sector`/`market`/`person`. |
| `method` | R | `exact` / `alias` / `fuzzy` / `unresolved`. |
| `confidence` | R | 0–1. |
| `candidates[]` | O | Competing canonical ids when ambiguous. |
| `resolved_period` | O | Fiscal/calendar period binding (nullable for static). |
| `review_status` | R | `resolved` / `review` / `quarantined`. |
| `entity_registry_version`, `resolution_logic_version` | R | Version pins. |
| `evidence` | R | Matched alias / fuzzy score / candidate set. |

**Invariants**
- Deterministic tiering: `exact → alias → fuzzy → unresolved`.
- **Never force-assign below threshold** → `quarantined` (not dropped, not attributed).
- **News and fuzzy matches default to `review`**, never silent attribution.
- Group/subsidiary disambiguation is mandatory; ambiguous group references → `review` with `candidates`.
- Every `IntelligenceSignal` carries exactly one resolution; quarantined signals never enter the evidence store as attributed.

**Version pins:** `entity_registry_version`, `resolution_logic_version`.
**Authority ownership:** **MSIL** owns resolution; no engine resolves.
**Freeze decisions:** tier thresholds; review/quarantine thresholds; the fuzzy/news→review rule; period-resolution rule.

---

## 3. IntelligenceSignal Contract (Task 3)

**Purpose:** the common evidence envelope; `QualitativeSignal` is its narrative specialization.

**Envelope shape (intended JSON; data, not code)**
```
{ "signal_id": "...", "entity_ref": "...", "entity_scope": "company",
  "content_class": "numeric_claim|narrative_claim|corporate_event|market_observation",
  "source_type": "...", "claim_type": "...", "authority_class": "...",
  "observation_time": "...", "subject_period": null, "time_basis": "calendar", "horizon": "current",
  "provenance": { "provenance_type": "...", "snapshot_ref": "...", "retrieved_at": "..." },
  "payload": { ...class-specific... },
  "source_independent_of_issuer": true, "verified": true, "source_lineage": [],
  "supersedes": null, "superseded_by": null, "corroboration_group": null, "divergence_refs": [],
  "msil_schema_version": "1.0.0", "authority_matrix_version": "1.0.0", "entity_registry_version": "1.0.0" }
```

**Required fields by group**
| Group | Fields |
|---|---|
| Identity | `signal_id` (D, **text-independent**, deterministic from entity+source+provenance+time), `entity_ref`, `entity_scope`, embedded `entity_resolution{method,confidence}` |
| Content | `content_class`, `payload` (class-specific), `claim` text (narrative), `value/unit/metric_ref` (numeric) |
| Source/authority | `source_type`, `claim_type`, `authority_class`, `source_independent_of_issuer`, `verified`, `source_lineage`, `trust_prior` |
| Time | `observation_time`, `subject_period` (nullable), `time_basis`, `horizon` |
| Provenance | `provenance` (§8) |
| Relations | `supersedes`/`superseded_by`, `corroboration_group`, `divergence_refs` |
| Versions | `msil_schema_version`, `authority_matrix_version`, `entity_registry_version` |

**Invariants**
- **No signal without immutable provenance** (`NONE` provenance ⇒ may not be emitted).
- `signal_id` **never derives from `claim` text** (re-extraction churn).
- `content_class` determines routing; **a `numeric_claim` is a candidate for FVE's gate, never a validated value**; a `market_observation` may **never** create a fact.
- `entity_scope` must match the consuming context (sector/market signals never populate a company profile).
- Version pins present on every signal.

**Version pins:** `msil_schema_version`, `authority_matrix_version`, `entity_registry_version`.
**Authority ownership:** **MSIL** owns the envelope, content-class assignment, authority/time/provenance; **not** the truth of numbers (FVE) or themes (QAE).
**Freeze decisions:** `content_class` enum; `signal_id` scheme; per-class payload shape; the version-pin set.

---

## 4. CorporateEvent Contract (Task 4)

**Purpose:** first-class dated corporate occurrence; the timeline's unit.

**Required fields**
| Field | R/O | Semantics |
|---|---|---|
| `event_id` | R (D) | Deterministic, text-independent. |
| `event_type` | R | `dividend_declared`/`dividend_paid`/`results_announced`/`board_change`/`capacity_commissioned`/`rights_issue`/`bonus_issue`/`secp_action`/`rating_change`/… (frozen enum). |
| `entity_ref` | R | Canonical company/security. |
| `event_time` | R | On the unified event-time axis. |
| `numeric_claim_refs[]` | O | Links to numeric signals (→FVE) — **references, not copies**. |
| `narrative_refs[]` | O | Links to narrative signals (→QAE). |
| `provenance` | R | §8. |
| `supersedes`/`superseded_by` | O | §7. |
| `authority_class` | R | Of the originating source. |
| version pins | R | As §3. |

**Invariants**
- Every event grounded in ≥1 provenance-backed signal.
- Events **link** to numeric/narrative signals by reference; they do not duplicate values (a payout amount lives once, as a numeric claim).
- `event_time` is calendar-anchored; placed on the shared axis.

**Authority ownership:** **MSIL** owns the timeline/events; FVE/QAE consume linked refs.
**Freeze decisions:** `event_type` enum; `event_time` semantics; the reference-not-copy rule.

---

## 5. Divergence Contract (Task 5)

**Purpose:** record cross-source contradiction; **shared** with FVE/QAE.

**Required fields**
| Field | R/O | Semantics |
|---|---|---|
| `divergence_id` | R (D) | Deterministic. |
| `entity_ref` | R | Subject company/security. |
| `subject` | R | Metric / theme / event the sides disagree on. |
| `divergence_type` | R | `narrative_vs_narrative`/`narrative_vs_numbers`/`fact_vs_fact`/`sentiment_vs_fundamentals`. |
| `side_a`, `side_b` | R | Each: `{signal_ref, authority_class, claim_summary}`. |
| `authority_weighting` | R (D) | Authority-weighted framing of the two sides. |
| `status` | R | **`surfaced` only** — MSIL never sets `resolved`. |
| `detected_by` | R | `msil`. |
| `pending_corroboration` | O | True for news-sourced sides. |
| version pins | R | As §3. |

**Invariants**
- **Both sides retained with `authority_class`; authority-weighted; never auto-resolved; never equal-weighted.**
- MSIL **surfaces**; the owning engine **adjudicates within its domain** (FVE for numbers, QAE for narrative); **neither resolves cross-domain**.
- News-sourced sides flagged `pending_corroboration`; a news claim contradicting an audited figure is recorded, **not elevated**.

**Authority ownership:** **MSIL** detects/surfaces; **owning engine** adjudicates; truth-resolution belongs to no one at MSIL level.
**Freeze decisions:** `divergence_type` enum; the surfaced-never-resolved rule; the authority-weighting method.

---

## 6. Corroboration Contract (Task 6)

**Purpose:** record independent agreement; defeat circular confirmation.

**Required fields**
| Field | R/O | Semantics |
|---|---|---|
| `corroboration_group_id` | R (D) | Deterministic. |
| `entity_ref`, `subject` | R | What is corroborated. |
| `member_signal_refs[]` | R | Supporting signals. |
| `independent_origin_count` | R (D) | Count of **distinct** authority classes with **no shared lineage**. |
| `authority_classes_present[]` | R (D) | The classes represented. |
| `lineage_checked` | R | Must be true before strength is computed. |
| `is_circular` | R (D) | True if members are lineage-linked (e.g. news echo of a PSX announcement). |
| `strength` | R (D) | Bounded, diminishing in `independent_origin_count`. |
| version pins | R | As §3. |

**Invariants**
- Corroboration credit **only** across distinct `authority_class` **and** no `source_lineage` link.
- **News echoes of issuer/analyst content are not independent** (`is_circular=true`) and are excluded from `independent_origin_count`.
- `strength` counts independent origins, **not raw signal volume**, and can **never** promote opinion/news class to fact class.

**Authority ownership:** **MSIL** computes corroboration; engines consume `strength`.
**Freeze decisions:** independence definition; the circularity/lineage rule; the bounded `strength` function.

---

## 7. Timeline & Supersession Contract (Task 7)

**Purpose:** the unified temporal backbone + current/superseded state (architecture §9–§10 folded here).

**Required fields**
| Field | R/O | Semantics |
|---|---|---|
| `entity_ref` | R | Timeline key. |
| `entries[]` | R | Ordered event/signal refs by `observation_time`. |
| `time_basis_per_entry` | R | `fiscal`/`calendar`/`continuous`/`static`. |
| `current_flag` | R (D) | Whether each entry is current or superseded. |
| `supersession_links` | R (D) | `supersedes`/`superseded_by` pairs. |
| version pins | R | As §3. |

**Invariants**
- **"Latest" is defined on `observation_time`; "trend/history" on `subject_period`** — never conflated.
- Supersession requires **same entity + same subject + later `observation_time` + authority ≥ prior** (a `news_media` item may **not** supersede an `audited_issuer` figure).
- Supersession is **explicit links, never deletion**; superseded entries remain with provenance; consumers default to current.
- Heterogeneous `time_basis` is aligned by an **explicit rule**, never silently mixed.

**Authority ownership:** **MSIL** owns timeline + supersession.
**Freeze decisions:** event-time axis definition; the supersession rule (time + authority); current-pointer semantics; time-basis alignment rule.

---

## 8. Provenance Contract (Task 8)

**Purpose:** reproducible citation for every signal/event.

**Discriminated union by `provenance_type`**
| `provenance_type` | Source | Snapshot |
|---|---|---|
| `PDF_PAGE` | annual_report | workbook fingerprint (already immutable) |
| `ANNOUNCEMENT_REF` | PSX Announcements | **required** |
| `REGULATORY_REF` | SECP Notices | **required** |
| `PAYOUT_REF` | Company Payouts | **required** |
| `MARKET_DATA_REF` | Market Watch | **required** |
| `FUTURES_REF` | Futures Market Watch | **required** |
| `SECTOR_REF` | Sector Summary | **required** |
| `URL_SNAPSHOT` | Company Overview, Analysis Reports | **required** |
| `NEWS_REF` | News Sources | **required** (publisher + url) |
| `NONE` | — | **forbidden to emit** |

**Common provenance fields:** `provenance_type`, source-specific locators, `snapshot_ref` (content hash + stored copy), `retrieved_at`, `verified` (authenticated-origin vs scraped), `source_lineage`.

**Invariants**
- Every non-PDF source carries an **immutable `snapshot_ref`** (web/market/news are ephemeral).
- **No false precision** — a market signal cites date+series, not a "page."
- `NONE` provenance ⇒ signal may not exist.
- `verified=false` caps authority (authority applies only to verified origins).

**Version pin:** `provenance_schema_version`.
**Authority ownership:** **MSIL** owns provenance + snapshot retention.
**Freeze decisions:** `provenance_type` enum; mandatory-snapshot rule; retention/immutability policy; `verified` semantics.

---

## 9. Authority Matrix Contract (Task 9)

**Purpose:** the versioned, **claim-type-scoped** authority mapping.

**Components**
- `authority_class` enum: `regulatory_independent`, `exchange_official`, `audited_issuer`, `official_issuer_unaudited`, `independent_opinion`, `sector_aggregate`, `market_revealed`, `news_media`.
- `claim_type` enum: `regulatory_compliance`, `corporate_action_fact`, `audited_fact`, `official_unaudited_fact`, `forward_expectation`, `descriptive`, `sentiment`, `sector_context`.
- `matrix`: for each `claim_type`, an ordered effective-authority ranking over `authority_class`.
- `special_rules`: `news_media` is **corroboration-only / never standalone fact authority**; `market_revealed` is **observation, never a fact-creator**.

**Invariants**
- Effective authority = function(`authority_class`, `claim_type`) — **never a single global rank**.
- Issuer dominates facts about itself but is low authority for its own forward optimism; independent regulator/analysts/market dominate compliance/forward claims.
- Every signal pins `authority_matrix_version`; re-weighting after a matrix change is an explicit, versioned operation (no silent re-scoring of history).

**Version pin:** `authority_matrix_version`.
**Authority ownership:** **MSIL** owns the matrix as a governed artifact; engines read it, never override it.
**Freeze decisions:** both enums; the matrix; the news/market special rules; the matrix-versioning/governance process.

---

## 10. Additive Consumption Contracts (Task 10)

All three are **additive and versioned** — they extend the engines' existing single-source inputs **without breaking the freshly-frozen MVPs**; engines may ignore unknown content classes (forward-compatible).

### 10.1 Forecast Validation Engine
| MSIL exposes | Rule |
|---|---|
| `numeric_claim` stream | **Gate candidates only** — FVE's integrity gate must extend to **non-OCR provenance**; MSIL never sends validated numbers. |
| `CorporateEvent` timeline | Dividend/capex/results events as forecast context. |
| `narrative_vs_numbers` Divergence | For FVE to evaluate against gate-admitted history. |
| entity/period binding | So FVE history aligns across sources. |
- **Version pin:** `fve_consumption_contract_version`. **Invariant:** numbers-to-FVE-under-gate; FVE never ingests raw sources.

### 10.2 Qualitative Analysis Engine
| MSIL exposes | Rule |
|---|---|
| `narrative_claim` (`QualitativeSignal`) stream | Tagged with source/authority/time; **QAE classifies themes**, MSIL does not. |
| corroboration + Divergence | Cross-source narrative context. |
| coverage caveats | So a "no-risk" silence is read as possible coverage gap, not absence. |
- **Version pin:** `qae_consumption_contract_version` (+ carried `taxonomy_version`). **Invariant:** narrative-to-QAE; MSIL never assigns themes.

### 10.3 Query Engine
| MSIL exposes | Rule |
|---|---|
| unified multi-source evidence store + timeline + provenance + entity index | For retrieval/citation across **all** provenance types. |
- **Version pin:** `query_consumption_contract_version`. **Invariant:** Query owns planning/answers; MSIL owns the substrate.

---

## 11. Version Pins (consolidated)

`entity_registry_version` · `resolution_logic_version` · `msil_schema_version` · `authority_matrix_version` · `provenance_schema_version` · `fve_consumption_contract_version` · `qae_consumption_contract_version` · `query_consumption_contract_version` (and `taxonomy_version` carried for narrative). **Every signal/event/divergence/corroboration/timeline record pins the versions it was produced under;** no record is interpreted under a different version without an explicit migration.

---

## 12. Authority Ownership (consolidated)

| Concern | Owner |
|---|---|
| Canonical identity (registry) | **MSIL** |
| Entity resolution | **MSIL** |
| Source authority class (matrix) | **MSIL** |
| Provenance + snapshot retention | **MSIL** |
| Event timeline + supersession | **MSIL** |
| Corroboration computation | **MSIL** |
| Divergence detection/surfacing | **MSIL** |
| Divergence adjudication | **owning engine** (FVE numbers / QAE narrative) |
| Number validation | **FVE** |
| Theme classification/assembly | **QAE** |
| Query planning/answers | **Query Engine** |

---

## 13. Hidden Dependencies & Master Freeze List

### Hidden dependencies
- **HD-1 — Entity registry frozen before any adapter** (every signal needs `entity_ref`); resolution truth set before correctness claims.
- **HD-2 — Snapshot storage/retention infra** before the provenance contract is real (citations rot otherwise).
- **HD-3 — Source authenticity/verification pipeline** (the `verified` flag is only meaningful with one).
- **HD-4 — Canonical Period/calendar model** underlies all time fields and the timeline.
- **HD-5 — FVE integrity gate must extend to non-OCR provenance** before FVE consumption is usable.
- **HD-6 — Engines' input contracts evolve additively + versioned**, or MSIL output is unconsumable / destabilizes frozen MVPs.
- **HD-7 — `source_lineage` captured at ingestion**, or corroboration circularity (news echoes) is undetectable.
- **HD-8 — Authority matrix governance process** (it is a living, versioned artifact spanning all sources).

### Freeze-before-implementation decisions (master)
1. `canonical_id` scheme + `entity_type`/`alias_type`/`rel_type` enums + merge/tombstone policy (§1).
2. Resolution tier + review/quarantine thresholds + fuzzy/news→review rule (§2).
3. `content_class` enum + `signal_id` scheme + per-class payload shapes + version-pin set (§3).
4. `event_type` enum + reference-not-copy rule (§4).
5. `divergence_type` enum + surfaced-never-resolved + authority-weighting method (§5).
6. Corroboration independence + circularity/lineage rule + bounded `strength` (§6).
7. Event-time axis + supersession rule (time + authority) + time-basis alignment (§7).
8. `provenance_type` enum + mandatory-snapshot + retention policy + `verified` semantics (§8).
9. `authority_class`/`claim_type` enums + the matrix + news/market special rules + versioning process (§9).
10. The three additive consumption-contract versions + the non-breaking/forward-compat rule (§10).

---

## 14. One-Paragraph Verdict

These ten contracts make MSIL implementable contracts-first: a frozen entity registry and a quarantine-not-force resolution layer establish *who* (the keystone); the `IntelligenceSignal` envelope with its content-class split establishes *what kind of thing* and routes it (numbers to FVE's gate, narrative to QAE, events to the timeline, market data to context); the authority matrix establishes *how authoritative* per claim type; provenance with mandatory immutable snapshots establishes *where to verify*; the timeline and supersession establish *when and what's current*; and corroboration and divergence establish *who agrees or disagrees* — independent-origin only, authority-weighted, never auto-resolved, with the news-echo circularity trap explicitly defeated by `source_lineage`. MSIL owns the substrate and only the substrate; FVE, QAE, and Query remain sovereign in numbers, themes, and answers, consuming MSIL through additive, versioned contracts that do not break their freshly-frozen single-source MVPs. Freeze the master decision list above — the enums, id schemes, thresholds, the matrix, the snapshot and supersession rules — before any adapter is built, because they are cheap now and ruinous to backfill, and because every one of them encodes a lesson this platform already paid to learn: resolve identity before trusting evidence, gate numbers before believing them, snapshot provenance before citing it, and never let source abundance be mistaken for source authority.
