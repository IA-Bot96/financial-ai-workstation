# Canonical Qualitative Taxonomy — MVP Content (v1.0.0)

**Status:** Frozen MVP taxonomy content. This document is the source-of-truth for `canonical_qualitative_taxonomy.json`.
**Date:** 2026-06-02
**Taxonomy version:** `1.0.0`
**Scope:** 6 content categories · 27 sector-neutral themes · alias + example-area seeds · separation/merge rules · unmapped policy.
**Governing contracts:** taxonomy / signal / theme-assembly / scorecard contracts. This document is **content**, not architecture.

---

## 0. How to Read This

- **Categories** and **themes** are **closed** for v1.0.0. **Sub-themes** are intentionally not enumerated here (governed-extensible later); sector-specific vocabulary lives in **aliases** and future sub-themes, never as new themes.
- Each theme carries: `theme_ref` (stable), `category_ref` (canonical parent — owns counting), `secondary_categories` (≤2, cross-reference only), `description` (classification boundary), `aliases` (normalized match seeds), `example_area_labels` (realistic OCR `area` strings), `sector_neutral` (all true for MVP).
- Matching uses the existing `_normalize_text` normalization (lowercase, `&`→`and`, strip punctuation). Aliases are seeds, extended only by governed versioning.

### Intended JSON entry shape (for `canonical_qualitative_taxonomy.json`)
```
{
  "taxonomy_version": "1.0.0",
  "themes": [
    {
      "theme_ref": "input_cost_energy",
      "category_ref": "business_risk",
      "secondary_categories": ["outlook"],
      "description": "...",
      "aliases": ["energy cost", "fuel cost", "coal price", ...],
      "example_area_labels": ["Energy Costs", "Coal Prices", ...],
      "sector_neutral": true,
      "never_merge_with": ["energy_transition", "cost_optimization"]
    }
  ]
}
```

---

## 1. Final Frozen Category Set (Task 1)

Six content categories. (Recurring-theme and year-over-year change are **derived analyses**, not categories — never populated directly.)

| `category_ref` | Name | Scope (boundary) |
|---|---|---|
| `outlook` | Management Outlook | Management's **forward-looking** posture and expectations. |
| `strategy` | Strategic Priorities | **Deliberate initiatives** the company is pursuing. |
| `business_risk` | Business Risks | **External / financial** threats to the business. |
| `operational_risk` | Operational Risks | **Internal / execution** threats within the company's control. |
| `governance` | Governance Themes | Board, controls, compliance, and ownership structure. |
| `esg` | ESG / Sustainability | Environmental, social, and sustainability-governance themes. |

---

## 2. Final Frozen Theme Set (Task 2 + 3) — 27 themes

### Category: `outlook` — Management Outlook (4)

**`demand_outlook`** · category `outlook` · secondary `[strategy]`
- *Description:* Management's forward view of **demand/volume/market growth** for its products. Boundary: forward expectation — not the competitive *threat* (`demand_competition`).
- *Aliases:* demand outlook, volume outlook, market growth, demand growth, sales outlook, order book outlook.
- *Example area labels:* "Demand Outlook", "Market Growth", "Volume Growth", "Tractor Demand", "Cement Demand".

**`margin_pricing_outlook`** · `outlook` · secondary `[business_risk]`
- *Description:* Forward view of **pricing, margins, and profitability**. Boundary: expectation — not realized cost pressure (`input_cost_energy`).
- *Aliases:* margin outlook, pricing outlook, profitability outlook, price expectation, margin guidance.
- *Example area labels:* "Margin Outlook", "Pricing", "Profitability Outlook", "Gross Margin Expectation".

**`investment_capex_outlook`** · `outlook` · secondary `[strategy]`
- *Description:* Forward **capital-deployment / capex / dividend intent**. Boundary: the *stated forward plan* — not the executing expansion program (`capacity_expansion`).
- *Aliases:* capex outlook, investment plan, capital expenditure plan, future investment, dividend outlook, capital allocation.
- *Example area labels:* "Capex Plan", "Future Investment", "Capital Expenditure", "Dividend".

