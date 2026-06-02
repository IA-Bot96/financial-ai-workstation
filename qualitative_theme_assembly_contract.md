# Qualitative Theme Assembly — Contract

**Status:** Contract specification. No code. Focus: aggregation rules, evidence rules, multi-source compatibility.
**Date:** 2026-06-02
**Derived from:** `qualitative_analysis_engine_architecture.md`, `qualitative_taxonomy_architecture.md`, `qualitative_analysis_multi_source_architecture_review.md`, `qualitative_signal_contract.md`.

---

## 0. First Principles

Theme assembly is the **deterministic** layer that turns classified `QualitativeSignal`s into evidence-backed `QualitativeTheme`s, which roll up into the six content categories and the run scorecard. It introduces no new facts; it groups, weighs, corroborates, contradicts, and scores what the signals already assert.

Five invariants, inherited and binding:

1. **Theme *type* (taxonomy) vs theme *instance* (assembly).** The taxonomy defines a closed set of theme *types* (`theme_ref`). Assembly produces theme *instances*: one per `(entity, theme_ref)`, populated by ≥1 bound signal. The vocabulary is never expanded at assembly.
2. **No ungrounded theme.** Every theme instance cites ≥1 admitted, mapped signal. A theme traceable to no admitted signal may not exist.
3. **One signal → one theme (counting).** A signal counts toward exactly one theme's salience (its canonical `theme_ref`); cross-category appearances are references, not recounts.
4. **Creation is gated; corroboration/contradiction is broad.** A theme may be *created* only by a mapped, creation-eligible signal. Market and overview signals may attach but never instantiate.
5. **Three axes stay separate:** `theme_confidence` (trust), `evidence_weight` (influence, claim-type-scoped authority × recency × independence × specificity × corroboration), `materiality` (business importance). No fused score.

---

## 1. How Signals Become Themes (Task 1)

Deterministic pipeline, gate-first (mirrors the Forecast Validation orchestration spine):

1. **Admit signals** — drop `unmapped` signals to the unmapped pool (§11); keep mapped signals whose `signal_confidence` clears the floor and whose `entity_scope` matches the theme's scope.
2. **Group by identity** — cluster admitted signals by theme identity (§2).
3. **Creation gate** — instantiate a theme only if ≥1 grouped signal is **mapped + `creation_eligible=true`** (§5 of the signal contract). A cluster of attach-only signals (market/overview/quarantined-opinion) does **not** instantiate a theme; it is held as a divergence/contextual note against an existing theme or surfaced as an unsupported-signal report.
4. **Deduplicate within the instance** (§3).
5. **Classify roles** — assign each signal a `theme_role` (`creates` / `strengthens` / `contradicts` / `contextualizes`) relative to the instance (§4–§5).
6. **Score** — corroboration, contradiction, coverage, confidence, materiality (§4–§10).
7. **Aggregate** to category (§8) and run scorecard.

Assembly is deterministic; an LLM may not create, merge, or rank themes — only (optionally, downstream) rephrase already-assembled output.

---

## 2. Theme Identity (Task 2)

Identity must be **stable across runs, across time, and across sources** so recurring detection and future year-over-year change are possible.

```
theme_identity = (entity_ref, entity_scope, theme_ref, taxonomy_version)
```

- **Period-agnostic:** `subject_period`/`observation_time` are **attributes of evidence, not identity** — a theme persists across years and accumulates per-period evidence. (A "Capacity Expansion" theme is one identity spanning 2023–2025, not three themes.)
- **Text-independent:** identity never depends on `claim` text or signal count (carry-over of signal-contract HR-2: LLM re-extraction churns text).
- **Sub-themes are facets, not identities:** roll-up dimension within a theme, not separate theme instances (avoids granularity-driven identity explosion, taxonomy TR4).
- **Version-pinned:** a theme aggregates only signals sharing its `taxonomy_version` (or migrated via an explicit map); cross-version aggregation is prohibited (§12 HR).

---

## 3. Theme Deduplication (Task 3)

The critical distinction: **dedup removes the same artifact counted twice; corroboration counts different sources agreeing.** Conflating them either under-counts independent evidence or over-counts one document.

