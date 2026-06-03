# Multi-Source Intelligence Layer (MSIL) — Architecture

**Status:** Architecture proposal. No code. Focus: architecture, contracts, authority, evidence, future integration.
**Date:** 2026-06-02
**Position:** Shared substrate beneath the four engines (OCR, Query, Forecast Validation, Qualitative Analysis). **MSIL is not a fifth analysis engine.**
**Builds on:** `qualitative_analysis_multi_source_architecture_review.md`, `qualitative_signal_contract.md`, `qualitative_theme_assembly_contract.md`, `qualitative_scorecard_contract.md`, and the FVE contracts.

**Future inputs in scope:** PSX Announcements, SECP Notices, Company Overview, Company Payouts, Market Watch, Futures Market Watch, Sector Summary, Analysis Reports, News Sources — plus the existing **annual report (OCR)**, which MSIL absorbs as *source #1*.

---

## 0. What MSIL Is (and Is Not)

MSIL is the **ingestion, entity-resolution, normalization, authority, provenance, and timeline substrate** that every analysis engine consumes. It answers the source-agnostic questions — *who, when, from where, how authoritative, supersedes what, agrees/disagrees with what* — and routes evidence to the right engine. It does **not** validate numbers (FVE), assemble themes (QAE), or answer questions (Query Engine).

Two decisions define it:

1. **Entity resolution is the keystone.** Every signal must bind to the right company *and* period across heterogeneous identifiers. A mis-link injects another issuer's evidence into a company's profile — the highest-severity failure in the platform. This is built first and gates everything.
2. **The content-class split is the universal routing contract.** Every incoming unit is classified by *what kind of thing it asserts* — **numeric claim → FVE (under the integrity gate), narrative claim → QAE, corporate event → timeline, market observation → context** — and one class may never masquerade as another. This generalizes the established numbers-to-FVE / narrative-to-QAE rule to all nine sources.

---

## 1. Responsibilities (Task 1)

1. **Source ingestion adapters** — one per source; normalize raw input into the common envelope.
2. **Entity resolution** — bind every signal to a canonical entity + period (§4).
3. **Normalization** — emit `IntelligenceSignal`s with content_class, authority, time, provenance (§5).
4. **Authority & claim-type assignment** — per the versioned, claim-type-scoped matrix (§6).
5. **Provenance + immutable snapshot** — reproducible citation for every signal (§11).
6. **Event-timeline construction** — unified event-time backbone (§9).
7. **Supersession tracking** — mark current vs superseded, never delete (§10).
8. **Cross-source corroboration & contradiction** — independent-origin corroboration + authority-weighted `Divergence` (§7, §8).
9. **Consumption contracts** — route/expose evidence to FVE, QAE, Query Engine (§12).

**Not MSIL:** numeric validation, theme classification/assembly, query planning/answering, forecasting, OCR.

---

## 2. Boundaries (Task 2)

| Engine | MSIL provides | MSIL must NOT do | Engine must NOT do |
|---|---|---|---|
| **OCR Engine** | MSIL *consumes* OCR's `.kb.json` as the `annual_report` source adapter | Re-do PDF→structured extraction | — (OCR is upstream of MSIL for that source) |
| **Forecast Validation** | Numeric-claim candidates + event timeline + narrative-vs-numbers divergences + entity/period binding | Validate numbers; never hand FVE a "validated" value | Ingest raw sources directly; resolve entities |
| **Qualitative Analysis** | Narrative signals (`QualitativeSignal`) + cross-source corroboration/divergence + coverage caveats | Classify themes; assign taxonomy | Ingest raw sources; resolve entities; assess source authority |
| **Query Engine** | Unified multi-source evidence store + timeline + provenance + entity index for retrieval/citation | Plan or answer queries | Ingest/normalize sources; build the timeline |

**Authority split:** MSIL is the authority on **entity, time, provenance, and source-authority-class**. It is *not* the authority on **numbers** (FVE), **themes** (QAE), or **answers** (Query). Each engine remains sovereign in its domain; MSIL is sovereign only over the shared substrate.

