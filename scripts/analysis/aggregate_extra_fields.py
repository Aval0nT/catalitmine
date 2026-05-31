"""
Aggregate extra_fields across all LLM evidence JSONL files.

Reads data/03_evidence/*.llm_evidence.jsonl, collects all keys found in
extra_fields across all units, and reports their frequency + example values.

This drives schema evolution: keys that appear frequently should be promoted
to formal fields in extract_llm_evidence.py.

Usage:
  python3 scripts/analysis/aggregate_extra_fields.py
  python3 scripts/analysis/aggregate_extra_fields.py --min-count 5
  python3 scripts/analysis/aggregate_extra_fields.py --pass 2  # only Pass 2 extra_fields
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT      = Path(__file__).resolve().parents[2]
EVID_DIR  = ROOT / "data" / "03_evidence"


def load_units(pass_filter: int | None) -> List[Dict[str, Any]]:
    units = []
    for path in sorted(EVID_DIR.glob("*.llm_evidence.jsonl")):
        for line in path.open(encoding="utf-8"):
            u = json.loads(line)
            units.append(u)
    return units


def aggregate(units: List[Dict], min_count: int) -> None:
    # extra_fields can appear at the top level of a merged unit
    # (merged from all three passes into one record)
    key_counter: Counter = Counter()
    key_examples: Dict[str, List] = defaultdict(list)

    total_units = len(units)
    units_with_extra = 0

    for u in units:
        ef = u.get("extra_fields")
        if not ef or not isinstance(ef, dict):
            continue
        units_with_extra += 1
        for k, v in ef.items():
            key_counter[k] += 1
            if len(key_examples[k]) < 3:
                key_examples[k].append(
                    {"value": v, "doi": u.get("source_review_doi", "?"),
                     "page": u.get("source_page")}
                )

    print(f"Total evidence units : {total_units}")
    print(f"Units with extra_fields: {units_with_extra} ({units_with_extra/max(total_units,1)*100:.1f}%)")
    print()

    candidates = [(k, n) for k, n in key_counter.most_common() if n >= min_count]

    if not candidates:
        print(f"No extra_fields keys found with count >= {min_count}.")
        return

    print(f"{'Rank':<5} {'Key':<35} {'Count':>6}  {'%':>6}  Examples")
    print("-" * 80)
    for rank, (k, n) in enumerate(candidates, 1):
        pct = n / total_units * 100
        ex  = key_examples[k][0]
        ex_str = f"{ex['value']!r}  (doi={ex['doi'].split('/')[-1]}, p{ex['page']})"
        print(f"{rank:<5} {k:<35} {n:>6}  {pct:>5.1f}%  {ex_str}")

    print()
    print("--- Promotion checklist ---")
    print("Keys with count >= 10% of units are strong candidates for formal fields.")
    threshold = max(min_count, int(total_units * 0.10))
    promote = [(k, n) for k, n in candidates if n >= threshold]
    if promote:
        for k, n in promote:
            print(f"  [ ] promote '{k}'  (count={n}, {n/total_units*100:.0f}%)")
    else:
        print("  (none above 10% threshold yet — run more papers first)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate extra_fields keys to guide schema evolution"
    )
    parser.add_argument("--min-count", type=int, default=2,
                        help="Minimum occurrence count to display (default: 2)")
    args = parser.parse_args()

    files = list(EVID_DIR.glob("*.llm_evidence.jsonl"))
    if not files:
        print(f"No evidence files found in {EVID_DIR}")
        return

    print(f"Reading {len(files)} evidence file(s) from {EVID_DIR.relative_to(ROOT)}\n")
    units = load_units(pass_filter=None)
    aggregate(units, min_count=args.min_count)


if __name__ == "__main__":
    main()
