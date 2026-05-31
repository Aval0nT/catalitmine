"""
Extract Pipeline v2 — Docling-based document processing.

Architecture:
  PDF → Docling parse → auto-detect paper_type → route sections

  Review:
    Abstract/Intro/Body → LLM (claims, trends, comparisons)
    Tables → Docling direct parse (performance comparison)
    References → Docling extract → OpenAlex resolve

  Primary:
    Abstract → LLM (key performance summary)
    Introduction → SKIP
    Experimental → regex (T, P, WHSV, catalyst loading)
    Characterization tables → Docling direct parse (BAS, LAS, BET, Si/Al)
    Results/Discussion → LLM (performance + claims)
    Conclusions → LLM (claims)
    Activity tables → Docling direct parse

Usage:
  python3 scripts/extraction/extract_docling_v2.py --pdf path/to/paper.pdf --topic mta
  python3 scripts/extraction/extract_docling_v2.py --all --topic mta
  python3 scripts/extraction/extract_docling_v2.py --doi 10.1021_acs.iecr.2c03873 --topic mta
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT     = Path(__file__).resolve().parents[2]
PDF_DIR  = ROOT / "pdfs"
OUT_DIR  = ROOT / "data" / "03_evidence"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "claude-haiku-4-5"

# ---------------------------------------------------------------------------
# Column name normalization: table header → DB field
# ---------------------------------------------------------------------------

COLUMN_MAP = {
    # Performance
    r"methanol\s*conv":           "methanol_conv_pct",
    r"conv(?:ersion)?[\s.]*\(?%":  "methanol_conv_pct",
    r"aromatic.*sel|^aromatics$":  "aromatic_sel_pct",
    r"btx.*sel|^btx$":            "btx_sel_pct",
    r"benzene.*sel":              "benzene_pct",
    r"toluene.*sel":              "toluene_pct",
    r"xylene.*sel":               "xylene_pct",
    r"olefin.*sel":               "olefin_pct",
    r"ethylene.*sel":             "ethylene_pct",
    r"propylene.*sel":            "propylene_pct",
    r"lifetime|catalyst\s*life":  "lifetime_h",
    r"tos|time.on.stream":       "tos_h",
    r"coke.*content|coke.*wt":   "coke_content_wt",

    # Conditions
    r"temp.*[°℃]|T\s*/\s*[°℃KC]|temperature.*[KCk°]|\bT\s*\(K\)": "temperature_c",
    r"press.*MPa|P\s*/\s*MPa":    "pressure_mpa",
    r"whsv":                       "whsv",
    r"ghsv":                       "ghsv",

    # Characterization - acid properties
    r"br[øo]nsted|BAS|B\s*acid":    "bas_umol_g",
    r"lewis|LAS|L\s*acid":          "las_umol_g",
    r"B\s*/\s*L|B/L":              "bl_ratio",
    r"total\s*acid|NH3.*total":    "total_acid_umol_g",
    r"strong\s*acid|NH3.*strong":  "strong_acid_umol_g",
    r"weak\s*acid|NH3.*weak":      "total_acid_umol_g",  # fallback

    # Characterization - textural
    r"S\s*BET|BET|surface\s*area.*m": "bet_m2_g",
    r"S\s*(?:Micro|micro)|micropore.*area": "micropore_vol_cm3_g",  # note: might be area
    r"S\s*(?:Exter|exter)|external.*area":  "external_sa_m2_g",
    r"V\s*(?:Total|total)|total.*(?:pore|vol)": "total_pore_vol_cm3_g",
    r"V\s*(?:Micro|micro)|micropore.*vol":      "micropore_vol_cm3_g",
    r"V\s*(?:Meso|meso)|mesopore.*vol":         "mesopore_vol_cm3_g",

    # Structure
    r"Si\s*/\s*Al|SiO.*Al.*O|si.al": "si_al_ratio",
    r"crystal.*size|particle.*size":  "crystal_size_nm",

    # Identity
    r"^sample$|^catalyst[\s_]?(?:name|system)?$|^zeolite$|^entry$": "catalyst_system",
}


def _normalize_column(header: str) -> Optional[str]:
    """Map a table column header to a DB field name."""
    h = header.strip()
    for pattern, field in COLUMN_MAP.items():
        if re.search(pattern, h, re.I):
            return field
    return None


# ---------------------------------------------------------------------------
# Section classification
# ---------------------------------------------------------------------------

SECTION_CLASSES = {
    "abstract":         r"abstract",
    "introduction":     r"introduction",
    "experimental":     r"experiment|method|synthesis|catalyst\s+prep|materials?\s+and",
    "characterization": r"characteriz|characteris",
    "results":          r"results?\s*(and|&)?\s*discuss|results?$|discussion",
    "conclusions":      r"conclusion|summary",
    "references":       r"references?$|bibliography",
    "skip":             r"acknowledg|author\s+info|associated\s+content|supporting\s+info|access$|notes$|conflicts?",
}


def _classify_section(name: str) -> str:
    """Classify a section header into a processing category."""
    for cls, pattern in SECTION_CLASSES.items():
        if re.search(pattern, name, re.I):
            return cls
    return "other"


# ---------------------------------------------------------------------------
# Regex condition extraction (for Experimental sections)
# ---------------------------------------------------------------------------

def _extract_conditions_regex(text: str) -> Dict[str, Any]:
    """Extract reaction conditions from Experimental section text."""
    conditions: Dict[str, Any] = {}

    # Temperature (handle PDF artifacts: ◦C, (cid:N)C, garbled 8C)
    temps = []
    for m in re.finditer(r"\b(\d{3})\s*[°◦∘]\s*[Cc]\b", text):
        v = float(m.group(1))
        if 150 <= v <= 800: temps.append(v)
    for m in re.finditer(r"\b(\d{3})\s*℃", text):
        v = float(m.group(1))
        if 150 <= v <= 800: temps.append(v)
    for m in re.finditer(r"\b(\d{3})\s*\(cid:\d+\)\s*[Cc]\b", text):
        v = float(m.group(1))
        if 150 <= v <= 800: temps.append(v)
    for m in re.finditer(r"\b([3-7]\d{2})[0-9][Cc]\b", text):
        v = float(m.group(1))
        if 150 <= v <= 800: temps.append(v)
    if temps:
        conditions["temperature_c"] = round(sum(set(temps)) / len(set(temps)), 1)
        if len(set(round(t) for t in temps)) > 1:
            conditions["temperature_note"] = f"multiple: {', '.join(str(int(t)) for t in sorted(set(temps)))}°C"

    # Pressure
    for m in re.finditer(r"(\d+\.?\d*)\s*MPa", text, re.I):
        conditions["pressure_mpa"] = float(m.group(1)); break
    for m in re.finditer(r"(\d+\.?\d*)\s*bar\b", text, re.I):
        conditions["pressure_mpa"] = round(float(m.group(1)) * 0.1, 4); break
    for m in re.finditer(r"(\d+\.?\d*)\s*atm\b", text, re.I):
        conditions["pressure_mpa"] = round(float(m.group(1)) * 0.101325, 4); break

    # WHSV
    for m in re.finditer(r"WHSV\s*[=:of\s]\s*(\d+\.?\d*)", text, re.I):
        conditions["whsv"] = float(m.group(1)); break

    # GHSV
    for m in re.finditer(r"GHSV\s*[=:of\s]\s*([\d,]+\.?\d*)", text, re.I):
        conditions["ghsv"] = float(m.group(1).replace(",", "")); break

    # Catalyst loading
    for m in re.finditer(r"(\d+\.?\d*)\s*g\s+(?:of\s+)?(?:catalyst|zeolite|sample)", text, re.I):
        v = float(m.group(1))
        if 0.01 <= v <= 20:
            conditions["catalyst_loading_g"] = v; break

    return conditions


# ---------------------------------------------------------------------------
# Table → evidence units
# ---------------------------------------------------------------------------

def _table_to_units(df, doi_slug: str, table_idx: int) -> List[Dict]:
    """Convert a Docling DataFrame to evidence_unit dicts.

    Handles:
    - Hierarchical column names (e.g. "Reaction Conditions.temperature, T (K)")
    - 'ref' / 'reference' column → source_reference for provenance tracing
    - Temperature in K → convert to °C
    """
    # Flatten hierarchical column names (Docling uses "Group.SubCol")
    flat_cols = {}
    for col in df.columns:
        leaf = str(col).split(".")[-1].strip()   # take sub-column name
        flat_cols[col] = leaf

    # Find ref column (any col whose leaf name matches ref/reference/cite)
    ref_col = None
    for col, leaf in flat_cols.items():
        if re.search(r'^ref(?:erence)?s?$', leaf, re.I):
            ref_col = col
            break

    # Map columns to DB fields using leaf names
    col_mapping = {}
    for col, leaf in flat_cols.items():
        if col == ref_col:
            continue
        db_field = _normalize_column(leaf)
        if not db_field:
            db_field = _normalize_column(str(col))   # try full name too
        if db_field:
            col_mapping[col] = db_field

    if not col_mapping and ref_col is None:
        return []

    # Find catalyst identity column
    cat_col = next((c for c, f in col_mapping.items() if f == "catalyst_system"), None)

    _EMPTY = {"", "-", "−", "–", "—", "n/a", "N/A", "nd", "ND", "—"}

    units = []
    for row_idx, row in df.iterrows():
        # Skip header-repeat rows (all same as column names)
        raw_vals = [str(v).strip() for v in row.values]
        if raw_vals == [str(c).strip() for c in df.columns]:
            continue

        unit: Dict[str, Any] = {
            "evidence_id":    f"{doi_slug}::docling::t{table_idx:02d}::r{row_idx:02d}",
            "source_chunk_id": f"{doi_slug}::table{table_idx:02d}",
            "source_section": "table",
            "llm_model":      "docling-tableformer",
        }

        # Catalyst system
        if cat_col is not None:
            unit["catalyst_system"] = str(row[cat_col]).strip()
        else:
            unit["catalyst_system"] = f"row_{row_idx}"

        # Source reference from ref column
        if ref_col is not None:
            ref_val = str(row[ref_col]).strip()
            if ref_val and ref_val not in _EMPTY:
                # Normalise: strip existing brackets then wrap
                ref_num = re.sub(r'[\[\]\(\)]', '', ref_val).strip()
                unit["source_reference"] = f"[{ref_num}]"

        # All other mapped columns
        for col, field in col_mapping.items():
            if field == "catalyst_system":
                continue
            val = str(row[col]).strip()
            if val in _EMPTY:
                continue
            # Strip footnote markers like "48 h (70%)" → try numeric first
            numeric_str = re.match(r'^([0-9]+\.?[0-9]*)', val)
            if numeric_str:
                num = float(numeric_str.group(1))
                # Convert K → °C for temperature fields
                if field == "temperature_c" and num > 200:
                    num = round(num - 273.15, 1)
                unit[field] = num
            else:
                unit[field] = val   # keep as string (e.g. "48 h (70%)")

        # Only keep rows with at least one numeric value beyond catalyst name
        numeric_fields = {k: v for k, v in unit.items()
                          if k not in ("evidence_id", "source_chunk_id", "source_section",
                                       "llm_model", "catalyst_system", "source_reference")
                          and isinstance(v, (int, float))}
        if numeric_fields:
            units.append(unit)

    return units


# ---------------------------------------------------------------------------
# LLM extraction for Results/Discussion
# ---------------------------------------------------------------------------

SYSTEM_PRIMARY_RESULTS = """\
You extract quantitative experimental data from MTA (methanol-to-aromatics) primary research papers.

