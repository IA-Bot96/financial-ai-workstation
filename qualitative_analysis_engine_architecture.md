# Qualitative Analysis Engine — Architecture

**Status:** Design proposal. No code. Architecture, contracts, boundaries, risks, MVP scope.
**Date:** 2026-06-02
**Position in platform:** Fifth engine. Consumes the qualitative output of OCR Engine v1; deterministic-first; gate-first; evidence/provenance-bound — same discipline as Query Engine Core, Historical Series Integrity Gate, and Forecast Validation.

---

## 0. Why This Engine, and Why Now

The platform extracts and validates **numbers** well, but its qualitative output stops at *atomic* insights: OCR Engine v1 emits a flat list of `Insight` records (one takeaway each) plus an Insights / Insights Review worksheet. There is no engine that turns that bag of insights into **structured qualitative understanding** of a company — its outlook, priorities, risk posture, governance/ESG themes, recurring narrative, and how the story changes year over year.

A decisive readiness fact separates this engine from Forecast Validation: **the qualitative dataset is the one part of OCR output that is *not* review-gated or scale-corrupted.** On the latest Lucky bundle the OCR engine produced strong, section-diverse coverage (Risks 45, Strategy 47, Sustainability 42, Outlook 24, Opportunities 37, plus Business/CEO Review), and the OCR freeze audit already rated Qualitative Analysis **`v1_ready`**. Where Forecast Validation could admit only EPS, the Qualitative Analysis Engine (QAE) has real, executable coverage today. This is the highest-readiness next engine — provided one structural gap (a canonical theme taxonomy over free-text `area`/`source_section`) is closed first.

---

## 1. Responsibilities (Task 1)

The QAE is a **deterministic synthesis and characterization layer** over already-extracted insights and narrative-section metadata. It is responsible for:

1. **Theme assembly** — cluster atomic insights into named, evidence-backed qualitative themes within defined categories.
2. **Category characterization** — produce a structured profile per analysis category (outlook, strategy, risks, governance, ESG, recurring themes, YoY change).
3. **Coverage gating** — determine, before synthesis, whether each category has sufficient insight volume, section presence, and confidence to be analyzable; emit `SKIPPED` with a deterministic reason otherwise.
4. **Salience / prevalence measurement** — quantify how strongly a theme is supported (how many insights, how many sections, what confidence) so a single boilerplate sentence is not presented as a company-defining theme.
5. **Year-over-year narrative change detection** — where ≥2 `source_report_year` filings exist, classify themes as emerged / persisted / intensified / diminished / disappeared, **with coverage-parity guards**.
6. **Evidence and provenance binding** — every theme and every change traces to specific insights, sections, pages, and report years; no ungrounded synthesis.
7. **Confidence governance** — compose deterministic confidence per theme/category with ceilings, respecting upstream insight routing; keep confidence separate from materiality.
8. **Honest coverage reporting** — a run-level qualitative scorecard whose headline encodes *how much of the report was analyzable*, not a flattering single score.

It is **not** responsible for: extracting text, identifying sections, generating atomic insights, answering ad-hoc questions, validating numbers, or authoring free-form narrative.

---

## 2. Boundaries (Task 2)

### Belongs in QAE
- Theme clustering, category characterization, recurring-theme detection, YoY narrative-change classification, salience scoring, qualitative coverage gating, qualitative scorecard.

### vs OCR Engine (upstream producer — do not duplicate)
- OCR owns: PDF text extraction, narrative **section identification** (`SectionIdentificationReport`), atomic **insight extraction**, and **`InsightConfidenceGovernance`** (export/review/reject routing). 
- QAE **consumes** `InsightsExtractionResult` and section diagnostics. It must **not** re-run OCR, re-identify sections, or re-extract insights. If insights are missing, the answer is `SKIPPED`/under-covered — never re-extraction.

### vs Query Engine (sibling consumer of the same `InsightDataset`)
- Query Engine answers *"what does the report say about X?"* (retrieval + Q&A, owns `InsightDataset` indexing and citation plumbing).
- QAE answers *"what is the company's qualitative posture across these categories, and how is it changing?"* (synthesis + structure).
- QAE **may reuse** Query Engine insight retrieval contracts to fetch insights by area/section/year, but owns classification and theme assembly. It does not perform query planning or one-off answers.

