# MSIL Phase 1 Architecture Review — Entity Registry & Resolution

**Status:** Review of MSIL Phase 1 against the contracts and truth-set spec. No code. Focus: identity correctness, future ingestion risk, freeze readiness.
**Date:** 2026-06-02
**Evidence:** `entity_resolution_audit.json`, `msil_phase1_report.json`. Registry `1.0.0`, resolution logic `1.0.0`, 50/50 tests.

---

## 0. Result Snapshot

| Freeze criterion | Target | Actual | Pass |
|---|---|---|---|
| Mis-resolution rate | 0% | **0%** | ✓ |
| Group-disambiguation accuracy | 100% | **100%** | ✓ |
| Quarantine correctness | 100% | **100%** | ✓ |
| Ambiguous→review correctness | 100% | **100%** | ✓ |

Truth-set coverage: 11/11 positive · 6/6 ambiguous · 10/10 quarantine · 7/7 group. Registry: 20 entities, 45 aliases, 23 relationships. `misresolved_cases: []`.

**Headline:** Phase 1 is a **clean, high-fidelity keystone result** — the mechanism does exactly what the contracts demand, and it **quarantines before it ever mis-attributes**. But this is a **closed-loop validation of a curated 20-entity, two-group, manufacturer-only world**: the truth set was authored alongside the registry it validates. The pass proves the *resolution mechanism* is sound and safe; it does **not** prove the *registry is real-world-correct* (analyst sign-off is missing) or that it *generalizes* (messy identifiers, cross-group collisions, news, and registry growth are all untested).

---

## 1. Architecture Fidelity (Task 1) — HIGH

The implementation matches the contracts and truth-set spec exactly:
- **Resolution precedence** `exact → alias → fuzzy → unresolved`; `confidence_overrides_precedence: false`; `llm_logic_used: false` — deterministic, as specified.
- **Quarantine-not-force** honored — all 10 quarantine cases return `null` entity, no candidates, `review_required: true`.
- **Security→company chaining** works (`LUCK → sec_luck → lucky_cement`; `MTL → sec_mtl → millat_tractors`).
- **Bare group tokens withheld from aliases and routed to review** — "Lucky"/"Millat"/"Yunus"/"ICI" resolve to `review` with full candidate sets and `resolved_entity_ref: null`, exactly as the truth-set spec's defense intended.
- **Group disambiguation** — the four Lucky entities each resolve distinctly; zero sibling confusion.
- **Version pins** on every record; reproducible.

**Two fidelity nuances worth recording (not defects):**
- **Counting overlap:** `quarantined_cases (10)` and `unresolved_cases (10)` are the same set (quarantine *is* method=`unresolved` + review_status=`quarantined`); the summary taxonomy conflates a *method* with a *review_status*. Cosmetic, but should be disambiguated in the audit schema.
- **Ambiguity routing is rule-driven, not threshold-emergent.** Review is triggered by explicit per-token rules (`bare_lucky_group_token`, `bare_millat_group_token`, `historical_generic_token_requires_review`), not purely by a confidence floor. This is correct for the curated set but is the seed of HR-2 below.

---

## 2. Hidden Identity-Resolution Risks (Task 2)

- **HR-1 — Closed-loop validation.** The truth set and the registry were built by the same effort; 100% means *internally consistent*, not *externally correct*. The audit cannot detect a wrong real-world fact (e.g. a mis-entered LCI ticker) because the truth set asserts the same value.
- **HR-2 — Ambiguity handling is curated-token-specific.** Review routing fires on explicit `manual_review_rule`s for known tokens. A bare token for a **new** group not pre-tagged may not route to review unless a **general** "short/generic/multi-candidate token → review" policy exists. Must be confirmed (§6 M-2).
- **HR-3 — The fuzzy tier is barely exercised and provides little recall.** All 6 fuzzy cases are pre-designed ambiguous tokens, all sent to review; nothing fuzzy auto-resolves. Safe — but real fuzzy near-misses (typos, OCR garble, unlisted variants) are untested, and the current behavior implies they will mostly land in review/quarantine.
- **HR-4 — Only clean curated identifiers tested.** Inputs are tidy ("Lucky Cement Limited", "LUCK"). Real PSX/SECP/news identifiers are messy ("M/s LUCKY CEMENT LTD.", company codes, CDC/scheme refs, paraphrases). The variation space is far larger than the 45 aliases cover.
- **HR-5 — Ticker uniqueness/temporal validity assumed.** Tickers are treated as unique and stable; PSX tickers can be reassigned after delisting — a latent mis-resolution vector when historical data arrives. No temporal validity on tickers.
- **HR-6 — Registry is a static snapshot.** Relationships (Lucky acquired ICI → renamed Lucky Core) are correct *now*; M&A/divestiture/renames change them. Entity lifecycle (merge/deprecate tombstones) and relationship temporal validity are untested.
- **HR-7 — Period resolution unexercised.** The contract requires period binding (fiscal/calendar); no truth case tests it. Entity resolution passed; period resolution is a separate, unvalidated concern.

---

## 3. Truth-Set Blind Spots (Task 3)

