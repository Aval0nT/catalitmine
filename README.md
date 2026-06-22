# catalitmine — Catalysis Literature Mining

<p align="center"><b>Papers in, catalyst data out — every number traceable to its source.</b></p>

<p align="center">
  <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="Corpus" src="https://img.shields.io/badge/corpus-51_papers_%C2%B7_726_records-6f42c1">
  <img alt="Table track: LLM-free" src="https://img.shields.io/badge/table_track-LLM--free-2E8B57">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-97CA00">
</p>
<p align="center">
  <a href="scripts/extraction/lineformer_port/"><img alt="LineFormer port" src="https://img.shields.io/badge/LineFormer_port-Apple_Silicon_%C2%B7_CPU_%3C1s%2Ffig-FF6F00?logo=apple&logoColor=white"></a>
  <a href="https://github.com/TheJaeLal/LineFormer"><img alt="Based on LineFormer" src="https://img.shields.io/badge/based_on-LineFormer_(ICDAR_2023)-E36209"></a>
  <img alt="Status" src="https://img.shields.io/badge/status-active_research-dfb317">
</p>

> A reproducible, **fine-tuning-free** pipeline that turns a research query into
> a structured, provenance-tracked database of catalysts, reaction conditions,
> and performance — end to end, automatically.

**Domains:** methanol-to-aromatics (MTA) and CO₂-to-aromatics; the schema is
designed to generalize to other catalysis reactions.

---

## Highlights

- **End-to-end** — research query → ranked literature → tables → **726
  per-catalyst records** from 51 papers → analysis.
- **Right tool per task, not LLM-everywhere** — the table track makes zero API
  calls and is ≈6× more complete than prose extraction; figure *typing* uses a
  zero-shot vision model (~$1–2 for the whole corpus); geometry is read by
  specialist models; every value is gated by a human.
- **Provenance by construction** — every record traces to its primary source
  (gold / silver / bronze tiers).
