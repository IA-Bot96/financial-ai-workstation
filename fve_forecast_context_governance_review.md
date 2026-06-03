# FVE Forecast-Context Governance Review (Phase 8C Stage 2)

**Status:** Governance contract for `forecast_context` evidence in FVE. No code, no implementation detail. Authority, plausibility, confidence, warnings, reporting, ownership only.
**Date:** 2026-06-03
**Constraint honored:** no redesign of HSIG, NAG, NumericEvidence, Revenue/EPS validation.
**Goal:** define exactly how `forecast_context` may influence forecast **plausibility** while preserving the guarantee that **external opinion never becomes forecast-validation truth.**
**Stage 1 state:** supporting/event consumption + divergence surfacing implemented; baseline path unchanged; HSIG sole authority; `forecast_context` ignored (0 consumed). All ownership-boundary checks passed.

---

## 0. The Firewall — Two Halves of FVE

FVE does two distinct things, and `forecast_context` belongs to exactly one of them:
- **Historical half (validation):** is the baseline series clean and trustworthy? Owned by **HSIG**; fed only by audited values. **`forecast_context` has zero reach here.**
- **Forward half (plausibility):** is a *submitted* forecast reasonable relative to history and informed expectations? This is where `forecast_context` lives — as a **benchmark**, never as truth.

The governing principle: **`forecast_context` is firewalled to the forward/plausibility half.** It can inform whether a submitted forecast is *plausible*; it can never touch *what the historical numbers are* or *whether they are valid*. Plausibility ≠ correctness; expectation ≠ fact.

---

## 1. What `forecast_context` Is — and Is Not (Task 1)

**It is:** forward-looking *expectation* evidence — analyst expectations/consensus, broker targets, management guidance, outlook disclosures, sector expectations. A **benchmark** against which a submitted forecast's plausibility is judged. Non-authoritative opinion or forward claims.

**It is not:** a historical fact, a baseline, a validated number, a forecast FVE itself produces, or validation truth. It does not describe what *happened* (that is baseline/supporting) — it describes what someone *expects*. It is never the thing validated as "correct"; it is a reference point for "is the submitted forecast plausible relative to expectations?"

Hard boundary: `forecast_context` answers *"does this forecast align with informed expectations?"* — **never** *"is this number true?"*

---

## 2. Forecast-Context Authority (Task 2)

Authority here is **forward-claim authority** (distinct from authority-for-fact — the inversion established in the multi-source review): for what *will* happen, the issuer and independent forecasters are the relevant voices, not audited history.

| Source | Forward authority | Risk flag |
|---|---|---|
| **Management guidance** (`official_issuer_unaudited`, forward) | High for the company's own *intent* (management knows its plans) | **Optimism bias** (issuer forecasting itself) |
| **Analyst consensus** (aggregate of `independent_opinion`) | High — diversified independent benchmark; the standard reference | Herding / circularity (may echo guidance) |
| **Individual analyst view** (`independent_opinion`) | Medium — single, possibly conflicted (sell-side) | Lower than consensus |
| **Sector outlook** (`sector_aggregate`) | Medium-low — base rates / peer expectations | Frames, doesn't target the company |
| **Market sentiment** (`market_revealed`) | Lowest — revealed expectation, noisy; observation not assertion | Noise; never a benchmark FVE leans on |

**Authority ceilings (structural):** *no* `forecast_context`, regardless of source, may reach baseline or historical-validation confidence — its ceiling is **"plausibility input."** Within plausibility, management guidance and analyst consensus are the **primary benchmarks**; individual analyst / sector / market are **secondary/context**. All `forecast_context` confidence is capped **below validated-fact confidence** because it is opinion.

---

## 3. Influence Boundaries (Task 3)

| `forecast_context` MAY influence | How |
|---|---|
| **Plausibility** | Core use: a submitted forecast is compared against benchmarks; deviation informs the plausibility assessment. |
| **Confidence** | **Only plausibility confidence** (how confident the plausibility assessment is) — never historical-validation or baseline confidence. |
| **Warnings** | A forecast deviating materially from consensus/guidance raises a plausibility warning. |
| **Reporting** | Benchmarks surfaced alongside the assessment, authority-labeled. |

| `forecast_context` MUST NEVER influence | Why |
|---|---|
| **Historical validation** | HSIG verdicts and baseline series are facts, not expectations. |
| **Baseline selection** | Only audited + HSIG-passed values are baseline. |
| **HSIG** | The integrity core is untouchable by opinion. |
| **Validation truth** | Whether the historical numbers are correct is independent of what anyone expects. |

