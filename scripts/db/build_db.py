"""
Build SQLite database from JSONL evidence files and table data.

Schema:
  papers         — source reviews (and primary papers once resolved)
  evidence_units — text-extracted claims/performance data
  table_rows     — vision-extracted table data

Usage:
  python3 scripts/db/build_db.py          # build/rebuild full DB
  python3 scripts/db/build_db.py --stats  # show DB stats only
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[2]
EVID_DIR = ROOT / "data" / "03_evidence"
DB_PATH  = ROOT / "db" / "catalysis.db"

# Source reviews metadata
REVIEWS = {
    "10.1038_s41929-018-0078-5": {
        "doi": "10.1038/s41929-018-0078-5",
        "title": "Methanol-to-hydrocarbons: catalytic materials and their behaviour",
        "first_author": "Yarulina",
        "year": 2018,
        "journal": "Nature Catalysis",
        "topic": "mta",
        "paper_type": "review",
    },
    "10.1007_s13203-016-0156-z": {
        "doi": "10.1007/s13203-016-0156-z",
        "title": "Coke formation on zeolite catalysts",
        "first_author": "Guisnet",
        "year": 2016,
        "journal": "ACS Catalysis",
        "topic": "mta",
        "paper_type": "review",
    },
    "10.1016_j.chempr.2021.02.024": {
        "doi": "10.1016/j.chempr.2021.02.024",
        "title": "CO2 hydrogenation to value-added products",
        "first_author": "Wang",
        "year": 2021,
        "journal": "Chem",
        "topic": "co2a",
        "paper_type": "review",
    },
    "10.1021_acs.chemrev.9b00723": {
        "doi": "10.1021/acs.chemrev.9b00723",
        "title": "CO2 hydrogenation to methanol",
        "first_author": "Zhong",
        "year": 2020,
        "journal": "Chemical Reviews",
        "topic": "co2a",
        "paper_type": "review",
    },
    "10.1016_j.apcatb.2021.120073": {
        "doi": "10.1016/j.apcatb.2021.120073",
        "title": "Higher alcohol synthesis via CO2 hydrogenation",
        "first_author": "Zhang",
        "year": 2021,
        "journal": "Applied Catalysis B",
        "topic": "co2a",
        "paper_type": "review",
    },
    "10.1021_acscatal.1c01422": {
        "doi": "10.1021/acscatal.1c01422",
        "title": "Aromatics Production via Methanol-Mediated Transformation Routes",
        "first_author": "Li",
        "year": 2021,
        "journal": "ACS Catalysis",
        "topic": "mta",
        "paper_type": "review",
    },
    # ── MTA primary papers ────────────────────────────────────────────────────
    "10.1002_cctc.201600650": {
        "doi": "10.1002/cctc.201600650",
        "title": "Suppression of the aromatic cycle in methanol-to-olefins reaction over ZSM-5 by post-synthetic modification",
        "first_author": "Yarulina",
        "year": 2016,
        "journal": "ChemCatChem",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2007.04.006": {
        "doi": "10.1016/j.jcat.2007.04.006",
        "title": "Conversion of methanol to hydrocarbons over zeolite H-ZSM-5: on the origin of the olefinic species",
        "first_author": "Bjørgen",
        "year": 2007,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2009.03.009": {
        "doi": "10.1016/j.jcat.2009.03.009",
        "title": "Product shape selectivity dominates the methanol-to-olefins (MTO) reaction over H-SAPO-34 catalysts",
        "first_author": "Hereijgers",
        "year": 2009,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2014.03.013": {
        "doi": "10.1016/j.jcat.2014.03.013",
        "title": "On the impact of co-feeding aromatics and olefins for the methanol-to-olefins reaction on HZSM-5",
        "first_author": "Sun",
        "year": 2014,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2014.06.017": {
        "doi": "10.1016/j.jcat.2014.06.017",
        "title": "On reaction pathways in the conversion of methanol to hydrocarbons on HZSM-5",
        "first_author": "Sun",
        "year": 2014,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2015.01.013": {
        "doi": "10.1016/j.jcat.2015.01.013",
        "title": "How zeolitic acid strength and composition alter the reactivity of alkenes and aromatics",
        "first_author": "Westgård Erichsen",
        "year": 2015,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2015.02.013": {
        "doi": "10.1016/j.jcat.2015.02.013",
        "title": "Coke formation and deactivation pathways on H-ZSM-5 in the conversion of methanol to olefins",
        "first_author": "Muller",
        "year": 2015,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1021_acscatal.6b01771": {
        "doi": "10.1021/acscatal.6b01771",
        "title": "Conversion of methanol to olefins over H-ZSM-5 zeolite: reaction pathway is related to the framework aluminum siting",
        "first_author": "Liang",
        "year": 2016,
        "journal": "ACS Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1021_cs300558x": {
        "doi": "10.1021/cs300558x",
        "title": "Effect of cage size on the selective conversion of methanol to light olefins",
        "first_author": "Bhawe",
        "year": 2012,
        "journal": "ACS Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    # ── New MTA papers ───────────────────────────────────────────────────────
    "10.1002_anie.201103657": {
        "doi": "10.1002/anie.201103657",
        "title": "Conversion of Methanol to Hydrocarbons: How Zeolite Cavity and Pore Size Controls Product Selectivity",
        "first_author": "Olsbye",
        "year": 2012,
        "journal": "Angewandte Chemie International Edition",
        "topic": "mta",
        "paper_type": "review",
    },
    "10.1016_j.catcom.2009.04.004": {
        "doi": "10.1016/j.catcom.2009.04.004",
        "title": "Methanol to propylene: Effect of phosphorus on a high silica HZSM-5 catalyst",
        "first_author": "Liu",
        "year": 2009,
        "journal": "Catalysis Communications",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1021_la0534367": {
        "doi": "10.1021/la0534367",
        "title": "Structural and Mechanistic Investigation of a Phosphate-Modified HZSM-5 Catalyst for Methanol Conversion",
        "first_author": "Abubakar",
        "year": 2006,
        "journal": "Langmuir",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2018.03.032": {
        "doi": "10.1016/j.jcat.2018.03.032",
        "title": "High Zn/Al ratios enhance dehydrogenation vs hydrogen transfer reactions of Zn-ZSM-5 catalytic systems in methanol-to-aromatics",
        "first_author": "Pinilla-Herrero",
        "year": 2018,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2012.03.016": {
        "doi": "10.1016/j.jcat.2012.03.016",
        "title": "Tuning the selectivity of methanol-to-hydrocarbons conversion on H-ZSM-5 by co-processing olefin or aromatic compounds",
        "first_author": "Ilias",
        "year": 2012,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1016_j.jcat.2013.03.021": {
        "doi": "10.1016/j.jcat.2013.03.021",
        "title": "A descriptor for the relative propagation of the aromatic- and olefin-based cycles in methanol-to-hydrocarbons conversion",
        "first_author": "Ilias",
        "year": 2013,
        "journal": "Journal of Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1021_acscatal.5b00192": {
        "doi": "10.1021/acscatal.5b00192",
        "title": "Increasing para-Xylene Selectivity in Making Aromatics from Methanol with a Surface-Modified Zn/P/ZSM-5 Catalyst",
        "first_author": "Zhang",
        "year": 2015,
        "journal": "ACS Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1021_acs.iecr.0c06342": {
        "doi": "10.1021/acs.iecr.0c06342",
        "title": "High-Efficiency Conversion of Methanol to BTX Aromatics Over a Zn-Modified Nanosheet-HZSM-5 Zeolite",
        "first_author": "Gong",
        "year": 2021,
        "journal": "Industrial & Engineering Chemistry Research",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1021_acscatal.8b03076": {
        "doi": "10.1021/acscatal.8b03076",
        "title": "A Mechanistic Study of Methanol-to-Aromatics Reaction over Ga-Modified ZSM-5 Zeolites",
        "first_author": "Gao",
        "year": 2018,
        "journal": "ACS Catalysis",
        "topic": "mta",
        "paper_type": "primary",
    },
    "10.1039_c9ra09657d": {
        "doi": "10.1039/c9ra09657d",
        "title": "Methanol to aromatics: isolated zinc phosphate groups on HZSM-5 zeolite enhance BTX selectivity and stability",
        "first_author": "Qiao",
        "year": 2020,
        "journal": "RSC Advances",
        "topic": "mta",
        "paper_type": "primary",
    },
    # ── PENDING batch (26 papers, added 2026-03-24) ──────────────────────────
    "10.1016_j.apcata.2024.119912": {
        "doi": "10.1016/j.apcata.2024.119912",
        "title": "γ-aminobutyric acid-assisted fabrication of plate-like ZSM-5 zeolite for efficient propylene production from methanol conversion",
        "first_author": "Dai", "year": 2024, "journal": "Applied Catalysis A: General",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.apcata.2024.120008": {
        "doi": "10.1016/j.apcata.2024.120008",
        "title": "Constructing hollow bivalve nanocomposite ZSM-5 with inverse Al zoned distribution to strengthen the stepwise conversion of methanol to aromatics",
        "first_author": "Guo", "year": 2025, "journal": "Applied Catalysis A: General",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.ces.2023.118542": {
        "doi": "10.1016/j.ces.2023.118542",
        "title": "Enhanced catalytic performance of hierarchical Zn/ZSM-5 with balanced acidities synthesized utilizing ZIF-14 as porogen and Zn source in methanol to aromatics",
        "first_author": "Liu", "year": 2023, "journal": "Chemical Engineering Science",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.checat.2022.05.012": {
        "doi": "10.1016/j.checat.2022.05.012",
        "title": "Recent progress on MTO reaction mechanisms and regulation of acid site distribution in the zeolite framework",
        "first_author": "Wang", "year": 2022, "journal": "Chem Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.checat.2023.100540": {
        "doi": "10.1016/j.checat.2023.100540",
        "title": "Influence of active-site proximity in zeolites on Brønsted acid-catalyzed reactions at the microscopic and mesoscopic levels",
        "first_author": "Li", "year": 2023, "journal": "Chem Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.fuel.2023.130704": {
        "doi": "10.1016/j.fuel.2023.130704",
        "title": "Dual-cycle-based lumped kinetic model for methanol-to-aromatics (MTA) reaction over H-ZSM-5 zeolites of different Si/Al ratio",
        "first_author": "Vicente", "year": 2024, "journal": "Fuel",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.fuel.2025.135207": {
        "doi": "10.1016/j.fuel.2025.135207",
        "title": "Investigation on deactivation periods of ZSM-5/SAPO-34 catalyst in MTA reaction: Carbon deposition behavior",
        "first_author": "Li", "year": 2025, "journal": "Fuel",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.jechem.2025.08.080": {
        "doi": "10.1016/j.jechem.2025.08.080",
        "title": "Long-lived metal-zeolite catalysts for polyolefin aromatization via synergistic tandem dehydroaromatization and hydrogenolysis",
        "first_author": "Chen", "year": 2026, "journal": "Journal of Energy Chemistry",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.mcat.2022.112702": {
        "doi": "10.1016/j.mcat.2022.112702",
        "title": "Effect of acid modification of ZSM-5 catalyst on performance and coke formation for methanol-to-hydrocarbon reaction",
        "first_author": "Park", "year": 2022, "journal": "Molecular Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.mcat.2024.114687": {
        "doi": "10.1016/j.mcat.2024.114687",
        "title": "Effect of different Ga species in Ga-ZSM-5 on dehydrogenation performance of cyclohexane to benzene",
        "first_author": "Mo", "year": 2025, "journal": "Molecular Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.micromeso.2022.112096": {
        "doi": "10.1016/j.micromeso.2022.112096",
        "title": "Hierarchical zeolites with high hydrothermal stability prepared via desilication of OSDA-occluded zeolites",
        "first_author": "Li", "year": 2022, "journal": "Microporous and Mesoporous Materials",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.micromeso.2023.112589": {
        "doi": "10.1016/j.micromeso.2023.112589",
        "title": "Efficient-selective-catalytic aromatization of methanol over Zn-HZSM-5/SAPO-34: Action mechanism of Zn",
        "first_author": "Meng", "year": 2023, "journal": "Microporous and Mesoporous Materials",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.mtchem.2025.103202": {
        "doi": "10.1016/j.mtchem.2025.103202",
        "title": "Effect of Brønsted acid over [GaO]+/HZSM-5 zeolite on cyclization and cracking reactions of long-chain olefins during methanol to aromatics",
        "first_author": "Li", "year": 2025, "journal": "Materials Today Chemistry",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_j.mtsust.2023.100364": {
        "doi": "10.1016/j.mtsust.2023.100364",
        "title": "Facile fabrication of a plate-like ZSM-5 zeolite as a highly efficient and stable catalyst for methanol to propylene conversion",
        "first_author": "Dai", "year": 2023, "journal": "Materials Today Sustainability",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1016_s1872-2067(22)64209-8": {
        "doi": "10.1016/s1872-2067(22)64209-8",
        "title": "Reaction mechanism of methanol-to-hydrocarbons conversion: Fundamental and application",
        "first_author": "Liu", "year": 2023, "journal": "Chinese Journal of Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_acs.iecr.2c03873": {
        "doi": "10.1021/acs.iecr.2c03873",
        "title": "Synergistic Catalysis of Brønsted Acid, Al-Lewis Acid, and Zn-Lewis Acid on Steam-Treated Zn/ZSM-5 for Highly Stable Conversion of Methanol to Aromatics",
        "first_author": "Fu", "year": 2023, "journal": "Industrial & Engineering Chemistry Research",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_acscatal.2c04600": {
        "doi": "10.1021/acscatal.2c04600",
        "title": "Evaluating the Role of Descriptor- and Spectator-Type Reaction Intermediates During the Early Phases of Zeolite Catalysis",
        "first_author": "Gong", "year": 2022, "journal": "ACS Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_acscatal.3c01332": {
        "doi": "10.1021/acscatal.3c01332",
        "title": "Relay and Feedback Conversion Effect of Hydrocarbons between ZSM-5 Grains on Product Selectivity and Coke Formation during Methanol Aromatization",
        "first_author": "Zhang", "year": 2023, "journal": "ACS Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_acscatal.3c01491": {
        "doi": "10.1021/acscatal.3c01491",
        "title": "Acetone–Butanol–Ethanol Catalytic Upgrading into Aromatics over Ga-Modified HZSM-5 Zeolites",
        "first_author": "Yan", "year": 2023, "journal": "ACS Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_acscatal.4c02625": {
        "doi": "10.1021/acscatal.4c02625",
        "title": "Structural Changes of ZSM-5 Catalysts during Methanol-to-Hydrocarbons Conversion Processes",
        "first_author": "Wang", "year": 2024, "journal": "ACS Catalysis",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_jacs.4c01155": {
        "doi": "10.1021/jacs.4c01155",
        "title": "Unraveling Spatially Dependent Hydrophilicity and Reactivity of Confined Carbocation Intermediates during Methanol Conversion over ZSM-5 Zeolite",
        "first_author": "Wang", "year": 2024, "journal": "Journal of the American Chemical Society",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_jacs.4c12145": {
        "doi": "10.1021/jacs.4c12145",
        "title": "Methanol to Olefins (MTO): Understanding and Regulating Dynamic Complex Catalysis",
        "first_author": "Lin", "year": 2025, "journal": "Journal of the American Chemical Society",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1021_jacs.5c06141": {
        "doi": "10.1021/jacs.5c06141",
        "title": "Formaldehyde-Mediated Initial Carbon–Carbon Bond Formation in Zeolite-Catalyzed Methanol-to-Hydrocarbon Conversion",
        "first_author": "Chen", "year": 2025, "journal": "Journal of the American Chemical Society",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1038_s41467-024-55514-1": {
        "doi": "10.1038/s41467-024-55514-1",
        "title": "Discovery of ketene/acetyl as a potential receptor for hydrogen-transfer reactions in zeolites",
        "first_author": "Guo", "year": 2025, "journal": "Nature Communications",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1039_d5ta01181g": {
        "doi": "10.1039/d5ta01181g",
        "title": "Crafting Zn/nano-H-ZSM-5 catalysts for methanol-to-aromatics conversion: tailoring crystal size and modifying surface electron density",
        "first_author": "Zhou", "year": 2025, "journal": "Journal of Materials Chemistry A",
        "topic": "mta", "paper_type": "primary",
    },
    "10.1039_d5ta07457f": {
        "doi": "10.1039/d5ta07457f",
        "title": "Investigation on the deactivation periods of ZSM-5/SAPO-34 catalysts in MTA reactions: an impact of product distribution",
        "first_author": "Li", "year": 2026, "journal": "Journal of Materials Chemistry A",
        "topic": "mta", "paper_type": "primary",
    },
}


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS papers (
        doi          TEXT PRIMARY KEY,
        title        TEXT,
        first_author TEXT,
        year         INTEGER,
        journal      TEXT,
        topic        TEXT,   -- 'mta', 'co2a', 'shared'
        paper_type   TEXT    -- 'review', 'primary'
    );

    CREATE TABLE IF NOT EXISTS evidence_units (
        evidence_id         TEXT PRIMARY KEY,
        source_review_doi   TEXT,
        primary_paper_doi   TEXT,   -- filled after OpenAlex resolution

        -- Catalyst identity (Pass 1)
        catalyst_system     TEXT,
        active_metal        TEXT,
        promoter            TEXT,
        support             TEXT,
        zeolite_type        TEXT,
        si_al_ratio         REAL,
        metal_loading_wt    REAL,
        morphology          TEXT,
        modification_method TEXT,
        preparation_method  TEXT,

        -- Performance (Pass 2)
        methanol_conv_pct   REAL,
        methanol_sel_pct    REAL,   -- methanol selectivity (CO2→MeOH papers); distinct from aromatic_sel_pct
        btx_sel_pct         REAL,
        aromatic_sel_pct    REAL,   -- total aromatics incl. C9+; broader than btx_sel_pct
        benzene_pct         REAL,
        toluene_pct         REAL,
        xylene_pct          REAL,
        c9plus_pct          REAL,
        ethylene_pct        REAL,
        propylene_pct       REAL,
        olefin_pct          REAL,
        paraffin_pct        REAL,
        btx_yield_pct       REAL,
        tos_h               REAL,
        lifetime_h          REAL,   -- total catalyst lifetime until deactivation
        conversion_drop_pct REAL,
        coke_content_wt     REAL,
        stability_note      TEXT,

        -- Conditions (Pass 3)
        temperature_c       REAL,
        pressure_mpa        REAL,
        whsv                REAL,
        ghsv                REAL,
        feed_methanol_conc  TEXT,

        -- Claim / Mechanism (Pass 3)
        claim_type          TEXT,
        claim_subject       TEXT,
        claim_predicate     TEXT,
        claim_object        TEXT,
        proposed_mechanism  TEXT,
        evidence_type       TEXT,
        confidence          TEXT,
        source_reference    TEXT,

        -- Provenance
        source_chunk_id     TEXT,
        source_page         INTEGER,
        source_section      TEXT,
        llm_model           TEXT,
        extra_json          TEXT    -- extra_fields as JSON blob
    );

    CREATE TABLE IF NOT EXISTS table_rows (
        row_id            TEXT PRIMARY KEY,
        source_review_doi TEXT,
        primary_paper_doi TEXT,
        table_number      TEXT,
        caption           TEXT,
        columns_json      TEXT,   -- JSON array of column names
        row_json          TEXT,   -- JSON array of cell values
        source_page       INTEGER,
        llm_model         TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_eu_review   ON evidence_units(source_review_doi);
    CREATE INDEX IF NOT EXISTS idx_eu_primary  ON evidence_units(primary_paper_doi);
    CREATE INDEX IF NOT EXISTS idx_eu_catalyst ON evidence_units(catalyst_system);
    CREATE INDEX IF NOT EXISTS idx_eu_zeolite  ON evidence_units(zeolite_type);
    CREATE INDEX IF NOT EXISTS idx_eu_claim    ON evidence_units(claim_type);
    CREATE INDEX IF NOT EXISTS idx_tr_review   ON table_rows(source_review_doi);
    """)
    conn.commit()


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").replace("wt%", "").strip())
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def import_papers(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO papers
           (doi, title, first_author, year, journal, topic, paper_type)
           VALUES (:doi,:title,:first_author,:year,:journal,:topic,:paper_type)""",
        REVIEWS.values(),
    )
    conn.commit()
    print(f"  papers: {len(REVIEWS)} reviews imported")


def import_evidence(conn: sqlite3.Connection) -> int:
    total = 0
    # Collect all evidence files:
    # Priority: .llm_evidence.filtered > .llm_evidence > .v2_evidence
    # v2_evidence is merged in only for slugs not already covered by llm_evidence
    seen_slugs: set[str] = set()
    evidence_files: list[tuple[Path, str]] = []
    for f in sorted(EVID_DIR.glob("*.llm_evidence.filtered.jsonl")):
        slug = f.name.replace(".llm_evidence.filtered.jsonl", "")
        seen_slugs.add(slug)
        evidence_files.append((f, slug))
    for f in sorted(EVID_DIR.glob("*.llm_evidence.jsonl")):
        slug = f.name.replace(".llm_evidence.jsonl", "")
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            evidence_files.append((f, slug))
    # v2_evidence: merge for all slugs (Docling table rows complement LLM rows)
    for f in sorted(EVID_DIR.glob("*.v2_evidence.jsonl")):
        slug = f.name.replace(".v2_evidence.jsonl", "")
        # Always include v2 — evidence_id namespacing prevents duplicates via INSERT OR REPLACE
        if f.stat().st_size > 2:   # skip empty files
            evidence_files.append((f, slug))

    for f, slug in sorted(evidence_files, key=lambda x: x[1]):
        meta = REVIEWS.get(slug, {})
        rows = []
        for line in f.read_text(encoding="utf-8").splitlines():
            u = json.loads(line)
            # review_doi: prefer unit's own field (v2), then REVIEWS dict, then slug
            review_doi = (u.get("source_review_doi")
                          or meta.get("doi")
                          or slug.replace("_", "/"))
            extra = u.get("extra_fields") or {}

            # temperature: schema uses temperature_c (lowercase); old JSONL may have
            # temperature_C or temperature_K in top-level or extra_fields
            temp_c = _safe_float(u.get("temperature_c") or u.get("temperature_C"))
            if temp_c is None:
                temp_k = _safe_float(
                    extra.get("temperature_K") or extra.get("temperature_k")
                    or extra.get("reaction_temperature_K") or extra.get("reaction_temp_K")
                )
                if temp_k and temp_k > 200:
                    temp_c = round(temp_k - 273.15, 1)

            # pressure: schema uses pressure_mpa (lowercase)
            pressure = _safe_float(u.get("pressure_mpa") or u.get("pressure_MPa")
                                   or extra.get("pressure_mpa") or extra.get("pressure_MPa"))

            # tos: tos_h is canonical; also accept time_on_stream_h and time_on_stream_min
            tos = _safe_float(u.get("tos_h") or extra.get("time_on_stream_h"))
            if tos is None:
                tos_min = _safe_float(extra.get("time_on_stream_min"))
                if tos_min is not None:
                    tos = round(tos_min / 60, 3)

            rows.append((
                u.get("evidence_id"),
                review_doi,
                None,  # primary_paper_doi — filled later
                u.get("catalyst_system"),
                u.get("active_metal"),
                u.get("promoter"),
                u.get("support"),
                u.get("zeolite_type"),
                _safe_float(u.get("si_al_ratio")),
                _safe_float(u.get("metal_loading_wt")),
                u.get("morphology"),
                u.get("modification_method"),
                u.get("preparation_method"),
                # Performance — handle both v1 and v2 field name variants
                _safe_float(u.get("methanol_conv_pct")         # v2
                            or u.get("methanol_conversion_pct") # v1
                            or extra.get("methanol_conversion_percent")),
                # methanol_sel_pct: for CO2→MeOH papers (Zhong 2020 ChemRev),
                # the LLM placed methanol selectivity into aromatic_sel_pct.
                # We rescue it here: if this is the Zhong 2020 review and the
                # unit has aromatic_sel_pct but no zeolite, treat it as methanol
                # selectivity and zero out aromatic_sel_pct below.
                _safe_float(u.get("methanol_sel_pct")
                            or extra.get("methanol_selectivity_pct")),
                _safe_float(u.get("btx_sel_pct")              # v2
                            or u.get("btx_selectivity_pct")),  # v1
                _safe_float(u.get("aromatic_sel_pct")
                            or extra.get("aromatics_pct")),
                _safe_float(u.get("benzene_pct")),
                _safe_float(u.get("toluene_pct")),
                _safe_float(u.get("xylene_pct")),
                _safe_float(u.get("c9plus_pct")),
                _safe_float(u.get("ethylene_pct")),
                _safe_float(u.get("propylene_pct")
                            or extra.get("propylene_selectivity_pct")),
                _safe_float(u.get("olefin_pct")),
                _safe_float(u.get("paraffin_pct")),
                _safe_float(u.get("btx_yield_pct")),
                tos,
                _safe_float(u.get("lifetime_h")),
                _safe_float(u.get("conversion_drop_pct")),
                _safe_float(u.get("coke_content_wt")),
                u.get("stability_note"),
                # Conditions
                temp_c,
                pressure,
                _safe_float(u.get("whsv")),
                _safe_float(u.get("ghsv")),
                u.get("feed_methanol_conc"),
                u.get("claim_type"),
                u.get("claim_subject"),
                u.get("claim_predicate"),
                u.get("claim_object"),
                u.get("proposed_mechanism"),
                u.get("evidence_type"),
                u.get("confidence"),
                u.get("source_reference"),
                u.get("source_chunk_id"),
                _safe_int(u.get("source_page")),
                u.get("source_section"),
                u.get("llm_model"),
                json.dumps(extra, ensure_ascii=False) if extra else None,
            ))
        conn.executemany("""INSERT OR REPLACE INTO evidence_units VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )""", rows)
        conn.commit()
        total += len(rows)
        print(f"  {slug}: {len(rows)} units")
    return total


def import_tables(conn: sqlite3.Connection) -> int:
    total = 0
    for f in sorted(EVID_DIR.glob("*.tables.jsonl")):
        slug = f.name.replace(".tables.jsonl", "")
        meta = REVIEWS.get(slug, {})
        review_doi = meta.get("doi", slug.replace("_", "/"))
        rows = []
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            t = json.loads(line)
            cols = t.get("columns", [])
            for j, row in enumerate(t.get("rows", [])):
                row_id = f"{slug}::tbl{t.get('table_number','?')}::r{j+1:03d}"
                rows.append((
                    row_id,
                    review_doi,
                    None,
                    str(t.get("table_number", "")),
                    t.get("caption", ""),
                    json.dumps(cols, ensure_ascii=False),
                    json.dumps(row, ensure_ascii=False),
                    _safe_int(t.get("source_page")),
                    t.get("llm_model"),
                ))
        conn.executemany("""INSERT OR REPLACE INTO table_rows VALUES (
            ?,?,?,?,?,?,?,?,?
        )""", rows)
        conn.commit()
        total += len(rows)
        print(f"  {slug}: {len(rows)} table rows")
    return total


def _extract_ref_number(source_ref: str):
    """Extract numeric ref ID from strings like 'Ref. [59]', '[59]', '59'."""
    if not source_ref:
        return None
    m = re.search(r'\[(\d{1,3})\]', source_ref)
    if m: return m.group(1)
    m = re.search(r'\((\d{1,3})\)', source_ref)
    if m: return m.group(1)
    m = re.search(r'ref\.?\s*(\d{1,3})', source_ref, re.I)
    if m: return m.group(1)
    m = re.match(r'^(\d{1,3})$', source_ref.strip())
    if m: return m.group(1)
    return None


def fill_primary_paper_doi(conn: sqlite3.Connection) -> None:
    """
    For each evidence unit with a source_reference, look up the resolved DOI
    from <doi_slug>.ref_resolved.json and write it to primary_paper_doi.
    Only updates rows where primary_paper_doi is currently NULL.
    Only uses high-confidence hits (score >= 0.7).
    """
    updated = 0
    skipped_low = 0

    for ref_file in sorted(EVID_DIR.glob("*.ref_resolved.json")):
        slug = ref_file.name.replace(".ref_resolved.json", "")
        review_doi = slug.replace("_", "/", 1)  # first underscore only for protocol
        # Reconstruct the review DOI from the slug (underscores → slashes except first two)
        # Actually the slug uses underscores for all slashes in the DOI
        review_doi = slug.replace("_", "/")
        # But that over-converts: 10.1038/s41929-018-0078-5 → correct
        # For slugs like 10.1016_j.apcatb.2021.120073 we need 10.1016/j.apcatb.2021.120073
        # The convention is: first underscore after the prefix is the DOI slash separator
        # Simple approach: replace underscores that follow digits or letters with /
        # Actually stored review_doi in REVIEWS dict — use that if available
        meta = REVIEWS.get(slug, {})
        review_doi = meta.get("doi", slug.replace("_", "/"))

        resolved: dict = json.loads(ref_file.read_text(encoding="utf-8"))

        # Build ref_num → doi map (high confidence only)
        ref_to_doi = {}
        for ref_num, info in resolved.items():
            if info.get("doi") and info.get("score", 0) >= 0.7:
                ref_to_doi[ref_num] = info["doi"]

        if not ref_to_doi:
            continue

        # Fetch evidence units from this review that have a source_reference and no primary_paper_doi
        rows = conn.execute(
            "SELECT evidence_id, source_reference FROM evidence_units "
            "WHERE source_review_doi = ? AND source_reference IS NOT NULL AND primary_paper_doi IS NULL",
            (review_doi,)
        ).fetchall()

        for ev_id, source_ref in rows:
            ref_num = _extract_ref_number(source_ref)
            if ref_num and ref_num in ref_to_doi:
                conn.execute(
                    "UPDATE evidence_units SET primary_paper_doi = ? WHERE evidence_id = ?",
                    (ref_to_doi[ref_num], ev_id)
                )
                updated += 1
            elif ref_num and ref_num in {k for k, v in resolved.items() if v.get("doi")}:
                skipped_low += 1  # found but score < 0.7

    conn.commit()
    print(f"  primary_paper_doi filled: {updated} rows updated, {skipped_low} skipped (low confidence)")


def print_stats(conn: sqlite3.Connection) -> None:
    print("\n=== Database Stats ===")
    for table in ["papers", "evidence_units", "table_rows"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<20}: {n:,}")

    print("\nEvidence units by topic:")
    rows = conn.execute("""
        SELECT p.topic, COUNT(*) as n
        FROM evidence_units e
        JOIN papers p ON e.source_review_doi = p.doi
        GROUP BY p.topic ORDER BY n DESC
    """).fetchall()
    for topic, n in rows:
        print(f"  {topic or 'unknown':<10}: {n:,}")

    print("\nField fill rates (evidence_units, non-null):")
    fields = [
        "catalyst_system","zeolite_type","active_metal",
        "methanol_conv_pct","btx_sel_pct","aromatic_sel_pct",
        "ethylene_pct","propylene_pct","olefin_pct",
        "tos_h","lifetime_h","conversion_drop_pct","coke_content_wt",
        "temperature_c","pressure_mpa","whsv","ghsv",
        "claim_type","source_reference",
    ]
    total = conn.execute("SELECT COUNT(*) FROM evidence_units").fetchone()[0]
    for f in fields:
        n = conn.execute(f"SELECT COUNT(*) FROM evidence_units WHERE {f} IS NOT NULL").fetchone()[0]
        bar = "#" * int(n/total*20)
        print(f"  {f:<25}: {n:4d}/{total} ({n/total*100:4.1f}%)  {bar}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build catalysis SQLite database")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if args.stats:
        if not DB_PATH.exists():
            print("Database not found. Run without --stats first.")
            return
        with sqlite3.connect(DB_PATH) as conn:
            print_stats(conn)
        return

    # Rebuild
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Deleted existing: {DB_PATH.name}")

    with sqlite3.connect(DB_PATH) as conn:
        create_schema(conn)
        print("Schema created.\n")

        print("Importing papers...")
        import_papers(conn)

        print("\nImporting evidence units...")
        n_ev = import_evidence(conn)

        # ── Migrate Zhong 2020 ChemRev methanol selectivity ───────────────────
        # Zhong 2020 (CO2→MeOH review) Table 2 column "selec/C-mol%" is
        # methanol selectivity, not aromatic selectivity. The LLM stored these
        # values in aromatic_sel_pct. Move them to methanol_sel_pct and clear
        # aromatic_sel_pct for rows from that source that have no zeolite.
        cur = conn.execute("""
            UPDATE evidence_units
            SET    methanol_sel_pct = aromatic_sel_pct,
                   aromatic_sel_pct = NULL
            WHERE  source_review_doi = '10.1021/acs.chemrev.9b00723'
              AND  aromatic_sel_pct IS NOT NULL
              AND  (zeolite_type IS NULL OR zeolite_type = '')
        """)
        conn.commit()
        print(f"  Zhong 2020 migration: {cur.rowcount} rows moved aromatic_sel_pct → methanol_sel_pct")

        print("\nImporting table rows...")
        n_tr = import_tables(conn)

        print("\nFilling primary_paper_doi from ref resolution...")
        fill_primary_paper_doi(conn)

        print(f"\nTotal: {n_ev} evidence units, {n_tr} table rows")
        print_stats(conn)

    print(f"\nDatabase saved: {DB_PATH}")


if __name__ == "__main__":
    main()
