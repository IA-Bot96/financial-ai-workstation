# Qualitative Analysis Engine — Implementation Sequencing Plan

**Status:** Implementation sequencing plan. No architecture changes. **All contracts are assumed frozen.**
**Date:** 2026-06-02
**Frozen inputs:** `canonical_qualitative_taxonomy_mvp.md` (taxonomy v1.0.0), `qualitative_signal_contract.md`, `qualitative_theme_assembly_contract.md`, `qualitative_scorecard_contract.md`.
**Target module:** `backend/qualitative_analysis_engine/` (mirroring `forecast_validation_engine/`).

---

## 0. Sequencing Principles (carried from the platform's proven path)

1. **Contracts first, then bottom-up by data dependency:** taxonomy data → models → classification services → admission gate → theme assembly → scorecard → orchestrator.
2. **Gate-first within execution:** the coverage gate is built and **run on the real bundle before** any theme-assembly logic is scoped — assembly is built **only for categories the gate admits** (the inverse of the Forecast Validation Phase 9 mistake, which built a deferred category ahead of admission).
3. **Real-bundle-gated progress:** each phase that touches classification or assembly is audited against the **real Lucky `.kb.json` insight set**, not fixtures only. Fixtures prove plumbing; real bundles prove behavior (the Query-Engine fixture-vs-real lesson).
4. **No synthetic-only depth:** MVP is **single-source (annual-report `Insight`) only**. Corroboration and cross-source contradiction have no real data to exercise — they are built **minimally as honored-but-inert structural paths**, never as deep logic proven only on synthetic fixtures.
5. **Version pinning everywhere:** `taxonomy_version`, `authority_matrix_version`, assembly/scorecard contract versions, and the source/bundle fingerprint are stamped from Phase 1 onward.
6. **Determinism:** classification and assembly are deterministic; runs pin a bundle fingerprint so audits are reproducible despite upstream OCR/LLM variability.

---

## 1. Implementation Phases (Task 1)

| Phase | Objective | Depends on | Audit milestone (artifact) | Exit criteria |
|---|---|---|---|---|
| **P0 — Taxonomy materialization** | Produce + validate `canonical_qualitative_taxonomy.json` from the frozen MVP content | content doc | `qae_taxonomy_integrity_audit.json` | All integrity checks pass (§7). |
| **P1 — Model layer** | All data models + enums + provenance union + version pins | P0 | `qae_phase1_report.json` | Models construct/validate; unit tests green. |
| **P2 — Taxonomy/classification service** | Loader + canonicalizer (`area`→theme) + section→category router + mapping confidence | P1 | `qae_mapping_audit.json` (real Lucky insights) | Mapping-method + per-category unmapped-rate measured. |
| **P3 — Signal adapter (annual report)** | OCR `Insight` → `QualitativeSignal` incl. derived fields | P2 | `qae_signal_generation_audit.json` (real bundle) | Signals generated; derived-field distributions sane. |
| **P4 — Admission / coverage gate** | Signal admission + creation-eligibility + per-category coverage gate → category statuses | P3 | `qae_coverage_gate_audit.json` (real bundle) | Deterministic statuses; **decides which categories enter P5**. |
| **P5 — Theme assembly** | Identity, dedup, (inert) corroboration/divergence, salience, confidence, materiality — **for admitted categories only** | P4 | `qae_theme_assembly_audit.json` (real bundle) | 100% grounded themes; dedup/salience correct. |
| **P6 — Scorecard / category aggregation** | `QualitativeCategoryResult` + coverage-first reporting + confidence distribution + materiality + unmapped backlog | P5 | `qae_scorecard_audit.json` | Three axes reported separately; no fused score. |
| **P7 — Orchestrator + run result + FVE handoff** | Orchestrator (gate→admit→assemble→aggregate→run result) + `narrative_only` handoff; end-to-end real-bundle run | P6 | `qae_real_bundle_smoke_audit.json` | Assembled `QualitativeRunResult` on real Lucky bundle. |
| **P8 — Second-issuer (Millat) pass** | Run end-to-end on Millat; measure unmapped/coverage/section variance; populate alias-extension backlog | P7 | `qae_millat_generalization_audit.json` | Per-category coverage + unmapped measured on issuer #2. |
| **P9 — Freeze readiness** | Assemble freeze evidence; analyst truth-set sample validation; freeze decision | P8 | `qae_freeze_readiness_audit.json` | Freeze criteria (§8) met or explicitly waived. |