**`macro_regulatory_outlook`** · `outlook` · secondary `[business_risk]`
- *Description:* Forward view of **macro/economic/regulatory environment** (rates, inflation, policy). Boundary: forecast of the environment — not a specific regulatory *threat* (`regulatory_tax`) or *violation* (`compliance_ethics`).
- *Aliases:* economic outlook, macro outlook, regulatory outlook, policy outlook, interest rate outlook, inflation outlook.
- *Example area labels:* "Economic Outlook", "Macroeconomic Environment", "Policy Outlook", "Inflation Outlook".

### Category: `strategy` — Strategic Priorities (5)

**`capacity_expansion`** · `strategy` · secondary `[outlook, operational_risk]`
- *Description:* Deliberate **capacity / plant / production-line expansion** programs. Boundary: the executing program — not the forward intent (`investment_capex_outlook`) nor plant *reliability risk* (`production_plant_reliability`).
- *Aliases:* capacity expansion, new plant, new line, expansion project, brownfield, greenfield, capacity addition, debottlenecking.
- *Example area labels:* "Capacity Expansion", "New Plant", "Expansion", "Production Line", "Kiln Expansion".

**`market_geographic_expansion`** · `strategy` · secondary `[outlook]`
- *Description:* Entering **new markets/geographies/channels, exports, distribution** growth. Boundary: market reach — not capacity (`capacity_expansion`).
- *Aliases:* exports, export sales, geographic expansion, new market, market entry, distribution network, dealership expansion, overseas.
- *Example area labels:* "Exports", "Export Sales", "Geographic Expansion", "New Markets", "Dealer Network".

**`cost_optimization`** · `strategy` · secondary `[outlook]`
- *Description:* **Deliberate** cost reduction / efficiency / productivity initiatives. Boundary: self-driven action — not external cost pressure (`input_cost_energy`).
- *Aliases:* cost optimization, cost reduction, efficiency, productivity, cost saving, operational efficiency, rationalization.
- *Example area labels:* "Cost Optimization", "Efficiency", "Cost Savings", "Productivity Improvement".

**`diversification`** · `strategy` · secondary `[outlook]`
- *Description:* **New products, segments, verticals, M&A, investments** broadening the business. Boundary: new lines of business — not geographic reach (`market_geographic_expansion`).
- *Aliases:* diversification, new product, new segment, acquisition, joint venture, vertical integration, new business, investment in subsidiary.
- *Example area labels:* "Diversification", "New Product", "Acquisition", "Joint Venture", "New Business Line".

**`digital_technology`** · `strategy` · secondary `[operational_risk]`
- *Description:* **Digital, automation, ERP, technology** adoption initiatives. Boundary: technology *adoption strategy* — not cyber *risk* (`cybersecurity_it`).
- *Aliases:* digital transformation, automation, technology, erp, digitalization, innovation, industry 4.0, system upgrade.
- *Example area labels:* "Digital Transformation", "Automation", "Technology", "ERP Implementation".

### Category: `business_risk` — Business Risks (5)

**`input_cost_energy`** · `business_risk` · secondary `[outlook]`
- *Description:* **External cost pressure**: raw materials, energy, fuel, freight prices. Boundary: cost *threat* — not cost *strategy* (`cost_optimization`) nor renewable *transition* (`energy_transition`).
- *Aliases:* energy cost, fuel cost, coal price, raw material cost, input cost, freight cost, power cost, gas price, commodity price.
- *Example area labels:* "Energy Costs", "Coal Prices", "Raw Material", "Fuel Cost", "Freight", "Input Costs".

**`fx_interest_rate`** · `business_risk` · secondary `[outlook]`
- *Description:* **Currency, interest-rate, finance-cost** exposure. Boundary: financial-market risk — not macro *forecast* (`macro_regulatory_outlook`) nor funding *availability* (`liquidity_funding`).
- *Aliases:* exchange rate, currency risk, interest rate, finance cost, forex, devaluation, rupee depreciation, markup rate.
- *Example area labels:* "Exchange Rate", "Finance Cost", "Interest Rate", "Currency Risk", "Rupee Devaluation".

**`regulatory_tax`** · `business_risk` · secondary `[outlook]`
- *Description:* **Specific regulatory, tax, tariff, subsidy, duty** threats/changes. Boundary: external regulatory *threat* — not internal *compliance posture* (`compliance_ethics`) nor macro *forecast* (`macro_regulatory_outlook`).
- *Aliases:* regulatory risk, tax, tariff, duty, gst, subsidy, levy, sales tax, regulatory change, import duty.
- *Example area labels:* "Regulatory", "Taxation", "Tariff", "GST", "Duty", "Subsidy".

