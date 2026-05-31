# Pilot Extraction v1 — 10.1016/j.apcatb.2021.120073

## Status
- Extraction mode: pilot v1
- Source basis:
  - local PDF
  - full-text extraction with `pdfplumber`
  - manual schema-guided interpretation
- Confidence:
  - paper-level: medium-high
  - system-level: medium
  - claim-level: medium
  - table row details: low-medium until row text is explicitly extracted
- Source files:
  - PDF: `/Users/avalont/Projects/knowledge/Science/pdfs/10.1016_j.apcatb.2021.120073.pdf`
  - Extracted text: `/Users/avalont/Projects/knowledge/Science/data/pdfplumber-10.1016_j.apcatb.2021.120073.full.txt`

---

## 1. Paper-level extraction

### Identification
- `paper_id`: `10.1016_j.apcatb.2021.120073`
- `doi`: `10.1016/j.apcatb.2021.120073`
- `title`: `Catalysts design for higher alcohols synthesis by CO2 hydrogenation: Trends and future perspectives`
- `year`: `2021`
- `journal`: `Applied Catalysis B: Environmental`
- `publisher`: `Elsevier / ScienceDirect`
- `paper_type`: `review`

### Workflow status
- `download_status`: `done`
- `reading_status`: `skimmed`
- `extraction_status`: `in_progress`
- `screen_status`: `core`
- `priority`: `high`
- `relevance_score`: `5`
- `text_mining_ready`: `yes`

### Scope positioning
- `topic_tags`:
  - CO2 hydrogenation
  - higher alcohols
  - C2+ alcohols
  - review
  - catalyst design
  - promoter effects
  - support effects
  - reaction conditions
  - reaction mechanism
- `focus_products`:
  - higher alcohols
  - C2–4 alcohols
  - mixed alcohols
- `focus_systems`:
  - Rh-based catalysts
  - Cu-based catalysts
  - Mo-based catalysts
  - Co-based catalysts
- `focus_level`: `broad landscape + catalyst family comparison + mechanism framing`

### Main question
How can catalysts for CO2 hydrogenation be designed to improve higher alcohol synthesis efficiency and selectivity, and which catalyst families / promoters / supports / conditions most strongly govern the outcome?

### Main contribution
Based on the extracted abstract and section transitions, this review organizes the recent progress in CO2 hydrogenation to higher alcohols around four major catalyst families—Rh-, Cu-, Mo-, and Co-based catalysts—and discusses thermodynamic limitations, catalytic performance, promoter effects, support effects, catalyst precursors, reaction conditions, and mechanistic insight.

### Key reason for project
This is one of the central review papers for the project because it directly targets higher alcohol synthesis from CO2 hydrogenation and provides a comparative structure that is useful for later text mining and cross-paper mapping.

### Project use cases
- core reading
- catalyst family map seed
- promoter/support effect map seed
- mechanism comparison seed
- table extraction seed

---

## 2. Evidence extracted directly from text

### Abstract-level evidence
From the abstract text extracted with `pdfplumber`:
- The review explicitly states that it covers:
  - catalyst design
  - catalytic performance
  - reaction mechanism
  - different experimental conditions
- It explicitly names four main catalyst categories:
  - Rh-based
  - Cu-based
  - Mo-based
  - Co-based
- It explicitly identifies important influencing factors:
  - alkali/alkaline earth metal promoters
  - transition metal promoters
  - catalyst supports
  - catalyst precursors
  - reaction conditions
  - reaction mechanism
- It explicitly frames future work in terms of:
  - emerging methodologies yet to be explored
  - future directions for high-efficiency CO2 hydrogenation to higher alcohols

### Thermodynamics section evidence
The extracted text around `Table 1` shows the paper emphasizes:
- alcohol formation is exothermic
- reverse water-gas shift is endothermic
- high pressure favors alcohol synthesis because of volume contraction
- in equilibrium, higher-carbon alcohols are favored over methanol if hydrocarbons are absent
- nevertheless, efficient HAS still requires optimized catalysts because kinetics remain limiting

This is important because it separates:
- thermodynamic feasibility
- from catalytic/kinetic control

### Catalyst-family section evidence
The extracted text explicitly indicates separate sections and summary tables for:
- `Table 2`: representative Rh-based catalysts
- `Table 3`: representative Cu-based catalysts
- `Table 4`: representative Mo-based catalysts

In addition, the abstract confirms Co-based catalysts are one of the four main categories discussed, even though the table numbering in the sampled snippets captured Rh/Cu/Mo table anchors more clearly than the Co section at this stage.

---

## 3. Paper-level scientific positioning

### Core scientific framing
This review positions higher alcohol synthesis (HAS) from CO2 hydrogenation as a more demanding target than methanol synthesis because it requires more than simple CO2 activation/hydrogenation; it also requires control over carbon-chain growth / C–C coupling and suppression of competing pathways.

