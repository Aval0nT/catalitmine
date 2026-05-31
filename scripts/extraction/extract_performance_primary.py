"""
Stage D (Primary papers) — Single-pass performance data extraction.

For primary research papers only. Extracts in ONE API call:
  - Catalyst identity (metal, support, zeolite, preparation)
  - Performance metrics (conversion, selectivity, yield)
  - Reaction conditions (T, P, WHSV)

Does NOT extract claims, mechanisms, or evidence assessments.
Use extract_llm_evidence.py for review papers (3-pass with claims).

~3× faster than the 3-pass script. Suitable for MTA primary papers
where the value is in numeric experimental data, not in claim interpretation.

Usage:
  python3 scripts/extraction/extract_performance_primary.py --doi 10.1016_j.apcata.2024.119912
  python3 scripts/extraction/extract_performance_primary.py --all
  python3 scripts/extraction/extract_performance_primary.py --doi ... --resume

Environment:
  ANTHROPIC_API_KEY — required
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT         = Path(__file__).resolve().parents[2]
ENRICHED_DIR = ROOT / "data" / "02_enriched"
OUT_DIR      = ROOT / "data" / "03_evidence"

MODEL = "claude-haiku-4-5"

# ---------------------------------------------------------------------------
# Single-pass schema
# ---------------------------------------------------------------------------

SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    # Catalyst identity
                    "catalyst_system":     {"type": "string"},
                    "active_metal":        {"type": ["string", "null"]},
                    "promoter":            {"type": ["string", "null"]},
                    "support":             {"type": ["string", "null"]},
                    "zeolite_type":        {"type": ["string", "null"]},
                    "si_al_ratio":         {"type": ["number", "null"]},
                    "metal_loading_wt":    {"type": ["number", "null"]},
                    "morphology":          {"type": ["string", "null"]},
                    "modification_method": {"type": ["string", "null"]},
                    "preparation_method":  {"type": ["string", "null"]},
                    # Performance
                    "methanol_conv_pct":   {"type": ["number", "null"]},
                    "aromatic_sel_pct":    {"type": ["number", "null"]},
                    "btx_sel_pct":         {"type": ["number", "null"]},
                    "benzene_pct":         {"type": ["number", "null"]},
                    "toluene_pct":         {"type": ["number", "null"]},
                    "xylene_pct":          {"type": ["number", "null"]},
                    "c9plus_pct":          {"type": ["number", "null"]},
                    "ethylene_pct":        {"type": ["number", "null"]},
                    "propylene_pct":       {"type": ["number", "null"]},
                    "olefin_pct":          {"type": ["number", "null"]},
                    "paraffin_pct":        {"type": ["number", "null"]},
                    "btx_yield_pct":       {"type": ["number", "null"]},
                    "tos_h":               {"type": ["number", "null"]},
                    "lifetime_h":          {"type": ["number", "null"]},
                    "conversion_drop_pct": {"type": ["number", "null"]},
                    "coke_content_wt":     {"type": ["number", "null"]},
                    "stability_note":      {"type": ["string", "null"]},
                    # Reaction conditions
                    "temperature_c":       {"type": ["number", "null"]},
                    "pressure_mpa":        {"type": ["number", "null"]},
                    "whsv":                {"type": ["number", "null"]},
                    "ghsv":                {"type": ["number", "null"]},
                    "feed_methanol_conc":  {"type": ["string", "null"]},
                    # Source
                    "source_reference":    {"type": ["string", "null"]},
                    # Overflow
                    "extra_fields": {
                        "type": "object",
                        "description": (
                            "Any numeric value not covered above. "
                            "E.g. {'p_xylene_pct': 12, 'bet_m2_g': 350, 'micropore_vol': 0.18}"
                        ),
                    },
                },
                "required": ["catalyst_system"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["evidence_units"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are extracting experimental performance data from a primary MTA (methanol-to-aromatics) research paper.

For each EXPERIMENTAL data point, extract one record containing:

CATALYST IDENTITY:
- catalyst_system: concise display name (e.g. "5wt%Zn/ZSM-5", "Ga/HZSM-5(25)", "P-HZSM-5")
- active_metal:    primary metal (Zn, Ga, Mo, Fe, In, ...) — null if none
- promoter:        dopant/promoter (P, K, La, B, ...) — null if none
- support:         carrier (ZSM-5, Beta, SAPO-34, Al2O3, ...) — null if unclear
- zeolite_type:    ZSM-5 / Beta / SAPO-34 / MCM-22 / ... — null if none
- si_al_ratio:     Si/Al molar ratio — null if not stated
- metal_loading_wt: wt% loading — null if not stated
- morphology:      nanosheet / hierarchical / conventional / ... — null if not stated
- modification_method: dealumination / desilication / acid-treatment / ... — null
- preparation_method: impregnation / ion-exchange / hydrothermal / coprecipitation / ...

PERFORMANCE (%, numeric only):
- methanol_conv_pct:  methanol conversion %
- aromatic_sel_pct:   total aromatic selectivity % (C6+ aromatics)
- btx_sel_pct:        BTX selectivity % (benzene+toluene+xylene only, C6–C8)
- benzene_pct, toluene_pct, xylene_pct: individual C6/C7/C8 selectivities %
- c9plus_pct:         C9+ heavy aromatic selectivity %
- ethylene_pct, propylene_pct: light olefin selectivities %
- olefin_pct:         total light olefin selectivity %
- paraffin_pct:       paraffin selectivity %
- btx_yield_pct:      BTX yield %
- tos_h:              time-on-stream at measurement point (h)
- lifetime_h:         total catalyst lifetime to deactivation (h)
- conversion_drop_pct: % drop in conversion from start to end
- coke_content_wt:    coke wt%
- stability_note:     one-sentence stability observation

REACTION CONDITIONS:
- temperature_c:  °C (convert from K if needed: °C = K − 273.15)
- pressure_mpa:   MPa (convert from bar: MPa = bar × 0.1)
- whsv:           WHSV g_MeOH/(g_cat·h)
- ghsv:           GHSV mL/(g_cat·h)
- feed_methanol_conc: methanol feed concentration or partial pressure (free text)

RULES:
- One record per catalyst × measurement condition (different T or WHSV = separate record).
- ONLY extract values explicitly stated in the text. Do NOT invent or estimate.
- All selectivity/conversion fields: numeric 0–100.
- Do NOT extract claims, interpretations, or mechanisms — only measurements.
- Return empty array if no experimental data is present (e.g. abstract-only or methods description).
- Put any unlisted numeric value (BET, pore volume, acid site density, p-xylene %) in extra_fields.
"""

# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def _call(
    client: Any,
    chunk: Dict,
    doi: str,
    max_retries: int = 4,
) -> List[Dict]:
    """Single extraction pass. Returns list of unit dicts."""
    text       = chunk.get("text", "")
    cems       = chunk.get("cde_cems", [])
    quantities = chunk.get("cde_quantities", [])
    mat_list   = chunk.get("matbert_mat_list", [])
    all_hints  = sorted(set(cems) | set(mat_list))

    # Pre-extract reference numbers from text
    _ref_nums = []
    for m in re.findall(r'\[(\d{1,3}(?:[,\s\-–]+\d{1,3})*)\]', text):
        for part in re.split(r'[,\s]+', m):
            if re.match(r'\d+[-–]\d+', part):
                lo, hi = re.split(r'[-–]', part)
                _ref_nums.extend(range(int(lo), int(hi) + 1))
            elif part.isdigit():
                _ref_nums.append(int(part))
    for m in re.finditer(r'[Rr]ef\.?\s*(\d{1,3})', text):
        _ref_nums.append(int(m.group(1)))
    ref_hints = sorted(set(_ref_nums))
    ref_hint_str = ", ".join(str(n) for n in ref_hints) if ref_hints else "none detected"

    user_content = (
        f"DOI: {doi.replace('_', '/')}\n"
        f"Page: {chunk.get('page')}\n\n"
        f"Material hints (NER): {', '.join(all_hints) if all_hints else 'none'}\n"
        f"Quantities detected: {json.dumps(quantities) if quantities else 'none'}\n"
        f"Reference numbers in text: [{ref_hint_str}]\n\n"
        f"TEXT:\n{text}\n\n"
        f"Extract all experimental data records from the TEXT above."
    )

    tool_def = {
        "name": "extract_performance",
        "description": "Extract catalyst + performance + conditions from a primary paper chunk.",
        "input_schema": SCHEMA,
    }

    last_exc = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                          "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content}],
                tools=[tool_def],
                tool_choice={"type": "any"},
            )
            break
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            status = getattr(exc, "status_code", 0)
            if status in (529, 500) and attempt < max_retries - 1:
                wait = 2 ** attempt * 5
                print(f"  ⏳ {status} retry {attempt+1}/{max_retries} in {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            if "429" in msg and attempt < max_retries - 1:
                wait = 2 ** attempt * 10
                print(f"  ⏳ 429 rate-limit, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    else:
        raise last_exc  # type: ignore[misc]

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        return []
    raw = tool_block.input.get("evidence_units", [])
    return [u for u in raw if isinstance(u, dict)]


# ---------------------------------------------------------------------------
# Per-paper processing
# ---------------------------------------------------------------------------

def _make_evidence_id(doi: str, chunk_id: str, idx: int) -> str:
    slug = doi.replace("/", "_")
    return f"{slug}::{chunk_id}::p{idx:02d}"


def process_file(
    inp: Path,
    client: Any,
    doi: str,
    resume: bool = False,
) -> int:
    out_path = OUT_DIR / f"{inp.stem.replace('.enriched', '')}.llm_evidence.jsonl"

    # Load already-done chunk IDs for resume
    done_ids: set[str] = set()
    if resume and out_path.exists():
        for line in out_path.open(encoding="utf-8"):
            u = json.loads(line)
            if cid := u.get("source_chunk_id"):
                done_ids.add(cid)
        print(f"  [resume] {len(done_ids)} chunks already done")

    chunks = [json.loads(line) for line in inp.open(encoding="utf-8")]
    total_units = 0
    errors = 0

    with out_path.open("a" if resume else "w", encoding="utf-8") as f_out:
        for i, chunk in enumerate(chunks):
            chunk_id = chunk.get("chunk_id") or f"chunk_{i:04d}"
            if chunk_id in done_ids:
                continue

            text_preview = (chunk.get("text") or "")[:50].replace("\n", " ")
            print(f"  [{i+1:02d}/{len(chunks)}] {chunk_id} | {text_preview}...",
                  end=" ", flush=True)

            try:
                units = _call(client, chunk, doi)
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                errors += 1
                continue

            # Attach source metadata + unique ID
            page = chunk.get("page")
            section = chunk.get("section") or chunk.get("source_section")
            for idx, unit in enumerate(units):
                unit["evidence_id"]    = _make_evidence_id(doi, chunk_id, idx)
                unit["source_chunk_id"] = chunk_id
                unit["source_page"]    = page
                unit["source_section"] = section
                unit["llm_model"]      = MODEL
                # Clear any claim fields that might appear (safety)
                for claim_field in ("claim_type", "claim_subject", "claim_predicate",
                                    "claim_object", "proposed_mechanism", "evidence_type",
                                    "confidence", "contradiction_flag"):
                    unit.pop(claim_field, None)

            for unit in units:
                f_out.write(json.dumps(unit, ensure_ascii=False) + "\n")

            total_units += len(units)
            print(f"→ {len(units)} units")

    print(f"\n  chunks: {len(chunks) - errors}  units: {total_units}  errors: {errors}")
    print(f"  saved: {out_path.name}")
    return total_units


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# These are the 26 PENDING primary papers (not reviews)
PRIMARY_SLUGS = [
    "10.1016_j.apcata.2024.119912", "10.1016_j.apcata.2024.120008",
    "10.1016_j.ces.2023.118542",    "10.1016_j.checat.2022.05.012",
    "10.1016_j.checat.2023.100540", "10.1016_j.fuel.2023.130704",
    "10.1016_j.fuel.2025.135207",   "10.1016_j.jechem.2025.08.080",
    "10.1016_j.mcat.2022.112702",   "10.1016_j.mcat.2024.114687",
    "10.1016_j.micromeso.2022.112096","10.1016_j.micromeso.2023.112589",
    "10.1016_j.mtchem.2025.103202", "10.1016_j.mtsust.2023.100364",
    "10.1016_s1872-2067(22)64209-8","10.1021_acs.iecr.2c03873",
    "10.1021_acscatal.2c04600",     "10.1021_acscatal.3c01332",
    "10.1021_acscatal.3c01491",     "10.1021_acscatal.4c02625",
    "10.1021_jacs.4c01155",         "10.1021_jacs.4c12145",
    "10.1021_jacs.5c06141",         "10.1038_s41467-024-55514-1",
    "10.1039_d5ta01181g",           "10.1039_d5ta07457f",
]


def main() -> None:
    import anthropic

    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(
        description="Stage D (primary): single-pass performance extraction"
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--doi",  help="Sanitised DOI slug")
    grp.add_argument("--all",  action="store_true",
                     help="Process all 26 primary PENDING papers")
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-extracted chunks")
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.all:
        slugs = PRIMARY_SLUGS
    else:
        slugs = [args.doi]

    grand_total = 0
    for slug in slugs:
        inp = ENRICHED_DIR / f"{slug}.enriched.jsonl"
        if not inp.exists():
            print(f"[skip] no enriched file: {slug}", file=sys.stderr)
            continue
        doi = slug.replace("_", "/")
        print(f"\n→ {slug}")
        grand_total += process_file(inp, client, doi, resume=args.resume)

    print(f"\n=== Done. Total units extracted: {grand_total} ===")


if __name__ == "__main__":
    main()