**`demand_competition`** · `business_risk` · secondary `[outlook]`
- *Description:* **Competitive pressure / demand-decline threat** (oversupply, price war, market loss). Boundary: downside threat — not management's forward *demand optimism* (`demand_outlook`).
- *Aliases:* competition, competitive pressure, demand risk, oversupply, price war, market share loss, slowdown, weak demand.
- *Example area labels:* "Competition", "Demand Risk", "Oversupply", "Market Slowdown", "Competitive Pressure".

**`liquidity_funding`** · `business_risk` · secondary `[outlook]`
- *Description:* **Funding availability, debt servicing, liquidity, working-capital stress.** Boundary: capital *availability/stress* — not rate exposure (`fx_interest_rate`) nor forward deployment (`investment_capex_outlook`).
- *Aliases:* liquidity, funding, debt servicing, working capital, borrowings, leverage, cash flow risk, refinancing, credit risk.
- *Example area labels:* "Liquidity", "Debt", "Borrowings", "Working Capital", "Funding", "Leverage".

### Category: `operational_risk` — Operational Risks (5)

**`supply_chain_procurement`** · `operational_risk` · secondary `[business_risk]`
- *Description:* **Supply, procurement, sourcing, logistics, inventory** disruption. Boundary: supply availability/continuity — not its *price* (`input_cost_energy`).
- *Aliases:* supply chain, procurement, sourcing, logistics, supplier, raw material availability, inventory, localization, import dependence.
- *Example area labels:* "Supply Chain", "Procurement", "Localization", "Raw Material Supply", "Inventory".

**`production_plant_reliability`** · `operational_risk` · secondary `[strategy]`
- *Description:* **Plant uptime, equipment, maintenance, utilization, quality** of existing operations. Boundary: running-asset reliability — not new *capacity* (`capacity_expansion`).
- *Aliases:* plant reliability, production, equipment, maintenance, utilization, downtime, capacity utilization, breakdown, quality.
- *Example area labels:* "Plant Operations", "Capacity Utilization", "Production", "Maintenance", "Equipment".

**`health_safety`** · `operational_risk` · secondary `[esg]`
- *Description:* **Workplace health & safety** of operations/workforce. Boundary: occupational safety — not broader community/social impact (`community_social`).
- *Aliases:* health and safety, hse, occupational safety, workplace safety, accident, safety record, lti.
- *Example area labels:* "Health & Safety", "HSE", "Workplace Safety", "Occupational Health".

**`workforce_labor`** · `operational_risk` · secondary `[esg]`
- *Description:* **Workforce availability, skills, retention, labor relations, training.** Boundary: human-capital *operations* — not social/community ESG (`community_social`).
- *Aliases:* workforce, labor, employees, talent, retention, training, skills, human resource, industrial relations, attrition.
- *Example area labels:* "Workforce", "Human Resource", "Training", "Employee Retention", "Labor Relations".

**`cybersecurity_it`** · `operational_risk` · secondary `[governance]`
- *Description:* **IT systems, cyber, data, business-continuity** risk. Boundary: technology *risk* — not technology *adoption strategy* (`digital_technology`).
- *Aliases:* cybersecurity, cyber risk, it risk, data security, information security, system failure, business continuity, data privacy.
- *Example area labels:* "Cybersecurity", "IT Risk", "Data Security", "Information Security".

### Category: `governance` — Governance Themes (4)

**`board_oversight`** · `governance` · secondary `[]`
- *Description:* **Board composition, independence, committees, oversight.** Boundary: corporate board — not ESG/sustainability oversight (`sustainability_governance`).
- *Aliases:* board of directors, board composition, independent director, audit committee, board oversight, governance structure, board evaluation.
- *Example area labels:* "Board of Directors", "Board Composition", "Audit Committee", "Independent Directors".

**`internal_controls`** · `governance` · secondary `[business_risk]`
- *Description:* **Internal financial controls, risk management framework, internal audit.** Boundary: control framework — not specific compliance *violations* (`compliance_ethics`).
- *Aliases:* internal controls, internal audit, risk management framework, control environment, financial controls, control framework.
- *Example area labels:* "Internal Controls", "Risk Management", "Internal Audit", "Control Framework".

