# Qualitative Analysis Engine — Canonical Taxonomy Architecture

**Status:** Design proposal. No code. Focus: taxonomy contracts, classification boundaries, generalization risk.
**Date:** 2026-06-02
**Resolves:** `qualitative_analysis_engine_architecture.md` HD2 (free-text `area`/`source_section`), HD3 (built-in category overlap), HD5 (issuer-specific section names).
**Grounded in:** `ocr_engine/constants/insights_constants.py` (`INSIGHTS_RELEVANT_SECTIONS`, `INSIGHTS_FINANCIAL_KEYWORDS`, `GENERIC_INSIGHT_FILTER_PATTERNS`), the `Insight` model, and `InsightConfidenceGovernance`.

---

## 0. The Governing Insight (read first)

The two fields the taxonomy must canonicalize are **not equally unreliable**:

| Field | Reality | Reliability for classification |
|---|---|---|
| `source_section` | OCR already **normalizes** page headings to a **closed set of 12** (`INSIGHTS_RELEVANT_SECTIONS`) via alias matching, with its own confidence score. | **Semi-controlled.** A strong, low-cardinality signal. |
| `area` | **Free-text LLM output** per insight (e.g. "Debt", "Geographic Expansion", "Exports"). Unbounded cardinality, varies run-to-run. | **Unreliable.** High-cardinality, drifts. |

**Design consequence — the load-bearing decision of this document:** route **categories primarily from `source_section`** (closed, reliable) and use **`area` for theme/sub-theme clustering under canonicalization** (open, must be mapped). Do **not** make the free-text `area` the category authority. This inverts the naive approach and is what makes the taxonomy generalize.

Classification authority order is frozen as: **canonical theme mapping → section prior → extraction confidence.** Deterministic, in that order.

---

## 1. The Three-Level Taxonomy (Tasks 1–2)

A strict hierarchy: **Category → Theme → Sub-theme.** Categories and Themes are **closed controlled vocabularies**; Sub-themes are **controlled but governed-extensible**; anything unmatched lands in an explicit `unmapped` bucket (never dropped, never force-fit).

### 1.1 Content Categories (closed set — 6)
These are the QAE *content* categories. Recurring-theme detection and year-over-year change are **derived analyses over these categories, not categories themselves** — a distinction the taxonomy must enforce so they are never populated directly.

| Category | Canonical id | Source-section prior (from the 12) |
|---|---|---|
| Management Outlook | `outlook` | Outlook, CEO Review, Chairman Review, MD&A, Directors Report |
| Strategic Priorities | `strategy` | Strategy, Opportunities, Business Review, MD&A |
| Business Risks | `business_risk` | Risks, MD&A, Financial Review |
| Operational Risks | `operational_risk` | Risks, Business Review |
| Governance Themes | `governance` | Directors Report, Chairman Review, (Governance) |
| ESG / Sustainability Themes | `esg` | Sustainability, ESG |

### 1.2 Themes (closed, sector-neutral core — ~4–6 per category)
A theme has exactly one **canonical parent category** plus a bounded set of **allowed secondary-tag categories** (§4). Illustrative core set (sector-neutral; cement-specific items are sub-themes, not themes):

- **Outlook:** Demand Outlook, Pricing/Margin Outlook, Investment/Capex Outlook, Macro/Regulatory Outlook.
- **Strategy:** Capacity Expansion, Market/Geographic Expansion, Cost Optimization, Diversification, Digital/Technology.
- **Business Risk:** Input Cost & Energy, FX & Interest Rate, Regulatory & Tax, Demand & Competition, Liquidity & Funding.
- **Operational Risk:** Supply Chain & Procurement, Production/Plant Reliability, Health & Safety, Workforce/Labor, Cybersecurity/IT.
- **Governance:** Board & Oversight, Internal Controls, Compliance & Ethics, Related-Party/Ownership.
- **ESG:** Emissions/Environment, Energy Transition, Community/Social, Sustainability Governance.

### 1.3 Sub-themes (governed-extensible — minimal seed only at MVP)
Sub-themes carry the **sector-specific** vocabulary, where overfit lives. Examples under *Input Cost & Energy*: Coal, Fuel/Oil, Electricity/Power, Freight (all seeded from `INSIGHTS_FINANCIAL_KEYWORDS`). MVP ships **structure + a thin seed + an `other` sub-theme**; it does not attempt exhaustive sub-themes.

