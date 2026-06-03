# MSIL Pre-Integration Review — Phases 1–7 (Substrate Build)

**Status:** Review of the MSIL substrate (P1–P7) against the architecture, contracts, and plan. No code. Focus: architecture, contracts, readiness, integration risk.
**Date:** 2026-06-02
**Evidence:** `msil_phase1–7_report.json` + the eight phase audits. All versions `1.0.0`; tests 50→60→69→86→93→101→109 passing.

---

## 0. Substrate Snapshot

| Phase | Built | Audit result | Data exercised |
|---|---|---|---|
| P1 | Entity registry + resolution | 4/4 freeze criteria; 34/34 truth cases | 20 entities (curated) |
| P2 | IntelligenceSignal + provenance + snapshot | 9/9 emittable provenance, 4/4 content classes, NONE rejected, invalid cases rejected | **4 synthetic signals** |
| P3 | Annual report adapter (source #1) | 5 signals, all provenance-backed, mapping failure reported | **4-insight fixture (`fp_lucky_2025_phase3_fixture`)** |
| P4 | Authority matrix application | 10/10 source types, 8/8 claim types, special rules enforced, invalid creation rejected | **11 synthetic signals** |
| P5 | Official triad (PSX/Payouts/SECP) | content-class split proven, AGCO quarantined, snapshot enforced, failures recorded | **5 synthetic records** |
| P6 | Timeline + supersession | 5 events, 2 supersession links, no deletion, authority rule enforced | **5 synthetic events** |
| P7 | Corroboration + divergence | 1 corroboration group (strength 0.5), 1 circularity rejection, 2 divergences surfaced | **5–6 synthetic signals** |

**Headline:** the substrate is **mechanically complete and contract-faithful across all seven phases** — deterministic, version-pinned, with the content-class split, supersession authority rule, corroboration independence, and divergence surfaced-never-resolved all working as specified. But **every phase is validated on tiny hand-crafted fixtures**, and most consequentially, **P3 never ran on the real 244-insight Lucky bundle** — it used a 4-insight fixture with a fixture fingerprint. The mechanisms are proven; their behavior on real source data and the real annual bundle is not.

---

## 1. Architecture Fidelity (Task 1) — HIGH

Every contract invariant that can be checked is honored:
- **P2** — `IntelligenceSignal` with the discriminated provenance union (9 emittable types), `NONE` forbidden, deterministic text-independent `signal_id`, version pins, and **invalid-case rejection** (none-provenance, missing-snapshot, unresolved-entity, content-class-mismatch, missing-version all rejected).
- **P3** — `Insight.takeaway → narrative_claim`; numeric mentions → **reference-only `numeric_claim` (`authoritative_numeric_values_created: false`)** — numbers correctly *not* asserted; PDF_PAGE provenance; `audited_issuer`; **mapping failure recorded, not dropped**.
- **P4** — **claim-type-scoped matrix (`global_authority_ranking_used: false`)**; special rules enforced (`news_media_corroboration_only`, `market_revealed_observation_only`, `numeric_reference_only_creation_disabled`, `unverified_origin_creation_disabled`); invalid creation-rights rejected (the `news_media`+`creation_eligible:true` case → `is_valid:false`).
- **P5** — content-class split proven on the triad (payouts→`corporate_event`+`numeric_claim`; announcements/SECP→`narrative`+`event`); **AGCO quarantined**; **a SECP record missing `snapshot_ref` failed and was recorded, not dropped** (snapshot rule enforced); `source_lineage` captured (HD-7).
- **P6** — supersession rule "same entity + compatible subject + later time + **equal-or-higher claim-scoped authority**"; no history deletion; lower-authority and incompatible-claim rejections test-covered.
- **P7** — corroboration credits **independent origins only** (annual_report + company_payouts on `dividend_declared`, independent_origin_count 2, strength 0.5) and **rejects circularity** (lineage overlap); divergence **surfaced, never resolved**, with authority-weighting recorded and `truth_resolution: not_determined_by_msil` (issuer "compliant" vs SECP "non-compliant"; payout 15 vs 10).

This is genuinely strong, disciplined contract adherence — the cleanest substrate build in the program.

---

## 2. Hidden Risks (Task 2)

- **HR-1 — The entire substrate is fixture-validated.** Per-phase signal counts are 4–11 hand-crafted records. The mechanisms are proven; real source volume, messiness, and the real annual bundle are not. This is the FVE-Phase-9 / QAE-pre-Millat pattern at the substrate layer.
- **HR-2 — P3 used a fixture, not the real bundle (the most consequential).** Fingerprint `fp_lucky_2025_phase3_fixture`, 4 insights — the real Lucky `.kb.json` has 244 (fingerprint `97c3123…`). The plan's P3 freeze criterion ("no regression to existing QAE/FVE single-source inputs") is therefore **unproven**; source #1 was never really absorbed.
- **HR-3 — P1's Must-Before-P2 items appear unaddressed.** No analyst sign-off / `[CONFIRM]`-resolution evidence surfaces in P2–P7, and no general-ambiguity-rule confirmation. The substrate was built for six phases on an **unconfirmed registry** (the closed-loop risk from the P1 review, still open).
- **HR-4 — Corroboration/divergence/supersession are each proven on a single instance.** 1 corroboration group, 1 circularity rejection, 2 divergences, 2 supersession links. The logic is correct on these; edge-case density (multi-party divergence, chained supersession, mixed time-basis) is untested.
- **HR-5 — `source_lineage` arrays contain duplicates** (e.g. `annual_report:annual-dividend-2025` ×3 in the corroboration member). Cosmetic now, but loose lineage dedup could weaken the circularity defense at news scale.

---

## 3. Contract Violations (Task 3)

No hard contract *violations* — but two **plan/criterion gaps**:
- **CV-1 — P3 real-bundle reconciliation not performed.** The plan required source #1 to absorb the real annual report with no engine regression; a fixture was used instead. Not a contract violation, but the stated P3 freeze criterion is unmet.
- **CV-2 — P1 freeze criterion #6 (analyst sign-off + `[CONFIRM]`) still unmet** and was the gate for proceeding past P1. Proceeding to P7 without it is a process gap against the truth-set spec's own criteria.
- Otherwise: numbers never asserted (✓), `NONE` forbidden (✓), quarantine-not-force (✓), divergence never resolved (✓), special rules enforced (✓), version pins everywhere (✓). Contract adherence is otherwise clean.

---

## 4. Over-Engineering (Task 4)

- **OE-1 — Full breadth built ahead of need.** P2 implemented model classes for `MarketDataProvenance`/`FuturesProvenance`/`NewsProvenance` and P4's matrix supports all 10 source types (incl. market/futures/news/analyst/sector) while only the 3 official sources are in scope. Defensible (the contracts are frozen, so modeling the full enum is cheap), but the market/futures/news authority behavior is **unexercised speculative breadth** — flag, don't fix.
- Otherwise the substrate is appropriately scoped to the triad; corroboration/divergence/supersession are built minimally as the contracts require, not over-deep. No significant over-engineering.

---

## 5. Under-Engineering (Task 5)

- **UE-1 — Real annual bundle never run (HR-2).** The single biggest gap; source #1 absorption is unproven on real data.
- **UE-2 — No real source feeds.** Adapters ran on synthetic records, not real PSX/SECP/payout data; ingestion volume and identifier messiness untested.
- **UE-3 — Registry foundation unconfirmed (HR-3).** Analyst sign-off / `[CONFIRM]` resolution still open.
- **UE-4 — Quarantine review-queue operational path** still not built (P1 review TB-6); AGCO/failed-SECP records are quarantined/recorded but the triage/re-resolution loop is absent.
- **UE-5 — Period resolution unexercised.** `subject_period` carries "FY2025" as a string, but no period-resolution validation exists.
- **UE-6 — Cross-source same-entity convergence only lightly shown** (LUCK + "Lucky Cement Limited" → `lucky_cement` across PSX/SECP fixtures) — encouraging, but not at real scale or across all id types simultaneously.

---

## 6. Is the MSIL Substrate Complete? (Task 6)

**Complete on contracts; not complete on real data.** All P1–P7 substrate components exist, are unit-validated, and adhere to the frozen contracts: registry+resolution, signal envelope, provenance+snapshots, authority matrix, annual-report adapter, official triad, timeline+supersession, corroboration+divergence. P8 (consumption contracts + real-bundle run) and P9 (Millat + freeze) remain. The substrate's *mechanisms* are done; what is missing is proof they work on the **real annual bundle and real source feeds** — which is precisely P8's purpose.

---

## 7. Integration Readiness (Task 7)

For all three engines, **MSIL's producing side is contract-ready and version-pinned; the consuming side is unbuilt** (every phase reports `engine_integrations_implemented: false`), and integration *output* is untrustworthy until the real bundle runs (HR-2).

- **FVE — ready to wire, blocked on HD-5.** MSIL produces reference-only `numeric_claim`s (payout amounts) + the `CorporateEvent` timeline + `fact_vs_fact` numeric divergences (the payout 15-vs-10 case is exactly FVE's domain). But **FVE's integrity gate must be extended to non-OCR provenance** before consuming, or external numbers bypass the gate or are unconsumable. Medium readiness.
- **QAE — ready to wire (additive).** MSIL produces `narrative_claim`s + corroboration + divergence + (will carry) coverage caveats; QAE consumption is additive over its frozen single-source path. Readiness good on MSIL side; QAE-side wiring needed.
- **Query Engine — ready to wire.** MSIL provides evidence store + timeline + provenance + entity index; Query-side consumption unbuilt.

**Common risk:** because P3 never ran the real bundle, the volume and shape the engines will actually consume from MSIL is unproven; wiring can proceed, but trusting integrated output cannot until P8's real run.

---

## 8. Findings Classification (Task 8)

**Must Resolve Before P8**
- **MB-1 — Close the carried-over P1 Musts:** analyst sign-off + `[CONFIRM]` resolution on the registry, and confirm a **general** ambiguity rule (not per-token). Six phases built on an unconfirmed identity foundation; integration must not proceed on it (HR-3/CV-2).
- **MB-2 — Run the annual-report adapter on the REAL Lucky `.kb.json`** (244 insights, fingerprint `97c3123…`) and demonstrate the no-regression reconciliation P3 required (HR-2/CV-1/UE-1). P8's real-bundle smoke run depends on it.
- **MB-3 — Settle HD-5** (FVE gate extension to non-OCR provenance) before wiring FVE consumption.

**Can Resolve During P8**
- Cross-source same-entity convergence at real scale (UE-6).
- Quarantine review-queue operational path (UE-4).
- `source_lineage` dedup cleanup (HR-5).
- Real-feed messiness handling as adapters meet real PSX/SECP data.
- Per-source coverage reporting in the consumption feeds.

**Post-MVP**
- Market/Futures/News/Analyst/Sector adapters (deferred by design).
- News-circularity validation at scale (mechanism built + tested on 1 case).
- Period-resolution depth (UE-5); person/board and security depth.
- Non-manufacturer registry expansion.

---

## 9. Determinations (Task 9)

**Is MSIL ready for integration? — READY TO WIRE, conditioned on MB-1/MB-2/MB-3.** The producing-side contracts are stable, additive, and version-pinned, so integration scaffolding can begin. But integration *output* should not be trusted until the registry is analyst-confirmed, the real annual bundle has actually flowed through source #1, and the FVE gate extension is settled. This is "ready to connect," not "ready to rely on."

**Is MSIL on track for freeze? — YES, on track.** The substrate is mechanically complete and the cleanest contract-adherence in the program; the remaining work (P8 consumption + real-bundle run, P9 Millat + freeze) is well-defined, and the gating items are known and bounded. Freeze remains achievable provided the substrate proves itself on the **real** annual bundle and real feeds — not just fixtures — and the registry-confirmation gate closes.

---

## 10. One-Paragraph Verdict

MSIL Phases 1–7 are the most contract-faithful build in this platform: the entity registry resolves and quarantines correctly, the signal envelope forbids un-provenanced and un-versioned signals, numbers are carried as reference-only candidates and never asserted, the authority matrix is claim-type-scoped with news/market special rules enforced, the official triad routes cleanly by content class with AGCO quarantined and a snapshot-less SECP record correctly rejected, the timeline supersedes only on later-time-plus-higher-authority, and corroboration credits independent origins while divergence is surfaced and never resolved. Every mechanism the contracts demand is present and disciplined. The honest caveat is that all of it is proven on a handful of synthetic fixtures, that source #1 (the annual report) was absorbed from a 4-insight fixture rather than the real 244-insight Lucky bundle, and that the P1 analyst-sign-off gate the prior review flagged as Must-Before-P2 is still open — so MSIL is **ready to wire its integrations and on track to freeze, but not ready to be trusted in integration until P8 runs the real bundle through the substrate, the registry is analyst-confirmed, and the FVE gate is extended to non-OCR numbers.** Prove the substrate on real data before believing it, exactly as every prior engine in this platform had to.