---

## 3. Canonical Entities (Task 3)

| Entity | Role | Notes |
|---|---|---|
| **Company** | Primary issuer identity | The group/subsidiary problem is real here (Lucky Cement vs Lucky Core vs Lucky Motor) — distinct companies under one group. |
| **Security** | A listed instrument of a Company | A company may have multiple securities; tickers are security-level, not company-level. |
| **Futures Instrument** | A derivative on a Security | Links to Security → Company; Futures Market Watch lands here. |
| **Sector** | Aggregate of Companies | Sector Summary scopes here; never a company. |
| **Person** | Board/management individual | For governance, board changes, news mentions. |
| **Event** | A dated corporate occurrence | First-class (§9). |
| **Period** | Fiscal or calendar time span | Bridges fiscal (reports) and calendar (events/market) time. |
| **Source** | A publisher/origin | Carries authority_class + lineage. |

Companies, securities, futures, and persons form a linked **canonical entity registry** (a frozen, versioned contract). `entity_scope` (company / security / sector / market / person) is required on every signal.

---

## 4. Entity-Resolution Requirements (Task 4) — the keystone

- **Deterministic-first, tiered:** exact canonical id → registered alias (ticker, SECP registration no., legal-name variant) → fuzzy match with confidence + review threshold → **unresolved → quarantine** (never force-assign).
- **Every signal carries** `entity_ref`, `entity_scope`, `entity_resolution_method`, `entity_resolution_confidence`, and `raw_identifier`.
- **Group/subsidiary disambiguation is mandatory** — consolidated vs standalone, parent vs subsidiary; resolving "Lucky" to the wrong group entity contaminates the profile.
- **Security ↔ Company mapping** — tickers and futures resolve to a Security, which resolves to a Company; market/futures signals must not be attributed directly to a Company without this link.
- **Period resolution** — bind to fiscal vs calendar period; a calendar-dated announcement about FY25 must resolve both.
- **News is the hardest case** — name mentions, no structured id, ambiguous references; news entity resolution defaults to **low confidence + review**, never silent attribution.
- **Resolution audit + review queue** — mis-resolution is the top-severity failure; an audit artifact and human review path are required, not optional.
- **No correctness claim without a resolution truth set** (the platform-wide assurance discipline applies here first).

---

## 5. Evidence Model (Task 5)

The **`IntelligenceSignal`** is the common envelope; `QualitativeSignal` becomes its **narrative specialization**. Four content classes share one envelope:

| content_class | Routes to | Payload |
|---|---|---|
| `numeric_claim` | **FVE (gate candidate)** | value, unit/scale, metric ref, *unvalidated* |
| `narrative_claim` | **QAE** | claim text, candidate theme (QAE classifies) |
| `corporate_event` | **Timeline** | event_type, linked numeric/narrative refs |
| `market_observation` | **Context / Query** | price/volume/OI series ref; never a fact-creator |

Common envelope fields (frozen):
- **Identity:** `signal_id` (deterministic, **text-independent**), `entity_ref`, `entity_scope`, `entity_resolution{method,confidence}`.
- **Source/authority:** `source_type`, `content_class`, `claim_type`, `authority_class`, `source_independent_of_issuer`, `verified`, `source_lineage`, `trust_prior`.
- **Time:** `observation_time`, `subject_period` (nullable), `time_basis` (fiscal/calendar/continuous/static), `horizon` (historical/current/forward).
- **Provenance:** discriminated union + `snapshot_ref` + `retrieved_at` (§11).
- **Relations:** `supersedes` / `superseded_by`, `corroboration_group`, `divergence_refs`.
- **Versions:** `msil_schema_version`, `authority_matrix_version`, `entity_registry_version`.

Invariant: **no signal without immutable provenance** (a `NONE`-provenance unit may not be emitted), and **numbers are never asserted as validated** — they are candidates for FVE's gate.

---

