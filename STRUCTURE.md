# Project Structure

Authoritative reference for the repository layout. The pipeline runs in four
converging tracks — **discovery**, **table extraction**, **figure extraction**,
and **prose evidence** — that consolidate into a single SQLite store. See
[README.md](README.md) for the narrative and
[notes/project_plan_v1.md](notes/project_plan_v1.md) for the plan.

---

## Top level

```
catalitmine/
├── README.md                ← overview & quickstart
├── STRUCTURE.md             ← this file
├── CLAUDE.md                ← conventions for AI-assisted work (writing register, plan, layout)
├── LICENSE                  ← MIT
├── requirements.txt         ← core Python dependencies (curated)
├── requirements-cde2.txt    ← legacy CDE2 evidence-track extras (optional)
├── setup_env.sh             ← venv setup (--with-cde2 adds the legacy stack)
├── .env.example             ← API-key template (copy to .env; .env is git-ignored)
├── settings.json            ← Claude Code permission settings (local tooling)
│
├── scripts/                 ← Python pipeline code            (tracked)
├── schema/                  ← JSON schemas + keyword libraries (tracked)
├── notes/                   ← design documents                (tracked)
├── notebooks/               ← Colab / Jupyter notebooks        (tracked)
│
├── topics/<topic>/pdfs/     ← input PDFs, downloaded by hand   (git-ignored)
├── data/                    ← pipeline intermediates           (git-ignored)
├── db/catalysis.db          ← SQLite store                     (git-ignored)
├── outputs/                 ← analysis outputs                 (git-ignored)
└── venv/                    ← Python virtual environment       (git-ignored)
```

Everything containing data derived from copyrighted papers — PDFs, the database,
extracted intermediates, chart JSON — is git-ignored. The repository ships
**code, schemas, and docs only**.

---

## scripts/ — pipeline code

```
scripts/
├── search/                        ← Phase 0: discovery
│   ├── discover.py                ← orchestrator: query → relevance-ranked shortlist
│   ├── semantic_scholar.py        ← S2 citation-network wrapper
│   ├── fetch_oa.py                ← best-effort OA-only PDF fetch (not a primary path)
│   ├── fetcher.py                 ← PaperFetcher interface + Candidate dataclass
│   ├── search_openalex.py         ← OpenAlex search (legacy CSV CLI)
│   └── s2_abstract_dryrun.py      ← abstract-coverage measurement tool
│
├── extraction/                    ← PDF → structured data
│   ├── docling_cache.py           ← parse-once layer: ONE Docling conversion per PDF, plain artifacts
│   ├── parse_pdfs.py              ← parallel batch parser (the heavy step, run once; --workers N)
│   ├── ingest_tables.py           ← Table track: tables → db.table_rows (no LLM; cache-fed; auto-detects SI)
│   ├── diagnose_tables.py         ← table-extraction diagnostic
│   ├── extract_figures.py         ← Figure track: Docling figure crops + captions
│   ├── scope_figures.py           ← Figure track: caption-based type inventory (no API)
│   ├── bar_reader.py              ← Figure track: deterministic CV bar reader (no model)
│   ├── line_reader.py             ← Figure track: deterministic line/scatter reader + verification HTML (no model)
│   ├── chart_extractor.py         ← Figure track: pluggable backends (vision, cv-line, lineformer)
│   ├── lineformer_port/           ← LineFormer→HF port: converter, mmdet-equivalent inference, parity checks
│   ├── extract_highvalue.py       ← Figure track: vision extraction on a caption-selected subset
│   ├── extract_docling_v2.py      ← Evidence track: section-aware prose extraction (Claude)
│   ├── classify_figures.py        ← (superseded by scope_figures.py)
│   ├── models/catalysis.py        ← custom entity models
│   └── (earlier evidence-track helpers: chunk_review_pdf, select_high_value_chunks[_v2],
│        enrich_chunks_cde, ner_enrich_chunks, extract_llm_evidence, extract_records_cde,
│        extract_tables_vision, extract_performance_primary)
│
├── analysis/                      ← records, validation, visualization
│   ├── build_catalyst_records.py  ← Table track: join a paper's tables → per-catalyst records
│   ├── build_structure_activity.py← Figure track: chart points → structure–activity dataset
│   ├── validate_data.py           ← density / joinability / correlation go-no-go check
│   ├── verify_charts.py           ← human verification HTML for chart extractions
│   ├── analyze_co2_window.py      ← CO₂ process-window + family-stratified correlations
│   ├── resolve_refs_openalex.py   ← in-text citation → primary DOI (provenance)
│   ├── filter_ref_chunks.py · extract_ref_lookup_vision.py · aggregate_extra_fields.py
│   ├── gap_detection.py · pareto_viz.py · correlation_heatmap.py · shap_analysis.py
│   └── visualize_*.py             ← heatmaps & landscape plots (MTA / CO₂)
│
├── db/
│   ├── build_db.py                ← JSONL → SQLite
│   └── fill_conditions_regex.py   ← regex condition backfill
│
├── ml/                            ← Phase 4 (data validated; modelling next)
│   ├── feature_engineering.py     ← DB → feature matrix
│   ├── train_model.py             ← model training (XGBoost / RF)
│   └── screen_candidates.py       ← virtual screening of new combinations
│
├── export/to_obsidian.py          ← export records to an Obsidian vault
└── zotero/                        ← Zotero library helpers (add / upload / triage)
```

---

## schema/ — schemas & keyword libraries

```
schema/
├── paper_record.schema.json       ← JSON schema for evidence records
├── paper_record.example.json      ← example conforming record
├── table_attribute_keywords.json  ← maintainable header→attribute library (table track)
└── screening_rules.json           ← high-value chunk selection rules (evidence track)
```

---

## notes/ — design documents

```
notes/
├── project_plan_v1.md             ← plan, positioning, venue strategy
├── phase0-discovery-design-v1.md  ← Phase 0 discovery design rationale
├── figure_reader_design.md        ← figure-extraction design & roadmap (CV + PyTorch backends, route B)
└── catalysis_lexicon.md           ← catalysis writing register (enforced via CLAUDE.md)
```

---

## Git-ignored runtime layout

Created locally as you run the pipeline; never committed (derived from
copyrighted papers, and regeneratable from code + PDFs):

```
topics/<topic>/pdfs/<doi>.pdf       ← input PDFs (+ <doi>_SI.pdf for Supporting Information)
data/00_parsed/<stem>/              ← parse-once cache (doc.md, tables.json, meta.json)
data/04_search/shortlist_*.md       ← Phase 0 shortlist output
data/05_normalized/catalyst_records_<date>.jsonl
db/catalysis.db                     ← consolidated store
outputs/{charts,reports,viz}/       ← extraction & analysis outputs
```

PDF naming: DOI with `/` replaced by `_` (e.g. `10.1016_j.apcatb.2021.120073.pdf`).
