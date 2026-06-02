# Qualitative Analysis Engine — Multi-Source Architecture Review

**Status:** Forward-looking architecture review. No code. Focus: contracts, authority hierarchy, evidence hierarchy, long-term engine evolution.
**Date:** 2026-06-02
**Reviewed:** `qualitative_analysis_engine_architecture.md` (+ `qualitative_taxonomy_architecture.md`).
**New confirmed sources (planned inputs to both FVE and QAE):** `company_announcements`, `secp_notices`, `company_overview`, `analysis_reports`, `sector_summary`, `daily_market_summary`.

---

## 0. The Assumption Multi-Source Breaks (read first)

The QAE and taxonomy designs are quietly **report-centric**, and one specific dependency is load-bearing: the taxonomy's *reliable* classification axis is `source_section`, because OCR normalizes annual-report headings into a **closed 12-value set**. Category routing leans on that closed axis; the free-text `area` axis is only the precision layer.

**That safety net exists only for annual reports.** Announcements, SECP notices, market summaries, sector data, and analyst reports have **no `source_section` structure at all**. So under multi-source:

- The reliable category-routing axis disappears for ~five of seven source types.
- `page_number` provenance is meaningless for events, market data, and web overviews.
- `value_year`/`source_report_year` (fiscal framing) cannot represent event-time, continuous market time, or static profiles.
- The confidence governance tuned for annual-report insight extraction does not transfer.

Multi-source is therefore **not "more inputs to the same engine"** — it is a re-architecture of how the engine *classifies, times, cites, and trusts* content. The rest of this document defines the contracts that absorb that change without fragmenting the engine.

---

## 1. Re-Evaluated QAE Architecture (Task 1)

The deterministic-first, gate-first, evidence-bound spine **survives** and should not change. What must change is the introduction of a **per-source adapter layer** between raw sources and the (unchanged) canonical taxonomy + theme assembly:

```
Sources ─▶ Per-Source Adapter ─▶ Normalized QualitativeSignal ─▶ Canonical Taxonomy ─▶ Theme Assembly ─▶ Scorecard
(annual report,    (source-specific      (source-agnostic unit:        (source-agnostic        (multi-source
 announcements,     extraction +          claim + provenance +          categories/themes)       evidence per theme)
 secp, overview,    provenance +          authority + time + trust)
 analysis, sector,  trust prior)
 market)
```

- **New normalized unit — `QualitativeSignal`** (generalizes `Insight`): `claim`/`takeaway`, canonical theme refs, `source_type`, `authority_class`, `event_time` (replacing the report-only `value_year`/`source_report_year` pair), `provenance` (source-specific), `extraction_confidence`, `trust_prior`. The annual-report `Insight` becomes one specialization of this unit.
- **The taxonomy stays source-agnostic** (Task 7 below). Adapters differ; categories/themes do not.
- **Coverage gating becomes per-source-and-per-category** — a category can be richly covered by the annual report but absent in announcements, and that asymmetry must be visible, not averaged away.

---

## 2. Source-Authority Hierarchy (Task 2)

**Authority is not a single global ranking — it is claim-type-scoped.** A source authoritative for one claim class is noise for another. Define authority per claim class:

**Regulatory / compliance / governance facts**
1. `secp_notices` (independent regulator — legally authoritative)
2. `annual_report` (audited)
3. `company_announcements` (issuer official, unaudited)

**Audited financials & historical narrative**
1. `annual_report` (audited, comprehensive)
2. `company_announcements` (timely, issuer, unaudited/selective)
3. `analysis_reports` (third-party interpretation)

