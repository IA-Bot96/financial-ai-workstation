# MB-4 Closure Review — Divergence-Policy Refinement

**Status:** Governance closure determination. No code, no redesign. Review only.
**Date:** 2026-06-03
**Question:** Is MB-4 still a freeze blocker, or resolved by the divergence-policy refinement?
**Answer (Task 7):** **CLOSED** — the specific defect (reference-only false-positive divergences) is eliminated and real-bundle-validated; the fix is surgical, regression-clean, and preserves genuine divergence capability; no engineering remains.

---

## 1. Reconstructing MB-4 (Task 1)

- **Original issue.** The first real Lucky run produced **120 divergences** that were not genuine contradictions.
- **Root cause.** Reference-only annual-report numerics, compared **same-source / same-authority**, bucketed by **coarse subject labels** ("renewable energy capacity details" ×21, etc.) — distinct numbers about one topic flagged as competing `fact_vs_fact` claims.
- **Why it mattered.** A consuming engine ingesting 120 false `fact_vs_fact` divergences would drown in noise, undermining the trustworthiness of the divergence signal — directly violating the divergence contract's intent (divergence = *cross-source* contradiction surfaced for adjudication).
- **Affected engines.** **Query** (would surface the 120 to users); **FVE** (consumes numeric divergence — though Stage 1's reference-only exclusion already insulated it); **QAE** (insulated — it consumes only narrative divergence).

---

## 2. Evaluating the Refinement (Task 2)

| Intent | Verdict | Evidence |
|---|---|---|
| **Architecture intent** (divergence = cross-source contradiction) | ✓ Matched | Guardrails skip same-source and same-authority comparisons — exactly the intra-report pairs that should never have been divergences. |
| **Divergence-contract intent** (authority-weighted, surfaced-never-resolved) | ✓ Matched | `surfaced_never_resolved: true` preserved; the fix changes *eligibility*, not resolution behavior — excluded candidates are deemed not-divergences, not "resolved." |
| **Ownership boundaries** | ✓ Preserved | Fix is entirely within MSIL (divergence detection is MSIL-owned); no engine logic moved; no consumer recomputes. |

The five enforced rules align precisely with intent: reference-only numerics cannot create `fact_vs_fact` unless `authoritative_numeric_value=true`; numeric `fact_vs_fact` requires **deterministic fact identity**; skips same-source; skips same-authority; **narrative divergence unchanged.** The fix is **surgical** — it removes false positives without disabling genuine divergence.

---

## 3. Evaluating Guardrails (Task 3)

| Guardrail | Triggered | Sufficient? |
|---|---|---|
| Reference-only exclusion | 121 | ✓ — reference-only numerics (non-authoritative by construction) are the correct exclusion. |
| Same-source exclusion | 121 | ✓ — intra-document numbers are not cross-source contradictions. |
| Same-authority exclusion | 121 | ✓ — equal-authority same-source pairs cannot be authority-weighted divergences. |
| Deterministic fact-identity requirement | enforced | ✓ in principle — requires a precise same-fact key before two numbers are "the same fact." |

**Sufficient for the validated case: yes** — 0 false positives on the real bundle, all 120 noise divergences eliminated. **For the genuine cross-source case:** the guardrails *permit* a real divergence (different source, different authority, precise same fact, conflicting value — e.g. issuer dividend 15 vs payout 10), and that path is **preserved and test-covered** (`authoritative_cross_source_numeric_preserved: true`) — but **not yet exercised on real data** because no real official-source feed exists at volume. That gap is **not MB-4** (which was the false-positive defect); it belongs to the pre-existing limited-real-source-volume limitation (PL-4).

---

## 4. Consumer Safety (Task 4)

| Consumer | Can a false divergence still reach it? | Status |
|---|---|---|
| **Query** (user answers) | No — 0 divergences on the validated bundle; genuine divergence still surfaceable (none on single-source). | Safe |
| **QAE** (qualitative themes) | No — consumes only `narrative_vs_narrative`; the 120 were numeric `fact_vs_fact`, never reaching QAE; narrative divergence preserved. | Safe (doubly) |
| **FVE** (forecast validation) | No — Stage 1 excludes reference-only numerics *before* divergence; now MSIL also emits 0. **Double-protected.** | Safe (doubly) |

No false divergence can reach user answers, themes, or forecast validation on the validated bundle, and every genuine divergence path is preserved.

---

## 5. Platform Invariants (Task 5)

| Invariant | Effect of MB-4 fix |
|---|---|
| **Divergence surfaced, not resolved** | **Preserved** — eligibility tightened; resolution behavior unchanged; `surfaced_never_resolved: true`. |
| **Source abundance ≠ source authority** | **Reinforced** — same-source/same-authority/reference-only exclusions prevent a volume of same-origin numbers from manufacturing divergences. |
| **Numbers gated before belief** | **Reinforced** — reference-only numerics remain non-authoritative and cannot create fact divergences unless authoritative (consistent with FVE NAG default-deny). |

MB-4's fix **violates no invariant and strengthens two.**

---

## 6. Residual Risks (Task 6)

| Risk | Classification |
|---|---|
| Genuine cross-source numeric divergence unexercised on **real** data (needs real PSX/payout/SECP volume) | **Non-blocking** — re-scoped to PL-4 (limited real-source validation), not MB-4 |
| False-**negative** risk: blanket reference-only exclusion or too-strict fact-identity could hide a genuine conflict once authoritative numbers arrive | **Roadmap** — unexercised (no authoritative cross-source numbers yet); validate when real feeds land |
| Future news/analyst divergence behavior | **Roadmap** — deferred sources |
| Authority-disagreement path (issuer vs regulator/payout) | **Non-blocking** — permitted + test-covered; real validation rolls into PL-4 |
| Source-lineage edge cases at news scale | **Roadmap** — independent of this fix |
| **Reporting hygiene:** excluded candidates are labeled under an `unresolved_divergence_details` array with `unresolved_divergences: 121`, while `divergences_detected: 0` — "unresolved" misnames *excluded* candidates | **Non-blocking** — cosmetic; clarify the field naming (excluded ≠ unresolved) |

None is blocking for MB-4 closure; all are pre-existing separate limitations or post-MVP roadmap.

---

## 7. Closure Status (Task 7)

### CLOSED

- **Defect eliminated:** 120 → 0 on the real, fingerprint-matched (`97c3123…`) bundle; `divergence_reduction: 120`.
- **Surgical & intent-matching:** removes false positives, preserves narrative and authoritative cross-source divergence; ownership and the surfaced-never-resolved rule intact.
- **Regression-clean:** authority, entity resolution, mapping failures, provenance, signal generation all pass.
- **Invariant-safe:** violates none; reinforces two.
- **Consumer-safe:** no false divergence reaches Query, QAE, or FVE.
- **Confirmation satisfied:** the platform review asked for "MB-4 confirmation"; this evidence *is* that confirmation. No MB-4-specific action remains.

Contrast with MB-1: MB-1 is CONDITIONALLY_CLOSED because a real analyst sign-off still must be performed; **MB-4 is fully CLOSED because its remediation is implemented and validated** — the two remaining-freeze items are not equivalent.

---

## 8. Remaining Actions (Task 8)

**None required to close MB-4.** For hygiene and forward safety (not closure conditions):
- Update the platform freeze review / limitations to mark **MB-4 → CLOSED**, leaving only **MB-1** as the open freeze condition.
- Re-scope the genuine-cross-source-divergence validation into **PL-4 (limited real-source validation)** — to be exercised when real PptX/SECP/payout feeds arrive — and add the false-negative check to that validation.
- Fix the cosmetic **`unresolved_divergences` → `excluded_divergence_candidates`** field naming.

---

## 9. One-Paragraph Verdict

MB-4 was a precise, well-understood defect — reference-only annual-report numerics, compared same-source and same-authority under coarse subject buckets, producing 120 phantom `fact_vs_fact` divergences — and the refinement closes it precisely: three guardrails (reference-only, same-source, same-authority) plus a deterministic-fact-identity requirement eliminate all 120 on the real fingerprint-matched bundle, with regressions clean and, crucially, **narrative divergence and authoritative cross-source numeric divergence preserved**, so the fix removes noise without amputating the capability divergence exists for. It violates no platform invariant and reinforces two (source-abundance-≠-authority and numbers-gated-before-belief), and no consumer — Query, QAE, or FVE — can now receive a false divergence. Unlike MB-1, which still requires a human attestation, MB-4 has no remaining work: it is **CLOSED**. The only honest caveat is one of scope, not of closure — genuine cross-source numeric divergence (the issuer-15-vs-payout-10 case) remains validated only by fixtures because no real official-source feed exists yet at volume; that is the pre-existing limited-real-source-volume limitation (PL-4), not a reopening of MB-4. Mark MB-4 closed, leave MB-1 as the platform's sole open freeze condition, and fix the one cosmetic field-naming issue.
