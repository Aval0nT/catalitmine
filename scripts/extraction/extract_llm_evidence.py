"""
Stage D — LLM Evidence Extraction (3-Pass Cascade, Claude API)

Architecture:
  Pass 1: Catalyst identity  — runs on every high-value chunk
  Pass 2: Performance metrics — runs only if Pass 1 found a catalyst entity
  Pass 3: Conditions + mechanism — runs only if Pass 1 found a catalyst entity

Cascade effect: ~60% of chunks have catalyst entities → effective pass rate ~1.7
(vs. 3.0 if all passes ran unconditionally).  Prompt caching further reduces cost.

MTA field schema v1 (replaces CO2 hydrogenation schema).

Output: data/03_evidence/<doi>.llm_evidence.jsonl
        Each line = one merged evidence unit (Pass 1 + 2 + 3 fields).

Usage:
  python3 scripts/extraction/extract_llm_evidence.py --doi 10.1038_s41929-018-0078-5
  python3 scripts/extraction/extract_llm_evidence.py --all
  python3 scripts/extraction/extract_llm_evidence.py --dry-run
  python3 scripts/extraction/extract_llm_evidence.py --doi ... --resume --max-chunks 10

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
PILOT_DOI    = "10.1038_s41929-018-0078-5"

MODEL = "claude-haiku-4-5"

# ---------------------------------------------------------------------------
# Pass 1 Schema — Catalyst Identity
# ---------------------------------------------------------------------------

PASS1_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "catalyst_system":     {"type": "string"},
                    "active_metal":        {"type": "string"},
                    "promoter":            {"type": "string"},
                    "support":             {"type": "string"},
                    "zeolite_type":        {"type": "string"},
                    "si_al_ratio":         {"type": "number"},
                    "metal_loading_wt":    {"type": "number"},
                    "morphology":          {"type": "string"},
                    "modification_method": {"type": "string"},
                    "preparation_method":  {"type": "string"},
                    "source_reference":    {"type": "string"},
                    "extra_fields": {
                        "type": "object",
                        "description": (
                            "Any catalyst identity fields not covered above. "
                            "E.g. {'crystal_size_nm': 15, 'acidity_type': 'strong Bronsted', "
                            "'calcination_temp_C': 550, 'particle_shape': 'rod'}"
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

# ---------------------------------------------------------------------------
# Pass 2 Schema — Performance Metrics
# ---------------------------------------------------------------------------

PASS2_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "catalyst_system":         {"type": "string"},
                    "methanol_conversion_pct":   {"type": "number"},
                    "btx_selectivity_pct":       {"type": "number"},
                    "aromatic_sel_pct":          {"type": "number"},
                    "benzene_pct":               {"type": "number"},
                    "toluene_pct":               {"type": "number"},
                    "xylene_pct":                {"type": "number"},
                    "c9plus_pct":                {"type": "number"},
                    "ethylene_pct":              {"type": "number"},
                    "propylene_pct":             {"type": "number"},
                    "olefin_pct":                {"type": "number"},
                    "paraffin_pct":              {"type": "number"},
                    "btx_yield_pct":             {"type": "number"},
                    "tos_h":                     {"type": "number"},
                    "lifetime_h":                {"type": "number"},
                    "conversion_drop_pct":       {"type": "number"},
                    "coke_content_wt":           {"type": "number"},
                    "stability_note":            {"type": "string"},
                    "bet_surface_area":        {"type": "number"},
                    "pore_volume":             {"type": "number"},
                    "bronsted_acid_mmol_g":    {"type": "number"},
                    "lewis_acid_mmol_g":       {"type": "number"},
                    "extra_fields": {
                        "type": "object",
                        "description": (
                            "Any performance or characterization fields not covered above. "
                            "E.g. {'p_xylene_selectivity_pct': 12, 'dmb_pct': 3, "
                            "'methane_pct': 2, 'crystal_size_nm': 20, 'b_l_ratio': 0.8}"
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

# ---------------------------------------------------------------------------
# Pass 3 Schema — Conditions + Mechanism
# ---------------------------------------------------------------------------

PASS3_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "catalyst_system":    {"type": "string"},
                    # Reaction conditions
                    "temperature_c":      {"type": "number"},
                    "pressure_mpa":       {"type": "number"},
                    "whsv":               {"type": "number"},
                    "ghsv":               {"type": "number"},
                    "feed_methanol_conc": {"type": "string"},
                    "carrier_gas":        {"type": "string"},
                    "reactor_type":       {
                        "type": "string",
                        "enum": ["fixed-bed", "batch", "flow", "slurry", "not_stated"],
                    },
                    # Claim triple
                    "claim_type": {
                        "type": "string",
                        "enum": ["performance", "mechanism", "trend", "comparison",
                                 "unresolved_question", "hypothesis"],
                    },
                    "claim_subject":   {"type": "string"},
                    "claim_predicate": {"type": "string"},
                    "claim_object":    {"type": "string"},
                    "claim_text":      {"type": "string"},
                    # Mechanism
                    "mechanism_text":     {"type": "string"},
                    "proposed_mechanism": {"type": "string"},
                    "key_intermediates":  {"type": "array", "items": {"type": "string"}},
                    # Quality
                    "evidence_type": {
                        "type": "string",
                        "enum": ["review_synthesis", "experimental", "kinetic",
                                 "in_situ", "operando", "isotopic", "DFT",
                                 "comparative", "speculative"],
                    },
                    "evidence_strength": {
                        "type": "string",
                        "enum": ["strong", "medium", "weak", "unclear"],
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "contradiction_flag": {"type": "boolean"},
                    "needs_manual_check": {"type": "boolean"},
                    "extra_fields": {
                        "type": "object",
                        "description": (
                            "Any condition or mechanism fields not covered above. "
                            "E.g. {'space_time_s': 0.5, 'h2o_partial_pressure_kPa': 5, "
                            "'regeneration_temp_C': 550, 'induction_period_h': 2}"
                        ),
                    },
                },
                "required": [
                    "catalyst_system", "claim_type",
                    "evidence_type", "evidence_strength",
                    "confidence", "contradiction_flag",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["evidence_units"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# System prompts (cached across chunks)
# ---------------------------------------------------------------------------

SYSTEM_PASS1 = """\
You are extracting catalyst identity information from MTA (methanol-to-aromatics) review literature.

