# Entity Resolution — Analyst Sign-Off Checklist (MB-1 Closure)

**Status:** Analyst-facing attestation checklist to close MB-1. No code, no redesign. Governance/verification only.
**Date:** 2026-06-03
**Registry under attestation:** `entity_registry_version 1.0.0` (20 entities; Lucky/Yunus Brothers Group + Millat groups).
**Outcome target:** convert MB-1 from CONDITIONALLY_CLOSED → CLOSED.

---

## 0. Instructions

- This checklist attests that the registry's **real-world facts match reality** — the one thing the closed-loop Phase 1 audit could not verify.
- **Attest only against independent sources** (PSX listing, SECP registry, the issuer's own filings) — never against the registry or truth set themselves.
- Mark each item **CONFIRMED**, **CORRECTED** (with the correct value), or **NOT_LOAD_BEARING / DEFERRED** (fact not used in resolution).
- **No registry redesign.** If a fact is wrong, record the correction; the value change is a data fix under a registry-version bump, not an engineering change.
- Completion = every load-bearing item dispositioned + a signed record (§7).

**Priority = load-bearing first** (facts the resolver actually uses): tickers, matching aliases, disambiguation relationships. Cosmetic facts may be deferred.

---

## 1. Tickers (load-bearing — used for exact resolution)

| Ticker | Registry → entity | Evidence source | Disposition |
|---|---|---|---|
| `LUCK` | `lucky_cement` | PSX listing | ☐ Confirmed / ☐ Corrected: ___ |
| `MTL` | `millat_tractors` | PSX listing | ☐ Confirmed / ☐ Corrected: ___ |
| `LCI` **[was CONFIRM]** | `lucky_core_industries` | PSX listing | ☐ Confirmed / ☐ Corrected: ___ |
| `BCL` **[was CONFIRM]** | `bolan_castings` | PSX listing | ☐ Confirmed / ☐ Corrected: ___ |

**Also confirm:** no ticker in the registry collides with an unrelated PSX issuer; ticker→security→company chaining targets the correct company.

---

## 2. Aliases (load-bearing — used for alias-tier matching)

| Alias / variant | Registry → entity | Evidence | Disposition |
|---|---|---|---|
| `LEPL` | `lucky_electric_power` | issuer filings | ☐ Confirmed / ☐ Corrected: ___ |
| `LMC` | `lucky_motor_corporation` | issuer filings | ☐ Confirmed / ☐ Corrected: ___ |
| `YTML` | `yunus_textile_mills` | issuer filings | ☐ Confirmed / ☐ Corrected: ___ |
| `ICI Pakistan Limited` (historical) **[was CONFIRM]** | `lucky_core_industries` | former-name / renaming filing | ☐ Confirmed / ☐ Corrected: ___ |
| Name variants (e.g. "Lucky Cement Ltd", "LCL") **[was CONFIRM]** | respective entities | legal-name records | ☐ Confirmed / ☐ Corrected: ___ |

**Also confirm (the ambiguity defense):** bare tokens **"Lucky", "Millat", "Yunus", "ICI"** remain **withheld** as standalone aliases (must route to review, not resolve). ☐ Confirmed.

---

## 3. Group Membership & Relationships (load-bearing — drive disambiguation)

| Relationship | Evidence | Disposition |
|---|---|---|
| `yunus_brothers_group` `parent_of` {lucky_cement, lucky_core_industries, lucky_motor_corporation, lucky_electric_power, yunus_textile_mills} | group disclosures / annual report | ☐ Confirmed / ☐ Corrected: ___ |
| The four Lucky entities are **four distinct companies** (no sibling collision) | filings | ☐ Confirmed |
| Millat set {millat_tractors, millat_industrial_products, millat_equipment, bolan_castings} distinct; relationships correct (subsidiary vs associate vs JV) **[was CONFIRM]** | Millat filings | ☐ Confirmed / ☐ Corrected: ___ |
| **AGCO / Massey Ferguson are external** (not Millat-group entities) | filings | ☐ Confirmed |
| `security_of` links (sec_luck→lucky_cement, sec_mtl→millat_tractors, sec_lci, sec_bcl) | PSX | ☐ Confirmed / ☐ Corrected: ___ |
| No disambiguation-relevant group member is **missing** from the registry | group disclosures | ☐ Confirmed |

---

## 4. Listed Status & Sector (routing-relevant)

| Entity | Listed status **[was CONFIRM]** | Sector **[was CONFIRM]** | Disposition |
|---|---|---|---|
| lucky_cement | listed | cement | ☐ |
| lucky_core_industries | listed | chemicals | ☐ |
| lucky_electric_power | unlisted? | power | ☐ Confirmed / ☐ Corrected: ___ |
| yunus_textile_mills | unlisted? | textile | ☐ Confirmed / ☐ Corrected: ___ |
| lucky_motor_corporation | unlisted (JV) | automobile_assembler | ☐ |
| millat_tractors | listed | (tractors/auto class) | ☐ Confirmed / ☐ Corrected: ___ |
| millat_industrial_products / millat_equipment | unlisted? | automobile_parts | ☐ Confirmed / ☐ Corrected: ___ |
| bolan_castings | listed? | automobile_parts | ☐ Confirmed / ☐ Corrected: ___ |

---

## 5. Registration Identifiers (attest or defer)

| SECP registration numbers | Disposition |
|---|---|
| All `[was CONFIRM]` registration IDs | ☐ Attested against SECP registry / ☐ **Marked NOT_LOAD_BEARING — not used in resolution — DEFERRED** |

*(If registration numbers are not used as resolution keys, they may be deferred; record the decision.)*

---

## 6. Implicit-Assumption Acknowledgements (record, don't necessarily resolve)

- ☐ **Ticker temporal stability** — acknowledge tickers are treated as stable; flag for re-attestation if historical/reassigned tickers are ingested (HR-5).
- ☐ **Registry completeness** — acknowledge the registry is scoped to validated issuers; new issuers require new attestation.
- ☐ **General ambiguity rule (M-2, distinct from MB-1)** — note as a *separate* governance/verification item: confirm whether bare/generic-token→review is a **general** rule or only per-token; **do not bundle into this sign-off.**

---

## 7. Sign-Off Record (governance — required for closure)

- ☐ All §1–§4 load-bearing items dispositioned (Confirmed or Corrected).
- ☐ §5 attested or explicitly deferred as not-load-bearing.
- ☐ §6 acknowledgements recorded.
- ☐ Corrections (if any) applied as a **data fix** under a registry-version note (no engineering/redesign).
- ☐ **Signed attestation** by the accountable analyst, dated, **pinned to `entity_registry_version 1.0.0`** (or the bumped version if corrections were applied).

**On completion of §7, MB-1 → CLOSED.**

---

## 8. One-Line Posture

This checklist is the *only* thing standing between CONDITIONALLY_CLOSED and CLOSED — a finite, evidence-based attestation that the identity keystone's facts are real, requiring an analyst and a regulator/exchange lookup, **no engineer and no redesign**: confirm the facts the resolver depends on, sign the record, and the platform's first invariant is verified in ground truth, not just in mechanism.