**Forward expectations / opinion** *(authority inverts here)*
1. `analysis_reports` + `company_announcements` (guidance) — the **external/forward** view the audited report cannot carry
2. `daily_market_summary` (market's revealed expectation)
3. `annual_report` outlook (issuer self-presentation)

**Entity description / static profile**
1. `company_overview` (with `annual_report` as the audited cross-check)

**Sector / peer context**
1. `sector_summary` (and `analysis_reports` for peer commentary)

Key principle: **issuer self-presentation (annual report, announcements, overview) is high-authority for *facts about itself* but low-authority for *its own forward optimism*; independent sources (SECP, analysts, market) invert that.** The engine must never collapse this into one number.

---

## 3. Evidence-Weighting Hierarchy (Task 3)

Theme/signal evidence weight is a **composition**, not a single rank:

```
evidence_weight = f(authority_class_for_claim_type,
                    recency_relative_to_claim_horizon,
                    independence_from_issuer,
                    specificity (named/quantified vs boilerplate),
                    corroboration (independent sources agreeing))
```

Weighting rules:
- **Claim-type scoping:** factual/historical themes weight **authority**; forward/sentiment themes weight **recency + independence**.
- **Recency is horizon-relative:** for "current risk posture," a recent announcement outweighs a lagging annual report; for "audited FY position," the annual report dominates regardless of market freshness.
- **Independence multiplier:** independent corroboration (SECP + analyst + market agreeing) raises weight; issuer-only repetition does not.
- **Market data is corroboration, not assertion:** `daily_market_summary` carries low standalone weight but meaningful **divergence** weight (when it contradicts management).
- **Specificity gate:** named/quantified claims outweigh boilerplate (reuse the existing generic-pattern filter), across all sources.

Weight feeds salience and confidence; it must remain **separate from materiality** (a low-weight market signal contradicting a high-authority management claim is *material* even if low-weight).

---

## 4. How Annual-Report Insights Interact With the New Sources (Task 4)

The annual report remains the **anchor narrative**; other sources **update, corroborate, or challenge** it along a shared event-time axis.

- **Announcements (same issuer, event-level).** Bridge the report's staleness: an outlook theme "planning capacity expansion" (report) is **updated** by an announcement "new line commissioned." Announcements may **supersede** report themes with newer events and may **create** post-report themes. Temporal rule: `event_time` after the report's period → newer signal, report theme marked `superseded`/`updated` (not deleted; both cited).
- **Market context (`daily_market_summary`).** Reflects the market's reaction, never asserts company facts. **May only strengthen or contradict** — e.g. bullish management outlook + sustained sell-off → a **divergence** signal. It is a *sentiment overlay*, not a theme source.
- **Sector intelligence (`sector_summary`).** Provides base rates and peer context. **Contextualizes and contradicts** (company claims margin expansion while the sector shows compression → divergence) and may create **clearly-labeled sector-level** themes, but not company themes.
- **Analyst reports (`analysis_reports`).** External opinion. May **create opinion-class** themes (a risk management didn't disclose), **strengthen** (independent corroboration), or **contradict** (disputes guidance) — always tagged third-party opinion, never merged into issuer-asserted fact.

The unifying mechanism: **all sources attach evidence to the same source-agnostic theme**, each tagged with source/authority/time — which is the entire payoff of multi-source and is only possible because the taxonomy is source-agnostic (§7).

---

## 5. Which Sources May Create / Strengthen / Contradict Themes (Task 5)

**Principle: creation authority is restricted; corroboration/contradiction is broad.** This prevents market noise and analyst opinion from manufacturing phantom company themes.

| Source | Create | Strengthen | Contradict | Notes |
|---|:--:|:--:|:--:|---|
| `annual_report` | ✓ (primary, fact) | ✓ | ✓ | Anchor; audited fact + issuer outlook. |
| `company_announcements` | ✓ (events) | ✓ | ✓ | Updates/supersedes report themes. |
| `secp_notices` | ✓ (regulatory/governance) | ✓ | ✓ (highest authority to contradict issuer compliance claims) | Independent regulator. |
| `analysis_reports` | ✓ **opinion-class only** | ✓ | ✓ | Must be tagged third-party opinion. |
| `sector_summary` | ✓ **sector-level only** (not company) | ✓ | ✓ (peer divergence) | Context/base rates. |
| `company_overview` | ✗ (descriptive context only) | weak ✓ | ✗ | Entity profile, not events. |
| `daily_market_summary` | ✗ | ✓ (sentiment) | ✓ (sentiment divergence) | Overlay, never a theme source. |

Hard rules:
- **`daily_market_summary` and `company_overview` may never create a company theme.**
- **Analyst/sector creations are quarantined into an `opinion`/`sector` evidence class** and may not be promoted to issuer-fact.
- **Contradiction never auto-resolves a theme** — it is surfaced with authority-weighted framing (§8 HR-F).

---

## 6. Future FVE ↔ QAE Interaction Contracts (Task 6)

Both engines now consume the same multi-source pool; the contracts that keep them from corrupting each other:

1. **Authority-class split (the keystone).** A source carrying both a number and a narrative is **split at ingestion**: the **number** enters FVE's domain (must pass Historical Series Integrity Gating like any value), the **narrative claim** enters QAE's domain. Neither engine ingests the other's authority class as fact. (e.g. an announcement "capacity 12m tons, financed by new borrowing": the figure is an FVE candidate subject to the gate; "expansion financed by debt" is a QAE theme.)
2. **Non-authoritative narrative support (existing, extended).** QAE themes — now including **management guidance** (announcements/outlook) and **analyst expectations** (analysis_reports) — flow to FVE as *non-authoritative plausibility evidence*. FVE may compare a submitted forecast against management guidance and analyst consensus **as narrative context**, never as validated numbers.
3. **Shared `Divergence` contract.** Both engines emit a common divergence record: QAE owns **narrative-vs-narrative** (management vs analyst vs market); FVE owns **narrative-vs-numbers** (guidance vs gate-admitted history). Each may *consume and display* the other's divergences but **neither resolves the other's domain**.
4. **Shared event-time + supersession contract.** Both engines use one `event_time` axis and one staleness/supersession rule, so an FVE baseline and a QAE theme agree on what "latest" means and on when a report fact is superseded by an announcement.
5. **Entity-resolution contract (shared, mandatory — see HR-G).** Both engines must bind every signal to the same company + period via one identity resolver, or cross-engine evidence silently mixes issuers.

---

## 7. Should the Canonical Taxonomy Be Report-, Source-, or Source-Agnostic? (Task 7)

**Source-agnostic taxonomy (the *what*) + source-aware adapters and provenance (the *how/where*).** This is the decisive recommendation.

- **Not report-centric:** its reliable axis (`source_section`) does not exist for five of seven sources; it would degrade to unmapped chaos off-report.
- **Not source-centric:** a per-source taxonomy fragments the same real-world theme into disconnected silos — the annual-report "capacity expansion" narrative, the announcement of a new plant, the analyst note, and the market reaction would live in four separate vocabularies and could never be unified. That destroys the entire value of multi-source.
- **Source-agnostic:** Categories (Outlook, Strategy, Business/Operational Risk, Governance, ESG) and core themes are **universal concepts** that hold across every source. Each source attaches **evidence** to the same theme, tagged with `source_type`, `authority_class`, `event_time`, and source-specific provenance. The **mapping strategy is per-source** (annual reports keep the section prior; event/market sources rely on adapter-specific signal + the `area`-equivalent canonicalization), but the **target vocabulary is one.**

Consequence for the taxonomy doc: its "section is the reliable axis" rule becomes **annual-report-specific**, and each new source needs its own routing prior inside its adapter — but they all map into the **same frozen category/theme vocabulary**. Source-specific vocabulary continues to live only in the **sub-theme** layer under governed versioning.

---

## 8. Hidden Risks Introduced by External Sources (Task 8)

- **HR-A — Loss of the reliable classification axis.** `source_section` (closed-12) exists only for annual reports; off-report category routing falls entirely on the unreliable free-text axis → `unmapped` rate and misclassification rise sharply. *Mitigation:* per-source routing priors in adapters; per-source `unmapped`-rate monitoring; do not assume report-level mapping confidence elsewhere.
- **HR-B — Provenance heterogeneity threatens the citation guarantee.** `page_number` is meaningless for announcements (id/date), market data (date/series), web overview (url/snapshot). *Mitigation:* extend the citation taxonomy with `ANNOUNCEMENT_REF`, `REGULATORY_REF`, `MARKET_DATA_REF`, `URL_SNAPSHOT`; require an **immutable snapshot** per non-PDF source (web/market content is ephemeral) so citations stay reproducible.
- **HR-C — Recency↔authority inversion (freshness bias).** The freshest source (market) is least authoritative; over-weighting recency lets noise dominate, over-weighting authority makes the engine perpetually stale. *Mitigation:* claim-type-scoped weighting (§3).
- **HR-D — Correlated-source / circularity laundering.** Analyst and sector reports are often *derived from the annual report*; counting them as "independent corroboration" double-counts the same origin. Sell-side analyst reports are conflicted. *Mitigation:* a **source-lineage/independence contract** — corroboration weight only for genuinely independent origins; tag conflicted/derived sources.
- **HR-E — Temporal misalignment.** Mixing fiscal `value_year`, event dates, continuous market time, and static overviews can fabricate false trend/YoY signals (the FM3 extraction-gap problem, now cross-source). *Mitigation:* one unified `event_time` model + explicit alignment + coverage-parity guards before any cross-time claim.
- **HR-F — Contradiction overload with no resolution authority.** Multi-source guarantees disagreement; QAE must **surface and authority-weight** divergence, not adjudicate truth — but must also not present a low-authority contradiction as equal to a high-authority fact. *Mitigation:* divergence records carry both sides' authority class; never auto-resolve; never equal-weight.
- **HR-G — Entity resolution (new hard dependency).** Linking announcements, SECP notices, analyst/sector/market content to the right company *and period* across heterogeneous identifiers (ticker, registration no., name variants) is error-prone; a mis-link injects another issuer's themes. *Mitigation:* a shared, audited entity-resolution contract is a **prerequisite**, not a feature.
- **HR-H — Per-source coverage illusion.** A company with a rich report but no analyst coverage vs one with heavy market chatter → confidence varies by data *availability*, not company quality; absence of a source reads as absence of an issue. *Mitigation:* per-source coverage reporting; never average source absence into a single health score.
- **HR-I — Source authenticity / spoofing.** Announcements and web overviews may include unofficial/scraped content; an SECP notice is authoritative only if verified from the regulator. *Mitigation:* a verified-vs-unverified provenance flag; authority applies only to verified-origin signals.
- **HR-J — Taxonomy-drift pressure.** External vocabularies (analyst jargon, regulatory citations, market terms) pressure the sector-neutral theme set toward fragmentation. *Mitigation:* hold the source-agnostic line — new vocabulary enters only as **sub-themes** under governed versioning; never new top-level themes per source.

---

## 9. Long-Term Evolution Note (sequencing implication)

The multi-source contracts above are **not MVP work** and must not preempt the QAE MVP (annual-report, within-report, gate-first). But three of them are **architecture decisions that should be frozen now**, because retrofitting them later is expensive and they shape the MVP's data model:

1. **The normalized `QualitativeSignal` unit** (so the annual-report `Insight` is designed as a *specialization*, not the base).
2. **Source-agnostic taxonomy + per-source adapter boundary** (§7) — so the MVP taxonomy is not silently report-coupled.
3. **`event_time` + authority-class fields on every signal** — cheap to include now, painful to backfill.

Everything else (the new sources themselves, divergence detection, cross-source corroboration) is sequenced strictly **after** the single-source QAE MVP freezes and after the shared **entity-resolution** and **provenance-snapshot** contracts exist.

---

## 10. One-Paragraph Verdict

Adding the six external sources is a re-architecture, not an expansion: the QAE/taxonomy design's reliable classification axis (`source_section`) and its citation and temporal models are all annual-report-specific, and five of the seven sources have none of them. The engine survives intact only if the **canonical taxonomy is made source-agnostic** — one universal vocabulary of categories and themes, with **per-source adapters** that handle routing, provenance, and trust, and **source-tagged evidence** that lets the annual report, an announcement, an analyst note, and the market reaction all attach to the *same* theme. Authority must be **claim-type-scoped** (the audited issuer dominates facts about itself; independent regulator, analysts, and market dominate forward and compliance claims), evidence weight must compose authority × recency × independence × specificity × corroboration, and creation rights must be restricted (market and overview may never create themes; analyst/sector creations are quarantined as opinion/context) while corroboration and contradiction stay broad and never auto-resolve. The FVE↔QAE boundary sharpens to a single rule — **split every mixed source at ingestion: numbers to FVE under the integrity gate, narrative to QAE** — with a shared divergence, event-time, and entity-resolution contract between them. None of this is MVP work, but the `QualitativeSignal` unit, the source-agnostic taxonomy boundary, and the `event_time`/authority fields should be frozen now so the single-source MVP is not built into a report-only corner it cannot later escape.