- **Dedup key = provenance locator + `observation_time` + `subject_period`** — NOT claim text. Two signals with identical provenance (same page / same announcement_id / same market_date+series) collapse to one.
- **Never dedup across sources.** The same real event reported by an issuer announcement, an analyst note, and a market summary are **three distinct signals** → corroboration (§4), not duplicates.
- **Re-extraction stability:** because dedup is provenance-keyed, OCR/LLM text variation across runs does not create phantom duplicates.
- Deduped signals are retained in evidence as a single record with a `duplicate_count`, never silently discarded.

---

## 4. Corroboration Rules (Task 4)

- **Corroboration credit requires independence.** Two signals corroborate only if they have **different `authority_class`** AND are **not linked by `source_lineage`/`derived_from`** (defeats circular corroboration — multi-source HR-D, e.g. an analyst report derived from the annual report).
- **Independent-origin groups:** group supporting signals by independent origin; corroboration strength = number of *independent* origins, not raw signal count (defeats volume-gaming — §12 HR).
- **Issuer self-repetition is weak.** Annual report + the issuer's own announcement = same origin class → little/no corroboration boost.
- **Strong corroboration** = independent classes agreeing (e.g. SECP + analyst + market) → bounded, **diminishing** weight multiplier on `evidence_weight` and a capped lift to `theme_confidence`.
- Corroboration raises weight/confidence within ceilings; it can never lift an opinion-class theme to fact-class (§10).

---

## 5. Contradiction Rules (Task 5)

- **QAE owns narrative-vs-narrative contradiction only.** Narrative-vs-numbers is FVE's domain; both emit the shared `Divergence` record (multi-source §6). QAE never validates a number to resolve a contradiction.
- **Contradiction never deletes or auto-resolves a theme.** It produces a `Divergence` attached to the theme, recording **both sides with their `authority_class`** — surfaced, authority-weighted, **never equal-weighted** (multi-source HR-F).
- **Detection:** opposing direction/sentiment/claim on the same theme identity from signals above a weight threshold. Market contradiction (sell-off vs bullish outlook) is recorded as a **sentiment divergence overlay** — flagged, low standalone authority, never a refutation of fact.
- **Effect:** a live contradiction **lowers `theme_confidence`** and **raises `materiality`** (a contested theme is more important to show, not less). These move in opposite directions by design.

---

## 6. Materiality Scoring (Task 6)

Materiality = business importance of the theme. **Strictly separate from, and never capped by, confidence** (platform invariant).

Inputs:
- **Salience** — count of *independent* supporting origins + source/section spread (not raw signal count).
- **Source authority** — claim-type-scoped effective authority of supporting signals.
- **Category severity prior** — risk/governance/compliance themes carry higher base materiality than descriptive ones.
- **Recency** — a current/forward theme outweighs a stale one (horizon-relative).
- **Contradiction presence** — a contested theme gains materiality.

Rules:
- Materiality is reported **alongside** confidence, never derived from it. A high-materiality, medium-confidence risk must surface prominently (the opposite of confidence-driven ranking).
- Materiality drives **surfacing/ranking**; confidence drives **trust**; weight drives **how much a signal moves the theme**. Three reported numbers, three purposes.

---

## 7. Coverage Requirements (Task 7)

- **Mapped vs raw, per category** (taxonomy contract): a category rich in raw signals but high in `unmapped` rate is **not** well-covered.
- **Per-theme salience tiers:** single-signal theme → `low_salience` label; multi-independent-origin → full salience.
- **Per-source coverage** (multi-source HR-H): a theme supported only by market sentiment is weaker than one spanning report + announcement + analyst; coverage records the **source mix**, and absence of a source is reported, never averaged into a single health score.
- **Creation vs corroboration coverage are distinguished:** a theme with corroboration but no creation-eligible source cannot exist (§5); a theme with creation but zero corroboration is valid but flagged single-origin.
- **Gate outcomes** (per category): `ANALYZED` / `ANALYZED_WITH_WARNING` (high unmapped rate or thin salience) / `SKIPPED_INSUFFICIENT_COVERAGE` / `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY` (YoY, single observation period). Skips are evidenced, never silently omitted (FVE Phase 10 lesson).

---

## 8. Category Aggregation (Task 8)