For each catalyst system mentioned in the text, extract one record with:
- catalyst_system: short display name (e.g. "5wt%Zn/ZSM-5", "Ga/HZSM-5(25)", "hierarchical ZSM-5")
- active_metal:  primary metal — Zn, Ga, Mo, Fe, Ag, Cu, In, Cr, ... — or null
- promoter:      dopant/promoter — K, Na, La, P, B, ... — or null
- support:       carrier — ZSM-5, Beta, SAPO-34, Al2O3, SiO2, ... — or null
- zeolite_type:  ZSM-5 / Beta / SAPO-34 / MCM-22 / ZSM-11 / ... — or null
- si_al_ratio:   numeric Si/Al molar ratio — or null
- metal_loading_wt: numeric wt% — or null
- morphology:    nanosheet / hierarchical / conventional / mesoporous / ... — or null
- modification_method: dealumination / desilication / steaming / acid-treatment / ... — or null
- preparation_method: impregnation / ion-exchange / coprecipitation / hydrothermal / ... — or null
- source_reference: CRITICAL — the reference number(s) cited alongside this catalyst/data.
    Extract the bracket number e.g. "[23]", "[59,60]" or superscript number.
    If text says "Ref. 23" or "ref 23", record "[23]".
    Check the "Reference numbers in text" hint in the user message.
    Only null if genuinely no reference is associated with this data point.

Rules:
- Return one record per distinct catalyst system mentioned.
- Do NOT invent values. Omit (leave null) any field not stated in text.
- For review papers, extract catalysts from the primary studies being cited.
- ALWAYS try to capture source_reference — essential for tracing data provenance.
- Return empty array if no catalyst system is mentioned.
- Use extra_fields for any catalyst identity detail that does not fit the fields above \
(e.g. crystal_size_nm, calcination_temp_C, acidity_type, particle_shape). \
Do NOT put performance numbers or reaction conditions there.
"""

SYSTEM_PASS2 = """\
You are extracting performance metrics from MTA (methanol-to-aromatics) review literature.

