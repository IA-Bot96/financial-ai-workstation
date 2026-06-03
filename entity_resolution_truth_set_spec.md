# Entity Resolution Truth Set — Specification (MSIL Phase 1)

**Status:** Specification for the analyst-reviewed entity-resolution truth set. No code.
**Date:** 2026-06-02
**Purpose:** Define the ground truth that validates the Entity Registry + Entity Resolution layer and gates `entity_resolution_audit.json` (the MSIL Phase 1 freeze keystone).
**Contracts:** `multi_source_intelligence_contracts.md` §1 (Entity Registry), §2 (Entity Resolution).

---

## 0. Principles & Analyst-Confirmation Protocol

- This document **seeds** the truth set with entities/aliases grounded in the existing corpus (Lucky Motor Corporation, Lucky Core, LEPL, YTML, ATF, AGCO all appeared in QAE/insight audits) and well-known PSX facts. It is **not** authoritative until an analyst confirms it.
- **Analyst-confirm-required fields (must be verified, never auto-trusted):** SECP registration numbers, exact legal names, less-common PSX tickers, listed-vs-unlisted status, and group-membership specifics. These are marked **[CONFIRM]**.
- **The dominant metric is mis-resolution (resolving to the *wrong* entity), not recall.** The truth set is designed first to catch cross-entity contamination — the platform's highest-severity failure — and only second to measure how much resolves.
- Resolution tiers (from the contract): `exact → alias → fuzzy → unresolved`; below-threshold ⇒ **quarantine, never force-assign**; fuzzy/news ⇒ **review**.

---

## 1. Required Entity Types (Task 1)

| `entity_type` | In MVP truth set? | Rationale |
|---|---|---|
| `company` | **Yes (core)** | Issuers + group members; the primary resolution target. |
| `security` | **Yes (core)** | Listed instruments (ticker-bearing); tickers resolve to a security, then to its company. |
| `sector` | **Yes** | PSX sector classification; Sector Summary scopes here; never a company. |
| `person` | **Optional / deferred** | Needed only once board-change events (PSX) are ingested; seeded minimally as a stub case set, not core MVP. |

`futures_instrument` is **out of scope** for the MVP truth set (Futures Market Watch is post-MVP).

---

## 2. Lucky Group Entities (Task 2)

Canonical entities (snake_case `canonical_id`). Lucky is part of the **Yunus Brothers Group (YBG)**.

| `canonical_id` | type | display_name | listed | ticker | sector | status |
|---|---|---|---|---|---|---|
| `yunus_brothers_group` | company | Yunus Brothers Group | no (holding) | — | — | active |
| `lucky_cement` | company | Lucky Cement Limited | yes | LUCK | cement | active |
| `lucky_core_industries` | company | Lucky Core Industries Limited (formerly ICI Pakistan) | yes | LCI **[CONFIRM]** | chemicals | active |
| `lucky_motor_corporation` | company | Lucky Motor Corporation (Pvt) Limited | no (JV) | — | automobile_assembler | active |
| `lucky_electric_power` | company | Lucky Electric Power Company Limited | no **[CONFIRM]** | — | power | active |
| `yunus_textile_mills` | company | Yunus Textile Mills Limited | no **[CONFIRM]** | — | textile | active |

Associated securities and sectors:

| `canonical_id` | type | links |
|---|---|---|
| `sec_luck` | security | `security_of` → `lucky_cement`; ticker LUCK |
| `sec_lci` | security | `security_of` → `lucky_core_industries`; ticker LCI **[CONFIRM]** |
| `sector_cement` | sector | members include `lucky_cement` |
| `sector_chemicals` | sector | members include `lucky_core_industries` |
| `sector_power` | sector | members include `lucky_electric_power` |
| `sector_automobile_assembler` | sector | members include `lucky_motor_corporation` |

Non-entities (must NOT enter the registry — see quarantine §8): **Aziz Tabba Foundation / "ATF"** (CSR foundation, not an issuer).

