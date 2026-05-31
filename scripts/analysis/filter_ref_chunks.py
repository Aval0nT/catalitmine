"""
Post-processing: Reference list chunk filter + resolver.

Two tasks:
  1. FILTER: identify evidence units extracted from reference-list chunks
     and write a cleaned JSONL without them.

  2. RESOLVE: parse reference-list chunks into a lookup table
     ref_number → {authors, title, journal, year}
     so that source_reference fields like "Ref. [59]" can later be
     matched to a DOI via OpenAlex.

Usage:
  python3 scripts/analysis/filter_ref_chunks.py --doi 10.1038_s41929-018-0078-5
  python3 scripts/analysis/filter_ref_chunks.py --all
  python3 scripts/analysis/filter_ref_chunks.py --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

ROOT         = Path(__file__).resolve().parents[2]
ENRICHED_DIR = ROOT / "data" / "02_enriched"
EVID_DIR     = ROOT / "data" / "03_evidence"
REF_DIR      = ROOT / "data" / "03_evidence"   # ref lookup saved alongside evidence


# ---------------------------------------------------------------------------
# Reference chunk detection
# ---------------------------------------------------------------------------

def is_ref_chunk(text: str) -> bool:
    """Detect chunks that are reference list pages (not scientific text).

    Handles three common journal formats:
      - Standard:   "59. Yarulina, I. et al. ..."       (Nature, RSC, Wiley)
      - ACS:        "(52) Fisher, I. A.; Bell, A. T. ..." (ACS journals)
      - Elsevier:   "127. Fröhlich, G., ..."             (may lack spaces in two-column PDFs)
    """
    # Standard numbered: "59. Author"
    ref_dot    = len(re.findall(r'\b\d{1,3}\.\s+[A-Z][a-z]+', text))
    # ACS bracket: "(52) Author" or "(52)Author" (space sometimes missing in merged PDFs)
    ref_brack  = len(re.findall(r'\(\d{1,3}\)\s*[A-Z][a-z]+', text))
    ref_num    = ref_dot + ref_brack

    et_al      = len(re.findall(r'et al\.', text))
    j_abbrev   = len(re.findall(r'(?:J\.|Chem\.|Phys\.|Nat\.|ACS |Angew\.|Catal\.)\s', text))
    # ACS-style semicolon-separated author lists: "A. T. Bell; I. Yarulina"
    semicolons = len(re.findall(r'[A-Z]\.\s+[A-Z][a-z]+;', text))

    return (
        (ref_num >= 4 and et_al >= 2) or
        (ref_num >= 5 and j_abbrev >= 4) or
        (ref_brack >= 5 and semicolons >= 3)   # ACS-heavy page
    )


# ---------------------------------------------------------------------------
# Reference parser: extract number → citation text mapping
# ---------------------------------------------------------------------------

def parse_ref_chunk(text: str) -> Dict[str, str]:
    """Extract {ref_number: citation_text} from a reference list chunk.

    Handles:
      - Standard dot format:  "59. Yarulina, I. ..."
      - ACS bracket format:   "(52) Fisher, I. A.; Bell, A. T. ..."
      - Two-column merged PDFs where spaces may be missing
    Returns dict like {'59': 'Yarulina, I., Kapteijn, F. ... (2016).', ...}
    """
    refs: Dict[str, str] = {}

    # --- Strategy 1: ACS bracket format "(52) Author..." ---
    for m in re.finditer(r'\((\d{1,3})\)\s*([A-Z][^\n]{10,250})', text):
        num, body = m.group(1), m.group(2).strip()[:300]
        # Basic sanity: should contain a semicolon (author separator) or "et al." or a year
        if re.search(r';|et al\.|19\d{2}|20\d{2}', body):
            refs[num] = body

    # --- Strategy 2: Standard dot format "59. Author..." ---
    if len(refs) < 3:
        parts = re.split(r'(?<!\d)(\b\d{1,3})\.\s+(?=[A-Z])', text)
        i = 0
        while i < len(parts) - 1:
            if re.match(r'^\d{1,3}$', parts[i + 1] if i + 1 < len(parts) else ''):
                num = parts[i + 1]
                body = parts[i + 2] if i + 2 < len(parts) else ''
                body = body.split('\n')[0].strip()[:300]
                refs[num] = body
                i += 3
            else:
                i += 1

    # --- Strategy 3: fallback for any "NN. Author..." pattern ---
    if len(refs) < 3:
        for m in re.finditer(r'\b(\d{1,3})\.\s+([A-Z][^.]{5,100}\.)', text):
            refs[m.group(1)] = m.group(2).strip()

    return refs


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_doi(doi_slug: str, dry_run: bool = False) -> None:
    enriched_path = ENRICHED_DIR / f"{doi_slug}.enriched.jsonl"
    evid_path     = EVID_DIR     / f"{doi_slug}.llm_evidence.jsonl"
    out_path      = EVID_DIR     / f"{doi_slug}.llm_evidence.filtered.jsonl"
    ref_out       = REF_DIR      / f"{doi_slug}.ref_lookup.json"

    if not evid_path.exists():
        print(f"[skip] no evidence file: {evid_path.name}")
        return

    # --- Build set of reference chunk IDs ---
    ref_chunk_ids: set = set()
    all_ref_citations: Dict[str, str] = {}

    if enriched_path.exists():
        for line in enriched_path.open(encoding="utf-8"):
            c = json.loads(line)
            if is_ref_chunk(c.get("text", "")):
                ref_chunk_ids.add(c["chunk_id"])
                parsed = parse_ref_chunk(c["text"])
                all_ref_citations.update(parsed)

    print(f"\n→ {doi_slug}")
    print(f"  reference chunks detected : {len(ref_chunk_ids)}")
    print(f"  ref numbers parsed        : {len(all_ref_citations)}")
    if all_ref_citations:
        sample_keys = sorted(all_ref_citations.keys(), key=lambda x: int(x) if x.isdigit() else 999)[:5]
        for k in sample_keys:
            print(f"    [{k}] {all_ref_citations[k][:80]}")

    # --- Filter evidence units ---
    units = [json.loads(l) for l in evid_path.open(encoding="utf-8")]
    clean = [u for u in units if u.get("source_chunk_id") not in ref_chunk_ids]
    removed = len(units) - len(clean)

    print(f"  evidence units total      : {len(units)}")
    print(f"  removed (from ref chunks) : {removed}")
    print(f"  remaining                 : {len(clean)}")

    if dry_run:
        print("  [DRY RUN] no files written.")
        return

    # Write filtered evidence
    with out_path.open("w", encoding="utf-8") as f:
        for u in clean:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    print(f"  filtered output           : {out_path.name}")

    # Write ref lookup
    if all_ref_citations:
        with ref_out.open("w", encoding="utf-8") as f:
            json.dump(all_ref_citations, f, ensure_ascii=False, indent=2)
        print(f"  ref lookup saved          : {ref_out.name}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter reference-list chunks from evidence + build ref lookup"
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--doi", help="Sanitised DOI slug")
    grp.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all:
        slugs = [f.stem.replace(".llm_evidence", "")
                 for f in sorted(EVID_DIR.glob("*.llm_evidence.jsonl"))]
    else:
        slugs = [args.doi]

    for slug in slugs:
        process_doi(slug, dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
