# MSIL → QAE Integration Review (Phase 8B)

**Status:** Additive integration contract, pre-implementation. No code, no implementation detail. Contracts, ownership, authority, provenance, evidence flow, coverage, corroboration, divergence, sequencing only.
**Date:** 2026-06-02
**Constraint honored:** additive only; **no redesign of frozen QAE contracts.**
**Context:** Phase 8A (MSIL → Query) complete; QAE frozen single-source READY_WITH_LIMITATIONS; QAE is the second integration (Query → **QAE** → FVE).

---

## 0. Framing — QAE Was Built For This

The QAE contracts already anticipate multi-source, and the integration mostly *activates dormant machinery* rather than adding new mechanism:
- `QualitativeSignal` is explicitly defined as **the narrative specialization of `IntelligenceSignal`** (source_type, authority_class, claim_type, event_time, provenance all present).
- Theme assembly already has **corroboration (independent-origin), divergence (authority-weighted, surfaced-never-resolved), class ceilings (opinion), and a creation gate** — all of which were *inert* on a single source (the QAE freeze recorded corroboration unexercised and divergence firing only intra-document).
- The scorecard already has **per-source coverage, divergence reporting, confidence-distribution-with-ceilings, materiality-separate-from-confidence, and coverage-first / no-fused-score.**

So MSIL integration is genuinely **additive**: MSIL supplies multi-source narrative + MSIL-computed corroboration/divergence + authority; QAE applies its existing, frozen logic. **One architectural tension must be resolved** (corroboration/divergence *ownership* — §8), and it is resolvable additively.

---

## 1. QAE in a Multi-Source World (Task 1)

QAE shifts from *single annual report, corroboration/divergence inert* to *multi-source narrative, corroboration/divergence active via MSIL* — without changing what QAE owns. QAE remains the **taxonomy + theme owner**; MSIL becomes its **evidence source** for narrative, corroboration, divergence, and authority.

**Realistic MVP coverage expansion:** the only narrative MSIL adds at MVP is **PSX-announcement narrative + SECP-notice narrative** on top of the annual report (payouts are numeric/event, not narrative; analyst/sector/news are post-MVP). Modest but real — and enough to *activate* corroboration (annual report + announcement on the same theme) and divergence (issuer "compliant" vs SECP "non-compliant"). Breadth grows; **correctness does not** — multi-source adds more keyword-tier-classified narrative, so the QAE freeze's correctness caveat **amplifies**, it does not resolve.

---

## 2. Which MSIL Signals QAE May Consume (Task 2)

| MSIL content class | QAE consumption | Rule |
|---|---|---|
| **`narrative_claim`** | **Primary input** — maps to `QualitativeSignal`; QAE classifies into taxonomy and assembles themes. | Consumed and themed. |
| **`numeric_claim`** | **Context reference only.** A theme ("borrowings increased") may *reference* a numeric_claim, but QAE never asserts the number, never validates it, never creates a theme *from* it. | Numbers route to FVE. Reference-only, never a theme source. |
| **`corporate_event`** | **Timeline/context anchor.** Themes may reference an event (a board change anchors a governance theme), but a bare event is a fact, not narrative. | Referenceable anchor; **not a standalone theme source.** |
| **`market_observation`** | **Not consumed directly.** Market is sentiment/price, not company narrative. | Reaches QAE only *via a divergence reference* (e.g. management optimism vs market sell-off), never as a theme source. |

Hard boundary: **only `narrative_claim` creates themes**; numeric and event are reference/context; market is divergence-context only.

---

## 3. Corroboration Effects (Task 3)

