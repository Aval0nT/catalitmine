"""parity_coords.py — Phase 3 acceptance: end-to-end coordinates vs Modal goldens.

Runs the full HF chain (lineformer_hf_infer masks -> line_postproc series)
on the 30 probe images and compares the RESULTING POINT SERIES against
figures/lineformer_probe_results/output/*/lineformer/coordinates.json —
the same artifact the original mmdet stack produced, so this measures the
whole port, model + post-processing together.

Matching: greedy 1-1 between golden and predicted lines by ascending mean
|Δy| over their common integer-x grid. Per matched pair we report
  overlap   |common x| / |golden x|   (does the trace span what theirs did?)
  mae_y     mean |Δy| on common x     (does it sit on the same curve?)

Phase 2 already showed masks diverge on near-tie regions (composites,
1-px lines); the Phase 3 question is narrower: wherever the masks agree,
do the COORDINATES come out identical? Clean panels should sit at
overlap ~1.0 / mae_y ~<=1 px.

Run:  venv/bin/python scripts/extraction/lineformer_port/parity_coords.py
Out:  figures/lineformer_probe_results/hf_coord_parity.json + console table
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from line_postproc import masks_to_dataseries  # noqa: E402
from lineformer_hf_infer import get_instance_masks, load_model  # noqa: E402

MODEL_DIR = ROOT / "models" / "lineformer_hf"
PROBE = ROOT / "figures" / "lineformer_probe"
GOLD = ROOT / "figures" / "lineformer_probe_results" / "output"
REPORT = ROOT / "figures" / "lineformer_probe_results" / "hf_coord_parity.json"


def as_dict(line: list[dict]) -> dict[int, float]:
    return {int(pt["x"]): float(pt["y"]) for pt in line}


def pair_stats(gold: list[dict], pred: list[dict]) -> tuple[float, float]:
    """-> (overlap fraction of golden x covered, mean |dy| on common x)."""
    g, p = as_dict(gold), as_dict(pred)
    if not g or not p:
        # only empty-vs-empty is a (trivially exact) match; an empty golden
        # line must never claim a real prediction, nor vice versa
        return (1.0, 0.0) if not g and not p else (0.0, float("inf"))
    common = sorted(set(g) & set(p))
    if not common:
        return 0.0, float("inf")
    mae = float(np.mean([abs(g[x] - p[x]) for x in common]))
    return len(common) / len(g), mae


def evaluate(name: str, model, device: str) -> dict | None:
    gold_path = GOLD / name / "lineformer" / "coordinates.json"
    img_path = PROBE / name
    if not gold_path.exists() or not img_path.exists():
        return None
    gold = json.load(open(gold_path))
    img = cv2.imread(str(img_path))
    masks, _scores = get_instance_masks(model, img, score_thr=0.3, device=device)
    pred = masks_to_dataseries(masks)

    candidates = sorted(
        ((pair_stats(gold[g], pred[p]), g, p)
         for g in range(len(gold)) for p in range(len(pred))),
        key=lambda t: t[0][1],  # ascending mean |dy|
    )
    used_g, used_p, pairs = set(), set(), []
    for (overlap, mae), g, p in candidates:
        if g in used_g or p in used_p:
            continue
        used_g.add(g)
        used_p.add(p)
        pairs.append({"gold": g, "pred": p,
                      "overlap": round(overlap, 3),
                      "mae_y": None if mae == float("inf") else round(mae, 2)})
    return {
        "image": name,
        "n_gold": len(gold),
        "n_pred": len(pred),
        "pairs": pairs,
        "median_overlap": round(float(np.median([q["overlap"] for q in pairs])), 3)
        if pairs else None,
        "median_mae_y": round(float(np.median([q["mae_y"] for q in pairs
                                               if q["mae_y"] is not None])), 2)
        if any(q["mae_y"] is not None for q in pairs) else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    model = load_model(MODEL_DIR, args.device)
    rows = []
    for name in sorted(p.name for p in PROBE.glob("*.png")):
        r = evaluate(name, model, args.device)
        if r is None:
            continue
        rows.append(r)
        ov = "-" if r["median_overlap"] is None else f"{r['median_overlap']:.2f}"
        mae = "-" if r["median_mae_y"] is None else f"{r['median_mae_y']:.1f}"
        print(f"gold={r['n_gold']:2d} pred={r['n_pred']:2d} "
              f"overlap={ov:>4} mae_y={mae:>5}px  {r['image']}")

    paired = [q for r in rows for q in r["pairs"] if q["mae_y"] is not None]
    tight = [q for q in paired if q["overlap"] >= 0.95 and q["mae_y"] <= 1.0]
    summary = {
        "images": len(rows),
        "lines_paired": len(paired),
        "lines_tight (overlap>=0.95, mae<=1px)": len(tight),
        "median_overlap": round(float(np.median([q["overlap"] for q in paired])), 3)
        if paired else None,
        "median_mae_y": round(float(np.median([q["mae_y"] for q in paired])), 2)
        if paired else None,
    }
    print("\n" + json.dumps(summary, indent=1))
    REPORT.write_text(json.dumps({"summary": summary, "per_image": rows}, indent=1))
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
