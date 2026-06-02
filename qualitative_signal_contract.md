# QualitativeSignal — Canonical Contract

**Status:** Contract specification. No code. Focus: data contracts, provenance, authority, future source integration.
**Date:** 2026-06-02
**Derived from:** `qualitative_analysis_engine_architecture.md`, `qualitative_taxonomy_architecture.md`, `qualitative_analysis_multi_source_architecture_review.md`, and the existing `Insight` model.

---

## 0. Purpose and First Principles

`QualitativeSignal` is the **single atomic evidence unit** of the Qualitative Analysis Engine. Every theme is assembled from signals; every signal is one *narrative claim* about one *entity*, classified into the canonical taxonomy, tagged with *who said it*, *when*, *how authoritative*, and *where to verify it*.

Five invariants, frozen for all time:

1. **Source-agnostic core, source-specific provenance.** Every source produces the same `QualitativeSignal` shape; only the `provenance` sub-contract differs by source.
2. **The annual-report `Insight` is a *specialization*, not the base.** `Insight` maps onto a subset of `QualitativeSignal`; the base is wider.
3. **Signals are narrative only — never numeric authority.** A figure inside a source goes to the Forecast Validation Engine under the integrity gate; only the *narrative claim* becomes a `QualitativeSignal`. A signal may *reference* a number but may never *assert* it as validated.
4. **Three separate axes, never collapsed:** `signal_confidence` (reliability of extraction+classification), `evidence_weight` inputs (authority × recency × independence × specificity × corroboration — composed downstream), and materiality (theme-level). The contract stores the *inputs*; it never stores a single fused score.
5. **Every signal is reproducible:** it pins a taxonomy version, an authority-matrix version, and an immutable source snapshot.

---

## 1. The QualitativeSignal Model (Task 1)

Field groups: **Identity · Content · Classification · Source & Authority · Temporal · Provenance · Confidence · Relational.** Full field tables in §2; the discriminated-union `provenance` in §3; enums in §4–§5.

```
QualitativeSignal
├─ Identity        : signal_id, entity_ref, entity_scope, source_type, taxonomy_version, authority_matrix_version
├─ Content         : claim, raw_excerpt, is_quantified, specificity
├─ Classification  : category_ref, theme_ref, subtheme_ref, mapping_method, mapping_confidence, routing_basis, unmapped
├─ Source/Authority: claim_type, authority_class, source_independent_of_issuer, verified, trust_prior, source_lineage
├─ Temporal        : observation_time, subject_period, time_basis, horizon, supersedes, superseded_by
├─ Provenance      : provenance (discriminated by provenance_type) + snapshot_ref + retrieved_at
├─ Confidence      : extraction_confidence, structure_confidence, signal_confidence
└─ Relational      : creation_eligible, theme_role (assembly-time)
```

---

## 2. Required Fields (Task 2)

R = required, O = optional, D = derived (computed, not author-supplied).

### Identity
| Field | R/O | Semantics / invariant |
|---|---|---|
| `signal_id` | R (D) | Deterministic id. **Must NOT be a hash of `claim` text** (text churns with LLM re-extraction). Derive from `entity_ref + source_type + provenance locator + theme_ref + observation_time`. |
| `entity_ref` | R | Canonical entity id from the shared entity-resolution contract. |
| `entity_scope` | R | `company` / `sector` / `market`. Prevents sector/market signals contaminating company coverage. |
| `source_type` | R | One of the 7 source enums (§5). |
| `taxonomy_version` | R | Frozen taxonomy version used for classification. |
| `authority_matrix_version` | R | Frozen authority-matrix version used to scope authority (§4). |

### Content
| Field | R/O | Semantics |
|---|---|---|
| `claim` | R | Normalized narrative takeaway (the `Insight.takeaway` analog). |
| `raw_excerpt` | O (strongly recommended) | Verbatim source text for audit. |
| `is_quantified` | R (D) | Whether the claim carries a number (specificity input; reuse `_has_quantitative_evidence`). |
| `specificity` | R (D) | `named` / `generic` (reuse generic-pattern filter). Boilerplate is down-weighted, never a standalone theme. |

