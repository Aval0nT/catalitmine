# Extraction Template v1

## Purpose
This template is **not** just for summarizing papers.
It is designed as the bridge from:
- literature collection
- to structured extraction
- to future text mining / pattern discovery / gap discovery

In other words, the goal is to make each paper machine-comparable and progressively usable for:
- catalyst-performance comparison
- mechanism comparison
- support/promoter effect mapping
- unexplored combination detection
- future hypothesis generation

---

# 1. Design Principles

## 1.1 Not a reading note template
This is **not** mainly for free-form notes like:
- summary
- impression
- takeaway

Those are still useful, but secondary.

The primary goal is to extract:
- entities
- relations
- conditions
- outcomes
- evidence strength

## 1.2 Review-first, but future-proof for primary papers
The first extraction round will include many review papers.
So the schema must support:
- paper-level synthesis claims
- mechanism overviews
- catalyst family grouping
- trend/gap statements

Later it should also support primary articles with direct experimental data.

## 1.3 Separate levels of information
A single paper may contain different layers:
- bibliographic metadata
- paper-level scope and claims
- catalyst-system-level observations
- experiment-level or condition-level details
- mechanism-level interpretations

These should not be mixed together blindly.

## 1.4 Allow uncertainty and contradiction
Scientific literature is not fully consistent.
The schema must allow:
- uncertain claims
- contradictory findings
- missing data
- inferred but not directly supported mechanism statements

---

# 2. Extraction Levels

## Level A — Paper-level
One record per paper.
Used for:
- triage
- relevance ranking
- reading workflow
- broad positioning

## Level B — Catalyst-system-level
One record per catalyst family / system discussed in a paper.
Used for:
- comparing catalysts across papers
- mapping metals/promoters/supports to products/selectivity/mechanisms

## Level C — Claim-level / mechanism-level
One record per important scientific claim.
Used for:
- contradiction tracking
- evidence scoring
- gap discovery
- future hypothesis generation

v1 does **not** need a full normalized database yet, but the template should preserve this separation conceptually.

---

# 3. Paper-Level Fields

## 3.1 Identification
- `paper_id`
  - Internal project identifier
  - Default suggestion: sanitized DOI
- `doi`
- `title`
- `year`
- `journal`
- `publisher`
- `paper_type`
  - review / article / perspective / communication / method
- `pdf_path`

## 3.2 Project Workflow Status
- `download_status`
  - not_found / partial / done
- `reading_status`
  - not_started / skimmed / read / extracted
- `extraction_status`
  - not_started / in_progress / done
- `screen_status`
  - candidate / core / supplementary / excluded
- `priority`
  - high / medium / low
- `relevance_score`
  - 1–5
- `text_mining_ready`
  - yes / no / partial

## 3.3 Scope Positioning
- `topic_tags`
  - e.g. CO2 hydrogenation; higher alcohols; C2+ alcohols; methanol; mechanism; zeolite; promoter effect
- `focus_products`
  - methanol / ethanol / propanol / butanol / higher alcohols / mixed alcohols / hydrocarbons
- `focus_systems`
  - Cu-based / Fe-based / Co-based / Rh-based / bifunctional / oxide / sulfide / carbide / zeolite-assisted
- `focus_level`
  - broad landscape / catalyst-focused / mechanism-focused / condition-focused / process-focused

## 3.4 Scientific Positioning
- `main_question`
  - What is the central scientific problem this paper addresses?
- `main_contribution`
  - Broad one-paragraph statement of the paper's contribution
- `key_reason`
  - Why it matters for this project
- `project_use_case`
  - background / core reading / mechanism source / catalyst comparison / extraction seed

## 3.5 Gap / Pattern Flags
- `gap_signals`
  - Free or semi-structured notes about missing combinations, unresolved debates, underexplored directions
- `contradiction_signals`
  - Does the paper mention conflicting views or inconsistent results?
- `followup_candidates`
  - What kinds of papers should be collected next because of this paper?

---

# 4. Catalyst-System-Level Fields

One paper may yield multiple catalyst-system records.
This level is crucial for future cross-paper comparison.

## 4.1 Catalyst Identity
- `system_id`
  - internal id, e.g. `<paper_id>::sys01`
- `paper_id`
- `system_label`
  - human-readable shorthand, e.g. `Cs-promoted Cu-Fe-Zn`
- `active_metal`
- `secondary_metal`
- `promoter`
- `support`
- `support_family`
  - oxide / zeolite / carbon / mesoporous silica / MOF-derived / carbide support / sulfide support
- `phase_features`
  - oxide / metallic / carbide / sulfide / mixed phase / interface-rich
- `acidity_feature`
  - none / Lewis / Brønsted / mixed / not_stated
- `zeolite_feature`
  - yes / no / type / topology if present
- `bifunctional_flag`
  - yes / no