### vs Forecast Validation Engine (bidirectional, non-authoritative)
- QAE characterizes **narrative**; FVE validates **numbers**. QAE must **never assert or validate a numeric fact.** When a theme references a number (e.g. "borrowings increased to finance expansion"), QAE reports the *narrative claim* with provenance and may **flag it** for FVE — but does not verify it.
- Reverse direction: FVE's deferred "insight-aware plausibility" phase will **consume** QAE themes as *non-authoritative supporting evidence*. Therefore QAE output must be structured for that consumption, and the contract must state: **QAE is never the arithmetic authority; FVE may not treat a QAE theme as a validated number.**

### vs Future LLM layers (the sharpest boundary, because QAE is inherently more semantic)
- QAE is **more LLM-dependent** than FVE — theme classification and narrative-change reasoning are semantic. The line is drawn at the **artifact**, not the absence of LLMs:
  - An LLM **may** assist theme clustering/classification **inside** the engine, but only under governance (grounded in admitted insights, output validated into deterministic structures with evidence).
  - A downstream LLM presentation layer **may** rephrase/summarize QAE's structured output for humans.
  - No LLM (inside or downstream) may **invent a theme not traceable to an admitted insight**, change a classification, alter citations, upgrade confidence, or convert a `SKIPPED` category into an analyzed one.
- This boundary is a named risk (§12 FM1) precisely because it is easy to cross here.

---

## 3. Engine Inputs (Task 3)

| Input | Source | Usage |
|---|---|---|
| `InsightsExtractionResult` (`Insight[]` + diagnostics) | OCR Engine | Primary substrate: atomic insights with `area`, `takeaway`, `source_section`, `value_year`, `source_report_year`, `page_number`, `confidence`. |
| Insight **governance routing** (export / review / reject) | OCR `InsightConfidenceGovernance` | Determines which insights are eligible for synthesis and at what confidence weight. **Contract decision required** (see §11 HD4). |
| `SectionIdentificationReport` | OCR | Section presence/absence and section-ID confidence → coverage gating. |
| `InsightDataset` / insight index | Query Engine / `CompanyKnowledgeBase` | Optional retrieval path (by area/section/year). |
| Bundle metadata | `.kb.json` | `company_name`, `report_years`, `workbook_id`, `workbook_fingerprint`, `schema_version` → pinning and provenance. |
| **Canonical theme/category taxonomy** | New QAE contract (does not exist yet) | Maps free-text `area`/`source_section` to controlled categories and themes (§11 HD3). |
| Multi-report insight set keyed by `source_report_year` | Multiple bundles (post-MVP) | Required for YoY narrative change. |
| Raw narrative section text/chunks | OCR (post-MVP optional) | Deeper synthesis beyond lossy atomic takeaways. |

**MVP consumes atomic insights + section diagnostics only.** Raw-chunk access is post-MVP.

---

## 4. Engine Outputs (Task 4)

- **`QualitativeAnalysisResult`** (root): company, `report_years`, bundle fingerprint, per-category results, run-level scorecard, coverage summary, aggregated evidence/citations/provenance.
- **`QualitativeCategoryResult`**: category, status (`ANALYZED` / `ANALYZED_WITH_WARNING` / `SKIPPED_INSUFFICIENT_COVERAGE` / `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY`), `themes[]`, coverage metrics, composed confidence (with ceiling), evidence refs.
- **`QualitativeTheme`**: canonical theme label, category, grounded summary (extractive, traceable), supporting insight ids, source sections, `source_report_years`, page citations, **salience** (supporting-insight count, section spread), confidence, optional coarse direction (improving/worsening/neutral), `is_recurring` flag, `change_vs_prior` (YoY only).
- **`NarrativeChangeResult`** (YoY): per theme/category — `emerged` / `persisted` / `intensified` / `diminished` / `disappeared` / `indeterminate_coverage_gap`, with prior- and current-period evidence.
- **Coverage summary**: sections present vs absent, insight volume by category, % of categories analyzable, governance-route breakdown.
- **Run-level qualitative scorecard**: coverage-first; analyzable-coverage as the headline signal, not a single flattering score.

