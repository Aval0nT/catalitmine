"""parity_probe.py — HF-ported LineFormer vs the 30 Modal probe goldens.

Golden reference: figures/lineformer_probe_results/output/<img>/lineformer/
coordinates.json — the mmdet pipeline's post-processed line points
(skeleton keypoints every 10 px + linear interpolation, original-image
pixel coordinates). Phase 2 compares at the MASK level (line_utils is not
ported yet), which the goldens still pin down tightly:

  per image   n_pred (score>0.3) vs n_gold lines
  per line    coverage = fraction of golden points lying inside a predicted
              mask (±1 px tolerance: interpolated points can graze the mask
              edge on curvature). 'union' uses all masks; 'matched' uses
              greedy 1-1 assignment, so merged/split instances show up.

Run:  venv/bin/python scripts/extraction/lineformer_port/parity_probe.py [--device cpu]
Out:  figures/lineformer_probe_results/hf_parity_report.json + console table
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

from lineformer_hf_infer import get_instance_masks, load_model  # noqa: E402

MODEL_DIR = ROOT / "models" / "lineformer_hf"
PROBE = ROOT / "figures" / "lineformer_probe"
GOLD = ROOT / "figures" / "lineformer_probe_results" / "output"
REPORT = ROOT / "figures" / "lineformer_probe_results" / "hf_parity_report.json"
TOL = 1  # px window half-width for point-in-mask


def point_covered(mask: np.ndarray, x: int, y: int) -> bool:
    h, w = mask.shape
    y0, y1 = max(0, y - TOL), min(h, y + TOL + 1)
    x0, x1 = max(0, x - TOL), min(w, x + TOL + 1)
    return bool(mask[y0:y1, x0:x1].any())


def line_coverage(mask: np.ndarray, line: list[dict]) -> float:
    if not line:
        return 1.0
    hits = sum(point_covered(mask, pt["x"], pt["y"]) for pt in line)
    return hits / len(line)


def evaluate(img_name: str, model, device: str) -> dict | None:
    gold_path = GOLD / img_name / "lineformer" / "coordinates.json"
    img_path = PROBE / img_name
    if not gold_path.exists() or not img_path.exists():
        return None
    gold = json.load(open(gold_path))
    img = cv2.imread(str(img_path))
    masks, scores = get_instance_masks(model, img, score_thr=0.3, device=device)

    union = masks.any(axis=0) if len(masks) else np.zeros(img.shape[:2], bool)
    union_cov = [line_coverage(union, ln) for ln in gold]

    # greedy 1-1: best (gold, mask) pairs first, each side used once
    pairs = sorted(
        ((line_coverage(masks[m], gold[g]), g, m)
         for g in range(len(gold)) for m in range(len(masks))),
        reverse=True,
    )
    matched_cov, used_g, used_m = {}, set(), set()
    for cov, g, m in pairs:
        if g in used_g or m in used_m:
            continue
        matched_cov[g] = cov
        used_g.add(g)
        used_m.add(m)
    matched = [matched_cov.get(g, 0.0) for g in range(len(gold))]

    return {
        "image": img_name,
        "n_gold": len(gold),
        "n_pred": int(len(masks)),
        "scores": [round(float(s), 3) for s in scores],
        "union_coverage": [round(c, 3) for c in union_cov],
        "matched_coverage": [round(c, 3) for c in matched],
        "mean_union": round(float(np.mean(union_cov)), 3) if union_cov else None,
        "mean_matched": round(float(np.mean(matched)), 3) if matched else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--limit", type=int, default=None, help="first N images only")
    args = ap.parse_args()

    model = load_model(MODEL_DIR, args.device)
    images = sorted(p.name for p in PROBE.glob("*.png"))
    if args.limit:
        images = images[: args.limit]

    rows = []
    for name in images:
        r = evaluate(name, model, args.device)
        if r is None:
            print(f"{'(no golden)':>12}  {name}")
            continue
        rows.append(r)
        mu = "-" if r["mean_union"] is None else f"{r['mean_union']:.2f}"
        mm = "-" if r["mean_matched"] is None else f"{r['mean_matched']:.2f}"
        flag = "OK " if r["n_pred"] == r["n_gold"] else "DIFF"
        print(f"{flag} gold={r['n_gold']:2d} pred={r['n_pred']:2d} "
              f"union={mu:>4} matched={mm:>4}  {r['image']}")

    with_lines = [r for r in rows if r["n_gold"] > 0]
    count_match = sum(r["n_pred"] == r["n_gold"] for r in rows)
    summary = {
        "images": len(rows),
        "count_match": count_match,
        "mean_union_coverage": round(
            float(np.mean([r["mean_union"] for r in with_lines])), 4),
        "mean_matched_coverage": round(
            float(np.mean([r["mean_matched"] for r in with_lines])), 4),
    }
    print(f"\ninstance-count match: {count_match}/{len(rows)} | "
          f"union coverage: {summary['mean_union_coverage']:.3f} | "
          f"matched coverage: {summary['mean_matched_coverage']:.3f}")

    REPORT.write_text(json.dumps({"summary": summary, "per_image": rows}, indent=1))
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