- **Primary-category ownership:** each theme rolls up to its canonical primary category for counting; bounded secondary-tag categories (≤2) get a **cross-reference**, not a recount (taxonomy anti-double-count).
- **`QualitativeCategoryResult`** carries: owned themes, category coverage (mapped/raw + source mix), category `status`, composed category confidence (§10), and aggregate category materiality (e.g. max/weighted of theme materialities — never averaged-to-dilute a single material risk).
- **Recurring themes and year-over-year change are derived analyses over assembled themes, not categories** — they read the period-agnostic theme identities + per-period evidence; YoY remains `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY` until ≥2 observation periods exist (current single-report reality).
- Run scorecard aggregates category outcomes with **coverage-first** reporting (the QAE/FVE lesson: the headline must encode how much was analyzable, not a flattering mean).

---

## 9. Evidence Requirements (Task 9)

Every theme instance carries a `ThemeEvidence` bundle:
- Supporting signal ids + claims + `theme_role`.
- **Per-source provenance, honestly typed** (PDF page / announcement ref / regulatory ref / market ref / sector ref / url snapshot) — no false precision.
- `observation_time` + `subject_period` + `time_basis` + `horizon` per signal.
- `authority_class` + `claim_type` per signal; **opinion-class (analyst) and sector-class evidence labeled as such** and never merged into issuer-fact.
- Corroboration groups (independent origins) and `Divergence` records.
- Salience, source mix, mapping methods, `duplicate_count`.
- **Single-signal themes labeled `low_salience`.**
- Skipped categories carry coverage-gap evidence.

---

## 10. Confidence Composition (Task 10)

```
theme_confidence = clamp(
    base   = max(signal_confidence of creation-eligible supporting signals),   # floor on the strongest grounded source
    + corroboration_lift(independent_origins)                                  # bounded, diminishing
    - contradiction_penalty(authority-weighted)                                # live divergence lowers trust
    , ceiling = class_ceiling(theme_class) )
```

- **Class ceilings:** an **opinion-only** theme (analyst-created, no fact/regulatory corroboration) is ceilinged below fact-class; **keyword-tier** mapping and **review-routed** signals cap confidence (taxonomy + insight-governance carry-over). Corroboration can never lift a theme above its class ceiling.
- **`theme_confidence` ≠ `materiality` ≠ `evidence_weight`** — composed and reported independently.
- A theme whose only support is below the signal-confidence floor does not instantiate (it joins the review pool).

---

## 11. Handling of Unmapped Signals (Task 11)

Unmapped signals are **first-class, never force-fit** (taxonomy + signal contract):
- They **do not create or attach to themes** (no `theme_ref`).
- They are pooled per category-prior (where a section/adapter prior exists) and surfaced as a **review/extension queue** so the taxonomy can be governed-extended.
- They count toward **raw coverage but not mapped coverage**, and toward **neither salience nor theme confidence**.
- A high unmapped rate forces `ANALYZED_WITH_WARNING` or `SKIPPED_INSUFFICIENT_COVERAGE` and is reported as a coverage gap — the inverse of pretending coverage exists.

---

## 12. Hidden Risks (Task 12)