---

## 5. Analysis Categories (Task 5)

Each category declares its required source sections, minimum coverage, and temporal requirement.

| Category | Primary source sections (typical) | Temporal need | MVP |
|---|---|---|---|
| **Management Outlook** | Outlook, CEO/Chairman Review, MD&A | 1 report | ✅ |
| **Strategic Priorities** | Strategy, Business Review, Opportunities | 1 report | ✅ |
| **Business Risks** | Risks, MD&A | 1 report | ✅ |
| **Operational Risks** | Risks, Business Review (operations) | 1 report | ✅ |
| **Governance Themes** | Directors' Report, Governance | 1 report | ✅ (coverage-guarded — see HD6) |
| **ESG / Sustainability Themes** | Sustainability, ESG | 1 report | ✅ (coverage-guarded) |
| **Recurring Narrative Themes (within-report)** | cross-section | 1 report | ✅ |
| **Year-over-Year Narrative Change** | all, matched across reports | **≥2 `source_report_year`** | ❌ Deferred |

**Hard rule mirroring Forecast Validation:** YoY narrative change is **structurally un-runnable on single-report bundles** (current Lucky bundle: `report_years=[2025]`, one `source_report_year`). It is defined now but `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY` until multi-report ingestion exists — do **not** build its rules ahead of the data (the Phase 9 Forecast Validation mistake).

---

## 6. Evidence Requirements (Task 6)

