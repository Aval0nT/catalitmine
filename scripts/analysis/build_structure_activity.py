"""
build_structure_activity.py — assemble structure–activity data from chart extractions.

Route A (focused): keep chart panels where the y-axis is a PERFORMANCE metric and the
x-axis is a STRUCTURAL DESCRIPTOR (Si/Al, loading, acid density, BET, coverage…). Each
extracted point then becomes a structure–activity datum: (catalyst, descriptor, value,
metric, value). Performance-vs-condition panels (x = T/pressure/TOS) are kept separately
as a secondary table. Product-distribution / other charts are deferred (IDEAS.md #004).

Input : outputs/charts/*.chart.json  (from chart_extractor.py)
Output: outputs/reports/structure_activity_<date>.csv + .jsonl  + a scatter figure
"""
from __future__ import annotations

import glob
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
CHARTS = ROOT / "outputs" / "charts"
OUT = ROOT / "outputs" / "reports"
FIG = ROOT / "figures"

# axis-label classification (substring, case-insensitive)
STRUCT = {
    "si_al": ["si/al", "sio2/al2o3", "si:al", "si-al"],
    "metal_loading": ["loading", "wt%", "wt %", "content", "metal/"],
    "acidity": ["acid", "bas", "las", "bronsted", "brønsted", "lewis", "nh3", "acidity"],
    "bet_area": ["bet", "surface area", "specific surface"],
    "pore": ["pore volume", "pore size", "pore diameter"],
    "crystallinity": ["crystallinity"],
    "coverage": ["coverage", "atoms nm", "atoms/nm", "monolayer"],
    "ratio_descriptor": ["acid/metal", "acid-to-metal", "n_acid", "proximity"],
}
CONDITION = ["temperature", "temp", "°c", "pressure", "mpa", "bar", "whsv", "ghsv",
             "tos", "time on stream", "time-on-stream", "contact time", "cycle",
             "h2/co", "reaction time", "space velocity"]
PERFORMANCE = ["conversion", "selectivity", "yield", "sty", "space-time",
               "productivity", "tof", "ton", "activity"]


def classify(label: str, table: dict | list) -> str | None:
    low = (label or "").lower()
    if isinstance(table, dict):
        for key, pats in table.items():
            if any(p in low for p in pats):
                return key
        return None
    return next((1 for p in table if p in low), None) and "match" or None


def is_perf(label: str) -> bool:
    low = (label or "").lower()
    return any(p in low for p in PERFORMANCE)

def struct_kind(label: str) -> str | None:
    low = (label or "").lower()
    for key, pats in STRUCT.items():
        if any(p in low for p in pats):
            return key
    return None

def is_condition(label: str) -> bool:
    low = (label or "").lower()
    return any(p in low for p in CONDITION)


def doi_from_image(name: str) -> str:
    m = re.match(r'(10\.\d{3,}_[^_]+(?:\.[^_]+)*?)(?:_fig|_p\d|\.)', name)
    slug = m.group(1) if m else name.split("_fig")[0]
    return slug.replace("_", "/", 1)   # best-effort DOI


_ACTIVITY = {"activity", "structure_activity_relation"}

