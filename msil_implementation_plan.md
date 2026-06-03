# Multi-Source Intelligence Layer (MSIL) — Implementation Plan

**Status:** Implementation sequencing plan. No code. **All MSIL contracts assumed frozen per `multi_source_intelligence_contracts.md`.**
**Date:** 2026-06-02
**Sources:** `multi_source_intelligence_architecture.md`, `multi_source_intelligence_contracts.md`.
**Target module:** `backend/multi_source_intelligence/` (substrate beneath OCR/Query/FVE/QAE).

---

## 0. Sequencing Principles

1. **Contracts before adapters.** Freeze enums, the entity registry, and the authority matrix before any source ingestion (the taxonomy-drift lesson, generalized).
2. **Entity resolution first.** The registry + resolution layer is the keystone (HD-1); **no source is ingested until resolution works**, because a mis-link is the platform's highest-severity failure.
3. **Official structured sources before news/market.** Prove every mechanism on **PSX Announcements + Company Payouts + SECP Notices** (official, structured, entity-resolvable, event-bearing) before touching the abundant-but-noisy sources (Market, Futures, News).
4. **Absorb the annual report as source #1** so the freshly-frozen QAE/FVE single-source MVPs keep working unchanged.
5. **Consumption contracts are additive + versioned** — extend the engines' inputs without breaking them.
6. **No synthetic-only depth.** Build corroboration/divergence and the news-circularity defense **minimally on the real triad**, not as deep logic proven only on fixtures (the FVE Phase 9 / QAE over-build trap).
7. **Real-data audit gates between phases; pin fingerprints** so audits are reproducible despite upstream OCR/source variability.
8. **Do not start MSIL until QAE/FVE single-source contracts are stable** (QAE just froze READY_WITH_LIMITATIONS; FVE is readiness-grade).

---

## 1. Implementation Phases (Tasks 1–3)

| Phase | Scope | Depends on | Audit artifact | Freeze criteria |
|---|---|---|---|---|
| **P0 — Contract & matrix materialization** | Freeze enums, authority matrix, provenance schema, version-pin set, `signal_id` scheme | contracts doc | `msil_contract_integrity_audit.json` | Enums valid; matrix total per claim_type; schemas frozen. |
| **P1 — Entity Registry + Resolution (keystone)** | Canonical registry + tiered resolution + quarantine/review | P0 | **`entity_resolution_audit.json`** | Group entities distinct; quarantine works; resolution truth-set baseline. |
| **P2 — IntelligenceSignal envelope + Provenance + snapshot infra** | Common envelope, provenance union, immutable snapshot store | P0, P1 | **`provenance_audit.json`** | Every signal provenance-backed; `NONE` blocked; snapshots reproducible. |
| **P3 — Absorb annual report as source #1** | OCR `.kb.json` → IntelligenceSignals (narrative/numeric/event), entity-bound | P1, P2 | `msil_annual_report_adapter_audit.json` | No regression to existing QAE/FVE single-source inputs. |
| **P4 — Authority assignment** | Apply claim-type-scoped matrix; special rules | P0, P3 | **`authority_audit.json`** | Deterministic authority; news/market special rules hold; verified-gates-authority. |
| **P5 — Official structured triad** | Adapters: PSX Announcements + Company Payouts + SECP Notices; **content-class split proven** | P1–P4 | `msil_official_sources_audit.json` | Triad ingests with resolved entities + correct routing + snapshots. |
| **P6 — Timeline + Supersession** | Unified event-time axis; supersession links | P5 | **`timeline_audit.json`** | Ordering correct; supersession rule (time + authority) enforced; no deletion. |
| **P7 — Corroboration + Divergence** | Independent-origin corroboration; authority-weighted divergence | P5, P6 | **`corroboration_audit.json`**, **`divergence_audit.json`** | Independence + lineage captured; divergence surfaced-never-resolved. |
| **P8 — Additive consumption + real-bundle run** | Wire FVE/QAE/Query feeds; end-to-end Lucky multi-source run; **FVE gate extended to non-OCR provenance** | P1–P7 | **`msil_real_bundle_smoke_audit.json`** | Coherent multi-source profile; consumption additive; no engine regression. |
| **P9 — Second-issuer (Millat) + freeze readiness** | Millat multi-source run; freeze evidence + truth-set spot checks | P8 | **`freeze_readiness_audit.json`** | Freeze criteria met or explicitly waived. |