**Critical sequencing dependency:** P4's real-bundle result is the **go/no-go input to P5 scope** — assembly is built first for the highest-coverage admitted categories (expected on Lucky: `business_risk`, `strategy`, `outlook`, `esg`, `operational_risk`), and **not built for categories the gate skips** (likely `governance`, boilerplate-starved).

---

## 2. Model Layer (Task 2) — built in P1

Pure data-contract realization, no logic. Build order within P1:

1. **Enums (frozen):** `source_type`, `claim_type`, `authority_class`, `provenance_type`, `mapping_method`, `theme_role`, category `status` enum, `entity_scope`, `horizon`, `time_basis`.
2. **`QualitativeSignal`** + the **provenance discriminated union** (`PDF_PAGE` is the only variant exercised at MVP; the others defined but unused) + version-pin fields. The annual-report-derived signal is the only producer at MVP.
3. **Taxonomy data models:** theme entry (`theme_ref`, `category_ref`, `secondary_categories`, `aliases`, `example_area_labels`, `never_merge_with`, `sector_neutral`) + loader target shape.
4. **`QualitativeTheme`**, **`ThemeEvidence`**, **`Divergence`** (defined; divergence inert at single-source).
5. **`QualitativeCategoryResult`**, **`QualitativeRunResult`**, scorecard sub-models, **FVE handoff payload** model.

Exit: every model validates against the contracts; serialization round-trips; no behavior.

---

## 3. Service Layer (Task 3) — built in P2–P3

**P2 — classification services (the core of QAE):**
- **Taxonomy loader** — load + validate `canonical_qualitative_taxonomy.json` (integrity already checked in P0; loader re-asserts at startup).
- **Canonicalizer (`area` → theme)** — tiers exact → alias → keyword → unmapped over `_normalize_text`; honors the ambiguous-keyword exclusion ("energy"/"cost"/"regulatory" matched only via disambiguating multi-word aliases); emits `mapping_method` + `mapping_confidence`.
- **Section → category router** — frozen section→category prior over the 12 `INSIGHTS_RELEVANT_SECTIONS`; sets `routing_basis = section_prior`; records `section_theme_conflict` where the section prior disagrees with the theme's category (never silently overridden).
- **Confidence composer** — `min(extraction, mapping, structure)` with keyword-tier ceiling.

**P3 — signal adapter (annual report only):**
- Maps `Insight` → `QualitativeSignal`; derives `claim_type`/`horizon` from `source_section` (the two **derived mini-classifiers** — flagged risk §9), fixes `authority_class = audited_issuer`, `entity_scope = company`, maps `observation_time ← source_report_year`, `subject_period ← value_year`, `time_basis = fiscal`, `PDF_PAGE` provenance from `page_number`/`source_section`/`workbook_fingerprint`, `extraction_confidence ← Insight.confidence`, `structure_confidence ← section-id confidence`, `creation_eligible = true`.

---

## 4. Admission Layer (Task 4) — built in P4

Built and **audited on the real bundle before assembly**:
1. **Signal admission** — drop `unmapped` to the pool; keep mapped signals clearing the confidence floor with matching `entity_scope`.
2. **Creation-eligibility enforcement** — at MVP all annual-report signals are creation-eligible, but the gate is built so attach-only/ineligible signals (future sources) cannot instantiate.
3. **Per-category coverage gate** — computes mapped vs raw coverage, unmapped rate, salience tiers; assigns the deterministic `status` in the frozen precedence order (`SKIPPED_NO_ELIGIBLE_SIGNALS` → `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY` → `SKIPPED_INSUFFICIENT_COVERAGE` → `ANALYZED_WITH_WARNING` → `ANALYZED`), using the taxonomy doc's initial thresholds (>25% warn, >50%/floor skip).
4. **Gate-only run** → `qae_coverage_gate_audit.json` — the decision artifact for P5 scope.

---

## 5. Theme Assembly Layer (Task 5) — built in P5, admitted categories first