For each catalyst with performance data, extract:
- catalyst_system: match the name used in the text
- methanol_conversion_pct: methanol conversion % (primary activity indicator)
- btx_selectivity_pct:  BTX selectivity % — ONLY C6–C8 aromatics (benzene+toluene+xylene)
- aromatic_sel_pct:     TOTAL aromatic selectivity % including C9+ — use this when the paper
                        reports "aromatic selectivity" without specifying BTX only
- benzene_pct, toluene_pct, xylene_pct: individual C6/C7/C8 aromatic selectivities %
- c9plus_pct:   C9+ heavy aromatics selectivity %
- ethylene_pct: ethylene (C2=) selectivity %
- propylene_pct: propylene (C3=) selectivity % — key MTO product
- olefin_pct:   total light olefin selectivity % (C2=–C4=)
- paraffin_pct: total paraffin selectivity %
- btx_yield_pct: BTX yield % (= conversion × BTX selectivity / 100)
- tos_h:              time-on-stream at the reported measurement point (h)
- lifetime_h:         total catalyst lifetime until full deactivation (h) — distinct from
                      tos_h; only fill when the paper explicitly states how long the catalyst
                      lasted before needing regeneration or replacement
- conversion_drop_pct: % drop in methanol conversion from initial to final measurement
- coke_content_wt:    coke deposition wt%
- stability_note:     free-text stability observation (e.g. "stable for 50 h", "rapid deactivation")
- bet_surface_area:   BET surface area m²/g
- pore_volume:        total pore volume cm³/g
- bronsted_acid_mmol_g: Brønsted acid site density mmol/g
- lewis_acid_mmol_g:    Lewis acid site density mmol/g

Rules:
- Return one record per distinct catalyst × condition data point (different temperature = separate record).
- Do NOT invent values. Omit fields not stated in text.
- All selectivity/conversion fields must be numeric percentages (0–100).
- Return empty array if no performance data is present.
- Use extra_fields for any performance or characterization value not covered above \
(e.g. p_xylene_selectivity_pct, methane_pct, b_l_ratio, micropore_volume). \
Do NOT put catalyst identity or reaction conditions there.
"""

SYSTEM_PASS3 = """\
You are extracting reaction conditions and mechanistic claims from MTA (methanol-to-aromatics) review literature.

For each catalyst system that has conditions or claims, extract:

Reaction conditions:
- temperature_c:      reaction temperature in CELSIUS. If source gives Kelvin, convert: °C = K − 273.15
- pressure_mpa:       total pressure MPa. If source gives bar, convert: MPa = bar × 0.1
- whsv:               weight hourly space velocity g_MeOH/(g_cat·h)
- ghsv:               gas hourly space velocity mL/(g_cat·h)
- feed_methanol_conc: methanol feed concentration or partial pressure (free text)
- carrier_gas:        N2 / He / none / ...
- reactor_type:       fixed-bed / batch / flow / slurry / not_stated

Claim triple (one claim per record — create multiple records for multiple claims):
- claim_type:      performance / mechanism / trend / comparison / unresolved_question / hypothesis
- claim_subject:   catalyst or entity making the observation
- claim_predicate: increases / decreases / suppresses / promotes / shifts / enables /
                   stabilizes / correlates_with / remains_unclear / other
- claim_object:    what is affected (e.g. "BTX selectivity", "coke formation")
- claim_text:      one-sentence factual summary

Mechanism:
- mechanism_text:     free-text description of the proposed mechanism
- proposed_mechanism: hydrocarbon_pool / paring / side_chain / dual_cycle / ... or null
- key_intermediates:  list of key intermediates (e.g. ["polymethylbenzenes", "carbenium ions"])

Quality assessment (required):
- evidence_type:     review_synthesis / experimental / kinetic / in_situ / operando / isotopic / DFT / comparative / speculative
- evidence_strength: strong / medium / weak / unclear
- confidence:        high / medium / low
- contradiction_flag: true if this claim contradicts other literature cited nearby
- needs_manual_check: true if values look anomalous or claim is ambiguous