## 6. Authority Hierarchy (Task 6) — claim-type-scoped

Authority is **not a single rank**; it is scoped by claim type via the versioned `authority_matrix`.

**`authority_class` enum (nine sources + annual report):**
`regulatory_independent` (SECP) · `exchange_official` (PSX Announcements, Company Payouts, Market/Futures Watch as exchange-published facts) · `audited_issuer` (annual report) · `official_issuer_unaudited` (issuer announcements, overview) · `independent_opinion` (Analysis Reports) · `sector_aggregate` (Sector Summary) · `market_revealed` (Market Watch, Futures) · `news_media` (News Sources).

**Effective authority by claim type (illustrative, frozen + versioned):**
| Claim type | Highest → lowest |
|---|---|
| Regulatory/compliance | regulatory_independent → audited_issuer → official_issuer_unaudited |
| Corporate-action fact (dividend, results) | exchange_official / company_payouts → official_issuer_unaudited → news_media |
| Audited financials | audited_issuer → official_issuer_unaudited → independent_opinion |
| Forward expectation | independent_opinion / issuer guidance → market_revealed → audited_issuer outlook |
| Market price/sentiment | market_revealed (Market/Futures) |
| Sector context | sector_aggregate / independent_opinion |
| Any (news) | **news_media is corroboration-only; never a standalone fact authority; requires verification + corroboration** |

Two new low/special classes vs the earlier six-source review:
- **News (`news_media`)** — highest recency, lowest authority, hardest entity resolution; may **never create a fact** alone (§8 circularity).
- **Market/Futures (`market_revealed`)** — observation, not assertion; high divergence value, low standalone weight.

---

## 7. Contradiction Model (Task 7)

- MSIL **detects** cross-source contradictions for the same entity + subject and emits the shared **`Divergence`** record (the contract already shared with QAE/FVE).
- Types: narrative-vs-narrative (→QAE), narrative-vs-numbers (→FVE), **fact-vs-fact** (issuer announcement vs SECP notice), **sentiment-vs-fundamentals** (market sell-off vs issuer optimism).
- Rules: **both sides retained with `authority_class`; authority-weighted; never auto-resolved; never equal-weighted.** MSIL surfaces; the consuming engine adjudicates within its domain; **MSIL never decides truth.**
- News-sourced contradictions are flagged **low-authority pending corroboration** — a news claim contradicting an audited figure is recorded, not elevated.

---

## 8. Corroboration Model (Task 8)

- Credit only for **genuinely independent origins** (distinct `authority_class` **and** no `source_lineage` link).
- **The news circularity trap (new, critical):** news routinely *re-reports* PSX announcements and analyst notes. A news echo of an issuer announcement is **not** independent corroboration. MSIL must record `source_lineage`/`derived_from` so echoed content is not counted as confirmation.
- Strong corroboration = independent classes agreeing (SECP + exchange + market). **Company Payouts confirming an announced dividend** is exchange-confirming-issuer — strong, structured corroboration.
- Strength = count of *independent* origins; bounded, diminishing. Corroboration raises evidence weight within ceilings; it can never promote an opinion/news class to fact class.

---

## 9. Event & Timeline Model (Task 9)

- **`CorporateEvent`** is first-class: dividend declared/paid (Payouts), results announced (PSX), board/management change, capacity commissioned, rights/bonus issue, SECP action, rating change.
- Each event: `event_type`, `entity_ref`, `event_time`, provenance, and **links to** its numeric claims (→FVE) and narrative (→QAE).
- The **timeline** is the ordered per-entity event sequence on a **unified event-time axis** — this is the shared temporal backbone that resolves the multi-source temporal-misalignment risk (fiscal vs calendar vs continuous). "Latest" is defined on `observation_time`; "trend/history" on `subject_period`; the two are never conflated.
- The timeline is the substrate FVE uses for event-aware forecast context and QAE uses for recurring/YoY narrative anchoring.

---

## 10. Supersession Model (Task 10)