- **HR-1 — Theme-identity instability.** If identity leaked from claim text or period, recurring/YoY break. *Mitigation:* period-agnostic, text-independent, version-pinned identity (§2).
- **HR-2 — Corroboration inflation via correlated sources.** Analyst/sector signals derived from the annual report counted as independent confirmation → false confidence. *Mitigation:* independence groups + `source_lineage` (§4).
- **HR-3 — Dedup/corroboration confusion.** Collapsing independent sources (under-count) or counting one artifact twice (over-count). *Mitigation:* provenance-keyed dedup; cross-source = corroboration, never dedup (§3).
- **HR-4 — Creation-gate bypass.** Market/overview/opinion signals manufacturing phantom themes through the attachment path. *Mitigation:* instantiation requires a mapped creation-eligible signal; attach-only clusters never become themes (§1, §5).
- **HR-5 — Materiality↔confidence collapse.** A low-confidence material risk buried, or a high-confidence trivial theme dominating. *Mitigation:* strict separation; contradiction lowers confidence but raises materiality (§5, §6).
- **HR-6 — Volume gaming.** Many low-quality signals inflate salience/materiality. *Mitigation:* salience counts independent origins + specificity, not raw signal count (§4, §6).
- **HR-7 — Quarantine leakage.** Analyst/sector opinion promoted into issuer-fact themes. *Mitigation:* opinion/sector evidence labeled, class-ceilinged, never merged into fact (§9, §10).
- **HR-8 — Intra-theme temporal mixing.** Fiscal report + calendar announcement + continuous market evidence in one theme producing a false intra-theme trend. *Mitigation:* per-period/per-`time_basis` evidence; trend/recurring claims gated on time-basis alignment (§2, §8).
- **HR-9 — Single-source coverage illusion.** A "complete" theme built from one market signal, over-trusted. *Mitigation:* per-source coverage + `low_salience` labeling + source-mix reporting (§7).
- **HR-10 — Contradiction mishandling.** Suppressed (hides risk) or equal-weighted (noise) divergence. *Mitigation:* authority-weighted `Divergence`, never auto-resolved, never equal-weighted (§5).
- **HR-11 — Version skew across aggregated signals.** Signals classified under different taxonomy/authority-matrix versions aggregated into one theme. *Mitigation:* same-version aggregation or explicit migration map; version pins on theme and signals (§2).
- **HR-12 — Entity-scope leakage.** Sector/market signals attaching to a company theme. *Mitigation:* only `entity_scope=company` signals populate company themes; sector→sector themes; market = overlay (§1).
- **HR-13 — No assembly truth set.** Theme correctness (clustering, materiality, contradiction) is unverified without analyst ground truth (platform-wide open gap). *Mitigation:* deterministic + audited rules; flagged as a pre-freeze validation item.

---

## 13. What Must Be Frozen Before Implementation

1. **Theme identity** scheme (period-agnostic, text-independent, version-pinned).
2. **Creation gate** (mapped + creation-eligible requirement) and the attach-only-cluster rule.
3. **Dedup key** (provenance locator) vs **corroboration** (independent origin) boundary.
4. **Independence definition** for corroboration (`authority_class` distinct + no lineage link).
5. **`Divergence` record contract** (both sides + authority class; never auto-resolved) — shared with FVE.
6. **The three-axis separation** (`theme_confidence` / `evidence_weight` / `materiality`) and their input sets.
7. **Confidence composition** (floor + bounded corroboration lift − contradiction penalty, clamped by class ceiling).
8. **Coverage taxonomy** (mapped vs raw, per-source, salience tiers, category status enum).
9. **Category aggregation** (primary ownership + bounded secondary cross-reference; recurring/YoY as derived analyses).
10. **Unmapped handling** (first-class pool, never force-fit, coverage-gap reporting).

Items 1–10 are the contract the category scorecard, recurring-theme detector, and future multi-source adapters all depend on — frozen before any assembly logic is built, per the platform's proven contracts-first discipline.

---

## 14. One-Paragraph Verdict

Theme assembly is the deterministic bridge from classified signals to category-level qualitative understanding, and its correctness rests on a handful of boundaries that are easy to blur and expensive to get wrong: a theme *instance* is one stable, period-agnostic, version-pinned identity per `(entity, theme_ref)` that accumulates per-period, per-source evidence; it may be *created* only by a mapped creation-eligible signal, *deduplicated* only within identical provenance, and *corroborated* only across genuinely independent origins so that an annual report echoed by a derived analyst note never masquerades as confirmation. Contradictions are surfaced as authority-weighted divergences that lower confidence while raising materiality — never auto-resolved, never equal-weighted — and the three measurement axes (confidence, weight, materiality) stay strictly separate so a low-confidence material risk is shown, not buried. Unmapped signals remain first-class and visible rather than force-fit, coverage is reported mapped-vs-raw and per-source so a single market sentence is never mistaken for a covered theme, and every theme cites real per-source provenance with opinion and sector evidence quarantined from issuer fact. Freeze the ten contracts above first; build assembly only after — and the engine inherits a stable, auditable, multi-source-ready aggregation layer rather than the silent over-counting, phantom themes, and confidence/materiality confusion that unconstrained assembly would otherwise guarantee.