**`compliance_ethics`** · `governance` · secondary `[business_risk]`
- *Description:* **Compliance posture, ethics, code of conduct, regulatory actions/violations, anti-corruption.** Boundary: conduct/compliance status — not the external regulatory *threat* (`regulatory_tax`).
- *Aliases:* compliance, code of conduct, ethics, anti-corruption, regulatory action, penalty, violation, whistleblower, secp notice.
- *Example area labels:* "Compliance", "Code of Conduct", "Ethics", "Regulatory Compliance", "Penalty".

**`ownership_related_party`** · `governance` · secondary `[]`
- *Description:* **Ownership structure, major shareholders, related-party transactions, group structure.** Boundary: ownership/relationships — not board operation (`board_oversight`).
- *Aliases:* shareholding, ownership, related party, major shareholder, group structure, associated company, sponsor, parent company.
- *Example area labels:* "Shareholding", "Related Party Transactions", "Ownership Structure", "Associated Companies".

### Category: `esg` — ESG / Sustainability (4)

**`emissions_environment`** · `esg` · secondary `[operational_risk]`
- *Description:* **Current environmental footprint**: emissions, waste, water, pollution, environmental compliance. Boundary: current footprint/impact — not the renewable *transition strategy* (`energy_transition`).
- *Aliases:* emissions, carbon, co2, environment, waste, water, pollution, environmental compliance, ghg, effluent.
- *Example area labels:* "Emissions", "Carbon Footprint", "Environment", "Waste Management", "Water Usage".

**`energy_transition`** · `esg` · secondary `[strategy]`
- *Description:* **Shift to renewable/clean energy, efficiency, decarbonization** initiatives. Boundary: the *transition strategy* — not energy *cost risk* (`input_cost_energy`) nor current emissions (`emissions_environment`).
- *Aliases:* renewable energy, solar, wind, waste heat recovery, whr, clean energy, energy efficiency, decarbonization, net zero.
- *Example area labels:* "Renewable Energy", "Solar", "Waste Heat Recovery", "Energy Efficiency", "Net Zero".

**`community_social`** · `esg` · secondary `[]`
- *Description:* **Community investment, CSR, social impact, education/health programs, diversity.** Boundary: external/social impact — not internal workforce (`workforce_labor`) or safety (`health_safety`).
- *Aliases:* community, csr, corporate social responsibility, social impact, philanthropy, education, healthcare, diversity, inclusion.
- *Example area labels:* "Community", "CSR", "Social Responsibility", "Education", "Philanthropy".

**`sustainability_governance`** · `esg` · secondary `[governance]`
- *Description:* **Sustainability governance, ESG reporting, frameworks, targets, ratings.** Boundary: ESG oversight/disclosure — not corporate board governance (`board_oversight`).
- *Aliases:* sustainability governance, esg framework, esg reporting, sustainability strategy, sdg, esg targets, sustainability committee, gri.
- *Example area labels:* "Sustainability", "ESG", "Sustainability Framework", "ESG Reporting", "SDGs".

---

## 3. Themes That Must Remain Separate Even If Similar (Task 4)

These pairs share surface vocabulary but differ in **category, intent, or direction**; collapsing them destroys meaning.

| Pair | Why separate |
|---|---|
| `demand_outlook` ↔ `demand_competition` | Management optimism vs competitive threat (opposite direction). |
| `input_cost_energy` ↔ `cost_optimization` | External pressure (risk) vs deliberate self-help (strategy). |
| `input_cost_energy` ↔ `energy_transition` | "Energy" as **cost risk** vs "energy" as **sustainability strategy** — same keyword, opposite meaning. |
| `investment_capex_outlook` ↔ `capacity_expansion` | Forward intent vs executing program. |
| `regulatory_tax` ↔ `compliance_ethics` ↔ `macro_regulatory_outlook` | External threat vs internal conduct vs macro forecast. |
| `digital_technology` ↔ `cybersecurity_it` | Tech adoption (strategy) vs tech risk (operational). |
| `emissions_environment` ↔ `energy_transition` | Current footprint vs forward transition. |
| `sustainability_governance` ↔ `board_oversight` | ESG oversight vs corporate board. |
| `health_safety` / `workforce_labor` ↔ `community_social` | Internal workforce vs external social impact. |

---

## 4. Themes That Must Never Be Auto-Merged (Task 5)