Build order (highest-coverage admitted categories first):
1. **Theme identity** — `(entity_ref, entity_scope, theme_ref, taxonomy_version)`; period-agnostic, text-independent.
2. **Grouping + creation gate** — instantiate a theme only with ≥1 mapped creation-eligible signal.
3. **Dedup** — provenance-locator keyed (not text); `duplicate_count` retained.
4. **Salience** — independent-origin + section spread (single-origin at MVP → most themes are single-source; salience tiers still computed).
5. **Confidence composition** — floor + (inert) corroboration lift − (inert) contradiction penalty, clamped by class ceiling.
6. **Materiality** — salience + category severity prior + recency + (no) contradiction; reported separate from confidence.
7. **Corroboration / divergence** — **built minimally as inert paths** (single-source MVP has no independent origins to corroborate and no cross-source contradictions); structurally honored, returns empty, covered by clearly-labeled synthetic tests only. **Not deepened until multi-source arrives.**
8. **Evidence builder** — `ThemeEvidence` with per-source provenance, salience, mapping methods, `low_salience` labels.

Exit: 100% of themes grounded in ≥1 admitted mapped signal; zero force-fit; dedup/salience verified on real bundle.

---

## 6. Scorecard / Orchestrator Layer (Task 6) — built in P6–P7

**P6 — category aggregation + scorecard:**
- `QualitativeCategoryResult` per category (owned themes, coverage, confidence distribution, non-dilutive materiality roll-up, divergence/unmapped refs, skip reason+evidence).
- Coverage-first reporting; confidence as **distribution + ceiling provenance**; materiality ranked independently; unmapped backlog surfaced. **No fused score field.**

**P7 — orchestrator + run result + handoff:**
- **Orchestrator** (mirrors `ForecastValidationOrchestrator`): run gate → admit → assemble (admitted categories) → aggregate → build `QualitativeRunResult`; deferred/skip accounting explicit and evidenced.
- **Run status** is coverage-framed (`ANALYZED_WITH_COVERAGE` / `PARTIAL_COVERAGE` / `INSUFFICIENT_COVERAGE`), never a grade.
- **FVE handoff payload** — themes tagged `narrative_only`; quantified-reference themes flagged for the FVE gate (never exported as values); coverage caveats included.
- **End-to-end real-bundle smoke run** → `qae_real_bundle_smoke_audit.json` (the MVP spine, the FVE-Phase-10 equivalent).

---

## 7. Audit Milestones (Task 7)

| Milestone | Phase | Decision it gates |
|---|---|---|
| `qae_taxonomy_integrity_audit.json` | P0 | No duplicate `theme_ref`; every `category_ref` valid; `secondary_categories` ≤2; `never_merge_with` symmetric; ambiguous single-word aliases absent. **Blocks all build if failing.** |
| `qae_mapping_audit.json` | P2 | First real unmapped-rate reading per category vs the taxonomy doc estimates; flags alias-seed gaps early. |
| `qae_signal_generation_audit.json` | P3 | Derived-field (`claim_type`/`horizon`) distribution sanity; signal counts vs insight counts. |
| `qae_coverage_gate_audit.json` | P4 | **Which categories are analyzable** — the go/no-go scoping input for P5. |
| `qae_theme_assembly_audit.json` | P5 | 100% grounding; dedup correctness; salience tiers; (inert) divergence = empty. |
| `qae_scorecard_audit.json` | P6 | Three-axis separation; no fused score; coverage-first. |
| `qae_real_bundle_smoke_audit.json` | P7 | Assembled run result on real Lucky bundle — headline readiness artifact. |
| `qae_millat_generalization_audit.json` | P8 | Second-issuer coverage + unmapped; alias-extension backlog. |
| `qae_freeze_readiness_audit.json` | P9 | Freeze decision evidence. |

---

## 8. Freeze Criteria (Task 8)

From the scorecard contract §10 + taxonomy freeze + implementation gates. MVP may freeze when:

1. **End-to-end real-bundle run** produces a `QualitativeRunResult` on the real Lucky bundle (P7).
2. **Coverage-first headline** present; **no fused score field** exists.
3. **Deterministic category statuses**; every `SKIPPED_*` carries reason + coverage-gap evidence.
4. **Anti-illusion distinction** enforced: "analyzed-none-found" ≠ "skipped-couldn't-see".
5. **0 ungrounded themes; 0 force-fit unmapped signals.**
6. **Three axes** (coverage / confidence-distribution / materiality) reported independently.
7. **FVE handoff** tagged `narrative_only`; quantified references routed to the gate, not exported as values.
8. **Version pinning** on every signal/theme/run (taxonomy 1.0.0 + matrix + contracts + fingerprint).
9. **Unmapped policy** active: thresholds enforced; backlog surfaced; no runtime vocabulary growth.
10. **Second-issuer (Millat) pass complete** — coverage + unmapped measured; not a nicety.
11. **Analyst truth-set validation** on a theme/divergence sample (the platform-wide open assurance gap) — required before any accuracy claim.
12. **Honest framing:** freeze as **coverage-first qualitative understanding** (READY_WITH_LIMITATIONS-style), single-source; YoY remains `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY`; corroboration/divergence inert until multi-source.
13. **Test coverage** across `clean`/mapped, `unmapped`, `low_salience`, every category `status`, and the skip-evidence path.