---

## 3. Millat Group Entities (Task 3)

Millat is anchored by **Millat Tractors Limited**; AGCO/Massey Ferguson is an **external principal**, not a group member.

| `canonical_id` | type | display_name | listed | ticker | sector | status |
|---|---|---|---|---|---|---|
| `millat_tractors` | company | Millat Tractors Limited | yes | MTL | automobile_assembler **[CONFIRM: tractors classification]** | active |
| `millat_industrial_products` | company | Millat Industrial Products Limited | no **[CONFIRM]** | — | automobile_parts | active |
| `millat_equipment` | company | Millat Equipment Limited | no **[CONFIRM]** | — | automobile_parts | active |
| `bolan_castings` | company | Bolan Castings Limited (associate) | yes **[CONFIRM]** | BCL **[CONFIRM]** | automobile_parts | active |

Associated securities/sectors:

| `canonical_id` | type | links |
|---|---|---|
| `sec_mtl` | security | `security_of` → `millat_tractors`; ticker MTL |
| `sec_bcl` | security | `security_of` → `bolan_castings`; ticker BCL **[CONFIRM]** |
| `sector_automobile_parts` | sector | members include the parts companies |

External principals (must NOT resolve to a Millat entity — quarantine §8): **AGCO**, **Massey Ferguson**.

---

## 4. Aliases (Task 4)

Each alias carries `alias_type` ∈ `ticker` / `legal_name` / `short_name` / `name_variant`. Ambiguity-prone bare tokens (e.g. "Lucky", "Millat", "ICI") are **deliberately excluded as standalone aliases** and handled as ambiguous cases (§7).

**Lucky group**
| `canonical_id` | ticker | legal_name | short_name | name_variants |
|---|---|---|---|---|
| `lucky_cement` | LUCK | Lucky Cement Limited | Lucky Cement | "Lucky Cement Ltd", "LCL" **[CONFIRM not colliding]** |
| `lucky_core_industries` | LCI **[CONFIRM]** | Lucky Core Industries Limited | Lucky Core | "ICI Pakistan Limited" (historical, `legal_name`), "Lucky Core Industries" |
| `lucky_motor_corporation` | — | Lucky Motor Corporation (Pvt) Limited | Lucky Motor | "LMC", "Lucky Motors" |
| `lucky_electric_power` | — | Lucky Electric Power Company Limited | Lucky Electric | "LEPL" |
| `yunus_textile_mills` | — | Yunus Textile Mills Limited | Yunus Textile | "YTML" |
| `yunus_brothers_group` | — | Yunus Brothers Group | YBG | "Yunus Brothers" |

**Millat group**
| `canonical_id` | ticker | legal_name | short_name | name_variants |
|---|---|---|---|---|
| `millat_tractors` | MTL | Millat Tractors Limited | Millat Tractors | "MTL", "Millat Tractor" |
| `millat_industrial_products` | — | Millat Industrial Products Limited | Millat Industrial | "MIPL" **[CONFIRM]** |
| `millat_equipment` | — | Millat Equipment Limited | Millat Equipment | "MEL" **[CONFIRM]** |
| `bolan_castings` | BCL **[CONFIRM]** | Bolan Castings Limited | Bolan Castings | "Bolan Casting" |

Alias rules: aliases are stored **normalized** (lowercase, `&`→`and`, punctuation stripped) per the platform `_normalize_text`; historical legal names (e.g. "ICI Pakistan Limited") are valid aliases **only with `[CONFIRM]` analyst sign-off** and are flagged historical.

---

## 5. Expected Relationships (Task 5)