Stronger than "keep separate" — these carry **opposite materiality, authority, or direction**, so an automatic merge would actively corrupt scoring. Encoded as `never_merge_with` in the JSON:

- `input_cost_energy` ⊗ `energy_transition` (cost threat vs green strategy — the most dangerous keyword collision).
- `input_cost_energy` ⊗ `cost_optimization` (suffered vs self-driven).
- `demand_outlook` ⊗ `demand_competition` (optimism vs threat).
- `regulatory_tax` ⊗ `compliance_ethics` (external threat vs internal violation — different authority class entirely; the latter often originates from SECP).
- `macro_regulatory_outlook` ⊗ `regulatory_tax` (forecast vs realized threat).
- `capacity_expansion` ⊗ `production_plant_reliability` (growth initiative vs existing-asset risk).
- `investment_capex_outlook` ⊗ `liquidity_funding` (deployment plan vs funding stress).
- `sustainability_governance` ⊗ `board_oversight` (ESG vs corporate governance — must not let ESG swallow governance or vice versa).
- `digital_technology` ⊗ `cybersecurity_it` (opportunity vs risk).

---

## 5. Initial Unmapped-Review Policy (Task 6)

- **Never force-fit, never drop.** An `area` that matches no theme alias/keyword → `unmapped`, pooled per category-prior (where a section/adapter prior exists), retained with provenance.
- **Coverage thresholds (initial, tunable):**
  - category `unmapped_rate` > **25%** → category `ANALYZED_WITH_WARNING`.
  - category `unmapped_rate` > **50%** (or mapped coverage below floor) → `SKIPPED_INSUFFICIENT_COVERAGE`.
- **Review backlog:** unmapped `area` labels recurring **≥3 times across ≥2 issuers** become governed-extension candidates:
  - → **add an alias** to an existing theme (minor version, backward-compatible), **preferred**;
  - → **add a sub-theme** (minor version) only if it is a genuine sector facet of an existing theme;
  - → **add a theme/category** only by **major version** (breaks YoY comparability — requires migration map).
- **No silent vocabulary growth at runtime** — the alias set is frozen per version; the engine may never invent a theme to absorb an unmapped area.

---

## 6. Initial Alias Seed Set (Task 7)

The alias seed = the union of every theme's `aliases` above (≈150 seeds), grounded in the real `INSIGHTS_FINANCIAL_KEYWORDS` (`coal`, `energy`, `freight`, `exports`, `debt`, `borrowings`, `working capital`, `regulatory`, `exchange rate`, `interest rate`, `margin`, `capacity`, `expansion`, `esg`, `sustainability`, etc.). Matching tiers (per the taxonomy contract): **exact → alias → keyword → unmapped**, over `_normalize_text`-normalized strings. Seed governance:
- Aliases are **lowercase normalized phrases**; multi-word aliases match as normalized substrings.
- Ambiguous single words that collide across never-merge pairs (notably **"energy"**, **"regulatory"**, **"cost"**) are **excluded as standalone aliases** and only matched via **disambiguating multi-word aliases** ("energy cost" → `input_cost_energy`; "renewable energy" → `energy_transition`). This is the seed-level defense against the keyword-collision risk.

---

## 7. Suitability Evaluation (Task 8)

### Lucky Cement (cement manufacturer)
- **Strong fit:** `capacity_expansion` (kilns/lines), `input_cost_energy` (coal/fuel/power — central to cement), `market_geographic_expansion` (exports), `emissions_environment` + `energy_transition` (carbon-heavy + WHR/solar), `demand_outlook` (construction demand), `fx_interest_rate`, `liquidity_funding` (debt-financed expansion).
- **Sector vocab safely absorbed as aliases/sub-themes:** coal, clinker, kiln, waste heat recovery — none require new themes.
- **Expected weak spots:** `governance` and `community_social` partly starved by the upstream boilerplate filter (HD6) → likely `ANALYZED_WITH_WARNING`/`SKIPPED`, not high-unmapped.