- **No theme without grounded evidence.** Every `QualitativeTheme` must reference ≥1 admitted insight by deterministic id. A theme not traceable to admitted insights is prohibited (the platform's hard anti-hallucination rule).
- **Evidence contents per theme:** supporting insight takeaways, `source_section`(s), `source_report_year`(s), `page_number`(s), per-insight confidence, governance route, and salience (support count + section spread).
- **Single-insight themes must be labeled low-salience** — never presented with the same weight as multi-insight recurring themes.
- **Boilerplate exclusion:** insights matching the upstream generic-pattern filter (and lacking specificity) must not become standalone themes.
- **YoY evidence:** both prior-period and current-period supporting insights cited; any `disappeared`/`emerged` classification must also cite the **section-coverage status** of both years (to distinguish real change from extraction gaps — §12 FM3).
- **Skipped categories are evidenced, not silently omitted** (the Forecast Validation Phase 10 lesson): each `SKIPPED` carries its coverage diagnostics.

---

## 7. Confidence Model (Task 7)

Reuses the Forecast Validation contract-decisions composition pattern.

- **Theme confidence** = deterministic function of: supporting insight confidences, salience (count/section spread), section-identification confidence, and governance route. Composed by `min`-style flooring so a theme is never more confident than its weakest required input.
- **Ceilings by governance route:** themes built only from `review`-bucket insights are capped (analogous to `clean_with_warning` ⇒ 0.80); `reject`-bucket insights are excluded from synthesis entirely.
- **Coverage-adjusted category confidence:** low section coverage lowers category confidence or forces `SKIPPED`.
- **Confidence ≠ materiality.** A high-salience risk theme is **material** even at medium extraction confidence; report **materiality/salience and confidence as separate axes** (mirrors FVE "confidence cannot override severity"). A downstream layer may not use high confidence to suppress a material theme or vice versa.
- **Buckets** align with the platform: High ≥0.85 / Medium 0.65–0.84 / Low 0.40–0.64 / Unreliable <0.40, reusing the existing insight confidence vocabulary.

---

## 8. Citation / Provenance Requirements (Task 8)

Reuses the four-type citation taxonomy from the Forecast Validation contract decisions.

| Citation type | When used in QAE |
|---|---|
| `PDF_PROVENANCE` | **Primary.** Theme/insight cites `source_report_year` + `page_number` + `source_section`. |
| `WORKBOOK_CELL` | Only when the supporting insight was exported to the Insights worksheet and has a persisted cell mapping. |
| `GATE_OVERRIDE` | N/A for QAE (no value-selection override). |
| `NONE` | No reliable citation → the theme is **not allowed** to be emitted. |

- **Every theme and every YoY change must carry provenance**; uncited synthesis is prohibited.
- **No false precision:** QAE must not claim citation precision the underlying insight does not have (insights carry page-level, not sentence-level, provenance).
- **Bundle binding:** every result records `workbook_fingerprint` + `schema_version` so a qualitative profile is reproducible against a specific bundle (insight counts vary run-to-run — §11 HD1).

---

## 9. MVP Scope (Task 9)

The MVP is a **gate-first within-report qualitative profile** — genuinely executable on the current bundle (unlike the Forecast Validation MVP).

**In scope:**
1. **Canonical taxonomy contract** (category + theme + `area`/`section` mapping) — the prerequisite keystone.
2. **Qualitative Coverage Gate** — per-category analyzable / under-covered / temporally-insufficient classification, with deterministic `SKIPPED` reasons; runs before synthesis.
3. **Theme assembly + category characterization** for the seven single-report categories, evidence- and provenance-bound, confidence-ceilinged.
4. **Within-report recurring-theme detection** (cross-section clustering).
5. **Orchestrator + run-level qualitative scorecard** with coverage-first reporting and evidence/citation aggregation.
6. **Honest `SKIPPED` accounting** for under-covered categories and (always, on current data) YoY.

**Out of scope (MVP):**
- Year-over-year narrative change (no multi-report data yet).
- Cross-issuer / sector benchmarking.
- Sentiment/tone beyond coarse direction.
- Deep synthesis from raw narrative chunks.
- Free-form LLM narrative report generation.
- Contradiction detection against FVE numbers.

**MVP realism check:** on the current Lucky bundle, Risks/Strategy/Sustainability/Outlook all have strong insight coverage, so the MVP produces *real* characterizations today — the engine ships value immediately, with YoY honestly deferred.

---

## 10. Post-MVP Roadmap (Task 10)

1. **Year-over-Year narrative change** — unlock when ≥2 `source_report_year` filings exist **and** the canonical taxonomy stabilizes theme matching across years **and** coverage-parity guards are in place.
2. **Deeper synthesis from raw narrative chunks** — beyond lossy atomic takeaways.
3. **Sentiment / tone / hedging analysis** — evidence-bound, coarse-to-fine.
4. **FVE Phase-3 integration** — expose QAE themes as non-authoritative narrative support for forecast plausibility.
5. **Narrative-vs-numbers contradiction detection** — cross-engine with FVE ("narrative says expansion; OCF says contraction").
6. **Cross-issuer / sector qualitative benchmarking.**
7. **Governed LLM presentation layer** — human-readable summaries over deterministic structured output.

---

## 11. Hidden Dependencies (Task 11)

- **HD1 — Run-to-run non-determinism of the substrate.** OCR insight counts vary across runs (the OCR freeze recorded accepted insights 198→175 between runs from OpenAI variability). QAE output therefore changes unless **pinned to a bundle fingerprint** (like FVE). Without pinning, "recurring" and YoY signals are unstable.
- **HD2 — `area` and `source_section` are free-text, LLM-generated strings, not controlled vocabularies.** Recurring-theme clustering and YoY matching require a **canonical theme/area taxonomy + mapping contract that does not yet exist.** This is the single largest dependency and the keystone of the MVP. Without it, category assignment is arbitrary and YoY matching is impossible.
- **HD3 — Category overlap is built into the data.** One insight ("expanding into Middle East") legitimately touches Outlook, Strategy, and Business Review. The taxonomy must define multi-tagging and de-duplication, or themes double-count across categories.
- **HD4 — Governance-route ingestion contract.** If QAE consumes only `export` insights it loses the `review` signal; if it consumes all it may synthesize from `reject`-bucket boilerplate. The ingested routes and their confidence weights must be an explicit contract decision.
- **HD5 — Section taxonomy is issuer-specific.** Lucky has "CEO Review"; Millat has "Chairman Review" and different sections. Single-issuer (Lucky) tuning will not generalize without a section-alias map — the same generalization gap the integrity gate has.
- **HD6 — The boilerplate filter can starve the Governance/ESG categories.** The upstream generic-pattern filter (correctly) removes platitudes — but governance/ESG narrative is *disproportionately* boilerplate, so those categories may be coverage-starved precisely because the filter worked. The gate must report this honestly rather than emit thin themes.
- **HD7 — No qualitative truth set.** Like the integrity gate, theme correctness is unverifiable at MVP. An analyst-confirmed truth set is required before any freeze claims theme accuracy (platform-wide open assurance gap).

---

## 12. Likely Failure Modes (Task 12)

- **FM1 — Ungrounded/hallucinated themes.** LLM synthesis invents narrative absent from the report. *Mitigation:* every theme cites ≥1 admitted insight; deterministic assembly; LLM constrained to admitted evidence.
- **FM2 — Boilerplate-as-substance.** "Committed to sustainability" presented as a defining ESG theme. *Mitigation:* generic-pattern filter + salience thresholds + specificity requirement.
- **FM3 — False YoY change from extraction noise (most dangerous).** A theme "disappears" only because OCR missed that section that year — the qualitative analog of scale-corruption. *Mitigation:* gate YoY on section-coverage **parity** across years; emit `indeterminate_coverage_gap` instead of asserting change. This is the strongest reason to defer YoY.
- **FM4 — Category double-counting / inconsistent classification.** *Mitigation:* canonical taxonomy + deterministic mapping; explicit multi-tag reporting.
- **FM5 — Coverage illusion.** A "complete" profile actually built from three insights in one section, over-trusted by the reader. *Mitigation:* coverage-first scorecard, per-theme salience, `SKIPPED` under-covered categories.
- **FM6 — Confidence inflation.** Medium-confidence summaries presented as authoritative. *Mitigation:* governance-route ceilings; materiality reported separately from confidence.
- **FM7 — Issuer/section variability → silent under-coverage.** Missing/renamed sections produce thin categories without warning. *Mitigation:* section-coverage gate + explicit absent-section reporting.
- **FM8 — Tone/hedging misread.** Forward-looking caveats or hedged optimism misclassified as fact. *Mitigation:* keep sentiment post-MVP / coarse and evidence-bound.

---

## 13. Recommended Implementation Sequencing (Task 13)

Mirror Forecast Validation's *good* sequencing (contracts → gate → executable categories → orchestrator → real-bundle run), and avoid its *bad* sequencing (do not build deferred/blocked categories early).

1. **Contracts first (keystone).** Canonical category/theme taxonomy + `area`/`source_section` mapping (HD2/HD3/HD5); governance-route ingestion contract (HD4); citation, confidence-composition, and coverage contracts; bundle-fingerprint pinning (HD1). Nothing synthesizes before this exists.
2. **Qualitative Coverage Gate.** Build the admission gate (analyzable / under-covered / temporally-insufficient), with deterministic `SKIPPED` reasons; **run it on the real Lucky bundle first** to confirm which categories are genuinely analyzable.
3. **Theme assembly for the highest-coverage categories first** — Risks, Strategy, Sustainability, Outlook (strongest real coverage), grounded + evidenced + confidence-ceilinged.
4. **Orchestrator + run-level qualitative scorecard** with coverage-first reporting and evidence/citation aggregation (apply the FVE Phase 10 pattern; produce one assembled result on the real bundle).
5. **Within-report recurring-theme detection.**
6. **Defer YoY** behind an explicit temporal-coverage unlock contract; do not implement its rules until multi-report bundles + stable taxonomy exist.
7. **Analyst truth-set validation** of the gate and a sample of themes before any freeze claim of accuracy (HD7).

---

## 14. One-Paragraph Verdict

The Qualitative Analysis Engine is the natural and highest-readiness next engine: it operates on the one OCR output that is rich and not review-gated, and the platform's deterministic-first, gate-first, evidence-bound patterns transfer directly. Built correctly, it characterizes a company's outlook, strategy, risks, governance, and ESG narrative — with grounded evidence, honest coverage, and confidence governance — and lays the contract for year-over-year narrative change once multi-report data arrives. Its one true prerequisite is a **canonical theme taxonomy over the free-text `area`/`source_section` fields**; without it, clustering and YoY matching have no foundation. Build the taxonomy and coverage gate first, ship a within-report qualitative profile that genuinely executes on today's bundle, defer year-over-year behind a temporal-coverage unlock contract, and keep every theme traceable to an admitted insight — and this engine closes the platform's last major capability gap without repeating the over-building mistake that the Forecast Validation rollout had to correct.