---

## 9. Implementation Risks (Task 9)

- **IR-1 — Derived mini-classifiers (`claim_type`, `horizon`).** Authority weighting depends on `claim_type`, which is *derived from `source_section`* (signal-contract HR-1). A wrong section→claim_type rule silently mis-weights authority. *Sequencing action:* freeze + audit the derivation table in P3; surface conflicts as evidence.
- **IR-2 — Unmapped rate exceeds thresholds late.** If P2's `qae_mapping_audit` shows `operational_risk`/`esg`/Millat-`strategy` above thresholds, categories warn/skip and rework hits the alias seed. *Action:* P2 is an **early** checkpoint precisely to catch this before assembly is built; extend aliases by governed minor version, not by widening matching.
- **IR-3 — Synthetic-only corroboration/divergence (the FVE Phase 9 trap).** Single-source MVP cannot exercise corroboration or cross-source contradiction on real data. *Action:* build them **minimally and inert**; label their tests as synthetic-not-real-proven; do **not** deepen until multi-source — count them as scaffolding, not MVP feature progress.
- **IR-4 — Building assembly for skipped categories.** Investing P5 effort in a category the gate skips (e.g. `governance` starvation) repeats the Phase 9 misallocation. *Action:* P5 scope is strictly driven by the P4 real-bundle gate result.
- **IR-5 — `taxonomy.json` drift from the frozen `.md` source.** Hand divergence between the content doc and the JSON. *Action:* P0 integrity audit asserts JSON matches the frozen content; JSON is generated/checked from the doc, not hand-edited independently.
- **IR-6 — Test non-determinism from upstream OCR/LLM variability.** Insight counts vary run-to-run (OCR freeze: 198→175). *Action:* pin a fixed bundle fingerprint for all P2–P8 audits; never test against a live re-extraction.
- **IR-7 — Coverage-illusion regression in the scorecard.** Pressure to emit a single convenient score. *Action:* the P6 audit explicitly asserts no fused score and coverage-first ordering (freeze criterion 2).
- **IR-8 — Governance/ESG starvation misread.** A `SKIPPED` governance category read as "no governance issues." *Action:* P6/P7 audits verify skip-vs-empty distinction and propagate the coverage caveat into the FVE handoff.
- **IR-9 — Millat alias gaps surface only at P8.** Late discovery of agri/auto vocabulary gaps. *Action:* treat P8 unmapped findings as a governed v1.1 alias backlog, not a freeze blocker for the Lucky-validated MVP — but record them explicitly.
- **IR-10 — No analyst truth set.** Mapping/materiality/divergence correctness unverified (platform-wide gap). *Action:* P9 truth-set sample on the highest-materiality themes before any accuracy claim; deterministic rules audited in the interim.

---

## 10. Verdict

The build order is the platform's proven path applied to QAE with all contracts frozen: materialize and integrity-check the taxonomy (P0), realize the models (P1), build the classification services and the single annual-report signal adapter (P2–P3), then **run the coverage gate on the real bundle before scoping assembly** (P4) so theme assembly is built only for admitted, high-coverage categories (P5) — never the Forecast-Validation-Phase-9 mistake of deepening a category the data cannot support. Aggregate into a coverage-first scorecard with the three axes kept separate and no fused score (P6), assemble the orchestrator and run it end-to-end on the real Lucky bundle (P7), validate generalization on Millat (P8), and freeze only after a truth-set sample (P9). The dominant implementation risks are all sequencing risks already mitigated by the order itself — early unmapped measurement at P2, gate-before-assembly at P4, and treating corroboration/divergence as inert single-source scaffolding rather than synthetic-proven features — so that the MVP ships an honest, deterministic, coverage-first qualitative-understanding engine rather than an over-built one whose richest code never runs on real data.
