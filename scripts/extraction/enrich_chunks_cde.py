"""
Stage B.5 — Regex Entity Enrichment

Takes high-value chunk JSONL produced by select_high_value_chunks.py and
adds catalyst token hints + quantity/unit extractions using regex only.

CDE2 (ChemDataExtractor) has been removed from this stage. The LLM in
Stage D (extract_llm_evidence.py) handles full entity recognition, making
CDE2 redundant for this pipeline scale.

Output JSONL adds these fields to each chunk:
  cde_cems       : catalyst-looking tokens from regex heuristics
  cde_quantities : list of {value, unit, quantity_type} dicts
  cde_cem_count  : integer count
  cde_version    : "regex_only"

Usage:
  python3 enrich_chunks_cde.py [--doi DOI] [--all]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]  # .../Science
CHUNKS_DIR = ROOT / "data" / "01_chunks"
OUT_DIR    = ROOT / "data" / "02_enriched"

PILOT_DOI = "10.1016_j.apcatb.2021.120073"

# ---------------------------------------------------------------------------
# Quantity patterns (fallback if CDE2 is unavailable)
# ---------------------------------------------------------------------------
# These are used when CDE2 cannot be imported, so the script degrades
# gracefully to regex-only enrichment.

_QUANTITY_RE = re.compile(
    r"""
    (?P<value>-?\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?)   # value or range
    \s*
    (?P<unit>
        %                         |
        °\s*C                     |
        K\b                       |
        MPa                       |
        bar\b                     |
        atm\b                     |
        mL\s*g?[-\s]?1|mL/g      |
        mmol\s*g[-\s]?1|mmol/g   |
        h[-\s]?1|h\^[-\s]?1|/h   |
        cm3\s*g[-\s]?1            |
        mol\s*%                   |
        wt\s*%                    |
        vol\s*%                   |
        ppm                       |
        nm\b                      |
        m2\s*g[-\s]?1             |
        μmol\s*g[-\s]?1
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_UNIT_TYPE_MAP = {
    "%":    "percentage",
    "°c":   "temperature",
    "k":    "temperature",
    "mpa":  "pressure",
    "bar":  "pressure",
    "atm":  "pressure",
    "wt %": "weight_fraction",
    "mol %":"mole_fraction",
    "vol %":"volume_fraction",
    "nm":   "particle_size",
    "h":    "rate_or_time",
    "ppm":  "concentration",
}


def _guess_unit_type(unit_raw: str) -> str:
    key = unit_raw.strip().lower().replace(" ", "")
    for k, v in _UNIT_TYPE_MAP.items():
        if key.startswith(k.replace(" ", "")):
            return v
    if re.search(r"m2|m²", key):
        return "surface_area"
    if re.search(r"mmol|μmol|mol", key):
        return "amount"
    if re.search(r"ml|cm3", key):
        return "volume_or_yield"
    return "unknown"


def extract_quantities_regex(text: str) -> List[Dict[str, str]]:
    """Fallback: extract value+unit pairs with regex."""
    results = []
    for m in _QUANTITY_RE.finditer(text):
        unit_raw = m.group("unit").strip()
        results.append(
            {
                "value": m.group("value").strip(),
                "unit": unit_raw,
                "quantity_type": _guess_unit_type(unit_raw),
                "source": "regex",
            }
        )
    return results


# ---------------------------------------------------------------------------
# CDE2 helpers
# ---------------------------------------------------------------------------

def enrich_chunk_regex_only(text: str) -> tuple[List[str], List[Dict]]:
    """Regex-only enrichment: quantities extraction."""
    quantities = extract_quantities_regex(text)
    return [], quantities


# ---------------------------------------------------------------------------
# Catalyst component heuristics (domain-specific post-processing)
# ---------------------------------------------------------------------------

# Pattern: recognise tokens that look like catalyst formulae
# e.g. Cu/ZnO, Fe2O3, Rh-SiO2, K-Co3O4/Al2O3
_CATALYST_TOKEN_RE = re.compile(
    r"""
    (?:
        [A-Z][a-z]?                          # element symbol
        (?:\d+)?                             # optional stoichiometry
        (?:O\d*|S\d*|N\d*|C\b|P\b)?         # common anion
    )
    (?:
        [-/]                                 # separator
        [A-Z][a-z]?(?:\d+)?(?:O\d*|S\d*)?
    )*
    """,
    re.VERBOSE,
)

_COMMON_NON_CHEM = {
    "CO2", "H2", "CO", "N2", "O2", "H2O", "He", "Ar", "CH4",
    "In", "At", "No", "As", "Is", "Be", "Can", "Do",
}


def _filter_catalyst_tokens(text: str) -> List[str]:
    """
    Lightweight heuristic to pull catalyst-looking tokens from text.
    Used to supplement CDE2 CEMs.
    """
    tokens = set()
    # Pattern: word before "/" is often an active metal, after is support
    slash_pattern = re.compile(
        r'\b([A-Z][a-z]?(?:[-–][A-Z][a-z]?)*(?:\d+[A-Z][a-z]*\d*)?)/([A-Za-z0-9]+)\b'
    )
    for m in slash_pattern.finditer(text):
        full = m.group(0)
        if len(full) >= 4 and full not in _COMMON_NON_CHEM:
            tokens.add(full)

    # Pattern: element symbol sequence like CuZnFe, NaCo, FeCo
    elem_seq = re.compile(r'\b(?:[A-Z][a-z]?)+\b')
    for m in elem_seq.finditer(text):
        tok = m.group(0)
        if (
            2 <= len(tok) <= 20
            and tok not in _COMMON_NON_CHEM
            and re.match(r'^([A-Z][a-z]?)+$', tok)
            and len(tok) > 2  # skip bare single-element like "Cu" which are too noisy
        ):
            tokens.add(tok)

    return sorted(tokens)


# ---------------------------------------------------------------------------
# Main enrichment
# ---------------------------------------------------------------------------

def enrich_chunk(chunk: Dict[str, Any], CdeDocument=None) -> Dict[str, Any]:
    text = chunk.get("text", "")
    cems, quantities = enrich_chunk_regex_only(text)

    # Supplement with lightweight catalyst-token heuristic
    extra_tokens = _filter_catalyst_tokens(text)
    all_cems = sorted(set(cems) | set(extra_tokens))

    chunk["cde_cems"] = all_cems
    chunk["cde_quantities"] = quantities
    chunk["cde_cem_count"] = len(all_cems)
    return chunk


def process_file(inp: Path, out: Path, CdeDocument=None, cde_version: Optional[str] = None) -> None:
    chunks = [json.loads(line) for line in inp.open(encoding="utf-8")]
    enriched = []
    for chunk in chunks:
        ec = enrich_chunk(dict(chunk))
        ec["cde_version"] = "regex_only"
        enriched.append(ec)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for rec in enriched:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Summary stats
    with_cems = sum(1 for e in enriched if e["cde_cem_count"] > 0)
    with_qty  = sum(1 for e in enriched if e["cde_quantities"])
    print(f"  chunks processed : {len(enriched)}")
    print(f"  chunks with cems : {with_cems}")
    print(f"  chunks with qty  : {with_qty}")
    print(f"  output           : {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich chunks with CDE2 NER")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--doi", default=PILOT_DOI, help="Sanitised DOI slug")
    grp.add_argument("--all", action="store_true", help="Process all papers")
    args = parser.parse_args()

    if args.all:
        files = list(CHUNKS_DIR.glob("*.high_value_chunks.jsonl"))
    else:
        doi = args.doi
        files = [CHUNKS_DIR / f"{doi}.high_value_chunks.jsonl"]

    for inp in files:
        if not inp.exists():
            print(f"[skip] not found: {inp}", file=sys.stderr)
            continue
        out_name = inp.stem.replace(".high_value_chunks", ".enriched") + ".jsonl"
        out = OUT_DIR / out_name
        print(f"\n→ {inp.name}")
        process_file(inp, out)


if __name__ == "__main__":
    main()