- **Validated, not merely built** — textbook kinetics fall out of the
  auto-extracted numbers ([Validation](#validation)).
- **Figures → data, by the right extractor** — a vision model types each
  figure, then specialist tools digitise it: a LineFormer port (Apple-Silicon
  CPU, ~0.7 s/figure) for line panels, a CV reader for bars, MarkerFormer
  (planned) for scatter; a human gate guards everything entering the database.

### In detail

**Table-centric structured data, no LLM.** Catalysis tables are catalyst-keyed
property sheets; joining a paper's textural / acidity / composition /
performance tables on the catalyst column reconstructs a dense per-catalyst
record even when no single table holds everything — 726 records across 51
papers, roughly sixfold more complete than sentence-level prose extraction
yielded from the same corpus. **318 records already support
condition–performance analysis.**

**Figures → data — a typed, routed pipeline.** Each figure is first *typed* by
a zero-shot vision model (Claude Haiku): chart vs reaction scheme vs spectrum
vs micrograph, the per-panel geometry (line / scatter / bar), and whether it
plots catalytic performance. On a hand-labelled validation set the vision
typing scored 12/12 — correcting exactly the cases a caption-keyword classifier
mishandles (an FT-IR figure whose caption merely says "conversion", a reaction
scheme, a bar chart). A **caption-driven triage** then selects the ~20–40
figures that would actually JOIN against existing property records into
structure–activity records, so the human gate is spent where it pays. The
selected figures route by geometry: bar panels to a pixel-level CV reader
(validated to ≤0.5 % on tall segments, ±2–4 % on small), line panels to the
LineFormer port below, and disconnected-marker **scatter** — LineFormer's blind
spot — to MarkerFormer (planned). Geometry models return pixel traces only;
turning pixels into values (axis calibration, legend = catalyst identity) is a
separate semantic layer (OCR + vision model + human). End-to-end automatic
accuracy on arbitrary journal styles is not yet data-grade, so the design is
**auto first-pass + human gate**: a verification page re-plots every extraction
beside the original, and only human-accepted data enters the database.

**LineFormer without MMDetection, CUDA, or cloud.** The strongest published
line-chart extractor ([LineFormer](https://github.com/TheJaeLal/LineFormer),
Lal et al., ICDAR 2023) ships pinned to a frozen stack (mmcv-full 1.x,
Python ≤3.10, CUDA containers) that no longer builds on current Python or on
macOS-arm64. We mapped its trained Mask2Former checkpoint tensor-by-tensor
onto Hugging Face `transformers`
([scripts/extraction/lineformer_port/](scripts/extraction/lineformer_port/))
and reimplemented the mask→trace post-processing in plain numpy/scipy.
Equivalence is measured, not assumed: across a 30-figure probe set, **125 of
129 extracted line traces are bit-identical** to the original CUDA stack
(worst remaining deviation: 0.45 px mean). Inference runs on an M-series
MacBook at **~0.7 s per figure on CPU alone** (MPS verified, identical
output) — and it reads grayscale, black, and crossing curves exactly where
colour-based CV is blind.

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
3. **Figure track** — a vision model types each figure and reads its per-panel
   geometry; a caption-driven triage selects the figures that close
   structure–activity records; then panels route by type — bar charts to a
   deterministic CV reader, line panels to the HF-ported LineFormer
   (colour-independent instance segmentation, local CPU), scatter to
   MarkerFormer (planned). A semantic layer (axes + legend names) and a human
   gate turn pixel traces into accepted data. Output feeds the
   structure–activity set.
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
| 3 | Corpus: 51 papers · 726 per-catalyst records · 7,491 prose evidence units | 🟡 Expanding (target ~200) |
| 4 | ML analysis: condition–performance → structure–activity (XGBoost/SHAP, GP screening) | 🟡 Data validated; modelling next |
| 5 | Wet-lab validation loop | ⏳ Collaborator-dependent |

This is an active, single-author research codebase. Interfaces may change.

**Data usability — verified.** 726 per-catalyst records; 408 carry a
performance metric, 120 a structural/textural/acidity property; 318 support
condition–performance analysis today. Structure–activity records (catalyst with
both performance *and* property) currently number 59 — 38 of them fully numeric
in the feature matrix — and are being grown via Supporting-Information tables,
figure digitisation, and corpus expansion.

**Figure inventory.** A caption-based scan of all 51 papers (no API) finds
48 with activity figures — ~150 line/scatter and ~43 bar charts — versus the
characterization figures (XRD/TPD/IR) that are correctly gated out. Bar charts
already digitise deterministically; line/scatter traces extract via the
LineFormer port (see Highlights) — axis calibration and series naming stay
with the human gate.

---

## Validation

A go/no-go check (`scripts/analysis/validate_data.py`) builds a numeric feature
matrix from the table-derived records and tests for signal. Without any curation
beyond unit coalescing, established catalysis relationships emerge:

| Relationship | *r* | *n* | Reading |
|---|---|---|---|
| GHSV ↑ → CO₂ conversion ↓ | −0.43 | 151 | shorter contact time lowers conversion |
| Temperature ↑ → CO₂ conversion ↑ | +0.41 | 271 | kinetic temperature dependence |
| BET area ↑ → Brønsted-acid density ↑ | +0.60 | 35 | more accessible framework acid sites |
| Benzene fraction ↑ ↔ toluene fraction ↑ | +0.98 | 15 | co-produced aromatics move together — an internal-consistency check |

(Space-time yield is deliberately absent: STY units are not yet normalised
across papers, and a correlation over mixed units would not be meaningful.)

That textbook kinetics fall out of automatically extracted numbers is the
clearest evidence the extraction is faithful. Early structure–activity signals
are also emerging (BET area × aromatics fraction *r* = +0.80, *n* = 20;
Lewis-acid density × aromatics fraction *r* = +0.86, *n* = 16) but stay out of
the headline until the records grow enough to stratify them properly.

**Methodological honesty.** Raw correlations across a pooled corpus can mislead:
the dataset mixes two reactions (MTA and CO₂→aromatics), so conversions and
selectivities are never merged across them, and a pressure × conversion trend
(*r* = −0.30) is a mixed-population (Simpson) artifact — notably weakened from
−0.58 by a unit- and label-correctness audit of the extraction code, which is
itself evidence the artifact is data noise rather than chemistry. Quantitative
modelling therefore proceeds stratified by reaction and catalyst family — which
is also why structure–activity records are being grown before any model is
reported.

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

The **table track** above supplies the *structure* half of every
structure–activity record (BET, Si/Al, acidity, pore — the catalyst's
properties). The *activity* half — conversion/selectivity/yield read off the
plots — comes from the **figure track**, which joins back onto the same
catalyst records:

```
figure crops + captions          scripts/extraction/extract_figures.py
      │  scripts/extraction/vlm_classify.py
      ▼   ── VLM types each figure + per-panel geometry; drops schemes/spectra
typed figures
      │  scripts/analysis/triage_figures.py
      ▼   ── which figures JOIN existing property records → the ~20–40 worth digitising
selected figures, routed by geometry:
      ├─▶ bar_reader.py              bar panels      (CV, validated ≤0.5 %)   ─┐
      ├─▶ lineformer_port/           line panels     (HF port, local CPU)      ├─▶ PIXEL traces
      └─▶ MarkerFormer (planned)     scatter panels  (LineFormer's blind spot)─┘        │
                                                                                         ▼
      ★ SEMANTIC LAYER — the critical, still-being-built step ★
        axis calibration (OCR + click two ticks) + legend = catalyst identity (VLM-prefilled)
        via a click-to-calibrate verification page = the HUMAN GATE
      └── turns pixel traces into real values, then JOINs the catalyst's properties ──┐
                                                                                       ▼
                                          structure–activity records  (data/05 + db)
```

> **Why the semantic layer is the bottleneck, not another model.** The geometry
> models (LineFormer, bar_reader, MarkerFormer) only ever return *pixel*
> traces — `x = 137 px, y = 204 px`. Turning those into `TOS = 10 h,
> conversion = 95 %` needs axis calibration and series → catalyst-name mapping;
> no geometry model does this. It is OCR + a vision model + two human clicks
> per axis, and it is what stands between "traces extracted" and "data in the
> database." Building it (a click-to-calibrate page that doubles as the human
> gate and emits training-grade ground truth) is the figure track's current
> priority — ahead of any new extractor.

### Key modules

| Path | Role |
|---|---|
| `scripts/search/discover.py` | **Phase 0** — query → relevance-ranked shortlist (OpenAlex + S2 citation network + Claude scoring) |
| `scripts/extraction/parse_pdfs.py` | **Parse once** — parallel Docling parse of the corpus; all extractors read the cache (`docling_cache.py`) |
| `scripts/extraction/ingest_tables.py` | **Table track** — tables → `db.table_rows` (LLM-free); cache-fed; auto-detects SI PDFs |
| `scripts/analysis/build_catalyst_records.py` | **Table track** — join a paper's tables on the catalyst label → per-catalyst records |
| `schema/table_attribute_keywords.json` | Maintainable header→attribute keyword library |
| `scripts/analysis/validate_data.py` | Density / joinability / correlation go-no-go check |
| `scripts/extraction/extract_figures.py` | **Figure track** — Docling figure crops + captions |
| `scripts/extraction/vlm_classify.py` | **Figure track** — VLM figure typing (kind + per-panel geometry + is-performance); zero-shot Haiku, ~$1–2/corpus |
| `scripts/analysis/triage_figures.py` | **Figure track** — selects the figures that JOIN existing property records into structure–activity records |
| `scripts/extraction/bar_reader.py` | **Figure track** — deterministic CV reader for bar charts (no model) |
| `scripts/extraction/lineformer_port/` | **Figure track** — LineFormer ported to HF `transformers` (line panels, local CPU); converter + inference + parity checks |
| `scripts/extraction/line_reader.py` | **Figure track** — deterministic colour-clustering line/scatter reader (no model; pre-LineFormer fallback) |
| `scripts/extraction/chart_extractor.py` | **Figure track** — pluggable geometry-backend interface (vision, cv-line, lineformer) |
| _semantic layer / click-to-calibrate_ | **Figure track — planned, the current priority** — pixel traces → real values (axis calibration + legend = catalyst), doubling as the human gate |
| `scripts/analysis/build_structure_activity.py` | **Figure track** — calibrated chart points → structure–activity dataset |
| `scripts/extraction/extract_docling_v2.py` | **Evidence track** — section-aware prose extraction |
| `scripts/analysis/resolve_refs_openalex.py` | In-text citation → primary DOI resolver (provenance) |
| `scripts/search/semantic_scholar.py` | S2 wrapper (citations, references, recommendations) |
| `scripts/db/build_db.py` | JSONL → SQLite |

Design rationale: [notes/phase0-discovery-design-v1.md](notes/phase0-discovery-design-v1.md) ·
plan & positioning: [notes/project_plan_v1.md](notes/project_plan_v1.md).

---

## Quickstart

**Requirements:** Python 3.10+, macOS / Linux. An Anthropic API key is needed
only for the LLM steps (Phase 0 relevance scoring, prose evidence, vision
charts) — the table track runs without one.

```bash
git clone https://github.com/Aval0nT/catalitmine.git
cd catalitmine
bash setup_env.sh                       # venv + core deps (--with-cde2 adds the legacy evidence-track stack)
cp .env.example .env                    # then edit .env, set ANTHROPIC_API_KEY (LLM steps only)
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

# 0. (recommended for many PDFs) one-time PARALLEL Docling parse. Each PDF is
#    parsed exactly once into data/00_parsed/ + figure crops; every later
#    stage (tables, figures, prose) reads that cache in seconds:
python3 scripts/extraction/parse_pdfs.py --from-pdfs --workers 6

# 1. Extract every table into db.table_rows (no API cost). Reads the parse
#    cache when present, runs Docling itself when not. --from-pdfs ingests
#    every DOI-named PDF it finds and bootstraps the DB, so this is the entry
#    point on a fresh clone:
python3 scripts/extraction/ingest_tables.py --from-pdfs

# 2. Join each paper's tables on the catalyst label → per-catalyst records:
python3 scripts/analysis/build_catalyst_records.py
# → data/05_normalized/catalyst_records_<date>.jsonl

# 3. Density / joinability / correlation check:
python3 scripts/analysis/validate_data.py
# → outputs/reports/feature_matrix.csv
```

**Path 3 — prose evidence + citation-network provenance**
(needs `ANTHROPIC_API_KEY`; add `--no-llm` to run only the table + regex parts):

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

The maintainable header→attribute library that drives the table track:
[`schema/table_attribute_keywords.json`](schema/table_attribute_keywords.json).
Paper-screening template: [`schema/paper_record.schema.json`](schema/paper_record.schema.json).

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

- **Figure track — typed → triaged → routed → gated** (live tracker & decision
  log: [notes/figure_track_todo.md](notes/figure_track_todo.md)). Built and
  verified: vision-model figure typing (12/12 on a hand-labelled set);
  caption-driven triage onto existing DB property records; a validated bar
  reader; and a [LineFormer](https://github.com/TheJaeLal/LineFormer) port
  (Lal et al., ICDAR 2023) — instance segmentation that is colour-independent
  where colour-based CV is blind, ported from MMDetection to plain HF
  `transformers`, running locally on Apple-Silicon CPU with coordinate parity
  verified against the original stack. **Remaining**, in order:
  - **MarkerFormer** — a marker-detection model for disconnected-marker scatter
    (LineFormer's blind spot). A visual census found 10 such scatter plots in
    the high-value pool, 5 of them tier-A structure–activity correlation plots
    (property-on-x, activity-on-y) — the project's most valuable figure type.
    Recipe: synthetic journal-style scatter generator → small detector
    (YOLO/DETR) → fine-tune on the human-gate gold set. ~2–4 weeks, GPU-hours
    not tokens.
  - **Panel-crop routing** — split composites into single panels before the
    geometry models (composites lose ≈0.3 coverage at 512 px), using the
    caption / vision panel inventory as a prior.
  - **Semantic layer** — a click-to-calibrate verification UI (click two ticks
    per axis, confirm vision-prefilled catalyst names); every corrected figure
    becomes ground truth for training and evaluation.

  For a dataset, precision of accepted data is what matters; automation only
  sets the human cost per figure. Design rationale:
  [notes/figure_reader_design.md](notes/figure_reader_design.md).
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