---

## 2. Mapping Strategy (Task 3)

### 2.1 `source_section` → Category (the reliable axis)
- A **frozen deterministic map** from each of the 12 `INSIGHTS_RELEVANT_SECTIONS` to a **primary category + allowed secondary categories**. Section is a **prior**, not the verdict, because several sections are intrinsically multi-category:
  - **MD&A** and **Business Review** legitimately feed Outlook + Strategy + Operations → they contribute a *weak* prior across several categories, broken by the theme mapping.
  - **Risks** feeds both Business Risk and Operational Risk → split by theme (Input Cost/FX/Regulatory → business; Supply Chain/Plant/Safety → operational).
- Sections in `INSIGHTS_IGNORED_SECTION_KEYWORDS` (auditor, notes, AGM, shareholding) are out of qualitative scope by construction.

### 2.2 `area` → Theme / Sub-theme (the unreliable axis, canonicalized)
A four-tier match, reusing the existing `_normalize_text` normalization already in `InsightConfidenceGovernance`:

| Tier | Method | Mapping confidence |
|---|---|---|
| **Exact** | normalized `area` equals a theme/sub-theme alias | High (1.0) |
| **Alias** | normalized `area` in a curated alias dictionary | High–Medium |
| **Keyword** | `area` + `takeaway` contains controlled keyword signals (seeded from `INSIGHTS_FINANCIAL_KEYWORDS`) | Medium |
| **Unmapped** | no match | None → `unmapped` bucket |

### 2.3 Combining the two axes (the classification contract)
1. Canonicalize `area` → candidate theme(s) (with mapping confidence).
2. The theme's **canonical parent category** is the **primary category** (authority).
3. The **section prior** must be *consistent* with the theme's category; if it is, confidence is reinforced; if it **conflicts** (e.g. theme "Capacity Expansion" but section "Risks"), the insight is flagged `section_theme_conflict` and routed to the theme's category at **reduced confidence**, with the conflict recorded as evidence — never silently overridden either way.
4. If `area` is `unmapped`, fall back to **section-only** category assignment at **low confidence**, tagged `section_only`, and excluded from theme-level salience (it counts toward category raw-coverage but not mapped-coverage).

This makes the reliable axis (section) the safety net and the unreliable axis (area) the precision driver — and records every disagreement.

---

## 3. Overlap, Multi-tag, and Issuer-specific Sections (Task 4)

### 3.1 Overlapping themes (HD3)
- **One insight → exactly one canonical theme** (its strongest area match by tier, then confidence). This is the anti-double-count rule.
- A **theme may surface in multiple categories**, but with **one designated primary category** that owns it for coverage/salience counting. Secondary appearances are **cross-references**, displayed but **not re-counted**. This directly closes the double-counting failure mode (QAE FM4).

### 3.2 Multi-tag themes
- Secondary-category tags are drawn from a **bounded allow-list per theme** (max 2 secondaries). Example: *Capacity Expansion* → primary `strategy`, secondary `outlook`, `operational_risk`. Unbounded multi-tagging is prohibited (it dissolves structure — §6 TR6).
- Tags are **declarations on the theme definition** (frozen), not runtime LLM decisions.

### 3.3 Issuer-specific section names (HD5)
- The 12 canonical sections already absorb most variance, but **distinct canonical labels with overlapping meaning** exist (Chairman Review vs CEO Review vs Directors Report). The taxonomy defines **section alias-families** that map to the same category prior:
  - *Leadership narrative family*: Chairman Review, CEO Review, Directors Report, MD&A → Outlook/Strategy/Governance priors.
  - *Risk family*: Risks → Business/Operational.
  - *Forward family*: Outlook, Opportunities, Strategy → Outlook/Strategy.
  - *Sustainability family*: Sustainability, ESG → ESG.
