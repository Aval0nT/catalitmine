"""
scope_figures.py — corpus-wide figure inventory via CAPTIONS (no API, no GPU).

Answers "across all papers, how many activity line charts and bar charts are
there?" Classification uses the figure CAPTION (extracted free by Docling) +
keyword matching — deterministic and reproducible, no vision model. Vision/API
is reserved for actually reading data points off the few activity charts later.

For each DB paper: extract figures + captions (Docling, cached under
figures/all_charts/<slug>/), classify each caption, tally.

Resumable: skips papers whose <slug>.captions.json already exists.

  python3 scripts/extraction/scope_figures.py            # all DB papers
  python3 scripts/extraction/scope_figures.py --limit 5  # quick sample
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "extraction"))
from extract_figures import find_pdf, extract            # noqa: E402

DB = ROOT / "db" / "catalysis.db"
ALL = ROOT / "figures" / "all_charts"
REPORT = ROOT / "outputs" / "reports"

# caption keyword lexicons (lowercased substring match)
CHAR = ["xrd", "raman", " tpd", "tpr", " ir ", "ftir", "infrared", "pyridine",
        " sem", " tem", "haadf", " nmr", "physisorption", "isotherm", " xps",
        "uv-vis", "uv–vis", "tga", "diffraction", "spectra", "spectrum",
        "morphology", "adsorption-desorption", "bet surface", "27al", "29si",
        "characterization", "micrograph", "edx", "eds mapping"]
PERF = ["conversion", "selectiv", "yield", "product distribution",
        "product profile", "productivity", "space-time", "space time",
        "stability", "time on stream", "time-on-stream", "catalytic performance",
        "regeneration", "deactivation", " tof ", "turnover"]
SA = ["effect of", "as a function of", " vs ", "versus", "relationship",
      "correlation", "influence of", "dependence", "with different"]
BARHINT = ["distribution", "profile of mta", "product profile"]


def classify_caption(cap: str) -> tuple[str, str | None]:
    """Return (type, shape_guess). type ∈ characterization / structure_activity /
    activity / mixed / other. shape_guess ∈ bar / line / None."""
    c = " " + (cap or "").lower() + " "
    has_perf = any(k in c for k in PERF)
    has_char = any(k in c for k in CHAR)
    has_sa = has_perf and any(k in c for k in SA)
    if not cap:
        return "no_caption", None
    if has_perf and has_char:
        t = "mixed"
    elif has_sa:
        t = "structure_activity"
    elif has_perf:
        t = "activity"
    elif has_char:
        t = "characterization"
    else:
        t = "other"
    shape = None
    if t in ("activity", "structure_activity", "mixed"):
        shape = "bar" if any(k in c for k in BARHINT) else "line/scatter"
    return t, shape


def captions_for(doi: str) -> dict | None:
    slug = doi.replace("/", "_")
    fdir = ALL / slug
    cj = fdir / f"{slug}.captions.json"
    if cj.exists():
        return json.loads(cj.read_text(encoding="utf-8"))
    pdf = find_pdf(doi)
    if not pdf:
        return None
    try:
        extract(pdf, fdir, scale=2.0)        # writes captions.json
    except Exception as e:
        print(f"    extract failed: {e}")
        return None
    return json.loads(cj.read_text(encoding="utf-8")) if cj.exists() else {}


def main() -> None:
    ap = argparse.ArgumentParser(description="Corpus figure inventory (caption-based)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    c = sqlite3.connect(DB)
    dois = [r[0] for r in c.execute("SELECT doi FROM papers ORDER BY doi")]
    c.close()
    if args.limit:
        dois = dois[: args.limit]

    REPORT.mkdir(parents=True, exist_ok=True)
    rows, types = [], Counter()
    shapes = Counter()
    papers_with_activity = 0

    for i, doi in enumerate(dois, 1):
        caps = captions_for(doi)
        if caps is None:
            print(f"[{i}/{len(dois)}] {doi}  — no PDF/captions")
            continue
        act = 0
        for fig, cap in caps.items():
            t, shape = classify_caption(cap)
            types[t] += 1
            if t in ("activity", "structure_activity", "mixed"):
                act += 1
                shapes[shape] += 1
            rows.append({"doi": doi, "figure": fig, "type": t,
                         "shape": shape, "caption": cap[:160]})
        if act:
            papers_with_activity += 1
        print(f"[{i}/{len(dois)}] {doi}  — {len(caps)} captioned figs, {act} activity/SA")

    (REPORT / "figure_scope.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print("\n" + "=" * 62)
    print(f"papers scanned          : {len(dois)}")
    print(f"papers with activity/SA : {papers_with_activity}")
    print(f"captioned figures total : {len(rows)}")
    print(f"figure types            : "
          + ", ".join(f"{k}={v}" for k, v in types.most_common()))
    print(f"activity/SA by shape    : "
          + ", ".join(f"{k}={v}" for k, v in shapes.most_common()))
    print(f"\nper-figure records → {REPORT / 'figure_scope.jsonl'}")
    print("(shape is a caption-based guess; confirm line vs bar at extraction.)")


if __name__ == "__main__":
    main()