| Relationship | Examples (truth) |
|---|---|
| `parent_of` | `yunus_brothers_group` → `lucky_cement`, `lucky_core_industries`, `lucky_motor_corporation`, `lucky_electric_power`, `yunus_textile_mills` |
| `subsidiary_of` | inverse of the above (each Lucky entity → `yunus_brothers_group`) **[CONFIRM exact ownership: subsidiary vs associate vs JV]** |
| `security_of` | `sec_luck` → `lucky_cement`; `sec_lci` → `lucky_core_industries`; `sec_mtl` → `millat_tractors`; `sec_bcl` → `bolan_castings` |
| `member_of_sector` | `lucky_cement` → `sector_cement`; `lucky_core_industries` → `sector_chemicals`; `millat_tractors` → `sector_automobile_assembler` **[CONFIRM]** |

**Critical truth assertion (the group-disambiguation guard):** `lucky_cement`, `lucky_core_industries`, `lucky_motor_corporation`, and `lucky_electric_power` are **four distinct companies**. Resolving any of them to another is a **severity-1 mis-resolution**. Millat group entities are likewise distinct from each other and from AGCO.

---

## 6. Positive Resolution Cases (Task 6)

Each: `raw_identifier` → expected `canonical_id`, `method`, minimum `confidence`. Resolution must match exactly.

| raw_identifier | expected entity | method | min conf |
|---|---|---|---|
| `LUCK` | `sec_luck` → `lucky_cement` | exact (ticker) | 0.99 |
| `MTL` | `sec_mtl` → `millat_tractors` | exact (ticker) | 0.99 |
| `Lucky Cement Limited` | `lucky_cement` | exact (legal) | 0.98 |
| `Lucky Cement` | `lucky_cement` | alias (short) | 0.95 |
| `Millat Tractors Limited` | `millat_tractors` | exact (legal) | 0.98 |
| `LEPL` | `lucky_electric_power` | alias (variant) | 0.90 |
| `LMC` | `lucky_motor_corporation` | alias (variant) | 0.90 |
| `YTML` | `yunus_textile_mills` | alias (variant) | 0.90 |
| `Lucky Core Industries Limited` | `lucky_core_industries` | exact (legal) | 0.98 |
| `Bolan Castings Limited` | `bolan_castings` | exact (legal) | 0.95 **[CONFIRM]** |
| `Lucky Cement Ltd.` | `lucky_cement` | alias (normalized variant) | 0.92 |

Pass condition: resolves to the expected entity at ≥ min confidence, with **correct security→company chaining** for ticker cases.

---

## 7. Ambiguous Cases (Task 7)

Each must resolve to **`review`** with the **correct candidate set** — never silently pick one.

| raw_identifier | expected behavior | expected candidates |
|---|---|---|
| `Lucky` | review | {`lucky_cement`, `lucky_core_industries`, `lucky_motor_corporation`, `lucky_electric_power`} |
| `Millat` | review | {`millat_tractors`, `millat_industrial_products`, `millat_equipment`} |
| `ICI` (bare) | review | {`lucky_core_industries` (historical)} + low-confidence flag (generic token) |
| `Lucky Power` | review | {`lucky_electric_power`} + low confidence (partial/variant) |
| `Millat Industrial` vs `Millat Equipment` | each resolves, but a bare `Millat I…` truncation | review with both as candidates |
| `Yunus` | review | {`yunus_brothers_group`, `yunus_textile_mills`} |

Pass condition: `review_status = review`, candidate set ⊇ the truth candidates, and **no auto-selection** of a single entity above threshold.

---

## 8. Expected Quarantine Cases (Task 8)

Each must resolve to **`quarantined`** (no attribution) — these must **never** bind to a group entity.