- **Unknown section** (future issuer heading not in the 12, surfaced as `none`/rejected by OCR): insight routed by `area`/theme only, tagged `unmapped_section`, with a **coverage warning** — never force-fit.
- **Absent section** (issuer simply has no Sustainability section): the dependent category is **coverage-starved → `SKIPPED_INSUFFICIENT_COVERAGE`** at the QAE gate, with the absent section named as evidence.
- **Generalization contract:** the section→category map is **frozen over the 12 canonical sections**; supporting a new issuer section is a **governed taxonomy change** (versioned), not emergent behavior.

---

## 4. Confidence and Coverage Implications (Task 5)

### 4.1 A new confidence axis: mapping confidence
Taxonomy mapping introduces a **third confidence input** alongside the platform's existing two:

```
theme_confidence = min(
    insight_extraction_confidence,   # from OCR Insight.confidence
    section_identification_confidence,  # from SectionIdentificationReport
    mapping_confidence                # new: exact/alias/keyword/unmapped tier
)
```

- Themes built only from **keyword-tier** mappings are **capped** (analogous to the `review`-bucket / `clean_with_warning` ceilings already used in the platform).
- `section_theme_conflict` and `section_only` flags **lower** confidence and are recorded as evidence.
- **Confidence ≠ materiality** still holds: a high-salience risk theme is material even at medium mapping confidence.

### 4.2 Coverage must be reported as mapped vs raw
- **Raw coverage** = insights in a category by section prior. **Mapped coverage** = insights successfully canonicalized to a theme. The gap is the **`unmapped` rate**.
- A category with high raw coverage but high `unmapped` rate is **not** well-covered — reporting only raw coverage recreates the "coverage illusion" the QAE review warned about (FM5).
- Gate rule: `unmapped` rate above a frozen threshold → `ANALYZED_WITH_WARNING`; below a minimum mapped-coverage floor → `SKIPPED_INSUFFICIENT_COVERAGE`. The `unmapped` bucket is **surfaced as first-class evidence**, never hidden.

---

## 5. Hidden Risks (Task 6)

- **TR1 — Sector overfit (the dominant risk).** Themes/sub-themes seeded from one cement issuer (coal, freight, capacity) will not fit banks, textiles, power. *Mitigation:* keep **themes sector-neutral**; isolate **sector-specific vocabulary in sub-themes**; ship sector packs post-MVP. Mark every taxonomy entry as `sector_neutral` or `sector_specific`.
- **TR2 — `area` drift across OCR runs.** OpenAI variability changes both insight counts and area surface strings run-to-run; an incomplete alias dictionary makes `unmapped` rate spike silently. *Mitigation:* normalization + keyword-tier fallback; **pin taxonomy version + bundle fingerprint**; monitor `unmapped` rate as a health metric.
- **TR3 — The mapping is itself an unvalidated classifier.** Canonicalization can mis-route ("exchange rate risk" → Strategy instead of Business Risk) silently. *Mitigation:* a **mapping audit** + an `unmapped`/low-confidence **review bucket** (mirror `InsightConfidenceGovernance` routing); no analyst truth set yet = no accuracy claims (carry-over of QAE HD7).
- **TR4 — Granularity calibration.** Too-fine sub-themes → every theme has one insight, salience collapses; too-coarse → everything is "Operations". *Mitigation:* MVP keeps sub-themes minimal; tune against real salience distributions before expanding.
- **TR5 — Irreducible category overlap in the source itself.** Outlook / Strategy / Opportunities are **three separate sections** but conceptually fused; the section prior is genuinely ambiguous among them. *Mitigation:* crisp primary-category rules at the **theme** level (theme owns category), so section ambiguity does not propagate.
- **TR6 — Multi-tag explosion.** Unbounded secondary tags make every theme appear everywhere, defeating structure. *Mitigation:* max-2 secondary tags, declared on frozen theme definitions.
- **TR7 — Section prior is not ground truth.** The section identifier has its own confidence and OCR-fallback errors; over-trusting it mis-routes. *Mitigation:* section is a *prior*, theme mapping is authority; conflicts recorded, not silently resolved.
- **TR8 — A frozen taxonomy goes stale and breaks YoY comparability.** Adding themes later changes what "recurring" and "year-over-year change" mean. *Mitigation:* **taxonomy versioning** with a governed extension process; YoY comparisons must run within a single taxonomy version or carry an explicit migration map.

---

