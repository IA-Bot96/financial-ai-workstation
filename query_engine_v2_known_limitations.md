# Query Engine v2 — Known Limitations

**Status:** Release-facing known-limitations catalogue. Ships with the Query v2 freeze.
**Date:** 2026-06-03
**Companion to:** `query_engine_v2_freeze_readiness_review.md` (recommendation: READY_WITH_LIMITATIONS).
**Scope statement:** *A deterministic, evidence-bound, citation-honest federated answering layer over the available platform sources — contract-correct and single-source-validated, but **not accuracy-certified**, with multi-source synthesis and messy-query robustness not yet exercised on real data.*

Severity: **Blocking** (close before freeze) · **Material** (real; accepted under scope; consumers must respect) · **Bounded** (minor/edge; manage operationally).

---

## 0. Posture

Query v2 is **trustworthy by construction, not by certification.** It cites every claim, attaches FVE integrity to every number, displays authority exactly as MSIL assigned it, surfaces divergence without resolving it, bounds confidence, and refuses or asks for clarification rather than fabricating. It does **not** guarantee that a cited answer is the *correct* answer — that remains an analyst judgment, supported by the citations and authority labels the engine always provides.

---

## 1. Carried Platform Limitation

| ID | Limitation | Severity | Consumer guidance |
|---|---|---|---|
| **QV2-0** | **Entity-registry analyst sign-off open (MB-1).** Query binds answers to MSIL entities; the registry is analyst-unconfirmed (closed-loop). A wrong entity fact → a confidently-wrong, cited answer about the wrong company. | **Blocking** | Do not rely on entity-attributed answers until MB-1 closes. |

---

## 2. Coverage & Source Limitations

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| QV2-1 | **Single-source validation.** All real-bundle evidence is annual-report (one authority class). Divergence presentation, corroboration, and cross-source authority ranking are built and contract-correct but **unexercised on real multi-source data**. | Material | The federated/multi-source value is not yet demonstrated; treat multi-source answers as untested until real feeds land. |
| QV2-2 | **Analyst / market / news sources absent.** `risk_analysis` answers from annual-report (+ SECP-capable) evidence only — coverage-thin; missing market/news/analyst risk inputs. | Material | A `risk_analysis` answer is not a complete risk picture; read its sources and confidence. |
| QV2-3 | **`risk_analysis` may read as more complete than its sourcing.** It returns `ANSWERED` even single-sourced. | Material (mitigated) | Mitigated by bounded confidence + authority labels; respect them. |
| QV2-4 | **Insufficiency off-ramp unexercised on real data.** `INSUFFICIENT_EVIDENCE` is implemented but not triggered on the validation set (the single source covered the queries). | Bounded | Behavior under genuinely missing evidence is contract-defined but unproven on real data. |

---

## 3. Reasoning & Planning Limitations

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| QV2-5 | **Deterministic intent classification proven on a curated set** (one clean query per intent, 10/10). Robustness on messy/natural phrasing is unproven. | Material | Expect classification misses on ambiguous real phrasing; the clarify off-ramp mitigates. |
| QV2-6 | **Ranking barely exercised.** Authority-differentiated, cross-provenance ranking is untested on single-authority data (exclusion of un-provenanced items does work). | Material | Ranking quality across differing authorities/recency is unvalidated. |
| QV2-7 | **Retrieval-plan multi-source routing unexercised.** Only annual_report + QAE + FVE were consulted; announcement/payout/SECP routing is contract-defined but untested on real feeds. | Bounded | Multi-source planning unproven until real triad feeds exist. |
| QV2-8 | **No generative answering.** Answers are assembled from cited evidence; any rephrasing is constrained to already-cited claims (no new facts). | Bounded (by design) | Answers are evidence-bound, not free-form prose. |

---

## 4. Correctness Limitation

| ID | Limitation | Severity | Guidance |
|---|---|---|---|
| QV2-9 | **No answer-correctness truth set.** The engine is validated for **contract**-correctness (cited, attributed, bounded, correct status), not **answer**-correctness (whether the cited claims are the *right* answer). | Material | Treat answers as analyst-review-grade; the citations and authority labels are the verification path. |

---

## 5. Trust Guarantees That DO Hold (for balance)

These are guaranteed by construction and verified on the real bundle:
- **Every shipped claim is cited** (40/40; 0 un-cited).
- **Every number carries its FVE integrity status** (100%).
- **Authority is displayed as MSIL-assigned**, attributed per claim, never recomputed.
- **Divergence is surfaced, never resolved**; both sides authority-weighted (0 to surface on this bundle).
- **Confidence is bounded, never inflated** across engines.
- **Ambiguity → clarification; nonsense → unsupported** — never fabrication.
- **Query re-derives nothing** (9/9 ownership booleans correct).

---

## 6. Acceptance Summary

- **Blocking:** QV2-0 (MB-1, carried platform condition).
- **Material (accepted under scope; consumers must respect):** QV2-1/2/3, QV2-5/6, QV2-9.
- **Bounded (operational / post-freeze):** QV2-4, QV2-7, QV2-8.

Once MB-1 closes and the scope statement (top) is published, the remaining limitations are **acceptable for a READY_WITH_LIMITATIONS freeze**.

---

## 7. One-Line Posture

Query v2 will always tell you **who said it, where it came from, how authoritative it is, and where sources disagree** — and will ask rather than guess — but it does not yet certify that a cited answer is correct, has only been proven on a single source and curated queries, and inherits the platform's open entity sign-off; use it as a citeable, authority-honest analyst interface, not as autonomous truth.
