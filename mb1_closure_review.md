# MB-1 Closure Review — Entity Registry Analyst Sign-Off

**Status:** Governance closure determination. No code, no redesign, no implementation. Review only.
**Date:** 2026-06-03
**Question:** Is MB-1 a real remaining blocker, or an uncompleted sign-off process?
**Answer (Task 8):** **CONDITIONALLY_CLOSED** — the resolution *mechanism* is proven and frozen; closure is conditional **only** on a bounded analyst fact-attestation plus a governance sign-off record, requiring **zero engineering and zero redesign.**

---

## 1. Reconstructing MB-1 (Task 1)

- **Why it exists.** Phase 1 validated entity resolution against a truth set **authored alongside the registry** — a closed loop. The audit proves the resolution *mechanism* (exact → alias → fuzzy → quarantine tiers, group disambiguation, quarantine-not-force) behaves exactly as the truth set specifies. But the truth set **asserts the same facts the registry holds**, so a wrong real-world fact (a ticker, a listed status, a subsidiary link, an alias) **passes at 100% while being wrong.** The audit has no independent ground truth; it cannot detect a fact error.
- **Why it survived to platform freeze.** The Phase 1 review flagged it as Must-Before-P2; it was carried — never closed — through P2–P7, the real-bundle run, and all three integrations. The platform freeze **elevated** it to the single hard blocker because **all three engines now bind to MSIL entities**, so a mis-binding contaminates the whole platform, not one engine.
- **Why it is a blocker.** It is the platform's first invariant — *resolve identity before trusting evidence*. Freezing on an analyst-unconfirmed registry freezes the identity keystone on unverified facts. The per-occurrence impact is severity-1 and invisible to the audit, even though the surface is small and the effort bounded.

---

## 2. Truth-Set `[CONFIRM]` and Unvalidated Facts (Task 2)

**Explicit `[CONFIRM]` items in the spec (analyst-owned, unattested):**
- Tickers: `LCI` (Lucky Core Industries), `BCL` (Bolan Castings), and the "LCL" non-collision note.
- Listed status: `lucky_electric_power`, `yunus_textile_mills`, `millat_industrial_products`, `millat_equipment`, `bolan_castings`.
- SECP registration identifiers (all entities).
- Subsidiary / associate / JV exact ownership (Lucky group, Millat group).
- `member_of_sector` mappings (esp. `millat_tractors` classification).
- Historical legal-name alias `ICI Pakistan Limited` → `lucky_core_industries`.

**Analyst-owned fact categories (per the concern):** ticker assignments · listed status · registration identifiers · subsidiary relationships · group membership · entity aliases.

**Facts not independently validated:** *all* registry facts are closed-loop-only, but they split by risk —
- **High-risk (load-bearing, drive resolution):** tickers used for matching, aliases used for matching, group/subsidiary relationships used for disambiguation, the historical-alias assignment.
- **Lower-risk (publicly obvious, still unattested):** `LUCK` → Lucky Cement, `MTL` → Millat Tractors — used in the corpus, externally verifiable, but technically not signed off.

---

## 3. Registry Assumptions Still Implicit / Unverified (Task 3)

- **Implicit — ticker uniqueness + temporal stability.** A ticker is assumed to map to one company permanently; PSX tickers can be reassigned after delisting (Phase 1 review HR-5). Unverified.
- **Implicit — registry completeness.** Assumed no missing group member that would affect disambiguation; not externally confirmed.
- **Unverified — all `[CONFIRM]` facts** (§2).
- **Analyst-dependent — group boundaries and relationship *types*** (subsidiary vs associate vs JV; YBG membership).
- **Distinct, not part of MB-1 — the general-ambiguity-rule question (Phase 1 M-2).** The audit routes bare tokens via *per-token* `manual_review_rule`s; whether a *general* "short/generic/multi-candidate → review" rule exists is a **governance/verification** question, **not** an analyst fact sign-off. It must not be bundled into MB-1; it is a separate residual.

---

## 4. Freeze-Criteria Evaluation (Task 4)

| Phase 1 criterion | Status | Note |
|---|---|---|
| Zero mis-resolution | **Satisfied (mechanism)** | 0%, on closed-loop data |
| Group-disambiguation accuracy | **Satisfied (mechanism)** | 100% |
| Quarantine correctness | **Satisfied (mechanism)** | 100% |
| Ambiguous → review correctness | **Satisfied (mechanism)** | 100%, but via per-token rules (M-2 caveat) |
| Analyst sign-off | **Unsatisfied** | Not performed |

Four of five are satisfied — **all of them mechanism criteria validated on closed-loop data.** The fifth, the only **external-reality** criterion and the only one that validates *facts*, is unsatisfied. The freeze criteria are precisely "**mechanism-satisfied, fact-validation-unsatisfied**" — exactly the MB-1 gap.

---

## 5. Residual Platform Risk if a Fact Were Wrong (Task 5)

Scenario: a wrong load-bearing fact (e.g. an incorrect `LCI` ticker, a mis-stated subsidiary link, or a mis-assigned alias).