Rules:
- For review papers: evidence_type = "review_synthesis" unless the review authors themselves ran experiments.
- Return one record per distinct catalyst × claim. A chunk with three different claims about one catalyst → three records.
- Return empty array if no conditions or claims are present.
- Use extra_fields for any condition or mechanism detail not covered above \
(e.g. space_time_s, h2o_partial_pressure_kPa, regeneration_temp_C, induction_period_h). \
Do NOT put catalyst identity or performance metrics there.
"""

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _call_pass(
    client,
    chunk: Dict[str, Any],
    doi: str,
    pass_num: int,
    schema: Dict,
    system_prompt: str,
    tool_name: str,
    max_retries: int = 4,
) -> List[Dict[str, Any]]:
    """Run one extraction pass. Returns list of unit dicts (may be empty)."""
    import anthropic as _anthropic

    text       = chunk.get("text", "")
    cems       = chunk.get("cde_cems", [])
    quantities = chunk.get("cde_quantities", [])
    mat_list   = chunk.get("matbert_mat_list", [])  # Stage C NER output

    # Merge regex catalyst tokens + MatSciBERT MAT entities as hints
    all_mat_hints = sorted(set(cems) | set(mat_list))

    # Pre-extract reference numbers from text (e.g. [23], [59,60], superscript-like 123)
    _ref_nums = []
    for m in re.findall(r'\[(\d{1,3}(?:[,\s\-–]+\d{1,3})*)\]', text):
        for part in re.split(r'[,\s]+', m):
            if re.match(r'\d+[-–]\d+', part):
                lo, hi = re.split(r'[-–]', part)
                _ref_nums.extend(range(int(lo), int(hi) + 1))
            elif part.isdigit():
                _ref_nums.append(int(part))
    # Also catch "ref N" or "Ref. N" patterns
    for m in re.finditer(r'[Rr]ef\.?\s*(\d{1,3})', text):
        _ref_nums.append(int(m.group(1)))
    ref_hints = sorted(set(_ref_nums))
    ref_hint_str = ", ".join(str(n) for n in ref_hints) if ref_hints else "none detected"

    user_content = (
        f"DOI: {doi.replace('_', '/')}\n"
        f"Section: {chunk.get('section') or 'unknown'}\n"
        f"Page: {chunk.get('page')}\n\n"
        f"Material entities (NER+regex): {', '.join(all_mat_hints) if all_mat_hints else 'none'}\n"
        f"Quantities detected: {json.dumps(quantities) if quantities else 'none'}\n"
        f"Reference numbers in text: [{ref_hint_str}]\n\n"
        f"TEXT:\n{text}\n\n"
        f"Extract all evidence units from the TEXT above."
    )

    tool_def = {
        "name": tool_name,
        "description": f"Extract Pass {pass_num} fields from the chunk.",
        "input_schema": schema,
    }

    last_exc = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
                tools=[tool_def],
                tool_choice={"type": "any"},
            )
            break
        except (_anthropic.InternalServerError, _anthropic.APIStatusError) as exc:
            last_exc = exc
            status = getattr(exc, "status_code", 0)
            if status in (529, 500) and attempt < max_retries - 1:
                wait = 2 ** attempt * 5
                print(
                    f"         ⏳ {status} — retry {attempt+1}/{max_retries} in {wait}s",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise
    else:
        raise last_exc  # type: ignore[misc]

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        return []
    raw = tool_block.input.get("evidence_units", [])
    # Guard: LLM occasionally returns strings instead of dicts inside the array
    return [u for u in raw if isinstance(u, dict)]


# ---------------------------------------------------------------------------
# Cascade gate
# ---------------------------------------------------------------------------

def _has_catalyst(units: List[Dict]) -> bool:
    """Pass 1 gate: proceed to Pass 2/3 only if any catalyst entity was found."""
    return bool(units)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _merge_units(
    p1: List[Dict],
    p2: List[Dict],
    p3: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Merge Pass 1/2/3 results by catalyst_system name (case-insensitive).

    For each catalyst in p1, find matching p2/p3 records and overlay their fields.
    Orphan p2/p3 records (no p1 counterpart) are appended as-is.
    """
    def key(name: str) -> str:
        return (name or "").strip().lower()

    p2_by_cat: Dict[str, List[Dict]] = {}
    for u in p2:
        if not isinstance(u, dict):
            continue
        k = key(u.get("catalyst_system", ""))
        p2_by_cat.setdefault(k, []).append(u)

    p3_by_cat: Dict[str, List[Dict]] = {}
    for u in p3:
        if not isinstance(u, dict):
            continue
        k = key(u.get("catalyst_system", ""))
        p3_by_cat.setdefault(k, []).append(u)

    merged: List[Dict[str, Any]] = []
    used_p2: set = set()
    used_p3: set = set()

    base_list = p1 if p1 else [{"catalyst_system": "unknown"}]

    for cat_unit in base_list:
        cat_name = cat_unit.get("catalyst_system", "")
        k = key(cat_name)

        # Prefer exact-key match; fall back to empty-key bucket (unnamed catalyst)
        p2_match = p2_by_cat.get(k) or p2_by_cat.get("", [])
        p3_match = p3_by_cat.get(k) or p3_by_cat.get("", [])

        n = max(1, len(p2_match), len(p3_match))
        for i in range(n):
            rec: Dict[str, Any] = dict(cat_unit)
            if i < len(p2_match):
                rec.update(
                    {fk: fv for fk, fv in p2_match[i].items()
                     if fv is not None and fk != "catalyst_system"}
                )
                used_p2.add(k)
            if i < len(p3_match):
                rec.update(
                    {fk: fv for fk, fv in p3_match[i].items()
                     if fv is not None and fk != "catalyst_system"}
                )
                used_p3.add(k)
            merged.append(rec)

    # Append orphan p2 records not matched to any p1 entry
    for k, units in p2_by_cat.items():
        if k not in used_p2:
            for u in units:
                merged.append(dict(u))

    # Append orphan p3 records not matched to any p1 or p2 entry
    all_used = used_p2 | used_p3 | {key(u.get("catalyst_system","")) for u in p1}
    for k, units in p3_by_cat.items():
        if k not in all_used:
            for u in units:
                merged.append(dict(u))

    return merged