| raw_identifier | why quarantine |
|---|---|
| `AGCO` | External principal/partner of Millat; **not** a Millat entity. |
| `Massey Ferguson` | External brand/principal; not a group entity. |
| `ATF` / `Aziz Tabba Foundation` | CSR foundation, not an issuer; not in the registry. |
| `XYZ Cement Limited` (unknown issuer) | No registry match; must not snap to `lucky_cement` by sector similarity. |
| `LUCKX` / `LUK` (typo'd tickers) | No exact match; must not fuzzy-bind to LUCK. |
| `Lucky Goldstar` / `LG` | Unrelated foreign entity sharing the "Lucky" token; must not bind to the Lucky group. |
| News mention: "Lucky" in a non-financial context | Unresolvable from context alone → quarantine, not attribution. |

Pass condition: `review_status = quarantined`, `resolved_entity_ref = null`, **zero attribution** to any group entity.

---

## 9. Audit Methodology (Task 9)

`entity_resolution_audit.json` is produced by running the resolution layer over **every** truth-set `raw_identifier` and comparing to expected:

1. **Per-case outcome** — actual `{resolved_entity_ref, method, confidence, review_status, candidates}` vs expected.
2. **Severity-1 metric — mis-resolution rate** — count of positives/ambiguous/quarantine cases that resolved to the **wrong** entity (especially cross-group within Lucky or Millat). **Target: 0.**
3. **Group-disambiguation accuracy** — of the four Lucky entities and the Millat entities, fraction never confused with a sibling. **Target: 100%.**
4. **Positive precision/recall** — positives resolving to the correct entity at ≥ min confidence (recall) with no wrong bindings (precision).
5. **Ambiguity handling** — ambiguous cases routed to `review` with correct candidate sets; **no auto-selection**.
6. **Quarantine correctness** — quarantine cases quarantined with null attribution; **no false positives**.
7. **Method distribution + confidence calibration** — exact/alias/fuzzy/unresolved counts; confidence sane per tier.
8. **Version pins** — `entity_registry_version` + `resolution_logic_version` recorded; the run is reproducible.
9. **Analyst sign-off** — the truth set carries an analyst-confirmation record; `[CONFIRM]` fields are resolved before the audit is authoritative.

The audit reports these as a scorecard; mis-resolution and group-disambiguation are the **gating** numbers, not aggregate accuracy.

---

## 10. Freeze Criteria for `entity_resolution_audit.json` (Task 10)

Phase 1 (and therefore all downstream MSIL ingestion) may proceed only when:

1. **Mis-resolution rate = 0** across all positive and ambiguous cases (no cross-entity contamination).
2. **Group-disambiguation accuracy = 100%** for the Lucky four and the Millat set (each distinct, none confused with a sibling).
3. **Quarantine cases = 100% quarantined**, zero false attribution (AGCO/Massey Ferguson/ATF/unknowns never bind to a group entity).
4. **Ambiguous cases = 100% routed to `review`** with candidate sets ⊇ truth; zero silent auto-selection.
5. **Positive recall ≥ a documented threshold** (e.g. ≥0.95) — *secondary* to criteria 1–4; missing a resolvable entity is recoverable, mis-attributing one is not.
6. **All `[CONFIRM]` fields analyst-resolved** and the truth set carries an **analyst sign-off** record.
7. **Version pins present** (`entity_registry_version`, `resolution_logic_version`) and the audit reproducible against a pinned registry.
8. **Unknown/typo/foreign-token cases** demonstrably quarantine rather than fuzzy-bind.

If any of 1–4 fail, Phase 1 does **not** freeze and **no source is ingested** — because the keystone is unsafe.

---

## 11. One-Paragraph Verdict

This truth set exists to answer one question before any source is ingested: *can MSIL tell the four Lucky companies apart from each other, the Millat entities apart from AGCO, and a real issuer apart from a CSR foundation or a foreign "Lucky"?* It seeds the Lucky (Yunus Brothers Group) and Millat group registries with corpus-grounded entities and aliases, deliberately withholds ambiguity-prone bare tokens ("Lucky", "Millat", "ICI") from the alias set so they route to review rather than guess, and defines positive, ambiguous, and quarantine cases whose expected outcomes an analyst confirms. The freeze gate is intentionally asymmetric — **zero mis-resolution and 100% group-disambiguation and quarantine correctness are hard requirements, while recall is secondary** — because the platform's costliest failure is injecting one company's evidence into another's profile, and Phase 1 must not freeze until the keystone proves it will quarantine before it ever mis-attributes.