## 6. Recommended MVP Taxonomy Scope (Task 7)

**Freeze a small, sector-neutral core; defer sector depth.**

In scope:
1. **6 content categories** (closed) + explicit statement that Recurring Themes and YoY are derived analyses.
2. **Section→category map** over the 12 `INSIGHTS_RELEVANT_SECTIONS`, with alias-families and unknown/absent handling.
3. **~25–30 sector-neutral themes** (≈4–6 per category), each with canonical parent + bounded secondary tags + an alias seed.
4. **Sub-theme structure + a thin seed + a mandatory `other` sub-theme** per theme. No exhaustive sub-theme build.
5. **`unmapped` as a first-class bucket** at theme and sub-theme level, surfaced and reviewable.
6. **Mapping-confidence axis + mapped-vs-raw coverage reporting.**

Out of scope (MVP):
- Sector-specific theme packs (cement/bank/textile/power).
- Fine sub-theme taxonomies.
- Sentiment/tone vocabulary.
- YoY-stable theme-identity migration maps (needed only once multi-report + versioning exist).

**Single-issuer caveat:** the MVP taxonomy is seeded from Lucky. Before freeze, run the mapping over **Millat** (different sections — it has Chairman Review, no Directors Report/Outlook in the same shape) and measure `unmapped` rate per category; a second-issuer pass is a freeze prerequisite, not a nicety.

---

## 7. What Must Be Frozen Before Implementation Begins (Task 8)

These are the taxonomy **contracts** that must be locked before the QAE coverage gate or any theme assembly is built:

1. **Category set** — closed list of 6 content categories; Recurring/YoY declared as derived analyses (not populated directly).
2. **Section→category map** — frozen over the 12 `INSIGHTS_RELEVANT_SECTIONS`, including alias-families and unknown/absent-section behavior.
3. **Theme vocabulary** — closed core list, each with **canonical parent category** + **bounded secondary-tag allow-list (≤2)** + alias seed; each tagged `sector_neutral`/`sector_specific`.
4. **`area`→theme canonicalization contract** — normalization rule (reuse `_normalize_text`), four match tiers (exact/alias/keyword/unmapped), and the `unmapped` route.
5. **Anti-double-count rules** — one insight → one canonical theme; one theme → one primary category for counting; secondaries are cross-references only.
6. **Classification authority order** — canonical theme mapping → section prior → confidence; `section_theme_conflict` recorded, never silently overridden.
7. **Mapping-confidence axis** — definition + composition (`min`) with extraction and section confidence + keyword-tier ceiling.
8. **Coverage definition** — mapped vs raw coverage, `unmapped`-rate warning threshold and mapped-coverage floor for `SKIPPED`.
9. **Taxonomy version id + bundle-fingerprint pinning** — every QAE result records both, for reproducibility and YoY comparability.
10. **Governed extension process** — how new themes/aliases/sections are added under a new version without breaking prior comparisons.

Until items 1–8 are frozen, no QAE classification logic should be built — they are the contract the gate, theme assembly, and scorecard all depend on (the same "contracts first" discipline that the Forecast Validation rollout proved correct, and whose absence caused its Phase 9 scope drift).

---

## 8. One-Paragraph Verdict

The canonical taxonomy is QAE's keystone, and its design turns on one asymmetry the platform already created: `source_section` is a closed, OCR-normalized 12-value set, while `area` is unbounded free text. The correct contract therefore routes **categories from the reliable section axis** and uses the **unreliable area axis only for theme/sub-theme precision under explicit canonicalization**, recording every section-vs-theme disagreement instead of silently resolving it. A three-level hierarchy — 6 closed content categories, ~25–30 sector-neutral themes with bounded multi-tagging and single-primary counting, and a thin governed-extensible sub-theme layer where sector overfit is quarantined — resolves HD2, HD3, and HD5 without inventing a brittle one-to-one map. The dominant generalization risk is sector overfit, mitigated by keeping themes sector-neutral and validating `unmapped` rates on a second issuer before freeze. Freeze the ten contracts above first; build the gate and theme assembly only after — and the engine inherits a stable, versioned, auditable classification foundation rather than the silent miscategorization that free-text `area` would otherwise guarantee.