# ---------------------------------------------------------------------------
# 3-Pass cascade
# ---------------------------------------------------------------------------

def call_claude_3pass(
    client,
    chunk: Dict[str, Any],
    doi: str,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Run the 3-pass cascade.

    Returns (merged_units, passes_run_label).
    """
    # --- Pass 1: Catalyst identity (always) ---
    p1_units = _call_pass(
        client, chunk, doi, 1,
        PASS1_SCHEMA, SYSTEM_PASS1, "extract_catalyst_identity",
    )
    time.sleep(1)

    if not _has_catalyst(p1_units):
        units = _finalize(p1_units, [], [], chunk, doi)
        return units, "P1-only"

    # --- Pass 2: Performance metrics ---
    p2_units = _call_pass(
        client, chunk, doi, 2,
        PASS2_SCHEMA, SYSTEM_PASS2, "extract_performance_metrics",
    )
    time.sleep(1)

    # --- Pass 3: Conditions + mechanism ---
    p3_units = _call_pass(
        client, chunk, doi, 3,
        PASS3_SCHEMA, SYSTEM_PASS3, "extract_conditions_mechanism",
    )
    time.sleep(1)

    units = _finalize(p1_units, p2_units, p3_units, chunk, doi)
    return units, "P1+P2+P3"


def _finalize(
    p1: List[Dict],
    p2: List[Dict],
    p3: List[Dict],
    chunk: Dict[str, Any],
    doi: str,
) -> List[Dict[str, Any]]:
    """Merge passes and attach provenance fields."""
    merged = _merge_units(p1, p2, p3)

    chunk_id = chunk.get("chunk_id", "")
    parts = chunk_id.split("::")
    page_part = parts[-2] if len(parts) >= 3 else "p000"
    chunk_part = parts[-1] if len(parts) >= 2 else "c00"

    for i, unit in enumerate(merged):
        unit["evidence_id"]       = f"{doi}::llm::{page_part}::{chunk_part}::u{i+1:02d}"
        unit["source_review_doi"] = doi.replace("_", "/")
        unit["source_chunk_id"]   = chunk_id
        unit["source_page"]       = chunk.get("page")
        unit["source_section"]    = chunk.get("section")
        unit["extraction_origin"] = "llm_3pass"
        unit["llm_model"]         = MODEL

    return merged


# ---------------------------------------------------------------------------
# File-level processing
# ---------------------------------------------------------------------------

def process_file(
    inp: Path,
    out: Path,
    client,
    dry_run: bool = False,
    resume: bool = False,
    max_chunks: Optional[int] = None,
) -> None:
    doi_slug = inp.stem.replace(".enriched", "")
    chunks = [json.loads(line) for line in inp.open(encoding="utf-8")]
    if max_chunks is not None:
        chunks = chunks[:max_chunks]

    done_chunk_ids: set = set()
    if resume and out.exists():
        for line in out.open(encoding="utf-8"):
            u = json.loads(line)
            done_chunk_ids.add(u.get("source_chunk_id", ""))
        print(f"  [resume] {len(done_chunk_ids)} chunks already done — skipping")

    errors   = 0
    new_count = 0
    p1_only_count = 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out_f = out.open("a", encoding="utf-8") if not dry_run else None

    try:
        for i, chunk in enumerate(chunks):
            chunk_id     = chunk.get("chunk_id", f"chunk_{i}")
            text_preview = chunk.get("text", "")[:60].replace("\n", " ")
            print(f"  [{i+1:02d}/{len(chunks)}] {chunk_id} | {text_preview}...")

            if resume and chunk_id in done_chunk_ids:
                print("         ↩ already done, skipping")
                continue

            if dry_run:
                if i == 0:
                    print("--- DRY RUN: Pass 1 prompt preview ---")
                    print(f"[system pass1]: {SYSTEM_PASS1[:200]}...")
                    _cems     = chunk.get("cde_cems", [])
                    _mat_ner  = chunk.get("matbert_mat_list", [])
                    _hints    = sorted(set(_cems) | set(_mat_ner))
                    _qtys     = chunk.get("cde_quantities", [])
                    print(f"[user] regex tokens  : {_cems[:5]}")
                    print(f"[user] matbert MAT   : {_mat_ner[:8]}")
                    print(f"[user] merged hints  : {_hints[:10]}")
                    print(f"[user] quantities    : {_qtys[:3]}")
                    print(f"[user] text: {chunk.get('text','')[:200]}...")
                    print("--------------------------------------")
                print("  [DRY RUN] Skipping API call.\n")
                break

            try:
                units, passes_label = call_claude_3pass(client, chunk, doi_slug)
                for unit in units:
                    out_f.write(json.dumps(unit, ensure_ascii=False) + "\n")
                out_f.flush()
                new_count += len(units)
                if passes_label == "P1-only":
                    p1_only_count += 1
                print(f"         → {len(units)} units  [{passes_label}]")
            except Exception as exc:
                print(f"         ✗ ERROR: {exc}", file=sys.stderr)
                errors += 1
                continue
    finally:
        if out_f:
            out_f.close()

    if not dry_run:
        total = sum(1 for _ in out.open(encoding="utf-8"))
        filtered = p1_only_count
        full_pass = len(chunks) - errors - filtered
        print(f"\n  chunks processed : {len(chunks) - errors}")
        print(f"  cascade filtered : {filtered} (Pass 1 only — no catalyst found)")
        print(f"  full 3-pass      : {full_pass}")
        print(f"  new units        : {new_count}  (errors={errors})")
        print(f"  total in file    : {total}")
        print(f"  output           : {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage D: 3-pass cascade LLM evidence extraction"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--doi", default=PILOT_DOI, help="Sanitised DOI slug")
    grp.add_argument("--all", action="store_true", help="Process all enriched files")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--resume",     action="store_true",
                        help="Skip chunks already present in existing output file")
    parser.add_argument("--max-chunks", type=int, default=None, metavar="N",
                        help="Process only first N chunks (testing)")
    args = parser.parse_args()

    # Load .env from project root if present
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print(
            "ERROR: ANTHROPIC_API_KEY environment variable not set.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key or "dummy")

    files = (
        list(ENRICHED_DIR.glob("*.enriched.jsonl"))
        if args.all
        else [ENRICHED_DIR / f"{args.doi}.enriched.jsonl"]
    )

    for inp in files:
        if not inp.exists():
            print(f"[skip] not found: {inp}", file=sys.stderr)
            continue
        out_name = inp.stem.replace(".enriched", ".llm_evidence") + ".jsonl"
        out = OUT_DIR / out_name
        print(f"\n→ {inp.name}")
        process_file(inp, out, client,
                     dry_run=args.dry_run, resume=args.resume,
                     max_chunks=args.max_chunks)


if __name__ == "__main__":
    main()
