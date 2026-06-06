# Project Plan v1 — MTA / CO₂→Aromatic Literature Mining & Catalyst Design

*Last updated: 2026-04-18*

## Vision

Build an automated, reusable pipeline that:
1. Extracts structured catalyst data from MTA and CO₂→aromatic literature
2. Tracks provenance (claim → primary paper DOI) for every data point
3. Uses ML to extract **design rules** and predict **underexplored promising catalysts**
4. Eventually feeds a wet-lab experimental validation loop

**Long-term ambition**: a domain-agnostic tool (user-defined schema + seed papers → auto-expanded catalyst database) that other catalysis groups can adopt. Comparable positioning to Dagdelen & Dunn 2024 but with citation-network validation + non-fine-tuned LLM approach.

---

## Main Pipeline (core project, must-have)

### Phase 1 — Extraction ✅ (mostly done)
- PDF → Docling → section-aware routing (v2 pipeline: `scripts/extraction/extract_docling_v2.py`)
- LLM-based evidence extraction (Claude Haiku 4.5 via Anthropic API)
- Table extraction via Docling TableFormer
- Regex-based condition extraction for Experimental sections
- SQLite DB: `db/catalysis.db`

### Phase 2 — Provenance ✅ (added 2026-04-17)
- `source_reference` extracted at unit level (LLM + table Ref. column)
- `_resolve_provenance()` maps `[12]` → `primary_paper_doi` via `ref_resolved.json`
- Every unit tagged with `provenance_tier`: **gold** (primary) / **silver** (review + DOI resolved) / **bronze** (review only)
- Multi-citation formats supported: `[12]`, `[12,15]`, `[12-15]`

### Phase 3 — Corpus expansion (in progress)
- Current: 25 papers in DB, 57 PDFs, 6,211 evidence units
- **TODO**: roll out v2 pipeline to all 26 remaining primary papers
- **TODO**: expand corpus via Semantic Scholar recommendations + OpenAlex (target ~200 papers)
- **TODO**: consider pulling Paunović 2026 supplementary data if released (912 MTH entries)

### Phase 4 — Analysis & ML (next priority)
- **Data density audit first**: how many records have ≥10 complete fields?
- Feature engineering: topology, Si/Al, metal, loading, acidity (BAS/LAS), BET, conditions → performance targets
- **Interpretable ML (path 1)**: XGBoost / decision tree + SHAP → extract design rules
- **Virtual screening (path 2)**: Gaussian Process regression → predict unexplored combinations → top-10 candidate list
- **Cross-reaction transfer (path 3)**: train on MTH data (Paunović), transfer to CO₂→aromatic
- Output target: Digital Discovery / J Chem Inf Model (methods-only) or ACS Catal (with experiments)

### Phase 5 — Experimental closure (optional, advisor-dependent)
- Collaborate with Petra de Jongh group (Utrecht) on top-2-3 candidate validation
- Template: Ren 2026 (JACS) — 336 data points + NN + 24 experiments
- Without this: target Digital Discovery
- With this: target ACS Catal / Nat Catal

---

## Branch Projects (optional, should NOT block main pipeline)

### Branch A — Chart-to-Data Extractor 🟡
**Rationale**: Paunović used ScanIt (AmsterCHEM, closed-source commercial). An open-source, pipeline-integrable alternative would have independent publishable value.

- **Short term**: use Claude Vision via extended `extract_tables_vision.py` for scatter/bar plots in papers
- **Long term (separate project)**: fine-tune or build dedicated chart-to-JSON model; position vs DePlot / UniChart / ChartLlama
- **Risk**: can easily become a year-long diversion. Keep it scoped.
- **Decision rule**: only promote to main project if Vision accuracy is a blocker for Phase 4.

### Branch B — Abstract-Level Claim Verification 🔴 (likely abandon)
**Rationale**: Semantic Scholar batch API is fast (~60× OpenAlex) but **abstract coverage for ACS/RSC/Elsevier chemistry papers is near zero** (dry run 2026-04-17: 0/20).