### Broad mechanism frame
The paper appears to treat higher alcohol synthesis as a competition among multiple pathways, where:
- RWGS can divert carbon toward CO
- methanol-related hydrogenation routes compete with deeper chain-growth chemistry
- CO insertion / acyl-type logic is relevant at least for some catalyst families
- catalyst composition and support/promoter environment shift the balance between these routes

### Why this matters for later mining
This paper is useful not only because it names catalyst families, but because it defines a comparison space:
- catalyst family
- promoter class
- support class
- reaction condition window
- product distribution
- proposed mechanism

That makes it a strong seed paper for later ontology/schema refinement.

---

## 4. Catalyst-system-level extraction (paper-informed, still review-grain)

### System 1 — Rh-based catalysts
- `system_id`: `10.1016_j.apcatb.2021.120073::sys01`
- `system_label`: `Rh-based catalysts`
- `active_metal`: `Rh`
- `promoter`: `alkali metals and transition metals discussed as key modifiers`
- `support`: `various; support effect discussed explicitly`
- `target_products`: `higher alcohols; ethanol emphasized in some mechanism discussion`
- `major_product_class`: `higher alcohols / oxygenates`
- `typical_mechanistic frame`: `CO insertion and related coupling logic appear prominently in Rh discussion`
- `support_role`: `changes selectivity and likely affects intermediate stabilization`
- `promoter_role`: `modifies alcohol yield/selectivity and path competition`
- `performance_summary`: `Rh appears as an important family for mechanistic understanding and alcohol formation pathways, but yield remains limited in many cases.`

### System 2 — Cu-based catalysts
- `system_id`: `10.1016_j.apcatb.2021.120073::sys02`
- `system_label`: `Cu-based catalysts`
- `active_metal`: `Cu`
- `promoter`: `Zn, Fe, K, Pd, Ga, Co mentioned in extracted text snippet`
- `support`: `various`
- `target_products`: `methanol and higher alcohols; review focuses on conditions for higher alcohol formation`
- `major_product_class`: `higher alcohols / mixed oxygenates`
- `typical_mechanistic frame`: `Cu systems are framed relative to methanol synthesis and RWGS competence, with adsorbed CO/methyl/acyl logic discussed nearby`
- `support_role`: `affects hydrogenation vs coupling balance`
- `promoter_role`: `enables Cu systems to move beyond methanol-dominant behavior`
- `performance_summary`: `Cu-based systems are attractive because they are already efficient for methanol synthesis / RWGS, but need additional design features for selective higher alcohol synthesis.`

### System 3 — Mo-based catalysts
- `system_id`: `10.1016_j.apcatb.2021.120073::sys03`
- `system_label`: `Mo-based catalysts`
- `active_metal`: `Mo`
- `promoter`: `K and related modifiers are important in the extracted Mo section snippet`
- `support`: `oxide/sulfide-related systems discussed`
- `target_products`: `C2+ alcohols / mixed alcohols`
- `major_product_class`: `mixed alcohols`
- `typical_mechanistic frame`: `chain-growth-type behavior with strong promoter sensitivity`
- `support_role`: `phase and support likely influence product distribution`
- `promoter_role`: `strongly affects alcohol selectivity; KCl noted as highly effective in one extracted snippet`
- `performance_summary`: `Mo-based systems can produce C2+ alcohols, but reported alcohol selectivities remain low in many gas-phase cases, highlighting the need for better catalyst design.`

### System 4 — Co-based catalysts
- `system_id`: `10.1016_j.apcatb.2021.120073::sys04`
- `system_label`: `Co-based catalysts`
- `active_metal`: `Co`
- `promoter`: `promoter effects expected to be significant`
- `support`: `various`
- `target_products`: `mixed alcohols / higher alcohols`
- `major_product_class`: `higher oxygenates and competing hydrocarbons`
- `typical_mechanistic frame`: `likely tied to chain-growth / FTS-adjacent logic in at least part of the literature`
- `support_role`: `to be refined with deeper section reading`
- `promoter_role`: `to be refined with deeper section reading`
- `performance_summary`: `Co-based systems are important because they sit close to hydrocarbon-producing chemistry, making selectivity control especially important.`

---

## 5. Claim-level extraction

### Claim 1
- `claim_id`: `10.1016_j.apcatb.2021.120073::claim01`
- `claim_type`: `trend`
- `claim_text`: `Higher alcohol synthesis from CO2 hydrogenation is kinetically difficult even when thermodynamics can favor higher-carbon alcohols under appropriate conditions.`
- `evidence_type`: `review synthesis + thermodynamic discussion`
- `evidence_strength`: `medium`
- `confidence`: `high`
- `contradiction_flag`: `no`
- `source_anchor`: `Table 1 discussion in thermodynamics section`

