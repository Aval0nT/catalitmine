"""viz_traces.py — overlay LineFormer-extracted traces on a figure + test
input-contrast preprocessing for the light-colour trace-dropout problem.

The probe review flagged that very pale lines (the middle of a blue→red
gradient, faint pastel series) are dropped: low contrast against the white
page → weak mask logits → cut at the score threshold. This harness runs the
HF LineFormer on a figure, draws each recovered trace in a distinct colour
over a faded copy of the original, and reports the trace count — with an
optional preprocessing pass so we can measure whether contrast enhancement
recovers the missing pale lines BEFORE wiring it into the backend.

Preprocessing modes (--prep):
  none    raw image (baseline)
  clahe   CLAHE on the L channel in LAB (local luminance contrast)
  sat     boost HSV saturation (pale pastel → vivid; pale lines gain colour)
  satclahe  saturation boost then CLAHE (both)

Run:
  venv/bin/python scripts/extraction/lineformer_port/viz_traces.py \
    --image figures/all_charts/<slug>/<fig>.png --prep none --out /tmp/before.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from line_postproc import masks_to_dataseries
from lineformer_hf_infer import get_instance_masks, load_model


def preprocess(img_bgr: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return img_bgr
    out = img_bgr
    if mode in ("sat", "satclahe"):
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * 1.8, 0, 255)  # 1.8× saturation
        out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    if mode in ("clahe", "satclahe"):
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        lab[..., 0] = clahe.apply(lab[..., 0])
        out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return out


# distinct overlay colours (BGR), high-contrast cycle
PALETTE = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 200, 255), (255, 0, 255),
           (255, 200, 0), (128, 0, 255), (0, 128, 255), (0, 255, 128), (255, 128, 0)]


def overlay(img_bgr: np.ndarray, series: list[list[dict]]) -> np.ndarray:
    canvas = (img_bgr.astype(np.float32) * 0.35 + 255 * 0.65).astype(np.uint8)  # fade
    for i, line in enumerate(series):
        if len(line) < 2:
            continue
        pts = np.array([[p["x"], p["y"]] for p in line], np.int32)
        cv2.polylines(canvas, [pts], False, PALETTE[i % len(PALETTE)], 2, cv2.LINE_AA)
    return canvas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--prep", default="none",
                    choices=["none", "clahe", "sat", "satclahe"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--score", type=float, default=0.3)
    args = ap.parse_args()

    model = load_model(ROOT / "models" / "lineformer_hf")
    raw = cv2.imread(args.image)
    if raw is None:
        raise SystemExit(f"unreadable: {args.image}")
    prepped = preprocess(raw, args.prep)
    masks, scores = get_instance_masks(model, prepped, score_thr=args.score)
    series = masks_to_dataseries(masks)
    n = sum(1 for s in series if len(s) >= 5)
    # overlay on the ORIGINAL (so the trace placement is judged against the
    # real figure, not the contrast-boosted one)
    out = overlay(raw, series)
    cv2.imwrite(args.out, out)
    print(f"prep={args.prep:9} traces={n:2d}  scores="
          f"{', '.join(f'{s:.2f}' for s in scores[:14])}")
    print(f"  -> {args.out}")


if __name__ == "__main__":
    main()
