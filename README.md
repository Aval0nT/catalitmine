# catalitmine — Catalysis Literature Mining

> A reproducible, **fine-tuning-free** pipeline that turns a research query into
> a structured, provenance-tracked database of catalysts, reaction conditions,
> and performance — end to end, automatically.

**Domains:** methanol-to-aromatics (MTA) and CO₂-to-aromatics; the schema is
designed to generalize to other catalysis reactions.

---

## Highlights

- **End-to-end automation** — research query → relevance-ranked literature
  shortlist → table extraction → joined per-catalyst records → analysis.
- **Table-centric structured data, no LLM** — catalysis tables are
  catalyst-keyed property sheets; joining a paper's textural / acidity /
  composition / performance tables on the catalyst column reconstructs a dense
  per-catalyst record, even when no single table holds everything. **547
  records across 51 papers** so far — roughly fivefold more complete records
  than sentence-level prose extraction yielded from the same corpus.
- **Citation-network provenance** — every record is traceable to its primary
  source via gold / silver / bronze tiers.
- **Validated, not merely built** — the auto-extracted data reproduces
  established kinetics: space velocity ↑ → conversion ↓ (*r* = −0.51, *n* = 50)
  and temperature ↑ → conversion ↑ (*r* = +0.33, *n* = 71), alongside
  BET area ↑ → Brønsted-acid density ↑ (*r* = +0.53). Recovering known physics
  from automatically extracted numbers is direct evidence the data is sound.
  **139 records already support condition–performance analysis.**
- **Figures → data, mostly API-free** — figures are typed from their *caption*
  (free, deterministic): characterization (XRD / NH₃-TPD / Raman / IR) is gated
  out and only activity & structure–activity panels go downstream. A pixel-level
  CV reader digitises stacked and grouped **bar charts** with no model (validated
  to ≤0.5 % on tall segments, ±2–4 % on small ones, against printed values).
  Across the corpus: **48 / 51 papers carry activity figures** (~150 line/scatter,
  ~43 bar). A line/scatter CV reader (markers + OCR-calibrated axes) is next, to
  make figure extraction fully model-free.

---

## What this does

Automated catalyst-data extraction usually either severs the link back to the
primary source (treating review-stated numbers as facts) or is locked to a
single fixed schema. This pipeline addresses both, across complementary tracks:

1. **Discovery** — a research query is expanded via OpenAlex search and the
   Semantic Scholar citation network, then each candidate is relevance-scored
   by Claude Haiku 4.5 into a screening shortlist.