- **TB-1 — Manufacturer-only, two-group world.** The same overfit risk that dogged the QAE taxonomy: no bank, power-pure, textile, or conglomerate with generic-word names ("National", "Pak", "United", "First") — exactly the hardest real disambiguation cases.
- **TB-2 — No degraded inputs.** No OCR-garbled names, no news paraphrase ("the cement giant"), no real truncation beyond the curated "Millat I".
- **TB-3 — All ambiguity is *within-group*.** The dangerous real case is **cross-issuer same-token collision** (two unrelated PSX companies sharing "Lucky"/"United"). "Lucky Goldstar"/"LG" tests *foreign*; a domestic different-issuer same-token collision is absent.
- **TB-4 — No analyst sign-off / unresolved `[CONFIRM]` fields.** The truth-set spec made analyst sign-off + `[CONFIRM]` resolution its **freeze criterion #6**; neither artifact shows it, and entities still carry `[CONFIRM]` values (LCI/BCL tickers, listed status, registration numbers). This is the **direct manifestation of HR-1** and is unmet against the spec's own bar.
- **TB-5 — Thin security/person depth.** Only 2 securities chained; person deferred; no share classes/bonds. Board-change and market/futures resolution have zero truth coverage.
- **TB-6 — No quarantine-recovery path.** Quarantine works, but the operational review queue + re-resolution after registry growth is untested; an unreviewed quarantine queue is silent data loss.

---

## 4. Future Source-Integration Risks (Task 4)

- **FS-1 — Messy real identifiers (HR-4 generalized).** Expect high review/quarantine volume on first real PSX/SECP/payout ingestion; the clean-string success will not transfer directly.
- **FS-2 — News is the resolution cliff.** Name mentions, no ids, context-dependent; the one news case correctly quarantined, but real news volume produces massive ambiguity — and the news-circularity defense (lineage, HD-7) **depends on resolving the news entity first**. News stays last for this reason.
- **FS-3 — Ticker→security→company at scale.** Market/Futures Watch are ticker-keyed and high-volume; ticker uniqueness/temporal validity (HR-5) becomes load-bearing.
- **FS-4 — Registry growth governance.** Each new source surfaces new entities (suppliers, peers, principals like AGCO); the registry must grow via **governed versioning**, and every growth re-opens resolution behavior. No extension process is evidenced yet.
- **FS-5 — Cross-source same-entity convergence.** The same company arrives as "Lucky Cement" (annual report), "LUCK" (PSX), a registration number (SECP), and a paraphrase (news) — all must converge on **one** `canonical_id`. Tested per-identifier in isolation; **not** tested as simultaneous convergence from heterogeneous id types. This is the core multi-source integration test and is naturally exercised at P3+P5.

---

## 5. Freeze Readiness (Task 5)

**Phase 1 is freeze-ready as a versioned baseline (v1.0.0) — conditioned on the one freeze criterion the spec defined but the artifacts do not show: analyst sign-off + `[CONFIRM]` resolution.**

- The four hard criteria pass cleanly, deterministically, version-pinned, across the full truth set — the keystone *mechanism* is sound and safe.
- But the truth-set spec's **freeze criterion #6 (analyst sign-off + all `[CONFIRM]` fields resolved)** is unmet in evidence. Because the audit is closed-loop (HR-1), this is the **only external-reality check** on the registry, and a wrong `[CONFIRM]` value (e.g. an incorrect ticker) would pass at 100% while being real-world-wrong. This must be closed before resolution is trusted against real sources.
- The generalization gaps (messy identifiers, cross-group collisions, news, registry growth) are **P2–P5 work, not Phase 1 blockers** — Phase 1's job was to prove the mechanism quarantines before it mis-attributes, and it did.

This mirrors the platform's established posture: freeze the keystone as a **versioned baseline whose result is real but bounded**, and make every later generalization a measurable governed extension.

---

## 6. Findings Classification (Task 6)

**Must Resolve Before P2**
- **M-1 — Analyst sign-off + resolve all `[CONFIRM]` fields** (TB-4/HR-1). The truth set's own freeze criterion #6, currently unmet; the sole external-reality check on a closed-loop audit. A wrong real-world fact is otherwise invisible.
- **M-2 — Confirm ambiguity routing is a *general* mechanism** (HR-2), not only per-token `manual_review_rule`s, so a new group's bare/generic token still routes to review. P2 builds directly on resolution behavior.

**Can Be Resolved During P2–P5**
- Messy real-identifier handling + normalization hardening (HR-4/FS-1) — as the official triad arrives.
- Cross-source same-entity convergence (FS-5) — naturally exercised when annual report (P3) + triad (P5) resolve one company from different id types.
- Quarantine review-queue operational process (TB-6/FS-5-queue).
- Registry growth/versioning governance (FS-4).
- Period resolution (HR-7).
- Cross-group / cross-issuer collision truth cases (TB-3) — expand the truth set as sources add entities.
- Ticker uniqueness/temporal validity groundwork (HR-5/FS-3) — before Market/Futures.

**Post-MVP**
- Person/board resolution (TB-5) — with board-change events.
- Security-level depth: share classes, bonds, futures (TB-5).
- News entity resolution at scale (FS-2) — News is the last source by design.
- Non-manufacturer issuer registry expansion (TB-1) — broad cross-industry generalization.

---

## 7. One-Paragraph Verdict

MSIL Phase 1 is exactly the keystone result the platform needed: deterministic, version-pinned, quarantine-before-misattribute resolution that passes every hard criterion — zero mis-resolution, perfect group disambiguation, perfect quarantine, perfect ambiguity-to-review — across a 34-case truth set, with the bare-token defense ("Lucky"/"Millat"/"Yunus") working precisely as designed. The fidelity is high and the safety posture is correct: it refuses before it guesses. The honest caveat is that this validates a **curated, manufacturer-only, two-group world against a truth set it co-authored** — a closed loop that proves the *mechanism* but not the *registry's real-world correctness*, which is why the one unmet item, the truth-set spec's own analyst-sign-off / `[CONFIRM]` gate, is the single Must-Resolve-Before-P2 (alongside confirming ambiguity routing is general, not per-token). Freeze Phase 1 as a versioned baseline with those two closed, then let the genuine generalization tests — messy real identifiers, cross-issuer token collisions, cross-source entity convergence, and eventually news — land as governed P2–P5 work, never letting a clean closed-loop pass be mistaken for proven real-world identity correctness.
