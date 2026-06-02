# QAE Category Scorecard & Run Result — Contract

**Status:** Contract specification. No code. Focus: governance, coverage, reporting, engine outputs.
**Date:** 2026-06-02
**Derived from:** `qualitative_analysis_engine_architecture.md`, `qualitative_taxonomy_architecture.md`, `qualitative_signal_contract.md`, `qualitative_theme_assembly_contract.md`, `qualitative_analysis_multi_source_architecture_review.md`.

---

## 0. First Principle — Coverage Is the Headline

This is the output layer, and its single most important governance job is **honesty about what could and could not be analyzed.** The directly-applicable precedent is the Forecast Validation freeze review: that run scorecard reported `overall_score = 70, outcome = warning, confidence = 0.55` while **10 of 11 metrics were unusable** — a coverage illusion in which a flattering mean hid that the engine validated almost nothing.

The QAE scorecard is contractually forbidden from repeating this. Therefore:

1. **The headline is coverage, never a single fused score.** A reader must see *how much of the report/sources was analyzable* before any confidence or materiality number.
2. **`SKIPPED ≠ FAIL ≠ "nothing wrong."** "Analyzed, none found" and "skipped, couldn't see" are different outcomes and must never collapse.
3. **Three axes reported separately** (coverage, confidence, materiality) — never blended into one number.
4. **No ungrounded or force-fit output** — every theme cites admitted signals; unmapped content is surfaced, not hidden.
5. **Reproducible** — every run pins taxonomy, authority-matrix, and assembly-contract versions plus source fingerprints.

---

## 1. QualitativeCategoryResult (Task 1)

One per content category (Outlook, Strategy, Business Risk, Operational Risk, Governance, ESG).

| Field | Semantics |
|---|---|
| `category_ref` | Canonical content category. |
| `status` | §3 enum (deterministic). |
| `owned_themes` | Theme instances whose **primary** category is this one (no recounts of secondary-tagged themes). |
| `theme_count_by_salience` | `{full_salience, low_salience}` — single-signal themes are `low_salience`. |
| `coverage` | `{mapped, raw, unmapped_rate, source_mix, expected_sections_present, expected_sections_absent}` (§4). |
| `category_confidence` | Distribution + ceiling provenance (§5) — **not** a lone number. |
| `category_materiality` | Aggregate of theme materialities via **max/weighted, never dilutive-average** (§6). |
| `divergence_refs` | Divergences touching this category (§7). |
| `unmapped_pool_ref` | Unmapped signals routed to this category-prior (§8). |
| `skip_reason` | Required when `status` is a `SKIPPED_*`. |
| `evidence_refs` | Theme evidence + (for skips) coverage-gap evidence. |
| `taxonomy_version`, `authority_matrix_version` | Version pins. |

Invariant: a category with `status` analyzed must have ≥1 grounded owned theme; a `SKIPPED_*` category must carry coverage-gap evidence (never silently empty).

---

## 2. QualitativeRunResult (Task 2)

The root output.

| Field | Semantics |
|---|---|
| `entity_ref`, `entity_scope` | Subject; `company` for company runs (sector/market signals stay overlay). |
| `source_set` | Sources actually ingested + per-source fingerprints/snapshots. |
| `observation_window` | Min/max `observation_time` across signals; `time_basis` mix. |
| `category_results[]` | The six `QualitativeCategoryResult`s. |
| `coverage_summary` | **Headline** (§4): analyzable %, category-status counts, per-source matrix, section presence map. |
| `confidence_summary` | Distribution + ceiling reasons (§5) — no single headline number. |
| `materiality_summary` | Top material themes/risks ranked by materiality, confidence shown alongside (§6). |
| `divergence_summary` | Counts by category/type; cross-engine candidates flagged (§7). |
| `unmapped_summary` | Taxonomy-extension/review backlog (§8). |
| `recurring_analysis` | Within-report recurring themes (derived analysis). |
| `yoy_analysis` | `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY` until ≥2 observation periods. |
| `fve_handoff` | Non-authoritative narrative-support payload (§9). |
| `run_status` | `ANALYZED_WITH_COVERAGE` / `PARTIAL_COVERAGE` / `INSUFFICIENT_COVERAGE` (coverage-framed, never a pass/fail score). |
| `versions` | taxonomy + authority_matrix + assembly_contract + scorecard_contract versions. |
| `generated_at` | Timestamp. |

**Prohibited field:** a single fused "qualitative score" presented as the headline. `run_status` is a coverage posture, not a grade.

---

## 3. Category Statuses (Task 3)

Closed, deterministic, total. Evaluated in precedence order (first match wins):

| Status | Condition |
|---|---|
| `SKIPPED_NO_ELIGIBLE_SIGNALS` | No mapped, creation-eligible signal exists for the category (only attach-only/market/overview, or none). Theme assembly could not instantiate any theme. |
| `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY` | A derived-analysis category/view (recurring-across-reports, YoY) with <2 observation periods. |
| `SKIPPED_INSUFFICIENT_COVERAGE` | Mapped coverage below floor, or a required source/section absent (e.g. no Sustainability section → ESG starved; the boilerplate-starvation case from QAE HD6). |
| `ANALYZED_WITH_WARNING` | Analyzable but caveated: high unmapped rate, only `low_salience` themes, opinion-only themes, a missing *expected* (not required) source, or an active high-materiality divergence. |
| `ANALYZED` | Mapped coverage ≥ floor, ≥1 full-salience grounded theme, low unmapped rate, no blocking caveat. |

Rules:
- **`SKIPPED_*` is not failure** and not "nothing found"; it means *not analyzable*. Each carries `skip_reason` + coverage-gap evidence.
- **"Analyzed, none found"** (a category genuinely lacking themes after analysis) is `ANALYZED`/`ANALYZED_WITH_WARNING` with zero/low themes — **distinct** from `SKIPPED_INSUFFICIENT_COVERAGE`. This distinction is the contract's core anti-illusion rule.

---

## 4. Run-Level Coverage Reporting (Task 4) — the Headline

Reported **first**, before confidence or materiality:

- **Analyzable coverage** = categories `ANALYZED` or `ANALYZED_WITH_WARNING` ÷ total categories, with the raw counts shown (e.g. "4/6 analyzable, 2 skipped").
- **Category-status breakdown** — counts per status, with skip reasons.
- **Per-source coverage matrix** — which sources contributed to which categories, and which expected sources were **absent** (multi-source HR-H: availability skew). Absence is reported, never averaged into a health number.
- **Section presence map** (annual-report source) — which of the 12 canonical sections were present/absent.
- **Mapped vs raw coverage + unmapped rate** per category and run-wide.

Governance rule: coverage must make it impossible to read a sparsely-covered run as a healthy one. A run that is mostly `SKIPPED` yields `run_status = INSUFFICIENT_COVERAGE`, regardless of how confident the few analyzed themes are.

---

## 5. Confidence Reporting (Task 5)

- Reported as a **distribution**, not a lone number (reuse the platform's confidence buckets: 0.0 / 0.1–0.5 / 0.5–0.7 / 0.7–0.9 / 0.9+).
- Each category and the run carry the distribution **plus ceiling provenance** — *why* confidence is capped (opinion-only theme, keyword-tier mapping, review-routed signals, single-origin).
- A single "overall confidence 0.55" headline is **prohibited** (the FVE smoke-audit opacity). Confidence answers *how much to trust what was analyzed*, scoped to the analyzed set — never to the skipped set.
- Confidence is reported **independently of coverage and materiality**.

---

## 6. Materiality Reporting (Task 6)

- The run surfaces **top material themes/risks ranked by materiality**, with **confidence shown in a separate column, never blended.**
- A **high-materiality, low/medium-confidence** risk (e.g. an SECP notice or an analyst-raised risk management didn't disclose) must be **prominent**, not buried by its confidence (the platform's "confidence cannot suppress materiality" rule).
- Category materiality = max/weighted of owned-theme materialities — **never a dilutive average** that lets one critical risk vanish among minor themes.
- Contested themes (active divergence) carry elevated materiality (a disagreement is important to show).

---

## 7. Divergence Reporting (Task 7)

- All `Divergence` records (narrative-vs-narrative, QAE-owned) are surfaced with **both sides + their `authority_class`**, **authority-weighted, never auto-resolved, never equal-weighted** (multi-source HR-F).
- Run-level summary: counts **by category** and **by type** (management-vs-analyst, management-vs-market sentiment, company-vs-sector).
- **Cross-engine divergences** (narrative-vs-numbers) are **not resolved here** — they are flagged into the FVE handoff (§9). QAE characterizes; it does not adjudicate numbers.
- Divergences are material by default and appear in the materiality view.

---

## 8. Unmapped-Theme Reporting (Task 8)

- Unmapped signals never became themes (assembly §11); "unmapped-theme reporting" = surfacing the **unmapped signal pool** as a **governed taxonomy-extension / review backlog.**
- Reported per category-prior: count, `unmapped_rate`, sample claims, suggested-but-unmatched terms.
- Counts toward **raw coverage but not mapped coverage, salience, or confidence.**
- A high unmapped rate is both a **coverage-quality** signal (drives `ANALYZED_WITH_WARNING`/`SKIPPED`) and a **taxonomy-health** signal (the vocabulary needs governed extension). Visibility is mandatory — the inverse of force-fitting.

---

## 9. QAE → FVE Handoff Contract (Task 9)

QAE exports a **non-authoritative narrative-support payload**; FVE consumes it as plausibility context, never as fact or validated numbers (multi-source §6, signal contract invariant 3).

Payload per exported theme:
| Field | Purpose |
|---|---|
| `theme_ref`, `category`, `horizon` | What and when (forward themes most relevant to FVE). |
| `materiality`, `confidence` (separate) | Importance and trust, unblended. |
| `authority_class` mix + `claim_type` | So FVE weights management guidance vs analyst expectation vs market sentiment correctly. |
| `evidence_refs` + per-source provenance | Auditability. |
| `narrative_only = true` | **Hard tag.** FVE may not treat this as a number. |
| `references_quantity` flag | If a theme references a figure (e.g. guidance "12m tons"), it is flagged for FVE to route the **number** through its integrity gate — the narrative claim itself is never a validated value. |
| `coverage_caveat` | If the source category was `SKIPPED`/warned, FVE is told a "no-risk" silence may be a **coverage gap**, not absence of risk (HR). |
| `divergence_refs` | Narrative-vs-numbers candidates for FVE to evaluate against gate-admitted history. |
| `entity_ref`, version pins, fingerprints | Binding + reproducibility. |

Reverse rule: FVE may emit `Divergence` records back; neither engine resolves the other's domain. The boundary is the frozen split — **numbers to FVE under the gate, narrative to QAE** — applied at the handoff exactly as at ingestion.

---

## 10. Freeze Criteria (Task 10)

Mirrors the proven Forecast Validation freeze discipline, framed for a **coverage-first qualitative-understanding product**:

| Criterion | Required result |
|---|---|
| End-to-end real-bundle run | QAE produces a `QualitativeRunResult` on the real Lucky bundle (not fixtures only). |
| Coverage-first headline | `coverage_summary` precedes and frames the run; **no fused headline score exists.** |
| Status determinism | 100% deterministic category status assignment; every `SKIPPED_*` carries reason + evidence. |
| Anti-illusion separation | "analyzed, none found" vs "skipped, couldn't see" are distinct in output. |
| Grounding | 0 ungrounded themes; 0 force-fit unmapped signals. |
| Three-axis separation | coverage, confidence (distribution), materiality reported independently; no blending. |
| Divergence honesty | divergences surfaced, authority-weighted, never auto-resolved. |
| Handoff safety | FVE payload tagged `narrative_only`; quantified claims flagged for the gate, not exported as values. |
| Version pinning | taxonomy + authority_matrix + assembly + scorecard versions + source fingerprints on every run. |
| Per-source coverage honesty | source absence reported, never averaged away. |
| Second-issuer pass | Millat run measured (coverage + unmapped rate) — a freeze prerequisite, not a nicety. |
| Truth-set validation | analyst-confirmed truth set for a theme/divergence sample (the platform-wide open assurance gap) — required before any accuracy claim. |
| Honest product framing | freeze as **coverage-first qualitative understanding** (READY_WITH_LIMITATIONS-style), not "complete qualitative analysis." |
| Temporal scope | recurring (within-report) runs; YoY `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY` until multi-report bundles exist. |

---

## 11. Hidden Risks (Task 11)

- **HR-1 — Coverage illusion / fused-score regression (the dominant risk).** A flattering mean hides that most categories were skipped (the literal FVE 70/warning failure). *Mitigation:* coverage headline; no single score; `INSUFFICIENT_COVERAGE` run status when mostly skipped.
- **HR-2 — Skipped-as-clean misread.** A run dominated by `SKIPPED` read as "no issues." *Mitigation:* prominent skip reasons; "analyzed-none-found" vs "skipped" distinction (§3).
- **HR-3 — Coverage gap mistaken for absence of issue.** "No governance theme" read as "no governance risk" when the boilerplate filter starved the category (HD6). *Mitigation:* `coverage_caveat`; distinguish analyzed-empty from skipped-blind; propagate caveat into the FVE handoff.
- **HR-4 — Confidence opacity.** A lone "0.55" hides the distribution. *Mitigation:* distribution + ceiling provenance (§5).
- **HR-5 — Materiality buried by confidence.** A low-confidence material risk not surfaced. *Mitigation:* independent materiality ranking; confidence shown beside, not multiplied in (§6).
- **HR-6 — Handoff misuse.** FVE treats QAE narrative as fact or a number. *Mitigation:* `narrative_only` tag; `references_quantity` routes numbers to the gate (§9).
- **HR-7 — Cross-company comparability illusion.** Source availability differs by company; coverage varies by data, not quality. *Mitigation:* per-source coverage matrix + comparability caveat (§4).
- **HR-8 — Version skew.** Mixing taxonomy/authority-matrix versions across a run yields incoherent aggregation. *Mitigation:* single-version runs (or migration map); version pins (§2).
- **HR-9 — Divergence overload.** Every minor disagreement surfaced as noise. *Mitigation:* authority-weighted, materiality-ranked, thresholded (§7).
- **HR-10 — Stale/superseded themes shown as current.** *Mitigation:* surface `observation_window` + supersession; horizon labeling.
- **HR-11 — No truth set.** Scorecard correctness (status, materiality, divergence) unverified. *Mitigation:* deterministic + audited; analyst truth-set as a pre-freeze gate (HR carry-over, platform-wide).
- **HR-12 — Recurring/YoY false signals from coverage gaps.** A theme "recurs" or "changes" only because a section was missed (assembly FM3 carry-over). *Mitigation:* coverage-parity gating; `SKIPPED_INSUFFICIENT_TEMPORAL_HISTORY`; recurring flagged within-report only.

---

## 12. One-Paragraph Verdict

The Category Scorecard and Run Result are where the qualitative platform either tells the truth or quietly lies, and the contract's overriding job is to make the truth structural: coverage is the headline, a fused "qualitative score" is prohibited, and "analyzed-none-found" can never be confused with "skipped-couldn't-see." Each category result reports its status deterministically with evidenced skips, its coverage as mapped-vs-raw and per-source, its confidence as a distribution with ceiling reasons, and its materiality as a non-dilutive roll-up where a high-materiality, low-confidence risk stays prominent — three axes never blended. Divergences are surfaced authority-weighted and never auto-resolved, unmapped signals are surfaced as a governed extension backlog rather than force-fit, and the FVE handoff exports themes strictly as `narrative_only` plausibility support with any referenced number routed to the integrity gate, preserving the platform's clean numbers-to-FVE / narrative-to-QAE split. Freeze it only after a real-bundle run, a second-issuer pass, and a truth-set validation — framed honestly as coverage-first qualitative understanding — and the engine's outputs inherit the one property the Forecast Validation freeze review proved most fragile and most valuable: a scorecard that cannot make sparse coverage look like a healthy company.