`forecast_context` lives **entirely in the forward/plausibility half** with **zero reach into the historical/baseline half.** A firewall, not a gradient.

---

## 4. Plausibility Rules (Task 4)

Plausibility produces **warnings, confidence adjustments, and reporting — never a historical-validation FAIL and never a "this forecast is wrong" verdict** (FVE cannot know the future). Status vocabulary is **plausible / plausible-with-warnings / implausible-requires-review** — distinct from pass/fail-as-truth; even "implausible" is a **review flag, not a falsehood claim.**

| Example | Warning threshold | Confidence effect | Status effect |
|---|---|---|---|
| Forecast **> analyst consensus** | Tiered by deviation: within range = info; moderately above = warning; far above = strong warning | Lowers plausibility confidence | WARNING, never FAIL (optimistic ≠ wrong) |
| Forecast **< management guidance** | Note/warning (below the company's own guidance) | Mild | Reported divergence |
| Forecast **outside historical trend AND outside consensus** | Stronger warning (data *and* experts disagree) | Lowers | WARNING / implausible-review, never historical FAIL |
| Forecast **contradicts disclosures** (e.g. growth forecast vs guided contraction) | Warning + surfaced divergence | Lowers | Implausible-requires-review |

Universal rule: a plausibility warning **never escalates to a historical-validation failure**, and FVE never declares the forecast false — it flags it for review against benchmarks.

---

## 5. Divergence Handling (Task 5) — within `forecast_context`

| Disagreement | Confidence | Warnings | Reporting |
|---|---|---|---|
| **Analyst vs analyst** (dispersion) | High dispersion → wider uncertainty band → **lower** plausibility confidence | "High analyst dispersion" | Band, not a point |
| **Analyst vs management** (consensus vs guidance) | Lowers plausibility confidence; forecast assessed against **both** | Surfaced, authority-weighted | Both benchmarks shown |
| **Management vs historical trend** (guided break) | Lowers; a guided break warrants scrutiny | Warning | Surfaced; **never a historical FAIL** (history is what it is) |
| **Sector vs company** | Lower-weight contextual divergence | Context warning | Company-vs-sector reported |

Effects summary: `forecast_context` divergence **lowers plausibility confidence + raises warnings + is reported authority-weighted** — **never a validation failure, never auto-resolved.** Dispersion is surfaced as an *uncertainty band*, not a verdict.

---

## 6. Authority Conflicts (Task 6) — management +30% vs consensus +5%

Represent **without choosing a winner**:
- **Disagreement:** show both benchmarks, authority-labeled (guidance +30%, optimism-bias-flagged; consensus +5%, independent aggregate).
- **Uncertainty:** the wide gap → a **wide plausibility band** → **low plausibility confidence** (benchmarks disagree ~6× → plausibility cannot be confidently assessed).
- **Confidence ceiling:** when authoritative forward sources diverge materially, plausibility confidence is **capped** — no high-confidence-plausible verdict is possible against self-contradicting benchmarks.
- **Assessment:** a submitted forecast is judged against the **range [consensus, guidance]**, and where it falls is reported (e.g. "+25% — near guidance, far above consensus; benchmarks diverge; review").
- **FVE never picks +30% or +5% as the right expectation** — it surfaces the disagreement, widens the band, caps confidence, and reports (surfaced-never-resolved, the platform discipline).

---

## 7. Prohibited Behaviors (Task 7)

- **Analyst forecast becoming baseline** (never).
- **Guidance becoming validation truth** — forward opinion never validates history.
- **Sentiment affecting history** — `market_revealed` never touches baseline or historical confidence.
- **Confidence inflation** — `forecast_context` boosting historical/baseline confidence (it may touch *only* plausibility confidence).
- **Authority laundering** — presenting analyst/guidance as validated fact or the company's actual number.
- **`forecast_context` entering HSIG or any baseline calculation.**
- **FVE generating its own forecast** — FVE validates the plausibility of a *submitted* forecast; forecast generation is out of scope.
- **FVE resolving `forecast_context` divergence** — surface only.
- **Plausibility warnings escalating to historical-validation FAIL.**
- **Treating a tight consensus as truth** (the consensus illusion — §8).
- **Counting guidance-echoing consensus as independent corroboration** (circularity).

---

## 8. Hidden Risks (Task 8)

- **Optimism bias** — management guidance systematically rosy. *Mitigation:* flag guidance as optimism-prone; guidance alone never makes a forecast "plausible"; weight against independent consensus.
- **Analyst herding** — analysts anchor to each other; a tight consensus may be correlated, not independent. *Mitigation:* tightness ≠ reliability; treat correlated views with caution; MSIL lineage/independence applies.
- **Stale guidance** — old guidance superseded by events. *Mitigation:* MSIL supersession; stale `forecast_context` down-weighted/flagged; recency matters for forward claims.
- **Survivorship bias** — only covered companies have consensus; absence ≠ no expectation. *Mitigation:* missing `forecast_context` = coverage gap (reported), not a quality signal.
- **Circular expectations** — consensus derived from management guidance (analysts parrot guidance) → guidance and consensus are not independent. *Mitigation:* lineage; guidance-derived consensus is **not** an independent benchmark, and apparent guidance↔consensus "agreement" may be illusory.
- **Confidence inflation** — `forecast_context` lifting confidence beyond its station. *Mitigation:* caps plausibility confidence only; never historical/baseline; never multiplied across sources.
- **Consensus illusion** — a tight consensus presented as the right answer. *Mitigation:* consensus is a benchmark, not truth; report dispersion; never treat consensus as validated.

---

## 9. Sequencing (Task 9) — by authority class, gated by MSIL source availability

**By authority class, ascending in bias-complexity — and constrained by which MSIL sources exist:**
1. **Management guidance / outlook disclosures** *(available now via PSX announcements; optimism-bias-governed)* — the first implementable `forecast_context`; prove the plausibility-benchmark mechanism with a single, bias-understood class.
2. **Analyst consensus** *(post-MVP MSIL source)* — the standard external benchmark; adds herding/circularity governance.
3. **Individual analyst → sector outlook → market sentiment** *(post-MVP)* — the noisier, lower-authority, higher-bias-complexity classes, last.

Rationale: the **authority-class axis** maps directly to influence weight and to each class's *distinct* bias risk (optimism for guidance, herding/circularity for consensus, noise for sentiment), so handling them class-by-class lets each governance be applied deliberately. **Not all-at-once** (would conflate optimism + herding + noise simultaneously). **Not by source type alone** ("analyst reports" spans consensus *and* individual views with different authority/risk). Practical order is constrained by MSIL: only guidance/outlook (via PSX) is available pre-post-MVP; analyst/sector/market arrive with their MSIL adapters.

---

## 10. Findings Classification (Task 10)

**Must Resolve Before Stage 2**
- **The firewall** — `forecast_context` structurally cannot reach historical validation / baseline / HSIG / validation truth. The integrity core.
- **Plausibility ≠ validation** — a plausibility status vocabulary (plausible / warning / implausible-review) distinct from pass/fail-as-truth; warnings never escalate to historical FAIL.
- **Authority ceilings ratified** — `forecast_context` caps at plausibility input; never baseline/historical confidence.
- **FVE generates no forecasts** — validates submitted forecasts only.
- **Carried MB-1 / MB-4** (entity sign-off; divergence policy) + **circularity/lineage for `forecast_context`** (consensus-echoing-guidance).

**Can Resolve During Stage 2**
- Plausibility-deviation thresholds and tiers.
- Dispersion / uncertainty-band presentation.
- Optimism-bias flagging for guidance.
- Per-benchmark reporting in the plausibility scorecard.

**Post-MVP**
- Analyst consensus / individual / sector / market `forecast_context` (post-MVP MSIL sources).
- The full forecast-plausibility rule set (largely deferred at FVE freeze).
- Consensus-dispersion / herding modeling.

---

## 11. One-Paragraph Verdict

`forecast_context` is the forward half of FVE's world — analyst expectations, management guidance, outlook, broker targets, sector views — and the governance is a firewall, not a dial: it may inform whether a *submitted* forecast is **plausible** against informed expectations, and it may move plausibility confidence, raise plausibility warnings, and be reported authority-weighted; it may **never** touch the historical baseline, HSIG, baseline selection, or validation truth. Plausibility is not correctness and expectation is not fact, so even an "implausible" forecast is flagged for review, never declared false, and a plausibility warning never escalates to a historical-validation failure. When forward sources disagree — management's +30% against consensus's +5% — FVE shows both with their authority and bias flags, widens the uncertainty band, caps plausibility confidence, and refuses to pick a winner, exactly as it surfaces every other divergence. Integrate it by authority class (management guidance first, available via PSX and optimism-governed; analyst/sector/market as those MSIL sources arrive) and guard against optimism bias, analyst herding, circular guidance-fed consensus, and the consensus illusion — and external opinion will sharpen FVE's forecast plausibility without ever crossing the line the whole platform was built to hold: **external expectation never becomes validation truth, and no opinion ever reaches the baseline HistoricalSeriesIntegrityGate still alone defends.**
