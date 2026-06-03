# FVE Multi-Source Numeric Governance Review

**Status:** Architecture & governance review resolving HD-5 / MB-3. No code, no implementation design. Focus: architecture, authority, provenance, governance, integration readiness.
**Date:** 2026-06-02
**Sources:** FVE freeze review + known limitations; MSIL architecture/contracts; MSIL pre-integration + real-bundle reviews.
**The dependency:** FVE must eventually consume non-OCR numeric evidence (Company Payouts, PSX Announcements, SECP Notices, future Analyst sources) **without letting external numbers bypass integrity validation.**

---

## 0. The Governing Question

FVE today validates exactly one numeric source — OCR-consolidated annual-report values — gated by the `HistoricalSeriesIntegrityGate` (HSIG), which admits a series only if it passes scale-consistency, unresolved-conflict, source-class, and candidate-spread checks (on Lucky, only EPS survived clean-with-warning). HSIG's checks are **intrinsically OCR-consolidation-shaped**: they assume the input is a consolidation result with competing candidates, `statement_scope`, and primary-vs-note `source_class`.

Multi-source breaks that assumption. A payout record, an SECP notice, an analyst target have **no candidate-spread, no statement scope, no primary/note class** — and different authority, different time semantics, and (as the MSIL real-bundle run proved) a tendency to disagree (issuer dividend 15 vs payout 10). The governance question is therefore: **how does every external number reach forecast math only through integrity validation, when HSIG's mechanism cannot evaluate most of them?**

---

## 1. FVE Architecture in a Multi-Source World (Task 1)

FVE must evolve from "validate one consolidation result's history" to "validate a **multi-source numeric evidence set**, where every number carries authority, provenance, time, and a **role**, and where integrity is enforced for *all* sources without overloading the frozen OCR gate." The non-negotiable that carries over from the whole platform: **no unvalidated or non-authoritative number enters forecast arithmetic.** The MECHANISM that enforces this differs by source; the GUARANTEE must not.

Three structural additions are implied (governance, not implementation):
1. A **routing layer** that classifies each incoming numeric claim by source/authority/claim-type into a numeric **role**.
2. A **role-scoped admission policy** deciding what each role may do (baseline / supporting / event-fact / forecast-context / nothing).
3. Preservation of HSIG **unchanged** as the authority for OCR-historical baselines, with everything else admitted by the new policy.

---

## 2. Should HSIG Remain / Extend / Wrap / Replace? (Task 2)

**WRAP it.** HSIG remains **unchanged**; a new **Numeric Admission Gate (NAG)** wraps it.