## 4.2 Reaction Framing
- `feed_type`
  - CO2/H2 / syngas / CO/H2 / mixed
- `target_products`
  - list-like field
- `major_product_class`
  - methanol / C2+ alcohols / mixed alcohols / hydrocarbons / oxygenates
- `selectivity_focus`
  - e.g. ethanol-selective / higher alcohol selective / methanol suppression

## 4.3 Conditions
- `temperature_range`
- `pressure_range`
- `feed_ratio`
  - e.g. H2:CO2
- `reactor_type`
  - fixed-bed / batch / flow / slurry / not_stated
- `pretreatment`
  - reduction / carburization / sulfiding / calcination / not_stated

## 4.4 Performance
- `conversion_metric`
- `selectivity_metric`
- `space_time_yield`
- `stability_metric`
- `benchmark_status`
  - strong / moderate / weak / unclear
- `performance_summary`
  - short free text for human-readable summary

## 4.5 Mechanistic Interpretation
- `proposed_mechanism`
  - RWGS + CO insertion / methanol-mediated / carbide route / tandem pathway / interface-driven / not_stated
- `key_intermediates`
  - CO / formate / methoxy / acetate / carbide / oxygen vacancies / etc.
- `rate_limiting_step`
  - if discussed
- `c_c_coupling_role`
  - yes / no / hypothesized / unclear
- `water_role`
  - promoting / inhibiting / restructuring / not_stated
- `support_role`
  - adsorption / acid site / dispersion / interface formation / stabilization / not_stated
- `promoter_role`
  - electronic / structural / adsorption tuning / phase stabilization / not_stated

---

# 5. Claim-Level Fields

This level is what enables future contradiction analysis and gap discovery.
A paper can yield multiple important claims.

## 5.1 Claim Identity
- `claim_id`
- `paper_id`
- `system_id` (optional if claim tied to a catalyst system)
- `claim_type`
  - performance / mechanism / trend / comparison / unresolved_question / hypothesis

## 5.2 Claim Content
- `claim_text`
  - Short normalized statement
- `claim_subject`
  - e.g. `Cu-Fe-Zn catalyst`, `water effect`, `Co3O4 interface`
- `claim_predicate`
  - promotes / suppresses / stabilizes / correlates_with / enables / remains_unclear
- `claim_object`
  - e.g. `C2+ alcohol selectivity`, `CO insertion pathway`, `oxygen vacancy formation`

## 5.3 Evidence Structure
- `evidence_type`
  - review synthesis / experimental / kinetic / in_situ / operando / isotopic / DFT / comparative / speculative
- `evidence_strength`
  - strong / medium / weak / unclear
- `evidence_notes`
- `source_span`
  - section / figure / table / page if manually available

## 5.4 Reliability / Conflict
- `confidence`
  - high / medium / low
- `contradiction_flag`
  - yes / no
- `contradiction_notes`
- `novelty_flag`
  - known / emerging / speculative

## 5.5 Discovery-Oriented Fields
- `suggested_missing_comparison`
  - What comparison is missing?
- `suggested_unexplored_combination`
  - e.g. metal-support-mechanism combinations not tested
- `transferable_pattern`
  - A pattern that may generalize to other catalyst families

---

# 6. Minimal v1 Extraction Output

To avoid overengineering, v1 should not require everything.

## Required in v1
### Paper-level
- doi
- title
- year
- journal
- publisher
- paper_type
- pdf_path
- topic_tags
- priority
- relevance_score
- main_question
- main_contribution
- key_reason
- gap_signals

### Catalyst-system-level (at least for important systems)
- system_label
- active_metal
- promoter
- support
- target_products
- proposed_mechanism
- support_role
- promoter_role
- performance_summary

### Claim-level (only major claims)
- claim_type
- claim_text
- evidence_type
- evidence_strength
- contradiction_flag
- suggested_unexplored_combination

## Optional in v1
- full numerical condition normalization
- full multi-system decomposition for every paper
- exhaustive claim extraction

---

# 7. What v1 Should Enable Later

If populated consistently, this template should later enable queries like:

- Which metals most often appear in papers claiming higher alcohol selectivity?
- Which promoters are most frequently associated with C2+ formation?
- Which support types are repeatedly linked to tandem or bifunctional mechanisms?
- Which mechanism claims appear often but have weak evidence?
- Which catalyst families are well studied for methanol but underexplored for higher alcohols?
- Which metal-support-promoter combinations are repeatedly adjacent in the literature but rarely explicitly tested?

This is the practical path toward the user's long-term goal:
- semi-self-supervised literature mining
- pattern discovery
- gap discovery
- hypothesis generation

---

# 8. Recommended Next Step

After approving this template, the next action should be:
1. Pilot extraction on 2 review papers and 1 primary article
2. Observe which fields are actually useful vs noisy
3. Refine schema to v1.1
4. Only then consider migration to SQLite / multi-table design