2. **Table track (no LLM)** — [Docling](https://github.com/DS4SD/docling)
   extracts every table; tables are parsed against a maintainable
   header→attribute keyword library, then joined within each paper on the
   catalyst label into per-catalyst records (handles transposed tables,
   ligature/OCR artifacts, and Supporting-Information PDFs).
3. **Figure track** — figures are classified by caption keywords (free),
   keeping only activity / structure–activity panels; a deterministic CV reader
   digitises bar charts (stacked & grouped) with no model, and a vision backend
   reads line/scatter points where needed. Output feeds the structure–activity set.
4. **Evidence track** — section-aware prose extraction (Claude Haiku 4.5,
   prompt-only) captures claims, mechanisms, and conditions, each tagged with a
   **provenance tier**: *gold* (primary paper), *silver* (review with the
   in-text citation resolved to a primary DOI), *bronze* (review synthesis).
5. **Analysis** — records consolidate into SQLite for density auditing,
   condition–performance correlation, and (next) structure–activity modelling.

---

## Status

| Phase | Goal | State |
|---|---|---|
| 0 | Discovery (query → relevance-ranked screening shortlist) | ✅ Complete (v1) |
| 1 | PDF → tables → per-catalyst records (LLM-free) + prose evidence | ✅ Complete |
| 2 | Citation-network provenance (gold / silver / bronze) | ✅ Complete |
| 3 | Corpus: 51 papers · 547 per-catalyst records · 7,491 prose evidence units | 🟡 Expanding (target ~200) |
| 4 | ML analysis: condition–performance → structure–activity (XGBoost/SHAP, GP screening) | 🟡 Data validated; modelling next |
| 5 | Wet-lab validation loop | ⏳ Collaborator-dependent |

This is an active, single-author research codebase. Interfaces may change.

**Data usability — verified.** 547 per-catalyst records; 219 carry a
performance metric, 164 a structural/textural/acidity property; 139 support
condition–performance analysis today. Structure–activity records (catalyst with
both performance *and* property) currently number ~47 and are being grown via
Supporting-Information tables, figure digitisation, and corpus expansion.

**Figure inventory.** A caption-based scan of all 51 papers (no API) finds
48 with activity figures — ~150 line/scatter and ~43 bar charts — versus the
characterization figures (XRD/TPD/IR) that are correctly gated out. Bar charts
already digitise deterministically; line/scatter digitisation is the next module.

---

## Validation

A go/no-go check (`scripts/analysis/validate_data.py`) builds a numeric feature
matrix from the table-derived records and tests for signal. Without any curation
beyond unit coalescing, established catalysis relationships emerge:

| Relationship | *r* | *n* | Reading |
|---|---|---|---|
| GHSV ↑ → CO₂ conversion ↓ | −0.51 | 50 | shorter contact time lowers conversion |
| Temperature ↑ → CO₂ conversion ↑ | +0.33 | 71 | kinetic temperature dependence |
| BET area ↑ → Brønsted-acid density ↑ | +0.53 | 27 | more accessible framework acid sites |
| CO₂ conversion ↑ → space-time yield ↑ | +0.54 | 20 | conversion drives productivity |

That textbook kinetics fall out of automatically extracted numbers is the
clearest evidence the extraction is faithful.

**Methodological honesty.** Raw correlations across a pooled corpus can mislead:
the dataset mixes two reactions (MTA and CO₂→aromatics), so conversions and
selectivities are never merged across them, and a spurious
pressure × conversion = −0.51 trend is a clear mixed-population (Simpson)
artifact. Quantitative modelling therefore proceeds stratified by reaction and
catalyst family — which is also why structure–activity records are being grown
before any model is reported.

---

## Architecture

Full directory layout: [STRUCTURE.md](STRUCTURE.md).
Active plan and venue strategy: [notes/project_plan_v1.md](notes/project_plan_v1.md).

```
research query
      │  scripts/search/discover.py                         (Phase 0)
      ▼
data/04_search/shortlist_<slug>_<date>.md                  ← relevance-ranked,
                                                              human-screened
      │  (download main PDF + Supporting Information by hand)
      ▼
topics/*/pdfs/<doi>.pdf  (+ <doi>_SI.pdf)
      │
      ├─▶ scripts/extraction/ingest_tables.py   ── Docling tables (no LLM) ──┐
      │                                                                       ▼
      │                                                         db.table_rows
      │                                                                       │
      │   scripts/analysis/build_catalyst_records.py  ── join tables on ──────┤
      │   (transpose-aware, artifact-clean, fuzzy within-paper join)          ▼
      │                                       data/05_normalized/catalyst_records.jsonl
      │                                                                       │
      └─▶ scripts/extraction/extract_docling_v2.py  ── prose evidence ────┐   │
                + scripts/analysis/resolve_refs_openalex.py (provenance)  ▼   │
                                              data/03_evidence/*.jsonl        │
                                                          │                   │
                          scripts/db/build_db.py ◀────────┴───────────────────┘
                                  ▼
                          db/catalysis.db
                                  │  scripts/analysis/validate_data.py
                                  ▼
                  feature matrix · density audit · correlations
```

### Key modules

| Path | Role |
|---|---|
| `scripts/search/discover.py` | **Phase 0** — query → relevance-ranked shortlist (OpenAlex + S2 citation network + Claude scoring) |
| `scripts/extraction/ingest_tables.py` | **Table track** — Docling tables → `db.table_rows` (LLM-free); auto-detects SI PDFs |
| `scripts/analysis/build_catalyst_records.py` | **Table track** — join a paper's tables on the catalyst label → per-catalyst records |
| `schema/table_attribute_keywords.json` | Maintainable header→attribute keyword library |
| `scripts/analysis/validate_data.py` | Density / joinability / correlation go-no-go check |
| `scripts/extraction/extract_figures.py` | **Figure track** — Docling figure crops + captions |
| `scripts/extraction/scope_figures.py` | **Figure track** — caption-based corpus figure inventory (no API) |
| `scripts/extraction/bar_reader.py` | **Figure track** — deterministic CV reader for bar charts (no model) |
| `scripts/extraction/chart_extractor.py` | **Figure track** — pluggable line/scatter reader (vision backend; CV/LineFormer planned) |
| `scripts/analysis/build_structure_activity.py` | **Figure track** — chart points → structure–activity dataset |
| `scripts/extraction/extract_docling_v2.py` | **Evidence track** — section-aware prose extraction |
| `scripts/analysis/resolve_refs_openalex.py` | In-text citation → primary DOI resolver (provenance) |
| `scripts/search/semantic_scholar.py` | S2 wrapper (citations, references, recommendations) |
| `scripts/db/build_db.py` | JSONL → SQLite |

Design rationale: [notes/phase0-discovery-design-v1.md](notes/phase0-discovery-design-v1.md) ·
plan & positioning: [notes/project_plan_v1.md](notes/project_plan_v1.md).

---

## Quickstart

**Requirements:** Python 3.11+, macOS / Linux, an Anthropic API key.

```bash
git clone https://github.com/Aval0nT/catalitmine.git
cd catalitmine
bash setup_env.sh                       # creates venv, installs deps, fetches CDE2 models
cp .env.example .env                    # then edit .env, set ANTHROPIC_API_KEY
source venv/bin/activate
```

**Path 1 — discover & screen candidates from a research query (Phase 0):**

```bash
# Discover + rank candidates for a topic; produces a screening shortlist
python3 scripts/search/discover.py \
        --query "methanol to aromatics ZSM-5 Brønsted acidity" \
        --top-k 15 --depth 1 --min-relevance 0.6
# → data/04_search/shortlist_<slug>_<date>.md   (human-readable, relevance-ranked)
# → data/04_search/discover_<slug>_<date>.jsonl (machine-readable candidates)
```

Open the shortlist `.md`, skim abstracts + relevance scores, and **download the
PDFs you want by hand** into `topics/<topic>/pdfs/` (DOI-named). Manual download
is the intended workflow — catalysis papers are largely paywalled, and OA
direct-PDF coverage is low.

`fetch_oa.py` exists as a *best-effort* convenience for the minority of papers
with a direct OA PDF (MDPI, arXiv, ChemRxiv); it is not a primary path:

```bash
python3 scripts/search/fetch_oa.py \
        --input data/04_search/discover_<slug>_<date>.jsonl --topic mta --dry-run
```

**Path 2 — tables → per-catalyst records (LLM-free, the validated track):**

```bash
# PDFs already in topics/<topic>/pdfs/ (DOI-named; add <doi>_SI.pdf for SI)

# 1. Extract every table via Docling into db.table_rows (no API cost):
python3 scripts/extraction/ingest_tables.py --from-no-tables

# 2. Join each paper's tables on the catalyst label → per-catalyst records:
python3 scripts/analysis/build_catalyst_records.py
# → data/05_normalized/catalyst_records_<date>.jsonl

# 3. Density / joinability / correlation check:
python3 scripts/analysis/validate_data.py
# → outputs/reports/feature_matrix.csv
```

**Path 3 — prose evidence + citation-network provenance:**

```bash
python3 scripts/extraction/extract_docling_v2.py --doi 10.1016/j.apcatb.2021.120073 --topic mta
python3 scripts/analysis/resolve_refs_openalex.py --doi 10.1016/j.apcatb.2021.120073
python3 scripts/db/build_db.py
```

---

## Evidence unit schema (preview)

```json
{
  "source_review_doi": "10.xxxx/review-paper",
  "primary_paper_doi": "10.yyyy/primary-paper",
  "provenance_tier": "silver",
  "source_reference": "[12]",
  "source_citation_text": "Smith et al., J. Catal. 2018, 358, 234.",
  "section": "results",
  "claim_type": "performance",
  "catalyst_system": {
    "active_metal": "Zn",
    "support": "ZSM-5",
    "loading_wt_percent": 3.0,
    "si_al_ratio": 25
  },
  "conditions": {"T_C": 400, "P_bar": 1, "WHSV_h": 2.0},
  "performance": {"aromatic_selectivity_pct": 78, "methanol_conversion_pct": 99}
}
```

Full schema: [`schema/paper_record.schema.json`](schema/paper_record.schema.json).

---

## Positioning

This work is positioned against:

- **Paunović et al., Nat. Catal. (2026)** — 912-entry MTH database, manually
  curated over 30 years (van Bokhoven group, ETH/PSI). This pipeline is
  fully automated and extends to CO₂→aromatics, which their dataset does not
  cover. Citation-network provenance is also additional.

- **Dagdelen, Dunn et al., Nat. Commun. (2024)** — fine-tuned GPT-3 / Llama-2
  for structured-information extraction. Their case studies (dopant-host,
  MOFs, general composition) do not cover catalysis performance. This
  pipeline uses prompt-only Claude (no fine-tuning) and adds catalysis-
  specific schema + citation-network provenance.

- **Ren et al., JACS (2026)** — methodological template: 336 ML data points +
  24 wet-lab validation experiments → JACS. Phase 5 of this pipeline targets
  the same closure pattern for MTA / CO₂→aromatics.

Strategic detail: [notes/project_plan_v1.md](notes/project_plan_v1.md).

---

## Roadmap

- **Line/scatter CV reader** (next): a model-free reader for line and scatter
  plots — coloured-marker detection (OpenCV) with OCR-calibrated axes
  (Tesseract) — so figure digitisation becomes fully deterministic and API-free,
  matching the bar reader. A standalone, MMDetection-free LineFormer backend is
  parked on the `feat/lineformer-standalone` branch as a reproducible fallback
  for dense/crossing curves.
- **Phase 4**: feature matrix → XGBoost + SHAP for design rules;
  Gaussian-process regression for virtual screening of under-explored
  catalyst combinations.
- **Phase 5**: integration with a wet-lab validation loop (collaborator-
  dependent).
- **v2**: schema generalization — user-defined JSON schema + seed papers →
  auto-built domain-specific extractor.

---

## Citation

A methods paper is in preparation. If you use this pipeline before that
preprint is available, please cite this repository directly:

```
Piao, Y. catalitmine: Catalysis Literature Mining (2026).
https://github.com/Aval0nT/catalitmine
```

---

## Contact

Yuang Piao — Materials Chemistry and Catalysis (MCC) group, Utrecht University
`y.piao@uu.nl`

---

## License

MIT. See [LICENSE](LICENSE).
