# MSIL → FVE Integration Review (Phase 8C)

**Status:** Additive integration contract, pre-implementation. No code, no implementation detail. Ownership, authority, evidence flow, divergence, confidence, validation governance only.
**Date:** 2026-06-02
**Constraint honored:** no redesign of HSIG, NAG, NumericEvidence, or existing FVE rules. Goal: define how MSIL evidence **influences** FVE outcomes **without weakening any frozen integrity guarantee.**
**Context:** Query and QAE integrations complete; FVE is the **last** engine (Query → QAE → **FVE**). Phase 11 (NAG / NumericEvidence / Numeric Admission Policy) implemented; HSIG frozen.

---

## 0. The Audit Proves Default-Deny Works

On the real Lucky bundle: 363 MSIL signals → **244 narrative ignored by FVE** (they route to QAE), **119 numeric_claims processed**, **all 119 reference-only annual-report numerics → role `non_authoritative` → excluded**, **0 baseline admissions, 0 HSIG delegations, 0 external/analyst baselines.** This is the **correct and safe** state: the gate refuses every number it cannot trust, and the content-class split holds (narrative to QAE, numbers to FVE-under-NAG). The integration's foundation — *when in doubt, exclude* — is proven before any influence path is opened.

**A clarifying architectural fact the audit reveals:** FVE has **two numeric entry points**, and the baseline one is untouched:
- **Baseline path (frozen):** OCR-consolidated authoritative values → **HSIG** (the existing FVE input, unchanged). MSIL does **not** carry these — its `annual_report` adapter emits only reference-only narrative numerics.
- **MSIL path (new, via NAG):** payouts, PSX, SECP, analyst, and annual-report reference-only numerics → **NAG** → roles. On current data, **all are non-baseline** (hence 0 delegations). Baseline admission via NAG would occur only if MSIL ever carried OCR-consolidated values.

---

## 1. FVE's Role in the Integrated Platform (Task 1)

FVE is now the platform's **sole numeric-validation and forecast authority** — the only engine that decides whether a number is trustworthy enough to forecast on, and the only one that produces forecast conclusions. With MSIL owning evidence, Query retrieving it, and QAE assembling narrative, FVE's distinct role sharpens:
- It **consumes** MSIL numbers as *candidates* via NAG; it **decides** their fate.
- Its **baseline authority (HSIG) is untouched** — multi-source numbers never become baseline without it.
- It is correctly the **most conservative consumer** (integrated last, highest stakes), and its default posture is **exclude unless authorized** — exactly what the audit shows.

