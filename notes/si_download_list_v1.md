# Supporting-Information download list (v1)

*Generated 2026-06-03. Goal: recover catalyst performance + property tables that
are not in the main-text PDF, to grow structure–activity records.*

## How to use

1. Download the SI PDF for each DOI below.
2. Save it next to the main PDF in the same `topics/<topic>/pdfs/` folder,
   named `<doi_slug>_SI.pdf` (slug = DOI with `/` → `_`).
   Example: `10.1021_acscatal.5b00192_SI.pdf`
3. Re-run `python3 scripts/extraction/ingest_tables.py --from-no-tables`
   (and for papers that already had tables, pass the DOI explicitly).
   `ingest_tables.py` auto-detects `*_SI.pdf` and pulls its tables in.

**When you open the SI, check where the performance data lives:**
- **In a table** → great, ingestion will capture it.
- **Only in figures** (scatter/bar plots) → SI download will *not* help; that is a
  chart-digitisation job (Branch A), so just note it and skip.

---

## Tier A — highest ROI (property tables already extracted; performance completes the structure–activity join)

These papers already contributed textural / acidity / composition records. If
their performance is in an SI table, each catalyst becomes a full
structure–activity record immediately.

- [ ] `10.1016/j.jcat.2018.03.032` — High Zn/Al ratios, dehydrogenation vs H-transfer (J. Catal.) — 9 property tables already in DB
- [ ] `10.1016/j.ces.2023.118542` — hierarchical Zn/ZSM-5, balanced acidity (Chem. Eng. Sci.)
- [ ] `10.1039/d5ta01181g` — Zn/nano-H-ZSM-5 for MTA (J. Mater. Chem. A)
- [ ] `10.1016/j.mcat.2024.114687` — Ga species in Ga-ZSM-5, dehydrogenation (Mol. Catal.)
- [ ] `10.1016/j.mcat.2022.112702` — acid-modified ZSM-5, performance + coke (Mol. Catal.)
- [ ] `10.1021/acs.iecr.2c03873` — synergistic Brønsted / Al-Lewis / Zn-Lewis acid (I&ECR)

## Tier B — flagship performance papers with zero main-text tables (data likely in SI)

- [ ] `10.1021/acscatal.5b00192` — Increasing para-xylene selectivity from methanol (ACS Catal.)
- [ ] `10.1016/j.jechem.2025.08.080` — Long-lived metal-zeolite catalysts, polyolefin aromatization (J. Energy Chem.)

---

## Lower priority / skip

- **Mechanism & spectroscopy papers** (JACS 2024–2025 MTO/C–C-bond studies,
  jcat.2009 shape-selectivity, checat reviews): their value is the prose claims,
  already captured. SI unlikely to add catalyst comparison tables. Skip for now.
- **Kinetic-model / deactivation papers** (fuel lumped-kinetic, SAPO-34
  deactivation): performance often as time-on-stream curves (figures), not
  tables — chart digitisation, not SI.

*Full unfiltered candidate list can be regenerated from the database query in
the chat log if needed.*
