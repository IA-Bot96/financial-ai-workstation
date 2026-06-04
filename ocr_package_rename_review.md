# OCR Package Rename Review

**Status:** Repository organization review only. No implementation, no OCR logic changes, no architecture changes.
**Date:** 2026-06-04
**Context:** `backend/ocr_engine` = OCR V1; `backend/ocr` = OCR V2. Question: rename before migration validation begins?

**Measured footprint (read from the repo, not estimated):**
| Package | Internal `.py` | **External references** | Wired into platform? |
|---|---|---|---|
| `ocr_engine` (V1) | 100 | **73** (MSIL, QAE, Query, API routes, `run_pipeline.py`, `shared`) | **Yes — load-bearing** |
| `ocr` (V2) | 29 | **0** | **No — self-contained**, only its own tests import it |

This asymmetry governs everything below.

---

## 1. Current Naming Clarity — POOR (and inverted)

The names carry **no version signal** and the intuition runs **backwards**:
- `ocr_engine` sounds like *the* primary/canonical engine — it is actually **V1, the one being replaced**.
- `ocr` sounds like a base/stub package — it is actually **V2, the newer capture-first engine**.

A newcomer would reasonably assume `ocr` is the main package and `ocr_engine` a helper, or that `ocr_engine` is current and `ocr` is a placeholder. During a migration where **both coexist**, "which is which" must be memorized rather than read. Clarity is poor precisely in the contexts (below) where it matters most.

## 2. Impact of the ambiguity

| Context | Impact of current names |
|---|---|
| **Developer onboarding** | High confusion — must be told `ocr` = V2, `ocr_engine` = V1; the names actively mislead |
| **Manager code review** | A reviewer cannot tell from a diff path whether a change touches the production engine or the new one |
| **Architecture reviews** | Every doc must restate the mapping; ambiguity invites mis-attribution |
| **Migration validation** | V1 (baseline) and V2 (candidate) are constantly compared; ambiguous names raise the risk of comparing/citing the wrong engine |
| **Rollback planning** | Rollback depends on knowing exactly which package is the frozen fallback; `ocr_engine`-vs-`ocr` does not encode "fallback vs new" |

The pain is real — but it is an **onboarding/communication** pain, solvable with documentation, not necessarily a rename.

## 3. Option Evaluation

| Option | Names | Clarity | Rename cost / risk |
|---|---|---|---|
| **A** | `ocr_engine/` · `ocr/` (keep) | **Poor** — no version signal, inverted intuition | **Zero** |
| **B** | `ocr_engine_v1/` · `ocr_engine_v2/` | **Best** — explicit, parallel, self-documenting, neutral | **High for V1** (73 external refs + 100 modules + downstream frozen engines + tests + CI); **near-zero for V2** (0 external refs) |
| **C** | `legacy_ocr/` · `ocr/` | Medium — signals V1 is old, but **mislabels** it | High for V1 (renames it); **"legacy" is premature & dangerous** |

**Why C is rejected:** V1 is **not legacy** during validation — it is the **active production engine, the comparison baseline, and the frozen rollback path**. Labeling it `legacy_ocr` before cutover misrepresents its role and risks signaling "deprioritize this," which undermines the rollback posture exactly when V1 must stay stable. C also leaves V2 as `ocr` with no version signal.

## 4. Recommended Convention

**Option B — `ocr_engine_v1` / `ocr_engine_v2`.** It is the only convention that is version-explicit, parallel, self-documenting, and free of a premature value judgment ("legacy"). It is the correct **target** end-state.

**Critical caveat — do not do a partial rename.** Because V2 (`ocr`) has 0 external references, it is tempting to rename only V2 now. **Don't:** renaming V2 → `ocr_engine_v2` while V1 stays `ocr_engine` produces a *worse* asymmetry (`ocr_engine` vs `ocr_engine_v2` — is `ocr_engine` "v1" or "the engine"?). The parallel clarity of Option B only exists if **both** are renamed together, and renaming V1 is the expensive, risky half.