- **Not "remain unchanged" alone** — HSIG cannot admit non-OCR numbers at all, which would force external numbers either to bypass it (the exact prohibited outcome) or be unconsumable.
- **Not "replace"** — HSIG is correct, freeze-grade, and proven for OCR consolidation series; replacing it discards validated behavior (scale-consistency, conflict exposure) that works.
- **Not "extend"** — cramming payout/SECP/analyst semantics into HSIG overloads a frozen, single-purpose gate with source logic it was never designed for, couples unrelated semantics, and destabilizes a frozen component (against the platform's additive discipline).
- **"Wrap" (recommended)** — NAG owns multi-source numeric admission: it routes by role, applies source-appropriate integrity checks, and for OCR-historical-baseline numbers **delegates to the unchanged HSIG**. HSIG stays the historical-baseline authority; NAG adds the source-policy and cross-source reconciliation HSIG never had. This preserves the freeze, isolates new risk, and is purely additive.

---

## 3. Authority Model for Numeric Evidence (Task 3)

Authority is **two-dimensional**: (a) claim-type-scoped authority class (inherited from MSIL), and (b) numeric **role**. The five source types:

| Source | Authority class | Authoritative for | Numeric role |
|---|---|---|---|
| **Audited annual-report values** (OCR-consolidated) | `audited_issuer` | Historical audited financials | **The only baseline-authoritative numbers — and only if HSIG-passed.** |
| **Issuer disclosures** (PSX announcements) | `official_issuer_unaudited` | Timely issuer-official facts (preliminary results, guidance) | Supporting / event / (guidance → forecast-context); **never standalone baseline**. |
| **Payout records** (Company Payouts) | `exchange_official` | The corporate-action fact (dividend declared/paid) | Authoritative **for the payout event**; supporting/corroborating for related ratios; **not a statement-line baseline**. |
| **Regulatory disclosures** (SECP) | `regulatory_independent` | Compliance/regulatory facts; restatement orders | Authoritative for regulatory facts; **can invalidate/trigger re-validation** of a baseline; not itself a baseline source. |
| **Analyst expectations** | `independent_opinion` | External forward opinion | **Forecast-comparison context only; never historical, never baseline, never authoritative.** |

The governing rule: **only audited annual-report values that pass HSIG are baseline-authoritative. Everything else is supporting, event-fact, forecast-context, or non-authoritative — and none of them bypass admission.**

---

## 4. How Numeric Claims Enter FVE, by Source (Task 4)

| Source | Admissible? | Supporting-only? | Baseline candidate? | Forecast candidate? | Never authoritative? |
|---|---|---|---|---|---|
| Audited annual-report **(HSIG-passed)** | Yes | also baseline | **Yes (sole)** | No (historical) | No — authoritative if clean |
| Audited annual-report **(HSIG-blocked)** | No baseline; SKIPPED | caveated supporting at most | No | No | n/a (excluded) |
| **PSX issuer disclosure** | Yes | **Yes** | Only after reconciliation→confirmed | Guidance only → forecast-context | Not standalone baseline |
| **Company payout** | Yes | corroborating | No (corporate action ≠ statement line) | No | Authoritative only for the payout fact |
| **SECP regulatory** | Yes | regulatory fact + re-validation trigger | No | No | Authoritative for compliance; can invalidate baseline |
| **Analyst expectation** | Yes (context) | comparison benchmark | **No (never)** | Forecast-context benchmark | **Yes — never authoritative, never historical** |
| **Reference-only numerics** (MSIL `numeric_claim` from narrative) | Supporting context at most | Yes | **No** | No | **Yes** — excluded from baseline/forecast/divergence-as-conflict |

Unifying rule: **every external number passes through NAG, is tagged with a role by (source, authority, claim_type), and only audited-and-HSIG-passed values reach baseline historical math.** No path makes an external number a baseline without both NAG's source policy *and* HSIG-equivalent integrity.

---

## 5. Required New Contracts (Task 5) — minimal, reuse MSIL

**Reuse, do not duplicate.** MSIL already provides `numeric_claim` (content class), the provenance union, `authority_class`, and `claim_type`. FVE should **consume MSIL's numeric_claim and provenance directly** — no new `NumericClaim` or `NumericProvenance` or `NumericAuthority` contract (those would duplicate MSIL).

Two genuinely new contracts are needed at the FVE boundary:
1. **Numeric Admission Policy** — the role/admissibility matrix mapping `(source_type, authority_class, claim_type)` → numeric role (baseline / supporting / event / forecast-context / non-authoritative) + admissibility. This is the governance core MSIL does not own (MSIL assigns authority; it does not decide FVE's numeric role). Versioned.
2. **NumericEvidence** — the FVE-internal envelope an admitted number carries into rules: its role, authority, provenance (from MSIL), integrity verdict (HSIG-passed vs source-gate-passed), reconciliation/supersession state, and divergence references. This is how a rule distinguishes "baseline-authoritative" from "supporting/forecast-context."

Everything else is reuse. This satisfies the "only if necessary" constraint.

---

## 6. Interaction Model (Task 6)

```
MSIL IntelligenceSignal (numeric_claim + authority + provenance + divergence)
        │
        ▼
Numeric Admission Gate (NAG)  ── role routing via Numeric Admission Policy
        ├── OCR-consolidated historical value ──▶ HistoricalSeriesIntegrityGate (UNCHANGED)
        │                                              └─▶ clean / clean_with_warning ▶ BASELINE
        │                                              └─▶ baseline_not_validatable / missing ▶ SKIPPED
        ├── payout / issuer / SECP number ──▶ source-appropriate integrity ▶ supporting / event / re-validation-trigger
        ├── analyst expectation ──▶ forecast-context benchmark (never baseline)
        └── reference-only numeric ──▶ supporting context at most (excluded from baseline/forecast/conflict)
        │
        ▼
NumericEvidence (role + integrity verdict + provenance + divergence refs)
        │
        ├──▶ Revenue validation: baseline = HSIG-admitted series (unchanged); payout/announcement = non-baseline corroboration that may raise/lower confidence or surface divergence — never replace the baseline.
        ├──▶ EPS validation: same; EPS baseline stays HSIG-gated; payout (dividend) gives ratio context only.
        └──▶ Forecast plausibility (future): baseline (HSIG) compared against analyst consensus + management guidance as explicitly non-authoritative forecast-context (mirrors the QAE narrative-support pattern).
```

Two hard interaction rules:
- **HSIG verdicts are untouched.** Revenue/EPS still consume only HSIG-admitted baselines; multi-source numbers enter as NumericEvidence with a non-baseline role.
- **Divergence forces review, never auto-pick.** A numeric divergence (issuer 15 vs payout 10) surfaced by MSIL caps confidence / blocks autonomous use / requires review — FVE never silently selects a winner, consistent with HSIG's "expose conflicts, don't hide."

---

## 7. Hidden Risks (Task 7)

- **Source disagreement** (issuer vs payout vs SECP on one number — the real 15-vs-10 case). *Governance:* surface as authority-weighted divergence; cap/block; never auto-resolve.
- **Duplicate numbers** (same fact from multiple sources). *Governance:* dedup by precise `(entity, canonical_metric, value_year, fact)` before any math; corroboration counts **independent origins only** — directly dependent on fixing MSIL's coarse-subject keying (the 120-divergence finding).
- **Stale disclosures** (preliminary announcement used after audited supersedes it). *Governance:* MSIL supersession — superseded numbers never baseline; audited outranks newer-unaudited for baseline.
- **Analyst targets leaking into history.** *Governance:* analyst = forecast-context **only**, hard rule, never baseline.
- **Issuer optimism** (unaudited announcement rosier than audited). *Governance:* unaudited issuer numbers are supporting/provisional; never override audited; HSIG/audited remains baseline authority.
- **Conflicting payout values** (the MSIL run surfaced this). *Governance:* payout authoritative for the payout *event*; conflicting payout records → divergence → review, never silent pick.
- **Reference-only numeric noise** (119 references → 120 false `fact_vs_fact` in the real run). *Governance:* reference-only numerics are **never** baseline/forecast candidates and are excluded from divergence-as-conflict — FVE must not inherit this noise.
- **Entity mis-resolution** feeding another company's numbers (carried from MSIL MB-1, still open). *Governance:* admission requires a confirmed-registry resolved entity; quarantined/review entities never reach baseline.

---

## 8. Sequencing (Task 8)

**Separate shared-contract work — prerequisite to BOTH MSIL Phase 8 (FVE consumption wiring) and a future FVE Phase 11 (wrapper-gate + multi-source rules).**

- Not "FVE Phase 11 first" — that would implement against undefined admission/role contracts.
- Not "MSIL Phase 8 prerequisite only" — the wrap-HSIG decision and rule consumption are FVE architecture, not MSIL's.
- The right order:
  1. **Shared-contract design** (this review → a Numeric Admission Policy + NumericEvidence contract + the wrap-HSIG decision).
  2. **MSIL divergence-policy fix (MB-4)** — so FVE never ingests reference-only numeric noise.
  3. **MSIL Phase 8** wires FVE consumption against the new contract.
  4. **FVE Phase 11** implements NAG (wrapping the unchanged HSIG) + multi-source rule consumption.

The contracts gate the wiring; the wiring gates the rules.

---

## 9. Findings Classification (Task 9)

**Must Resolve Before Integration**
- **Wrap-HSIG decision + Numeric Admission Policy + NumericEvidence contract** — the governance core; without it external numbers bypass integrity or are unconsumable (HD-5/MB-3).
- **MSIL divergence-policy fix (MB-4)** — reference-only numerics excluded from baseline/forecast candidacy and from divergence-as-conflict, or FVE inherits the 120-divergence noise.
- **The hard authority rules** — audited+HSIG-only baseline; analyst never baseline; unaudited issuer never overrides audited; superseded never baseline; conflicts → divergence/review never auto-pick.
- **Carried MB-1** — entity-resolution analyst sign-off (wrong-entity numbers are the worst failure).
- **Carried MB-3** — FVE gate extension to non-OCR provenance is *this* work; it must be designed, not assumed.

**Can Resolve During Integration**
- Per-source reconciliation tuning (provisional→confirmed announcements; payout corroboration of audited).
- Confidence composition for supporting numbers adjusting baseline confidence.
- Divergence presentation/caps in FVE outputs.
- Forecast-context plumbing groundwork for guidance/consensus benchmarks.

**Post-MVP**
- Analyst-source ingestion + forecast plausibility vs consensus (analyst is post-MVP in MSIL).
- Market/futures numeric context.
- Numeric-reference → canonical-metric grounding (precise same-fact key — deep).
- Approved reconciliation policy allowing non-OCR numbers (e.g. payout-confirmed) to *become* baseline.

---

## 10. One-Paragraph Verdict

The multi-source future does not require rebuilding FVE's integrity gate — it requires **wrapping** it. `HistoricalSeriesIntegrityGate` stays exactly as frozen, the sole authority for OCR-historical baselines, and a new **Numeric Admission Gate** governed by a **Numeric Admission Policy** routes every external number by role — admitting only audited-and-HSIG-passed values as baseline, treating payouts as authoritative-for-the-event, issuer disclosures as supporting/provisional, SECP as regulatory-fact-and-re-validation-trigger, analyst targets as forecast-context-only, and reference-only narrative numerics as never-baseline — so that **no external number ever reaches forecast arithmetic without passing integrity, and none silently overrides an audited baseline.** FVE should consume MSIL's existing `numeric_claim`, provenance, and authority rather than re-inventing them, adding only the admission-policy and NumericEvidence contracts; source disagreement, duplicates, staleness, optimism, and conflicting payouts are all handled by surfacing authority-weighted divergence and never auto-resolving, exactly as MSIL and HSIG already do for their domains. This is **shared-contract work that must precede both MSIL Phase 8's FVE wiring and a future FVE Phase 11** — and it depends on the MSIL divergence-policy fix and the still-open entity-resolution sign-off — but it is purely additive, preserves every frozen guarantee, and keeps the platform's oldest rule intact: numbers are gated before they are believed, no matter which source they come from.
