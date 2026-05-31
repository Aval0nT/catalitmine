"""
Stage A.5 — Table Extraction via Claude Vision

Identifies pages containing data tables in a PDF, renders them as PNG images,
and sends them to Claude Sonnet Vision to extract structured table data.

Output: data/03_evidence/<doi>.tables.jsonl
Each line is one table record with columns and rows as structured JSON.

Usage:
  # Single paper (topic required to locate PDF)
  python3 scripts/extraction/extract_tables_vision.py --doi 10.1038_s41929-018-0078-5 --topic mta

  # All PDFs in a topic
  python3 scripts/extraction/extract_tables_vision.py --topic mta --all

  # Dry run: show detected table pages without calling API
  python3 scripts/extraction/extract_tables_vision.py --doi ... --topic mta --dry-run

Environment:
  ANTHROPIC_API_KEY — required
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber

ROOT      = Path(__file__).resolve().parents[2]
TOPICS_DIR = ROOT / "topics"
OUT_DIR   = ROOT / "data" / "03_evidence"
PILOT_DOI = "10.1038_s41929-018-0078-5"

MODEL = "claude-sonnet-4-6"  # vision requires sonnet or above

# ---------------------------------------------------------------------------
# Table detection: find pages that contain actual data tables
# ---------------------------------------------------------------------------

def page_has_table(text: str) -> bool:
    """Detect pages that contain a data table header or continuation.

    Handles both well-formatted PDFs ("Table 1\\n") and two-column PDFs
    where text is merged without spaces ("Table1.Summary...").

    Matches:
      - 'Table 1.'  / 'Table1.'   (caption line)
      - 'Table 1\\n' / 'Table 1 '  (number followed by whitespace)
      - 'Table 1. Continued'       (continuation page)
    Does NOT match mid-sentence inline refs like '(see Table 1)' because
    those are preceded by non-whitespace characters.
    """
    # After a newline (or start), optional whitespace, then "Table" + optional
    # space + digit — catches both spaced and merged two-column formats
    return bool(re.search(r'(?:^|\n)\s*Table\s*\d+', text))


def find_table_pages(pdf_path: Path) -> List[int]:
    """Return 1-based page numbers that likely contain data tables."""
    table_pages = []
    with pdfplumber.open(str(pdf_path)) as doc:
        for page_num, page in enumerate(doc.pages, start=1):
            text = page.extract_text() or ""
            if page_has_table(text):
                table_pages.append(page_num)
    return table_pages


# ---------------------------------------------------------------------------
# Render page as base64 PNG
# ---------------------------------------------------------------------------

def page_to_base64(pdf_path: Path, page_num: int, resolution: int = 150) -> str:
    with pdfplumber.open(str(pdf_path)) as doc:
        page = doc.pages[page_num - 1]
        img = page.to_image(resolution=resolution)
        buf = io.BytesIO()
        img.original.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Claude Vision extraction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a scientific data extraction specialist for MTA (methanol-to-aromatics) catalysis literature.

Your task is to extract data tables from images of journal paper pages.

## Column header rules (CRITICAL)
Chemistry tables often have multi-row or merged headers. You MUST handle them correctly:
- If a top-level header spans multiple sub-columns (e.g. "Reaction Conditions" over "T (°C) | WHSV | P"), combine them into fully qualified column names: "Reaction Conditions / T (°C)", "Reaction Conditions / WHSV", "Reaction Conditions / P (MPa)".
- Always include units in the column name exactly as printed: "T (°C)" not just "T", "WHSV (h-1)" not just "WHSV".
- If a header cell is empty (blank) but sits under a parent header, inherit the parent label.
- Footnote markers (a, b, *, †) in headers: keep them in the column name, e.g. "Conv. (%)a".

## Data row rules
- Preserve every value exactly as printed, including "—", "n.d.", "<1", ">99", footnote markers.
- For merged row cells (a catalyst name spanning multiple condition rows), repeat the value in each row so every row is self-contained.
- Do NOT skip rows or aggregate values.

## Common MTA abbreviations
XMeOH=methanol conversion, SBTX=BTX selectivity, SBenzene/SToluene/SXylene=individual aromatic selectivity, TOS=time-on-stream, WHSV/GHSV=space velocity, T=temperature, P=pressure, Si/Al or SiO2/Al2O3=silica-alumina ratio, SBET=BET surface area, Vmicro=micropore volume

## What to return
Return ONLY tables containing actual experimental data:
  - Catalyst performance (conversion, selectivity, yield)
  - Reaction conditions (T, P, WHSV, feed composition)
  - Catalyst characterization (BET, pore volume, acidity, Si/Al)
  - Stability / deactivation data (TOS, coke content)

Do NOT return figure captions, section headers, reference lists, or table-of-contents tables.
If the page has no data tables, return an empty tables array."""

