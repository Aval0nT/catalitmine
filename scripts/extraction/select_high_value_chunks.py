"""
Stage B — High-value chunk selection

Reads data/01_chunks/<doi>.chunks.jsonl, filters is_high_value=True,
sorts by score descending, writes data/01_chunks/<doi>.high_value_chunks.jsonl.

Usage:
  python3 scripts/extraction/select_high_value_chunks.py --doi 10.1021_acs.chemrev.9b00723
  python3 scripts/extraction/select_high_value_chunks.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[2]
CHUNKS_DIR = ROOT / "data" / "01_chunks"


def process_file(inp: Path) -> None:
    doi_slug = inp.stem.replace('.chunks', '')
    out = CHUNKS_DIR / f"{doi_slug}.high_value_chunks.jsonl"

    if out.exists():
        print(f"  [skip] already selected: {out.name}")
        return

    rows = [json.loads(line) for line in inp.open(encoding='utf-8')]
    selected = [r for r in rows if r.get('is_high_value')]
    selected.sort(key=lambda r: (-r.get('high_value_score', 0), r.get('page', 0)))

    with out.open('w', encoding='utf-8') as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"  {inp.name} → {len(selected)}/{len(rows)} high-value chunks → {out.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage B: filter high-value chunks")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--doi', help="Sanitised DOI slug")
    grp.add_argument('--all', action='store_true', help="Process all chunk files")
    args = parser.parse_args()

    if args.all:
        files = sorted(CHUNKS_DIR.glob('*.chunks.jsonl'))
    else:
        files = [CHUNKS_DIR / f"{args.doi}.chunks.jsonl"]

    for f in files:
        if not f.exists():
            print(f"[skip] not found: {f}", file=sys.stderr)
            continue
        process_file(f)


if __name__ == '__main__':
    main()