**Sequencing rules visible in the table:** contracts (P0) precede the registry (P1) which precedes all adapters (P3, P5); resolution (P1) is the second phase, before any ingestion; the official triad (P5) precedes all news/market work (post-MVP §5).

---

## 2. Per-Phase Detail (scope · inputs · outputs · dependencies · audit · freeze)

**P0 — Contracts & matrix.** *Scope:* materialize the frozen master decision list (entity/alias/rel/content_class/claim_type/authority_class/provenance_type/event_type/divergence_type enums; the authority matrix; version-pin set; `signal_id` scheme). *Inputs:* contracts doc. *Outputs:* versioned matrix + provenance schema + enum registry. *Audit:* `msil_contract_integrity_audit` (no duplicate ids, matrix total per claim_type, special rules present). *Freeze:* integrity passes; nothing builds before this.

**P1 — Entity Registry + Resolution (keystone).** *Scope:* canonical registry for MVP issuers (Lucky group, Millat) + securities + sectors + group/subsidiary links; tiered resolution (exact→alias→fuzzy→unresolved) with quarantine/review. *Inputs:* PSX ticker list, SECP reg numbers, known legal-name variants. *Outputs:* registry + resolution service + EntityResolution records. *Dependencies:* P0. *Audit:* `entity_resolution_audit` — method distribution, quarantine/review rate, **group-disambiguation correctness (Lucky Cement vs Lucky Core vs Lucky Motor)**, resolution truth-set spot check. *Freeze:* group entities distinct; deterministic; quarantine path works; truth baseline recorded.

**P2 — Envelope + Provenance + snapshot.** *Scope:* `IntelligenceSignal` envelope, provenance discriminated union, immutable snapshot store + retention. *Inputs:* P0 contracts, P1 registry. *Outputs:* envelope + provenance impl + snapshot store. *Audit:* `provenance_audit` — provenance + `snapshot_ref` + `retrieved_at` + `verified` on every signal; `NONE` blocked; snapshot round-trip immutability; no false precision. *Freeze:* provenance complete + reproducible.

**P3 — Annual report as source #1.** *Scope:* adapter mapping OCR `.kb.json` insights→narrative signals, consolidated values→numeric claims, events where present; entity-bound. *Inputs:* Lucky/Millat `.kb.json`, registry, envelope. *Outputs:* `annual_report` IntelligenceSignals. *Audit:* `msil_annual_report_adapter_audit` — signals reconcile with existing QAE/FVE single-source inputs (**no regression**). *Freeze:* parity with current single-source behavior.

**P4 — Authority assignment.** *Scope:* apply the claim-type-scoped matrix; enforce news/market special rules; verified-gates-authority. *Inputs:* matrix (P0), signals (P3). *Outputs:* authority-tagged signals. *Audit:* `authority_audit` — `authority_class × claim_type` distribution; special rules enforced; version pin present. *Freeze:* deterministic + rules hold.

**P5 — Official structured triad.** *Scope:* PSX Announcements, Company Payouts, SECP Notices adapters; prove the **content-class split** (payout amount→numeric_claim/FVE candidate; announcement narrative→narrative_claim/QAE; results/dividend→corporate_event); **capture `source_lineage` at ingestion** (HD-7). *Inputs:* P1–P4. *Outputs:* triad signals + events. *Audit:* `msil_official_sources_audit` — resolution success, routing correctness, provenance + snapshots, lineage captured. *Freeze:* triad ingests cleanly with correct routing.

**P6 — Timeline + Supersession.** *Scope:* per-entity unified event-time axis; supersession links across annual report + triad (preliminary vs revised results; announced vs paid dividend). *Inputs:* events (P5). *Outputs:* timeline + supersession state. *Audit:* `timeline_audit` — ordering; latest-on-observation_time vs trend-on-subject_period not conflated; supersession rule (later + authority ≥ prior); no deletion; time-basis alignment. *Freeze:* deterministic + supersession honored.

**P7 — Corroboration + Divergence.** *Scope:* independent-origin corroboration (payouts confirming announcements); authority-weighted divergence (issuer vs SECP); lineage-based circularity exclusion. *Inputs:* P5–P6. *Outputs:* corroboration groups + divergence records. *Audits:* `corroboration_audit` (independence, circularity exclusion, bounded strength), `divergence_audit` (both sides retained, authority-weighted, surfaced-never-resolved, news-pending flag). *Freeze:* independence-only credit; divergence never auto-resolved.