TABLE_SCHEMA = {
    "type": "object",
    "properties": {
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "table_number": {"type": "string"},
                    "caption": {"type": "string"},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "notes": {"type": "string"},
                },
                "required": ["table_number", "caption", "columns", "rows"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tables"],
    "additionalProperties": False,
}

EXTRACT_TOOL = {
    "name": "extract_tables",
    "description": "Extract all data tables from the journal page image.",
    "input_schema": TABLE_SCHEMA,
}


def extract_tables_from_page(
    client,
    img_b64: str,
    page_num: int,
    doi: str,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    import anthropic as _anthropic

    last_exc = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                          "cache_control": {"type": "ephemeral"}}],
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"Extract all data tables from this page (page {page_num} of DOI {doi.replace('_', '/')}).",
                        },
                    ],
                }],
                tools=[EXTRACT_TOOL],
                tool_choice={"type": "any"},
            )
            break
        except (_anthropic.InternalServerError, _anthropic.APIStatusError) as exc:
            last_exc = exc
            status = getattr(exc, "status_code", 0)
            if status in (529, 500) and attempt < max_retries - 1:
                wait = 2 ** attempt * 5
                print(f"   ⏳ {status} — retry {attempt+1}/{max_retries} in {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    else:
        raise last_exc

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        return []

    tables = tool_block.input.get("tables", [])

    # Attach provenance
    for i, tbl in enumerate(tables):
        tbl["table_id"] = f"{doi}::p{page_num:02d}::t{i+1:02d}"
        tbl["source_doi"] = doi.replace("_", "/")
        tbl["source_page"] = page_num
        tbl["extraction_origin"] = "vision_claude"
        tbl["llm_model"] = MODEL

    return tables


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def process_pdf(pdf_path: Path, out_path: Path, client, dry_run: bool = False) -> None:
    doi_slug = pdf_path.stem

    print(f"\n→ {pdf_path.name}")
    table_pages = find_table_pages(pdf_path)
    print(f"  Detected table pages: {table_pages}")

    if dry_run:
        print("  [DRY RUN] Would send these pages to Claude Vision.")
        return

    if not table_pages:
        print("  No table pages detected.")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    all_tables = []
    errors = 0

    for page_num in table_pages:
        print(f"  [p{page_num:02d}] Rendering and extracting...", end="", flush=True)
        try:
            img_b64 = page_to_base64(pdf_path, page_num)
            tables = extract_tables_from_page(client, img_b64, page_num, doi_slug)
            all_tables.extend(tables)
            print(f" {len(tables)} table(s) found")
            time.sleep(1)
        except Exception as exc:
            print(f" ✗ ERROR: {exc}", file=sys.stderr)
            errors += 1

    with out_path.open("w", encoding="utf-8") as f:
        for tbl in all_tables:
            f.write(json.dumps(tbl, ensure_ascii=False) + "\n")

    print(f"  Total tables extracted: {len(all_tables)} (errors={errors})")
    print(f"  Output: {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_pdfs(topic: Optional[str], doi_slug: Optional[str]) -> List[Path]:
    """Resolve PDF paths from topics/{topic}/pdfs/."""
    topics = [topic] if topic else [d.name for d in TOPICS_DIR.iterdir() if d.is_dir()]
    results = []
    for t in topics:
        pdf_dir = TOPICS_DIR / t / "pdfs"
        if not pdf_dir.exists():
            continue
        pdfs = sorted(pdf_dir.glob("*.pdf"))
        if doi_slug:
            pdfs = [p for p in pdfs if p.stem == doi_slug]
        results.extend(pdfs)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage A.5: Table extraction via Claude Vision")
    parser.add_argument("--topic", default=None, choices=["mta", "co2a", "shared"],
                        help="Research topic (determines PDF source folder)")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--doi", default=PILOT_DOI, help="Sanitised DOI slug")
    grp.add_argument("--all", action="store_true", help="Process all PDFs in topic")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect table pages only, no API calls")
    args = parser.parse_args()

    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key or "dummy")

    doi_slug = None if args.all else args.doi
    pdfs = get_pdfs(args.topic, doi_slug)

    if not pdfs:
        print("No PDFs found. Check --topic and --doi.", file=sys.stderr)
        return

    for pdf_path in pdfs:
        out_name = pdf_path.stem + ".tables.jsonl"
        process_pdf(pdf_path, OUT_DIR / out_name, client, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