| Engine | Impact | Severity |
|---|---|---|
| **Query** | Retrieves/cites evidence attributed to the wrong entity → a **confidently-wrong, cited** answer about the wrong company. | **High** |
| **QAE** | Narrative themes from the wrong entity's disclosures attributed to company X → wrong-company qualitative profile. | **High** |
| **FVE** | Supporting/event evidence and divergence mis-attributed; **latent baseline corruption** once baseline delegation exists. | **High (latent)** |
| **MSIL** | Source of contamination — corroboration groups wrong-entity signals, divergence false-fires across entities, timeline mixes entities. | **High (origin)** |

**Assessment:** a wrong entity fact is a **severity-1 cross-engine contamination — the platform's worst failure mode — and it is invisible to the current audit.** *But* the probability is bounded (20 entities, enumerable facts; the highest-value tickers are publicly verifiable), so the risk is **high-impact / bounded-surface / fully mitigable by a finite attestation.** This is why MB-1 is a real gate, not a formality — and equally why it is *closable* without engineering.

---

## 6. Closure Requirements (Task 6)

| Item | Owner | Required evidence | Effort | Closure condition |
|---|---|---|---|---|
| Ticker assignments (LUCK, MTL, LCI, BCL) | Analyst | PSX official ticker listing | Trivial | Each load-bearing ticker attested against PSX |
| Listed status (per entity) | Analyst | PSX listed-companies registry | Trivial | Listed/unlisted attested for each entity |
| Registration identifiers | Analyst | SECP company registry | Low | Attested, **or** marked "not load-bearing for resolution" and deferred |
| Subsidiary / associate / JV relationships | Analyst | Annual-report group structure / SECP filings | Low–Medium | Each relationship attested against filings |
| Group membership boundaries | Analyst | Group disclosures / annual report | Low | YBG / Millat boundaries attested; no disambiguation-relevant member missing |
| Entity aliases (incl. historical `ICI Pakistan Limited`, variants) | Analyst | Legal-name / former-name records | Low | Each matching alias attested; ambiguous-token withholding confirmed |
| Sector classifications | Analyst | PSX sector classification | Trivial | Each `member_of_sector` attested |
| **Sign-off record** | Governance | Signed attestation referencing `entity_registry_version 1.0.0` | Trivial | Record exists and pins the version |

---

## 7. Engineering Work Required? (Task 7)

| Work | Classification |
|---|---|
| Fact attestation (tickers, status, relationships, aliases, sectors) | **Analyst task** — lookup + confirm against PSX/SECP/filings |
| Sign-off record + version pin | **Governance task** |
| (Separate) general-ambiguity-rule confirmation (M-2) | **Governance/verification task** — *not part of MB-1*; small engineering follow-up only if routing proves per-token-only |

**Decisive finding: MB-1 requires zero engineering and zero registry redesign.** It is **100% analyst attestation + governance sign-off.** It is therefore an *uncompleted sign-off process*, not an engineering blocker — but a **genuine** governance gate, because the closed-loop audit cannot self-detect a fact error and the blast radius is severity-1.

---

## 8. Outcome (Task 8)

### CONDITIONALLY_CLOSED

- **Not CLOSED** — the attestation and sign-off record do not yet exist.
- **Not OPEN** — there is no unresolved mechanism or engineering work; calling it OPEN would falsely imply remaining build effort.
- **CONDITIONALLY_CLOSED** — the engineering is complete and frozen; closure is conditional on a **bounded, enumerable analyst fact-attestation + a governance sign-off record**, with no code and no redesign.

---

## 9. Smallest Possible Closure Checklist (Task 9)

Minimization principle: **attest only what resolution actually depends on**; defer cosmetic facts.

1. Attest the **load-bearing tickers** used for matching (LUCK, MTL, LCI, BCL) against PSX.
2. Attest **aliases used for matching**, including the historical `ICI Pakistan Limited` assignment and the ambiguous-token withholding ("Lucky"/"Millat"/"Yunus"/"ICI" excluded as standalone aliases).
3. Attest **group membership + the subsidiary/associate/JV relationships used for disambiguation** (the four Lucky entities distinct; Millat set distinct; AGCO/Massey Ferguson external).
4. Attest **listed status and sector** where they affect routing.
5. Mark any **non-load-bearing facts** (e.g. unused registration numbers) as "not used in resolution — deferred."
6. Produce a **signed attestation record** pinned to `entity_registry_version 1.0.0`.

(Detailed itemization in `entity_resolution_signoff_checklist.md`.)

---

## 10. One-Paragraph Verdict

MB-1 is exactly what the platform freeze review suspected and no more: the entity-resolution *mechanism* is proven, frozen, and faithful — zero mis-resolution, perfect group disambiguation and quarantine — but it was proven against a truth set it co-authored, so the registry's *real-world facts* (tickers, listed status, registrations, relationships, group membership, aliases) have never been externally attested, and the closed-loop audit structurally cannot catch a fact error. Because all three engines now bind to those entities, a single wrong fact is a severity-1, audit-invisible, cross-engine contamination — which is why MB-1 is a genuine gate and not a rubber stamp. But the surface is small and enumerable, the highest-value facts are publicly verifiable, and **closing it requires no engineering and no redesign — only a bounded analyst attestation against PSX/SECP/filings and a signed record pinned to registry version 1.0.0.** MB-1 is therefore **CONDITIONALLY_CLOSED**: not a remaining engineering blocker, but a real, finite, analyst-and-governance sign-off that must be completed — not waived — before the platform freeze is honest. Complete the six-item checklist and MB-1 closes cleanly, with the platform's first invariant finally verified in ground truth rather than only in mechanism.