### Classification
| Field | R/O | Semantics |
|---|---|---|
| `category_ref` | R if classified | Canonical content category. |
| `theme_ref` | R if classified | Canonical theme (one per signal — anti-double-count rule). |
| `subtheme_ref` | O | Canonical sub-theme or `other`. |
| `mapping_method` | R | `exact` / `alias` / `keyword` / `section_only` / `unmapped`. |
| `mapping_confidence` | R | From the mapping tier. |
| `routing_basis` | R | `section_prior` (report only) / `adapter_signal` / `none`. |
| `unmapped` | R | First-class flag; unmapped signals are surfaced, never dropped or force-fit. |

### Source & Authority
| Field | R/O | Semantics |
|---|---|---|
| `claim_type` | R | §4 enum. Content-derived; drives authority scoping. |
| `authority_class` | R | §4 enum. Source-derived. |
| `source_independent_of_issuer` | R | Independence input for corroboration weighting. |
| `verified` | R | Whether provenance origin is authenticated (regulator/exchange/issuer official) vs scraped/unverified. |
| `trust_prior` | R | Per-source baseline trust (§5). |
| `source_lineage` / `derived_from` | O | Upstream origin(s) — detects circular corroboration (analyst report derived from the annual report). |

### Temporal — see §5 event_time contract
| Field | R/O | Semantics |
|---|---|---|
| `observation_time` | R | When the claim was made/published. |
| `subject_period` | O (nullable) | The period the claim is *about*; null for static/sentiment. |
| `time_basis` | R | `fiscal` / `calendar` / `continuous` / `static`. |
| `horizon` | R | `historical` / `current` / `forward`. |
| `supersedes` / `superseded_by` | O | Supersession links across time/sources. |

### Provenance — see §3
| Field | R/O | Semantics |
|---|---|---|
| `provenance` | R | Discriminated by `provenance_type`. |
| `snapshot_ref` | R for ephemeral sources | Immutable stored snapshot / content hash. |
| `retrieved_at` | R for external sources | Fetch timestamp. |

### Confidence — see §6
| Field | R/O | Semantics |
|---|---|---|
| `extraction_confidence` | R | Reliability of the claim extraction. |
| `structure_confidence` | O | Section-ID confidence (reports) or equivalent; null where no structure. |
| `signal_confidence` | R (D) | `min(extraction, mapping, structure-if-present)`. |

### Relational
| Field | R/O | Semantics |
|---|---|---|
| `creation_eligible` | R (D) | From `source_type` via the create/strengthen/contradict matrix. `daily_market_summary` and `company_overview` = false. |
| `theme_role` | O (assembly-time) | `creates` / `strengthens` / `contradicts` / `contextualizes` — assigned during theme assembly, not at ingestion. |

---

## 3. Source-Specific Provenance Contracts (Task 3)

`provenance` is a **discriminated union** keyed by `provenance_type` (which equals the citation type). Each variant lists its required locators. **Every non-PDF variant must carry an immutable `snapshot_ref`** because web/market/announcement content is ephemeral — without it the platform's citation guarantee breaks (HR-B).

| `provenance_type` | Source(s) | Required locators | Snapshot |
|---|---|---|---|
| `PDF_PAGE` | annual_report | `page_number`, `source_section`, `workbook_fingerprint` | workbook fingerprint (already immutable) |
| `ANNOUNCEMENT_REF` | company_announcements | `exchange`, `announcement_id`, `announcement_date`, `url` | **required** snapshot/content hash |
| `REGULATORY_REF` | secp_notices | `regulator`, `notice_id`, `notice_date`, `url` | **required** |
| `URL_SNAPSHOT` | company_overview, analysis_reports | `url`, `publisher`, `document_date`, `retrieved_at` | **required** content hash + stored copy |
| `MARKET_DATA_REF` | daily_market_summary | `market_date`, `series_or_ticker`, `dataset` | **required** (daily summaries are ephemeral) |
| `SECTOR_REF` | sector_summary | `sector_id`, `provider`, `summary_date` | **required** |
| `NONE` | any | — | A signal that resolves to `NONE` provenance **may not be emitted** (anti-hallucination rule). |

Provenance precision must be honest: a PDF signal cites page-level, not sentence-level; a market signal cites a date and series, not a "page." No variant may claim precision it does not have.

---

## 4. Authority Classes (Task 4)

Authority is **claim-type-scoped**: a source authoritative for one claim class is noise for another. The signal carries `authority_class` (from source) and `claim_type` (from content); the engine derives the **effective authority** via the frozen `authority_matrix`.