### Millat Tractors (tractor / automotive manufacturer)
- **Strong fit:** `demand_outlook` (farm mechanization/agriculture), `capacity_expansion` (tractor units), `supply_chain_procurement` (localization/deletion, parts), `market_geographic_expansion` (dealer network/exports), `regulatory_tax` (GST/subsidy on tractors — highly material), `workforce_labor`.
- **Sector vocab as aliases:** localization, deletion %, farm mechanization, dealership, agri-subsidy → aliases under existing themes (some need adding — see unmapped risk).
- **Verdict:** both issuers map cleanly with **no new themes required** — strong evidence the sector-neutral set generalizes across two distinct manufacturers.

---

## 8. Likely Unmapped-Rate Risks (Task 9)

Estimates (directional, to be measured on real bundles):

| Category | Lucky | Millat | Stress driver |
|---|---|---|---|
| `business_risk` | ~10–15% | ~15–20% | Well-covered by financial keywords; Millat subsidy/agri terms slightly thinner. |
| `strategy` | ~10–15% | ~15–25% | Millat localization/dealership terms under-seeded. |
| `outlook` | ~15–20% | ~15–20% | Forward phrasing varies; manageable. |
| `operational_risk` | ~20–25% | ~25–30% | Plant/HSE/workforce phrasing diverse; Millat parts/localization. |
| `esg` | ~20–30% | ~20–30% | Rich but varied vocabulary (WHR, SDGs, CSR). |
| `governance` | low volume | low volume | Boilerplate filter starvation → likely `SKIPPED`, low *mapped* volume rather than high unmapped. |

- **Run-wide MVP target:** <25% unmapped per *analyzed* category; **`operational_risk` and `esg` are the expected stress points**, and **Millat `strategy`/`operational_risk`** will likely exceed Lucky due to thinner agri/auto alias seeds → an early governed-alias-extension target.

---

## 9. Taxonomy Freeze Risks (Task 10)

- **FR-1 — Manufacturing overfit (dominant).** Both validation issuers are manufacturers; `input_cost_energy`, `capacity_expansion`, `production_plant_reliability` fit them naturally. **Untested on banks (credit risk, NIM, deposits), power/IPPs (tariff, circular debt), textiles, tech.** The sector-neutral *labels* should hold, but coverage on a financial-sector issuer is unproven → highest freeze risk. *Action:* validate a non-manufacturing issuer before claiming cross-industry generality.
- **FR-2 — Risk-category granularity.** `regulatory_tax` lumps tax, tariff, subsidy, duty, and environmental regulation; `liquidity_funding` lumps debt-servicing, working capital, and credit risk. Low resolution for risk-heavy issuers (esp. banks). *Action:* candidate sub-themes post-MVP, not new themes.
- **FR-3 — Keyword-collision residue.** Even with disambiguating aliases, "energy", "cost", "regulatory" will mis-route some signals across never-merge pairs. *Action:* monitor never-merge pairs in the mapping audit.
- **FR-4 — Governance/ESG starvation read as absence.** The upstream boilerplate filter (correctly) removes platitudes, starving `governance`/`community_social`; the scorecard must report `SKIPPED`/`ANALYZED_WITH_WARNING`, never "no governance issues."
- **FR-5 — Frozen `theme_ref`s commit YoY comparability.** Any v2 theme addition needs a migration map; freezing now is a comparability commitment.
- **FR-6 — Locale coupling.** Aliases reflect Pakistan-market annual-report idiom (PKR, GST, WHR, "Turnover"). Fine for the current corpus; flagged for non-Pakistan issuers.
- **FR-7 — Category-boundary ambiguity at source.** `outlook`/`strategy` and the Outlook/Opportunities/Strategy sections overlap; the primary-category-owns-counting rule contains this, but YoY/recurring signals on these will be noisier.

---

## 10. Freeze Statement

This is the **v1.0.0 frozen taxonomy content** for QAE MVP: 6 closed content categories, 27 sector-neutral themes with canonical parents, bounded secondary tags, alias and example-area seeds, explicit separation and never-merge rules, and an unmapped-review policy that grows the vocabulary only by governed versioning. It maps cleanly across two distinct manufacturers (Lucky, Millat) **without requiring any new theme**, which is the intended evidence of sector-neutrality — but its cross-industry claim is unproven until a non-manufacturing issuer is measured, and `operational_risk`/`esg` are the expected unmapped stress points. Freeze this content, seed `canonical_qualitative_taxonomy.json` from it, pin `taxonomy_version = 1.0.0` on every signal and theme, and treat all vocabulary growth (aliases → sub-themes → themes) as versioned governed change, never runtime improvisation.
