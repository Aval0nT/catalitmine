"""
Stage C — CDE2 Structured Record Extraction

Takes enriched chunks (from enrich_chunks_cde.py) and produces
evidence_unit JSONL records aligned with extraction-template-v1.md.

This script uses CDE2's custom catalysis models to extract:
  - catalyst system mentions (active_metal, support, promoter heuristics)
  - performance metrics (CO2 conversion, product selectivity)
  - reaction conditions (temperature, pressure)

Each output record conforms to the Level-C claim/evidence schema:
  {
    "evidence_id":           "...",
    "source_review_doi":     "...",
    "source_chunk_id":       "...",
    "source_section":        "...",
    "extraction_origin":     "cde2_sentence" | "cde2_table" | "regex",
    "catalyst_system":       "...",          # raw string from text
    "active_metal_candidates": [...],        # heuristic decomposition
    "support_candidates":    [...],
    "promoter_candidates":   [...],
    "co2_conversion":        {"value": ..., "unit": ...} | null,
    "selectivity":           {"value": ..., "unit": ..., "product": ...} | null,
    "temperature":           {"value": ..., "unit": ...} | null,
    "pressure":              {"value": ..., "unit": ...} | null,
    "raw_text":              "...",
    "needs_manual_check":    true/false,
    "confidence":            "high" | "medium" | "low",
    "cde_version":           "..."
  }

Usage:
  python3 extract_records_cde.py [--doi DOI] [--all]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
ENRICHED_DIR = ROOT / "data" / "review_evidence_enriched"
OUT_DIR      = ROOT / "data" / "review_evidence"
PILOT_DOI    = "10.1016_j.apcatb.2021.120073"

# ---------------------------------------------------------------------------
# CDE2 model import
# ---------------------------------------------------------------------------

def _load_cde_models():
    """Return (Document, ALL_MODELS, version) or (None, [], None)."""
    try:
        import chemdataextractor as cde
        from chemdataextractor import Document
        from models.catalysis import ALL_MODELS
        return Document, ALL_MODELS, cde.__version__
    except ImportError:
        return None, [], None


# ---------------------------------------------------------------------------
# Catalyst component heuristics
# ---------------------------------------------------------------------------

# Known supports (partial list; extend as needed)
_KNOWN_SUPPORTS = {
    "SiO2", "Al2O3", "TiO2", "ZrO2", "CeO2", "MgO", "ZnO", "La2O3",
    "activated carbon", "carbon", "graphene", "CNT", "zeolite",
    "HZSM-5", "SAPO-34", "MCM-41", "SBA-15", "MOF",
}

# Known promoters
_KNOWN_PROMOTERS = {
    "K", "Na", "Cs", "Rb", "Li",        # alkali
    "Ca", "Ba", "Sr", "Mg",             # alkaline earth
    "La", "Ce", "Pr", "Sm",             # rare earth
    "Mn", "V", "Cr",                    # transition metal promoters
}

# Common active metals in CO2 hydrogenation
_KNOWN_ACTIVES = {
    "Cu", "Fe", "Co", "Rh", "Ru", "Pd", "Pt", "Ni",
    "In", "Ga", "Zn",
}


def decompose_catalyst(cem_text: str) -> Dict[str, List[str]]:
    """
    Heuristically split a catalyst string like 'K-Cu-Fe/ZnO-Al2O3'
    into active_metal, support, promoter candidates.
    """
    actives: List[str] = []
    supports: List[str] = []
    promoters: List[str] = []

    # Split on "/" into (metal-part, support-part)
    parts = cem_text.split("/", 1)
    metal_part = parts[0]
    support_part = parts[1] if len(parts) > 1 else ""

    # Support candidates
    for sup in _KNOWN_SUPPORTS:
        if sup.lower() in support_part.lower():
            supports.append(sup)

    # Active metals and promoters from metal part
    tokens = re.split(r"[-–,\s]+", metal_part)
    for tok in tokens:
        tok = tok.strip()
        if tok in _KNOWN_PROMOTERS:
            promoters.append(tok)
        elif tok in _KNOWN_ACTIVES:
            actives.append(tok)

    # Also scan support part for mixed-oxide supports with active components
    for tok in re.split(r"[-–,\s]+", support_part):
        tok = tok.strip()
        if tok in _KNOWN_ACTIVES and tok not in actives:
            # e.g. "Cu/ZnO" — ZnO is support but Zn could be structural
            pass  # don't double-count

    return {
        "active_metal_candidates": actives,
        "support_candidates": supports,
        "promoter_candidates": promoters,
    }


# ---------------------------------------------------------------------------
# Quantity extraction from enriched chunk
# ---------------------------------------------------------------------------

def _pick_quantity(quantities: List[Dict], unit_types: List[str]) -> Optional[Dict]:
    """Return first quantity whose quantity_type is in unit_types."""
    for q in quantities:
        if q.get("quantity_type") in unit_types:
            return {"value": q["value"], "unit": q["unit"]}
    return None


def _pick_selectivity(quantities: List[Dict], text: str) -> Optional[Dict]:
    """
    Try to find a selectivity value and associated product from text.
    Looks for patterns like '32% selectivity to ethanol'.
    """
    # Find % quantities that appear near selectivity-related words
    sel_re = re.compile(
        r'(\d+(?:\.\d+)?)\s*%\s*(?:selectivity|sel\.?)(?:\s+(?:to|toward|for)\s+'
        r'(?P<product>\w[\w\s+]*?))?(?=[,\.;\s]|$)',
        re.IGNORECASE,
    )
    m = sel_re.search(text)
    if m:
        return {
            "value": m.group(1),
            "unit": "%",
            "product": m.group("product").strip() if m.group("product") else None,
        }
    # Also look for reverse order: '32% C2+ alcohol selectivity'
    sel_re2 = re.compile(
        r'(\d+(?:\.\d+)?)\s*%\s+(?P<product>\w[\w+ ]*?)\s+(?:selectivity|sel\.?)',
        re.IGNORECASE,
    )
    m2 = sel_re2.search(text)
    if m2:
        return {
            "value": m2.group(1),
            "unit": "%",
            "product": m2.group("product").strip(),
        }
    # Fall back to any % quantity labelled as percentage from enrichment
    for q in quantities:
        if q.get("quantity_type") == "percentage" and q.get("source") == "regex":
            return {"value": q["value"], "unit": "%", "product": None}
    return None


def _pick_conversion(quantities: List[Dict], text: str) -> Optional[Dict]:
    """Find CO2 conversion value."""
    conv_re = re.compile(
        r'(?:CO2|CO₂)\s+conversion\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%'
        r'|(\d+(?:\.\d+)?)\s*%\s+(?:CO2|CO₂)\s+conversion',
        re.IGNORECASE,
    )
    m = conv_re.search(text)
    if m:
        val = m.group(1) or m.group(2)
        return {"value": val, "unit": "%"}
    return None


# ---------------------------------------------------------------------------
# Confidence heuristic
# ---------------------------------------------------------------------------

def _confidence(chunk: Dict, record: Dict) -> str:
    """Rough confidence scoring based on how many fields were populated."""
    filled = sum(
        1 for k in ("co2_conversion", "selectivity", "temperature", "pressure")
        if record.get(k) is not None
    )
    cem_count = chunk.get("cde_cem_count", 0)
    if filled >= 2 and cem_count >= 1:
        return "high"
    if filled >= 1 or cem_count >= 1:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Per-chunk record builder
# ---------------------------------------------------------------------------

def chunk_to_records(
    chunk: Dict[str, Any],
    source_doi: str,
    cde_version: str,
) -> List[Dict[str, Any]]:
    """
    Convert one enriched chunk into zero or more evidence_unit records.
    Currently produces one record per chunk (future: one per catalyst mention).
    """
    text = chunk.get("text", "")
    quantities = chunk.get("cde_quantities", [])
    cems = chunk.get("cde_cems", [])

    # Pick the most catalyst-looking CEM as the primary catalyst string
    catalyst_str: Optional[str] = None
    if cems:
        # Prefer tokens with "/" (active/support notation)
        slash_cems = [c for c in cems if "/" in c]
        catalyst_str = slash_cems[0] if slash_cems else cems[0]

    decomp = decompose_catalyst(catalyst_str) if catalyst_str else {
        "active_metal_candidates": [],
        "support_candidates": [],
        "promoter_candidates": [],
    }

    co2_conv   = _pick_conversion(quantities, text)
    selectivity = _pick_selectivity(quantities, text)
    temperature = _pick_quantity(quantities, ["temperature"])
    pressure    = _pick_quantity(quantities, ["pressure"])

    evidence_id = (
        f"{source_doi}::cde::{chunk['chunk_id'].split('::')[-2]}"
        f"::{chunk['chunk_id'].split('::')[-1]}"
    )

    record: Dict[str, Any] = {
        "evidence_id":              evidence_id,
        "source_review_doi":        source_doi.replace("_", "/"),
        "source_chunk_id":          chunk.get("chunk_id"),
        "source_section":           chunk.get("section"),
        "source_page":              chunk.get("page"),
        "extraction_origin":        "cde2_sentence",
        "catalyst_system":          catalyst_str,
        **decomp,
        "co2_conversion":           co2_conv,
        "selectivity":              selectivity,
        "temperature":              temperature,
        "pressure":                 pressure,
        "raw_text":                 text,
        "needs_manual_check":       not bool(co2_conv or selectivity),
        "cde_cems_all":             cems,
        "cde_version":              cde_version,
    }
    record["confidence"] = _confidence(chunk, record)

    # Only emit record if there is at least one extracted entity or quantity
    if cems or co2_conv or selectivity or temperature or pressure:
        return [record]
    return []


# ---------------------------------------------------------------------------
# File-level processing
# ---------------------------------------------------------------------------

def process_file(inp: Path, out: Path, cde_version: str) -> None:
    chunks = [json.loads(line) for line in inp.open(encoding="utf-8")]
    doi_slug = inp.stem.split(".enriched")[0]

    records: List[Dict] = []
    for chunk in chunks:
        records.extend(chunk_to_records(chunk, doi_slug, cde_version))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    high = sum(1 for r in records if r["confidence"] == "high")
    med  = sum(1 for r in records if r["confidence"] == "medium")
    print(f"  evidence records : {len(records)}  (high={high}, medium={med})")
    print(f"  output           : {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structured records via CDE2")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--doi", default=PILOT_DOI)
    grp.add_argument("--all", action="store_true")
    args = parser.parse_args()

    _, _, cde_version = _load_cde_models()
    version_str = cde_version or "regex_fallback"
    if not cde_version:
        print(
            "⚠️  chemdataextractor2 not found — using regex-only extraction.\n",
            file=sys.stderr,
        )

    if args.all:
        files = list(ENRICHED_DIR.glob("*.enriched.jsonl"))
    else:
        files = [ENRICHED_DIR / f"{args.doi}.enriched.jsonl"]

    for inp in files:
        if not inp.exists():
            print(f"[skip] not found: {inp}", file=sys.stderr)
            continue
        out_name = inp.stem.replace(".enriched", ".cde_records") + ".jsonl"
        out = OUT_DIR / out_name
        print(f"\n→ {inp.name}")
        process_file(inp, out, version_str)


if __name__ == "__main__":
    main()