**P8 — Additive consumption + real-bundle run.** *Scope:* wire FVE (numeric candidates + events + divergence), QAE (narrative + corroboration/divergence + coverage caveats), Query (evidence store + timeline + entity index); **extend FVE integrity gate to non-OCR provenance (HD-5)**; end-to-end Lucky multi-source run. *Inputs:* P1–P7. *Outputs:* three consumption feeds + a multi-source Lucky profile. *Audit:* `msil_real_bundle_smoke_audit` — all contracts exercised; consumption additive; **no regression to frozen QAE/FVE single-source**. *Freeze:* coherent profile; engines unaffected.

**P9 — Millat + freeze readiness.** *Scope:* multi-source Millat run; freeze evidence; truth-set spot checks (resolution + authority + corroboration/divergence sample). *Inputs:* P8. *Outputs:* generalization deltas + freeze decision. *Audit:* `freeze_readiness_audit`. *Freeze:* MVP freeze criteria met or limitations explicitly accepted.

---

## 3. MVP Scope (Task 4)

**In scope (P0–P9):** frozen contracts; entity registry + resolution; signal envelope + provenance + snapshots; annual report as source #1; the **official structured triad (PSX Announcements, Company Payouts, SECP Notices)**; timeline + supersession; corroboration + divergence on the real multi-source set; additive consumption contracts for FVE/QAE/Query; Lucky + Millat runs; freeze.

**MVP framing (honest):** *"Official, structured, entity-resolvable, event-bearing sources integrated on a shared timeline — numbers gated to FVE, narrative to QAE, events on the timeline, authority-weighted divergence surfaced, with reproducible provenance."* Explicitly **not** "all nine sources fused."

---

## 4. Post-MVP Scope (Task 5)

Governed additive source onboarding, in risk order:
1. **Sector Summary, Company Overview, Analysis Reports** (opinion/context/static) — lower authority, manageable volume.
2. **Market Watch, then Futures Market Watch** (market_revealed; observation-not-assertion; high volume).
3. **News Sources — last** (highest volume, lowest authority, hardest entity resolution, **circular re-reporting**); only after `source_lineage` circularity defense is proven at scale.
Plus: non-manufacturing issuer generalization (bank/power); full news-circularity validation; cross-source dedup at scale; deeper FVE/QAE multi-source integration; sub-entity (person/futures) enrichment.

---

## 5. Integration Points (Task 6)

All additive + versioned; wired in P8.

- **Forecast Validation Engine** — consumes `numeric_claim` candidates (**gate-bound, never validated**; gate extended to non-OCR provenance), the `CorporateEvent` timeline, and `narrative_vs_numbers` divergences. Pin: `fve_consumption_contract_version`.
- **Qualitative Analysis Engine** — consumes `narrative_claim` (`QualitativeSignal`) signals + corroboration/divergence + coverage caveats; QAE still owns taxonomy/themes. Pin: `qae_consumption_contract_version`.
- **Query Engine** — consumes the unified evidence store + timeline + provenance + entity index for retrieval/citation across all provenance types. Pin: `query_consumption_contract_version`.

Forward-compatibility rule: engines may ignore unknown `content_class`/source types, so new post-MVP sources never break a consumer.

---

## 6. Required Audits (Task 7)

| Audit | Phase | Verifies |
|---|---|---|
| `entity_resolution_audit` | P1 | Method distribution; quarantine/review; group disambiguation; truth-set baseline. |
| `provenance_audit` | P2 | Provenance + snapshot completeness; `NONE` blocked; immutability; no false precision. |
| `authority_audit` | P4 | Claim-type-scoped authority; news/market special rules; verified-gating; version pins. |
| `timeline_audit` | P6 | Ordering; observation vs subject time; supersession rule; no deletion; time-basis alignment. |
| `corroboration_audit` | P7 | Independence; circularity (lineage) exclusion; bounded strength; no opinion→fact promotion. |
| `divergence_audit` | P7 | Both sides + authority retained; surfaced-never-resolved; never equal-weighted; news-pending. |
| `real_bundle_smoke_audit` | P8 | End-to-end multi-source Lucky run; consumption feeds; no engine regression. |
| `freeze_readiness_audit` | P9 | Millat generalization + truth-set spot checks + freeze criteria. |

---

## 7. Implementation Risks (Task 8)