**`authority_class` enum**
- `regulatory_independent` (SECP)
- `audited_issuer` (annual report)
- `official_issuer_unaudited` (announcements)
- `issuer_descriptive` (overview)
- `independent_opinion` (analysis reports)
- `sector_aggregate` (sector summary)
- `market_revealed` (daily market summary)

**`claim_type` enum**
- `regulatory_compliance` · `audited_fact` · `official_unaudited_fact` · `forward_expectation` · `descriptive` · `sentiment` · `sector_context`

**Effective-authority matrix (frozen, versioned) — illustrative ranking by claim type**
| Claim type | Highest → lowest effective authority |
|---|---|
| `regulatory_compliance` | regulatory_independent → audited_issuer → official_issuer_unaudited |
| `audited_fact` | audited_issuer → official_issuer_unaudited → independent_opinion |
| `forward_expectation` | independent_opinion / official_issuer_unaudited (guidance) → market_revealed → audited_issuer (outlook) |
| `descriptive` | issuer_descriptive (audited cross-check) |
| `sentiment` | market_revealed |
| `sector_context` | sector_aggregate / independent_opinion |

The inversion is the point: **the issuer dominates facts about itself but is *low* authority for its own forward optimism**; independent regulator/analysts/market dominate compliance and forward claims. A single global ranking is prohibited.

---

## 5. event_time Contract (Task 5)