For each distinct data point in the text, extract:
- catalyst_system: short name (e.g. "5wt%Zn/ZSM-5", "HZSM-5(25)")
- active_metal: Zn, Ga, Mo, Fe, Ni, ... — or null
- support / zeolite_type: ZSM-5 / Beta / SAPO-34 / ... — or null
- si_al_ratio: numeric — or null
- methanol_conv_pct, aromatic_sel_pct, btx_sel_pct: numeric — or null
- temperature_c, pressure_mpa, whsv, ghsv: numeric — or null
- tos_h, lifetime_h: numeric — or null
- source_reference: reference number in brackets e.g. "[23]" — CRITICAL for tracing provenance

Rules:
- Only extract data explicitly stated in text with numbers. Do NOT invent.
- Do NOT extract claims, interpretations, or mechanisms.
- Return empty array if no quantitative data found.
"""

SYSTEM_CLAIMS = """\
You extract scientific claims and conclusions from MTA (methanol-to-aromatics) literature.

For each distinct claim, extract:
- claim_type: performance / mechanism / trend / comparison / unresolved_question / hypothesis
- claim_subject: what the claim is about (e.g. "Zn/ZSM-5")
- claim_predicate: the relationship (e.g. "increases", "correlates_with", "outperforms")
- claim_object: the target (e.g. "aromatic selectivity at 400°C")
- source_reference: reference number "[N]" if citing another work — or null
- evidence_type: experimental / computational / review_synthesis — or null

