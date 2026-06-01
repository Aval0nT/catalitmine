# catalitmine — Catalysis Literature Mining

> A reproducible pipeline that turns catalysis PDFs into a queryable,
> provenance-tracked database of catalyst systems, reaction conditions, and
> performance evidence — without LLM fine-tuning.

**Domains:** methanol-to-aromatics (MTA), CO₂-to-aromatics. Generalization to
other catalysis reactions via schema customization is planned.

---

## What this does

Existing automated catalyst-data extraction either drops the link back to the
primary source (treating review-stated numbers as facts) or works only on a
single fixed schema. This pipeline:

1. parses PDFs section-aware via [Docling](https://github.com/DS4SD/docling)
   (Methods / Results / Discussion / Tables routed separately);
2. extracts catalyst-system, conditions, and performance evidence via
   Claude Haiku 4.5 (prompt-only, no fine-tuning);
3. resolves in-text citations (`[12]`, `[12,15]`, `[12-15]`, `Ref. 12`) to
   primary-paper DOIs via OpenAlex title search;
4. tags every evidence unit with a **provenance tier**:
   - **gold** — direct primary-paper extraction;
   - **silver** — review article, in-text citation resolved to primary DOI;
   - **bronze** — review article, no resolvable citation (treat as review
     synthesis, not a primary claim);
5. consolidates into SQLite (`db/catalysis.db`) for downstream analysis.

---

## Status

| Phase | Goal | State |
|---|---|---|
| 1 | PDF → evidence units (v2 pipeline) | ✅ Complete |
| 2 | Citation-network provenance | ✅ Complete |
| 3 | Corpus expansion (target ~200 papers) | 🟡 In progress (25 papers, 6,211 evidence units) |
| 4 | ML analysis: XGBoost+SHAP design rules; GP virtual screening | ⏳ Planned |
| 5 | Wet-lab validation loop | ⏳ Collaborator-dependent |

This is an active research codebase. Interfaces may change without notice.

---

## Architecture

Full directory layout: [STRUCTURE.md](STRUCTURE.md).
Active plan and venue strategy: [notes/project_plan_v1.md](notes/project_plan_v1.md).

```
topics/*/pdfs/                      ← input PDFs (DOI-named)
        │
        ▼  scripts/extraction/extract_docling_v2.py
data/03_evidence/<doi>.v2_evidence.jsonl
        │
        ▼  scripts/analysis/resolve_refs_openalex.py
data/03_evidence/<doi>.ref_resolved.json
        │   (auto-merged into evidence_units → primary_paper_doi)
        │
        ▼  scripts/db/build_db.py
db/catalysis.db                     ← papers · evidence_units · table_rows
        │
        ▼  scripts/analysis/*  +  scripts/ml/*
outputs/viz/ · outputs/reports/ · outputs/candidates/
```

### Key modules

| Path | Role |
|---|---|
| `scripts/extraction/extract_docling_v2.py` | v2 section-aware evidence extraction |
| `scripts/extraction/extract_tables_vision.py` | Table extraction (Docling TableFormer + Vision fallback) |
| `scripts/analysis/resolve_refs_openalex.py` | In-text citation → primary DOI resolver |
| `scripts/search/semantic_scholar.py` | Corpus expansion via S2 |
| `scripts/db/build_db.py` | Evidence JSONL → SQLite |
| `schema/paper_record.schema.json` | Evidence unit JSON schema |

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

**Run on a single paper:**

```bash
# 1. Drop a PDF into the topic folder, DOI-named:
cp my_paper.pdf topics/mta/pdfs/10.1016_j.apcatb.2021.120073.pdf

# 2. Extract evidence units:
python3 scripts/extraction/extract_docling_v2.py \
        --doi 10.1016/j.apcatb.2021.120073 \
        --topic mta

# 3. (For reviews) resolve in-text citations to primary DOIs:
python3 scripts/analysis/resolve_refs_openalex.py \
        --doi 10.1016/j.apcatb.2021.120073

# 4. Build the database:
python3 scripts/db/build_db.py
```

Outputs land in `data/03_evidence/` (per-paper JSONL) and `db/catalysis.db`.

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

- **Phase 4** (next): feature matrix → XGBoost + SHAP for design rules;
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

Yuang Piao — Utrecht University, de Jongh group
`y.piao@uu.nl`

---

## License

MIT. See [LICENSE](LICENSE).