- A later signal/event **supersedes** an earlier one about the same entity + subject when `observation_time` is later **and** authority ≥ the prior's (a news item may **not** supersede an audited figure; revised results supersede preliminary; final dividend supersedes intent; the annual report supersedes interims).
- Supersession is **explicit links** (`supersedes`/`superseded_by`), **never deletion** — both retained with provenance; consumers default to current and may inspect history.
- Supersession requires same entity + same subject + monotonic time + non-decreasing authority — encoded as a frozen rule, not heuristic.

---

## 11. Source Provenance Requirements (Task 11)

`provenance` is a discriminated union; **every non-PDF source requires an immutable `snapshot_ref`** (content hash + stored copy) because web/market/news content is ephemeral.

| provenance_type | Sources |
|---|---|
| `PDF_PAGE` | annual_report (fingerprinted) |
| `ANNOUNCEMENT_REF` | PSX Announcements |
| `REGULATORY_REF` | SECP Notices |
| `PAYOUT_REF` | Company Payouts |
| `MARKET_DATA_REF` | Market Watch |
| `FUTURES_REF` | Futures Market Watch |
| `SECTOR_REF` | Sector Summary |
| `URL_SNAPSHOT` | Company Overview, Analysis Reports |
| `NEWS_REF` | News Sources (publisher + url + snapshot mandatory) |
| `NONE` | **forbidden** — a signal with no citation may not be emitted |

Each carries `retrieved_at`, a `verified` flag (authenticated-origin vs scraped), and `source_lineage`. **No false precision** — a market signal cites a date+series, not a "page."

---

## 12. Contracts Consumed by Each Engine (Task 12)

**FVE consumes** (additive, versioned):
- `numeric_claim` stream as **gate candidates** (payout amounts, announced capacity, analyst targets) — **never pre-validated**; FVE's integrity gate must extend to non-OCR provenance.
- `CorporateEvent` timeline (dividends/capex/results) as forecast context.
- narrative-vs-numbers `Divergence` records.
- entity/period binding.

**QAE consumes:**
- `narrative_claim` (`QualitativeSignal`) stream tagged with source/authority/time.
- cross-source corroboration + `Divergence`.
- multi-source coverage caveats (so a "no-risk" silence is read as possible gap, not absence).

**Query Engine consumes:**
- the unified multi-source **evidence store + timeline + provenance + entity index** for retrieval/citation across all provenance types.

**All three consume the shared:** entity registry, authority matrix, event-time axis, `Divergence` contract, and version pins. All consumption contracts are **additive** — they extend the engines' existing single-source inputs without breaking the just-frozen MVPs.

---

## 13. Hidden Dependencies (Task 13)

- **HD-1 — Entity resolution is the universal prerequisite.** Group/subsidiary structure is a present, real problem; nothing downstream is trustworthy until resolution + a resolution truth set exist.
- **HD-2 — Immutable snapshot storage/retention infra.** Citations rot for news/market/web without it.
- **HD-3 — Source authenticity/verification pipeline** (official vs scraped) — authority applies only to verified origins.
- **HD-4 — Canonical Period/calendar model** bridging fiscal/calendar/continuous time.
- **HD-5 — The engines' input contracts are single-source today.** QAE just froze single-source; FVE is single-source readiness-MVP. MSIL introduces a multi-source store — the consuming contracts must evolve **additively and versioned**, or MSIL output is unusable.
- **HD-6 — FVE's integrity gate was built for OCR-consolidated values.** Ingesting external numbers (payouts, targets) requires the gate to handle non-OCR provenance and authority.
- **HD-7 — Heterogeneous ingestion cadence** (annual = yearly, market = continuous, news = streaming) → the layer must handle differing freshness, staleness, and supersession rates.
- **HD-8 — The authority matrix and entity registry are themselves versioned governance artifacts** spanning all sources; both must be frozen before adapters, or each adapter re-implements authority ad hoc (the taxonomy-drift analog).

---

## 14. Sequencing Risks (Task 14)

