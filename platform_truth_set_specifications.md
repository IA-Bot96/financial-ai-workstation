# Platform Truth-Set Specifications

**Status:** Truth-set specifications for substantive-correctness validation. No code, no implementation. Source: `platform_correctness_validation_architecture.md`.
**Date:** 2026-06-03
**Scope:** OCR · QAE · FVE · Query. (MSIL resolution truth-set = MB-1 / `entity_resolution_signoff_checklist` — already specified; foundational and referenced here.)

---

## 0. Common Framework (applies to all four)

- **External & blind.** Analysts record ground truth **from the source, before/independently of** seeing system output. Never validate against system output (anti-closed-loop).
- **Layered.** OCR (extraction) and MSIL (resolution) are **foundational** — QAE/FVE/Query correctness is bounded by them, so errors are **attributed to the originating layer**, never blamed on the consumer.
- **Census for S1 / small populations; adversarial-stratified sampling otherwise.** Over-sample the *known-weak* areas where errors concentrate.
- **Severity-scaled, asymmetric tolerance** — the same DNA in every engine: **a confidently-asserted wrong fact (S1, near-zero tolerance) is far worse than an honest withholding (tolerable).**
- **Versioned + fingerprint-pinned + signed.** Each truth set pins bundle fingerprint + engine version + analyst sign-off; reused as a **CI regression gate**.
- **Multi-issuer.** Built on Lucky + Millat, with a path to a non-manufacturer.

---

## 1. OCR Truth Set — Extraction Correctness (foundational)

*Does the extracted value/label/scale match the source PDF?* All downstream correctness rests here.

**Sample selection**
- **Census:** the baseline-eligible **core metrics** (revenue, gross/operating profit, PAT, total assets, total equity, cash, operating cash flow, EPS, debt) across **all value-years** — these feed FVE.
- **Adversarial over-sample:** scale-flagged values (the dominant failure — e.g. the revenue 41,871→62.9bn→95m series), review-gated values, unresolved-conflict groups, note-vs-statement selections, missing-year/rejected tables.
- **Stratified sample:** the broader consolidated values by sheet/table_type.

**Review workflow**
- Analyst opens the **source PDF at the cited page**, reads the actual line item, records the **correct value, unit/scale, label, page** — *then* compares to the consolidated/extracted value (blind-first).
- Disposition per item: `confirmed` / `corrected (+value)`. **Scale errors flagged specifically** (thousands/millions/full-rupee).

**Analyst responsibilities**
- Read the **source PDF, not the workbook**; financially literate; adjudicate scale ambiguity; record page-anchored truth.

**Pass criteria**
- **S1 (baseline-eligible core metrics, esp. scale):** near-zero error.
- **S2 (material non-core values):** low.
- **S3 (non-load-bearing):** moderate, reported.
- *Asymmetry:* a **wrong value/scale (false assertion) is S1**; a **missing extraction (withheld) is tolerable**.

**Freeze criteria**
- S1 census complete; scale-error rate within the near-zero band for baseline-eligible metrics; signed + fingerprint-pinned.

**Audit output**
- `ocr_extraction_correctness_audit` — error rate per severity (CI); scale/value/label error catalogue; per-metric per-year disposition; analyst sign-off.

---

## 2. QAE Truth Set — Classification & Theme Correctness

*Is content mapped to the right category/theme, and is a surfaced divergence genuine?*

**Sample selection**
- **Adversarial over-sample (where errors concentrate):** keyword-tier classifications (~80–84% of all mappings), the **section-theme conflict cases** (84 on Lucky), single-signal/low-salience themes, governance/ESG (boilerplate-starvation), and **every surfaced divergence** (validate genuineness).
- **Census:** high-materiality themes (since materiality drives surfacing).
- **Stratified sample:** across the 24 themes / 6 categories.

**Review workflow**
- Analyst reads the **source narrative section** (cited page), independently records the **correct category/theme per the frozen taxonomy**, then compares to QAE's mapping (blind-first).
- For each theme: *is this a correct characterization?* For each divergence: *is this a genuine contradiction?* For materiality: *is the ranking defensible?* For skips: *was the category correctly skipped (coverage-honest), not a missed theme?*

**Analyst responsibilities**
- Know the frozen taxonomy; read report sections; judge classification, theme characterization, divergence genuineness, materiality defensibility; sector-aware.

**Pass criteria**
- **S1 — divergence false-positive rate near-zero** (a fabricated contradiction surfaced as real is dangerous).
- **S2 — mis-classification of a *material* theme:** low.
- **S3 — low-salience/minor mis-mapping:** moderate, reported.
- *Asymmetry:* an **asserted wrong theme/divergence is S1–S2**; a **skipped/missed category (withheld) is tolerable** (coverage-honest).

**Freeze criteria**
- Classification error rate within band on the adversarial+stratified sample; **divergence false-positive near-zero**; coverage-honesty confirmed; signed + pinned.

**Audit output**
- `qae_classification_correctness_audit` — classification error rate per severity; mis-classification catalogue (incl. conflict cases); divergence-genuineness verdicts; materiality-defensibility sample; sign-off.

---

## 3. FVE Truth Set — Validation Correctness

*Is the gate verdict and plausibility assessment right? ("validated ≠ correct.")*

**Sample selection**
- **Census:** every **baseline-eligible verdict** (clean / clean-with-warning / baseline_not_validatable / missing) for the core metrics — *both directions*: is a "clean" baseline truly clean, and is a "blocked" series truly uncleanable (or wrongly blocked)?
- **Census:** NumericEvidence **admission decisions** (confirm the 119 reference-only were correctly excluded; supporting/event role assignments correct).
- **Sample:** divergence handling; (when forecast rules exist) forecast-vs-baseline plausibility assessments.