Rules:
- One record per distinct claim.
- For review papers, capture the key judgments and comparisons the authors make.
- ALWAYS extract source_reference when a citation is present.
- Return empty array if no claims found.
"""

SCHEMA_PERFORMANCE = {
    "type": "object",
    "properties": {
        "evidence_units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "catalyst_system":     {"type": "string"},
                    "active_metal":        {"type": ["string", "null"]},
                    "support":             {"type": ["string", "null"]},
                    "zeolite_type":        {"type": ["string", "null"]},
                    "si_al_ratio":         {"type": ["number", "null"]},
                    "methanol_conv_pct":   {"type": ["number", "null"]},
                    "aromatic_sel_pct":    {"type": ["number", "null"]},
                    "btx_sel_pct":         {"type": ["number", "null"]},
                    "temperature_c":       {"type": ["number", "null"]},
                    "pressure_mpa":        {"type": ["number", "null"]},
                    "whsv":                {"type": ["number", "null"]},
                    "ghsv":                {"type": ["number", "null"]},
                    "tos_h":               {"type": ["number", "null"]},
                    "lifetime_h":          {"type": ["number", "null"]},
                    "source_reference":    {"type": ["string", "null"]},
                },
                "required": ["catalyst_system"],
            },
        }
    },
    "required": ["evidence_units"],
}

SCHEMA_CLAIMS = {
    "type": "object",
    "properties": {
        "evidence_units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_type":       {"type": "string"},
                    "claim_subject":    {"type": "string"},
                    "claim_predicate":  {"type": "string"},
                    "claim_object":     {"type": "string"},
                    "source_reference": {"type": ["string", "null"]},
                    "evidence_type":    {"type": ["string", "null"]},
                },
                "required": ["claim_type", "claim_subject", "claim_predicate", "claim_object"],
            },
        }
    },
    "required": ["evidence_units"],
}


def _call_llm(
    client,
    text: str,
    doi: str,
    section: str,
    page: Optional[int],
    system_prompt: str,
    schema: Dict,
    tool_name: str,
    max_retries: int = 3,
) -> List[Dict]:
    """Call Claude API for extraction. Returns list of unit dicts."""
    # Pre-extract reference hints
    ref_nums = []
    for m in re.findall(r'\[(\d{1,3}(?:[,\s\-–]+\d{1,3})*)\]', text):
        for part in re.split(r'[,\s]+', m):
            if re.match(r'\d+[-–]\d+', part):
                lo, hi = re.split(r'[-–]', part)
                ref_nums.extend(range(int(lo), int(hi) + 1))
            elif part.isdigit():
                ref_nums.append(int(part))
    ref_hint = ", ".join(str(n) for n in sorted(set(ref_nums))) if ref_nums else "none"

    user_content = (
        f"DOI: {doi}\n"
        f"Section: {section}\n"
        f"Reference numbers in text: [{ref_hint}]\n\n"
        f"TEXT:\n{text}\n\n"
        f"Extract all relevant data from the TEXT above."
    )

    tool_def = {
        "name": tool_name,
        "description": f"Extract structured data from {section}.",
        "input_schema": schema,
    }

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[{"type": "text", "text": system_prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content}],
                tools=[tool_def],
                tool_choice={"type": "any"},
            )
            for block in response.content:
                if block.type == "tool_use":
                    return block.input.get("evidence_units", [])
            return []
        except Exception as exc:
            status = getattr(exc, "status_code", 0)
            if status in (429, 529, 500) and attempt < max_retries - 1:
                time.sleep(2 ** attempt * 3)
                continue
            raise
    return []


# ---------------------------------------------------------------------------
# Reference extraction (Docling-based, replaces Vision API)
# ---------------------------------------------------------------------------

def _extract_references(md_text: str) -> Dict[str, str]:
    """Extract reference list from markdown text."""
    lines = md_text.split('\n')

    ref_start = None
    for i, line in enumerate(lines):
        if re.search(r'REFERENCES|Bibliography', line, re.I) and re.match(r'^#', line):
            ref_start = i + 1
            break
        if '■ REFERENCES' in line.upper():
            ref_start = i + 1
            break

    if ref_start is None:
        return {}

    ref_lookup = {}
    current_num = None
    current_text = ""

    # Support multiple formats: (N), [N], N.
    ref_pattern = re.compile(r'\s*[-•]?\s*[\(\[]?(\d{1,3})[\)\]]?\s*[.)]?\s+(.*)')

    for line in lines[ref_start:]:
        m = ref_pattern.match(line)
        if m:
            if current_num and current_text:
                ref_lookup[current_num] = current_text.strip()[:200]
            current_num = m.group(1)
            current_text = m.group(2)
        elif current_num and line.strip():
            current_text += " " + line.strip()

    if current_num and current_text:
        ref_lookup[current_num] = current_text.strip()[:200]

    return ref_lookup


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

class PaperProcessor:
    """Process a single PDF through the v2 pipeline."""

    def __init__(self, pdf_path: Path, topic: str = "mta",
                 doi_slug: Optional[str] = None,
                 paper_type: Optional[str] = None):
        self.pdf_path = pdf_path
        self.topic = topic
        self.doi_slug = doi_slug or pdf_path.stem
        self.doi = self.doi_slug.replace("_", "/")

        self.doc = None
        self.md_text = ""
        self.paper_type = paper_type  # override if provided; else auto-detect
        self.sections: List[Dict] = []   # [{name, cls, text}]
        self.tables: List[Any] = []      # Docling table DataFrames
        self.ref_lookup: Dict[str, str] = {}
        self.conditions: Dict[str, Any] = {}  # paper-level conditions from Experimental
        self.evidence_units: List[Dict] = []

    # --- Stage 1: Parse ---

    def parse(self) -> None:
        """Use Docling to parse PDF into structured sections + tables."""
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        result = converter.convert(self.pdf_path)
        self.doc = result.document
        self.md_text = self.doc.export_to_markdown()

        self._split_sections()
        self._extract_tables()

        # Load ref_lookup: prefer existing file on disk, then parse from markdown
        ref_lookup_path = OUT_DIR / f"{self.doi_slug}.ref_lookup.json"
        if ref_lookup_path.exists():
            self.ref_lookup = json.loads(ref_lookup_path.read_text(encoding="utf-8"))
        else:
            self.ref_lookup = _extract_references(self.md_text)

        # Detect paper type only if not provided externally
        if self.paper_type is None:
            self._detect_paper_type()

        print(f"  Parsed: {len(self.sections)} sections, {len(self.tables)} tables, "
              f"{len(self.ref_lookup)} refs, type={self.paper_type}")

    def _split_sections(self) -> None:
        """Split markdown into named sections with classification."""
        lines = self.md_text.split('\n')
        current_name = "header"
        current_lines: List[str] = []

        for line in lines:
            if re.match(r'^#{1,3}\s', line):
                if current_lines:
                    text = '\n'.join(current_lines).strip()
                    if text:
                        self.sections.append({
                            "name": current_name,
                            "cls": _classify_section(current_name),
                            "text": text,
                        })
                current_name = line.strip('#').strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            text = '\n'.join(current_lines).strip()
            if text:
                self.sections.append({
                    "name": current_name,
                    "cls": _classify_section(current_name),
                    "text": text,
                })

    def _extract_tables(self) -> None:
        """Extract tables as DataFrames using current Docling API."""
        import warnings
        for tbl in self.doc.tables:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    df = tbl.export_to_dataframe()
                if df is not None and not df.empty:
                    self.tables.append(df)
            except Exception as e:
                print(f"    [table skip] {e}")

    def _detect_paper_type(self) -> None:
        """Auto-detect review vs primary based on section structure."""
        section_classes = {s["cls"] for s in self.sections}
        if "experimental" in section_classes:
            self.paper_type = "primary"
        elif len(self.ref_lookup) > 80:
            self.paper_type = "review"
        else:
            # Heuristic: if "review" appears in title/abstract
            title_text = " ".join(s["text"][:500] for s in self.sections[:3]).lower()
            if any(w in title_text for w in ["review", "survey", "perspective", "progress"]):
                self.paper_type = "review"
            else:
                self.paper_type = "primary"

    # --- Stage 2: Process by type ---

    def process(self, client=None) -> List[Dict]:
        """Main processing entry point."""
        self.parse()

        # Tables → direct parse (both types)
        for i, df in enumerate(self.tables):
            units = _table_to_units(df, self.doi_slug, i)
            for u in units:
                u["source_review_doi"] = self.doi
            self.evidence_units.extend(units)
            if units:
                print(f"    Table {i}: {len(units)} units extracted")

        # Save ref_lookup
        ref_path = OUT_DIR / f"{self.doi_slug}.ref_lookup.json"
        if self.ref_lookup:
            ref_path.write_text(
                json.dumps(self.ref_lookup, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"    Saved {len(self.ref_lookup)} refs → {ref_path.name}")

        if self.paper_type == "primary":
            self._process_primary(client)
        else:
            self._process_review(client)

        # Apply paper-level conditions to units missing them
        if self.conditions:
            for unit in self.evidence_units:
                for field, val in self.conditions.items():
                    if field not in unit or unit[field] is None:
                        unit[field] = val

        # Set common fields
        for unit in self.evidence_units:
            unit["source_review_doi"] = self.doi
            if self.paper_type != "review":
                unit.setdefault("primary_paper_doi", self.doi)

        # For reviews: resolve source_reference → primary_paper_doi via ref_resolved.json
        if self.paper_type == "review":
            self._resolve_provenance()

        # Provenance tier: gold=direct primary, silver=review+doi resolved, bronze=review only
        for unit in self.evidence_units:
            if self.paper_type == "primary":
                unit["provenance_tier"] = "gold"
            elif unit.get("primary_paper_doi"):
                unit["provenance_tier"] = "silver"
            else:
                unit["provenance_tier"] = "bronze"

        return self.evidence_units

    def _process_primary(self, client) -> None:
        """Primary paper processing pipeline."""
        for sec in self.sections:
            cls = sec["cls"]

            if cls == "introduction":
                continue  # Skip

            elif cls == "experimental":
                # Regex extraction for conditions
                self.conditions = _extract_conditions_regex(sec["text"])
                if self.conditions:
                    print(f"    Experimental: {self.conditions}")

            elif cls in ("abstract", "results", "conclusions", "characterization", "other"):
                if not client:
                    continue
                if not sec["text"].strip():
                    continue
                # Send to LLM
                text = sec["text"]
                # Chunk if too long (>6000 chars)
                chunks = _chunk_text(text, max_chars=6000)
                for ci, chunk in enumerate(chunks):
                    system = SYSTEM_PRIMARY_RESULTS if cls != "conclusions" else SYSTEM_CLAIMS
                    schema = SCHEMA_PERFORMANCE if cls != "conclusions" else SCHEMA_CLAIMS
                    tool = "extract_performance" if cls != "conclusions" else "extract_claims"

                    units = _call_llm(
                        client, chunk, self.doi, sec["name"], None,
                        system, schema, tool,
                    )
                    for j, u in enumerate(units):
                        u["evidence_id"] = f"{self.doi_slug}::v2::{cls}::c{ci:02d}::u{j:02d}"
                        u["source_section"] = sec["name"]
                        u["llm_model"] = MODEL
                    self.evidence_units.extend(units)
                    time.sleep(1)

                if units:
                    print(f"    {sec['name'][:40]}: {len(units)} units via LLM")

    def _resolve_provenance(self) -> None:
        """Link review evidence units to primary_paper_doi using ref_resolved.json.

        For each unit with source_reference like "[12]" or "[12,15]":
          1. Parse citation number(s)
          2. Look up ref_resolved.json for this paper
          3. Fill primary_paper_doi + source_citation_text if DOI resolved
        """
        resolved_path = OUT_DIR / f"{self.doi_slug}.ref_resolved.json"
        if not resolved_path.exists():
            return

        ref_resolved: Dict[str, Dict] = json.loads(
            resolved_path.read_text(encoding="utf-8")
        )
        enriched = 0

        for unit in self.evidence_units:
            src_ref = unit.get("source_reference")
            if not src_ref:
                continue

            # Parse all citation numbers — handles "[12]", "[12,15]", "[12-15]"
            nums: List[str] = []
            cleaned = re.sub(r'[\[\]\(\)]', ' ', str(src_ref))
            for part in re.split(r'[,;\s]+', cleaned):
                part = part.strip()
                rng = re.match(r'^(\d{1,3})[-–](\d{1,3})$', part)
                if rng:
                    nums.extend(str(n) for n in range(int(rng.group(1)), int(rng.group(2)) + 1))
                elif re.match(r'^\d{1,3}$', part):
                    nums.append(part)

            for num in nums:
                entry = ref_resolved.get(num, {})

                # Always add citation text if available (even without DOI)
                if not unit.get("source_citation_text"):
                    cit = entry.get("citation_text") or self.ref_lookup.get(num, "")
                    if cit:
                        unit["source_citation_text"] = cit[:200]

                doi = entry.get("doi")
                if doi and not unit.get("primary_paper_doi"):
                    unit["primary_paper_doi"] = doi
                    enriched += 1
                    break  # first resolved DOI wins

        if enriched:
            print(f"    Provenance: {enriched}/{len(self.evidence_units)} units linked to primary DOI")

    def _process_review(self, client) -> None:
        """Review paper processing pipeline."""
        for sec in self.sections:
            cls = sec["cls"]

            if cls in ("references", "skip"):
                continue

            if not client or not sec["text"].strip():
                continue

            # Reviews: extract claims from all content sections
            text = sec["text"]
            chunks = _chunk_text(text, max_chars=6000)

            for ci, chunk in enumerate(chunks):
                # Use claims schema for intro/conclusions, performance for results-like
                if cls in ("abstract", "introduction", "conclusions"):
                    system, schema, tool = SYSTEM_CLAIMS, SCHEMA_CLAIMS, "extract_claims"
                else:
                    # Body sections: extract both performance and claims
                    system, schema, tool = SYSTEM_PRIMARY_RESULTS, SCHEMA_PERFORMANCE, "extract_performance"

                units = _call_llm(
                    client, chunk, self.doi, sec["name"], None,
                    system, schema, tool,
                )
                for j, u in enumerate(units):
                    u["evidence_id"] = f"{self.doi_slug}::v2::{cls}::c{ci:02d}::u{j:02d}"
                    u["source_section"] = sec["name"]
                    u["llm_model"] = MODEL
                self.evidence_units.extend(units)
                time.sleep(1)

            if units:
                print(f"    {sec['name'][:40]}: {len(units)} units via LLM")


def _chunk_text(text: str, max_chars: int = 6000) -> List[str]:
    """Split text into chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split('\n\n')
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract Pipeline v2 (Docling-based)")
    parser.add_argument("--pdf", type=Path, help="Single PDF file")
    parser.add_argument("--doi", help="DOI slug (looks up PDF in topics/)")
    parser.add_argument("--all", action="store_true", help="Process all PDFs in topic")
    parser.add_argument("--topic", default="mta", help="Topic: mta, co2a, shared")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM calls (tables + regex only)")
    parser.add_argument("--resume", action="store_true", help="Skip papers that already have v2 output")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output")
    args = parser.parse_args()

    # API client (if LLM needed)
    client = None
    if not args.no_llm:
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception as e:
            print(f"Warning: No API client ({e}). Running in no-llm mode.")

    # Collect PDFs
    pdfs: List[Path] = []
    if args.pdf:
        pdfs = [args.pdf]
    elif args.doi:
        slug = args.doi
        p = PDF_DIR / f"{slug}.pdf"
        if p.exists():
            pdfs = [p]
        else:
            print(f"PDF not found: {p}"); sys.exit(1)
    elif args.all:
        # Only process review papers (primary papers use extract_performance_primary.py)
        import sqlite3
        conn = sqlite3.connect(ROOT / "db" / "catalysis.db")
        review_dois = [r[0].replace("/", "_")
                       for r in conn.execute(
                           "SELECT doi FROM papers WHERE paper_type='review'"
                       ).fetchall()]
        conn.close()
        pdfs = sorted(p for slug in review_dois
                      if (p := PDF_DIR / f"{slug}.pdf").exists())
        args._db_paper_type = "review"   # all papers from --all are reviews
    else:
        parser.print_help(); sys.exit(1)

    print(f"Processing {len(pdfs)} PDF(s), topic={args.topic}, "
          f"llm={'on' if client else 'off'}\n")

    total_units = 0
    for pdf_path in pdfs:
        doi_slug = pdf_path.stem
        out_file = OUT_DIR / f"{doi_slug}.v2_evidence.jsonl"

        if args.resume and out_file.exists():
            print(f"[skip] {doi_slug} (v2 output exists)")
            continue

        print(f"→ {doi_slug}")
        try:
            forced_type = getattr(args, '_db_paper_type', None)
            proc = PaperProcessor(pdf_path, args.topic, doi_slug,
                                  paper_type=forced_type)
            units = proc.process(client)

            # Save output
            with open(out_file, "w", encoding="utf-8") as f:
                for u in units:
                    f.write(json.dumps(u, ensure_ascii=False) + "\n")

            print(f"  ✓ {len(units)} units → {out_file.name}\n")
            total_units += len(units)

        except Exception as exc:
            print(f"  ✗ Error: {exc}\n", file=sys.stderr)

    print(f"Done. {total_units} total units from {len(pdfs)} papers.")


if __name__ == "__main__":
    main()