### Claim 2
- `claim_id`: `10.1016_j.apcatb.2021.120073::claim02`
- `claim_type`: `comparison`
- `claim_text`: `Catalyst family alone is insufficient to explain performance; promoter class, support, precursor, and reaction conditions are treated as major selectivity-governing variables.`
- `evidence_type`: `abstract-level review synthesis`
- `evidence_strength`: `medium`
- `confidence`: `high`
- `contradiction_flag`: `no`

### Claim 3
- `claim_id`: `10.1016_j.apcatb.2021.120073::claim03`
- `claim_type`: `mechanism`
- `claim_text`: `Mechanistic understanding remains distributed across catalyst families rather than unified into one settled universal route.`
- `evidence_type`: `review synthesis`
- `evidence_strength`: `medium`
- `confidence`: `medium-high`
- `contradiction_flag`: `yes`
- `contradiction_notes`: `Different catalyst families likely emphasize different dominant intermediates and coupling routes.`

### Claim 4
- `claim_id`: `10.1016_j.apcatb.2021.120073::claim04`
- `claim_type`: `unresolved_question`
- `claim_text`: `Promoter and support effects are central but not yet reduced to a clear design law across Rh-, Cu-, Mo-, and Co-based catalysts.`
- `evidence_type`: `review synthesis`
- `evidence_strength`: `medium`
- `confidence`: `medium`
- `contradiction_flag`: `possible`
- `suggested_missing_comparison`: `Matched-condition comparison of promoter/support effects across catalyst families`
- `suggested_unexplored_combination`: `Cross-family promoter-support-mechanism matrix`

---

## 6. Table-level extraction pilot

## Table metadata sample A
- `table_id`: `10.1016_j.apcatb.2021.120073::table01`
- `table_label`: `Table 1`
- `table_type`: `thermodynamics summary`
- `table_caption_role`: `summarizes Gibbs free energy, enthalpy, and equilibrium constants of main reactions during CO2 hydrogenation`
- `why_it_matters`: `This table provides the thermodynamic backbone needed to separate kinetic limitations from equilibrium limitations.`

### Table-level insight
From the surrounding extracted text:
- alcohol selectivity decreases with increasing temperature because alcohol formation is exothermic
- RWGS becomes more favored at higher temperature because it is endothermic
- high pressure favors alcohol synthesis
- if hydrocarbons are absent, HAS is thermodynamically favored relative to methanol
- efficient catalysts are still required because kinetics remain limiting

## Table metadata sample B
- `table_id`: `10.1016_j.apcatb.2021.120073::table02`
- `table_label`: `Table 2`
- `table_type`: `Rh-catalyst performance summary`
- `why_it_matters`: `Likely a high-value row-extraction target because it compares representative Rh-based catalysts and should expose composition–condition–performance structure.`

## Table metadata sample C
- `table_id`: `10.1016_j.apcatb.2021.120073::table03`
- `table_label`: `Table 3`
- `table_type`: `Cu-catalyst performance summary`
- `why_it_matters`: `Likely one of the most important comparison tables for this project because Cu-based systems are central to CO2 hydrogenation chemistry.`

## Table metadata sample D
- `table_id`: `10.1016_j.apcatb.2021.120073::table04`
- `table_label`: `Table 4`
- `table_type`: `Mo-catalyst performance summary`
- `why_it_matters`: `Important for understanding mixed alcohol and C2+OH yield limitations and promoter effects in Mo-based systems.`

### Row-level extraction status
- Row-level extraction is **not yet complete** in this file.
- Next technical target: extract the actual row text around Tables 2–4 using page-region or table-specific extraction logic.

---

## 7. Gap-discovery signals

Based on the review framing and extracted snippets, the following gap directions are worth tracking:

1. **Cross-family comparability gap**
   - Rh-, Cu-, Mo-, and Co-based systems are discussed as separate families, but unified comparison under harmonized metrics/conditions is still difficult.

2. **Promoter role generalization gap**
   - Alkali/alkaline earth and transition metal promoters are highlighted as major factors, but a transferable promoter-function map is still missing.

3. **Support-role gap**
   - Supports are treated as important, yet support effects likely remain family-specific and mechanistically fragmented.

4. **Mechanism-evidence gap**
   - Mechanistic pictures are discussed, but evidence quality likely varies across families and studies.

5. **Selectivity-control gap**
   - The key unresolved practical issue remains how to move from CO2 activation to selective C2+ alcohol formation without losing carbon to CO, CH4, methanol, or hydrocarbons.

---

## 8. Assessment for the project

This paper is a strong seed document for:
- building a catalyst family ontology
- building a promoter/support effect ontology
- defining comparison dimensions for later extraction from primary papers
- generating a row-level benchmark table schema

It is **less useful** for direct, final numerical database population until the actual performance tables are extracted row-by-row.

---

## 9. Recommended next action

For this paper specifically, the next best action is:
1. target `Table 2`, `Table 3`, and `Table 4`
2. extract row structure
3. convert each row into catalyst-system comparison records
4. only then refine the catalyst-system schema to v1.1