def activity_panels(image: str) -> set | None:
    """Panel ids classified activity/SA in the sibling figtype.json (gate);
    None if the figure was never classified (then keep all, with a warning)."""
    ft = CHARTS / (Path(image).stem + ".figtype.json")
    if not ft.exists():
        return None
    try:
        data = json.loads(ft.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {str(p.get("panel")) for p in data.get("panels", [])
            if p.get("type") in _ACTIVITY}


def main() -> None:
    files = sorted(glob.glob(str(CHARTS / "*.chart.json")))
    if not files:
        raise SystemExit("no chart JSONs — run chart_extractor.py first")

    sa_rows, cond_rows = [], []
    skipped = Counter()
    ungated = 0
    for f in files:
        ce = json.loads(Path(f).read_text(encoding="utf-8"))
        if ce.get("error"):
            skipped["extraction_error"] += 1
            continue
        paper = doi_from_image(ce["image"])
        gate = activity_panels(ce["image"])     # classifier gate
        if gate is None:
            ungated += 1
        for p in ce.get("panels", []):
            if gate is not None and str(p.get("panel")) not in gate:
                skipped["gated_non_activity"] += 1
                continue
            xl = (p.get("x_axis") or {}).get("label", "")
            yl = (p.get("y_axis") or {}).get("label", "")
            if not is_perf(yl):
                skipped["y_not_performance"] += 1
                continue
            sk = struct_kind(xl)
            target = None
            if sk:
                target = ("structure", sk, sa_rows)
            elif is_condition(xl):
                target = ("condition", xl, cond_rows)
            else:
                skipped["x_unclassified"] += 1
                continue
            kind, xkey, bucket = target
            for s in p.get("series", []):
                for pt in s.get("points", []):
                    if pt.get("x") is None or pt.get("y") is None:
                        continue
                    bucket.append({
                        "paper_doi": paper,
                        "catalyst": s.get("name", "?"),
                        "x_kind": xkey,
                        "x_label": xl,
                        "x_value": pt["x"],
                        "metric": yl,
                        "metric_value": pt["y"],
                        "source_image": ce["image"],
                        "panel": p.get("panel"),
                        "confidence": ce.get("confidence"),
                    })

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    sa_path = OUT / f"structure_activity_{stamp}.jsonl"
    with sa_path.open("w", encoding="utf-8") as fh:
        for r in sa_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    # CSV too
    import csv
    if sa_rows:
        with (OUT / f"structure_activity_{stamp}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(sa_rows[0].keys()))
            w.writeheader(); w.writerows(sa_rows)

    print("=" * 64)
    print("STRUCTURE–ACTIVITY from charts (route A)")
    print("=" * 64)
    print(f"chart files parsed         : {len(files)}")
    print(f"structure–activity points  : {len(sa_rows)}")
    print(f"  by descriptor            : "
          + ", ".join(f"{k}={v}" for k, v in Counter(r['x_kind'] for r in sa_rows).most_common()))
    print(f"  distinct catalysts       : {len(set(r['catalyst'] for r in sa_rows))}")
    print(f"  metrics                  : "
          + ", ".join(sorted(set(r['metric'][:24] for r in sa_rows)))[:90])
    print(f"performance-vs-condition   : {len(cond_rows)} points (secondary)")
    print(f"skipped panels             : "
          + ", ".join(f"{k}={v}" for k, v in skipped.most_common()))

    # plot the dominant descriptor — ONE SUBPLOT PER METRIC (never merge metrics;
    # conversion, selectivity, yield are distinct quantities with distinct axes)
    if sa_rows:
        top_desc = Counter(r['x_kind'] for r in sa_rows).most_common(1)[0][0]
        sub = [r for r in sa_rows if r['x_kind'] == top_desc]
        metrics = sorted(set(r['metric'] for r in sub))
        FIG.mkdir(parents=True, exist_ok=True)
        n = len(metrics)
        fig, axes = plt.subplots(1, n, figsize=(5 * n, 4.2), squeeze=False)
        for ax, metric in zip(axes[0], metrics):
            for cat, grp in _by_catalyst(sub, metric):
                grp = sorted(grp, key=lambda r: r['x_value'])
                ax.plot([r['x_value'] for r in grp], [r['metric_value'] for r in grp],
                        marker="o", label=cat)
            ax.set_xlabel(top_desc)
            ax.set_ylabel(metric)            # the REAL metric, not "performance"
            ax.set_title(metric[:40], fontsize=10)
            ax.legend(fontsize=7)
        fig.suptitle(f"Structure–activity from charts — {top_desc} vs each metric "
                     "(metrics kept separate)", fontsize=11)
        fig.tight_layout()
        out = FIG / f"structure_activity_{top_desc}.png"
        fig.savefig(out, dpi=130)
        print(f"\nfigure → {out}")
    print(f"dataset → {sa_path}")
    if ungated:
        print(f"[warn] {ungated} figures had no figtype.json (not gated) — run "
              "classify_figures.py on their folder for a clean activity gate.")
    print("\nNote: grows as you run extract_figures + chart_extractor on more papers.")


def _by_catalyst(rows, metric):
    g: dict = {}
    for r in rows:
        if r['metric'] == metric:
            g.setdefault(r['catalyst'], []).append(r)
    return g.items()


if __name__ == "__main__":
    main()
