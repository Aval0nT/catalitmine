"""
extract_highvalue.py — run chart_extractor on the high-value subset only.

Reads the corpus scope (figure_scope.jsonl), selects figures by caption type
(default: structure_activity), locates the cached PNG under figures/all_charts/,
and runs the vision chart extractor on just those — keeping API cost to the
subset. Output JSONs land in outputs/charts/ for build_structure_activity.py.

  python3 scripts/extraction/extract_highvalue.py                 # structure_activity
  python3 scripts/extraction/extract_highvalue.py --types structure_activity,mixed
  python3 scripts/extraction/extract_highvalue.py --limit 30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "extraction"))
from chart_extractor import VisionChartExtractor          # noqa: E402

ALL = ROOT / "figures" / "all_charts"
SCOPE = ROOT / "outputs" / "reports" / "figure_scope.jsonl"
OUT = ROOT / "outputs" / "charts"


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract high-value figure subset (vision)")
    ap.add_argument("--types", default="structure_activity",
                    help="comma-separated caption types to include")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-existing", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="skip figures with a successful result on disk "
                         "(failed results are always retried); "
                         "--no-skip-existing re-runs everything")
    args = ap.parse_args()

    want = set(args.types.split(","))
    rows = [json.loads(l) for l in open(SCOPE, encoding="utf-8")]
    sel = [r for r in rows if r["type"] in want]
    if args.limit:
        sel = sel[: args.limit]
    OUT.mkdir(parents=True, exist_ok=True)

    ex = VisionChartExtractor()
    print(f"selected {len(sel)} figures (types={want})\n")
    done = skipped = miss = 0
    for r in sel:
        slug = r["doi"].replace("/", "_")
        png = ALL / slug / r["figure"]
        out = OUT / f"{png.stem}.chart.json"
        if not png.exists():
            print(f"  · missing PNG: {r['figure']}"); miss += 1; continue
        if args.skip_existing and out.exists():
            # only a SUCCESSFUL result counts as done — an error result
            # (API failure, unparseable reply) is retried, not skipped
            try:
                prev = json.loads(out.read_text(encoding="utf-8"))
            except Exception:
                prev = None
            if prev is not None and not prev.get("error"):
                skipped += 1; continue
        res = ex.extract(png)
        out.write_text(json.dumps(res.to_dict(), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tag = "✓" if not res.error else "✗"
        print(f"  {tag} {r['figure'][:48]:48s} {res.n_points}pts  | {r['caption'][:40]}")
        done += 1
    print(f"\nextracted {done}, skipped {skipped} (existing), {miss} missing PNGs")
    print(f"→ {OUT}  (then: build_structure_activity.py)")


if __name__ == "__main__":
    main()