**Review workflow**
- Analyst independently judges, **from the source financials**, whether each verdict is correct — checking **both** false-positive (admitted-but-bad) **and** false-negative (blocked-but-good) — then compares to the FVE/HSIG verdict.
- Validate role assignments (baseline/supporting/event/forecast-context/non-authoritative). For plausibility: *does the analyst agree the forecast is plausible/implausible?*

**Analyst responsibilities**
- Financial analyst; judge baseline cleanliness from source; judge verdict correctness in both directions; judge admission-role correctness; financial-forecasting judgment for plausibility.

**Pass criteria**
- **S1 — a wrongly-*admitted* bad baseline (false positive) near-zero** (a corrupt number entering forecast math — the dangerous direction).
- **Wrongly-*blocked* good baselines (false negative):** more tolerable (default-deny / err-toward-silence) but **tracked** (over-blocking erodes usefulness).
- **Admission-role correctness:** high; **no reference-only admitted as baseline**.
- *Asymmetry:* admitting-bad (assertion) is S1; blocking-good (withholding) is tolerable.

**Freeze criteria**
- S1 false-positive (bad baseline admitted) near-zero on the census; admission decisions correct; signed + pinned.

**Audit output**
- `fve_validation_correctness_audit` — verdict correctness **by direction** (false-positive vs false-negative); admission-role correctness; plausibility-agreement (when applicable); sign-off.

---

## 4. Query Truth Set — Answer Correctness (composite)

*Does the cited answer correctly answer the question?* Decomposed into **Query-assembly correctness** (Query owns) and **upstream-evidence correctness** (OCR/MSIL/QAE/FVE own).

**Sample selection**
- **Golden Q&A set across all 8 intents**, expanded adversarially: **messy/natural phrasing variants** (intent robustness), multi-claim answers, **divergence-bearing questions**, **metric questions** (verify FVE integrity-status displayed), and **ambiguous/unsupported** queries (verify off-ramps).
- Questions whose correct answer the analyst can establish from the source.

**Review workflow**
- Analyst **formulates the correct answer from the source evidence independently**, then compares to Query's answer.
- For each error, **attribute the layer** (PR-5): was **Query's assembly** wrong, or was the **underlying evidence** wrong (inherited from OCR/MSIL/QAE/FVE)?
- Verify per claim: **cited**; **citation points to the right source** (does it actually support the claim?); **authority displayed correctly**; **divergence surfaced where present**; **metric carries integrity status**; honest **insufficiency/clarification** where evidence is absent.

**Analyst responsibilities**
- Formulate correct answers from source; judge correctness + completeness; **verify citation targets**; **attribute errors by layer**; judge intent classification on messy phrasing.

**Pass criteria**
- **S1 — a confidently-wrong cited answer (false assertion) near-zero**; **citation-target error near-zero** (a citation pointing to the wrong source is S1).
- **Query-assembly errors** held to a **tighter band** than inherited upstream errors (attribute, don't blame the consumer).
- **S2 — materially incomplete answers:** low. **Intent classification on messy queries:** within band. **Off-ramps** fire correctly.
- *Asymmetry:* a **wrong cited answer (assertion) is S1**; an **insufficient-evidence/clarification (withholding) is tolerable**.

**Freeze criteria**
- S1 (wrong-cited-answer + wrong-citation-target) near-zero on the golden set; intent robustness validated on messy phrasing; layer attribution recorded; signed + pinned.

**Audit output**
- `query_answer_correctness_audit` — answer correctness per severity; **error attribution by layer** (Query-assembly vs upstream); citation-target correctness; intent-robustness; off-ramp correctness; sign-off.

---

## 5. Cross-Engine Freeze-Tier Mapping

| Truth set | S1 freeze gate (Tier-1) | Tier-2 certification |
|---|---|---|
| MSIL resolution (MB-1) | Mis-resolution 0% (census) | — (keystone, S1 only) |
| OCR extraction | Baseline-metric scale/value error near-zero | S2/S3 value accuracy per issuer |
| QAE classification | Divergence false-positive near-zero | Classification accuracy band per issuer |
| FVE validation | Bad-baseline admission near-zero | Plausibility agreement (when rules exist) |
| Query answer | Wrong-cited-answer + wrong-citation-target near-zero | Completeness + intent robustness per issuer |

**S1 truth sets are freeze-gating (Tier-1); S2/S3 are progressive post-freeze certification (Tier-2/3).** All redesign nothing — corrections are data fixes / version bumps.

---

## 6. One-Paragraph Verdict

These four truth-set specifications operationalize the correctness program engine by engine, each built the same disciplined way: analysts establish ground truth from the **source, blind to system output**; sampling is **census for the critical few and adversarial for the known-weak many** (scale-corrupt values, keyword-tier classifications, both-direction baseline verdicts, messy real queries); and acceptance is **severity-scaled and asymmetric** — across all four, a confidently-asserted wrong fact (a wrong value, a fabricated divergence, an admitted-bad baseline, a wrong cited answer) is S1 with near-zero tolerance, while an honest withholding (a missed extraction, a skipped category, an over-blocked baseline, an insufficient-evidence response) is tolerable. OCR's extraction truth set is foundational and FVE/QAE/Query errors are attributed to their true layer rather than blamed on the consumer; Query's answer correctness is explicitly split into what Query assembled versus what it inherited. Every truth set is versioned, fingerprint-pinned, signed, and re-runnable as the regression eval the platform never had — and the S1 tier (led by the already-in-motion MB-1) is the freeze gate that lifts the "correctness not certified" caveat first where it matters most, while S2–S3 certify progressively per issuer. They validate everything substantive and redesign nothing — the final, measurable step that turns an honestly-scoped analyst-review-grade platform into an accuracy-certified one.