## 5. Change Surface for Option B (factual)

| Surface | V1 (`ocr_engine` → `ocr_engine_v1`) | V2 (`ocr` → `ocr_engine_v2`) |
|---|---|---|
| **Import changes** | **~73 external references** across MSIL (`annual_report_adapter`), QAE (`insight_to_signal_adapter`, `orchestrator`), Query (`input_bundle`, `knowledge_base_builder`, +many tests), `api/routes/ocr.py`, `run_pipeline.py`, `shared/company_context` — **plus 100 internal modules' import paths** | **~8 of its own test files** + `__init__` + the `sys.path` `from ocr import …` |
| **Test changes** | Test suites across MSIL/QAE/Query that import `ocr_engine` | V2's own test suite only |
| **CI impact** | Package discovery (`pyproject`/`setup`), coverage paths, pytest rootdir/conftest, any import-string config; pipeline entry points | Minimal — V2 test discovery only |
| **Documentation impact** | All OCR V1/V2 `.md` deliverables + architecture/migration/contracts docs referencing `backend/ocr_engine` and `backend/ocr` paths | Same docs reference `backend/ocr` |
| **Data impact** | None — `.xlsx`/`.kb.json`/fingerprints are data, unaffected by module path | None |

The V1 column is large and touches **frozen downstream engines**; the V2 column is trivial.

## 6. Timing Determination

| When | Verdict | Why |
|---|---|---|
| **Before bridge implementation** | **NO (physical rename)** | Adds 73-reference churn across frozen engines on the critical path; the bridge work targets `backend/ocr` (V2) and would thrash. **Do the zero-risk documentation layer instead** (below). |
| **After bridge implementation, before cutover** | **NO** | V1 must stay **frozen and unperturbed** as the comparison baseline and rollback path through validation; renaming its 73 external references mid-validation endangers the stable baseline for a cosmetic gain. |
| **After cutover** | **YES** | Once V2 is canonical and V1 is genuinely being retired, the import churn is safe (the comparison/rollback dependence on a stable V1 is over). Rename **both** to `*_v1`/`*_v2` then. (At that point even `legacy_ocr` becomes defensible, but `*_v1`/`*_v2` remains clearer.) |

**Recommended now (zero-risk):** resolve the *actual* onboarding/review pain **without any rename** — add package docstrings and a top-level README/`CLAUDE.md` mapping:
> `backend/ocr_engine` = **OCR V1** (production; frozen comparison baseline & rollback path)
> `backend/ocr` = **OCR V2** (capture-first; in migration validation)

This removes the ambiguity that hurts onboarding, review, and rollback clarity **at zero import/test/CI risk**, and defers the physical Option-B rename to after cutover.

---

## 7. One-Paragraph Verdict

The current names are genuinely poor — `ocr_engine` reads as the canonical engine when it is the one being replaced, and `ocr` reads as a base package when it is the new V2 — so the intuition is inverted exactly where clarity matters: onboarding, review, and especially rollback, where knowing which package is the frozen fallback is load-bearing. The clearest target convention is **Option B (`ocr_engine_v1` / `ocr_engine_v2`)**, not Option C, because V1 is not "legacy" during validation — it is the active production engine, the comparison baseline, and the rollback path, and mislabeling it could quietly erode the very stability the migration depends on. But the rename must be timed against the measured footprint: V2 carries **zero external references** and is free to rename, while V1 carries **seventy-three** across the frozen MSIL, QAE, and Query engines, and a partial rename of only V2 would worsen the confusion rather than fix it — so the physical Option-B rename should wait until **after cutover**, when perturbing V1's imports no longer threatens the baseline or the rollback. In the meantime, the real onboarding-and-review pain is fully resolved at zero risk by documenting the mapping in package docstrings and a top-level README, leaving the cosmetics for after correctness is won.