- **IR-1 — Entity-resolution correctness unvalidated.** No truth set ⇒ mis-links undetected. *Action:* P1 truth-set spot check is a freeze gate, not optional.
- **IR-2 — Adapters before registry frozen.** *Action:* P1 strictly precedes P3/P5.
- **IR-3 — FVE gate not extended to non-OCR provenance (HD-5).** External numbers either bypass the gate (silent corruption) or are unconsumable. *Action:* resolve before P8; it is a pre-coding decision (§9 hidden deps).
- **IR-4 — `source_lineage` not captured at ingestion (HD-7).** Corroboration circularity becomes undetectable when news arrives. *Action:* capture lineage from **P5**, even though news is post-MVP.
- **IR-5 — Snapshot retention infra absent (HD-2).** Provenance rot. *Action:* stand up before P2.
- **IR-6 — Breaking frozen QAE/FVE MVPs** via non-additive consumption changes. *Action:* additive + versioned; P3/P8 audits assert no regression.
- **IR-7 — Group/subsidiary mis-resolution** injecting wrong-entity evidence. *Action:* P1 group-disambiguation is an explicit freeze criterion.
- **IR-8 — Test non-determinism** from upstream OCR/source variability. *Action:* pin source fingerprints for all audits.
- **IR-9 — Source-abundance illusion** (more sources read as "better covered/more authoritative"). *Action:* per-source coverage + authority reporting from P4 onward.

---

## 8. Over-Engineering Risks (Task 9)

- **OE-1 — Building all nine adapters before the triad proves mechanisms** (the FVE Phase 9 trap). Build the triad, prove split/timeline/corroboration/divergence, then defer.
- **OE-2 — Deep news-circularity / divergence logic before news exists.** Build minimally on the triad; full circularity validation is post-MVP with real news.
- **OE-3 — Futures/derivatives modeling depth before equity basics.** Futures is post-MVP; do not model derivatives before the equity timeline is proven.
- **OE-4 — Over-rich entity registry** (all persons, all securities) before MVP issuers need it. Seed minimally (Lucky group, Millat, their securities/sectors).
- **OE-5 — A generic "any-source" framework before 3–4 concrete adapters reveal the real shape.** Let the triad + annual report define the adapter contract empirically.
- **OE-6 — Dedup-at-scale infra before news volume justifies it.**

---

## 9. Hidden Dependencies to Resolve Before Coding (Task 10)

- **HD-1 — Entity registry + resolution truth set** (the keystone; nothing trustworthy without it).
- **HD-2 — Immutable snapshot storage/retention infra** (provenance depends on it).
- **HD-3 — Source authenticity/verification pipeline** (the `verified` flag is meaningless without one).
- **HD-4 — Canonical Period/calendar model** (underlies all time fields + the timeline).
- **HD-5 — FVE integrity-gate extension to non-OCR provenance** (decide before P8; otherwise external numbers are unconsumable or ungated).
- **HD-6 — Additive/versioned consumption-contract agreement** with FVE/QAE/Query owners (or MSIL output destabilizes frozen MVPs).
- **HD-7 — `source_lineage` capture decision at ingestion** (or corroboration circularity is permanently undetectable).
- **HD-8 — Authority-matrix governance process** (a living, versioned, cross-source artifact).
- **HD-9 (practical) — Actual source access/feeds** (PSX/SECP/payout data availability and format) confirmed before adapter phases.

---

## 10. One-Paragraph Verdict

MSIL is built the way every successful freeze in this platform was built: contracts first (P0), the keystone next (entity registry + resolution, P1 — because a mis-link is the worst failure and nothing ingests until identity is solid), then the common envelope and provenance with real immutable snapshots (P2–P3), then — only then — the **official structured triad of PSX Announcements, Company Payouts, and SECP Notices** (P5), which proves the content-class split, the timeline, supersession, corroboration, and divergence on real, entity-resolvable, low-noise data before the abundant-but-dangerous Market, Futures, and News sources are ever touched. The integrations to FVE, QAE, and Query are additive and versioned so the freshly-frozen single-source MVPs keep working, with the two decisions that must precede coding flagged plainly: extend FVE's gate to non-OCR provenance, and capture `source_lineage` from the first official source so the news-echo circularity trap is defeated before news exists. Build it entity-resolution-first, prove it on the triad, defer the noise to a governed post-MVP, gate the freeze on a resolution truth set — and MSIL becomes the coverage-honest substrate the multi-source future needs, never letting source abundance be mistaken for source authority.