QAE **consumes** MSIL-computed independent-origin corroboration (it does not recompute it — §7). Applying its frozen logic:
- **Theme creation:** corroboration **never creates** a theme. Creation still requires ≥1 creation-eligible mapped `narrative_claim` (the frozen creation gate, unchanged). Corroboration only strengthens an existing theme.
- **Theme confidence:** corroboration from **independent origins** raises confidence — **bounded, diminishing, and capped by class ceiling** (cannot lift an opinion-only theme to fact class).
- **Theme materiality:** corroboration raises **salience** (counted by independent origins, not raw signal volume), which raises materiality. A multi-source-corroborated theme is more material than a single-source one.
- **No double-count:** a corroboration group counts once; circularity (news echoes, lineage) is MSIL's defense — QAE must not reintroduce it.

---

## 4. Divergence Effects (Task 4)

QAE **consumes** MSIL-surfaced **narrative-vs-narrative** divergences only (numeric divergence is FVE's — so the MB-4 numeric-divergence noise **does not reach QAE**). Applying its frozen logic:
- **Theme confidence:** a live divergence **lowers** confidence (a contested theme is less certain).
- **Theme materiality:** a live divergence **raises** materiality (a contested theme is more important to show). Confidence↓ / materiality↑ move oppositely — the designed separation.
- **Scorecard reporting:** divergences surfaced **authority-weighted, both sides + authority class, never resolved** (the scorecard contract). The QAE divergence summary now carries cross-source narrative divergences.
- QAE **surfaces, never resolves** (e.g. issuer-compliant vs SECP-noncompliant: presented with the regulator's higher authority shown, not adjudicated).

---

## 5. Authority Usage (Task 5)

- **Authority ceilings:** MSIL claim-type-scoped authority **caps** theme confidence — a theme built only from analyst/issuer-unaudited narrative is ceilinged below one from audited/regulatory narrative. QAE *applies* MSIL authority into its frozen confidence composition (alongside the existing keyword-tier/review ceilings); it never recomputes authority.
- **Opinion handling:** analyst/sector narrative = opinion-class — quarantined per the frozen create/strengthen/contradict matrix; may strengthen/contradict but **never promoted to issuer fact**; may create only clearly-labeled opinion-class themes.
- **Issuer vs regulator conflicts:** surfaced as an authority-weighted divergence (regulator higher for compliance claims), lowering the related theme's confidence and raising materiality — **never resolved by QAE.**
- **Analyst evidence:** opinion-class, ceilinged, quarantined from fact themes (analyst sources are post-MVP regardless).

---

## 6. Coverage Implications (Task 6)

- **Source-specific coverage:** the frozen scorecard's per-source coverage becomes meaningful — coverage reported per source (annual report vs PSX vs SECP narrative). A category covered by only one source is flagged.
- **Missing-source handling:** absence of a source ≠ absence of an issue. No SECP/announcement narrative for a category is a **coverage gap, reported**, never read as "no issue." The coverage caveat propagates (including into any FVE handoff).
- **Coverage-first reporting (unchanged):** coverage is the headline; no fused score; SKIPPED reasons evidenced. **Multi-source adds breadth, not validated correctness** — the keyword-tier classification limitation now spans more sources, so the scorecard must keep stating, prominently, that coverage is not correctness.

---

## 7. Prohibited Behaviors (Task 7)

- **Theme creation from `market_observation`** (never) or from `numeric_claim`/`corporate_event` alone.
- **Numeric authority leakage** — asserting a number as validated or creating a numeric theme.
- **Re-deriving corroboration** — consume MSIL's; never recompute.
- **Re-deriving divergence** — consume MSIL's narrative divergences; never recompute.
- **Resolving divergence** — surface only; never pick a side.
- **Recomputing/overriding authority** — apply MSIL's matrix, never redefine.
- **Promoting analyst/sector opinion to issuer fact.**
- **Consuming numeric divergences as narrative** (stay in lane; numeric divergence is FVE's).
- **Double-counting corroboration / treating echoed sources as independent** (MSIL lineage owns this).
- **Consuming quarantined/unresolved-entity signals as attributed.**
- **Treating multi-source coverage as correctness.**

---

## 8. Do QAE Contracts Require Additive Extension? (Task 8)

**Yes — additive clarifications only, no redesign.** Three, and one is the critical architectural reconciliation:

1. **Corroboration/Divergence ownership reconciliation (critical).** The frozen theme-assembly contract was written assuming **QAE computes** corroboration/divergence; the platform ownership table assigns **computation/detection to MSIL**. Resolve additively: **MSIL computes/detects; QAE *applies*** the results to its frozen confidence/materiality/scorecard logic and **does not re-derive cross-source corroboration/divergence.** Without this, QAE and MSIL both compute — the platform's "conflicting authorities / duplicated logic / re-deriving" prohibitions. This is the single most important finding.
2. **`QualitativeSignal` source mapping (additive).** A clarification that MSIL `narrative_claim` maps onto `QualitativeSignal` (the fields already exist); QAE consumes MSIL signals rather than only OCR insights.
3. **Scorecard source clarification (additive).** Divergence/corroboration inputs now originate from MSIL; per-source coverage now spans multiple real sources. The scorecard *structure* is unchanged.

All three are **consumption-source clarifications** captured under a `qae_consumption_contract_version` bump — the frozen *application* logic (creation gate, ceilings, materiality separation, coverage-first) is untouched.

---

## 9. Findings Classification (Task 9)

**Must Resolve Before Integration**
- **Corroboration/divergence ownership reconciliation** — MSIL computes, QAE applies; prohibit QAE re-derivation (§8.1). The key blocker.
- **MB-1 — entity-resolution analyst sign-off** (carried) — QAE binds narrative to MSIL-resolved entities; wrong-entity narrative poisons themes.
- **Content-class consumption boundary ratified** — narrative_claim only as theme source; numeric/event = reference; market = divergence-context only (§2).
- **Additive `qae_consumption_contract_version`** + the three clarifications, confirmed non-breaking to frozen application logic.
- **"Multi-source coverage ≠ correctness" caveat preserved** in the scorecard (the keyword-tier limitation amplifies with more sources).

**Can Resolve During Integration**
- Per-source coverage reporting tuning across real multi-source narrative.
- Authority-ceiling composition tuning (MSIL authority into QAE confidence).
- Corporate-event anchoring/reference plumbing into themes.
- Cross-source divergence presentation in the QAE scorecard.

**Post-MVP**
- Analyst / sector / news narrative (deferred MSIL sources) → clearly-labeled opinion-class themes.
- Cross-source recurring / year-over-year narrative (needs multi-report + the temporal model).
- Analyst truth-set validation of multi-source themes (the carried correctness gap).
- Non-manufacturer generalization.

---

## 10. One-Paragraph Verdict

The MSIL → QAE integration is the cleanest of the three because QAE was designed for it: `QualitativeSignal` is already an `IntelligenceSignal` specialization, and corroboration, divergence, authority ceilings, and per-source coverage are frozen-but-inert mechanisms that MSIL now *activates* by supplying multi-source narrative and MSIL-computed corroboration/divergence. QAE consumes **only `narrative_claim`** as a theme source (numbers are reference, events are anchors, market reaches it only through divergence), **applies** MSIL corroboration to strengthen confidence/materiality and MSIL divergence to lower confidence while raising materiality, **caps** theme confidence by MSIL authority, and keeps every frozen discipline — creation gate, opinion quarantine, surfaced-never-resolved divergence, and coverage-first reporting — untouched. The one genuine architectural issue is an ownership overlap between two frozen-era documents: the theme-assembly contract assumes QAE computes corroboration/divergence while the platform table gives that to MSIL — resolved additively by the rule **MSIL computes, QAE applies, QAE never re-derives**, captured in a consumption-contract version bump rather than a redesign. Sequenced second after Query and insulated from the numeric-divergence (MB-4) noise, QAE gains modest real multi-source breadth (announcement + SECP narrative) and finally exercises its dormant cross-source machinery — provided the integration keeps stating, as loudly as the QAE freeze did, that more sources mean more coverage, never more proven correctness.