Generalizes the `Insight` pair (`value_year` = what it's about; `source_report_year` = where it was found) into a source-agnostic time model.

| Field | Generalizes | Values |
|---|---|---|
| `observation_time` | `source_report_year` | When stated/published: report publication, announcement/notice date, market date, snapshot date. **Always present.** |
| `subject_period` | `value_year` | What the claim is *about*: a fiscal year, a future guidance period, a range, `current`, or **null** (static/sentiment). Nullable by design — forcing a value fabricates false temporal alignment (HR-E). |
| `time_basis` | (new) | `fiscal` (reports), `calendar` (events/notices/analysis), `continuous` (market), `static` (overview). |
| `horizon` | (new) | `historical` / `current` / `forward` — drives recency weighting and the authority inversion. |
| `supersedes` / `superseded_by` | (new) | A later announcement can mark a report theme `superseded`; both are retained and cited, never deleted. |

Cross-time invariants:
- Comparisons (recurring/YoY/divergence) may only run **within one `time_basis`** or through an explicit alignment rule; mixing fiscal and calendar without alignment is prohibited.
- "Latest" is defined on `observation_time`; "trend" is defined on `subject_period`. They must not be conflated.

---

## 6. Confidence Inputs (Task 6)

`signal_confidence` is reliability only and composes by flooring (consistent with the platform's `min` pattern):

```
signal_confidence = min(
    extraction_confidence,            # how reliably the claim was extracted from the source
    mapping_confidence,               # taxonomy tier: exact/alias/keyword/unmapped
    structure_confidence              # section-ID confidence for reports; omitted where absent
)
```
- **Ceilings:** keyword-tier mapping and `review`-routed inputs cap `signal_confidence` (carry-over from taxonomy + insight governance).
- **`unmapped` signals** carry low/no mapping confidence and are excluded from theme salience.

**Confidence is not evidence weight.** `evidence_weight` is composed downstream from authority(claim-type-scoped) × recency(horizon) × independence × specificity × corroboration — and is **theme/context-relative**, so it is *not* stored on the signal. The signal stores the **weight inputs** (`authority_class`, `claim_type`, `observation_time`, `horizon`, `source_independent_of_issuer`, `source_lineage`, `is_quantified`, `specificity`). **Confidence is not materiality** either — materiality is a theme-level judgment.

---

## 7. annual-report `Insight` → QualitativeSignal (Task 7)

| QualitativeSignal field | Source from `Insight` | Notes |
|---|---|---|
| `claim` | `takeaway` | direct |
| `category_ref` / `theme_ref` / `subtheme_ref` | from `area` + `source_section` via taxonomy | per taxonomy contract |
| `routing_basis` | `section_prior` | reports keep the reliable section axis |
| `mapping_method` / `mapping_confidence` | taxonomy canonicalization of `area` | |
| `claim_type` | **derived** from `source_section` | Outlook/CEO/Chairman → `forward_expectation`; Risks/Business/Financial Review → `audited_fact`; Governance/Directors → `regulatory_compliance`-adjacent |
| `authority_class` | `audited_issuer` | fixed |
| `source_independent_of_issuer` | `false` | |
| `verified` | `true` | audited |
| `observation_time` | `source_report_year` | publication |
| `subject_period` | `value_year` | fiscal |
| `time_basis` | `fiscal` | |
| `horizon` | derived (`historical` or `forward` for outlook) | |
| `provenance` | `PDF_PAGE` with `page_number`, `source_section`, `workbook_fingerprint` | |
| `extraction_confidence` | `confidence` | |
| `structure_confidence` | section-ID confidence (`SectionIdentificationReport`) | |
| `creation_eligible` | `true` | |
| `trust_prior` | high | |

**Two derivations are themselves mini-classifiers** (`claim_type` and `horizon` from section) — flagged in §10 HR.

---

## 8. The Six New Sources → QualitativeSignal (Task 8)

| Field | company_announcements | secp_notices | company_overview | analysis_reports | sector_summary | daily_market_summary |
|---|---|---|---|---|---|---|
| `entity_scope` | company | company | company | company | **sector** | market/company |
| `claim_type` | official_unaudited_fact / forward_expectation (guidance) | regulatory_compliance | descriptive | forward_expectation (opinion) | sector_context | sentiment |
| `authority_class` | official_issuer_unaudited | regulatory_independent | issuer_descriptive | independent_opinion | sector_aggregate | market_revealed |
| `independent_of_issuer` | false | true | false | true (check lineage) | true | true |
| `routing_basis` | adapter_signal | adapter_signal | adapter_signal | adapter_signal | adapter_signal | adapter_signal |
| `observation_time` | announcement_date | notice_date | snapshot_date | report_date | summary_date | market_date |
| `subject_period` | event period | referenced period | null (static) | forecast period | period | trading day |
| `time_basis` | calendar | calendar | static | calendar | calendar/continuous | continuous |
| `horizon` | current/forward | current/historical | current | forward | current | current |
| `provenance_type` | ANNOUNCEMENT_REF | REGULATORY_REF | URL_SNAPSHOT | URL_SNAPSHOT | SECTOR_REF | MARKET_DATA_REF |
| `creation_eligible` | ✓ (events) | ✓ (regulatory/governance) | ✗ | ✓ **opinion-class only** | ✓ **sector-level only** | ✗ (overlay) |
| `trust_prior` | medium-high | high | low-medium | medium | medium | low standalone / high divergence |
| typical category prior | events → strategy/outlook/risk | governance/business_risk | descriptive context | any (opinion) | sector | sentiment overlay |

Hard mapping rules:
- **`daily_market_summary` and `company_overview` carry `creation_eligible = false`** — they may only strengthen/contradict.
- **`analysis_reports` and `sector_summary` creations are quarantined** into opinion/sector evidence classes; they may never be promoted to issuer-fact.
- **`sector_summary` uses `entity_scope = sector`** — its signals never count toward a company's coverage.
- **All six lose the section axis** → `routing_basis = adapter_signal`; expect higher `unmapped` rates than reports (HR).

---

## 9. Fields That Must Be Frozen Before Implementation (Task 9)

These are the structural/enum/scaffolding fields whose later change forces a full re-ingestion or breaks comparability — freeze them before any adapter or theme-assembly code:

1. **`signal_id` derivation scheme** (text-independent, supersession-stable).
2. **`source_type` enum** (the 7 sources) and **`entity_scope` enum**.
3. **`claim_type` and `authority_class` enums + the `authority_matrix` (versioned)**.
4. **event_time contract:** `observation_time`, `subject_period` (nullable), `time_basis`, `horizon`, supersession links.
5. **`provenance` discriminated-union shape + `provenance_type` enum + mandatory `snapshot_ref`/`retrieved_at` rules.**
6. **Classification field set:** `category_ref`, `theme_ref`, `subtheme_ref`, `mapping_method`, `routing_basis`, `unmapped`.
7. **Confidence-input slots** (`extraction_confidence`, `structure_confidence`, `mapping_confidence`) and the separation of **confidence vs weight-inputs vs materiality** (no fused score field).
8. **`creation_eligible` derivation** from `source_type` (the create/strengthen/contradict matrix).
9. **Independence/authenticity fields:** `source_independent_of_issuer`, `verified`, `source_lineage`.
10. **Version pins:** `taxonomy_version` + `authority_matrix_version` on every signal.

Items 1–10 are the contract the gate, theme assembly, scorecard, and every future adapter depend on — the same "contracts first" discipline that succeeded for Forecast Validation and whose absence caused its Phase 9 drift.

---

## 10. Hidden Risks (Task 10)

- **HR-1 — `claim_type` ↔ authority coupling.** Authority is derived from `claim_type`, but `claim_type` is itself a classification (Outlook→forward, Risks→fact). A mislabeled `claim_type` silently mis-weights authority (e.g. guidance treated as audited fact). *Mitigation:* `claim_type` derivation rules are a frozen, audited mini-contract; conflicts logged as evidence.
- **HR-2 — `signal_id` churn.** If the id depends on `claim` text, OCR/LLM re-extraction variability (the OCR freeze recorded insight counts 198→175 across runs) churns ids → dedup and supersession break. *Mitigation:* id from entity+theme+observation_time+provenance-locator, not text.
- **HR-3 — Snapshot storage burden / ephemerality.** The citation guarantee now depends on storing immutable snapshots of web/market/announcement content; without a retention contract, citations rot. *Mitigation:* mandatory `snapshot_ref` + a defined retention/immutability policy per source.
- **HR-4 — Forced `subject_period` fabricates time.** Static/sentiment signals have no subject period; forcing one creates false temporal alignment and phantom YoY signals. *Mitigation:* `subject_period` is explicitly nullable; cross-time comparison guards.
- **HR-5 — Entity-scope contamination.** A sector or market signal mis-scoped as `company` inflates a company's coverage/themes with non-company content. *Mitigation:* `entity_scope` required; sector/market signals excluded from company coverage counting.
- **HR-6 — Numeric-authority leakage.** Pressure to let a quantified announcement signal ("capacity 12m tons") act as a number. *Mitigation:* reaffirm signals are narrative-only; numbers split to FVE under the gate; `is_quantified` is a *specificity* input, not a value.
- **HR-7 — Single-score regression.** Future convenience pressure to store one "score" collapses the confidence/weight/materiality separation. *Mitigation:* contract forbids a fused score field; weight is computed downstream from inputs.
- **HR-8 — Circular corroboration.** Analyst/sector signals derived from the annual report counted as "independent" confirmation. *Mitigation:* `source_lineage`/`derived_from` required where known; corroboration weight only for genuinely independent origins.
- **HR-9 — `Insight` backfill gap.** The existing `Insight` lacks most of these fields; the report adapter must *derive* `claim_type`, `horizon`, `authority_class`, `entity_scope`, snapshot binding. Derivation correctness is unverified without a truth set (platform-wide open assurance gap). *Mitigation:* derivations are deterministic + audited; flagged as a pre-freeze validation item.
- **HR-10 — Authority-matrix versioning drift.** The authority matrix is a living contract; if a signal does not pin `authority_matrix_version`, re-weighting after a matrix change silently changes historical conclusions. *Mitigation:* pin `authority_matrix_version` per signal; re-weighting is an explicit, versioned operation.

---

## 11. One-Paragraph Verdict

`QualitativeSignal` is the contract that lets one source-agnostic taxonomy carry evidence from seven heterogeneous sources without fragmenting: a single atomic claim about one entity, classified into the canonical taxonomy, tagged with a claim-type-scoped authority class, placed on a generalized `observation_time`/`subject_period` axis, cited through a source-specific but uniformly-immutable provenance union, and scored on a confidence axis kept strictly separate from evidence weight and materiality. The annual-report `Insight` becomes one specialization of it, and the six future sources slot in through per-source adapters that differ only in provenance, authority, temporality, and creation rights — while the classification target stays one vocabulary. The non-negotiables to freeze now are the enums and the discriminated-union shape (source/claim/authority types, the event-time fields, the provenance variants with mandatory snapshots, and the version pins), because they are cheap today and ruinous to backfill — and the sharpest hidden risks are the `claim_type`↔authority coupling, text-derived id churn, snapshot rot, and any future pressure to collapse the three measurement axes into one score or to let a quantified signal masquerade as a validated number.