- **SR-1 — Building MSIL on moving foundations.** QAE/FVE are single-source and freshly frozen/readiness-grade. Start MSIL only after their single-source contracts are stable, and evolve their consumption contracts additively.
- **SR-2 — Entity-resolution-last instead of first.** Resolution is the keystone; building adapters before it repeats the platform's "contracts-first" lesson in reverse. Build registry + resolution first.
- **SR-3 — Starting with the abundant-but-riskiest sources.** News, Market, and Futures are highest-volume and most tempting, but lowest-authority, hardest to resolve, and most prone to circular corroboration. They must come **last**, not first.
- **SR-4 — Over-building corroboration/divergence depth on synthetic data** before two real independent sources exist (the FVE Phase 9 / QAE over-build trap). Prove the split, timeline, and divergence on a small real source set first.
- **SR-5 — Scope creep into engine domains** (MSIL drifting into validation/themes/answers). Hold the substrate boundary.
- **SR-6 — Coverage-illusion at the source level** (the QAE/FVE lesson generalized): a company with heavy news but no analyst coverage must not look "better covered" than one with sparse data. Per-source coverage reporting is mandatory from day one.

---

## 15. MVP Scope (Task 15)

**Build, in order:**
1. **Entity registry + entity resolution** (deterministic-first, group/subsidiary aware, review queue, resolution audit) — the keystone, first.
2. **The shared contracts:** `IntelligenceSignal` envelope, content-class split, provenance union + snapshot, authority matrix, event-time axis, `Divergence` + supersession.
3. **Absorb the annual report (OCR `.kb.json`) as source #1** — keeps existing engines working unchanged.
4. **Integrate the official, structured, low-noise, event-bearing sources:** **PSX Announcements + Company Payouts + SECP Notices.** These prove every MSIL mechanism on real data — the split (payout numbers → FVE, announcement narrative → QAE, results → timeline), corroboration (payouts confirm announcements), supersession (revised results), authority inversion (SECP > issuer), and entity resolution via exchange ids.
5. **Additive consumption contracts** to FVE (numeric candidates + events), QAE (narrative + divergence), Query (evidence store + timeline) — versioned, non-breaking.

**Defer (post-MVP, in roughly this order):** Sector Summary, Company Overview, Analysis Reports (opinion/context), then **Market Watch, Futures Market Watch, News Sources** last — the high-volume, low-authority, hardest-to-resolve, circular-corroboration-prone sources.

**Honest MVP framing:** MSIL MVP = "**official, structured, entity-resolvable, event-bearing sources integrated on a shared timeline, with numbers gated to FVE, narrative to QAE, and authority-weighted divergence surfaced**" — explicitly **not** "all nine sources fused." Like every freeze in this platform, it ships as a substrate with a respected gate, not as autonomous multi-source truth.

---

## 16. One-Paragraph Verdict

MSIL is the shared substrate the multi-source future requires — an ingestion, entity-resolution, normalization, authority, provenance, and timeline layer that feeds the four engines without absorbing their jobs. Its design turns on two non-negotiables proven across the platform: **entity resolution is the keystone** (a mis-link is the worst failure, and group/subsidiary structure makes it a present danger), and **the content-class split is the universal routing contract** (numbers to FVE's gate, narrative to QAE, events to the timeline, market data to context — never one masquerading as another). Authority must stay claim-type-scoped, corroboration must require genuinely independent origins (so news echoes of issuer announcements never count as confirmation), contradictions must be surfaced authority-weighted and never auto-resolved, and every signal must carry immutable, snapshot-backed provenance. Build it entity-resolution-first, absorb the annual report as source #1, prove every mechanism on the official structured triad (PSX Announcements, Company Payouts, SECP Notices), and defer the abundant-but-noisy sources (Market, Futures, News) to last — evolving the engines' consumption contracts additively so the freshly-frozen single-source MVPs keep working. Ship it as a coverage-honest substrate, never letting source abundance be mistaken for source authority.