FVE does not own entity identity, authority, provenance, corroboration, or divergence-detection (all MSIL's). It owns **numeric validation, baseline admission, and forecast plausibility** — and nothing else.

---

## 2. How NumericEvidence Enters FVE, by Role (Task 2)

| Role | Admissible? | Validation influence | Confidence influence | Status influence | Reporting influence |
|---|---|---|---|---|---|
| **baseline** | Yes — **only audited + HSIG-passed** | Drives the calculation | Sets baseline confidence | Can pass/warn/fail/skip | Primary |
| **supporting** | Yes (non-baseline) | **None direct** — never a calc input | May raise (corroborate) / lower (contradict), bounded, capped | May raise a **warning**; never fails the calc alone | Surfaced as supporting evidence/corroboration |
| **event_fact** | Yes (payout/results events) | Context/anchor, not a calc input | Mild (corroboration) | May inform warnings (e.g. dividend inconsistent with cash) | Timeline/event context |
| **forecast_context** | Yes (analyst/guidance) | **Never validates history** — plausibility only | Comparison benchmark, non-authoritative | May warn (forecast far from consensus) | Forecast-context, labeled opinion/forward |
| **non_authoritative** | **No — excluded** (the 119) | None | None | None | Logged as excluded (audit), not surfaced as evidence |

The cardinal rule: **only `baseline` reaches the validation calculation, and `baseline` exists only via HSIG.** Every other role modulates confidence/warnings/reporting but **never the baseline value**.

---

## 3. NAG / HSIG / Revenue / EPS / Future Interaction (Task 3)

```
MSIL numeric_claim ─▶ NAG (role routing by Numeric Admission Policy)
   ├─ OCR-consolidated authoritative value (if ever present) ─▶ HSIG ─▶ baseline
   ├─ supporting / event_fact ─▶ NumericEvidence (non-baseline; confidence/warning only)
   ├─ forecast_context ─▶ NumericEvidence (plausibility only)
   └─ reference-only / non_authoritative ─▶ excluded
OCR consolidation result ─▶ HSIG (existing frozen path) ─▶ baseline  [unchanged]
```
- **NAG** is the front door for MSIL numbers; it never validates — it routes and tags.
- **HSIG** is unchanged, the **sole baseline authority**, whether fed by the existing OCR path or a future NAG delegation. Its verdicts (clean / clean_with_warning / baseline_not_validatable / missing) are untouched.
- **Revenue validation** consumes the HSIG baseline (unchanged); may consume a supporting PSX revenue disclosure as **corroboration** → adjusts confidence / warns / surfaces divergence — **never replaces** the baseline.
- **EPS validation** consumes the HSIG EPS baseline (unchanged); payout/dividend = ratio context; an analyst EPS estimate = forecast-context only.
- **Future validation categories** (plausibility) consume baseline (HSIG) + forecast_context (analyst/guidance) as **non-authoritative benchmarks**.

---

## 4. Divergence Handling (Task 4)

FVE consumes MSIL-detected **numeric** divergences (precise same-fact only — see §9 risk), surfaces them authority-weighted, and **never auto-resolves**. Effect by kind:

| Divergence kind | Affects validation? | Affects confidence? | Affects status? | Merely reported? |
|---|---|---|---|---|
| **Baseline divergence** (two baseline-candidate values disagree) | Yes — forces review / caps toward not-validatable | Lowers | **Yes** — blocks autonomous use pending resolution | + surfaced |
| **Supporting-evidence divergence** (supporting ≠ baseline) | No (baseline value unchanged) | **Lowers** | Warning, not fail | + surfaced |
| **Analyst divergence** (estimate ≠ baseline/forecast) | **No** (never touches history) | No (history); plausibility only | Plausibility warning only | + surfaced |
| **Regulatory divergence** (SECP contradicts an issuer number, e.g. restatement) | **Triggers re-validation / can invalidate a baseline** (highest authority for compliance) | Lowers | **Yes** — re-validate / flag, never silently adopt | + surfaced |

Universal rule: FVE **adjusts confidence, raises warnings, sets status (review/blocked), reports — but never picks a winner**, exactly as HSIG already exposes conflicts without hiding them. Regulatory divergence is the only kind that can *trigger* a baseline re-validation, and even then FVE flags/blocks rather than adopting the regulator's number as the baseline value.

---

## 5. Supporting-Evidence Usage (Task 5) — payouts / PSX / SECP

Without becoming baseline truth:
- **Validation confidence:** corroboration of the baseline raises confidence (bounded, capped by authority); contradiction lowers it.
- **Warning generation:** a supporting number materially diverging from the baseline raises a warning (e.g. a payout dividend implying a payout ratio inconsistent with reported earnings).
- **Plausibility:** supporting events (capex/expansion announcement) inform forecast-plausibility context.
- **Scorecard reporting:** surfaced as supporting evidence + corroboration/divergence, **clearly labeled non-baseline**.
- **Hard rule:** supporting evidence **never enters the baseline calc as an input and never overrides HSIG** — it only modulates confidence, warnings, and reporting.

---

## 6. Forecast-Context Usage (Task 6) — analyst / guidance / outlook

Without becoming validation truth:
- **Plausibility:** a submitted forecast is compared against analyst consensus + management guidance as **benchmarks**; large deviation → plausibility warning.
- **Warning generation:** forecast far above historical CAGR **and** above consensus → stronger warning; forecast aligned with guidance → context note.
- **Confidence:** forecast-context is non-authoritative — it may inform a *plausibility* confidence but **never a historical-validation confidence**, and never raises baseline confidence.
- **Hard rule:** forecast-context **never validates history, never becomes baseline**, and is always labeled opinion/forward. (Analyst sources are post-MVP in MSIL regardless.)

---

## 7. Authority Usage (Task 7)

- **Authority ceilings:** a number's MSIL authority caps its influence — analyst (`independent_opinion`) ceilinged to forecast-context; issuer-unaudited ceilinged to supporting; **only audited (+HSIG) reaches baseline**; regulatory highest for compliance/triggers.
- **Authority conflicts:** handled as divergence (§4), authority-weighted, never auto-resolved.
- **Authority disagreement:** surface both sides + authority class; higher authority frames the warning/status (and, for regulatory, triggers re-validation) but FVE **does not silently adopt the higher-authority number as baseline** — HSIG still governs the baseline value.
- **Authority display:** every NumericEvidence carries its MSIL `authority_class`; FVE reports it; **never reassigns it.**

---

## 8. Prohibited Behaviors (Task 8)

- **Analyst evidence becoming baseline** (never) or influencing historical validation.
- **Supporting evidence overriding HSIG** or entering the baseline calc as an input.
- **Divergence auto-resolution** — FVE surfaces/flags/blocks, never picks a winner.
- **Authority reassignment** — apply MSIL authority, never redefine.
- **Numeric authority laundering** — presenting a reference-only or external number as validated/baseline.
- **Treating reference-only numerics as authoritative** (the 119 must stay excluded).
- **HSIG bypass** — any path to baseline that skips HSIG.
- **FVE creating/resolving entities** — must consume MSIL resolution; quarantined/unresolved-entity numbers never admitted.
- **Consuming narrative as numeric fact** (content-class lane; narrative is QAE's).
- **Double-counting corroborating numbers from echoed sources** (MSIL lineage owns this).
- **Forecast-context inflating historical-validation confidence.**
- **Adopting a regulator's number as baseline** (regulatory triggers re-validation; it does not supply the baseline value).

---

## 9. Hidden Risks (Task 9)

- **Source disagreement** (payout 15 vs 10) → divergence, never auto-pick.
- **Stale evidence** (preliminary superseded by audited) → MSIL supersession; superseded numbers never baseline or current-supporting.
- **Duplicate evidence** (same number, many sources) → dedup on a **precise same-fact key**; corroboration counts independent origins only.
- **Payout leakage** (payout amount treated as a statement line) → payout is `event_fact`, never baseline.
- **Optimism bias** (issuer-unaudited rosier than audited) → supporting only; never overrides audited.
- **Divergence inflation (critical, ties to MB-4)** — the real-bundle run produced 120 false `fact_vs_fact` divergences from reference-only coarse-subject numerics; if those reach FVE, it drowns. **Only precise same-fact divergences may reach FVE; the MB-4 fix is a hard prerequisite.**
- **Confidence inflation** (supporting corroboration + forecast-context both boosting) → confidence composes **downward** under authority ceilings; forecast-context cannot lift a baseline; **never multiply across roles or engines.**
- **Cross-engine authority drift** → MSIL authority is substrate truth; FVE applies, never redefines.
- **Carried prerequisites:** MB-1 (entity sign-off) — numbers bound to the wrong entity is the worst failure.

---

## 10. Sequencing (Task 10) — by evidence ROLE, ascending in risk

**Integrate by evidence role, ascending in blast radius** — because *role*, not source or category, determines how a number can affect outcomes:
1. **`non_authoritative` exclusion** — already proven (the 119; the gate refuses safely). ✓
2. **`event_fact` + `supporting`** — influence confidence/warnings/reporting but **never the baseline calc**; lowest live-influence risk; integrate next and prove they modulate without corrupting.
3. **`forecast_context`** — plausibility-only; integrate when forecast plausibility rules exist (analyst is post-MVP).
4. **`baseline` (HSIG-delegated)** — highest risk; only if/when MSIL carries OCR-consolidated values; integrate **last**, fully gated by HSIG.

Rationale: role-ascending sequencing **isolates the baseline/HSIG integrity core until last** and lets the safe non-baseline roles prove the influence paths first — the platform's "prove on the safest path first" discipline. **Not all-at-once** (would expose the baseline path to untested multi-source numbers simultaneously). **Not by source** (a single source carries multiple roles; source doesn't bound blast radius). **Not by validation category** (Revenue/EPS doesn't isolate the integrity risk; role does).

---

## 11. Findings Classification (Task 11)

**Must Resolve Before Integration**
- **MB-4 — MSIL divergence-policy fix.** Only precise same-fact numeric divergences may reach FVE; reference-only coarse-subject noise excluded, or FVE drowns in 120 false divergences.
- **MB-1 — entity-resolution analyst sign-off** (carried) — numbers must bind to confirmed entities.
- **HSIG-bypass-impossible guarantee** — no path to baseline skips HSIG; baseline stays HSIG-only.
- **Role→influence matrix ratified** (§2) + the prohibited-behaviors guardrails (§8).
- **Baseline-entry clarification** — baseline comes via the existing OCR→HSIG path (or future HSIG-delegated); MSIL numbers never baseline without HSIG.

**Can Resolve During Integration**
- Supporting/event confidence-modulation + warning thresholds.
- Divergence presentation + status thresholds in FVE outputs.
- Per-role reporting in the FVE scorecard.
- Regulatory-divergence re-validation-trigger handling.

**Post-MVP**
- `forecast_context` + forecast plausibility rules (analyst/guidance; analyst is post-MVP in MSIL).
- `baseline` via NAG delegation if MSIL ever carries OCR-consolidated values.
- Numeric-reference → canonical-metric grounding (precise same-fact keys).
- Approved reconciliation policy letting non-OCR numbers (e.g. payout-confirmed) become baseline.

---

## 12. One-Paragraph Verdict

The MSIL → FVE integration is the highest-stakes and most conservative of the three, and the Phase 11 audit shows its foundation is already correct: on the real bundle, FVE ignored all 244 narrative signals, processed all 119 numeric claims, and **excluded every one as non-authoritative reference-only — zero baselines, zero HSIG delegations — exactly the default-deny posture the integrity guarantee requires.** The integration adds influence paths without touching the baseline core: **only audited, HSIG-passed values are baseline**; payouts and disclosures enter as `supporting`/`event_fact` that can move confidence and raise warnings but never enter the calculation or override HSIG; analyst and guidance enter as `forecast_context` that informs plausibility but never validates history; regulatory contradictions can *trigger* a re-validation but never *supply* a baseline number; and every divergence is surfaced authority-weighted and never auto-resolved. The two hard prerequisites are the MB-4 divergence-policy fix (so the 120 false reference-only divergences never reach FVE) and the MB-1 entity sign-off (so numbers bind to the right company), and the safe build order is by evidence role ascending in risk — exclusion first (done), then non-baseline supporting/event, then forecast-context, then any HSIG-delegated baseline last. Done this way, MSIL evidence enriches FVE's confidence, warnings, plausibility, and reporting while the frozen integrity promise stands exactly where it always has: **no number becomes a forecast baseline without passing HistoricalSeriesIntegrityGate — no matter how many sources now surround it.**