- **Decision**: not worth building on S2. Full-text PDF verification via Docling (we already have PDFs) is more reliable.
- **Keep**: `scripts/search/s2_abstract_dryrun.py` as a measurement tool in case S2 coverage improves.

### Branch C — Contradiction Detection 🔴 (abandoned)
**Rationale**: Framing is confrontational ("who's wrong?") and adds little over landscape analysis. Pivoted toward positive discovery framing (design rules, virtual screening) instead.

### Branch D — Schema Learning from Seed Papers 🟢 (aspirational)
**Rationale**: The quant-trading-style "factor identification" vision. User-defined schema + seed papers → auto-expanded database.

- This is the long-term tool ambition, not a short-term deliverable
- Position vs Dagdelen & Dunn 2024: they use fine-tuned LLM with fixed schema; you'd add (a) citation-network validation, (b) schema evolution from seeds, (c) no fine-tuning required
- **Scope discipline**: first do one-domain pipeline (MTA) well, generalize later

---

## Strategic Positioning

### Closest competitor: Paunović 2026 (Nature Catalysis)
- "Exploring the landscape of methanol-to-hydrocarbons conversion catalysts"
- 912 manually curated MTH datasets over 30 years
- van Bokhoven group (ETH/PSI), published 2026-03-23
- **Your differentiation**:
  - MTA-focused (they cover all MTH, weighted toward olefins)
  - Extends to CO₂→aromatics (they don't cover this at all)
  - Automated pipeline vs manual curation
  - Citation-network provenance they don't have
  - Can be paired with experimental validation loop

### Closest methods peer: Dagdelen & Dunn 2024 (Nat Commun)
- "Structured information extraction from scientific text with large language models"
- Fine-tuned GPT-3 / Llama-2 for JSON schema extraction
- Code: github.com/lbnlp/NERRE
- Case studies: dopant-host, MOF, general composition — **no catalysis performance**
- **Your differentiation**:
  - Prompt-based (no fine-tuning), cheaper entry barrier
  - Citation-network cross-paper validation
  - Catalyst-specific schema with conditions + performance + characterization

### Template for experimental closure: Ren 2026 (JACS)
- "Deciphering the Interfacial Catalysis of Metal–Oxide Nanocatalysts in CO₂ Hydrogenation through ML"
- 336 data points + 2-layer NN + 24 validation experiments → JACS
- Proves small-data + ML + experiments is a viable publishable pattern

---

## Target Venue Ladder

| Scenario | Target journal |
|----------|---------------|
| Methods-only, no experiments | Digital Discovery / J Chem Inf Model / npj Comp Mat |
| Methods + clear design rules | ACS Catal / Chem Sci |
| Methods + experimental validation | ACS Catal / Nat Comm |
| Full story + novel catalyst + strong results | Nat Catal / Nat Synth |

**Realistic aim for solo-driven MVP**: Digital Discovery (methods) or ACS Catal (with experimental collaboration).

---

## Open Questions & Decisions Needed

1. **Data density audit**: run script to count records with ≥10 complete fields (blocks Phase 4)
2. **Paunović SI data**: check if the 912 MTH entries are publicly released
3. **Scope for generalization**: is MTA case study enough for first paper, or does the tool need to be multi-domain from day one? → likely **start domain-specific, generalize in v2**

---

## Rough Timeline (personal project)

| Week | Deliverable |
|------|------------|
| 1 | Data density audit + corpus expansion plan |
| 2–3 | v2 pipeline rollout across all 57 PDFs + provenance resolution |
| 4 | Feature matrix built; initial XGBoost + SHAP design rules |
| 5–6 | Virtual screening + top-10 candidate list |
| 7 | Internal demo material: design rules + candidate list |
| 8+ | (Contingent on advisor alignment) Paper draft / experimental pilot |
